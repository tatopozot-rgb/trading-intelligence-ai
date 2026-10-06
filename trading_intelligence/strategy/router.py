"""
Routes a regime classification to the strategy built for it — the piece
this project was explicitly missing: one fixed strategy was always "the
brain," regardless of what the market was doing.

This router does not invent coverage it doesn't have. Today exactly one
strategy exists (DualMACrossover, trend-following, long-only spot — see
trading_intelligence/strategy/strategies/ma_crossover.py), so it is
registered only for TREND_UP. Every other regime — TREND_DOWN (no
shorting in this spot-only system), RANGE, BREAKOUT_UP, BREAKOUT_DOWN,
NO_EDGE — correctly routes to no strategy at all. Adding a strategy for
one of those regimes means registering it here, not teaching this router
to fake confidence it doesn't have.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from trading_intelligence.regime.detector import Regime, RegimeSnapshot
from trading_intelligence.strategy.base import AbstractStrategy

NO_STRATEGY_FOR_REGIME = "NO_STRATEGY_FOR_REGIME"
CONFIDENCE_BELOW_THRESHOLD = "CONFIDENCE_BELOW_THRESHOLD"
ROUTED = "ROUTED"


@dataclass(frozen=True)
class RouterDecision:
    strategy: Optional[AbstractStrategy]
    reason: str
    regime: Regime
    confidence: float

    @property
    def is_no_trade(self) -> bool:
        return self.strategy is None


class StrategyRouter:
    """Holds a {Regime: (strategy, min_confidence)} registry and routes a
    RegimeSnapshot to the matching strategy, or explicitly to no trade."""

    def __init__(self) -> None:
        self._registry: dict[Regime, tuple[AbstractStrategy, float]] = {}

    def register(self, regime: Regime, strategy: AbstractStrategy, *, min_confidence: float = 0.0) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError(f"min_confidence must be in [0, 1], got {min_confidence}")
        self._registry[regime] = (strategy, min_confidence)

    def registered_regimes(self) -> frozenset[Regime]:
        return frozenset(self._registry)

    def route(self, snapshot: RegimeSnapshot) -> RouterDecision:
        entry = self._registry.get(snapshot.regime)
        if entry is None:
            return RouterDecision(None, NO_STRATEGY_FOR_REGIME, snapshot.regime, snapshot.confidence)
        strategy, min_confidence = entry
        if snapshot.confidence < min_confidence:
            return RouterDecision(None, CONFIDENCE_BELOW_THRESHOLD, snapshot.regime, snapshot.confidence)
        return RouterDecision(strategy, ROUTED, snapshot.regime, snapshot.confidence)


def default_router() -> StrategyRouter:
    """The router's current real coverage: DualMACrossover, for TREND_UP and
    BREAKOUT_UP. Originally registered for TREND_UP alone; running it
    end-to-end through BacktestEngine on synthetic data produced zero trades
    despite real bullish crossovers occurring. Checked why rather than
    accepting a silent NO_TRADE: ADX-confirmed TREND_UP only registers once a
    trend is already established, by which point the crossover that would
    have opened it has already fired a few bars earlier — on a BREAKOUT_UP or
    RANGE bar, not TREND_UP. BREAKOUT_UP is where this strategy's actual
    signal lands, verified against the crossover bars directly (not assumed).
    RANGE is NOT added: a crossover inside an already-ranging market is a
    much weaker signal for a trend-following strategy, and adding it without
    separate evidence would be exactly the kind of unvalidated coverage this
    router exists to avoid. Every other regime remains honestly NO_TRADE
    until a strategy is built and validated for it per
    docs/STRATEGY_VALIDATION_FRAMEWORK.md."""
    from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover

    strategy = DualMACrossover(
        "BTCUSDT", "1d", params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0}
    )
    router = StrategyRouter()
    router.register(Regime.TREND_UP, strategy, min_confidence=0.5)
    router.register(Regime.BREAKOUT_UP, strategy, min_confidence=0.0)
    return router
