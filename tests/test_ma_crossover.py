"""Tests for DualMACrossover strategy."""
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover


def _make_ohlcv(prices: list, volume: float = 1000.0) -> pd.DataFrame:
    """Create OHLCV DataFrame from close prices. Synthetic OHLC around close."""
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="1D")
    closes = np.array(prices, dtype=float)
    return pd.DataFrame(
        {
            "open": closes * 0.999,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": volume,
        },
        index=idx,
    )


class TestDualMACrossoverValidation:
    def test_invalid_fast_slow(self):
        with pytest.raises(ValueError, match="fast_period"):
            DualMACrossover(
                "BTCUSDT", "1d",
                params={"fast_period": 50, "slow_period": 20},
            )

    def test_invalid_ma_type(self):
        with pytest.raises(ValueError, match="ma_type"):
            DualMACrossover(
                "BTCUSDT", "1d",
                params={"fast_period": 10, "slow_period": 50, "ma_type": "wma"},
            )


class TestDualMACrossoverSignals:
    def _strategy(self, **kwargs) -> DualMACrossover:
        params = {"fast_period": 5, "slow_period": 10, "trend_filter_period": 0, **kwargs}
        return DualMACrossover("BTCUSDT", "1d", params=params)

    def test_no_signal_with_insufficient_data(self):
        strategy = self._strategy()
        data = _make_ohlcv([100.0] * 5)
        assert strategy.on_bar(data) is None

    def test_no_signal_flat_prices(self):
        # Flat prices → no crossover
        strategy = self._strategy()
        data = _make_ohlcv([100.0] * 50)
        assert strategy.on_bar(data) is None

    def test_proposal_has_stop(self):
        """Any proposal must contain a valid stop_price below entry."""
        strategy = self._strategy()
        # Rising then flat: at some bar a signal will fire
        prices = [100.0] * 10 + [float(100 + i * 2) for i in range(40)]
        data = _make_ohlcv(prices)
        # Scan all bars
        proposal = None
        for i in range(len(data)):
            sub = data.iloc[: i + 1]
            p = strategy.on_bar(sub)
            if p is not None:
                proposal = p
                break
        if proposal is not None:
            assert proposal.stop_price is not None
            assert isinstance(proposal.stop_price, Decimal)
            assert proposal.stop_price < Decimal(str(data["close"].iloc[i]))

    def test_trend_filter_suppresses_signal(self):
        """Signal should be suppressed when price is below trend filter MA."""
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={
                "fast_period": 5,
                "slow_period": 10,
                "trend_filter_period": 20,
                "trend_filter_ma_type": "sma",
            },
        )
        # Downtrend: prices falling — fast will cross above slow during dead-cat bounces
        # but trend filter (200 MA) should suppress
        # Simpler test: build flat data at low level — price below 20-bar SMA is impossible
        # with only flat data, so use: first 20 bars at 100, next bars at 50
        prices = [100.0] * 25 + [50.0, 52.0, 54.0, 56.0, 58.0, 60.0, 62.0, 64.0]
        data = _make_ohlcv(prices)
        proposal = strategy.on_bar(data)
        # Price at end is ~64, trend filter (SMA 20) is around 65-80 → price below filter
        # So proposal should be None
        assert proposal is None

    def test_exit_signal_on_bearish_crossover(self):
        """on_exit_signal returns True when fast crosses below slow."""
        strategy = self._strategy()
        # Build data where fast MA is now crossing below slow MA
        # Declining prices after rise → fast MA drops below slow
        prices = [float(100 + i) for i in range(20)] + [float(120 - i * 3) for i in range(20)]
        data = _make_ohlcv(prices)
        entry_price = Decimal("120")
        # Scan for exit signal
        found_exit = False
        for i in range(15, len(data)):
            sub = data.iloc[: i + 1]
            if strategy.on_exit_signal(sub, entry_price):
                found_exit = True
                break
        assert found_exit
