"""Tests for research_real (synthetic data, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_real as rr
from trading_intelligence.live import desk as D


def _sym(n=600, at=(10,), stop=95.0):
    close = np.full(n, 100.0)
    close[300:] = 120.0  # every long that is still open by then reaches its 3R target
    side = np.zeros(n, dtype=np.int8)
    side[list(at)] = 1
    return rm.Sym(np.arange(n, dtype=np.int64), close, close * 1.001, close * 0.999, close, side, np.full(n, 0.5),
                  np.where(side != 0, stop, np.nan), np.zeros(n), np.full(n, np.nan), np.zeros(n, bool))


@pytest.fixture(autouse=True)
def _plain_rules(monkeypatch):
    monkeypatch.setattr(D.DeskRules, "load", classmethod(lambda cls, *a, **k: D.DeskRules()))


def test_blocks_are_chained_with_the_previous_final_capital():
    s = _sym(1200, at=(10, 610))
    run = rr.run_chained({"XUSDT": s}, [(0, 600), (600, 1200)], 31.69, None)
    assert len(run["equity"]) == 1200
    first_end = 31.69 + sum(t["pnl"] for t in run["trades"] if t["k0"] < 600)
    assert run["starts"] == [31.69, pytest.approx(first_end)]
    assert run["equity"][599] == pytest.approx(first_end)
    assert run["equity"][-1] == pytest.approx(31.69 + sum(t["pnl"] for t in run["trades"]))


def test_binance_minimums_keep_btc_and_eth_out_of_a_31_usdt_account():
    syms = {name: _sym() for name in ("BTCUSDT", "ETHUSDT", "SOLUSDT")}
    small = rr.run_chained(syms, [(0, 600)], rr.REAL_CAPITAL, None)
    assert {t["symbol"] for t in small["trades"]} == {"SOLUSDT"}
    big = rr.run_chained(syms, [(0, 600)], 1000.0, None)
    assert {t["symbol"] for t in big["trades"]} == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


def test_summary_net_drawdown_daily_equity_and_deflated_sharpe():
    times = pd.date_range("2026-01-01", periods=288 * 6, freq="5min", tz="UTC").as_unit("ns").asi8
    eq = list(np.linspace(100, 90, 288 * 3)) + list(np.linspace(90, 120, 288 * 3))
    s = rr.summarize({"equity": eq, "trades": []}, times, 0, 100.0, 257)
    assert s["net_pct"] == pytest.approx(20.0) and s["max_dd_pct"] == pytest.approx(10.0)
    assert s["net_dd"] == pytest.approx(2.0)
    assert len(s["daily_equity"]) == 6 and s["daily_equity"]["2026-01-06"] == pytest.approx(120.0)
    assert 0.0 <= s["dsr"] <= 1.0 and len(s["quarters"]) == 4


def _years(real, fijo2, dsr):
    return [{"rows": {"real": {"net_pct": n, "net_dd": nd, "dsr": dsr}, "fijo2": {"net_pct": f}}}
            for (n, nd), f in zip(real, fijo2)]


def test_preregistered_recommendation():
    assert rr.recommend(_years([(50, 1.2), (20, 1.1)], [5, 5], 0.97)) == (True, "seguir igual")
    assert rr.recommend(_years([(50, 1.2), (20, 1.1)], [5, 5], 0.5))[1].startswith("bajar el tamaño")
    assert rr.recommend(_years([(50, 1.2), (20, 1.1)], [5, -1], 0.5))[1] == "pausar las entradas nuevas"
    assert rr.recommend(_years([(50, 1.2), (6, 0.2)], [5, 5], 0.99))[1].startswith("pausar las entradas nuevas y")


def test_evaluate_and_render(monkeypatch):
    from tests.test_research_mesa import _prepared

    times, rr.SYMS = rm.align({s: rm.arrays(p, D.DeskRules()) for s, p in _prepared(1600).items()})
    monkeypatch.setattr(rm, "BLOCK_BARS", 400)
    rr.REGIME = {name: np.full(len(times), rm.LONG, dtype=np.int8) for name in rr.SYMS}
    rr.EVENTS = {name: np.full(len(times), rm.BOTH, dtype=np.int8) for name in rr.SYMS}
    rows = rr.evaluate(times, 1, 257)
    assert set(rows) == set(rr.ROWS)
    assert all(t >= 0 for t in (r["trades"] for r in rows.values()))
    years = [{"label": "y1", "desk": 1.73, "rows": rows}, {"label": "y2", "desk": 0.2, "rows": rows}]
    md = rr.render(years, 257)
    assert "dos listones" in md and "Recomendación preregistrada" in md and "31,69" in md
