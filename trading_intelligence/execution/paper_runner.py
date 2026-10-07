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
  * Every filled entry is registered with the RiskEngine and gets a protective
    STOP; every close is registered back and cancels the sibling STOP.
  * New entries are blocked whenever the RiskEngine's and the PaperAdapter's
    books disagree, or an open position has no protective STOP. Closing
    existing positions is never blocked.

Paper only: this wraps PaperAdapter and cannot reach an exchange.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

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
    exit_order_id: Optional[str] = None


class PaperTradingRunner:
    def __init__(
        self,
        router: StrategyRouter,
        risk_engine: RiskEngine,
        paper: PaperAdapter,
        regime_kwargs: Optional[dict] = None,
    ):
        self.router = router
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
        if data.empty:
            return self._record(RunnerStep(symbol, "", "NO_DATA"))

        bar_time = _bar_time(data)
        last = data.iloc[-1]
        fills = self.paper.on_new_bar(
            symbol,
            Decimal(str(float(last["open"]))), Decimal(str(float(last["high"]))),
            Decimal(str(float(last["low"]))), Decimal(str(float(last["close"]))),
            bar_time.isoformat(),
        )
        self._handle_fills(symbol, fills, bar_time)

        step = RunnerStep(symbol, bar_time.isoformat(), "", fills=fills)
        problems = self.reconcile()

        position = self.paper.get_position(symbol)
        if position is not None:
            step.action = self._maybe_exit(symbol, data, position)
        elif symbol in self._pending_entries:
            step.action = "ENTRY_PENDING"
        elif problems:
            step.action = "ENTRIES_BLOCKED"
            step.blocked_by = problems
            logger.error("Entries blocked for %s: %s", symbol, "; ".join(problems))
        else:
            self._maybe_enter(symbol, data, bar_time, step)
        return self._record(step)

    def run_replay(self, symbol: str, data: pd.DataFrame, warmup: int = 60) -> list[RunnerStep]:
        """Replays `data` bar by bar. Needs no network; with cached real
        klines it runs the same code path a live loop would."""
        out: list[RunnerStep] = []
        for i in range(warmup, len(data)):
            out.append(self.process_bar(symbol, data.iloc[: i + 1]))
        return out

    def reconcile(self) -> list[str]:
        """Disagreements between the RiskEngine's and the PaperAdapter's books.
        Empty list means consistent."""
        problems: list[str] = []
        paper_ids = {p.position_id: sym for sym, p in self.paper.positions.items()}
        risk_ids = {pid: info["symbol"] for pid, info in self.risk_engine.state.open_positions.items()}
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
        decision = self.router.route(snapshot)
        if decision.is_no_trade or decision.strategy is None:
            step.action = f"NO_TRADE:{decision.reason}"
            return

        proposal = decision.strategy.on_bar(data)
        if proposal is None:
            step.action = "NO_SIGNAL"
            return
        step.proposal = proposal

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
        result = self.paper.submit_order(order)
        if result.status != "SUBMITTED":
            step.action = f"ORDER_NOT_ACCEPTED:{result.reject_reason}"
            return
        self._pending_entries[symbol] = _PendingEntry(order.client_order_id, proposal, decision.strategy)
        step.action = "ENTRY_SUBMITTED"

    # ------------------------------------------------------------------
    # Exits
    # ------------------------------------------------------------------

    def _maybe_exit(self, symbol: str, data: pd.DataFrame, position: Position) -> str:
        trade = self._open_trades.get(symbol)
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
        self.risk_engine.register_position_opened(
            position.position_id, symbol, result.fill_price * result.filled_quantity,
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
            strategy=pending.strategy,
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
        for symbol, position in self.paper.positions.items():
            stop = self._stop_order_for(symbol)
            if stop is None or stop.stop_price is None:
                continue
            self._open_trades[symbol] = _OpenTrade(
                position_id=position.position_id, quantity=position.quantity,
                entry_price=position.avg_entry_price, entry_fee=position.entry_fee,
                stop_order_id=stop.client_order_id, stop_price=stop.stop_price, strategy=None,
            )

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
