"""Tests for research_carry (synthetic data, no network)."""
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_carry as rc

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _raw(days=10, price=None, perp=None, rate=0.01, every_h=8, symbol="SOLUSDT"):
    idx = pd.date_range(START, periods=days * 24 + 1, freq="h", tz="UTC")
    spot = pd.Series(100.0 if price is None else price, index=idx, dtype=float)
    fut = spot.copy() if perp is None else pd.Series(perp, index=idx, dtype=float)
    ft = pd.date_range(START - pd.Timedelta(days=2), START + pd.Timedelta(days=days), freq=f"{every_h}h", tz="UTC")
    fund = pd.Series(rate, index=ft + pd.Timedelta(milliseconds=3), dtype=float)  # calc_time is a few ms late
    return {symbol: (spot, fut, fund)}


def _panel(raw, days=10):
    return rc.build_panel(raw, START, START + pd.Timedelta(days=days), (3, 9, 21))


def test_parse_klines_skips_header_and_reads_micro_and_milliseconds():
    rows = [["open_time", "open", "high", "low", "close"],
            ["1767225600000", "1", "1", "1", "10.5"],
            ["1767229200000000", "1", "1", "1", "11.0"]]  # µs
    s = rc.parse_klines(rows)
    assert list(s.values) == [10.5, 11.0]
    assert s.index[0] == pd.Timestamp("2026-01-01 01:00", tz="UTC")  # indexed by the bar's close time


def test_panel_rates_land_on_the_hour_and_are_normalised_to_8h():
    p = _panel(_raw(rate=0.01, every_h=4))
    t = int(np.where(p.times == pd.Timestamp("2026-01-02 04:00", tz="UTC").value)[0][0])
    assert p.rate[0, t] == pytest.approx(0.01) and p.rate[0, t + 1] == 0
    assert p.norm[3][0, t] == pytest.approx(0.02)  # 0.01% every 4 h = 0.02% per 8 h


def test_flat_prices_earn_the_funding_minus_costs():
    p = _panel(_raw(rate=0.01))
    run = rc.simulate(p, rc.Rule(3, 0.005, k=1))
    (tr,) = run.trades
    q = 1000 / 2 / 100
    payments = int((p.rate[0] != 0)[int(np.argmax(run.invested > 0)) + 1:].sum())
    cost = 2 * q * 100 * (rc.SPOT_COST + rc.PERP_COST)
    assert tr["funding"] == pytest.approx(q * 100 * 0.0001 * payments)
    assert run.curve[-1] == pytest.approx(1000 + tr["funding"] - cost)


def test_price_moves_cancel_between_the_legs():
    path = 100 * np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, 241))
    flat = rc.simulate(_panel(_raw(rate=0.01)), rc.Rule(3, 0.005, k=1))
    moving = rc.simulate(_panel(_raw(price=path, rate=0.01)), rc.Rule(3, 0.005, k=1))
    assert abs(moving.basis.sum()) < 1e-9
    assert moving.curve[-1] == pytest.approx(flat.curve[-1], rel=0.01)  # funding is paid on the moving notional


def test_exit_when_funding_turns_negative_and_rebalance_when_the_short_bleeds():
    raw = _raw(rate=0.01)
    s, f, fund = raw["SOLUSDT"]
    fund[fund.index > pd.Timestamp("2026-01-05", tz="UTC")] = -0.01
    run = rc.simulate(_panel({"SOLUSDT": (s, f, fund)}), rc.Rule(3, 0.005, k=1))
    assert run.trades[0]["why"] == "financiación baja"
    path = np.r_[np.full(48, 100.0), np.linspace(100, 300, 193)]
    run = rc.simulate(_panel(_raw(price=path, rate=0.01)), rc.Rule(3, 0.005, k=1))
    assert run.rebalances >= 1 and any(t["why"] == "rebalanceo" for t in run.trades)


def test_always_in_and_btc_only_baselines():
    raw = {**_raw(symbol="BTCUSDT"), **_raw(symbol="ETHUSDT", rate=-0.01)}
    p = _panel(raw)
    every = rc.simulate(p, rc.Rule(0, -math.inf, -math.inf))
    assert {t["symbol"] for t in every.trades} == {"BTCUSDT", "ETHUSDT"}
    btc = rc.simulate(p, rc.Rule(0, -math.inf, -math.inf, only="BTCUSDT"))
    assert {t["symbol"] for t in btc.trades} == {"BTCUSDT"}
    picky = rc.simulate(p, rc.Rule(3, 0.005, k=4))
    assert {t["symbol"] for t in picky.trades} == {"BTCUSDT"}  # ETH pays the shorts: never entered


def test_experiments_and_render_end_to_end():
    raw = {**_raw(days=130, symbol="BTCUSDT"), **_raw(days=130, symbol="ETHUSDT", rate=0.02)}
    p = rc.build_panel(raw, START, START + pd.Timedelta(days=130), (3, 9, 21))
    res = rc.experiments(p, 1)
    assert res["walk_forward"]["blocks"] and res["quarters"]
    md = rc.render(res, {"desde": "a", "hasta": "b", "simbolos": p.names})
    assert "Carry de financiación" in md and "Walk-forward" in md and ("**Pasa:**" in md or "**No pasa:**" in md)
