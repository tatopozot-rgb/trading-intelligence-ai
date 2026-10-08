"""
PAPER / SHADOW copy follower: turns leader events into simulated orders with what
copying costs in reality, and journals every decision with its reason.

Realism: our fill happens `latency_seconds` after the leader's event, at the price
then, plus adverse slippage and the taker fee; quantities are floored to the step
size; orders under the exchange minimum notional are skipped (decisive at small
capital); unaffordable buys are cut to the cash available; injected order failures
are journaled and healed by the next leader event (targets, not deltas).

LIVE is not implemented here and cannot be enabled: the constructor refuses it. Live
order transport belongs to Claude Code local (Testnet first), behind the same policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Callable, Optional

from trading_intelligence.copy_trading import risk as R
from trading_intelligence.copy_trading.models import LeaderAction, LeaderEvent, Side
from trading_intelligence.copy_trading.risk import CopyDecision, CopyRiskPolicy, PositionView, loss_pct

PriceAt = Callable[[str, datetime], Decimal]
RegimeAt = Callable[[str, datetime], Optional[str]]
FailureAt = Callable[[str, datetime], Optional[str]]


class LiveTradingNotAuthorized(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionModel:
    fee_rate: Decimal = Decimal("0.001")  # Binance Spot taker, no BNB discount
    slippage_bps: Decimal = Decimal("5")
    latency_seconds: int = 30
    min_notional: Decimal = Decimal("5")  # live: read the NOTIONAL filter from exchangeInfo per symbol
    qty_step: Decimal = Decimal("0.00001")  # live: LOT_SIZE stepSize per symbol


@dataclass
class CopyPosition:
    trader_id: str
    symbol: str
    side: Side
    qty: Decimal
    avg_entry: Decimal
    fees: Decimal
    opened_at: str
    leader_entry: Decimal
    position_id: str


@dataclass
class LeaderBook:
    avg_entry: Decimal = Decimal("0")
    fraction: Decimal = Decimal("0")
    losing_adds: int = 0


@dataclass
class ClosedCopy:
    trader_id: str
    symbol: str
    qty: Decimal
    entry: Decimal
    exit: Decimal
    pnl: Decimal
    reason: str
    closed_at: str
    leader_entry: Decimal
    leader_exit: Optional[Decimal]  # None when we exited and the leader did not

    @property
    def our_return_pct(self) -> Decimal:
        return (self.exit - self.entry) / self.entry * 100

    @property
    def leader_return_pct(self) -> Optional[Decimal]:
        if self.leader_exit is None or self.leader_entry <= 0:
            return None
        return (self.leader_exit - self.leader_entry) / self.leader_entry * 100


@dataclass
class CopyFollower:
    policy: CopyRiskPolicy
    execution: ExecutionModel
    price_at: PriceAt
    starting_equity: Decimal
    mode: str = "PAPER"
    regime_at: Optional[RegimeAt] = None
    failure_at: Optional[FailureAt] = None
    cash: Decimal = field(init=False)
    positions: dict[tuple[str, str], CopyPosition] = field(default_factory=dict)
    leader_books: dict[tuple[str, str], LeaderBook] = field(default_factory=dict)
    followed: set[str] = field(default_factory=set)
    blocked: dict[str, str] = field(default_factory=dict)
    exited_until_leader_closes: set[tuple[str, str]] = field(default_factory=set)
    held_through_drawdown: set[str] = field(default_factory=set)  # position ids already journaled as held
    realized_by_trader: dict[str, Decimal] = field(default_factory=dict)
    closed: list[ClosedCopy] = field(default_factory=list)
    journal: list[dict] = field(default_factory=list)
    _seq: int = 0

    def __post_init__(self) -> None:
        if self.mode not in ("PAPER", "SHADOW"):
            raise LiveTradingNotAuthorized(
                f"mode {self.mode!r} refused: only PAPER and SHADOW exist here; LIVE needs the owner's "
                "limits and explicit authorization, and a reviewed live port (Claude Code local, Testnet first)"
            )
        self.cash = self.starting_equity

    # ------------------------------------------------------------------
    # Valuation
    # ------------------------------------------------------------------

    def _value(self, pos: CopyPosition, ts: datetime) -> Decimal:
        return pos.qty * self.price_at(pos.symbol, ts)

    def equity(self, ts: datetime) -> Decimal:
        return self.cash + sum((self._value(p, ts) for p in self.positions.values()), Decimal("0"))

    def exposure(self, ts: datetime, excluding: Optional[tuple[str, str]] = None) -> Decimal:
        return sum((self._value(p, ts) for k, p in self.positions.items() if k != excluding), Decimal("0"))

    def _log(self, ts: datetime, trader: str, symbol: str, source: str, decision: CopyDecision, **extra) -> None:
        self.journal.append({
            "ts": ts.isoformat(), "mode": self.mode, "trader": trader, "symbol": symbol, "source": source,
            "action": decision.action, "reason": decision.reason,
            "target_notional": str(decision.target_notional.quantize(Decimal("0.01"))),
            "equity": str(self.equity(ts).quantize(Decimal("0.0001"))),
            **{k: str(v) for k, v in extra.items()},
        })

    # ------------------------------------------------------------------
    # Selection changes
    # ------------------------------------------------------------------

    def apply_selection(self, ts: datetime, decisions: list) -> None:
        for d in decisions:
            if d.decision in ("ADD", "KEEP"):
                self.followed.add(d.trader_id)
            elif d.decision.startswith("REMOVE") or d.decision in ("REJECT", "NOT_SELECTED"):
                self.followed.discard(d.trader_id)
            if d.decision == "REMOVE_INVALIDATED":
                for key in [k for k in self.positions if k[0] == d.trader_id]:
                    self._exit(ts, key, f"TRADER_INVALIDATED:{','.join(d.reasons)}", "selection")

    # ------------------------------------------------------------------
    # Leader events
    # ------------------------------------------------------------------

    def on_event(self, event: LeaderEvent) -> None:
        key = (event.trader_id, event.symbol)
        fill_ts = event.ts
        self._advance_risk(fill_ts)
        book = self.leader_books.setdefault(key, LeaderBook())
        underwater = (
            book.fraction > 0 and book.avg_entry > 0
            and ((event.price < book.avg_entry) if event.side is Side.LONG else (event.price > book.avg_entry))
        )
        pos = self.positions.get(key)
        view = PositionView(self._value(pos, fill_ts), pos.avg_entry, pos.side) if pos else None
        decision = self.policy.on_leader_event(
            event, self.equity(fill_ts), view,
            trader_followed=event.trader_id in self.followed,
            trader_blocked=event.trader_id in self.blocked,
            leader_losing_adds=book.losing_adds, leader_underwater=underwater,
            exposure_excluding_this=self.exposure(fill_ts, excluding=key),
            exited_until_leader_closes=key in self.exited_until_leader_closes,
        )
        self._update_leader_book(book, event, underwater)
        if event.action is LeaderAction.CLOSE:
            self.exited_until_leader_closes.discard(key)
            # We left earlier: record where the leader actually got out, to compare.
            for c in reversed(self.closed):
                if (c.trader_id, c.symbol) == key:
                    if c.leader_exit is None:
                        c.leader_exit = event.price
                    break

        if decision.action == R.BLOCK_TRADER:
            self.blocked[event.trader_id] = decision.reason
            self.followed.discard(event.trader_id)
            self._log(event.ts, event.trader_id, event.symbol, event.action.value, decision)
            for k in [k for k in self.positions if k[0] == event.trader_id]:
                self._exit(event.ts, k, f"TRADER_BLOCKED:{decision.reason}", "risk", leader_exit=None)
            return
        if decision.action == R.COPY_EXIT:
            self._exit(event.ts, key, decision.reason, event.action.value, leader_exit=event.price)
            return
        if decision.action in (R.COPY_OPEN, R.COPY_RESIZE):
            self._resize(event, key, decision)
            return
        self._log(event.ts, event.trader_id, event.symbol, event.action.value, decision)

    @staticmethod
    def _update_leader_book(book: LeaderBook, event: LeaderEvent, underwater: bool) -> None:
        if event.action is LeaderAction.CLOSE:
            book.avg_entry, book.fraction, book.losing_adds = Decimal("0"), Decimal("0"), 0
            return
        if event.action in (LeaderAction.OPEN, LeaderAction.INCREASE) and event.target_fraction > book.fraction:
            added = event.target_fraction - book.fraction
            book.avg_entry = (
                (book.avg_entry * book.fraction + event.price * added) / event.target_fraction
                if book.fraction > 0 else event.price
            )
            if event.action is LeaderAction.INCREASE and underwater:
                book.losing_adds += 1
        book.fraction = event.target_fraction

    def _fill_price(self, symbol: str, ts: datetime, buying: bool) -> tuple[datetime, Decimal]:
        from datetime import timedelta

        fill_ts = ts + timedelta(seconds=self.execution.latency_seconds)
        ref = self.price_at(symbol, fill_ts)
        slip = ref * self.execution.slippage_bps / Decimal("10000")
        return fill_ts, (ref + slip) if buying else (ref - slip)

    def _resize(self, event: LeaderEvent, key: tuple[str, str], decision: CopyDecision) -> None:
        pos = self.positions.get(key)
        buying = decision.target_notional > (self._value(pos, event.ts) if pos else Decimal("0"))
        fill_ts, price = self._fill_price(event.symbol, event.ts, buying)
        current_qty = pos.qty if pos else Decimal("0")
        target_qty = (decision.target_notional / price).quantize(self.execution.qty_step, rounding=ROUND_DOWN)
        delta = target_qty - current_qty
        if self.failure_at is not None:
            failure = self.failure_at(event.symbol, fill_ts)
            if failure:
                self._log(event.ts, event.trader_id, event.symbol, event.action.value,
                          CopyDecision("ORDER_FAILED", failure, decision.target_notional))
                return
        if delta == 0:
            self._log(event.ts, event.trader_id, event.symbol, event.action.value,
                      CopyDecision(R.HOLD, "ROUNDS_TO_NO_CHANGE", decision.target_notional))
            return
        if delta > 0:
            cost = delta * price
            fee = cost * self.execution.fee_rate
            if cost + fee > self.cash:
                affordable = (self.cash / (price * (1 + self.execution.fee_rate))).quantize(
                    self.execution.qty_step, rounding=ROUND_DOWN)
                delta, note = affordable, "|CUT_TO_CASH"
                cost, fee = delta * price, delta * price * self.execution.fee_rate
            else:
                note = ""
            if cost < self.execution.min_notional:
                self._log(event.ts, event.trader_id, event.symbol, event.action.value,
                          CopyDecision(R.SKIP, f"BELOW_MIN_NOTIONAL:{cost.quantize(Decimal('0.01'))}<"
                                               f"{self.execution.min_notional}{note}", decision.target_notional))
                return
            self.cash -= cost + fee
            if pos is None:
                self._seq += 1
                pos = CopyPosition(event.trader_id, event.symbol, event.side, delta, price, fee,
                                   fill_ts.isoformat(), self.leader_books[key].avg_entry, f"copy-{self._seq}")
                self.positions[key] = pos
                self.policy.engine.register_position_opened(pos.position_id, event.symbol, cost)
            else:
                pos.avg_entry = (pos.avg_entry * pos.qty + price * delta) / (pos.qty + delta)
                pos.qty += delta
                pos.fees += fee
                self.policy.engine.register_position_closed(pos.position_id, Decimal("0"))
                self.policy.engine.register_position_opened(pos.position_id, event.symbol, pos.qty * price)
            self._log(event.ts, event.trader_id, event.symbol, event.action.value,
                      CopyDecision(decision.action, decision.reason + note, decision.target_notional),
                      side="BUY", qty=delta, price=price.quantize(Decimal("0.00000001")),
                      fee=fee.quantize(Decimal("0.00000001")), fill_ts=fill_ts.isoformat())
            return
        # Reduce
        assert pos is not None
        sell_qty = -delta
        if target_qty * price < self.execution.min_notional:
            sell_qty = pos.qty  # what would remain is dust: sell all of it
        proceeds = sell_qty * price
        if proceeds < self.execution.min_notional:
            self._log(event.ts, event.trader_id, event.symbol, event.action.value,
                      CopyDecision(R.SKIP, "REDUCE_BELOW_MIN_NOTIONAL", decision.target_notional))
            return
        self._sell(event.ts, key, sell_qty, price, fill_ts, decision.reason, event.action.value, event.price
                   if sell_qty == pos.qty else None)

    def _sell(self, ts: datetime, key: tuple[str, str], qty: Decimal, price: Decimal, fill_ts: datetime,
              reason: str, source: str, leader_exit: Optional[Decimal]) -> None:
        pos = self.positions[key]
        proceeds = qty * price
        fee = proceeds * self.execution.fee_rate
        entry_fee_share = pos.fees * qty / pos.qty
        pnl = proceeds - fee - qty * pos.avg_entry - entry_fee_share
        self.cash += proceeds - fee
        self.realized_by_trader[pos.trader_id] = self.realized_by_trader.get(pos.trader_id, Decimal("0")) + pnl
        full = qty == pos.qty
        if full:
            del self.positions[key]
            self.policy.engine.register_position_closed(pos.position_id, pnl)
            self.closed.append(ClosedCopy(pos.trader_id, pos.symbol, qty, pos.avg_entry, price, pnl, reason,
                                          fill_ts.isoformat(), pos.leader_entry, leader_exit))
        else:
            pos.qty -= qty
            pos.fees -= entry_fee_share
            self.policy.engine.register_position_closed(pos.position_id, pnl)
            self.policy.engine.register_position_opened(pos.position_id, pos.symbol, pos.qty * pos.avg_entry)
        self._log(ts, pos.trader_id, pos.symbol, source,
                  CopyDecision(R.COPY_EXIT if full else R.COPY_RESIZE, reason),
                  side="SELL", qty=qty, price=price.quantize(Decimal("0.00000001")),
                  fee=fee.quantize(Decimal("0.00000001")), pnl=pnl.quantize(Decimal("0.0001")),
                  fill_ts=fill_ts.isoformat())
        self._check_trader_budget(ts, pos.trader_id)

    def _exit(self, ts: datetime, key: tuple[str, str], reason: str, source: str,
              leader_exit: Optional[Decimal] = None) -> None:
        pos = self.positions.get(key)
        if pos is None:
            return
        fill_ts, price = self._fill_price(pos.symbol, ts, buying=False)
        if self.failure_at is not None and (failure := self.failure_at(pos.symbol, fill_ts)):
            self._log(ts, pos.trader_id, pos.symbol, source, CopyDecision("ORDER_FAILED", f"{failure}|EXIT:{reason}"))
            return  # retried on the next mark / event
        self._sell(ts, key, pos.qty, price, fill_ts, reason, source, leader_exit)
        if source not in ("LEADER_CLOSED", LeaderAction.CLOSE.value) and leader_exit is None:
            self.exited_until_leader_closes.add(key)

    def _check_trader_budget(self, ts: datetime, trader_id: str) -> None:
        budget = self.starting_equity * self.policy.config.trader_loss_budget_pct / 100
        if self.realized_by_trader.get(trader_id, Decimal("0")) <= -budget and trader_id not in self.blocked:
            self.blocked[trader_id] = "TRADER_LOSS_BUDGET"
            self.followed.discard(trader_id)
            self._log(ts, trader_id, "*", "risk", CopyDecision(R.BLOCK_TRADER, "TRADER_LOSS_BUDGET"))

    # ------------------------------------------------------------------
    # Marks
    # ------------------------------------------------------------------

    def _advance_risk(self, ts: datetime) -> None:
        equity = self.equity(ts)
        self.policy.engine.advance_clock(equity, ts)
        self.policy.engine.observe_equity(equity, ts)

    def on_mark(self, ts: datetime) -> None:
        self._advance_risk(ts)
        for key, pos in list(self.positions.items()):
            price = self.price_at(pos.symbol, ts)
            view = PositionView(pos.qty * price, pos.avg_entry, pos.side)
            regime = self.regime_at(pos.symbol, ts) if self.regime_at else None
            decision = self.policy.on_mark(view, price, regime)
            if decision.action == R.COPY_EXIT:
                self._exit(ts, key, decision.reason, "mark")
            elif decision.reason == "WATCH_BEYOND_ENVELOPE" or (
                decision.reason == "TEMPORARY_DRAWDOWN" and pos.position_id not in self.held_through_drawdown
                # Fees and slippage alone put a fresh fill slightly under water; only a real
                # dip (half the envelope) is worth recording as "held through a drawdown".
                and loss_pct(view, price) * 2 >= self.policy.config.temporary_drawdown_envelope_pct
            ):
                self.held_through_drawdown.add(pos.position_id)
                self._log(ts, pos.trader_id, pos.symbol, "mark", decision,
                          loss_pct=loss_pct(view, price).quantize(Decimal("0.01")))

    # ------------------------------------------------------------------
    # Emergency stop
    # ------------------------------------------------------------------

    def emergency_stop(self, ts: datetime, reason: str, *, flatten: bool = False, owner_confirmed: bool = False) -> None:
        """Blocks every new entry at once (RiskEngine kill switch, cleared only by the
        owner). Closing positions too is a separate, explicit owner decision."""
        self.policy.engine.activate_kill_switch(f"EMERGENCY_STOP: {reason}")
        self._log(ts, "*", "*", "owner", CopyDecision("EMERGENCY_STOP", reason))
        if flatten:
            if not owner_confirmed:
                raise ValueError("flattening every position requires owner_confirmed=True")
            for key in list(self.positions):
                self._exit(ts, key, f"EMERGENCY_FLATTEN:{reason}", "owner", leader_exit=None)
