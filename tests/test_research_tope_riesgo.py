"""Tests for research_tope_riesgo and the open-risk cap in research_mesa.replay (synthetic, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_tope_riesgo as rt
from trading_intelligence.live import desk as D


@pytest.fixture(autouse=True)
def _plain_rules(monkeypatch):
    monkeypatch.setattr(D.DeskRules, "load", classmethod(lambda cls, *a, **k: D.DeskRules()))


def _sym(sides, n=200):
    close = np.full(n, 100.0)
    side = np.zeros(n, dtype=np.int8)
    for k, v in sides:
        side[k] = v
    stop = np.where(side > 0, 95.0, np.where(side < 0, 105.0, np.nan))
    return rm.Sym(np.arange(n, dtype=np.int64), close, close, close, close, side, np.full(n, 0.5), stop,
                  np.zeros(n), np.full(n, np.nan), np.zeros(n, bool))


def _replay(syms, cap):
    return rm.replay(syms, 0, 200, rules=D.DeskRules(), slippage=0.0, capital=1000.0,
                     sizing=rm.Sizing("f", 0.05), open_risk_cap=cap)


def test_cap_blocks_a_second_entry_on_the_same_side_only():
    # The first long risks 2.5% (5 units capped by the 50% position limit, 5 USDT each): over the 2% cap.
    syms = {"A": _sym([(10, 1)]), "B": _sym([(20, 1), (21, 1), (22, 1)]), "C": _sym([(30, -1)])}
    free = _replay(syms, None)
    capped = _replay(syms, 0.02)
    assert {t["symbol"] for t in free.trades} == {"A", "B", "C"}
    assert {t["symbol"] for t in capped.trades} == {"A", "C"}
    assert capped.capped == 1 and free.capped == 0


def test_cap_lets_a_small_first_position_through():
    syms = {"A": _sym([(10, 1)]), "B": _sym([(20, 1)])}
    out = rm.replay(syms, 0, 200, rules=D.DeskRules(), slippage=0.0, capital=1000.0, sizing=rm.Sizing("f", 0.01),
                    open_risk_cap=0.02)
    assert {t["symbol"] for t in out.trades} == {"A", "B"} and out.capped == 0


def test_rows_and_summary_count_the_capped_signals():
    assert [k for k, v in rt.ROWS.items() if v[3] == "decisoria"] == ["t1x"] and rt.ROWS["t1x"][2] == 0.02
    times = pd.date_range("2026-01-01", periods=200, freq="5min", tz="UTC").as_unit("ns").asi8
    syms = {"A": _sym([(10, 1)]), "B": _sym([(20, 1)])}
    out = rt.run(syms, [(0, 200)], rm.Sizing("f", 0.05), 0.02)
    s = rt.summarize(out, times, 0, 301)
    assert s["capped"] == 1 and s["trades"] == 1 and s["exits"] == {"fin del bloque": 1}
