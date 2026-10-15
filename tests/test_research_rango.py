"""Tests for research_rango (synthetic candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_rango as rr


def _data(n_coins=2, T=12, freq="D", start="2026-01-01"):
    bars = pd.date_range(start, periods=T, freq=freq, tz="UTC")
    o = np.full((n_coins, T), 100.0)
    names = [f"C{i}USDT" for i in range(n_coins - 1)] + ["BTCUSDT"]
    return rr.Data(bars, o.copy(), o.copy(), o.copy(), o.copy(), np.ones((n_coins, T)), np.zeros((n_coins, T)), names)


def _sig(d, adx=10.0, atr=2.0, mid=100.0, width=5.0):
    full = lambda v: np.full(d.close.shape, v)  # noqa: E731
    return rr.Signals(full(mid), full(mid + width), full(mid - width), full(adx), full(atr))


def test_trade_return_costs_and_funding():
    r = rr.trade_return(1, 100.0, 102.0, 0.03)
    assert r == pytest.approx(0.02 - rr.FEE - rr.FEE * 1.02 - 0.0003)
    s = rr.trade_return(-1, 100.0, 98.0, 0.03)  # a short receives positive funding
    assert s == pytest.approx(0.02 - rr.FEE - rr.FEE * 0.98 + 0.0003)


def test_long_below_band_exits_at_open_after_close_at_mean():
    d, s = _data(), None
    s = _sig(d)
    d.close[0, 2] = 94.0  # closes under the lower band (95) while ADX 10 < 20
    d.open[0, 3], d.high[0, 3], d.low[0, 3], d.close[0, 3] = 94.0, 96.0, 93.5, 96.0  # still under the mean
    d.open[0, 4], d.high[0, 4], d.low[0, 4], d.close[0, 4] = 96.0, 101.0, 95.5, 100.5  # closes at/over the mean
    d.open[0, 5] = 101.0
    r = rr.simulate(d, s, 2, 8, 20.0)
    (t,) = r.trades
    assert t["side"] == 1 and t["why"] == "media" and t["bars"] == 2
    expected = rr.trade_return(1, 94.0 * (1 + rr.SLIP), 101.0 * (1 - rr.SLIP), 0.0)
    assert t["ret_pct"] == pytest.approx(expected * 100)
    assert r.equity[-1] == pytest.approx(rr.CAPITAL + rr.CAPITAL / 3 * expected)


def test_no_entry_when_adx_says_trend():
    d = _data()
    s = _sig(d, adx=30.0)
    d.close[0, 2] = 94.0
    assert rr.simulate(d, s, 2, 8, 20.0).trades == []
    assert len(rr.simulate(d, s, 2, 8, 35.0).trades) == 1


def test_short_stop_hit_intrabar_and_gap_fills_at_open():
    d = _data()
    s = _sig(d, atr=2.0)
    d.close[0, 2] = 106.0  # above the upper band (105): short at 100 next open, stop 100 + 1.5 * 2 = 103
    d.high[0, 3] = 104.0
    r = rr.simulate(d, s, 2, 8, 20.0)
    (t,) = r.trades
    assert t["side"] == -1 and t["why"] == "stop" and t["bars"] == 0
    assert t["ret_pct"] == pytest.approx(rr.trade_return(-1, 100 * (1 - rr.SLIP), 103 * (1 + rr.SLIP), 0.0) * 100)
    d2 = _data()
    d2.close[0, 2] = 106.0
    d2.close[0, 3] = 102.0  # stays above the mean, no exit signal
    d2.open[0, 4], d2.high[0, 4] = 110.0, 111.0  # gaps past the stop: fills at the open
    (t2,) = rr.simulate(d2, s, 2, 8, 20.0).trades
    assert t2["why"] == "stop" and t2["ret_pct"] == pytest.approx(
        rr.trade_return(-1, 100 * (1 - rr.SLIP), 110 * (1 + rr.SLIP), 0.0) * 100)


def test_stop_beats_mean_on_the_same_candle():
    d = _data()
    s = _sig(d, atr=2.0)
    d.close[0, 2] = 94.0  # long at 100, stop 97
    d.low[0, 3], d.close[0, 3] = 96.0, 101.0  # touches the stop and closes over the mean
    (t,) = rr.simulate(d, s, 2, 8, 20.0).trades
    assert t["why"] == "stop"


def test_time_exit_after_ten_candles_and_funding_counted():
    d = _data(T=20)
    s = _sig(d, mid=200.0, width=105.0, atr=50.0)  # lower band 95: a close of 94 enters; mean never reached
    d.close[0, 2] = 94.0
    d.funding[0, :] = 0.01
    (t,) = rr.simulate(d, s, 2, 18, 20.0).trades
    assert t["why"] == "tiempo" and t["bars"] == rr.MAX_BARS
    assert t["ret_pct"] == pytest.approx(rr.trade_return(1, 100 * (1 + rr.SLIP), 100 * (1 - rr.SLIP), 0.1) * 100)


def test_three_slots_go_to_the_most_volume():
    d = _data(n_coins=5)
    s = _sig(d)
    d.close[:, 2] = 94.0
    d.usdt_volume[:, 2] = [5.0, 1.0, 4.0, 2.0, 3.0]
    r = rr.simulate(d, s, 2, 8, 20.0)
    assert sorted({x["symbol"] for x in r.trades}) == sorted([d.names[0], d.names[2], d.names[4]])


def test_brakes_block_shorts_events_and_weak_regime():
    d = _data()
    s = _sig(d)
    d.close[0, 2] = 106.0  # a short signal: blocked by the brakes
    assert rr.simulate(d, s, 2, 8, 20.0, brakes=True).trades == []
    assert len(rr.simulate(d, s, 2, 8, 20.0).trades) == 1


def test_regime_uses_the_last_complete_day_on_4h_bars():
    T = 6 * 60
    d = _data(T=T, freq="4h")
    d.close[-1] = np.linspace(100, 200, T)  # BTC rising: above its 50-day mean once there is history
    ok = rr.regime_by_bar(d)
    day = d.bars.floor("D")
    assert not ok[day < day[0] + pd.Timedelta(days=50)].any()
    assert ok[-1]
    same_day = day == day[-1]
    assert len(set(ok[same_day])) == 1  # every 4h bar of a day uses the same, previous, daily close


def test_build_buckets_funding_into_4h_bars():
    bars = pd.date_range("2026-01-01", periods=6, freq="4h", tz="UTC")
    k = pd.DataFrame({c: 100.0 for c in ("open", "high", "low", "close", "volume")}, index=bars)
    f = pd.Series([0.01, 0.02, 0.03], index=pd.to_datetime(["2026-01-01 00:00", "2026-01-01 08:00",
                                                          "2026-01-01 16:00"], utc=True))
    d = rr.build([("BTCUSDT", k, f)], "4h")
    assert d.funding[0].tolist() == pytest.approx([0.01, 0.0, 0.02, 0.0, 0.03, 0.0])
