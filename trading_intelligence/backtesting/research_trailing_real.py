"""
The real futures bot with the trailing stop from 2R and no close on an opposite signal (leader, 2026-10-22),
research only.

Preregistered in docs/research/trailing_real/PREREGISTRO.md before any run. The real bot as in docs/research/real/
(31.69 USDT, 1x, risk 1-15% by quality, regime b with exit, +-2 h events, Binance costs and minimums, 30-day blocks
chained). Only the exits change: the trailing stop starts at +2R (R/2 behind, 3R target kept) and an opposite signal
no longer closes the position. Public data only: no account, no key, no orders. Nothing here changes config/ or live/.
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
CAPITAL = rr.REAL_CAPITAL
DECISIVE_N = 297
DESK = rf.DESK
OUT_DIR = Path("docs/research/trailing_real")
TESTED = rm.Exits(trail_start=2.0, close_on_signal=False)
# key: (label, exits, kind)
ROWS = {"t2r": ("Real con trailing desde 2R y sin cierre por señal", TESTED, "decisoria"),
        "ref": ("Real tal cual (referencia)", rm.BASELINE, "referencia")}
REFERENCE = {"t2r": "ref"}

SYMS: dict[str, Any] = {}
REGIME: dict[str, np.ndarray] = {}
EVENTS: dict[str, np.ndarray] = {}


def run(syms: dict, bounds: list[tuple[int, int]], exits: rm.Exits, allow: Optional[dict] = None,
        entry_allow: Optional[dict] = None) -> dict:
    return rf.run_chained(syms, bounds, CAPITAL, rm.SIZINGS[0], False, True, allow=allow, entry_allow=entry_allow,
                          exits=exits)


def summarize(out: dict, times: np.ndarray, first: int, n_decisive: int) -> dict:
    s = rr.summarize(out, times, first, CAPITAL, n_decisive)
    whys: dict[str, int] = {}
    for t in out["trades"]:
        whys[t["why"]] = whys.get(t["why"], 0) + 1
    s["exits"] = whys
    return s


def _row(task: tuple) -> tuple:
    key, bounds = task
    return key, run(SYMS, bounds, ROWS[key][1], allow=REGIME, entry_allow=EVENTS)


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
    L = ["# El bot real con trailing desde 2R y sin cierre por señal opuesta", "",
         "Preregistro: `docs/research/trailing_real/PREREGISTRO.md`, escrito antes de correr. El bot real (31,69 USDT, "
         "1x, riesgo 1-15% por calidad, régimen b con salida, eventos ±2 h), costos de Binance Futuros (0,05% por lado, "
         "0,02% de deslizamiento, financiación real) y mínimos por orden; bloques de 30 días encadenados. Cambia solo "
         "la salida: el trailing arranca en +2R (a R/2, meta 3R) y la señal contraria ya no cierra. Sharpe deflactado "
         f"con N = {n} decisorias.", "", "## Veredicto", ""]
    for k, v in ROWS.items():
        if v[2] != "decisoria":
            continue
        ref = REFERENCE[k]
        L.append(f"- **{v[0]}: {'pasa' if passes(years, k) else 'no pasa'}.** Neto/caída "
                 + " ; ".join(str(y["rows"][k]["net_dd"]) for y in years)
                 + f" contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 {years[-1]['rows'][k]['dsr']} "
                 f"(listón {rd.PASS_DSR}). Tal cual: neto/caída "
                 + " ; ".join(str(y["rows"][ref]["net_dd"]) for y in years) + ".")
    for y in years:
        L += ["", f"## {y['label']}", "",
              "| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra tal cual (neto, caída) | Ops | "
              "Salidas | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            ref = y["rows"].get(REFERENCE.get(k, ""))
            delta = (f"{r['net_pct'] - ref['net_pct']:+.1f} pts, {r['max_dd_pct'] - ref['max_dd_pct']:+.1f} pts"
                     if ref else "—")
            ex = ", ".join(f"{w} {c}" for w, c in sorted(r["exits"].items()))
            L.append(f"| {ROWS[k][0]} | {ROWS[k][2]} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | "
                     f"{delta} | {r['trades']} | {ex} | {r['win_rate']}% | {r['worst_trade_pct']:+.1f}% | "
                     f"{r['sharpe_anual']} | {r['dsr']} | " + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "\"stop\" incluye el trailing (el stop movido). La peor operación es sobre el capital del bloque. El capital "
          "diario está en el JSON. Un resultado pasado no promete uno futuro. El dinero real no cambia por este estudio: "
          "si pasa, decide el líder."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS
    parser = argparse.ArgumentParser(description="Bot real con trailing desde 2R (investigación)")
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
    (args.salida / f"trailing_real_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"trailing_real_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
