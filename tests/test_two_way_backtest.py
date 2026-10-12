"""The real-data check of the futures engine, on synthetic bars (the real run is in GitHub Actions)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import two_way_backtest as B

END = datetime(2026, 10, 10, tzinfo=timezone.utc)


def _fetcher(drift):
    def fetch(symbol, interval, start, end):
        step = {"5m": "5min", "1h": "1h"}[interval]
        idx = pd.date_range(start, end, freq=step, inclusive="left")
        rng = np.random.default_rng(sum(map(ord, symbol)))
        wave = np.sin(np.arange(len(idx)) / 40) * 0.004
        c = 100 * np.exp(np.cumsum(rng.normal(drift.get(symbol, 0.0), 0.002, len(idx)) + wave / 10))
        return pd.DataFrame({"open": c, "high": c * 1.003, "low": c * 0.997, "close": c, "volume": 1.0}, index=idx)
    return fetch


def _extras(symbol, start, end):
    idx = pd.date_range(start, end, freq="5min")
    top = pd.Series(1.3 if symbol == "SOLUSDT" else 0.7, index=idx)  # top traders long SOL, short XRP
    funding = pd.Series(0.01, index=pd.date_range(start, end, freq="8h"))
    return top, funding


def test_every_variant_is_measured_with_costs_and_written_down(tmp_path):
    out = B.run(2, ["SOLUSDT", "XRPUSDT"], 37.0, tmp_path, _fetcher({"SOLUSDT": 0.0004, "XRPUSDT": -0.0004}),
                end=END, warmup=200, extras=_extras)
    assert [s["variante"] for s in out] == list(B.ALL_VARIANTS) and "mesa" in [s["variante"] for s in out]
    assert "Escenarios de riesgo" in (tmp_path / "2026-10-10.md").read_text()
    for s in out:
        assert s["operaciones"] == s["por"]["BUY"]["operaciones"] + s["por"]["SELL"]["operaciones"]
        if s["operaciones"]:
            assert s["comisiones_usdt"] > 0
    report = (tmp_path / "2026-10-10.md").read_text()
    assert "Veredicto" in report and "aproximación" in report
    assert (tmp_path / "2026-10-10.json").exists()


def test_a_falling_market_is_traded_short():
    fetch = _fetcher({"SOLUSDT": -0.0008})
    m5 = fetch("SOLUSDT", "5m", datetime(2026, 10, 7, tzinfo=timezone.utc), END)
    h1 = fetch("SOLUSDT", "1h", datetime(2026, 10, 4, tzinfo=timezone.utc), END)
    res = B.simulate({"SOLUSDT": B.prepare(m5, h1, 200)}, "regimen", 37.0)
    sides = {t["side"] for t in res.trades}
    assert "SELL" in sides


def test_btc_does_not_fit_a_small_account():
    fetch = _fetcher({"BTCUSDT": 0.0008})
    m5 = fetch("BTCUSDT", "5m", datetime(2026, 10, 8, tzinfo=timezone.utc), END)
    h1 = fetch("BTCUSDT", "1h", datetime(2026, 10, 5, tzinfo=timezone.utc), END)
    res = B.simulate({"BTCUSDT": B.prepare(m5, h1, 200)}, "regimen", 37.0)
    assert not res.trades and res.skipped_minimum > 0  # 40% of 37 USDT < Binance's 100 USDT minimum


def test_risk_is_sized_from_1_to_15_percent_and_positions_fit_the_equity():
    fetch = _fetcher({"SOLUSDT": 0.0006, "XRPUSDT": -0.0006})
    start = datetime(2026, 10, 6, tzinfo=timezone.utc)
    prepared = {s: B.prepare(fetch(s, "5m", start, END), fetch(s, "1h", datetime(2026, 10, 3, tzinfo=timezone.utc), END),
                             200, *_extras(s, start, END)) for s in ("SOLUSDT", "XRPUSDT")}
    res = B.simulate(prepared, "tendencia_rango_1h_top", 37.0)
    assert res.risks and all(B.RISK_MIN <= r <= B.RISK_MAX for r in res.risks)


def test_the_desk_scores_its_vetoes():
    fetch = _fetcher({"SOLUSDT": 0.0006})
    start = datetime(2026, 10, 6, tzinfo=timezone.utc)
    p = {"SOLUSDT": B.prepare(fetch("SOLUSDT", "5m", start, END),
                              fetch("SOLUSDT", "1h", datetime(2026, 10, 3, tzinfo=timezone.utc), END), 200,
                              *_extras("SOLUSDT", start, END))}
    strict = B.D.DeskRules(min_reward_risk=B.Decimal("50"))  # refuses everything
    res = B.simulate(p, "mesa", 37.0, strict)
    assert not res.trades and sum(res.vetoes.values()) > 0


def test_the_verdict_names_positive_variants_with_too_few_trades():
    def row(name, n, net):
        side = {"operaciones": n, "neto": net}
        return {"variante": name, "operaciones": n, "acierto_pct": 50, "neto_usdt": net, "neto_pct": net, "max_caida_pct": 5,
                "riesgo_medio_pct": 5, "comisiones_usdt": 0.1, "por": {"BUY": side, "SELL": {"operaciones": 0, "neto": 0}},
                "final": "fin del periodo", "vetos": {"evitó pérdida": 0, "dejó pasar ganancia": 0, "sin resultado": 0}}
    meta = {"desde": "a", "hasta": "b", "capital": 37.0, "simbolos": ["SOLUSDT"]}
    text = B.render([row("tendencia_rango_1h", 138, -2.34), row("mesa", 25, 6.39)], meta)
    assert "**mesa** +6.39 USDT en 25" in text and "muestra es corta" in text
    assert "Entre las de 30 operaciones o más, ninguna ganó" in text


def test_real_risk_respects_the_caps_and_leverage_refuses_stops_beyond_liquidation():
    fetch = _fetcher({"SOLUSDT": 0.0006, "XRPUSDT": -0.0006})
    start = datetime(2026, 10, 6, tzinfo=timezone.utc)
    prepared = {s: B.prepare(fetch(s, "5m", start, END), fetch(s, "1h", datetime(2026, 10, 3, tzinfo=timezone.utc), END),
                             200, *_extras(s, start, END)) for s in ("SOLUSDT", "XRPUSDT")}
    live = B.simulate(prepared, "tendencia_rango_1h_top", 37.0)
    # at 1x with 50% per position, a stop of at most 15% loses at most 7.5% of the account
    assert live.real_risks and max(live.real_risks) <= 0.075 + 1e-9
    assert all(r <= n + 1e-9 for r, n in zip(live.real_risks, live.risks))
    wild = B.Sizing("20x", risk_min=0.15, risk_max=0.30, max_position=10, leverage=20)
    res = B.simulate(prepared, "tendencia_rango_1h_top", 37.0, sizing=wild)
    assert res.skipped_liquidation > 0  # liquidation at ~4.5% comes before market stops of 3-15%
    assert all(r <= 0.30 + 1e-9 for r in res.real_risks)


def test_the_backtest_rides_a_bull_run_in_the_live_desk_variant():
    fetch = _fetcher({"SOLUSDT": 0.0003})  # about +9% a day: a bull run after two weeks
    start = datetime(2026, 9, 22, tzinfo=timezone.utc)
    p = {"SOLUSDT": B.prepare(fetch("SOLUSDT", "5m", start, END),
                              fetch("SOLUSDT", "1h", datetime(2026, 9, 19, tzinfo=timezone.utc), END), 200,
                              *_extras("SOLUSDT", start, END))}
    riding = B.D.DeskRules(target_r=B.Decimal("3"), target_min_pct=None)  # the bull-run mode switched on
    live = B.simulate(p, "mesa", 37.0, rules=riding)
    plain = B.simulate(p, "mesa_libre", 37.0, rules=riding)
    assert live.rally_entries > 0 and plain.rally_entries == 0
    assert all(t["side"] == "BUY" for t in live.trades)
    assert B.simulate(p, "mesa", 37.0).rally_entries == 0  # the live rules: bull-run mode off (2026-10-12)
