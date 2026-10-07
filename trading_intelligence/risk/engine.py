"""
Deterministic, non-bypassable risk engine. Per docs/RISK_ENGINE_SPEC.md.

The risk engine has veto on every order. There is no override path, no
"force" flag, no emergency bypass. Claude/strategy layers cannot bypass it.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Optional

from trading_intelligence.monitoring.alerts import AlertSink, LoggingAlertSink
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.risk.models import RiskConfig, RiskState
from trading_intelligence.strategy.models import RiskDecision, TradeProposal

logger = logging.getLogger(__name__)

# Reject reason codes — exact strings per spec's audit log schema.
REASON_OK = "OK"
REASON_KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
REASON_DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
REASON_DRAWDOWN_PAUSE_ACTIVE = "DRAWDOWN_PAUSE_ACTIVE"
REASON_NO_STOP_LOSS_DEFINED = "NO_STOP_LOSS_DEFINED"
REASON_INVALID_REFERENCE_PRICE = "INVALID_REFERENCE_PRICE"
REASON_INVALID_STOP_PRICE = "INVALID_STOP_PRICE"
REASON_INVALID_STOP_DIRECTION = "INVALID_STOP_DIRECTION"
REASON_STOP_TOO_TIGHT = "STOP_TOO_TIGHT"
REASON_DAILY_TURNOVER_LIMIT_EXCEEDED = "DAILY_TURNOVER_LIMIT_EXCEEDED"
REASON_POSITION_SIZE_ZERO = "POSITION_SIZE_ZERO"
REASON_MAX_POSITIONS_REACHED = "MAX_POSITIONS_REACHED"
REASON_DAILY_TRADE_LIMIT_REACHED = "DAILY_TRADE_LIMIT_REACHED"
REASON_EXPOSURE_LIMIT_EXCEEDED = "EXPOSURE_LIMIT_EXCEEDED"
REASON_CORRELATED_EXPOSURE_EXCEEDED = "CORRELATED_EXPOSURE_EXCEEDED"
REASON_MAX_POSITION_SIZE_EXCEEDED = "MAX_POSITION_SIZE_EXCEEDED"
# Fill-time vetoes: the order was approved against a reference price, but a
# MARKET entry fills at the NEXT bar's open, which can have gapped away.
REASON_FILL_AT_OR_BELOW_STOP = "FILL_AT_OR_BELOW_STOP"
REASON_FILL_EXCEEDS_POSITION_CAP = "FILL_EXCEEDS_POSITION_CAP"
REASON_FILL_RISK_EXCEEDS_BUDGET = "FILL_RISK_EXCEEDS_BUDGET"


class RiskEngine:
    """
    Synchronous gate. Every TradeProposal must pass validate_order() before
    any order reaches an exchange adapter (paper or live).

    Thread-safe: all state mutation is protected by a single lock.
    """

    def __init__(
        self,
        config: RiskConfig,
        state_path: Path,
        audit_log: AuditLog,
        alert_sink: Optional[AlertSink] = None,
    ):
        self.config = config
        self.state_path = Path(state_path)
        self.audit_log = audit_log
        self.alert_sink = alert_sink or LoggingAlertSink()
        self._lock = threading.Lock()

        self.state = RiskState.load(self.state_path)
        if self.state.kill_switch:
            logger.warning(
                "RiskEngine starting with kill_switch ACTIVE (reason: %s) — "
                "persisted from previous session",
                self.state.kill_switch_reason,
            )
        if config.kill_switch_active and not self.state.kill_switch:
            self._set_kill_switch(True, "kill_switch_active=true in config at startup")

    # ------------------------------------------------------------------
    # Kill switch (manual + automatic)
    # ------------------------------------------------------------------

    def activate_kill_switch(self, reason: str) -> None:
        """Operator/owner or automatic trigger. No bypass once active."""
        with self._lock:
            self._set_kill_switch(True, reason)

    def clear_kill_switch(self, operator_confirmation: bool = False) -> None:
        """Requires explicit manual operator action — never automatic."""
        if not operator_confirmation:
            raise ValueError(
                "clear_kill_switch requires operator_confirmation=True — "
                "this is a safety gate, not a formality"
            )
        with self._lock:
            self._set_kill_switch(False, "")

    def _set_kill_switch(self, active: bool, reason: str) -> None:
        self.state.kill_switch = active
        self.state.kill_switch_reason = reason
        self.state.save(self.state_path)
        if active:
            logger.error("KILL SWITCH ACTIVATED: %s", reason)
            self.alert_sink.send("CRITICAL", "KILL_SWITCH_ACTIVATED", {"reason": reason})
        else:
            logger.warning("Kill switch cleared by operator")

    def check_connectivity(self, is_connected: bool, now: Optional[datetime] = None) -> None:
        """
        Call periodically from the exchange adapter's heartbeat. Auto-triggers
        the kill switch if connectivity has been down > max_connectivity_gap_seconds.
        """
        now = now or datetime.now(timezone.utc)
        with self._lock:
            if is_connected:
                self.state.last_connectivity_ok_at = now.isoformat()
                self.state.save(self.state_path)
                return

            if self.state.last_connectivity_ok_at is None:
                self.state.last_connectivity_ok_at = now.isoformat()
                self.state.save(self.state_path)
                return

            last_ok = datetime.fromisoformat(self.state.last_connectivity_ok_at)
            gap = (now - last_ok).total_seconds()
            if gap > self.config.max_connectivity_gap_seconds and not self.state.kill_switch:
                self._set_kill_switch(
                    True,
                    f"Connectivity lost for {gap:.0f}s (> {self.config.max_connectivity_gap_seconds}s)",
                )

    # ------------------------------------------------------------------
    # Daily reset / drawdown bookkeeping
    # ------------------------------------------------------------------

    def _today_str(self, now: datetime) -> str:
        return now.date().isoformat()

    def _maybe_roll_day(self, equity: Decimal, now: datetime) -> None:
        today = self._today_str(now)
        if self.state.current_day != today:
            self.state.current_day = today
            self.state.equity_at_day_start = str(equity)
            self.state.daily_realized_pnl = "0"
            self.state.daily_trade_count = 0
            self.state.daily_turnover = "0"
            self.state.trading_day_halted = False
            self.state.save(self.state_path)

    def _update_drawdown(self, equity: Decimal, now: datetime) -> Decimal:
        today = self._today_str(now)
        history = [(d, Decimal(v)) for d, v in self.state.equity_history]
        # One entry per day holding that day's highest equity: the peak is the
        # only thing this history is used for, and observe_equity() calls this
        # on every bar, so appending per call would grow the list (and the
        # JSON rewritten on every save) without bound within a day.
        for i, (d, v) in enumerate(history):
            if d == today:
                history[i] = (d, max(v, equity))
                break
        else:
            history.append((today, equity))

        cutoff = now.date().toordinal() - self.config.drawdown_lookback_days
        history = [(d, v) for d, v in history if date.fromisoformat(d).toordinal() >= cutoff]
        self.state.equity_history = [[d, str(v)] for d, v in history]

        peak = max((v for _, v in history), default=equity)
        if peak <= 0:
            drawdown_pct = Decimal("0")
        else:
            drawdown_pct = (peak - equity) / peak * 100

        if drawdown_pct >= Decimal(str(self.config.drawdown_halt_pct)):
            if not self.state.kill_switch:
                self._set_kill_switch(
                    True, f"Drawdown halt: {drawdown_pct:.2f}% >= {self.config.drawdown_halt_pct}%"
                )
                self._audit_event("DRAWDOWN_HALT_TRIGGERED", drawdown_pct=float(drawdown_pct))
                self.alert_sink.send("CRITICAL", "DRAWDOWN_HALT_TRIGGERED", {"drawdown_pct": float(drawdown_pct)})
        elif drawdown_pct >= Decimal(str(self.config.drawdown_pause_pct)):
            if not self.state.drawdown_paused:
                self._audit_event("DRAWDOWN_PAUSE_TRIGGERED", drawdown_pct=float(drawdown_pct))
                self.alert_sink.send("WARNING", "DRAWDOWN_PAUSE_TRIGGERED", {"drawdown_pct": float(drawdown_pct)})
            self.state.drawdown_paused = True
        else:
            self.state.drawdown_paused = False

        self.state.save(self.state_path)
        return drawdown_pct

    def _audit_event(self, event: str, **fields) -> None:
        self.audit_log.append({"event": event, **fields})

    # ------------------------------------------------------------------
    # Position registration (called by execution layer on fill/close)
    # ------------------------------------------------------------------

    def register_position_opened(self, position_id: str, symbol: str, notional_value: Decimal) -> None:
        with self._lock:
            self.state.open_positions[position_id] = {
                "symbol": symbol,
                "notional_value": str(notional_value),
            }
            self.state.daily_trade_count += 1
            self.state.daily_turnover = str(Decimal(self.state.daily_turnover) + notional_value)
            self.state.save(self.state_path)

    def register_position_closed(self, position_id: str, realized_pnl: Decimal) -> None:
        with self._lock:
            self.state.open_positions.pop(position_id, None)
            self.state.daily_realized_pnl = str(Decimal(self.state.daily_realized_pnl) + realized_pnl)
            self.state.save(self.state_path)

    # A position is approved on one bar and only fills (and would only register)
    # on the next. Without a reservation, every symbol approved on the same
    # bar sees the same "nothing open" books, so together they can exceed
    # max_open_positions, total exposure, correlated exposure and turnover.
    # Reserved entries count toward every one of those limits immediately.

    def reserve_position(self, reservation_id: str, symbol: str, notional_value: Decimal) -> None:
        with self._lock:
            # "day" ties the reservation's trade-count/turnover charge to the
            # day that was current when it was made. The daily counters reset
            # at day roll, so a reservation that outlives its day must not
            # later debit (release) or under-charge (confirm) the NEW day.
            self.state.open_positions[reservation_id] = {
                "symbol": symbol, "notional_value": str(notional_value), "reserved": True,
                "day": self.state.current_day,
            }
            self.state.daily_trade_count += 1
            self.state.daily_turnover = str(Decimal(self.state.daily_turnover) + notional_value)
            self.state.save(self.state_path)

    def _reservation_in_current_day(self, info: dict) -> bool:
        # Reservations persisted before "day" existed are treated as same-day.
        return info.get("day", self.state.current_day) == self.state.current_day

    def confirm_reservation(
        self, reservation_id: str, position_id: str, symbol: str, actual_notional: Decimal,
    ) -> None:
        """The reserved entry filled: swap the reservation for the real position
        and true-up turnover to the actual notional. An unknown reservation is
        treated as a fresh open so exposure is never under-counted. A
        reservation made on an EARLIER day charges the whole fill to the
        current day (the day it executed), since its own charge was reset."""
        with self._lock:
            reserved = self.state.open_positions.pop(reservation_id, None)
            if reserved is None or not self._reservation_in_current_day(reserved):
                self.state.daily_trade_count += 1
                reserved_notional = Decimal("0")
            else:
                reserved_notional = Decimal(reserved["notional_value"])
            self.state.open_positions[position_id] = {
                "symbol": symbol, "notional_value": str(actual_notional),
            }
            self.state.daily_turnover = str(
                max(Decimal("0"), Decimal(self.state.daily_turnover) + actual_notional - reserved_notional)
            )
            self.state.save(self.state_path)

    def release_reservation(self, reservation_id: str) -> bool:
        """The reserved entry never filled: give back its slot, exposure,
        trade count and turnover. Returns False if no such reservation. A
        reservation from an earlier day frees its slot and exposure but gives
        nothing back to today's counters (it never counted there)."""
        with self._lock:
            info = self.state.open_positions.get(reservation_id)
            if info is None or not info.get("reserved"):
                return False
            del self.state.open_positions[reservation_id]
            if self._reservation_in_current_day(info):
                self.state.daily_trade_count = max(0, self.state.daily_trade_count - 1)
                self.state.daily_turnover = str(
                    max(Decimal("0"), Decimal(self.state.daily_turnover) - Decimal(info["notional_value"]))
                )
            self.state.save(self.state_path)
            return True

    def reservation_ids(self) -> list[str]:
        return [pid for pid, info in self.state.open_positions.items() if info.get("reserved")]

    @property
    def open_position_count(self) -> int:
        return len(self.state.open_positions)

    def _exposure_value(self, info: dict) -> Decimal:
        """What one open position counts for toward the exposure caps."""
        notional = Decimal(info["notional_value"])
        if self.config.exposure_basis == "entry_or_market" and not info.get("reserved") and "mark_value" in info:
            return max(notional, Decimal(info["mark_value"]))
        return notional

    @property
    def total_open_exposure(self) -> Decimal:
        return sum((self._exposure_value(p) for p in self.state.open_positions.values()), Decimal("0"))

    def _correlated_exposure(self, symbol: str) -> Decimal:
        """
        Simplified correlation model: positions in the SAME symbol are treated
        as correlated. A full correlation matrix (cross-asset) is a future
        enhancement — not yet implemented pending real market data.
        """
        return sum(
            (self._exposure_value(p) for p in self.state.open_positions.values() if p["symbol"] == symbol),
            Decimal("0"),
        )

    def update_marks(self, values: dict[str, Decimal]) -> None:
        """Latest market value per REGISTERED position id. Only used when
        exposure_basis is "entry_or_market"; otherwise a no-op, so the default
        state is byte-for-byte what it always was."""
        if self.config.exposure_basis != "entry_or_market":
            return
        with self._lock:
            changed = False
            for position_id, value in values.items():
                info = self.state.open_positions.get(position_id)
                if info is None or info.get("reserved"):
                    continue
                if info.get("mark_value") != str(value):
                    info["mark_value"] = str(value)
                    changed = True
            if changed:
                self.state.save(self.state_path)

    # ------------------------------------------------------------------
    # Equity observation — halts must not depend on a new signal arriving
    # ------------------------------------------------------------------

    def advance_clock(self, equity: Decimal, now: datetime) -> None:
        """Roll the trading day to `now` BEFORE the bar's fills are accounted.
        `equity` is the last mark before this bar, i.e. the day's true starting
        equity. Without this the day rolled inside observe_equity(), after
        confirm_reservation() had already charged a midnight fill to the old
        day (the roll then erased it), and the day-start equity was taken
        after the first bar's P&L, which blinded the daily loss limit on
        one-bar-per-day data."""
        with self._lock:
            self._maybe_roll_day(equity, now)

    def entry_block_reason(self) -> Optional[str]:
        """Why a NEW entry must not execute right now (state gates 1-3 of
        validate_order), or None. For an entry that was approved on an earlier
        bar and has not filled yet: a halt that began in between must stop it."""
        with self._lock:
            if self.state.kill_switch:
                return REASON_KILL_SWITCH_ACTIVE
            if self.state.trading_day_halted:
                return REASON_DAILY_LOSS_LIMIT_REACHED
            if self.state.drawdown_paused:
                return REASON_DRAWDOWN_PAUSE_ACTIVE
            return None

    def validate_fill(
        self, quantity: Decimal, stop_price: Decimal, fill_price: Decimal, equity: Decimal,
    ) -> Optional[str]:
        """Re-check an approved MARKET entry against the price it would
        ACTUALLY fill at. Returns a veto reason, or None to let it fill.
        Approval used the last close; the fill is the next open, and a gap can
        multiply the risk the engine thought it was approving. Checked: the
        fill is still above the stop, the position stays within the single
        position cap, and the loss at the stop stays within the per-trade risk
        budget plus `max_fill_risk_overshoot_pct`."""
        with self._lock:
            if fill_price <= stop_price:
                reason: Optional[str] = REASON_FILL_AT_OR_BELOW_STOP
            elif quantity * fill_price > equity * Decimal(str(self.config.max_position_size_pct)) / 100:
                reason = REASON_FILL_EXCEEDS_POSITION_CAP
            else:
                fee_rate = (
                    Decimal(str(self.config.taker_fee_rate)) if self.config.include_fees_in_risk_calc
                    else Decimal("0")
                )
                loss_at_stop = quantity * (fill_price - stop_price) + 2 * fee_rate * quantity * fill_price
                budget = equity * Decimal(str(self.config.max_risk_per_trade_pct)) / 100
                allowed = budget * (1 + Decimal(str(self.config.max_fill_risk_overshoot_pct)) / 100)
                reason = REASON_FILL_RISK_EXCEEDS_BUDGET if loss_at_stop > allowed else None
            if reason is not None:
                self._audit_event(
                    "FILL_VETOED", reason=reason, quantity=str(quantity), stop_price=str(stop_price),
                    fill_price=str(fill_price), equity=str(equity),
                )
            return reason

    def observe_equity(self, equity: Decimal, now: Optional[datetime] = None) -> None:
        """
        Mark-to-market observation. Call on every bar, whether or not a trade
        is proposed. Drawdown and the daily loss limit were previously only
        evaluated inside validate_order(), i.e. only when a NEW signal
        arrived: a position bleeding through a crash with no fresh signals
        never tripped the halt, and a drawdown that recovered before the next
        signal was never seen at all. A tripped halt only blocks new entries
        (it never touches open positions), so observing more often can only
        make the system more conservative.
        """
        now = now or datetime.now(timezone.utc)
        with self._lock:
            self._refresh_risk_state(equity, now)

    def _refresh_risk_state(self, equity: Decimal, now: datetime) -> tuple[Decimal, Decimal, Decimal]:
        """Caller must hold self._lock. Returns (daily_pnl, daily_loss_pct, drawdown_pct)."""
        self._maybe_roll_day(equity, now)
        drawdown_pct = self._update_drawdown(equity, now)

        # Daily loss limit check (uses realized + mark-to-market equity delta)
        equity_at_day_start = Decimal(self.state.equity_at_day_start)
        daily_pnl = equity - equity_at_day_start
        if equity_at_day_start > 0:
            daily_loss_pct = daily_pnl / equity_at_day_start * 100
        else:
            daily_loss_pct = Decimal("0")

        if daily_pnl < 0 and abs(daily_loss_pct) >= Decimal(str(self.config.daily_loss_limit_pct)):
            if not self.state.trading_day_halted:
                self._audit_event("DAILY_LOSS_LIMIT_REACHED", daily_loss_pct=float(daily_loss_pct))
                self.alert_sink.send("WARNING", "DAILY_LOSS_LIMIT_REACHED",
                                      {"daily_loss_pct": float(daily_loss_pct)})
            self.state.trading_day_halted = True
            self.state.save(self.state_path)
        return daily_pnl, daily_loss_pct, drawdown_pct

    # ------------------------------------------------------------------
    # Core gate
    # ------------------------------------------------------------------

    def validate_order(
        self,
        proposal: TradeProposal,
        equity: Decimal,
        reference_price: Decimal,
        now: Optional[datetime] = None,
    ) -> RiskDecision:
        """
        Runs the full 11-step validation sequence from docs/RISK_ENGINE_SPEC.md.
        First failure wins. Every call — approve or reject — is audit logged.
        """
        now = now or datetime.now(timezone.utc)

        with self._lock:
            daily_pnl, daily_loss_pct, drawdown_pct = self._refresh_risk_state(equity, now)

            # --- Step 1: kill switch ---
            if self.state.kill_switch:
                return self._reject(proposal, REASON_KILL_SWITCH_ACTIVE, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct)

            # --- Step 2: daily loss halt ---
            if self.state.trading_day_halted:
                return self._reject(proposal, REASON_DAILY_LOSS_LIMIT_REACHED, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct)

            # --- Step 3: drawdown pause ---
            if self.state.drawdown_paused:
                return self._reject(proposal, REASON_DRAWDOWN_PAUSE_ACTIVE, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct)

            # --- Step 4: stop loss presence ---
            if proposal.stop_price is None:
                return self._reject(proposal, REASON_NO_STOP_LOSS_DEFINED, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct)

            entry_price = proposal.entry_price if proposal.entry_price is not None else reference_price
            if entry_price <= 0:
                return self._reject(proposal, REASON_INVALID_REFERENCE_PRICE, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct)

            # --- Step 4b/4c: stop price sanity ---
            # Found by GPT Work's independent review: abs(entry - stop) below
            # treats direction as irrelevant, so a non-positive stop or a
            # stop placed on the wrong side of entry passed as long as its
            # absolute distance wasn't "too tight". TradeProposal.side is
            # spot-only BUY (long-only, per its own type) — a stop that
            # protects a long position must be strictly below entry.
            if proposal.stop_price <= 0:
                return self._reject(proposal, REASON_INVALID_STOP_PRICE, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct)
            if proposal.stop_price >= entry_price:
                return self._reject(proposal, REASON_INVALID_STOP_DIRECTION, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct)

            stop_distance_pct = abs(entry_price - proposal.stop_price) / entry_price * 100

            # --- Step 5: stop too tight ---
            if stop_distance_pct <= Decimal(str(self.config.min_stop_distance_pct)):
                return self._reject(proposal, REASON_STOP_TOO_TIGHT, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct, stop_distance_pct=stop_distance_pct)

            # --- Step 6: position sizing (fixed fractional) ---
            quantity, position_value = self._size_position(equity, entry_price, proposal.stop_price)

            # --- Step 7: position size > 0 ---
            if quantity <= 0:
                return self._reject(proposal, REASON_POSITION_SIZE_ZERO, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct, stop_distance_pct=stop_distance_pct)

            # Hard cap: single position size
            max_position_value = equity * Decimal(str(self.config.max_position_size_pct)) / 100
            if position_value > max_position_value:
                return self._reject(proposal, REASON_MAX_POSITION_SIZE_EXCEEDED, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct, stop_distance_pct=stop_distance_pct,
                                     position_value=position_value)

            # --- Step 8: max open positions ---
            if self.open_position_count >= self.config.max_open_positions:
                return self._reject(proposal, REASON_MAX_POSITIONS_REACHED, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct, stop_distance_pct=stop_distance_pct,
                                     position_value=position_value)

            # --- Step 9: daily trade count ---
            if self.state.daily_trade_count >= self.config.max_trades_per_day:
                return self._reject(proposal, REASON_DAILY_TRADE_LIMIT_REACHED, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct, stop_distance_pct=stop_distance_pct,
                                     position_value=position_value)

            # --- Step 9b: daily turnover limit ---
            # Found by GPT Work's independent review: max_daily_turnover_pct
            # has existed in RiskConfig since the start, and daily_turnover
            # is tracked (register_position_opened), but validate_order()
            # never actually checked one against the other — a configured
            # hard limit that silently enforced nothing.
            new_daily_turnover = Decimal(self.state.daily_turnover) + position_value
            max_daily_turnover = equity * Decimal(str(self.config.max_daily_turnover_pct)) / 100
            if new_daily_turnover > max_daily_turnover:
                return self._reject(proposal, REASON_DAILY_TURNOVER_LIMIT_EXCEEDED, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct, stop_distance_pct=stop_distance_pct,
                                     position_value=position_value)

            # --- Step 10: total exposure limit ---
            new_total_exposure = self.total_open_exposure + position_value
            max_total_exposure = equity * Decimal(str(self.config.max_total_exposure_pct)) / 100
            if new_total_exposure > max_total_exposure:
                return self._reject(proposal, REASON_EXPOSURE_LIMIT_EXCEEDED, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct, stop_distance_pct=stop_distance_pct,
                                     position_value=position_value)

            # --- Step 11: correlated exposure limit ---
            new_correlated_exposure = self._correlated_exposure(proposal.symbol) + position_value
            max_correlated_exposure = equity * Decimal(str(self.config.max_correlated_exposure_pct)) / 100
            if new_correlated_exposure > max_correlated_exposure:
                return self._reject(proposal, REASON_CORRELATED_EXPOSURE_EXCEEDED, equity, daily_pnl,
                                     daily_loss_pct, drawdown_pct, stop_distance_pct=stop_distance_pct,
                                     position_value=position_value)

            # --- Step 12: APPROVE ---
            return self._approve(proposal, quantity, equity, daily_pnl, daily_loss_pct,
                                  drawdown_pct, stop_distance_pct, position_value)

    def _size_position(
        self, equity: Decimal, entry_price: Decimal, stop_price: Decimal
    ) -> tuple[Decimal, Decimal]:
        risk_amount = equity * Decimal(str(self.config.max_risk_per_trade_pct)) / 100
        stop_distance_pct = abs(entry_price - stop_price) / entry_price
        fee_rate = Decimal(str(self.config.taker_fee_rate)) if self.config.include_fees_in_risk_calc else Decimal("0")
        effective_stop_distance = stop_distance_pct + (2 * fee_rate)
        if effective_stop_distance <= 0:
            return Decimal("0"), Decimal("0")
        quantity = risk_amount / (entry_price * effective_stop_distance)
        quantity = quantity.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        position_value = quantity * entry_price
        return quantity, position_value

    def _reject(
        self,
        proposal: TradeProposal,
        reason: str,
        equity: Decimal,
        daily_pnl: Decimal,
        daily_loss_pct: Decimal,
        drawdown_pct: Decimal,
        stop_distance_pct: Optional[Decimal] = None,
        position_value: Optional[Decimal] = None,
    ) -> RiskDecision:
        self._log_decision(proposal, "REJECTED", reason, equity, daily_pnl, daily_loss_pct,
                            drawdown_pct, Decimal("0"), stop_distance_pct, position_value)
        return RiskDecision(approved=False, reason=reason, quantity=None, proposal_id=proposal.proposal_id)

    def _approve(
        self,
        proposal: TradeProposal,
        quantity: Decimal,
        equity: Decimal,
        daily_pnl: Decimal,
        daily_loss_pct: Decimal,
        drawdown_pct: Decimal,
        stop_distance_pct: Decimal,
        position_value: Decimal,
    ) -> RiskDecision:
        self._log_decision(proposal, "APPROVED", REASON_OK, equity, daily_pnl, daily_loss_pct,
                            drawdown_pct, quantity, stop_distance_pct, position_value)
        return RiskDecision(approved=True, reason=REASON_OK, quantity=quantity, proposal_id=proposal.proposal_id)

    def _log_decision(
        self,
        proposal: TradeProposal,
        decision: str,
        reason: str,
        equity: Decimal,
        daily_pnl: Decimal,
        daily_loss_pct: Decimal,
        drawdown_pct: Decimal,
        approved_quantity: Decimal,
        stop_distance_pct: Optional[Decimal],
        position_value: Optional[Decimal],
    ) -> None:
        self.audit_log.append({
            "event": "RISK_DECISION",
            "decision": decision,
            "reason": reason,
            "order_id": proposal.proposal_id,
            "symbol": proposal.symbol,
            "side": proposal.side,
            "approved_quantity": str(approved_quantity),
            "entry_price": str(proposal.entry_price) if proposal.entry_price else None,
            "stop_price": str(proposal.stop_price),
            "stop_distance_pct": float(stop_distance_pct) if stop_distance_pct is not None else None,
            "position_value": str(position_value) if position_value is not None else None,
            "risk_pct": self.config.max_risk_per_trade_pct,
            "equity": str(equity),
            "daily_pnl": str(daily_pnl),
            "daily_pnl_pct": float(daily_loss_pct),
            "drawdown_pct": float(drawdown_pct),
            "open_positions": self.open_position_count,
            "kill_switch": self.state.kill_switch,
        })
