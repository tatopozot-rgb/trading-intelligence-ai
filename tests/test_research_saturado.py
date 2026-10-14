"""Tests for research_saturado (synthetic data, no network)."""
import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_saturado as rsat
from trading_intelligence.live import desk as D


def _times(n):
    return pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC").as_unit("ns").asi8


def test_long_filter_needs_open_interest_up_with_price_flat():
    n = 288 * 4
    t = _times(n)
    close = np.full(n, 100.0)
    oi = np.full(n, 1000.0)
    oi[2 * 288:] = 1120.0  # +12% in a day, price flat
    m = rsat.crowded_masks(close, oi, t)
    k = 2 * 288 + 10
    assert m["L5"][k] == rm.SHORT and m["L10"][k] == rm.SHORT and m["L15"][k] == rm.BOTH
    assert m["L10"][100] == rm.BOTH  # unknown 24 h ago: no filter
    moving = close.copy()
    moving[2 * 288:] = 110.0  # the same OI rise with price +10%: not crowded
    assert rsat.crowded_masks(moving, oi, t)["L5"][k] == rm.BOTH


def test_short_filter_after_a_long_cascade():
    n = 288 * 4
    t = _times(n)
    close = np.full(n, 100.0)
    oi = np.full(n, 1000.0)
    close[2 * 288:] = 95.0
    oi[2 * 288:] = 900.0  # OI -10% and price -5%: long cascade
    m = rsat.crowded_masks(close, oi, t)
    k = 2 * 288
    assert m["S12"][k] == rm.LONG and m["S24"][k] == rm.LONG
    last = 3 * 288 - 1  # the cascade reads true until 24 h after the drop
    assert m["S12"][last + 12 * 12 + 1] == rm.BOTH and m["S24"][last + 12 * 12 + 1] == rm.LONG


def test_entry_mask_blocks_entries_but_keeps_open_positions():
    n = 600
    close = np.full(n, 100.0)
    side = np.zeros(n, dtype=np.int8)
    side[10] = 1
    s = rm.Sym(np.arange(n, dtype=np.int64), close, close * 1.001, close * 0.999, close, side, np.full(n, 0.5),
               np.where(side != 0, 95.0, np.nan), np.zeros(n), np.full(n, np.nan), np.zeros(n, bool))
    shut = {"X": np.full(n, rm.SHORT, dtype=np.int8)}
    assert rm.replay({"X": s}, 0, n, rules=D.DeskRules(), slippage=0.0, entry_allow=shut).trades == []
    late = np.full(n, rm.BOTH, dtype=np.int8)
    late[50:] = rm.SHORT
    rep = rm.replay({"X": s}, 0, n, rules=D.DeskRules(), slippage=0.0, entry_allow={"X": late})
    assert rep.trades[0]["why"] != "régimen" and rep.trades[0]["k1"] == n - 1


def test_evaluate_and_render(monkeypatch):
    from tests.test_research_mesa import _prepared

    times, rsat.SYMS = rm.align({s: rm.arrays(p, D.DeskRules.load()) for s, p in _prepared(1600).items()})
    monkeypatch.setattr(rm, "BLOCK_BARS", 400)
    every = {name: np.full(len(times), rm.BOTH, dtype=np.int8) for name in rsat.SYMS}
    rsat.REGIME = {name: np.full(len(times), rm.LONG, dtype=np.int8) for name in rsat.SYMS}
    for s in rsat.SETUPS:
        for f in rsat.FILTERS:
            rsat.ENTRY[(s, f)] = every
    table = rsat.evaluate(times, 1)
    assert table["frenos"]["base"]["short_n"] == 0  # regime b: longs only
    assert table["eventos"]["base"]["trades"] >= table["frenos"]["base"]["trades"]
    years = [{"label": "y1", "table": table}, {"label": "y2", "table": table}]
    md = rsat.render(years)
    assert "lado saturado" in md and "**L10**" in md and "no ayuda" in md  # identical masks cannot help
