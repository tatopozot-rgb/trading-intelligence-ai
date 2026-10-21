"""Tests for research_ttm (synthetic daily candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_ttm as rt


def _frame(closes, start="2025-01-01", spread=0.5):
    c = np.array(closes, float)
    o = np.concatenate([[c[0]], c[:-1]])
    idx = pd.date_range(start, periods=len(c), freq="D", tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c}, index=idx)


def test_linreg_last_is_the_fitted_end_of_the_line():
    x = pd.Series(np.arange(30, dtype=float) * 2 + 5)
    assert rt.linreg_last(x, 20).iloc[-1] == pytest.approx(x.iloc[-1])
    noisy = pd.Series([1.0, 3.0, 2.0, 4.0])
    a, b = np.polyfit(np.arange(4), noisy, 1)
    assert rt.linreg_last(noisy, 4).iloc[-1] == pytest.approx(a * 3 + b)


def test_quiet_market_squeezes_and_a_breakout_releases_and_buys():
    rng = np.random.default_rng(0)
    quiet = list(100 + rng.normal(0, 0.05, 60))  # tight closes, wide daily ranges: Bollinger inside Keltner
    burst = list(100 + np.cumsum(np.full(10, 3.0)))
    f = _frame(quiet + burst, spread=1.0)
    on, mom = rt.squeeze(f)
    assert on[40:59].all()
    x = rt.signals(f)
    first = int(np.flatnonzero(x.up)[0])
    assert first >= 60 and on[first - 1] and not on[first] and mom[first] > 0 and mom[first] > mom[first - 1]


def test_exit_needs_two_falling_momentum_closes():
    f = _frame(list(np.linspace(100, 150, 60)) + list(np.linspace(150, 120, 15)))
    _, mom = rt.squeeze(f)
    x = rt.signals(f)
    k = int(np.flatnonzero(x.down)[0])
    assert mom[k] < mom[k - 1] < mom[k - 2]
    assert not x.down[k - 1] or mom[k - 1] < mom[k - 2] < mom[k - 3]


def test_prepare_uses_ttm_signals():
    frames = {k: _frame(np.linspace(100, 200, 400), start="2024-01-01") for k in ("btc", "eth")}
    mk = rt.prepare(frames, {})
    assert set(mk.cross) == {"btc", "eth"} and len(mk.cross["btc"].up) == 400
