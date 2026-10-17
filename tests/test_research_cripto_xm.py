"""Tests for research_cripto_xm (synthetic candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_cripto_xm as cx
from trading_intelligence.backtesting import research_oro as ro


def test_lots_round_to_xm_step():
    assert cx.lots(0.004) == 0.0
    assert cx.lots(0.006) == pytest.approx(0.01)
    assert cx.lots(0.0249) == pytest.approx(0.02)


def test_xm_costs_are_half_the_fixed_spread_per_side_and_no_fees():
    c = cx.XmCosts("btc")
    assert c.fill(80_000.0, 1, True) == pytest.approx(80_020.0)
    assert c.fill(80_000.0, 1, False) == pytest.approx(79_980.0)
    assert c.fill(80_000.0, -1, True) == pytest.approx(79_980.0)
    assert c.fees(1e6, 1e6) == 0.0
    assert cx.XmCosts("btc", 2.0).fill(80_000.0, 1, True) == pytest.approx(80_040.0)


def _day(break_up=True, base=80_000.0, day="2026-01-05"):
    idx = pd.date_range(day, periods=24, freq="h", tz="UTC")
    o = np.full(24, base)
    h, lo, c = o + 100, o - 100, o.copy()  # Asia range 79,900-80,100
    lo[7:] = base  # above the stop after Asia
    if break_up:
        h[8], c[8] = base + 300, base + 250  # breaks the high at 08:00
        h[10], c[10] = base + 600, base + 500  # reaches 1 range (200) above the entry: target
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)


def test_breakout_trade_with_xm_lots_and_costs():
    bars = _day()
    book = cx.run(bars, 1.0, 1000.0)
    (t,) = book.trades
    assert t["side"] == 1 and t["why"] == "meta"
    qty = cx.lots(min(ro.RISK * 1000 / 200, ro.MAX_NOTIONAL * 1000 / 80_100))  # risk 10 USD over a 200 USD range
    pnl = qty * ((80_300 - 20) - (80_100 + 20))
    assert book.cash == pytest.approx(1000 + pnl)


def test_200_usd_is_below_half_a_minimum_lot_on_a_wide_range():
    bars = _day()
    asia = bars.index.hour < 7
    bars.loc[asia, "high"] += 400
    bars.loc[asia, "low"] -= 400  # range 1,000 USD: 1% of 200 USD buys 0.002 BTC
    bars.iloc[8, bars.columns.get_loc("high")] = 81_000.0
    book = cx.run(bars, 1.0, 200.0)
    assert book.trades == [] and book.skipped >= 1


def test_render_and_summary():
    idx = _day().index
    book = cx.run(_day(), 1.0, 1000.0)
    s = cx.summarize(book, idx, 1000.0, 259)
    assert s["trades"] == 1 and "daily_equity" in s
    y = {"from": "a", "to": "b", "desk": 1.67, "rows": {k: s for k in cx.ROWS}}
    md = cx.render([y, {**y, "desk": -0.21}], 259)
    assert "Ruptura de Londres en BTC" in md and "N = 259" in md
