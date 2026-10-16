"""Tests for research_cartera_xm (synthetic candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_cartera_xm as cx


def _spec(name="EURUSD", contract=100_000.0, vmin=0.01, step=0.01, point=0.00001, spread=10.0, sl=0.0, ss=0.0,
          mode=1, triple=3, ccy="USD"):
    return cx.Spec(name, contract, vmin, step, point, spread, sl, ss, mode, triple, ccy)


def _frame(closes, start="2024-01-01", weekdays=True, spread=10):
    days = pd.date_range(start, periods=len(closes) * 2, freq="D", tz="UTC")
    if weekdays:
        days = days[days.dayofweek < 5]
    days = days[:len(closes)]
    c = np.asarray(closes, float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c), "low": np.minimum(o, c), "close": c,
                         "spread": spread}, index=days)


def _market(frames, specs):
    for name, f in frames.items():
        f["spread_px"] = f["spread"] * specs[name].point
    return cx.build(frames, specs)


def test_round_lots_uses_step_and_minimum():
    s = _spec()
    assert cx.round_lots(400.0, s) == 0.0  # 0.004 lots < half of 0.01
    assert cx.round_lots(600.0, s) == pytest.approx(1000.0)  # one minimum lot
    assert cx.round_lots(-2_340.0, s) == pytest.approx(-2000.0)


def test_forecast_is_long_in_an_uptrend_and_short_in_a_downtrend():
    up = 1.0 + 0.002 * np.arange(400)
    fc, vol = cx.forecasts(np.vstack([up + 0.001 * np.sin(np.arange(400)), up[::-1] + 0.001 * np.cos(np.arange(400))]))
    assert fc[0, -1] > 5 and fc[1, -1] < -5 and np.all(np.abs(fc[:, 300:]) <= cx.CAP)
    assert np.isnan(fc[0, 20])  # no pair is ready before 32 days


def test_swap_modes_points_money_and_percent():
    s = _spec(sl=-5.0, ss=2.0)
    assert cx.swap_cost(1000.0, s, 1.1, 1.0, 1, 1.0) == pytest.approx(5 * 0.00001 * 100_000 * 0.01)
    assert cx.swap_cost(-1000.0, s, 1.1, 1.0, 3, 1.0) == pytest.approx(-2 * 0.00001 * 100_000 * 0.01 * 3)
    money = _spec(sl=-10.0, mode=4)
    assert cx.swap_cost(2000.0, money, 1.1, 1.0, 1, 2.0) == pytest.approx(10 * 0.02 * 2)
    pct = _spec(sl=-18.0, mode=5, contract=1.0)
    assert cx.swap_cost(1.0, pct, 50_000.0, 1.0, 1, 1.0) == pytest.approx(0.18 / 360 * 50_000)


def test_triple_swap_on_the_rollover_day_only_for_weekday_markets():
    s = _spec(triple=3)  # Wednesday night
    wed = pd.Timestamp("2026-10-14", tz="UTC")  # a Wednesday: its night is the triple one
    assert cx.nights_held(wed, s, False) == 3
    assert cx.nights_held(wed + pd.Timedelta(days=1), s, False) == 1
    assert cx.nights_held(wed, s, True) == 1


def test_simulation_profits_from_a_trend_and_pays_spread_and_swap():
    n = 700
    trend = list(1.0 + 0.003 * np.arange(n) + 0.004 * np.sin(np.arange(n) / 3))
    specs = {"EURUSD": _spec(sl=-3.0)}
    m = _market({"EURUSD": _frame(trend)}, specs)
    r = cx.simulate(m, [specs["EURUSD"]], 400, n, capital=100_000.0)
    assert r.equity[-1] > 100_000.0 and r.entries >= 1
    assert r.spread_paid > 0 and r.swap_paid > 0
    s = cx.summarize(r, 100_000.0, 258)
    assert len(s["daily_equity"]) == n - 400 and 0 <= s["dsr"] <= 1


def test_small_account_cannot_hold_a_lot_that_is_too_big():
    n = 700
    trend = list(1.0 + 0.003 * np.arange(n) + 0.004 * np.sin(np.arange(n) / 3))
    specs = {"EURUSD": _spec()}
    m = _market({"EURUSD": _frame(trend)}, specs)
    r = cx.simulate(m, [specs["EURUSD"]], 400, n, capital=200.0)
    assert r.entries == 0 and r.equity[-1] == pytest.approx(200.0)
    (row,) = cx.lot_check([specs["EURUSD"]], m, n - 1, 200.0)
    assert not row["fits"] and row["min_lot_usd"] > 2 * 200.0


def test_profit_currency_is_converted_with_the_fx_pair():
    specs = {"USDJPY": _spec("USDJPY", point=0.001, ccy="JPY"), "JP225": _spec("JP225", contract=1.0, point=1.0,
                                                                                ccy="JPY")}
    frames = {"USDJPY": _frame([150.0] * 10), "JP225": _frame([40_000.0] * 10)}
    m = _market(frames, specs)
    i = m.names.index("JP225")
    assert m.usd[i, 0] == pytest.approx(1 / 150.0)


def test_render_says_no_pass_when_it_loses():
    row = {"net_pct": -5.0, "max_dd_pct": 10.0, "net_dd": -0.5, "orders": 3, "entries": 2, "spread_pct": 0.1,
           "swap_pct": 0.1, "sharpe_anual": -0.3, "dsr": 0.0, "quarters": [0, 0, 0, 0], "traded_markets": ["A"],
           "per_market_pct": {"A": -5.0}}
    years = [{"label": "y", "desk": 1.67, "rows": {k: row for k in cx.ROWS}},
             {"label": "z", "desk": -0.21, "rows": {k: row for k in cx.ROWS}}]
    md = cx.render(years, [{"market": "A", "min_lot_usd": 1000.0, "target_usd": 50.0, "ratio": 20.0, "fits": False}], 258)
    assert "**No pasa.**" in md and "caben 0 de 1" in md
