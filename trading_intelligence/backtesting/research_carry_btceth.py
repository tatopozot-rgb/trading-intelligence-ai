"""
Funding carry on BTC and ETH alone, and whether it fits in 31 USDT, research only.

Preregistered in docs/research/carry_btceth/PREREGISTRO.md before any run. Reuses research_carry: spot long + perp
short of the same quantity, half the capital each leg, decisions every 8 h on the mean of the last 21 funding payments.
Enter at 0.0042%/8h or more (at that rate funding pays the 0.19% round trip within 30 days), leave below 0%. Each
coin alone; "always in" as sensitivity. Judged per docs/research/PROTOCOLO.md: net/drawdown above the desk in both
years and a deflated Sharpe of at least 0.95 in 2025-26. Then the 31 USDT check: order minimums, the leverage the
smallest possible position needs, the rise that liquidates it and how often the rule's holdings saw such a rise.
"""
from __future__ import annotations

import argparse
import json
import math
import urllib.request
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_carry as rc
from trading_intelligence.backtesting import research_deflactado as rd

SYMBOLS = ("BTCUSDT", "ETHUSDT")
LOOKBACK, ENTER, EXIT = 21, 0.0042, 0.0
YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
DESK = {"2024-10-12": 1.67, "2025-10-13": -0.21}
CASH_PCT = 4.0
DECISIVE_N = 254
SMALL_CAPITAL, MMR = 31.0, 0.005
PERP_MIN_FALLBACK = {"BTCUSDT": 100.0, "ETHUSDT": 20.0}
SPOT_MIN_FALLBACK = 5.0
OUT_DIR = Path("docs/research/carry_btceth")


def rules() -> dict[str, tuple[rc.Rule, bool]]:
    out: dict[str, tuple[rc.Rule, bool]] = {}
    for s in SYMBOLS:
        out[f"regla, {s}"] = (rc.Rule(LOOKBACK, ENTER, EXIT, k=1, only=s), True)
    for s in SYMBOLS:
        out[f"siempre dentro, {s}"] = (rc.Rule(LOOKBACK, -math.inf, k=1, only=s), False)
    return out


def hour_index(p: rc.Panel, day: str) -> int:
    return int(np.searchsorted(p.times, pd.Timestamp(day, tz="UTC").value))


def daily_dsr(run: rc.Run, a: int, b: int, n: int) -> tuple[float, float]:
    start = run.curve[a - 1] if a > 0 else rc.CAPITAL
    seg = np.r_[start, run.curve[a:b]][::24]
    r = pd.Series(seg).pct_change().dropna()
    m = rd.moments(r)
    return round(m["sr_anual"], 2), round(rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n,
                                                             1 / m["T"]), 3)


def holdings(run: rc.Run, symbol: str) -> list[tuple[int, int]]:
    """Contiguous holding periods (rebalances joined), as nanosecond times."""
    spans: list[list[int]] = []
    for t in sorted((x for x in run.trades if x["symbol"] == symbol), key=lambda x: x["t0"]):
        if spans and t["t0"] <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], t["t1"])
        else:
            spans.append([t["t0"], t["t1"]])
    return [(a, b) for a, b in spans]


def liquidation_rise(spot_leg: float, margin: float, mmr: float = MMR) -> float:
    """Price rise (fraction) that liquidates a short of notional spot_leg on isolated margin `margin`."""
    return (margin / spot_leg - mmr) / (1 + mmr)


def small_account(p: rc.Panel, run: rc.Run, symbol: str, mins: dict[str, Any], net_annual_pct: float) -> dict:
    i = p.names.index(symbol)
    perp_min = mins["perp"].get(symbol, PERP_MIN_FALLBACK[symbol])
    spot_min = mins["spot"].get(symbol, SPOT_MIN_FALLBACK)
    leg = max(perp_min, spot_min)
    margin = SMALL_CAPITAL - leg
    out: dict[str, Any] = {"symbol": symbol, "perp_min": perp_min, "spot_min": spot_min,
                           "verificado": mins["verified"], "pata_usdt": leg, "margen_usdt": round(margin, 2)}
    if margin <= 0:
        return {**out, "cabe": False}
    rise = liquidation_rise(leg, margin)
    worst, hits = 0.0, 0
    for a, b in holdings(run, symbol):
        ia, ib = np.searchsorted(p.times, a), np.searchsorted(p.times, b)
        seg = p.perp[i, ia:ib + 1]
        if len(seg) < 2 or not np.isfinite(seg[0]):
            continue
        up = float(np.nanmax(seg) / seg[0] - 1)
        worst = max(worst, up)
        hits += up >= rise
    yearly = 2 * net_annual_pct / 100 * leg  # net return per unit of short notional, times the small notional
    return {**out, "cabe": True, "apalancamiento_corto": round(leg / margin, 2), "subida_liquida_pct": round(rise * 100, 1),
            "peor_subida_pct": round(worst * 100, 1), "liquidaciones": hits, "tenencias": len(holdings(run, symbol)),
            "ingreso_usdt_anual_aprox": round(yearly, 2)}


def order_minimums() -> dict[str, Any]:
    spot: dict[str, float] = {}
    perp: dict[str, float] = {}
    verified = {"spot": False, "perp": False}
    try:
        url = "https://data-api.binance.vision/api/v3/exchangeInfo?symbols=" + json.dumps(list(SYMBOLS)).replace(" ", "")
        with urllib.request.urlopen(url, timeout=20) as resp:
            for s in json.load(resp)["symbols"]:
                for f in s["filters"]:
                    if f["filterType"] in ("NOTIONAL", "MIN_NOTIONAL"):
                        spot[s["symbol"]] = float(f.get("minNotional", 0))
        verified["spot"] = bool(spot)
    except Exception as error:  # noqa: BLE001 - public endpoint may be unreachable from the runner
        print(f"exchangeInfo spot: {type(error).__name__}")
    try:
        with urllib.request.urlopen("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=20) as resp:
            for s in json.load(resp)["symbols"]:
                if s["symbol"] in SYMBOLS:
                    for f in s["filters"]:
                        if f["filterType"] == "MIN_NOTIONAL":
                            perp[s["symbol"]] = float(f.get("notional", 0))
        verified["perp"] = bool(perp)
    except Exception as error:  # noqa: BLE001
        print(f"exchangeInfo futuros: {type(error).__name__}")
    return {"spot": spot, "perp": perp, "verified": verified}


def evaluate(p: rc.Panel, n_decisive: int, mins: dict[str, Any]) -> dict[str, Any]:
    res: dict[str, Any] = {"rows": {}, "small": {}}
    for name, (rule, decisive) in rules().items():
        run = rc.simulate(p, rule)
        row: dict[str, Any] = {"decisoria": decisive, "todo": rc.window(run, 0, len(p.times)), "years": [],
                               "rebalanceos": run.rebalances, "entradas": len(holdings(run, rule.only or ""))}
        for a, b in YEARS:
            ia, ib = hour_index(p, a), hour_index(p, b)
            w = rc.window(run, ia, ib)
            sr, dsr = daily_dsr(run, ia, ib, n_decisive)
            row["years"].append({**w, "from": a, "to": b, "sharpe_anual": sr, "dsr": dsr,
                                 "gana_mesa": (w["net_dd"] if w["net_dd"] is not None else -99) > DESK[a],
                                 "quarters": [(q, rc.window(run, ia + x, ia + y)["net_pct"])
                                              for q, x, y in rc.quarters(p.times[ia:ib])]})
        y2 = row["years"][-1]
        row["pasa"] = decisive and all(y["gana_mesa"] for y in row["years"]) and y2["dsr"] >= rd.PASS_DSR
        row["daily_equity"] = {str(pd.Timestamp(t, tz="UTC").date()): round(float(v), 2)
                               for t, v in zip(p.times[::24], run.curve[::24])}
        res["rows"][name] = row
        if decisive and rule.only:
            res["small"][rule.only] = small_account(p, run, rule.only, mins, row["todo"]["annual_pct"])
    return res


def render(res: dict[str, Any], meta: dict) -> str:
    L = ["# Carry de financiación en BTC y ETH (spot comprado + perpetuo vendido)", "",
         f"Preregistro: `docs/research/carry_btceth/PREREGISTRO.md`, escrito antes de correr. Datos {meta['desde']} → "
         f"{meta['hasta']}. Entra con la media de 21 pagos ≥ {ENTER}%/8h, sale bajo 0%. Mitad spot, mitad margen del "
         "corto (1x). Costes: spot 0,10% y perpetuo 0,05% por lado, más 0,02% de deslizamiento en cada pata. Efectivo "
         f"de referencia: {CASH_PCT:g}% al año.", "", "## Veredicto", ""]
    for name, r in res["rows"].items():
        if not r["decisoria"]:
            continue
        ys = r["years"]
        L.append(f"- **{name}: {'pasa' if r['pasa'] else 'no pasa'}.** Neto {ys[0]['net_pct']:+.2f}% y "
                 f"{ys[1]['net_pct']:+.2f}% (efectivo {CASH_PCT:g}%); neto/caída {ys[0]['net_dd']} ; {ys[1]['net_dd']} "
                 f"contra 1,67 ; −0,21; Sharpe deflactado 2025-26 {ys[1]['dsr']} (listón {rd.PASS_DSR}).")
    for y_i, (a, b) in enumerate(YEARS):
        L += ["", f"## {a} → {b}", "", "| Prueba | Neto % | Anual % | Máx. caída | Neto/caída | Financiación % | "
              "Costes % | Base % | Tiempo dentro | Sharpe anual | Sharpe deflactado | Trimestres |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for name, r in res["rows"].items():
            y = r["years"][y_i]
            q = " / ".join(f"{v:+.2f}" for _, v in y["quarters"])
            L.append(f"| {name} | {y['net_pct']:+.2f}% | {y['annual_pct']:+.2f}% | {y['max_dd_pct']}% | {y['net_dd']} | "
                     f"{y['funding_pct']:+.2f}% | {y['costs_pct']}% | {y['basis_pct']:+.2f}% | {y['invested_pct']}% | "
                     f"{y['sharpe_anual']} | {y['dsr']} | {q} |")
    L += ["", f"## Todo el periodo ({meta['desde']} → {meta['hasta']})", "",
          "| Prueba | Neto % | Anual % | Máx. caída | Financiación % | Costes % | Tiempo dentro | Entradas | Rebalanceos |",
          "|---|---|---|---|---|---|---|---|---|"]
    for name, r in res["rows"].items():
        w = r["todo"]
        L.append(f"| {name} | {w['net_pct']:+.1f}% | {w['annual_pct']:+.2f}% | {w['max_dd_pct']}% | {w['funding_pct']:+.1f}% | "
                 f"{w['costs_pct']}% | {w['invested_pct']}% | {r['entradas']} | {r['rebalanceos']} |")
    L += ["", f"## ¿Cabe en {SMALL_CAPITAL:g} USDT?", ""]
    for s, m in res["small"].items():
        ver = "verificado" if m["verificado"]["perp"] else "no verificado (Claude local debe confirmarlo)"
        if not m["cabe"]:
            L.append(f"- **{s}: no cabe.** El perpetuo pide al menos {m['perp_min']:g} USDT de tamaño ({ver}); con "
                     f"{SMALL_CAPITAL:g} USDT no queda margen para el corto después de comprar el spot.")
            continue
        L.append(f"- **{s}:** pata mínima {m['pata_usdt']:g} USDT (perpetuo {m['perp_min']:g}, {ver}; spot "
                 f"{m['spot_min']:g}), margen del corto {m['margen_usdt']:g} USDT, apalancamiento del corto "
                 f"{m['apalancamiento_corto']}x. Lo liquida una subida de {m['subida_liquida_pct']}% (margen aislado, "
                 f"mantenimiento {MMR * 100:g}%). En {m['tenencias']} tenencias de la regla desde 2020, la peor subida fue "
                 f"{m['peor_subida_pct']}% y hubo {m['liquidaciones']} que habrían liquidado sin rebalancear. Ingreso neto "
                 f"aproximado: {m['ingreso_usdt_anual_aprox']:+.2f} USDT al año.")
    L += ["", "Advertencias: el spot y el perpetuo viven en carteras distintas; la ganancia del spot no protege al corto de "
          "la liquidación salvo que se pase dinero entre carteras (el rebalanceo). Un resultado pasado no promete uno "
          "futuro. Nada de esto mueve dinero real."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Carry de financiación en BTC y ETH (investigación)")
    parser.add_argument("--desde", default=rc.DEFAULT_START)
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(args.desde).replace(tzinfo=timezone.utc)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    with Pool(2) as pool:
        loaded = pool.map(rc._load, [(s, start.isoformat(), end.isoformat()) for s in SYMBOLS])
    raw = {}
    last = []
    for sym, data, note in loaded:
        print(f"{sym}: {note}")
        if not any(x.empty for x in data):
            raw[sym] = data
            last.append(data[2].index[-1])
    end = min(end, max(last).to_pydatetime()) if last else end
    p = rc.build_panel(raw, start, end, (LOOKBACK,))
    mins = order_minimums()
    res = evaluate(p, args.decisorias, mins)
    meta = {"desde": start.date().isoformat(), "hasta": end.date().isoformat(), "minimos": mins}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"carry_btceth_{stamp}.json").write_text(json.dumps({"meta": meta, **res}, indent=1, default=str),
                                                            encoding="utf-8")
    report = render(res, meta)
    (args.salida / f"carry_btceth_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
