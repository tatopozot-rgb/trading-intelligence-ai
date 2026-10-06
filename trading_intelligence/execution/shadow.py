"""
ShadowRunner — observes REAL current market data and produces REAL
RiskEngine decisions, without ever executing anything.

Distinct from PaperAdapter (which simulates fills on historical/replay
data): this is the last validation step before LIVE_ACTIVATION_APPROVAL —
run the actual strategy and the actual RiskEngine against live market
conditions and record what the system WOULD have decided. It never
constructs an OrderRequest, never calls submit_order, and never touches
any account/trading endpoint — only public market data (get_ohlcv,
get_current_price).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import RiskDecision, TradeProposal

logger = logging.getLogger(__name__)


@dataclass
class ShadowDecision:
    symbol: str
    checked_at: str
    proposal: Optional[TradeProposal]
    risk_decision: Optional[RiskDecision]
    reference_price: Optional[Decimal]
    note: str


class ShadowRunner:
    """
    One `check_once()` call: fetch real OHLCV for `symbol`, run the
    strategy's on_bar(), and if it proposes a trade, run it through the
    real RiskEngine. Every outcome is recorded in `self.decisions` and
    logged — nothing is ever executed.
    """

    def __init__(
        self,
        strategy: AbstractStrategy,
        risk_engine: RiskEngine,
        market_data_adapter: AbstractExchangeAdapter,
        equity_fn: Callable[[], Decimal],
        history_bars: int = 500,
    ):
        self.strategy = strategy
        self.risk_engine = risk_engine
        self.market_data_adapter = market_data_adapter
        self.equity_fn = equity_fn
        self.history_bars = history_bars
        self.decisions: list[ShadowDecision] = []

    def check_once(self, symbol: str, timeframe: str) -> ShadowDecision:
        now = datetime.now(timezone.utc).isoformat()
        data = self.market_data_adapter.get_ohlcv(symbol, timeframe, limit=self.history_bars)

        if data.empty:
            return self._record(symbol, now, None, None, None, "no market data available")

        proposal = self.strategy.on_bar(data)
        if proposal is None:
            return self._record(symbol, now, None, None, None, "no signal this bar")

        reference_price = self.market_data_adapter.get_current_price(symbol)
        equity = self.equity_fn()
        risk_decision = self.risk_engine.validate_order(
            proposal, equity=equity, reference_price=reference_price,
        )

        verdict = "APPROVE" if risk_decision.approved else "REJECT"
        note = f"SHADOW would {verdict} — {risk_decision.reason}"
        decision = self._record(symbol, now, proposal, risk_decision, reference_price, note)
        logger.info(
            "SHADOW %s %s: %s (qty=%s, ref_price=%s)",
            symbol, verdict, risk_decision.reason, risk_decision.quantity, reference_price,
        )
        return decision

    def _record(
        self,
        symbol: str,
        checked_at: str,
        proposal: Optional[TradeProposal],
        risk_decision: Optional[RiskDecision],
        reference_price: Optional[Decimal],
        note: str,
    ) -> ShadowDecision:
        decision = ShadowDecision(
            symbol=symbol, checked_at=checked_at, proposal=proposal,
            risk_decision=risk_decision, reference_price=reference_price, note=note,
        )
        self.decisions.append(decision)
        return decision
