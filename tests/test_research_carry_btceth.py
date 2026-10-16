"""Tests for research_carry_btceth (synthetic data, no network)."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_carry as rc
from trading_intelligence.backtesting import research_carry_btceth as cb

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _raw(symbol, rate, days=20, perp=None):
    idx = pd.date_range(START, periods=days * 24 + 1, freq="h", tz="UTC")
    spot = pd.Series(100.0, index=idx, dtype=float)
    fut = spot.copy() if perp is None else pd.Series(perp, index=idx, dtype=float)
    ft = pd.date_range(START - pd.Timedelta(days=10), START + pd.Timedelta(days=days), freq="8h", tz="UTC")
    rates = rate if np.ndim(rate) else np.full(len(ft), rate)
    return symbol, (spot, fut, pd.Series(rates, index=ft + pd.Timedelta(milliseconds=3), dtype=float))


def _panel(*raws, days=20):
    return rc.build_panel(dict(raws), START, START + pd.Timedelta(days=days), (cb.LOOKBACK,))


def test_enters_only_when_funding_pays_its_costs_in_30_days():
    p = _panel(_raw("BTCUSDT", 0.005), _raw("ETHUSDT", 0.003))
    btc = rc.simulate(p, cb.rules()["regla, BTCUSDT"][0])
    eth = rc.simulate(p, cb.rules()["regla, ETHUSDT"][0])
    assert btc.trades and btc.curve[-1] > rc.CAPITAL - 5
    assert eth.trades == [] and eth.curve[-1] == rc.CAPITAL
    assert 0.38 / 90 == pytest.approx(cb.ENTER, abs=1e-4)


def test_liquidation_rise_and_the_31_usdt_check():
    assert cb.liquidation_rise(20.0, 11.0) == pytest.approx((0.55 - 0.005) / 1.005)
    perp = np.r_[np.full(200, 100.0), np.linspace(100, 170, 281)]
    p = _panel(_raw("ETHUSDT", 0.02, perp=perp), _raw("BTCUSDT", 0.02))
    run = rc.simulate(p, cb.rules()["regla, ETHUSDT"][0])
    mins = {"spot": {}, "perp": {}, "verified": {"spot": False, "perp": False}}
    eth = cb.small_account(p, run, "ETHUSDT", mins, 5.0)
    assert eth["cabe"] and eth["pata_usdt"] == 20.0 and eth["apalancamiento_corto"] == pytest.approx(1.82, abs=0.01)
    assert eth["peor_subida_pct"] > 0
    btc = cb.small_account(p, rc.simulate(p, cb.rules()["regla, BTCUSDT"][0]), "BTCUSDT", mins, 5.0)
    assert btc["cabe"] is False


def test_holdings_join_rebalances():
    run = rc.Run(np.zeros(1), np.zeros(1), np.zeros(1), np.zeros(1), np.zeros(1, dtype=np.int16),
                 [{"symbol": "ETHUSDT", "t0": 0, "t1": 5}, {"symbol": "ETHUSDT", "t0": 5, "t1": 9},
                  {"symbol": "ETHUSDT", "t0": 20, "t1": 30}, {"symbol": "BTCUSDT", "t0": 1, "t1": 2}])
    assert cb.holdings(run, "ETHUSDT") == [(0, 9), (20, 30)]


def test_evaluate_and_render_end_to_end(monkeypatch):
    monkeypatch.setattr(cb, "YEARS", (("2026-01-01", "2026-01-11"), ("2026-01-11", "2026-01-21")))
    monkeypatch.setattr(cb, "DESK", {"2026-01-01": 1.67, "2026-01-11": -0.21})
    p = _panel(_raw("BTCUSDT", 0.01), _raw("ETHUSDT", 0.01))
    mins = {"spot": {"BTCUSDT": 5.0}, "perp": {"BTCUSDT": 100.0, "ETHUSDT": 20.0},
            "verified": {"spot": True, "perp": True}}
    res = cb.evaluate(p, 254, mins)
    assert set(res["rows"]) == set(cb.rules()) and set(res["small"]) == {"BTCUSDT", "ETHUSDT"}
    assert res["rows"]["regla, BTCUSDT"]["daily_equity"]
    text = cb.render(res, {"desde": "2026-01-01", "hasta": "2026-01-21"})
    assert "no cabe" in text and "ETHUSDT" in text
