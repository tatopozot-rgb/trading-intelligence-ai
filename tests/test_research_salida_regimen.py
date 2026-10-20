"""Tests for research_salida_regimen (synthetic, no network)."""
import numpy as np
import pytest

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_salida_regimen as rs
from trading_intelligence.live import desk as D


@pytest.fixture(autouse=True)
def _plain_rules(monkeypatch):
    monkeypatch.setattr(D.DeskRules, "load", classmethod(lambda cls, *a, **k: D.DeskRules()))


def _sym(n=600):
    close = np.full(n, 100.0)
    side = np.zeros(n, dtype=np.int8)
    side[10] = 1
    return rm.Sym(np.arange(n, dtype=np.int64), close, close * 1.001, close * 0.999, close, side, np.full(n, 0.5),
                  np.where(side != 0, 95.0, np.nan), np.zeros(n), np.full(n, np.nan), np.zeros(n, bool))


def test_regime_exit_closes_the_long_when_the_gate_turns():
    allow = np.full(600, rm.BOTH, dtype=np.int8)
    allow[200:] = 0
    with_exit = rs.run({"XUSDT": _sym()}, [(0, 600)], rm.SIZINGS[0], True, allow={"XUSDT": allow})
    without = rs.run({"XUSDT": _sym()}, [(0, 600)], rm.SIZINGS[0], False, allow={"XUSDT": allow})
    assert with_exit["trades"][0]["why"] == "régimen" and with_exit["trades"][0]["k1"] == 200
    assert without["trades"][0]["why"] == "fin del bloque"


def test_rows_and_summary_counts_regime_exits():
    assert [k for k, v in rs.ROWS.items() if v[3] == "decisoria"] == ["s1x", "s3x"]
    import pandas as pd
    times = pd.date_range("2026-01-01", periods=600, freq="5min", tz="UTC").as_unit("ns").asi8
    allow = np.full(600, rm.BOTH, dtype=np.int8)
    allow[200:] = 0
    out = rs.run({"XUSDT": _sym()}, [(0, 600)], rm.SIZINGS[0], True, allow={"XUSDT": allow})
    s = rs.summarize(out, times, 0, 288)
    assert s["regime_exits"] == 1 and s["stops"] == 0
