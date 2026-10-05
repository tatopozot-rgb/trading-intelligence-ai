"""Tests for indicator functions — known-input / known-output pairs."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.analysis.indicators import (
    atr,
    donchian_high,
    donchian_low,
    ema,
    ma_crossover_signal,
    roc,
    rsi,
    sma,
    above_ma_filter,
)


def _series(values: list) -> pd.Series:
    return pd.Series(values, dtype=float)


# ── SMA ──────────────────────────────────────────────────────────────────────

class TestSMA:
    def test_basic(self):
        s = _series([1, 2, 3, 4, 5])
        result = sma(s, 3)
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])
        assert result.iloc[2] == pytest.approx(2.0)
        assert result.iloc[4] == pytest.approx(4.0)

    def test_period_1(self):
        s = _series([10, 20, 30])
        result = sma(s, 1)
        assert list(result) == pytest.approx([10, 20, 30])

    def test_invalid_period(self):
        with pytest.raises(ValueError):
            sma(_series([1, 2, 3]), 0)


# ── EMA ──────────────────────────────────────────────────────────────────────

class TestEMA:
    def test_returns_series_same_length(self):
        s = _series(list(range(1, 21)))
        result = ema(s, 5)
        assert len(result) == len(s)

    def test_warmup_nans(self):
        s = _series([1.0] * 3 + [2.0] * 7)
        result = ema(s, 5)
        assert pd.isna(result.iloc[0])

    def test_converges_to_constant(self):
        # EMA of constant series equals the constant
        s = _series([5.0] * 20)
        result = ema(s, 10)
        assert result.dropna().iloc[-1] == pytest.approx(5.0, abs=1e-9)


# ── ATR ──────────────────────────────────────────────────────────────────────

class TestATR:
    def test_positive(self):
        n = 20
        high = _series([10 + i * 0.1 for i in range(n)])
        low = _series([9 + i * 0.1 for i in range(n)])
        close = _series([9.5 + i * 0.1 for i in range(n)])
        result = atr(high, low, close, period=5)
        # All non-NaN ATR values should be positive
        assert (result.dropna() > 0).all()

    def test_zero_range(self):
        # If every bar has zero range, ATR = 0
        s = _series([100.0] * 20)
        result = atr(s, s, s, period=5)
        assert (result.dropna().abs() < 1e-10).all()


# ── RSI ──────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_bounds(self):
        np.random.seed(42)
        prices = pd.Series(100 + np.random.randn(100).cumsum())
        result = rsi(prices, period=14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_all_up_days_rsi_near_100(self):
        s = _series([float(i) for i in range(1, 31)])
        result = rsi(s, period=14)
        valid = result.dropna()
        assert len(valid) > 0, "RSI should produce valid values for 30 bars with period=14"
        assert valid.iloc[-1] > 90

    def test_all_down_days_rsi_near_0(self):
        s = _series([float(i) for i in range(30, 0, -1)])
        result = rsi(s, period=14)
        assert result.dropna().iloc[-1] < 10


# ── ROC ──────────────────────────────────────────────────────────────────────

class TestROC:
    def test_known_value(self):
        s = _series([100, 110, 121])
        result = roc(s, period=1)
        # bar 1: (110-100)/100 = 0.10
        assert result.iloc[1] == pytest.approx(0.10)

    def test_flat_is_zero(self):
        s = _series([50.0] * 15)
        result = roc(s, period=5)
        assert (result.dropna().abs() < 1e-10).all()


# ── Donchian ─────────────────────────────────────────────────────────────────

class TestDonchian:
    def test_high_rolling_max(self):
        s = _series([1, 3, 2, 5, 4])
        result = donchian_high(s, period=3)
        assert result.iloc[2] == pytest.approx(3.0)
        assert result.iloc[4] == pytest.approx(5.0)

    def test_low_rolling_min(self):
        s = _series([5, 3, 4, 1, 2])
        result = donchian_low(s, period=3)
        assert result.iloc[2] == pytest.approx(3.0)
        assert result.iloc[4] == pytest.approx(1.0)


# ── MA Crossover Signal ───────────────────────────────────────────────────────

class TestMACrossoverSignal:
    def _make_crossover_data(self) -> pd.Series:
        # Prices rise from 10 to 30, causing fast MA to cross above slow MA
        return _series([float(i) for i in range(10, 50)])

    def test_invalid_periods(self):
        with pytest.raises(ValueError):
            ma_crossover_signal(_series([1.0] * 10), fast_period=10, slow_period=5)

    def test_signal_values_in_set(self):
        s = self._make_crossover_data()
        result = ma_crossover_signal(s, fast_period=5, slow_period=10)
        assert set(result.unique()).issubset({-1, 0, 1})

    def test_bullish_crossover_occurs(self):
        # Trending up then flat: at some point fast crosses above slow
        prices = _series([10.0] * 20 + [float(i) for i in range(10, 40)])
        result = ma_crossover_signal(prices, fast_period=5, slow_period=15, ma_type="sma")
        assert (result == 1).any()


# ── Above MA Filter ───────────────────────────────────────────────────────────

class TestAboveMAFilter:
    def test_trending_up(self):
        s = _series([float(i) for i in range(1, 30)])
        result = above_ma_filter(s, period=10)
        # Near end, price should be above MA
        assert result.dropna().iloc[-1] is True or result.dropna().iloc[-1] == True

    def test_trending_down(self):
        s = _series([float(i) for i in range(30, 0, -1)])
        result = above_ma_filter(s, period=10)
        # Near end, price should be below MA
        assert not result.dropna().iloc[-1]
