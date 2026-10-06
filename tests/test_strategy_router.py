"""Tests for trading_intelligence.strategy.router."""
import pytest

from trading_intelligence.regime.detector import Regime, RegimeSnapshot, Volatility
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.router import (
    CONFIDENCE_BELOW_THRESHOLD,
    NO_STRATEGY_FOR_REGIME,
    ROUTED,
    StrategyRouter,
    default_router,
)
from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover


def _snapshot(regime: Regime, confidence: float = 1.0) -> RegimeSnapshot:
    return RegimeSnapshot(regime=regime, volatility=Volatility.NORMAL, confidence=confidence, metrics={})


class _DummyStrategy(AbstractStrategy):
    def __init__(self):
        super().__init__(strategy_id="dummy", symbol="BTCUSDT", timeframe="1d", params={})

    def on_bar(self, data):
        return None

    def on_exit_signal(self, data, entry_price):
        return False


class TestStrategyRouter:
    def test_no_strategy_registered_for_a_regime_is_explicit_no_trade(self):
        router = StrategyRouter()
        decision = router.route(_snapshot(Regime.RANGE))
        assert decision.is_no_trade
        assert decision.reason == NO_STRATEGY_FOR_REGIME

    def test_routes_to_the_registered_strategy_when_confidence_clears_the_bar(self):
        router = StrategyRouter()
        strat = _DummyStrategy()
        router.register(Regime.TREND_UP, strat, min_confidence=0.5)
        decision = router.route(_snapshot(Regime.TREND_UP, confidence=0.8))
        assert decision.reason == ROUTED
        assert decision.strategy is strat
        assert not decision.is_no_trade

    def test_confidence_below_threshold_is_no_trade_even_with_a_registered_strategy(self):
        router = StrategyRouter()
        router.register(Regime.TREND_UP, _DummyStrategy(), min_confidence=0.5)
        decision = router.route(_snapshot(Regime.TREND_UP, confidence=0.3))
        assert decision.is_no_trade
        assert decision.reason == CONFIDENCE_BELOW_THRESHOLD

    def test_no_edge_regime_blocked_by_any_positive_min_confidence(self):
        """NO_EDGE always carries confidence exactly 0.0 from the detector, so any
        positive min_confidence blocks it. (min_confidence=0.0 is a real, if unwise,
        way to disable the confidence filter entirely — that's the caller's choice,
        not a hole in the router: see the next test.)"""
        router = StrategyRouter()
        router.register(Regime.NO_EDGE, _DummyStrategy(), min_confidence=0.01)
        decision = router.route(_snapshot(Regime.NO_EDGE, confidence=0.0))
        assert decision.is_no_trade
        assert decision.reason == CONFIDENCE_BELOW_THRESHOLD

    def test_min_confidence_zero_means_no_confidence_filtering_at_all(self):
        router = StrategyRouter()
        router.register(Regime.NO_EDGE, _DummyStrategy(), min_confidence=0.0)
        decision = router.route(_snapshot(Regime.NO_EDGE, confidence=0.0))
        assert decision.reason == ROUTED
        assert not decision.is_no_trade

    def test_rejects_out_of_range_min_confidence(self):
        router = StrategyRouter()
        with pytest.raises(ValueError):
            router.register(Regime.TREND_UP, _DummyStrategy(), min_confidence=1.5)

    def test_registered_regimes_reflects_the_registry(self):
        router = StrategyRouter()
        router.register(Regime.TREND_UP, _DummyStrategy())
        router.register(Regime.RANGE, _DummyStrategy())
        assert router.registered_regimes() == frozenset({Regime.TREND_UP, Regime.RANGE})


class TestDefaultRouter:
    def test_only_covers_trend_up_today_honestly(self):
        """The whole point of this router: it must not claim coverage the
        project doesn't actually have. Exactly one strategy exists today."""
        router = default_router()
        assert router.registered_regimes() == frozenset({Regime.TREND_UP})

    def test_trend_up_routes_to_dual_ma_crossover(self):
        router = default_router()
        decision = router.route(_snapshot(Regime.TREND_UP, confidence=0.9))
        assert isinstance(decision.strategy, DualMACrossover)

    def test_every_other_regime_is_no_trade(self):
        router = default_router()
        for regime in (Regime.TREND_DOWN, Regime.RANGE, Regime.BREAKOUT_UP,
                       Regime.BREAKOUT_DOWN, Regime.NO_EDGE):
            decision = router.route(_snapshot(regime, confidence=1.0))
            assert decision.is_no_trade, f"{regime} should be NO_TRADE but got a strategy"
            assert decision.reason == NO_STRATEGY_FOR_REGIME
