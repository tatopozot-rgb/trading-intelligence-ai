"""Tests for research_mesa (synthetic data, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import two_way_backtest as tw
from trading_intelligence.live import desk as D


def _m5(n, seed, drift):
    idx = pd.date_range("2026-08-01", periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(seed)
    steps = drift * np.sign(np.sin(np.arange(n) / 150)) + rng.normal(0, 0.0025, n)  # alternating trends
    close = 100 * np.cumprod(1 + steps)
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.002,
                         "low": np.minimum(open_, close) * 0.998, "close": close, "volume": 10.0}, index=idx)


def _prepared(n=1400):
    out = {}
    for i, sym in enumerate(("SOLUSDT", "XRPUSDT")):
        m5 = _m5(n, i, 0.0015)
        h1 = m5.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        funding = pd.Series([0.01, -0.02, 0.08], index=m5.index[[0, 400, 900]])
        out[sym] = tw.prepare(m5, h1, tw.WARMUP, None, funding)
    return out


@pytest.fixture(scope="module")
def prepared():
    return _prepared()


def test_replay_matches_the_desk_backtest_trade_for_trade(prepared):
    rules = D.DeskRules.load()
    times, syms = rm.align({s: rm.arrays(p, rules) for s, p in prepared.items()})
    mine = rm.replay(syms, 0, len(times), rm.BASELINE, rm.SIZINGS[0], frozenset(rm.RULES), rules, slippage=0.0,
                     capital=37.0)
    theirs = tw.simulate(prepared, "mesa_r3", 37.0)
    assert len(theirs.trades) > 0
    assert [(t["symbol"], t["side"], round(t["pnl"], 9)) for t in mine.trades] == \
           [(t["symbol"], t["side"], round(t["pnl"], 9)) for t in theirs.trades]


def test_slippage_costs_money(prepared):
    rules = D.DeskRules.load()
    times, syms = rm.align({s: rm.arrays(p, rules) for s, p in prepared.items()})
    a = rm.replay(syms, 0, len(times), slippage=0.0, rules=rules)
    b = rm.replay(syms, 0, len(times), slippage=rm.SLIPPAGE, rules=rules)
    assert sum(t["pnl"] for t in b.trades) < sum(t["pnl"] for t in a.trades)


def _sym(n=600, side_at=(), stop_pct=0.02, near=(), funding=np.nan, mood=0.0, path=None):
    close = np.full(n, 100.0) if path is None else path
    side = np.zeros(n, dtype=np.int8)
    stop = np.full(n, np.nan)
    for k, s in side_at:
        side[k] = s
        stop[k] = close[k] * (1 - s * stop_pct)
    nr = np.zeros(n, dtype=bool)
    nr[list(near)] = True
    return rm.Sym(np.arange(n, dtype=np.int64), close.copy(), close * 1.001, close * 0.999, close.copy(), side,
                  np.full(n, 0.5), stop, np.full(n, mood), np.full(n, funding), nr)


def test_veto_audit_counts_a_setup_once_not_per_bar():
    path = np.r_[np.full(110, 100.0), np.linspace(100, 120, 490)]  # goes up after the veto: a missed win
    s = _sym(side_at=[(k, 1) for k in range(100, 106)], near=range(100, 106), path=path)
    audit = rm.veto_audit({"X": s}, 0, 600, D.DeskRules())
    assert audit["redondo"]["setups"] == 1 and audit["redondo"]["dejó pasar ganancia"] == 1
    assert audit["redondo"]["solo"] == 1 and audit["rr"]["setups"] == 0  # 3R always clears 1.5:1


def test_vetoes_follow_the_rules():
    rules = D.DeskRules()
    s = _sym(side_at=[(10, 1)], funding=0.08, mood=-0.8)
    assert set(rm.vetoes(s, 10, 1, 3.0, rules)) == {"financiacion", "sentimiento"}
    assert rm.vetoes(s, 10, -1, 3.0, rules) == []  # a short is with the crowd's funding and mood
    assert "rr" in rm.vetoes(s, 10, 1, 1.2, rules)


def test_leverage_skips_stops_beyond_liquidation_and_fixed_risk_sizes():
    s = _sym(side_at=[(10, 1)], stop_pct=0.40)
    rep = rm.replay({"X": s}, 0, 600, sizing=rm.SIZINGS[4], rules=D.DeskRules(), slippage=0.0)
    assert rep.skipped_liquidation == 1 and rep.trades == []
    s = _sym(side_at=[(10, 1)], stop_pct=0.05)
    rep = rm.replay({"X": s}, 0, 600, sizing=rm.Sizing("f", 0.02), rules=D.DeskRules(), slippage=0.0)
    assert rep.trades[0]["risk_usdt"] == pytest.approx(rm.CAPITAL * 0.02, rel=1e-6)


def test_time_exit_and_half_kelly_and_chain():
    s = _sym(side_at=[(10, 1)], stop_pct=0.05)
    rep = rm.replay({"X": s}, 0, 600, exits=rm.Exits(3.0, 1.0, 0.5, 24), rules=D.DeskRules(), slippage=0.0)
    assert rep.trades[0]["why"] == "tiempo" and rep.trades[0]["k1"] == 34
    trades = [{"pnl": 3.0, "risk_usdt": 1.0}] * 5 + [{"pnl": -1.0, "risk_usdt": 1.0}] * 5
    assert rm.half_kelly(trades) == pytest.approx(min(tw.RISK_MAX, (0.5 - 0.5 / 3) / 2))
    assert rm.half_kelly(trades[:3]) == tw.RISK_MIN
    c = rm.chain([{"net_pct": 10, "trades": 1}, {"net_pct": -5, "trades": 2}], [[1000, 1100], [1000, 950]])
    assert c["net_pct"] == pytest.approx(4.5) and c["trades"] == 3 and c["blocks_positive"] == 1


def test_render_says_loudly_when_quarters_lose():
    q = {"from": "2025-10-01", "to": "2025-12-30", "net_pct": -12.0, "max_dd_pct": 20.0, "net_dd": -0.6, "trades": 50,
         "long_n": 20, "long_net_pct": -15.0, "short_n": 30, "short_net_pct": 3.0, "win_rate": 30.0,
         "btc_buy_hold_pct": -20.0, "blocks_positive": 0, "blocks": 3}
    tot = {"net_pct": 1.0, "max_dd_pct": 2.0, "net_dd": 0.5, "trades": 10, "blocks_positive": 1, "blocks": 2}
    result = {"baseline_year": tot, "quarters": [q], "blocks": [],
              "walk_forward": {"chosen": [], "oos": tot, "baseline_same_blocks": tot},
              "skeptic": {"per_setup": {r: {"setups": 0, "solo": 0, "evitó pérdida": 0, "dejó pasar ganancia": 0,
                                            "sin resultado": 0, "solo_evitó": 0, "solo_dejó": 0} for r in rm.RULES},
                          "ablation": {r: tot for r in (*rm.RULES, "todas")}, "baseline": tot},
              "sizing": {"x": tot}}
    md = rm.render(result, {"desde": "a", "hasta": "b"})
    assert "ALERTA: mesa_r3 pierde en 1 de 1 trimestres" in md and "Trimestre bajista" in md
