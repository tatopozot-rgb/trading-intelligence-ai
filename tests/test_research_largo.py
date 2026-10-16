"""Tests for research_largo (synthetic candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_largo as rl


def _asset(name, closes, start="2024-01-01", weekdays=False, funding=0.0):
    idx = pd.date_range(start, periods=len(closes), freq="D", tz="UTC")
    c = pd.Series(closes, index=idx, dtype=float)
    if weekdays:
        c = c[c.index.dayofweek < 5]
    o = c.shift(1).fillna(c.iloc[0])
    return rl.Asset(name, o, c, pd.Series(funding, index=c.index))


def test_month_end_signals_use_only_closed_months():
    a = _asset("btc", np.r_[np.full(320, 100.0), np.linspace(100, 200, 100)])
    f = rl.faber(a.close)
    assert f.index[0] == pd.Timestamp("2024-01-31", tz="UTC")
    assert f.iloc[:10].sum() == 0 and f.iloc[-1] == 1
    m = rl.momentum(a.close)
    assert (m.iloc[:12] == 0).all() and m.iloc[-1] == 1
    days = a.close.index
    want = rl.targets_by_day(f, days, lambda x: ("btc", int(x)) if x else ("", 0))
    k = days.get_loc(pd.Timestamp("2024-12-31", tz="UTC"))
    assert want[k] == (("btc", 1) if f.loc[pd.Timestamp("2024-11-30", tz="UTC")] else ("", 0))  # still November


def test_momentum_goes_short_after_a_fall():
    a = _asset("btc", np.r_[np.full(380, 200.0), np.linspace(200, 100, 60)])
    assert rl.momentum(a.close).iloc[-1] == -1


def test_dual_picks_the_better_positive_asset_or_cash():
    n = 450
    btc = _asset("btc", np.linspace(100, 300, n))
    gold = _asset("oro", np.linspace(100, 120, n), weekdays=True)
    assert rl.dual(btc.close, gold.close).iloc[-1] == "btc"
    btc2 = _asset("btc", np.linspace(300, 100, n))
    assert rl.dual(btc2.close, gold.close).iloc[-1] == "oro"
    gold2 = _asset("oro", np.linspace(120, 100, n), weekdays=True)
    assert rl.dual(btc2.close, gold2.close).iloc[-1] == ""


def test_gold_long_pays_spread_and_swap_with_wednesday_triple():
    g = _asset("oro", np.full(14, 2000.0), start="2026-01-05", weekdays=True)  # Monday
    days = g.close.index
    want = [("oro", 1)] * len(days)
    book = rl.simulate({"oro": g}, days, want)
    qty = rl.CAPITAL / (2000 + 0.25)
    nights = (len(days) - 1) + 2 * sum(1 for d in days[:-1] if d.dayofweek == 2)
    expected = rl.CAPITAL + qty * ((2000 - 0.25) - (2000 + 0.25)) + qty * rl.GOLD_SWAP_LONG * nights
    assert book.cash == pytest.approx(expected)
    assert len(book.trades) == 1 and book.trades[0]["why"] == "fin"


def test_btc_short_receives_positive_funding_and_pays_fees():
    b = _asset("btc", np.full(5, 100.0), funding=0.03)
    days = b.close.index
    book = rl.simulate({"btc": b}, days, [("btc", -1)] * 5)
    fill_in, fill_out = 100 * (1 - rl.BTC_SLIP), 100 * (1 + rl.BTC_SLIP)
    qty = rl.CAPITAL / fill_in
    fees = rl.BTC_FEE * qty * fill_in + rl.BTC_FEE * qty * fill_out
    funding = 4 * 0.0003 * qty * 100
    assert book.cash == pytest.approx(rl.CAPITAL - qty * (fill_out - fill_in) - fees + funding)


def test_switch_waits_for_a_gold_candle_on_weekends():
    btc = _asset("btc", np.full(10, 100.0), start="2026-01-02")  # Friday
    gold = _asset("oro", np.full(10, 2000.0), start="2026-01-02", weekdays=True)
    days = btc.close.index
    want = [("btc", 1)] + [("oro", 1)] * 9  # switch asked on Saturday
    book = rl.simulate({"btc": btc, "oro": gold}, days, want)
    assert book.trades[0]["asset"] == "btc" and book.trades[0]["exit"] == "2026-01-03"
    assert book.trades[1]["asset"] == "oro" and book.trades[1]["entry"] == "2026-01-05"  # Monday


def test_stats_keep_daily_equity_and_costs_double():
    g = _asset("oro", np.linspace(2000, 2100, 30), start="2026-01-05", weekdays=True)
    days = g.close.index
    want = [("oro", 1)] * len(days)
    s1 = rl.stats(rl.simulate({"oro": g}, days, want), days)
    s2 = rl.stats(rl.simulate({"oro": g}, days, want, 2.0), days)
    assert len(s1["daily_equity"]) == len(days) and s2["net_pct"] < s1["net_pct"]
