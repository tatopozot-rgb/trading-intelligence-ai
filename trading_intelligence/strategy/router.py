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

import math
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

    def strategy_by_id(self, strategy_id: str, symbol: str) -> Optional[AbstractStrategy]:
        """The registered strategy with this id trading this symbol, if any.
        Used to re-attach an open position to its strategy after a restart."""
        for strategy, _ in self._registry.values():
            if strategy.strategy_id == strategy_id and strategy.symbol == symbol:
                return strategy
        return None

    def route(self, snapshot: RegimeSnapshot) -> RouterDecision:
        entry = self._registry.get(snapshot.regime)
        if entry is None:
            return RouterDecision(None, NO_STRATEGY_FOR_REGIME, snapshot.regime, snapshot.confidence)
        strategy, min_confidence = entry
        # NaN fails every comparison (including `<`), so `NaN < min_confidence`
        # is False and a malformed snapshot would otherwise fall through to
        # ROUTED; `inf` would also always pass. Neither should ever occur from
        # this project's own detector (bounded to [0, 1] by construction), but
        # a malformed snapshot from anywhere else must not silently route —
        # fail closed, the same way an invalid risk threshold does elsewhere
        # in this project, rather than trusting untrusted input.
        if not math.isfinite(snapshot.confidence) or snapshot.confidence < min_confidence:
            return RouterDecision(None, CONFIDENCE_BELOW_THRESHOLD, snapshot.regime, snapshot.confidence)
        return RouterDecision(strategy, ROUTED, snapshot.regime, snapshot.confidence)


def default_router(symbol: str = "BTCUSDT", timeframe: str = "1d") -> StrategyRouter:
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
        symbol, timeframe, params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0}
    )
    router = StrategyRouter()
    router.register(Regime.TREND_UP, strategy, min_confidence=0.5)
    router.register(Regime.BREAKOUT_UP, strategy, min_confidence=0.0)
    return router


def candidate_router_trend_4h(symbol: str = "BTCUSDT") -> StrategyRouter:
    """CANDIDATE, NOT the live default — see docs/CHECKPOINT.md's
    Quant/Validation section and
    docs/STRATEGY_CANDIDATE_TREND_4H_VALIDATION.md for the full Stage 0-4
    write-up before relying on this.

    default_router()'s DualMACrossover(1d, fast=20/slow=50) is the ONLY
    strategy wired into this project's live router, and it failed its own
    validation gate on real BTCUSDT 1D data (11 completed trades in
    2019-2026, below the 30-trade minimum; 0 walk-forward folds cleared
    IS Sharpe >= 0.5 — docs/CHECKPOINT.md section 12). The cause is a
    trade-FREQUENCY problem, not a parameter problem: a 20/50-period
    crossover's economic rationale (ride an established trend until it
    reverses) doesn't depend on calendar bar size, but sampling it once a
    day gives it only ~365 opportunities/year to cross on 7 years of data.

    Economic rationale (Stage 0, stated before any backtest number was
    looked at): the identical crossover logic, the identical 20:50
    fast:slow ratio, and the identical long-only spot rules -- sampled at
    4h instead of 1D. This is a sampling-frequency change, not a
    retuning: the periods themselves (20, 50) and their ratio are
    unchanged, so this is NOT "retuning the existing MA periods on the
    same series to force more trades" (the exact move
    docs/STRATEGY_VALIDATION_FRAMEWORK.md bans) -- it changes which bars
    those same periods are computed over. At 4h, the same strategy gets
    ~6x more independent crossover opportunities per calendar year on the
    same multi-year span, which is the structural fix the frequency
    problem calls for.

    This project's own `HistoricalDataDownloader`/`BinanceSpotAdapter`
    already support "4h" as an ordinary interval string (see
    data/downloader.py's `_INTERVAL_SECONDS` map) -- no new data-layer
    architecture is needed to run this for real.

    Synthetic-data-validated only (this cloud session has no real Binance
    network access) -- see the validation doc for the full Stage 0-4
    write-up and its explicit synthetic-only caveat. NOT wired into
    default_router(); promote it there only after a real-data
    walk-forward run (Claude Code local) confirms it clears the same gate
    that failed real DualMACrossover(1D)."""
    from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover

    strategy = DualMACrossover(
        symbol, "4h", params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0}
    )
    router = StrategyRouter()
    router.register(Regime.TREND_UP, strategy, min_confidence=0.5)
    router.register(Regime.BREAKOUT_UP, strategy, min_confidence=0.0)
    return router


def router_with_range_reversion(symbol: str = "BTCUSDT") -> StrategyRouter:
    """default_router()'s coverage, PLUS BollingerReversion (mean-reversion,
    see trading_intelligence/strategy/strategies/bollinger_reversion.py)
    registered for Regime.RANGE.

    Deliberately kept separate from default_router() rather than mutating it
    in place — per docs/AGENT_COORDINATION.md's coordination note, adding
    RANGE coverage to the shared router needs its own explicit review, not a
    silent edit to the config every other caller already uses.

    **Walk-forward validation result: NO-GO. Do NOT promote this into
    default_router().** Run through run_anchored_walk_forward() on ~4 years
    of realistic regime-mixed synthetic daily data (RANGE-only router, to
    isolate this strategy's own performance): every attempted fold's IS
    window had zero trades (IS Sharpe stuck at 0.00), because BollingerReversion's
    own oversold-bounce signal predominantly fires during TREND_DOWN/
    BREAKOUT_DOWN bars (16+3 of 25 standalone signals), not RANGE (4 of 25) —
    a confirmed-RANGE bar (low ADX) correlates with LOW realized volatility
    on this data, which makes a 2-standard-deviation Bollinger Band breach
    intrinsically rare while genuinely ranging. The RANGE-gated router
    produced exactly 1 trade across the full ~4-year dataset: nowhere near
    the 30-OOS-trade minimum STRATEGY_VALIDATION_FRAMEWORK.md requires. See
    docs/CHECKPOINT.md's entry for this session for the full evidence. Not
    re-tuned after seeing this result, per that framework's explicit rule
    against tuning until something looks good.
    """
    from trading_intelligence.strategy.strategies.bollinger_reversion import BollingerReversion

    router = default_router(symbol)
    strategy = BollingerReversion(symbol, "1d")
    router.register(Regime.RANGE, strategy, min_confidence=0.5)
    return router
