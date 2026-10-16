"""Tests for research_rsi2 (synthetic candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_breakout as rb
from trading_intelligence.backtesting import research_rsi2 as rs


def _data(closes: dict[str, list[float]], start="2026-01-01", funding=0.0) -> rb.Data:
    names = sorted(closes)
    c = np.array([closes[s] for s in names], float)
    o = np.c_[c[:, :1], c[:, :-1]]  # opens at yesterday's close
    days = pd.date_range(start, periods=c.shape[1], freq="D", tz="UTC")
    return rb.Data(days, o, np.maximum(o, c), np.minimum(o, c), c, np.ones_like(c), np.full(c.shape, funding), names)


def _uptrend_with_dip(n=210, dip_at=205, depth=(8.0, 8.0)):
    px = list(100 + 0.5 * np.arange(n, dtype=float))
    px[dip_at] = px[dip_at - 1] - depth[0]
    px[dip_at + 1] = px[dip_at] - depth[1]
    for k in range(dip_at + 2, n):
        px[k] = px[dip_at + 1] + 6.0 * (k - dip_at - 1)  # quick rebound
    return px


def test_rsi_is_wilder_with_period_two():
    r = rs.rsi(np.array([[10.0, 11.0, 10.0, 10.0, 12.0]]))[0]
    assert np.isnan(r[1]) and r[2] == pytest.approx(50.0)
    assert r[3] == pytest.approx(100 - 100 / (1 + 0.25 / 0.25))  # gain 0.25, loss 0.25 after a flat day
    assert rs.rsi(np.array([[1.0, 2.0, 3.0, 4.0]]))[0][-1] == 100.0


def test_buys_the_dip_next_open_and_exits_after_close_above_5_day_mean():
    d = _data({"AAAUSDT": _uptrend_with_dip()})
    ind = rs.indicators(d)
    sig = next(k for k in range(200, 210) if ind.rsi[0, k] < 10)
    assert d.close[0, sig] > ind.trend[0, sig]
    r = rs.simulate(d, ind, 200, 210)
    (t,) = r.trades
    assert t["day"] == str(d.days[sig + 1].date()) and t["side"] == 1
    out = int(d.days.searchsorted(pd.Timestamp(t["out"], tz="UTC")))
    first_above = next(k for k in range(sig + 1, 210) if d.close[0, k] > ind.exit_mean[0, k])
    assert out == first_above + 1
    fill_in, fill_out = d.open[0, sig + 1] * (1 + rs.SLIP), d.open[0, out] * (1 - rs.SLIP)
    qty = rs.CAPITAL / rs.MAX_OPEN / fill_in
    pnl = qty * (fill_out - fill_in) - rs.FEE * qty * fill_in - rs.FEE * qty * fill_out
    assert t["ret_pct"] == pytest.approx(pnl / (qty * fill_in) * 100)
    assert r.equity[-1] == pytest.approx(rs.CAPITAL + pnl)


def test_no_buy_below_the_200_day_mean():
    px = list(300 - 0.5 * np.arange(210, dtype=float))  # downtrend: dips are below the 200-day mean
    px[206], px[207] = px[205] - 8, px[205] - 16
    d = _data({"AAAUSDT": px})
    assert rs.simulate(d, rs.indicators(d), 200, 210).trades == []


def test_more_signals_than_slots_takes_the_lowest_rsi():
    coins = {f"C{k}USDT": _uptrend_with_dip(depth=(10.0 + k, 10.0 + k)) for k in range(5)}
    d = _data(coins)
    r = rs.simulate(d, rs.indicators(d), 200, 210)
    first_day = min(t["day"] for t in r.trades)
    taken = sorted(t["symbol"] for t in r.trades if t["day"] == first_day)
    assert taken == ["C2USDT", "C3USDT", "C4USDT"]  # the deepest dips have the lowest RSI-2


def test_funding_is_paid_by_the_long_each_day_held():
    d0 = _data({"AAAUSDT": _uptrend_with_dip()})
    d1 = _data({"AAAUSDT": _uptrend_with_dip()}, funding=0.03)
    t0 = rs.simulate(d0, rs.indicators(d0), 200, 210).trades[0]
    t1 = rs.simulate(d1, rs.indicators(d1), 200, 210).trades[0]
    held = t0["days"]
    assert held >= 1
    assert t0["ret_pct"] - t1["ret_pct"] == pytest.approx(0.03 * held, rel=0.1)


def test_brakes_block_entries_in_bad_regime_and_on_event_days(monkeypatch):
    btc_down = list(400 - 1.0 * np.arange(210, dtype=float))
    d = _data({"AAAUSDT": _uptrend_with_dip(), "BTCUSDT": btc_down})
    ind = rs.indicators(d)
    assert any(t["symbol"] == "AAAUSDT" for t in rs.simulate(d, ind, 200, 210).trades)
    assert rs.simulate(d, ind, 200, 210, brakes=True).trades == []
    d2 = _data({"AAAUSDT": _uptrend_with_dip(), "BTCUSDT": list(100 + 1.0 * np.arange(210, dtype=float))})
    ind2 = rs.indicators(d2)
    assert [t["symbol"] for t in rs.simulate(d2, ind2, 200, 210, brakes=True).trades] == ["AAAUSDT"]
    blocked = np.zeros(210, bool)
    blocked[207] = True
    monkeypatch.setattr(rb, "event_days", lambda days: blocked)
    assert all(t["day"] != str(d2.days[207].date()) for t in rs.simulate(d2, ind2, 200, 210, brakes=True).trades)


def test_open_position_is_closed_at_the_last_close_of_the_year():
    px = _uptrend_with_dip()
    d = _data({"AAAUSDT": px})
    r = rs.simulate(d, rs.indicators(d), 200, 208)  # ends the day after the entry, before any exit
    (t,) = r.trades
    assert t["out"] == str(d.days[207].date())
    assert r.equity[-1] == pytest.approx(rs.CAPITAL * (1 + t["ret_pct"] / 100 / rs.MAX_OPEN))


def test_short_mirror_sells_spikes_below_the_200_day_mean():
    px = list(300 - 0.5 * np.arange(210, dtype=float))
    px[205], px[206] = px[204] + 8, px[204] + 16
    for k in range(207, 210):
        px[k] = px[206] - 6.0 * (k - 206)
    d = _data({"AAAUSDT": px})
    (t,) = rs.simulate(d, rs.indicators(d), 200, 210, side=-1).trades
    assert t["side"] == -1 and t["ret_pct"] > 0


def test_stats_reports_worst_trade_and_quarters():
    d = _data({"AAAUSDT": _uptrend_with_dip()})
    s = rs.stats(rs.simulate(d, rs.indicators(d), 200, 210))
    assert s["trades"] == 1 and s["worst"]["symbol"] == "AAAUSDT" and len(s["quarters"]) == 4
