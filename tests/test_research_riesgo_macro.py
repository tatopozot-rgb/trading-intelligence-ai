"""Tests for research_riesgo_macro (synthetic, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_riesgo_macro as rq
from trading_intelligence.live import desk as D


@pytest.fixture(autouse=True)
def _plain_rules(monkeypatch):
    monkeypatch.setattr(D.DeskRules, "load", classmethod(lambda cls, *a, **k: D.DeskRules()))


def test_above_is_known_only_after_the_lag():
    idx = pd.bdate_range("2025-01-01", periods=60)
    s = pd.Series(np.r_[np.full(55, 1.0), np.full(5, 2.0)], index=idx)
    up = rq.above(s, 2)
    assert up.index[0] == (idx[49] + pd.Timedelta(days=2)).tz_localize("UTC")
    assert not up.iloc[0] and up.iloc[-1]


def test_tight_needs_both_and_unknown_is_not_tight():
    t0 = pd.Timestamp("2025-03-01", tz="UTC")
    times = pd.date_range(t0, periods=4, freq="D").as_unit("ns").asi8
    bond = pd.Series([True, True], index=[t0 + pd.Timedelta(days=1), t0 + pd.Timedelta(days=2)])
    dollar = pd.Series([True, False], index=[t0 + pd.Timedelta(days=1), t0 + pd.Timedelta(days=3)])
    assert rq.tight_at(times, bond, dollar).tolist() == [False, True, True, False]


def test_risk_scale_halves_new_entries_only():
    n = 600
    close = np.full(n, 100.0)
    side = np.zeros(n, dtype=np.int8)
    side[10] = 1
    s = rm.Sym(np.arange(n, dtype=np.int64), close, close * 1.001, close * 0.999, close, side, np.full(n, 0.5),
               np.where(side != 0, 95.0, np.nan), np.zeros(n), np.full(n, np.nan), np.zeros(n, bool))
    fixed = rm.Sizing("fijo 2%", 0.02)
    full = rm.replay({"X": s}, 0, n, sizing=fixed, rules=D.DeskRules(), slippage=0.0, capital=1000.0)
    half = rm.replay({"X": s}, 0, n, sizing=fixed, rules=D.DeskRules(), slippage=0.0, capital=1000.0,
                     risk_scale=np.full(n, 0.5))
    up = rm.replay({"X": s}, 0, n, sizing=fixed, rules=D.DeskRules(), slippage=0.0, capital=1000.0,
                   risk_scale=np.full(n, 3.0))
    assert half.trades[0]["risk_usdt"] == pytest.approx(full.trades[0]["risk_usdt"] / 2, rel=1e-6)
    assert up.trades[0]["risk_usdt"] == pytest.approx(full.trades[0]["risk_usdt"], rel=1e-6)  # never raises


def test_rows():
    assert [k for k, v in rq.ROWS.items() if v[3] == "decisoria"] == ["m1x", "m3x"]
