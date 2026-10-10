"""
A minimum stop distance around any strategy. Owner, 2026-10-10, after a real AVAX trade was
stopped out for -0.04 USDT: "el stop debe ser más alto y con lógica; puede hacer un stop loss
largo y dejar operando; con uno así de bajo se va a pérdida siempre".

On 1m-5m bars the strategies' own stops (swing low of the last 10 bars, 1.5 x ATR(14)) sit a few
tenths of a percent below entry, inside normal noise. This wrapper keeps the strategy's entries
and exits unchanged and only moves the stop down to at least `min_stop_pct` below the entry, when
the strategy's own stop is closer. The risk engine then sizes the position for the wider stop
(smaller quantity for the same risk budget), so a wider stop does not mean a bigger loss budget.

Then, same day: "yo creo un stop más alto con lógica; tú y local deciden, desde 3 al 15, no siempre
lo mismo". With `max_stop_pct` set, the distance follows the market: `vol_mult` x the coin's recent
volatility projected over `horizon_minutes` (std of bar returns x sqrt(bars in the horizon)),
clamped to [min_stop_pct, max_stop_pct]. A calm coin gets ~3%; a coin swinging hard gets more room,
up to 15%. A strategy stop already inside the band is kept; one farther than the max is pulled up
to it. The engine sizes every position for its own stop, so wider stops mean smaller positions.
"""
from __future__ import annotations

import math
from dataclasses import replace
from decimal import ROUND_DOWN, Decimal
from typing import Optional

import pandas as pd

from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal

VOL_MULT = Decimal("2.5")
HORIZON_MINUTES = 240  # the move a position should be able to survive: about four hours of noise


def volatility_stop_pct(data: pd.DataFrame, horizon_minutes: int = HORIZON_MINUTES) -> Optional[Decimal]:
    """Recent volatility projected over the horizon, in % of price: std of bar-to-bar log returns
    x sqrt(bars per horizon). None when there is not enough history to say."""
    closes = data["close"].astype(float)
    if len(closes) < 30:
        return None
    rets = (closes / closes.shift(1)).apply(lambda r: math.log(r) if r > 0 else float("nan")).dropna()
    if len(rets) < 20:
        return None
    step = (data.index[-1] - data.index[-2]).total_seconds() / 60 if len(data.index) > 1 else 0
    if step <= 0:
        return None
    vol = float(rets.tail(500).std()) * math.sqrt(max(horizon_minutes / step, 1.0)) * 100
    return Decimal(str(round(vol, 4))) if math.isfinite(vol) and vol > 0 else None


class StopFloor(AbstractStrategy):
    def __init__(self, inner: AbstractStrategy, min_stop_pct: Decimal, max_stop_pct: Optional[Decimal] = None,
                 vol_mult: Decimal = VOL_MULT) -> None:
        if not Decimal("0") < min_stop_pct < Decimal("50"):
            raise ValueError("min_stop_pct must be in (0, 50)")
        if max_stop_pct is not None and not min_stop_pct <= max_stop_pct < Decimal("50"):
            raise ValueError("max_stop_pct must be in [min_stop_pct, 50)")
        # Same id and symbol as the inner strategy: open positions re-attach to it after a restart.
        super().__init__(inner.strategy_id, inner.symbol, inner.timeframe, inner.params)
        self.inner = inner
        self.min_stop_pct = min_stop_pct
        self.max_stop_pct = max_stop_pct
        self.vol_mult = vol_mult

    def stop_distance_pct(self, data: pd.DataFrame) -> Decimal:
        """The floor for this bar: fixed, or volatility-scaled inside [min, max]."""
        if self.max_stop_pct is None:
            return self.min_stop_pct
        vol = volatility_stop_pct(data)
        wanted = self.vol_mult * vol if vol is not None else self.min_stop_pct
        return min(max(wanted, self.min_stop_pct), self.max_stop_pct).quantize(Decimal("0.01"))

    def on_bar(self, data: pd.DataFrame) -> Optional[TradeProposal]:
        proposal = self.inner.on_bar(data)
        if proposal is None:
            return None
        entry = proposal.entry_price if proposal.entry_price is not None else Decimal(str(data["close"].iloc[-1]))
        pct = self.stop_distance_pct(data)
        floor = (entry * (1 - pct / 100)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        if self.max_stop_pct is not None:
            deepest = (entry * (1 - self.max_stop_pct / 100)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
            if proposal.stop_price < deepest:  # a strategy stop farther than the owner's max is pulled up to it
                return replace(proposal, stop_price=deepest,
                               rationale=f"{proposal.rationale} | stop capped at {self.max_stop_pct}% below entry")
        if proposal.stop_price <= floor:
            return proposal
        return replace(proposal, stop_price=floor,
                       rationale=f"{proposal.rationale} | stop widened to {pct}% below entry (by volatility)"
                       if self.max_stop_pct is not None else
                       f"{proposal.rationale} | stop widened to {pct}% below entry")

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        return self.inner.on_exit_signal(data, entry_price)


def with_stop_floor(router, min_stop_pct: Optional[Decimal], max_stop_pct: Optional[Decimal] = None):
    """The same router with every registered strategy wrapped in StopFloor (None/0: unchanged)."""
    if not min_stop_pct:
        return router
    for regime, (strategy, confidence) in list(router._registry.items()):
        if not isinstance(strategy, StopFloor):
            router._registry[regime] = (StopFloor(strategy, min_stop_pct, max_stop_pct), confidence)
    return router
