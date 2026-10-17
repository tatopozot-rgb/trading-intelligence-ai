"""Tests for research_grid (synthetic candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_grid as rg


def _frame(prices, start="2026-01-05", spread=0.0):
    """1h candles that open at the previous close and move straight to the next price."""
    idx = pd.date_range(start, periods=len(prices) - 1, freq="h", tz="UTC")
    o, c = np.array(prices[:-1], float), np.array(prices[1:], float)
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c}, index=idx)


def test_levels_are_geometric_and_span_the_range():
    lv = rg.levels(100.0, 0.10)
    assert len(lv) == 21
    assert lv[0] == pytest.approx(90.0) and lv[-1] == pytest.approx(110.0)
    assert np.allclose(lv[1:] / lv[:-1], (110 / 90) ** (1 / 20))


def test_touching_a_level_does_not_fill_crossing_does():
    lv = rg.levels(100.0, 0.10)
    below = lv[10]  # highest level under 100 (the geometric middle is 99.5)
    books, _ = rg.run({"btc": _frame([100.0, below, 100.0])}, {"btc": 1.0}, 0.10, rg.GridCosts(0, 0, 0))
    assert books["btc"].buys == 0
    books, _ = rg.run({"btc": _frame([100.0, below - 0.01, 100.0])}, {"btc": 1.0}, 0.10, rg.GridCosts(0, 0, 0))
    assert books["btc"].buys == 1


def test_one_round_trip_earns_one_step_minus_fees():
    lv = rg.levels(100.0, 0.10)
    path = [100.0, lv[10] - 0.01, lv[11] + 0.01, lv[11] + 0.01]
    costs = rg.GridCosts(fee=0.001)
    books, eq = rg.run({"btc": _frame(path)}, {"btc": 1.0}, 0.10, costs, capital=1000.0)
    b = books["btc"]
    assert b.trips == 1
    budget = 1000.0 / 20
    qty = budget / (lv[10] * 1.001)
    expect = qty * lv[11] * 0.999 - budget
    assert b.round_trip == pytest.approx(expect)
    assert b.inventory == pytest.approx(0.0)
    assert eq.iloc[-1] == pytest.approx(1000.0 + expect)


def test_no_buy_and_sell_of_the_same_step_in_one_candle():
    lv = rg.levels(100.0, 0.10)
    f = pd.DataFrame({"open": [100.0], "high": [lv[11] + 1], "low": [lv[10] - 1], "close": [100.0]},
                     index=pd.date_range("2026-01-05", periods=1, freq="h", tz="UTC"))
    books, _ = rg.run({"btc": f}, {"btc": 1.0}, 0.10, rg.GridCosts(0, 0, 0))
    assert books["btc"].buys >= 1 and books["btc"].trips == 0


def test_fall_leaves_inventory_closed_at_a_loss_on_monday():
    # falls 15% on a Sunday, the grid closes at Monday's open
    prices = list(np.linspace(100.0, 85.0, 24)) + [85.0, 85.0]
    f = _frame(prices, start="2026-01-11 01:00")  # Sunday
    books, eq = rg.run({"btc": f}, {"btc": 1.0}, 0.10, rg.BASE, capital=1000.0)
    b = books["btc"]
    assert b.buys == 11 and b.trips == 0  # every level from 99.5 down to 90, nothing below the range
    assert b.inventory < 0
    assert eq.iloc[-1] == pytest.approx(1000.0 + b.inventory + b.round_trip)


def test_new_grid_each_monday_and_halves_rebalance():
    idx = pd.date_range("2026-01-04", periods=48, freq="h", tz="UTC")  # Sunday and Monday
    flat = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}, index=idx)
    up = flat * 2.0
    books, eq = rg.run({"btc": flat, "eth": up}, {"btc": 0.5, "eth": 0.5}, 0.10, rg.BASE, capital=1000.0)
    assert books["btc"].lv[10] == pytest.approx(100.0 * 0.99 ** 0.5) and books["eth"].lv[10] == pytest.approx(200.0 * 0.99 ** 0.5)
    assert eq.iloc[-1] == pytest.approx(1000.0)
    assert books["btc"].budget == pytest.approx(500.0 / 20)


def test_maker_case_costs_less_than_base():
    lv = rg.levels(100.0, 0.10)
    path = [100.0, lv[10] - 0.01, lv[11] + 0.01, lv[11] + 0.01]
    base, _ = rg.run({"btc": _frame(path)}, {"btc": 1.0}, 0.10, rg.BASE)
    maker, _ = rg.run({"btc": _frame(path)}, {"btc": 1.0}, 0.10, rg.MAKER)
    assert maker["btc"].round_trip > base["btc"].round_trip


def test_summary_and_hold():
    lv = rg.levels(100.0, 0.10)
    path = [100.0] + [lv[10] - 0.01, lv[11] + 0.01] * 60 + [100.0]
    f = _frame(path)
    books, eq = rg.run({"btc": f}, {"btc": 1.0}, 0.10, rg.BASE)
    s = rg.summarize(books, eq, 1000.0, 266)
    assert s["trips"] > 0 and s["round_trip_usd"] > 0
    assert s["net_pct"] == pytest.approx(eq.iloc[-1] / 10 - 100, abs=0.01)
    assert set(rg.hold(f)) == {"net_pct", "max_dd_pct", "net_dd"}
