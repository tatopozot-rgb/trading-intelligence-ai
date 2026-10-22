"""Tests for research_trailing_real and the exit switches in research_mesa.replay (synthetic, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_trailing_real as rt
from trading_intelligence.live import desk as D


@pytest.fixture(autouse=True)
def _plain_rules(monkeypatch):
    monkeypatch.setattr(D.DeskRules, "load", classmethod(lambda cls, *a, **k: D.DeskRules()))


def _sym(path, sides):
    n = len(path)
    close = np.array(path, float)
    side = np.zeros(n, dtype=np.int8)
    for k, v in sides:
        side[k] = v
    stop = np.where(side > 0, close * 0.95, np.where(side < 0, close * 1.05, np.nan))
    return rm.Sym(np.arange(n, dtype=np.int64), close, close, close, close, side, np.full(n, 0.5), stop,
                  np.zeros(n), np.full(n, np.nan), np.zeros(n, bool))


def _replay(s, exits):
    return rm.replay({"X": s}, 0, len(s.close), exits=exits, rules=D.DeskRules(), slippage=0.0, capital=1000.0,
                     sizing=rm.Sizing("f", 0.02))


def test_opposite_signal_closes_only_when_allowed():
    s = _sym(np.full(100, 100.0), [(10, 1), (20, -1)])
    assert _replay(s, rm.BASELINE).trades[0]["why"] == "señal contraria"
    kept = _replay(s, rt.TESTED).trades[0]
    assert kept["why"] == "fin del bloque" and kept["k1"] == 99


def test_trailing_starts_at_2r_not_1r():
    # R = 5: up 1.5R then back to the entry. From 1R the stop trails at +1R - 0.5R; from 2R it never starts.
    path = np.r_[np.full(11, 100.0), np.linspace(100, 107.5, 10), np.linspace(107.5, 100, 10), np.full(20, 100.0)]
    s = _sym(path, [(10, 1)])
    base = _replay(s, rm.BASELINE).trades[0]
    late = _replay(s, rt.TESTED).trades[0]
    assert base["why"] == "stop" and base["pnl"] > 0
    assert late["why"] == "fin del bloque"


def test_rows_and_run_end_to_end():
    assert [k for k, v in rt.ROWS.items() if v[2] == "decisoria"] == ["t2r"]
    assert rt.TESTED.trail_start == 2.0 and rt.TESTED.trail_dist == rm.BASELINE.trail_dist
    assert rt.TESTED.target_r == rm.BASELINE.target_r and not rt.TESTED.close_on_signal
    s = _sym(np.full(600, 100.0), [(10, 1), (20, -1)])
    out = rt.run({"XUSDT": s}, [(0, 300), (300, 600)], rt.TESTED)
    times = pd.date_range("2026-01-01", periods=600, freq="5min", tz="UTC").as_unit("ns").asi8
    summary = rt.summarize(out, times, 0, 297)
    assert summary["exits"] == {"fin del bloque": 1}
