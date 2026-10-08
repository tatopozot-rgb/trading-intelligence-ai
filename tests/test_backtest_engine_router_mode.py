"""Tests for BacktestEngine's regime-aware mode (router=... instead of strategy=...).

Fixed-strategy mode's own behavior is covered by test_backtest_engine.py and
must stay byte-for-byte unchanged — these tests only exercise the new path.
"""
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting.backtest_engine import BacktestEngine
from trading_intelligence.regime.detector import Regime
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal
from trading_intelligence.strategy.router import StrategyRouter
from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover


def _trending_ohlcv(n: int = 400, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.015, n)
    close = 100.0 * np.cumprod(1 + returns)
    idx = pd.date_range("2019-01-01", periods=n, freq="1D")
    return pd.DataFrame(
        {
            "open": close * (1 + rng.uniform(-0.003, 0.003, n)),
            "high": close * (1 + rng.uniform(0.001, 0.008, n)),
            "low": close * (1 - rng.uniform(0.001, 0.008, n)),
            "close": close,
            "volume": rng.uniform(1000, 5000, n),
        },
        index=idx,
    )


class _AlwaysSignalsOnce(AbstractStrategy):
    """Fires exactly one BUY on its first on_bar() call — used to prove which
    strategy object the engine actually invoked, by identity."""

    def __init__(self, strategy_id: str):
        super().__init__(strategy_id=strategy_id, symbol="TESTUSDT", timeframe="1d", params={})
        self.fired = False
        self.on_bar_calls = 0

    def on_bar(self, data):
        self.on_bar_calls += 1
        if self.fired:
            return None
        self.fired = True
        return TradeProposal(
            strategy_id=self.strategy_id, symbol=self.symbol, side="BUY", entry_type="MARKET",
            stop_price=Decimal(str(float(data["close"].iloc[-1]) * 0.9)), timeframe=self.timeframe,
            rationale="test", signal_strength=1.0, timestamp=str(data.index[-1]),
        )

    def on_exit_signal(self, data, entry_price):
        return False


class TestConstructorValidation:
    def test_requires_exactly_one_of_strategy_or_router(self):
        with pytest.raises(ValueError, match="exactly one"):
            BacktestEngine()
        with pytest.raises(ValueError, match="exactly one"):
            BacktestEngine(strategy=DualMACrossover("BTCUSDT", "1d"), router=StrategyRouter())


class TestRouterModeNoTrade:
    def test_empty_router_never_trades_capital_preserved(self):
        """A router with nothing registered must produce zero trades — the
        NO_TRADE/CAPITAL_PRESERVED behavior the owner's directive requires
        when no edge is detected, now actually exercised end-to-end."""
        data = _trending_ohlcv()
        engine = BacktestEngine(router=StrategyRouter(), initial_equity=Decimal("10000"))
        result = engine.run(data)
        assert result.trades == []
        assert result.final_equity == Decimal("10000")


class TestRouterModeRoutesByRegime:
    def test_router_mode_calls_the_registered_strategy_not_a_copy(self):
        strat = _AlwaysSignalsOnce("probe")
        router = StrategyRouter()
        router.register(Regime.TREND_UP, strat, min_confidence=0.0)
        router.register(Regime.RANGE, strat, min_confidence=0.0)
        router.register(Regime.NO_EDGE, strat, min_confidence=0.0)
        router.register(Regime.BREAKOUT_UP, strat, min_confidence=0.0)
        router.register(Regime.BREAKOUT_DOWN, strat, min_confidence=0.0)
        data = _trending_ohlcv()
        engine = BacktestEngine(router=router, initial_equity=Decimal("10000"))
        engine.run(data)
        # Registered for every regime -> on_bar must have been called every
        # eligible bar, proving the engine is actually invoking the routed
        # strategy object, not silently falling back to anything else.
        assert strat.on_bar_calls > 0
        assert strat.fired

    def test_exit_check_uses_the_strategy_that_opened_the_trade(self):
        """If the regime changes while a position is open, the engine must
        keep asking the ORIGINAL strategy about exiting — not whatever the
        router would route to for the new regime, which doesn't know this
        position exists."""
        opener = _AlwaysSignalsOnce("opener")

        class _NeverAskedToExit(AbstractStrategy):
            def __init__(self):
                super().__init__(strategy_id="bystander", symbol="TESTUSDT", timeframe="1d", params={})
                self.exit_checks = 0

            def on_bar(self, data):
                return None

            def on_exit_signal(self, data, entry_price):
                self.exit_checks += 1
                return False

        bystander = _NeverAskedToExit()
        router = StrategyRouter()
        for regime in Regime:
            router.register(regime, opener if regime is Regime.TREND_UP else bystander, min_confidence=0.0)
        data = _trending_ohlcv()
        engine = BacktestEngine(router=router, initial_equity=Decimal("10000"))
        engine.run(data)
        assert bystander.exit_checks == 0


class TestRouterModeFeeAccountingUnchanged:
    def test_router_mode_single_strategy_matches_fixed_strategy_mode_exactly(self):
        """Routing to the SAME strategy for every regime must produce
        byte-identical results to fixed-strategy mode — the router path
        must not introduce any accounting drift of its own."""
        data = _trending_ohlcv()
        params = {"fast_period": 20, "slow_period": 50, "trend_filter_period": 0}

        fixed = BacktestEngine(
            strategy=DualMACrossover("BTCUSDT", "1d", params=params), initial_equity=Decimal("10000")
        )
        fixed_result = fixed.run(data)

        router = StrategyRouter()
        always_on = DualMACrossover("BTCUSDT", "1d", params=params)
        for regime in Regime:
            router.register(regime, always_on, min_confidence=0.0)
        routed = BacktestEngine(router=router, initial_equity=Decimal("10000"))
        routed_result = routed.run(data)

        assert routed_result.final_equity == fixed_result.final_equity
        assert len(routed_result.trades) == len(fixed_result.trades)
