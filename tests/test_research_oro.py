"""Tests for research_oro (synthetic candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_oro as ro


def _hourly(day="2026-01-05", n_days=1, px=100.0):
    idx = pd.date_range(day, periods=24 * n_days, freq="h", tz="UTC")
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px}, index=idx)


def test_gold_costs_spread_and_wednesday_triple_swap():
    c = ro.Costs("oro")
    assert c.fill(2000.0, 1, True) == pytest.approx(2000.25) and c.fill(2000.0, 1, False) == pytest.approx(1999.75)
    tue = pd.Timestamp("2026-01-06 12:00", tz="UTC")  # Tuesday noon to Thursday noon: Tue night 1 + Wed night 3
    assert c.carry(1, tue, tue + pd.Timedelta(days=2), 10_000) == pytest.approx(10_000 * 0.00015 * 4)
    assert c.carry(-1, tue, tue + pd.Timedelta(hours=2), 10_000) == 0.0
    assert ro.Costs("oro", 2.0).fill(2000.0, -1, True) == pytest.approx(1999.5)


def test_btc_costs_fee_and_funding_sign():
    c = ro.Costs("btc")
    assert c.fill(100.0, 1, True) == pytest.approx(100.02)
    assert c.fees(1000, 1000) == pytest.approx(1.0)
    t = pd.Timestamp("2026-01-05 07:00", tz="UTC")  # holds through 08:00 and 16:00
    assert c.carry(1, t, t + pd.Timedelta(hours=10), 1000) == pytest.approx(0.2)
    assert c.carry(-1, t, t + pd.Timedelta(hours=10), 1000) == pytest.approx(-0.2)


def test_london_long_hits_target_and_sizes_by_risk():
    b = _hourly()
    b.loc[b.index[2], "high"], b.loc[b.index[4], "low"] = 102.0, 98.0  # Asian range 98-102
    b.loc[b.index[8], ["high", "close"]] = [103.0, 102.5]  # 08:00 breaks the high: long at 102, stop 98, target 106
    b.loc[b.index[10], "high"] = 106.5
    book = ro.london(b, ro.Costs("oro"))
    (t,) = book.trades
    assert t["side"] == 1 and t["why"] == "meta"
    qty = ro.RISK * ro.CAPITAL / 4.0
    assert book.cash == pytest.approx(ro.CAPITAL + qty * (105.75 - 102.25))


def test_london_both_sides_in_one_candle_counts_the_stop_and_exits_at_20():
    b = _hourly()
    b.loc[b.index[2], "high"], b.loc[b.index[4], "low"] = 102.0, 98.0
    b.loc[b.index[9], ["high", "low"]] = [102.5, 97.5]
    (t,) = ro.london(b, ro.Costs("oro")).trades
    assert t["why"] == "stop" and t["ret_pct"] < 0
    b2 = _hourly()
    b2.loc[b2.index[2], "high"], b2.loc[b2.index[4], "low"] = 102.0, 98.0
    b2.loc[b2.index[8], "low"] = 97.0  # short at 98, stop 102, target 94: never touched
    b2.loc[b2.index[20], "open"] = 99.0
    (t2,) = ro.london(b2, ro.Costs("oro")).trades
    assert t2["side"] == -1 and t2["why"] == "hora" and t2["exit"].endswith("20:00:00+00:00")


def test_london_needs_a_full_asian_range():
    b = _hourly().drop(_hourly().index[3])
    b.loc[b.index[8], "high"] = 150.0
    assert ro.london(b, ro.Costs("oro")).trades == []


def _daily(n=40, px=100.0):
    idx = pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC")
    shrink = 0.01 * np.arange(n)  # a narrowing range: no channel is touched unless a test sets one
    return pd.DataFrame({"open": px, "high": px + 1 - shrink, "low": px - 1 + shrink, "close": px}, index=idx)


def test_turtle_enters_on_20_day_high_and_exits_on_10_day_low():
    d = _daily()
    d.loc[d.index[25], ["high", "close"]] = [103.0, 102.0]  # breaks the 20-day high (about 100.95)
    d.loc[d.index[26:30], ["open", "high", "low", "close"]] = [105.0, 106.0, 104.0, 105.0]
    d.loc[d.index[30], ["open", "low"]] = [104.0, 98.0]  # touches the 10-day low: exits at min(level, open)
    book = ro.turtle(d, ro.Costs("btc"), 21)
    first = book.trades[0]
    assert first["side"] == 1 and first["why"] == "canal" and first["entry"].startswith("2026-01-26")


def test_turtle_stop_is_two_n():
    d = _daily()
    d.loc[d.index[25], "high"] = 103.0
    d.loc[d.index[26], ["open", "low"]] = [100.0, 90.0]  # 2N with N about 2 -> stop near 97: hit
    first = ro.turtle(d, ro.Costs("btc"), 21).trades[0]
    assert first["why"] == "stop"


def test_news_fades_a_big_event_candle_to_its_middle():
    b = _hourly(n_days=2)
    b["high"], b["low"] = 100.5, 99.5  # ATR about 1
    ev = pd.Timestamp("2026-01-06 13:30", tz="UTC")
    k = b.index.get_loc(ev.floor("h"))
    b.iloc[k, :] = [100.0, 106.0, 99.5, 105.5]  # range 6.5 >= 2 ATR, closed up: short next open
    b.iloc[k + 1, :] = [105.0, 105.2, 102.0, 102.5]  # middle 102.75 touched
    book = ro.news(b, ro.Costs("btc"), 20, [ev])
    (t,) = book.trades
    assert t["side"] == -1 and t["why"] == "meta"


def test_news_skips_small_candles_and_exits_after_eight():
    b = _hourly(n_days=2)
    b["high"], b["low"] = 100.5, 99.5
    ev = pd.Timestamp("2026-01-06 13:30", tz="UTC")
    k = b.index.get_loc(ev.floor("h"))
    b.iloc[k, :] = [100.0, 100.8, 99.6, 100.6]
    assert ro.news(b, ro.Costs("btc"), 20, [ev]).trades == []
    b.iloc[k, :] = [100.0, 106.0, 99.5, 105.5]
    b.iloc[k + 1:, b.columns.get_loc("open")] = 104.0
    b.iloc[k + 1:, b.columns.get_loc("high")] = 104.5
    b.iloc[k + 1:, b.columns.get_loc("low")] = 103.5
    (t,) = ro.news(b, ro.Costs("btc"), 20, [ev]).trades
    assert t["why"] == "hora" and pd.Timestamp(t["exit"]) - pd.Timestamp(t["entry"]) == pd.Timedelta(hours=8)


def test_passes_needs_profit_ratio_and_quarters():
    base = {"net_pct": 10.0, "net_dd": 1.2, "quarters": [1, 2, -1, 3]}
    assert ro.passes(base)
    assert not ro.passes({**base, "net_dd": 0.9})
    assert not ro.passes({**base, "quarters": [1, -2, -1, 3]})
    assert not ro.passes({**base, "net_pct": -1.0})


def test_stats_quarters_and_drawdown():
    book = ro.Book(ro.Costs("oro"))
    book.equity = list(np.array([1000, 900, 950, 1100, 1050, 1200, 1210, 1300], float))
    s = ro.stats(book)
    assert s["net_pct"] == pytest.approx(30.0) and s["max_dd_pct"] == pytest.approx(10.0)
    assert len(s["quarters"]) == 4
