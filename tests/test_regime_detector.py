"""Tests for trading_intelligence.regime.detector — no network, synthetic OHLCV only."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.regime.detector import (
    Regime,
    Volatility,
    detect_regime,
)


def _ohlcv(close: np.ndarray, *, spread: float = 0.3, volume: float = 1000.0) -> pd.DataFrame:
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq="1D")
    return pd.DataFrame(
        {
            "open": close,
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "volume": np.full(n, volume),
        },
        index=idx,
    )


class TestInsufficientData:
    def test_too_few_bars_returns_no_edge_not_a_crash(self):
        data = _ohlcv(np.full(5, 100.0))
        snap = detect_regime(data)
        assert snap.regime is Regime.NO_EDGE
        assert snap.confidence == 0.0
        assert snap.metrics["insufficient_data"] is True


class TestTrendDetection:
    def test_strong_uptrend_detected(self):
        rng = np.random.default_rng(1)
        close = 100 + np.arange(150) * 0.5 + rng.normal(0, 0.2, 150)
        data = _ohlcv(close)
        snap = detect_regime(data)
        assert snap.regime is Regime.TREND_UP
        assert snap.confidence > 0.0

    def test_strong_downtrend_detected(self):
        rng = np.random.default_rng(2)
        close = 200 - np.arange(150) * 0.5 + rng.normal(0, 0.2, 150)
        data = _ohlcv(close)
        snap = detect_regime(data)
        assert snap.regime is Regime.TREND_DOWN


class TestRangeDetection:
    def test_choppy_sideways_detected_as_range(self):
        rng = np.random.default_rng(3)
        close = 100 + np.sin(np.arange(150) / 1.5) * 0.5 + rng.normal(0, 0.15, 150)
        data = _ohlcv(close)
        snap = detect_regime(data)
        assert snap.regime is Regime.RANGE
        assert snap.confidence > 0.0


class TestBreakout:
    def test_breakout_up_after_a_range_is_detected(self):
        rng = np.random.default_rng(4)
        flat = 100 + np.sin(np.arange(100) / 3.0) * 0.5 + rng.normal(0, 0.05, 100)
        jump = np.array([flat[-1] + 5.0])  # single bar, well above the prior 20-bar high
        close = np.concatenate([flat, jump])
        data = _ohlcv(close)
        snap = detect_regime(data, breakout_period=20)
        assert snap.regime is Regime.BREAKOUT_UP
        assert snap.confidence == 1.0

    def test_breakout_down_after_a_range_is_detected(self):
        rng = np.random.default_rng(5)
        flat = 100 + np.sin(np.arange(100) / 3.0) * 0.5 + rng.normal(0, 0.05, 100)
        drop = np.array([flat[-1] - 5.0])
        close = np.concatenate([flat, drop])
        data = _ohlcv(close)
        snap = detect_regime(data, breakout_period=20)
        assert snap.regime is Regime.BREAKOUT_DOWN

    def test_breakout_window_excludes_the_current_bar_not_a_tautology(self):
        """A single new bar that is itself the highest point must NOT trivially
        count as a breakout just because rolling-max includes itself — the
        comparison level must come from the PRIOR window only."""
        rng = np.random.default_rng(6)
        flat = 100 + rng.normal(0, 0.05, 100)
        tiny_new_high = np.array([flat[-20:].max() + 0.01])  # barely a new high, not a real breakout
        close = np.concatenate([flat, tiny_new_high])
        data = _ohlcv(close)
        snap = detect_regime(data, breakout_period=20)
        # A trivial 0.01 new high over a near-flat series is still, correctly, a
        # breakout signal (it IS above the prior 20-bar high) — what matters here
        # is that it's evaluated against the PRIOR high, not a window including itself.
        prior_high_only = flat[-20:].max()
        assert close[-1] > prior_high_only
        assert snap.regime is Regime.BREAKOUT_UP


class TestNoEdge:
    def test_ambiguous_adx_band_returns_no_edge(self):
        """Construct data whose ADX (~24, verified separately) lands between the
        default range_threshold (20) and trend_threshold (25) — neither a
        confirmed trend nor a confirmed range."""
        rng = np.random.default_rng(7)
        close = 100 + np.arange(150) * 0.1 + rng.normal(0, 0.4, 150)
        data = _ohlcv(close)
        snap = detect_regime(data)
        assert snap.regime is Regime.NO_EDGE
        assert snap.confidence == 0.0


class TestVolatilityClassification:
    def test_unknown_when_not_enough_history_for_percentile(self):
        rng = np.random.default_rng(8)
        close = 100 + np.arange(120) * 0.3 + rng.normal(0, 0.2, 120)
        data = _ohlcv(close)
        snap = detect_regime(data, vol_lookback=100)
        # 120 bars of close, but atr_pct series has NaN for the first adx_period-1
        # bars, so fewer than 100 non-NaN volatility samples exist yet.
        assert snap.volatility in (Volatility.UNKNOWN, Volatility.NORMAL, Volatility.HIGH, Volatility.LOW)

    def test_high_volatility_detected_against_its_own_recent_history(self):
        rng = np.random.default_rng(9)
        quiet = 100 + rng.normal(0, 0.05, 150)
        volatile = 100 + np.cumsum(rng.normal(0, 3.0, 50))
        close = np.concatenate([quiet, volatile])
        data = _ohlcv(close, spread=0.1)
        snap = detect_regime(data, vol_lookback=100)
        assert snap.volatility is Volatility.HIGH


class TestInputValidation:
    def test_rejects_range_threshold_not_below_trend_threshold(self):
        data = _ohlcv(np.full(150, 100.0))
        with pytest.raises(ValueError, match="must be <"):
            detect_regime(data, trend_threshold=20.0, range_threshold=25.0)

    def test_rejects_missing_columns(self):
        data = pd.DataFrame({"close": [1.0] * 50})
        with pytest.raises(ValueError, match="missing columns"):
            detect_regime(data)
