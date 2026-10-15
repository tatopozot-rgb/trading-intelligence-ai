"""The practice account's daily report: what the leader and GPT Work study every day."""
from __future__ import annotations

import json
from datetime import date

from trading_intelligence.live import shadow_report as R


def _run(tmp_path, closed):
    d = tmp_path / "shadow"
    d.mkdir()
    (d / "paper.json").write_text(json.dumps({"cash": "30", "positions": {
        "SOLUSDT": {"side": "SELL", "entry": "150", "sl": "155", "tp": "140", "qty": "0.1"}}, "closed": closed}))
    (d / "state.json").write_text(json.dumps({"capital": "30", "status": "RUNNING",
                                              "veto_score": {"evitó pérdida": 2, "dejó pasar ganancia": 1}}))
    return d


def _t(sym, side, pnl, r, why, at):
    return {"symbol": sym, "side": side, "pnl": pnl, "r": r, "why": why, "at": at}


def test_the_report_measures_today_and_the_whole_practice(tmp_path):
    d = _run(tmp_path, [_t("BTCUSDT", "BUY", "2.0", "1.5", "meta", "2026-10-11T10:00:00+00:00"),
                        _t("ETHUSDT", "SELL", "-1.0", "-1.0", "stop", "2026-10-12T09:00:00+00:00"),
                        _t("BTCUSDT", "BUY", "0.5", "0.4", "señal contraria", "2026-10-12T15:00:00+00:00")])
    r = R.build(d, date(2026, 10, 12))
    assert r["hoy"]["operaciones"] == 2 and r["acumulado"]["operaciones"] == 3
    assert r["acumulado"]["esperanza_r"] == round((1.5 - 1.0 + 0.4) / 3, 2)
    assert r["acumulado"]["factor_beneficio"] == 2.5
    assert r["neto_pct"] == round(1.5 / 30 * 100, 2)
    assert r["caida_max_pct"] == round(1.0 / 32 * 100, 2)  # from 32 down to 31
    assert r["por_moneda"]["BTCUSDT"]["operaciones"] == 2 and r["vetos"]["evitó pérdida"] == 2
    text = R.render(r)
    assert "dinero ficticio" in text and "Muestra corta" in text and "SOLUSDT" not in text.split("Posiciones")[0]


def test_the_cli_writes_markdown_and_json(tmp_path):
    d = _run(tmp_path, [])
    out = tmp_path / "out"
    assert R.main(["--dir", str(d), "--salida", str(out), "--dia", "2026-10-11"]) == 0
    assert (out / "2026-10-11.md").exists() and json.loads((out / "2026-10-11.json").read_text())["acumulado"][
        "operaciones"] == 0


def test_today_is_the_owners_ecuador_day_not_the_utc_one(tmp_path):
    # The report runs at 19:30 Ecuador, 00:30 UTC of the next day: trades of the Ecuador evening count as today.
    d = _run(tmp_path, [_t("BTCUSDT", "BUY", "1.0", "1.0", "meta", "2026-10-13T15:00:00+00:00"),
                        _t("ETHUSDT", "BUY", "1.0", "1.0", "meta", "2026-10-14T00:20:00+00:00"),  # 19:20 Ecuador, 13-10
                        _t("SOLUSDT", "BUY", "1.0", "1.0", "meta", "2026-10-14T05:30:00+00:00")])  # 00:30 Ecuador, 14-10
    assert R.build(d, date(2026, 10, 13))["hoy"]["operaciones"] == 2
    assert R.build(d, date(2026, 10, 14))["hoy"]["operaciones"] == 1
    assert R._local_day("not a date") is None and R._local_day("2026-10-14T03:00:00") == date(2026, 10, 13)
