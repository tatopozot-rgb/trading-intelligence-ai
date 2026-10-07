"""
PaperTradingRunner — the missing link that makes the pipeline run end to end:
regime -> StrategyRouter -> strategy proposal -> RiskEngine veto -> PaperAdapter
order -> fill -> position registration + protective STOP -> exit -> P&L.

Before this module each stage existed and was tested in isolation, but nothing
connected a RiskEngine approval to an actual (paper) order, registered the
resulting position back into the RiskEngine's exposure accounting, or kept a
protective STOP alive for it. ShadowRunner stops at the decision; BacktestEngine
simulates internally and never consults the RiskEngine.

Invariants this runner enforces (each has a test):
  * An entry order is submitted ONLY from an approved RiskDecision, sized by the
    RiskEngine. There is no other path to an entry.
  * A RiskEngine exception means no order (fail closed), never a bypass.
  * An approved entry is RESERVED in the RiskEngine immediately (so same-bar
    approvals on other symbols see it against every limit), confirmed when it
    fills and released if it never does. Every filled entry gets a protective
    STOP; every close is registered back and cancels the sibling STOP.
  * New entries are blocked whenever the RiskEngine's and the PaperAdapter's
    books disagree, or an open position has no protective STOP. Closing
    existing positions is never blocked.
  * Equity is reported to the RiskEngine on EVERY bar, after every symbol is
    marked, so drawdown and daily-loss halts do not depend on a new signal.
    If that observation fails, new entries are blocked.
  * Optional `trailing_stop_pct` ratchets each protective STOP up to that
    fraction below the highest close since entry (never down). The risk
    limits measure exposure at ENTRY notional and the initial stop is fixed
    at the entry price, so without a trail an appreciated position ends up
    holding far more than the cap with a stop far below the market. The new
    STOP is submitted before the old one is cancelled, so the position is
    never unprotected. Off by default: it changes exit behavior.
  * A proposal whose symbol differs from the symbol of the data it was
    generated from is rejected (fail closed): the risk checks and the order
    would otherwise apply to different instruments.
  * Multi-asset: `router` may be a callable building one router per symbol;
    all symbols share one account and one RiskEngine, so its exposure,
    position-count and drawdown limits are portfolio-wide.

Paper only: this wraps PaperAdapter and cannot reach an exchange.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Mapping, Optional, Union

import pandas as pd

from trading_intelligence.execution.order_models import OrderRequest, OrderResult, Position
from trading_intelligence.execution.paper import PaperAdapter
from trading_intelligence.regime.detector import detect_regime
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import RiskDecision, TradeProposal
from trading_intelligence.strategy.router import StrategyRouter

logger = logging.getLogger(__name__)

EXIT_STOP = "STOP"
EXIT_STRATEGY = "STRATEGY_EXIT"
EXIT_UNKNOWN = "UNKNOWN"


@dataclass
class ClosedTrade:
    symbol: str
    position_id: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    pnl: Decimal
    exit_reason: str
    closed_at: str


@dataclass
class RunnerStep:
    symbol: str
    bar_time: str
    action: str
    regime: Optional[str] = None
    proposal: Optional[TradeProposal] = None
    risk_decision: Optional[RiskDecision] = None
    fills: list[OrderResult] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    equity: Optional[Decimal] = None  # account equity at this timestamp, after every symbol was marked


@dataclass
class _PendingEntry:
    order_id: str
    proposal: TradeProposal
    strategy: AbstractStrategy


@dataclass
class _OpenTrade:
    position_id: str
    quantity: Decimal
    entry_price: Decimal
    entry_fee: Decimal
    stop_order_id: str
    stop_price: Decimal
    strategy: Optional[AbstractStrategy]  # None after a restart: exits via the persisted STOP only
    high_water: Decimal = Decimal("0")  # highest close since entry; drives the optional trailing stop
    exit_order_id: Optional[str] = None


class PaperTradingRunner:
    def __init__(
        self,
        router: Union[StrategyRouter, Callable[[str], StrategyRouter]],
        risk_engine: RiskEngine,
        paper: PaperAdapter,
        regime_kwargs: Optional[dict] = None,
        history_bars: int = 500,
        trailing_stop_pct: Optional[float] = None,
    ):
        if history_bars < 2:
            raise ValueError("history_bars must be >= 2")
        if trailing_stop_pct is not None and not 0.0 < trailing_stop_pct < 1.0:
            raise ValueError("trailing_stop_pct must be in (0, 1)")
        self.history_bars = history_bars
        self.trailing_stop_pct = None if trailing_stop_pct is None else Decimal(str(trailing_stop_pct))
        self._router_source = router
        self._routers: dict[str, StrategyRouter] = {}
        self.risk_engine = risk_engine
        self.paper = paper
        self.regime_kwargs = regime_kwargs or {}
        self.closed_trades: list[ClosedTrade] = []
        self.steps: list[RunnerStep] = []
        self._pending_entries: dict[str, _PendingEntry] = {}
        self._open_trades: dict[str, _OpenTrade] = {}
        self._rebuild_after_restart()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_bar(self, symbol: str, data: pd.DataFrame) -> RunnerStep:
        """Feed one newly completed bar (the LAST row of `data`; earlier rows
        are history). Orders decided on this bar fill at the next bar's open,
        exactly as PaperAdapter models it."""
        return self.process_bars({symbol: data})[0]

    def process_bars(self, frames: Mapping[str, pd.DataFrame]) -> list[RunnerStep]:
        """One timestamp across several symbols (`history_bars` of trailing
        history are used for decisions, as a live loop would have). Phase 1 fills and marks every
        symbol; phase 2 reports equity to the RiskEngine once, with every
        position marked at this timestamp; phase 3 decides, symbol by symbol
        in sorted order (deterministic; the shared RiskEngine caps are
        first-come-first-served)."""
        steps: list[RunnerStep] = []
        ingested: dict[str, tuple[datetime, list[OrderResult]]] = {}
        for symbol in sorted(frames):
            data = frames[symbol]
            if data.empty:
                steps.append(self._record(RunnerStep(symbol, "", "NO_DATA")))
                continue
            ingested[symbol] = self._ingest(symbol, data)
        if not ingested:
            return steps

        problems: list[str] = []
        equity = self.paper.get_account_info().equity
        try:
            self.risk_engine.observe_equity(equity, now=max(t for t, _ in ingested.values()))
        except Exception:
            logger.exception("RiskEngine could not observe equity — blocking new entries")
            problems.append("RiskEngine failed to observe equity")
        problems += self.reconcile()

        for symbol in sorted(ingested):
            bar_time, fills = ingested[symbol]
            window = frames[symbol].iloc[-self.history_bars:]
            step = self._decide(symbol, window, bar_time, fills, problems)
            step.equity = equity
            steps.append(self._record(step))
        return steps

    def _ingest(self, symbol: str, data: pd.DataFrame) -> tuple[datetime, list[OrderResult]]:
        bar_time = _bar_time(data)
        last = data.iloc[-1]
        fills = self.paper.on_new_bar(
            symbol,
            Decimal(str(float(last["open"]))), Decimal(str(float(last["high"]))),
            Decimal(str(float(last["low"]))), Decimal(str(float(last["close"]))),
            bar_time.isoformat(),
        )
        self._handle_fills(symbol, fills, bar_time)
        return bar_time, fills

    def _decide(
        self, symbol: str, data: pd.DataFrame, bar_time: datetime,
        fills: list[OrderResult], problems: list[str],
    ) -> RunnerStep:
        step = RunnerStep(symbol, bar_time.isoformat(), "", fills=fills)
        position = self.paper.get_position(symbol)
        if position is not None:
            step.action = self._maybe_exit(symbol, data, position)
        elif symbol in self._pending_entries:
            step.action = "ENTRY_PENDING"
        elif problems:
            step.action = "ENTRIES_BLOCKED"
            step.blocked_by = list(problems)
            logger.error("Entries blocked for %s: %s", symbol, "; ".join(problems))
        else:
            self._maybe_enter(symbol, data, bar_time, step)
        return step

    def _router_for(self, symbol: str) -> StrategyRouter:
        if isinstance(self._router_source, StrategyRouter):
            return self._router_source
        if symbol not in self._routers:
            self._routers[symbol] = self._router_source(symbol)
        return self._routers[symbol]

    def run_replay(self, symbol: str, data: pd.DataFrame, warmup: int = 60) -> list[RunnerStep]:
        """Replays `data` bar by bar. Needs no network; with cached real
        klines it runs the same code path a live loop would."""
        out: list[RunnerStep] = []
        for i in range(warmup, len(data)):
            out.append(self.process_bar(symbol, data.iloc[: i + 1]))
        return out

    def run_portfolio_replay(
        self, frames: Mapping[str, pd.DataFrame], warmup: int = 60,
    ) -> list[RunnerStep]:
        """Replays several symbols on their common timestamps, one shared
        account and RiskEngine. Frames are aligned to the intersection of
        their indexes so every step sees every symbol at the same time."""
        common = None
        for frame in frames.values():
            common = frame.index if common is None else common.intersection(frame.index)
        if common is None:
            return []
        aligned = {sym: frame.loc[common] for sym, frame in frames.items()}
        out: list[RunnerStep] = []
        for i in range(warmup, len(common)):
            out.extend(self.process_bars({sym: f.iloc[: i + 1] for sym, f in aligned.items()}))
        return out

    def reconcile(self) -> list[str]:
        """Disagreements between the RiskEngine's and the PaperAdapter's books.
        Empty list means consistent."""
        problems: list[str] = []
        paper_ids = {p.position_id: sym for sym, p in self.paper.positions.items()}
        risk_ids = {
            pid: info["symbol"] for pid, info in self.risk_engine.state.open_positions.items()
            if not info.get("reserved")
        }
        live_entries = {p.order_id for p in self._pending_entries.values()}
        for rid in self.risk_engine.reservation_ids():
            if rid not in live_entries:
                problems.append(f"RiskEngine holds a reservation ({rid}) with no pending entry")
        for pid, sym in paper_ids.items():
            if pid not in risk_ids:
                problems.append(f"paper position {sym} ({pid}) is not registered in the RiskEngine")
        for pid, sym in risk_ids.items():
            if pid not in paper_ids:
                problems.append(f"RiskEngine position {sym} ({pid}) has no paper position")
        for sym in self.paper.positions:
            if self._stop_order_for(sym) is None:
                problems.append(f"open position {sym} has no protective STOP")
        return problems

    # ------------------------------------------------------------------
    # Entries
    # ------------------------------------------------------------------

    def _maybe_enter(self, symbol: str, data: pd.DataFrame, bar_time: datetime, step: RunnerStep) -> None:
        snapshot = detect_regime(data, **self.regime_kwargs)
        step.regime = snapshot.regime.value
        decision = self._router_for(symbol).route(snapshot)
        if decision.is_no_trade or decision.strategy is None:
            step.action = f"NO_TRADE:{decision.reason}"
            return

        proposal = decision.strategy.on_bar(data)
        if proposal is None:
            step.action = "NO_SIGNAL"
            return
        step.proposal = proposal
        if proposal.symbol != symbol:
            logger.error(
                "Strategy proposed %s while processing %s data — rejecting (fail closed)",
                proposal.symbol, symbol,
            )
            step.action = "SYMBOL_MISMATCH_NO_ORDER"
            return

        reference_price = Decimal(str(float(data["close"].iloc[-1])))
        try:
            equity = self.paper.get_account_info().equity
            risk = self.risk_engine.validate_order(
                proposal, equity=equity, reference_price=reference_price, now=bar_time,
            )
        except Exception:
            logger.exception("RiskEngine failed for %s — failing closed, no order", symbol)
            step.action = "RISK_ERROR_NO_ORDER"
            return
        step.risk_decision = risk

        if not risk.approved or risk.quantity is None or risk.quantity <= 0:
            step.action = f"RISK_REJECTED:{risk.reason}"
            return

        order = OrderRequest(symbol=symbol, side="BUY", order_type="MARKET", quantity=risk.quantity)
        # Reserve before submitting: other symbols decided on this same bar
        # must already see this entry against max positions and exposure.
        self.risk_engine.reserve_position(order.client_order_id, symbol, risk.quantity * reference_price)
        result = self.paper.submit_order(order)
        if result.status != "SUBMITTED":
            self.risk_engine.release_reservation(order.client_order_id)
            step.action = f"ORDER_NOT_ACCEPTED:{result.reject_reason}"
            return
        self._pending_entries[symbol] = _PendingEntry(order.client_order_id, proposal, decision.strategy)
        step.action = "ENTRY_SUBMITTED"

    # ------------------------------------------------------------------
    # Exits
    # ------------------------------------------------------------------

    def _ratchet_stop(self, symbol: str, trade: _OpenTrade, close: Decimal) -> None:
        if self.trailing_stop_pct is None:
            return
        trade.high_water = max(trade.high_water, close)
        new_stop = trade.high_water * (1 - self.trailing_stop_pct)
        if new_stop <= trade.stop_price:
            return
        old = self._stop_order_for(symbol)
        if old is None:
            return
        stop = OrderRequest(
            symbol=symbol, side="SELL", order_type="STOP",
            quantity=trade.quantity, stop_price=new_stop,
        )
        self.paper.submit_order(stop)
        self.paper.cancel_order(old.client_order_id)
        trade.stop_order_id = stop.client_order_id
        trade.stop_price = new_stop

    def _maybe_exit(self, symbol: str, data: pd.DataFrame, position: Position) -> str:
        trade = self._open_trades.get(symbol)
        if trade is not None:
            self._ratchet_stop(symbol, trade, Decimal(str(float(data["close"].iloc[-1]))))
        if trade is None or trade.strategy is None:
            return "HOLDING"
        if trade.exit_order_id is not None:
            return "EXIT_PENDING"
        if trade.strategy.on_exit_signal(data, trade.entry_price):
            order = OrderRequest(symbol=symbol, side="SELL", order_type="MARKET", quantity=position.quantity)
            result = self.paper.submit_order(order)
            if result.status == "SUBMITTED":
                trade.exit_order_id = order.client_order_id
                return "EXIT_SUBMITTED"
        return "HOLDING"

    # ------------------------------------------------------------------
    # Fill handling
    # ------------------------------------------------------------------

    def _handle_fills(self, symbol: str, fills: list[OrderResult], bar_time: datetime) -> None:
        for result in fills:
            if result.status not in ("FILLED", "REJECTED"):
                continue
            pending = self._pending_entries.get(symbol)
            if pending is not None and result.client_order_id == pending.order_id:
                del self._pending_entries[symbol]
                if result.status == "FILLED":
                    self._on_entry_filled(symbol, pending, result)
                else:
                    self.risk_engine.release_reservation(pending.order_id)
                    logger.warning("Entry for %s rejected at fill: %s", symbol, result.reject_reason)
                continue
            trade = self._open_trades.get(symbol)
            if trade is not None and result.side == "SELL" and result.status == "FILLED":
                self._on_exit_filled(symbol, trade, result, bar_time)

    def _on_entry_filled(self, symbol: str, pending: _PendingEntry, result: OrderResult) -> None:
        position = self.paper.get_position(symbol)
        if position is None or result.fill_price is None:
            logger.error("Entry fill for %s but no paper position — leaving for reconcile()", symbol)
            return
        self.risk_engine.confirm_reservation(
            pending.order_id, position.position_id, symbol, result.fill_price * result.filled_quantity,
        )
        stop = OrderRequest(
            symbol=symbol, side="SELL", order_type="STOP",
            quantity=position.quantity, stop_price=pending.proposal.stop_price,
        )
        self.paper.submit_order(stop)
        self._open_trades[symbol] = _OpenTrade(
            position_id=position.position_id, quantity=position.quantity,
            entry_price=position.avg_entry_price, entry_fee=position.entry_fee,
            stop_order_id=stop.client_order_id, stop_price=pending.proposal.stop_price,
            strategy=pending.strategy, high_water=position.avg_entry_price,
        )

    def _on_exit_filled(self, symbol: str, trade: _OpenTrade, result: OrderResult, bar_time: datetime) -> None:
        if result.fill_price is None:
            return
        if result.client_order_id == trade.stop_order_id:
            reason = EXIT_STOP
        elif result.client_order_id == trade.exit_order_id:
            reason = EXIT_STRATEGY
            self.paper.cancel_order(trade.stop_order_id)
        else:
            reason = EXIT_UNKNOWN
        quantity = result.filled_quantity
        pnl = (
            result.fill_price * quantity - result.fee
            - trade.entry_price * quantity - trade.entry_fee * (quantity / trade.quantity)
        )
        self.risk_engine.register_position_closed(trade.position_id, pnl)
        self.closed_trades.append(ClosedTrade(
            symbol=symbol, position_id=trade.position_id, quantity=quantity,
            entry_price=trade.entry_price, exit_price=result.fill_price, pnl=pnl,
            exit_reason=reason, closed_at=bar_time.isoformat(),
        ))
        del self._open_trades[symbol]

    # ------------------------------------------------------------------
    # Restart recovery
    # ------------------------------------------------------------------

    def _rebuild_after_restart(self) -> None:
        """PaperAdapter and RiskEngine persist their own state. Rebuild the
        runner's trade records from it: a position whose protective STOP
        survived keeps being managed (stop-only exits, since the originating
        strategy object is not persisted). A position with no STOP is left
        unrecorded so reconcile() blocks new entries instead of guessing."""
        # Entries/exits that were merely pending are decisions about a bar that
        # is now stale, and the proposal behind them is not persisted. Drop
        # them and give back their reservations; a fresh signal will re-decide.
        for order in list(self.paper.pending_orders):
            if order.order_type != "STOP":
                logger.warning("Restart: cancelling stale pending %s %s order %s",
                               order.side, order.symbol, order.client_order_id)
                self.paper.cancel_order(order.client_order_id)
        for rid in self.risk_engine.reservation_ids():
            self.risk_engine.release_reservation(rid)
        for symbol, position in self.paper.positions.items():
            stop = self._stop_order_for(symbol)
            if stop is None or stop.stop_price is None:
                continue
            self._open_trades[symbol] = _OpenTrade(
                position_id=position.position_id, quantity=position.quantity,
                entry_price=position.avg_entry_price, entry_fee=position.entry_fee,
                stop_order_id=stop.client_order_id, stop_price=stop.stop_price, strategy=None,
                high_water=self._high_water_from_stop(position.avg_entry_price, stop.stop_price),
            )

    def _high_water_from_stop(self, entry_price: Decimal, stop_price: Decimal) -> Decimal:
        """The high-water mark is not persisted; with a trailing stop it is
        recoverable from the ratcheted stop (stop = high * (1 - trail))."""
        if self.trailing_stop_pct is None:
            return entry_price
        return max(entry_price, stop_price / (1 - self.trailing_stop_pct))

    def _stop_order_for(self, symbol: str) -> Optional[OrderRequest]:
        for order in self.paper.pending_orders:
            if order.symbol == symbol and order.side == "SELL" and order.order_type == "STOP":
                return order
        return None

    def _record(self, step: RunnerStep) -> RunnerStep:
        self.steps.append(step)
        return step


def _bar_time(data: pd.DataFrame) -> datetime:
    ts = data.index[-1]
    dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
