"""Tests for research_breakout (synthetic candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_breakout as rb


def _data(n_coins=2, T=10, start="2026-01-01"):
    days = pd.date_range(start, periods=T, freq="D", tz="UTC")
    o = np.full((n_coins, T), 100.0)
    h, lo, c = o.copy(), o.copy(), o.copy()  # flat candles: no range, no trigger unless a test sets one
    names = [f"C{i}USDT" for i in range(n_coins - 1)] + ["BTCUSDT"]
    return rb.Data(days, o.copy(), h, lo, c, np.ones((n_coins, T)), np.zeros((n_coins, T)), names)


def test_trade_return_costs_and_funding():
    r = rb.trade_return(1, 101.0, 100.0, 103.0, 0.03)
    fill_in, fill_out = 101 * 1.0002, 103 * 0.9998
    assert r == pytest.approx((fill_out - fill_in) / fill_in - rb.FEE - rb.FEE * fill_out / fill_in - 0.0003)
    s = rb.trade_return(-1, 99.0, 100.0, 97.0, 0.03)  # a short receives positive funding
    assert s > 0 and s == pytest.approx((99 * 0.9998 - 97 * 1.0002) / (99 * 0.9998) - rb.FEE - rb.FEE * 97 * 1.0002 / (99 * 0.9998) + 0.0003)


def test_long_trigger_and_exit_at_next_open():
    d = _data()
    d.high[0, 2], d.low[0, 2] = 101.0, 99.0  # range of day 2 = 2, trigger at 100 + 1 = 101
    d.high[0, 3] = 102.0
    d.open[0, 4] = 104.0
    r = rb.simulate(d, 3, 4)
    (t,) = r.trades
    assert t["side"] == 1 and t["ret_pct"] == pytest.approx(rb.trade_return(1, 101.0, 100.0, 104.0, 0.0) * 100)
    assert r.equity[-1] == pytest.approx(rb.CAPITAL + rb.CAPITAL / 3 * t["ret_pct"] / 100)


def test_both_triggers_count_the_worse_and_top_volume_wins():
    d = _data(n_coins=5)
    d.high[:, 2], d.low[:, 2] = 101.0, 99.0
    d.high[:, 3], d.low[:, 3] = 102.0, 98.0  # every coin hits both triggers (range 2, k 0.5 -> 101 / 99)
    d.open[:, 4] = 103.0  # the long would win: the short (worse) counts
    d.usdt_volume[:, 2] = [5, 1, 4, 3, 2]
    r = rb.simulate(d, 3, 4)
    assert r.both_hit == 5 and len(r.trades) == 3
    assert {t["symbol"] for t in r.trades} == {d.names[0], d.names[2], d.names[3]}
    assert all(t["side"] == -1 for t in r.trades)


def test_brakes_block_shorts_event_days_and_bear_regime():
    d = _data(T=60, start="2026-01-01")
    d.close[-1] = np.linspace(100, 150, 60)  # BTC above its mean: regime on
    k = 55
    d.high[0, k - 1], d.low[0, k - 1] = 101.0, 99.0
    d.high[0, k], d.low[0, k] = 102.0, 98.0
    d.open[0, k + 1] = 97.0
    r = rb.simulate(d, k, k + 1, brakes=True)
    assert [t["side"] for t in r.trades] == [1]  # longs only
    d.close[-1] = np.linspace(150, 100, 60)  # BTC below its mean: no entries
    assert rb.simulate(d, k, k + 1, brakes=True).trades == []
    ev = _data(T=60, start="2026-01-01")
    ev.close[-1] = np.linspace(100, 150, 60)
    day = int(ev.days.searchsorted(pd.Timestamp("2026-01-28", tz="UTC")))  # FOMC 2026-01-28
    ev.high[0, day - 1], ev.low[0, day - 1] = 101.0, 99.0
    ev.high[0, day] = 102.0
    assert rb.simulate(ev, day, day + 1, brakes=True).trades == []
    assert rb.simulate(ev, day, day + 1, brakes=False).trades


def test_year_and_render():
    T = 900
    rng = np.random.default_rng(1)
    d = _data(n_coins=4, T=T, start="2024-06-01")
    walk = 100 * np.cumprod(1 + rng.normal(0, 0.02, (4, T)), axis=1)
    d.open, d.close = walk, walk * (1 + rng.normal(0, 0.01, (4, T)))
    d.high = np.maximum(d.open, d.close) * 1.02
    d.low = np.minimum(d.open, d.close) * 0.98
    ys = [rb.year(d, a, b) for a, b in rb.YEARS]
    assert set(ys[0]["rows"]) == {f"{v}, k={k:g}" for v in ("A pura", "B con frenos") for k in (0.5, 0.25, 0.75)}
    md = rb.render(ys, {"simbolos": d.names})
    assert "Larry Williams" in md and "k = 0,5" in md
