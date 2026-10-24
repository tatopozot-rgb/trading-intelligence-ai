"""Tests for research_keltner (synthetic daily candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_keltner as rk
from trading_intelligence.backtesting import research_macd as rmc


def _frame(closes, start="2025-01-01", spread=0.5):
    c = np.array(closes, float)
    o = np.concatenate([[c[0]], c[:-1]])
    idx = pd.date_range(start, periods=len(c), freq="D", tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c}, index=idx)


def _flat_burst_fade():
    return [100.0] * 40 + list(100 + np.cumsum(np.full(15, 4.0))) + list(np.linspace(160, 120, 25))


@pytest.fixture
def free(monkeypatch):
    monkeypatch.setattr(rmc, "FEE", 0.0)
    monkeypatch.setattr(rmc, "SLIP", 0.0)


def test_channel_uses_ema20_and_wilder_atr10():
    f = _frame(_flat_burst_fade())
    ema, upper = rk.channel(f)
    c = f["close"]
    assert ema[-1] == pytest.approx(c.ewm(span=20, adjust=False).mean().iloc[-1])
    assert ema[39] == pytest.approx(100.0) and upper[39] == pytest.approx(100.0 + 2 * 1.0, rel=1e-3)  # range 1


def test_signals_follow_closes_against_the_bands():
    f = _frame(_flat_burst_fade())
    ema, upper = rk.channel(f)
    x = rk.signals(f)
    c = f["close"].to_numpy()
    assert (x.up == (c > upper)).all() and (x.down == (c < ema)).all()
    assert not x.up[:40].any() and x.up[40:55].any()


def test_version_a_buys_the_breakout_and_sells_under_the_ema(free):
    f = _frame(_flat_burst_fade())
    x = rk.signals(f)
    book, _ = rmc.simulate(f, x, 1, len(f), 1000.0, False)
    t = book.trades[0]
    assert t["in"] == str(f.index[int(np.flatnonzero(x.up)[0]) + 1].date()) and t["why"] == "señal"
    assert t["ret_pct"] > 0


def test_version_b_stop_rides_the_previous_ema(free):
    f = _frame(_flat_burst_fade())
    x = rk.signals(f)
    trail = rk.trail_levels(f)
    ema, _ = rk.channel(f)
    assert trail[50] == pytest.approx(ema[49]) and np.isnan(trail[0])
    n = len(f)
    book, _ = rmc.simulate(f, x, 1, n, 1000.0, True, gate=np.ones(n, bool), events=np.zeros(n, bool),
                           stop_fn=lambda *_: 1.0, trail=trail)
    assert book.trades[0]["why"] == "stop" and book.trades[0]["ret_pct"] > 0


def test_same_three_decisive_rows():
    assert list(rk.ROWS) == ["a_juntas", "b_juntas", "b_btc"]
