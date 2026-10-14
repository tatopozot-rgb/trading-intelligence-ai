"""Tests for research_ewmac (synthetic data, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_ewmac as ew


def _data(paths, start="2023-01-01"):
    paths = np.atleast_2d(np.array(paths, dtype=float))
    n, T = paths.shape
    days = pd.date_range(start, periods=T, freq="D", tz="UTC")
    names = [f"C{i}USDT" for i in range(n - 1)] + ["BTCUSDT"]
    return ew.Data(days, paths.copy(), paths.copy(), np.zeros((n, T)), names)


def test_forecast_is_causal_and_scalar_uses_only_the_fit_window():
    rng = np.random.default_rng(0)
    p = 100 * np.cumprod(1 + rng.normal(0.001, 0.02, (3, 700)), axis=1)
    raw, vol = ew.raw_forecasts(p)
    q = p.copy()
    q[:, 600:] *= 3  # change the future only
    raw2, _ = ew.raw_forecasts(q)
    assert np.allclose(np.nan_to_num(raw[:, :, :600]), np.nan_to_num(raw2[:, :, :600]))
    assert np.allclose(ew.scalars(raw, 500, 590), ew.scalars(raw2, 500, 590))
    s = ew.scalars(raw, 500, 590)
    for k in range(len(ew.PAIRS)):
        x = np.abs(raw[k, :, 500:590] * s[k])
        assert np.nanmean(x) == pytest.approx(10.0)


def test_targets_top_three_caps_and_one_x():
    f = np.array([20.0, -15.0, 5.0, 12.0, np.nan])
    vol = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
    t = ew.targets(f, vol)
    assert t[2] == 0 and t[4] == 0  # weakest and unknown dropped
    assert np.count_nonzero(t) == 3 and t[1] < 0
    assert np.abs(t).max() <= ew.MAX_POSITION + 1e-12 and np.abs(t).sum() <= 1 + 1e-12
    small = ew.targets(np.array([10.0, 0, 0]), np.array([0.05, 0.05, 0.05]))
    assert small[0] == pytest.approx(10 / 10 * 0.01 / 0.05)  # 20% of equity: 1% daily vol at forecast 10


def test_uptrend_goes_long_downtrend_short_and_buffer_limits_orders():
    T = 900
    up = 100 * np.exp(np.linspace(0, 1.5, T)) * (1 + 0.01 * np.sin(np.arange(T)))
    down = 100 * np.exp(np.linspace(0, -1.5, T)) * (1 + 0.01 * np.cos(np.arange(T)))
    d = _data([up, down])
    r = ew.simulate(d, 600, 840)
    last = {}
    for tr in r.trades:
        last[tr["symbol"]] = tr["to"]
    assert last["C0USDT"] > 0 and last["BTCUSDT"] < 0
    assert r.equity[-1] > ew.CAPITAL  # both trends paid
    assert len(r.trades) < 240  # the 10% buffer keeps it from trading every day
    assert r.fees > 0


def test_orders_fill_at_the_next_open_and_funding_is_charged():
    T = 800
    up = 100 * np.exp(np.linspace(0, 1.2, T))
    d = _data([up, up * 2])
    d.open[:, 650] = d.close[:, 649] * 1.05  # a gap at the open of the day after the first decision
    d.funding[:, :] = 0.03
    r = ew.simulate(d, 649, 700)
    assert r.trades[0]["day"] == str(d.days[650].date())
    assert r.funding > 0  # longs pay positive funding


def test_year_and_render_verdict():
    T = 1400
    rng = np.random.default_rng(3)
    p = 100 * np.cumprod(1 + rng.normal(0.0005, 0.02, (4, T)), axis=1)
    d = _data(p, start="2022-06-01")
    ys = [ew.year(d, a, b) for a, b in ew.YEARS]
    assert all(len(y["quarters"]) == 4 for y in ys)
    md = ew.render(ys, {"simbolos": d.names})
    assert "EWMAC de Carver" in md and ("**No pasa:**" in md or "**Pasa a práctica:**" in md)
    assert set(ys[0]["beats"]) == {"mesa_r3", ew.PRACTICE}
