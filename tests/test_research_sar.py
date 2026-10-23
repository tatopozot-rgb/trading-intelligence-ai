"""Tests for research_sar (synthetic daily candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_macd as rmc
from trading_intelligence.backtesting import research_sar as rs


def _frame(closes, start="2025-01-01", spread=0.5):
    c = np.array(closes, float)
    o = np.concatenate([[c[0]], c[:-1]])
    idx = pd.date_range(start, periods=len(c), freq="D", tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c}, index=idx)


def _vee():
    return list(np.linspace(200, 100, 40)) + list(np.linspace(100, 200, 40)) + list(np.linspace(200, 140, 30))


@pytest.fixture
def free(monkeypatch):
    monkeypatch.setattr(rmc, "FEE", 0.0)
    monkeypatch.setattr(rmc, "SLIP", 0.0)


def test_rising_sar_stays_under_the_two_previous_lows_and_accelerates():
    f = _frame(list(np.linspace(100, 200, 50)))
    p = rs.parabolic(f)
    lo = f["low"].to_numpy()
    assert p.up[2:].all()  # day 1's low only ties day 0's (a synthetic artifact), so the trend starts on day 2
    assert all(p.level[i] <= min(lo[i - 1], lo[i - 2]) + 1e-9 for i in range(3, 50))
    gaps = np.diff(p.level[3:])
    assert gaps[-1] > gaps[2] > 0  # the stop closes faster as the trend lasts


def test_first_steps_follow_wilder():
    idx = pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC")
    f = pd.DataFrame({"open": [9.5, 9.6, 10.9, 11.9], "high": [10.0, 11.0, 12.0, 13.0], "low": [9.0, 9.5, 10.5, 11.5],
                      "close": [9.5, 10.8, 11.8, 12.8]}, index=idx)
    p = rs.parabolic(f)
    assert p.level[1] == 9.0  # the low of day 0
    assert p.level[2] == 9.0  # 9 + 0.04 x (11 - 9) = 9.08, held under the low of day 0
    assert p.level[3] == pytest.approx(9.18)  # 9 + 0.06 x (12 - 9): AF rose with each new high
    assert p.up[1:].all()


def test_reversal_puts_the_sar_at_the_extreme_point_and_signals_follow_closes():
    f = _frame(_vee())
    p = rs.parabolic(f)
    flips = np.flatnonzero(p.up[1:] != p.up[:-1]) + 1
    assert len(flips) >= 2
    k = int(flips[-1])  # the turn down after the rally
    assert not p.up[k] and p.sar[k] == pytest.approx(f["high"].iloc[:k].max())
    x = rs.signals(f, p)
    c = f["close"].to_numpy()
    for j in np.flatnonzero(x.up):
        assert c[j] > p.sar[j] and c[j - 1] < p.sar[j - 1]
    assert (x.down == (c < p.sar)).all()


def test_version_a_buys_the_turn_up_and_sells_the_turn_down(free):
    f = _frame(_vee())
    p = rs.parabolic(f)
    x = rs.signals(f, p)
    book, _ = rmc.simulate(f, x, 1, len(f), 1000.0, False)
    t = book.trades[0]
    j_in = int(np.flatnonzero(x.up)[0]) + 1
    assert t["in"] == str(f.index[j_in].date()) and t["why"] == "señal" and t["ret_pct"] > 0


def test_version_b_trails_the_stop_up_with_the_sar(free):
    f = _frame(_vee())
    p = rs.parabolic(f)
    x = rs.signals(f, p)
    trail = rs.trail_levels(p)
    n = len(f)
    book, _ = rmc.simulate(f, x, 1, n, 1000.0, True, gate=np.ones(n, bool), events=np.zeros(n, bool),
                           stop_fn=lambda *_: 1.0, trail=trail)
    t = book.trades[0]
    assert t["why"] == "stop"  # the far desk stop never binds; the SAR level does, intraday
    out = f.index.get_loc(pd.Timestamp(t["out"], tz="UTC"))
    assert f["low"].iloc[out] <= trail[out] and t["ret_pct"] > 0


def test_three_decisive_rows_with_btc_alone():
    assert list(rs.ROWS) == ["a_juntas", "b_juntas", "b_btc"]
    assert rs.ROWS["b_btc"][1] == ("btc",) and rs.ROWS["b_btc"][2] and not rs.ROWS["a_juntas"][2]
