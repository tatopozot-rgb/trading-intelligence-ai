"""Tests for research_volatilidad (synthetic data, no network)."""
import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_saturado as rsat
from trading_intelligence.backtesting import research_volatilidad as rv
from trading_intelligence.live import desk as D


def _btc(days=500, calm=0.01, storm_from=None, storm=0.08, seed=0):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, calm, days)
    if storm_from is not None:
        r[storm_from:] = rng.normal(0, storm, days - storm_from)
    idx = pd.date_range("2024-01-01", periods=days, freq="D", tz="UTC")
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx)


def test_brake_needs_a_year_of_history_and_fires_in_a_storm():
    s = _btc(storm_from=420)
    b = rv.brake_days(s, 90)
    assert not b.iloc[:372].any()  # no 365-day history yet: no brake
    assert b.iloc[425:432].all()  # the storm's 7-day vol is far above the past year's 90th percentile
    assert b.iloc[380:415].mean() < 0.3  # calm days rarely cross it


def test_brake_uses_only_closed_days():
    s = _btc(storm_from=None)
    b1 = rv.brake_days(s, 90)
    s2 = s.copy()
    s2.iloc[450] *= 3  # a jump on day 450 is only known from day 451
    b2 = rv.brake_days(s2, 90)
    assert (b1.iloc[:451] == b2.iloc[:451]).all() and b2.iloc[451]


def test_bar_mask_maps_days_to_5_minute_bars():
    days = pd.Series([False, True], index=pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"))
    t = pd.date_range("2026-01-01 23:50", periods=4, freq="5min", tz="UTC").as_unit("ns").asi8
    assert list(rv.bar_mask(t, days)) == [False, False, True, True]
    assert not rv.bar_mask(np.array([pd.Timestamp("2027-01-01", tz="UTC").value]), days)[0]


def test_masks_evaluate_and_render(monkeypatch):
    from tests.test_research_mesa import _prepared

    times, rsat.SYMS = rm.align({s: rm.arrays(p, D.DeskRules.load()) for s, p in _prepared(1600).items()})
    monkeypatch.setattr(rm, "BLOCK_BARS", 400)
    every = {n: np.full(len(times), rm.BOTH, dtype=np.int8) for n in rsat.SYMS}
    rsat.REGIME = every
    for s in rsat.SETUPS:
        rsat.ENTRY[(s, "base")] = every
    storm = pd.Series(True, index=pd.date_range("2026-07-01", periods=60, freq="D", tz="UTC"))
    monkeypatch.setattr(rv, "brake_days", lambda close, q: storm)
    share = rv.add_masks(times, pd.Series(dtype=float))
    assert share == {"V80": 100.0, "V90": 100.0, "V95": 100.0}
    table = rsat.evaluate(times, 1, rv.FILTERS)
    assert table["frenos"]["V90"]["trades"] == 0 < table["frenos"]["base"]["trades"]
    y = {"label": "y", "braked_pct": share, "table": table}
    md = rv.render([y, y])
    assert "Freno de volatilidad" in md and "no ayuda" in md
