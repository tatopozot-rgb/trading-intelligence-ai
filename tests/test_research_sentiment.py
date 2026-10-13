"""Tests for research_sentiment (synthetic data, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_sentiment as rs
from trading_intelligence.live import desk as D


def _sym(n=1200, sides=(), mood=0.0, path=None):
    close = np.linspace(100, 112, n) if path is None else path
    side = np.zeros(n, dtype=np.int8)
    for k, s in sides:
        side[k] = s
    return rm.Sym(np.arange(n, dtype=np.int64), close.copy(), close, close, close.copy(), side, np.full(n, 0.5),
                  np.where(side != 0, close * 0.98, np.nan), np.full(n, mood), np.full(n, np.nan), np.zeros(n, bool))


def test_setups_once_per_run_and_per_24h_with_lean_and_side_signed_return():
    s = _sym(sides=[(10, 1), (11, 1), (100, -1), (400, 1)], mood=-0.6)
    rows = rs.setups({"X": s}, 0, 1200)
    assert [(r["k"], r["side"]) for r in rows] == [(10, 1), (400, 1)]  # the run at 11 and the short within 24 h skipped
    r = rows[0]
    assert r["lean"] == pytest.approx(-0.6)  # bearish mood against a long
    assert r["ret"] == pytest.approx((s.close[10 + rs.AHEAD] / s.close[10] - 1) * 100)
    short = rs.setups({"X": _sym(sides=[(10, -1)], mood=-0.6)}, 0, 1200)[0]
    assert short["lean"] == pytest.approx(0.6) and short["ret"] < 0  # price rises: the short loses


def test_describe_buckets_and_spearman():
    rng = np.random.default_rng(0)
    lean = rng.uniform(-1, 1, 400)
    rows = [{"lean": x, "ret": x * 2 + rng.normal(0, 0.5)} for x in lean]
    d = rs.describe(rows)
    assert d["n"] == 400 and sum(b["n"] for b in d["buckets"]) == 400
    assert d["spearman"] > 0.5 and d["p_value"] < 0.001 and rs.predictive(d)
    assert d["buckets"][0]["mean_pct"] < 0 < d["buckets"][-1]["mean_pct"]
    noise = rs.describe([{"lean": x, "ret": rng.normal()} for x in lean])
    assert not rs.predictive(noise)


def test_funding_rows_use_the_last_rate_and_the_next_day():
    idx = pd.date_range("2026-01-01 01:00", periods=24 * 5, freq="h", tz="UTC")
    spot = pd.Series(np.linspace(100, 110, len(idx)), index=idx)
    fund = pd.Series([0.05, -0.05], index=pd.DatetimeIndex(["2026-01-01 16:00", "2026-01-02 16:00"], tz="UTC"))
    rows = rs.funding_rows("X", spot, fund)
    assert [r["day"] for r in rows] == ["2026-01-02", "2026-01-03"]
    assert rows[0]["rate"] == 0.05 and rows[0]["lean"] == pytest.approx(D.sentiment(0.05, None, None).score / 0.4)
    assert rows[1]["rate"] == -0.05 and rows[1]["ret"] > 0


def test_threshold_table_and_render(monkeypatch):
    from tests.test_research_mesa import _prepared  # synthetic desk data

    times, rs.SYMS = rm.align({s: rm.arrays(p, D.DeskRules.load()) for s, p in _prepared(1600).items()})
    monkeypatch.setattr(rm, "BLOCK_BARS", 400)
    table = rs.threshold_table(times, 1)
    assert set(table) == {"apagada", "-0.5", "-0.3", "-0.2", "-0.1"}
    assert table["apagada"]["trades"] >= table["-0.1"]["trades"]  # a stricter rule never adds trades
    rows = rs.setups(rs.SYMS, rm.tw.WARMUP, len(times))
    year = {"label": "y", "all": rs.describe(rows), "thresholds": table,
            "by_side": {s: rs.describe([r for r in rows if r["side"] == (1 if s == "BUY" else -1)]) for s in ("BUY", "SELL")}}
    md = rs.render({"years": [year]})
    assert "¿Predice algo el sentimiento" in md and ("no predice nada útil" in md or "predice algo" in md)
