"""
A minimum stop distance around any strategy. Owner, 2026-10-10, after a real AVAX trade was
stopped out for -0.04 USDT: "el stop debe ser más alto y con lógica; puede hacer un stop loss
largo y dejar operando; con uno así de bajo se va a pérdida siempre".

On 1m-5m bars the strategies' own stops (swing low of the last 10 bars, 1.5 x ATR(14)) sit a few
tenths of a percent below entry, inside normal noise. This wrapper keeps the strategy's entries
and exits unchanged and only moves the stop down to at least `min_stop_pct` below the entry, when
the strategy's own stop is closer. The risk engine then sizes the position for the wider stop
(smaller quantity for the same risk budget), so a wider stop does not mean a bigger loss budget.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import ROUND_DOWN, Decimal
from typing import Optional

import pandas as pd

from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal


class StopFloor(AbstractStrategy):
    def __init__(self, inner: AbstractStrategy, min_stop_pct: Decimal) -> None:
        if not Decimal("0") < min_stop_pct < Decimal("50"):
            raise ValueError("min_stop_pct must be in (0, 50)")
        # Same id and symbol as the inner strategy: open positions re-attach to it after a restart.
        super().__init__(inner.strategy_id, inner.symbol, inner.timeframe, inner.params)
        self.inner = inner
        self.min_stop_pct = min_stop_pct

    def on_bar(self, data: pd.DataFrame) -> Optional[TradeProposal]:
        proposal = self.inner.on_bar(data)
        if proposal is None:
            return None
        entry = proposal.entry_price if proposal.entry_price is not None else Decimal(str(data["close"].iloc[-1]))
        floor = (entry * (1 - self.min_stop_pct / 100)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        if proposal.stop_price <= floor:
            return proposal
        return replace(proposal, stop_price=floor,
                       rationale=f"{proposal.rationale} | stop widened to {self.min_stop_pct}% below entry")

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        return self.inner.on_exit_signal(data, entry_price)


def with_stop_floor(router, min_stop_pct: Optional[Decimal]):
    """The same router with every registered strategy wrapped in StopFloor (None/0: unchanged)."""
    if not min_stop_pct:
        return router
    for regime, (strategy, confidence) in list(router._registry.items()):
        if not isinstance(strategy, StopFloor):
            router._registry[regime] = (StopFloor(strategy, min_stop_pct), confidence)
    return router
