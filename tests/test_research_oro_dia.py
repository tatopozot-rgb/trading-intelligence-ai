"""Tests for research_oro_dia (synthetic candles, no network)."""
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_oro as ro
from trading_intelligence.backtesting import research_oro_dia as od


def _bars(day="2026-01-05", n_days=1, px=2000.0):  # a Monday in winter: New York opens 14:30 UTC
    idx = pd.date_range(day, periods=96 * n_days, freq="15min", tz="UTC")
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px}, index=idx)


def test_new_york_open_follows_daylight_saving():
    assert od.ny_open(pd.Timestamp("2026-01-05", tz="UTC")) == pd.Timestamp("2026-01-05 14:30", tz="UTC")
    assert od.ny_open(pd.Timestamp("2026-07-06", tz="UTC")) == pd.Timestamp("2026-07-06 13:30", tz="UTC")


def test_orb30_long_breakout_stops_on_the_other_side_risking_one_percent():
    b = _bars()
    b.loc["2026-01-05 14:30", "high"] = 2010.0
    b.loc["2026-01-05 14:45", "low"] = 1990.0  # range 1990-2010
    b.loc["2026-01-05 15:00", ["high", "close"]] = [2012.0, 2011.0]  # breaks the high: long at 2010
    b.loc["2026-01-05 16:00", ["open", "low"]] = [2000.0, 1985.0]  # stop at 1990
    book = od.orb(b, ro.Costs("oro"), 30)
    (t,) = book.trades
    assert t["side"] == 1 and t["why"] == "stop"
    qty = min(ro.RISK * ro.CAPITAL / 20.0, ro.MAX_NOTIONAL * ro.CAPITAL / 2010.0)
    assert book.cash == pytest.approx(ro.CAPITAL + qty * ((1990 - 0.25) - (2010 + 0.25)))


def test_orb60_waits_for_the_full_hour_and_exits_at_20():
    b = _bars()
    b.loc["2026-01-05 14:30", "high"] = 2010.0
    b.loc["2026-01-05 15:15", "low"] = 1990.0
    b.loc["2026-01-05 15:00", "high"] = 2009.0  # inside the 60-minute range: no entry
    b.loc["2026-01-05 15:45", "low"] = 1989.0  # first break after 15:30: short at 1990
    b.loc["2026-01-05 20:00", "open"] = 1995.0
    (t,) = od.orb(b, ro.Costs("oro"), 60).trades
    assert t["side"] == -1 and t["why"] == "hora" and t["exit"].startswith("2026-01-05 20:00")


def test_no_entry_after_18_utc_or_without_a_full_range():
    b = _bars()
    b.loc["2026-01-05 14:30", "high"] = 2010.0
    b.loc["2026-01-05 14:45", "low"] = 1990.0
    b.loc["2026-01-05 18:15", "high"] = 2020.0
    assert od.orb(b, ro.Costs("oro"), 30).trades == []
    b2 = b.drop(pd.Timestamp("2026-01-05 14:45", tz="UTC"))
    b2.loc["2026-01-05 15:00", "high"] = 2020.0
    assert od.orb(b2, ro.Costs("oro"), 30).trades == []


def test_intraday_momentum_follows_the_morning_move_from_19_to_20():
    b = _bars(n_days=2)
    b.loc["2026-01-05 20:00", "close"] = 2000.0  # yesterday's reference
    b.loc["2026-01-06 14:45", "close"] = 2010.0  # 30 minutes after the open: up
    b.loc["2026-01-06 19:00", "open"] = 2005.0
    b.loc["2026-01-06 20:00", "open"] = 2015.0
    book = od.momentum(b, ro.Costs("oro"))
    (t,) = book.trades
    assert t["side"] == 1 and t["why"] == "hora"
    qty = ro.CAPITAL / 2005.25
    assert book.cash == pytest.approx(ro.CAPITAL + qty * (2014.75 - 2005.25))


def test_year_reports_dsr_and_daily_equity():
    b = _bars(n_days=10)
    b = b[b.index.dayofweek < 5]
    y = od.year(b, "2026-01-05", "2026-01-15", 257)
    assert set(y["rows"]) == {"orb30", "orb60", "impulso", "orb30, costes ×2", "orb60, costes ×2", "impulso, costes ×2"}
    assert all("dsr" in r and r["daily_equity"] for r in y["rows"].values())
    years = [{**y, "desk": od.DESK["2024-10-12"]}, {**y, "from": "2025-10-13", "desk": od.DESK["2025-10-13"]}]
    text = od.render(years, 257)
    assert "no pasa" in text and "muestra corta" in text
