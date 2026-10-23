"""
Cap on the total open risk on the futures desk (leader, theory topic 5, 2026-10-23), research only.

Preregistered in docs/research/tope_riesgo/PREREGISTRO.md before any run. The practice desk as in
docs/research/salida_regimen/ (regime b with exit, +-2 h events, Binance costs, 30-day blocks chained, 1,000 USDT, 1x).
The tested rule opens no new position while the open positions on the same side would lose more than 2% of the
bar's equity if every stop were hit (research_mesa.replay open_risk_cap). Reference: the same desk without the cap.
Public data only: no account, no key, no orders. Nothing here changes config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Optional

import numpy as np

from trading_intelligence.backtesting import research_deflactado as rd
from trading_intelligence.backtesting import research_freno_caida as rf
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_real as rr
from trading_intelligence.backtesting import two_way_backtest as tw

YEARS = rr.YEARS
CAPITAL = 1000.0
DECISIVE_N = 301
CAP = 0.02
DESK = rf.DESK
OUT_DIR = Path("docs/research/tope_riesgo")
# key: (label, sizing, open-risk cap, kind)
ROWS = {"t1x": ("1x con tope de 2% al riesgo abierto del mismo lado", rm.SIZINGS[0], CAP, "decisoria"),
        "ref1x": ("1x sin tope (referencia)", rm.SIZINGS[0], None, "referencia")}
REFERENCE = {"t1x": "ref1x"}

SYMS: dict[str, Any] = {}
REGIME: dict[str, np.ndarray] = {}
EVENTS: dict[str, np.ndarray] = {}


def run(syms: dict, bounds: list[tuple[int, int]], sizing: rm.Sizing, cap: Optional[float],
        allow: Optional[dict] = None, entry_allow: Optional[dict] = None) -> dict:
    return rf.run_chained(syms, bounds, CAPITAL, sizing, False, True, allow=allow, entry_allow=entry_allow,
                          open_risk_cap=cap)


def summarize(out: dict, times: np.ndarray, first: int, n_decisive: int) -> dict:
    s = rr.summarize(out, times, first, CAPITAL, n_decisive)
    whys: dict[str, int] = {}
    for t in out["trades"]:
        whys[t["why"]] = whys.get(t["why"], 0) + 1
    s.update(capped=out["capped"], exits=whys)
    return s


def _row(task: tuple) -> tuple:
    key, bounds = task
    _, sizing, cap, _ = ROWS[key]
    return key, run(SYMS, bounds, sizing, cap, allow=REGIME, entry_allow=EVENTS)


def evaluate(times: np.ndarray, workers: int, n_decisive: int) -> dict:
    bounds = rm.blocks(len(times), tw.WARMUP)
    first = bounds[0][0]
    with Pool(max(1, min(workers, len(ROWS)))) as pool:
        out = pool.map(_row, [(k, bounds) for k in ROWS])
    return {k: summarize(o, times, first, n_decisive) for k, o in out}


def build_masks(times: np.ndarray, extras: dict[str, dict], btc_d1: Any) -> None:
    global REGIME, EVENTS
    REGIME = rm.gates(times, list(SYMS), btc_d1, {s: x["h4"] for s, x in extras.items()})["b"]
    events = np.where(rm.near_event(times, rm.macro_events(), rr.EVENT_HOURS), 0, rm.BOTH).astype(np.int8)
    EVENTS = {name: events for name in SYMS}


def passes(years: list[dict], key: str) -> bool:
    beats = all((y["rows"][key]["net_dd"] or -99) > y["desk"] for y in years)
    return beats and years[-1]["rows"][key]["dsr"] >= rd.PASS_DSR


def render(years: list[dict], n: int) -> str:
    L = ["# Tope al riesgo abierto total en la mesa de futuros", "",
         "Preregistro: `docs/research/tope_riesgo/PREREGISTRO.md`, escrito antes de correr. La mesa de práctica 1x con "
         "freno de régimen b y de eventos ±2 h, costos de Binance Futuros (0,05% por lado, 0,02% de deslizamiento, "
         "financiación real) y mínimos por orden; bloques de 30 días encadenados, 1.000 USDT. El tope: no se abre una "
         "posición nueva si las abiertas del mismo lado perderían más del 2% del saldo si saltan todos sus stops. "
         f"Sharpe deflactado con N = {n} decisorias.", "", "## Veredicto", ""]
    for k, v in ROWS.items():
        if v[3] != "decisoria":
            continue
        ref = REFERENCE[k]
        L.append(f"- **{v[0]}: {'pasa' if passes(years, k) else 'no pasa'}.** Neto/caída "
                 + " ; ".join(str(y["rows"][k]["net_dd"]) for y in years)
                 + f" contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 {years[-1]['rows'][k]['dsr']} "
                 f"(listón {rd.PASS_DSR}). Sin tope: neto/caída "
                 + " ; ".join(str(y["rows"][ref]["net_dd"]) for y in years) + ".")
    for y in years:
        L += ["", f"## {y['label']}", "",
              "| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin tope (neto, caída) | Ops | "
              "Señales frenadas por el tope | Salidas | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | "
              "Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            ref = y["rows"].get(REFERENCE.get(k, ""))
            delta = (f"{r['net_pct'] - ref['net_pct']:+.1f} pts, {r['max_dd_pct'] - ref['max_dd_pct']:+.1f} pts"
                     if ref else "—")
            ex = ", ".join(f"{w} {c}" for w, c in sorted(r["exits"].items()))
            L.append(f"| {ROWS[k][0]} | {ROWS[k][3]} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | "
                     f"{delta} | {r['trades']} | {r['capped']} | {ex} | {r['win_rate']}% | "
                     f"{r['worst_trade_pct']:+.1f}% | {r['sharpe_anual']} | {r['dsr']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Una señal frenada cuenta una vez por racha de velas seguidas en la misma moneda. La peor operación es "
          "sobre el capital del bloque. El capital diario está en el JSON. Un resultado pasado no promete uno futuro. "
          "El dinero real no cambia por este estudio."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS
    parser = argparse.ArgumentParser(description="Tope al riesgo abierto en la mesa (investigación)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    years = []
    for a, b in YEARS:
        end = datetime.fromisoformat(b).replace(tzinfo=timezone.utc)
        warm = datetime.fromisoformat(a).replace(tzinfo=timezone.utc) - timedelta(minutes=5 * tw.WARMUP)
        with Pool(max(1, args.workers)) as pool:
            loaded = pool.map(rm._load_symbol, [(s, warm.isoformat(), end.isoformat()) for s in args.simbolos])
        for sym, _, note, _ in loaded:
            print(f"{a}→{b} {sym}: {note}")
        extras = {s: x for s, a_, _, x in loaded if a_ is not None}
        times, SYMS = rm.align({s: x for s, x, _, _ in loaded if x is not None})
        build_masks(times, extras, extras["BTCUSDT"]["d1"])
        years.append({"label": f"{a} → {b}", "desk": DESK[a], "rows": evaluate(times, args.workers, args.decisorias)})
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"tope_riesgo_{stamp}.json").write_text(json.dumps(years, indent=1, default=str),
                                                              encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"tope_riesgo_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
