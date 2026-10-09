"""Tests for the EXPLORATORY spot momentum variants. No network."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import spot_momentum_variants as sv
from trading_intelligence.backtesting import two_way_momentum as tw

DAYS = pd.date_range("2019-01-01", periods=400, freq="1D", tz="UTC")


def _frames(paths):
    closes = pd.DataFrame(paths, index=DAYS)
    return closes, closes.shift(1).fillna(closes.iloc[0])


def _weeks(closes, opens):
    return [m for m in tw.mondays("2019-01-01", "2020-01-30") if sv.signal_inputs(closes, opens, m)]


def test_weights():
    inputs = {"A": (0.10, 0.8), "B": (0.20, 0.8), "C": (0.05, 0.4), "D": (-0.1, 0.5), "E": (0.3, 2.0)}
    a = sv.weights("A", inputs)
    assert "D" not in a and a["C"] == pytest.approx(1 / 5)  # shorts become cash; low vol capped at 1/N
    b = sv.weights("B", inputs)
    assert set(b) == {"B", "E", "C"}  # top-3 by r/sigma: B .25, E .15, then C over A on the .125 tie
    assert all(v <= sv.MAX_WEIGHT for v in b.values()) and sum(b.values()) <= 1 + 1e-12


def test_long_only_never_shorts_and_downtrend_stays_in_cash():
    rng = np.random.default_rng(0)
    down = 100 * np.cumprod(1 - 0.004 + rng.normal(0, 0.01, 400))
    closes, opens = _frames({"X": down})
    for v in sv.VARIANTS:
        r = sv.simulate(closes, opens, _weeks(closes, opens), v)
        assert r.total_return > -0.05  # mostly cash in a downtrend


def test_trailing_stop_exits_and_waits_for_monday():
    up = np.r_[100 * np.cumprod(np.full(300, 1.004)), np.linspace(0, 0, 100)]
    up[300:] = up[299] * np.cumprod(np.full(100, 0.97))  # crash
    closes, opens = _frames({"X": up})
    weeks = _weeks(closes, opens)
    b = sv.simulate(closes, opens, weeks, "B")
    c = sv.simulate(closes, opens, weeks, "C")
    assert c.stops >= 1 and c.total_return > b.total_return


def test_run_period_and_min_equity():
    rng = np.random.default_rng(2)
    paths = {s: 100 * np.cumprod(1 + 0.002 + rng.normal(0, 0.03, 400)) for s in ("A", "B", "C", "D")}
    closes, opens = _frames(paths)
    res = sv.run_period(closes, opens, "2019-01-01", "2020-02-01")
    assert set(sv.VARIANTS) <= set(res) and res["A"]["turnover_per_week"] > 0
    mq = sv.min_equity_for_a(closes, opens, "2019-01-01", "2020-02-01")
    assert mq["median"] >= sv.MIN_ORDER_USDT * 4  # 4 symbols, each <= 1/4 of equity
    assert "Minimum equity" in sv.render("T", res, mq)
