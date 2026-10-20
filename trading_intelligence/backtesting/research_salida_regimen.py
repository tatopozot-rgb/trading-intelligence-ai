"""
Regime exit on the current desk (leader, 2026-10-20), research only.

Preregistered in docs/research/salida_regimen/PREREGISTRO.md before any run. The desk as in docs/research/real/
(regime brake b for entries, +-2 h event brake, Binance costs, 30-day blocks chained, 1,000 USDT) in 1x and 3x. The
tested rule closes the open longs on the first 5-minute bar after BTC's daily close falls under its 50-day mean
(research_mesa.replay close_on_gate=True). The reference keeps them until their stop, target or opposite signal
(close_on_gate=False). Public data only: no account, no key, no orders. Nothing here changes config/ or live/.
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
DECISIVE_N = 288
DESK = rf.DESK
OUT_DIR = Path("docs/research/salida_regimen")
# key: (label, sizing, close open longs when the regime turns, kind)
ROWS = {"s1x": ("1x con salida por régimen", rm.SIZINGS[0], True, "decisoria"),
        "s3x": ("3x con salida por régimen", rm.SIZINGS[4], True, "decisoria"),
        "ref1x": ("1x sin salida por régimen (referencia)", rm.SIZINGS[0], False, "referencia"),
        "ref3x": ("3x sin salida por régimen (referencia)", rm.SIZINGS[4], False, "referencia")}
REFERENCE = {"s1x": "ref1x", "s3x": "ref3x"}

SYMS: dict[str, Any] = {}
REGIME: dict[str, np.ndarray] = {}
EVENTS: dict[str, np.ndarray] = {}


def run(syms: dict, bounds: list[tuple[int, int]], sizing: rm.Sizing, exit_on_regime: bool,
        allow: Optional[dict] = None, entry_allow: Optional[dict] = None) -> dict:
    return rf.run_chained(syms, bounds, CAPITAL, sizing, False, True, allow=allow, entry_allow=entry_allow,
                          close_on_gate=exit_on_regime)


def summarize(out: dict, times: np.ndarray, first: int, n_decisive: int) -> dict:
    s = rr.summarize(out, times, first, CAPITAL, n_decisive)
    by_regime = [t for t in out["trades"] if t["why"] == "régimen"]
    s.update(regime_exits=len(by_regime),
             regime_exits_pnl_pct=round(sum(t["pnl"] / t["block_capital"] for t in by_regime) * 100, 2),
             stops=sum(1 for t in out["trades"] if t["why"] == "stop"))
    return s


def _row(task: tuple) -> tuple:
    key, bounds = task
    _, sizing, exit_on_regime, _ = ROWS[key]
    return key, run(SYMS, bounds, sizing, exit_on_regime, allow=REGIME, entry_allow=EVENTS)


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
    L = ["# Salida por régimen sobre la mesa actual", "",
         "Preregistro: `docs/research/salida_regimen/PREREGISTRO.md`, escrito antes de correr. La mesa con freno de "
         "régimen b para entrar y de eventos ±2 h, costos de Binance Futuros (0,05% por lado, 0,02% de deslizamiento, "
         "financiación real) y mínimos por orden; bloques de 30 días encadenados, 1.000 USDT. La salida por régimen "
         "cierra los largos abiertos en la primera vela de 5 minutos del día siguiente al cierre de BTC bajo su media "
         f"de 50 días; la referencia los deja hasta su stop o su meta. Sharpe deflactado con N = {n} decisorias.", "",
         "## Veredicto", ""]
    for k, v in ROWS.items():
        if v[3] != "decisoria":
            continue
        ref = REFERENCE[k]
        L.append(f"- **{v[0]}: {'pasa' if passes(years, k) else 'no pasa'}.** Neto/caída "
                 + " ; ".join(str(y["rows"][k]["net_dd"]) for y in years)
                 + f" contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 {years[-1]['rows'][k]['dsr']} "
                 f"(listón {rd.PASS_DSR}). Sin salida por régimen: neto/caída "
                 + " ; ".join(str(y["rows"][ref]["net_dd"]) for y in years) + ".")
    for y in years:
        L += ["", f"## {y['label']}", "",
              "| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin salida (neto, caída) | Ops | "
              "Cerradas por régimen | Resultado de esas (% del bloque) | Stops | Acierto | Peor op. | Sharpe anual | "
              "Sharpe deflactado | Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            ref = y["rows"].get(REFERENCE.get(k, ""))
            delta = (f"{r['net_pct'] - ref['net_pct']:+.1f} pts, {r['max_dd_pct'] - ref['max_dd_pct']:+.1f} pts"
                     if ref else "—")
            L.append(f"| {ROWS[k][0]} | {ROWS[k][3]} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | "
                     f"{delta} | {r['trades']} | {r['regime_exits']} | {r['regime_exits_pnl_pct']:+.1f}% | "
                     f"{r['stops']} | {r['win_rate']}% | {r['worst_trade_pct']:+.1f}% | {r['sharpe_anual']} | "
                     f"{r['dsr']} | " + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "La peor operación y el resultado de las cerradas por régimen son sobre el capital del bloque. El capital "
          "diario está en el JSON. Un resultado pasado no promete uno futuro. El dinero real no cambia por este estudio."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS
    parser = argparse.ArgumentParser(description="Salida por régimen sobre la mesa (investigación)")
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
    (args.salida / f"salida_regimen_{stamp}.json").write_text(json.dumps(years, indent=1, default=str),
                                                              encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"salida_regimen_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
