"""Smoke test for BacktestEngine — confirms the engine runs end-to-end."""
from decimal import Decimal

import numpy as np
import pandas as pd

from trading_intelligence.backtesting.backtest_engine import BacktestEngine
from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover


def _make_trending_ohlcv(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Synthetic trending price series for integration testing."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.015, n)  # slight upward drift
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


class TestBacktestEngineSmoke:
    def test_runs_without_error(self):
        data = _make_trending_ohlcv()
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        result.compute_metrics()
        assert isinstance(result.total_trades, int)
        assert result.total_trades >= 0

    def test_equity_curve_non_empty(self):
        data = _make_trending_ohlcv()
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        assert len(result.equity_curve) > 0

    def test_all_trades_have_exit(self):
        """Every trade in a completed backtest should have an exit."""
        data = _make_trending_ohlcv(n=300)
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 10, "slow_period": 30, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        for trade in result.trades:
            assert trade.exit_price is not None, f"Trade {trade.entry_time} has no exit"

    def test_fees_are_positive(self):
        data = _make_trending_ohlcv()
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        for trade in result.trades:
            if trade.exit_price is not None:
                assert trade.entry_fee >= 0
                assert trade.exit_fee >= 0

    def test_metrics_summary_string(self):
        data = _make_trending_ohlcv()
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        result.compute_metrics()
        s = result.summary()
        assert "Sharpe" in s
        assert "PF" in s
