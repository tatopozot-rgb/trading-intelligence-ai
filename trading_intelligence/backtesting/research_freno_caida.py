"""
Drawdown brake on the current desk (leader, 2026-10-19), research only.

Preregistered in docs/research/freno_caida/PREREGISTRO.md before any run. The desk as in docs/research/real/ (regime
brake b, +-2 h event brake, Binance costs, 30-day blocks chained, 1,000 USDT) in 1x and 3x, with a brake that only
lowers risk: half the risk from a 10% drawdown off the highest bar-close equity, no new entries from 20%. A pause
lasts until the next block starts, where the peak becomes the capital of that moment (the leader's review); without
a pause there is no reset. Sensitivity: the pause never ends. References: the same desk without the brake.
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
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_real as rr
from trading_intelligence.backtesting import two_way_backtest as tw

YEARS = rr.YEARS
CAPITAL = 1000.0
DECISIVE_N = 280
BRAKE = (0.10, 0.20)
DESK = {"2024-10-12": 1.67, "2025-10-13": -0.21}
OUT_DIR = Path("docs/research/freno_caida")
# key: (label, sizing, brake, reset after a pause, kind)
ROWS = {"f1x": ("1x con freno por caída", rm.SIZINGS[0], True, True, "decisoria"),
        "f3x": ("3x con freno por caída", rm.SIZINGS[4], True, True, "decisoria"),
        "f1x_fija": ("1x, pausa sin reinicio", rm.SIZINGS[0], True, False, "sensibilidad"),
        "f3x_fija": ("3x, pausa sin reinicio", rm.SIZINGS[4], True, False, "sensibilidad"),
        "ref1x": ("1x sin freno (referencia)", rm.SIZINGS[0], False, True, "referencia"),
        "ref3x": ("3x sin freno (referencia)", rm.SIZINGS[4], False, True, "referencia")}
REFERENCE = {"f1x": "ref1x", "f3x": "ref3x", "f1x_fija": "ref1x", "f3x_fija": "ref3x"}

SYMS: dict[str, Any] = {}
REGIME: dict[str, np.ndarray] = {}
EVENTS: dict[str, np.ndarray] = {}


def run_chained(syms: dict, bounds: list[tuple[int, int]], capital: float, sizing: rm.Sizing, brake: bool,
                reset: bool, allow: Optional[dict] = None, entry_allow: Optional[dict] = None,
                replay: Any = None) -> dict:
    """research_real.run_chained with the sizing and the brake; the peak and a pause carry over between blocks."""
    replay = replay or rm.replay
    equity: list[float] = []
    trades: list[dict] = []
    starts: list[float] = []
    level, peak, paused = capital, capital, False
    pauses = halved = 0
    for lo, hi in bounds:
        if paused and reset:
            peak, paused = level, False
        starts.append(level)
        rep = replay(syms, lo, hi, sizing=sizing, capital=level, allow=allow, entry_allow=entry_allow,
                     dd_brake=BRAKE if brake else None, peak=peak, paused=paused)
        end = level + sum(t["pnl"] for t in rep.trades)
        curve = list(rep.curve) or [level]
        curve += [curve[-1]] * (hi - lo - len(curve))
        curve[-1] = end
        equity.extend(curve)
        trades.extend({**t, "block_capital": level} for t in rep.trades)
        pauses += int(rep.paused and not paused)
        halved += rep.halved
        peak, paused, level = max(rep.peak, end), rep.paused, end
    return {"equity": equity, "trades": trades, "starts": starts, "pauses": pauses, "halved": halved}


def summarize(run: dict, times: np.ndarray, first: int, n_decisive: int) -> dict:
    out = rr.summarize(run, times, first, CAPITAL, n_decisive)
    out.update(pauses=run["pauses"], halved=run["halved"])
    return out


def _row(task: tuple) -> tuple:
    key, bounds = task
    _, sizing, brake, reset, _ = ROWS[key]
    return key, run_chained(SYMS, bounds, CAPITAL, sizing, brake, reset, allow=REGIME, entry_allow=EVENTS)


def evaluate(times: np.ndarray, workers: int, n_decisive: int) -> dict:
    bounds = rm.blocks(len(times), tw.WARMUP)
    first = bounds[0][0]
    with Pool(max(1, min(workers, len(ROWS)))) as pool:
        out = pool.map(_row, [(k, bounds) for k in ROWS])
    return {k: summarize(run, times, first, n_decisive) for k, run in out}


def build_masks(times: np.ndarray, extras: dict[str, dict], btc_d1: Any) -> None:
    global REGIME, EVENTS
    REGIME = rm.gates(times, list(SYMS), btc_d1, {s: x["h4"] for s, x in extras.items()})["b"]
    events = np.where(rm.near_event(times, rm.macro_events(), rr.EVENT_HOURS), 0, rm.BOTH).astype(np.int8)
    EVENTS = {name: events for name in SYMS}


def passes(years: list[dict], key: str) -> bool:
    beats = all((y["rows"][key]["net_dd"] or -99) > y["desk"] for y in years)
    return beats and years[-1]["rows"][key]["dsr"] >= rd.PASS_DSR


def render(years: list[dict], n: int) -> str:
    L = ["# Freno por caída de la cuenta sobre la mesa actual", "",
         "Preregistro: `docs/research/freno_caida/PREREGISTRO.md`, escrito antes de correr. La mesa con freno de "
         "régimen b y de eventos ±2 h, costos de Binance Futuros (0,05% por lado, 0,02% de deslizamiento, "
         "financiación real) y mínimos por orden; bloques de 30 días encadenados, 1.000 USDT. Freno: riesgo a la mitad "
         "desde 10% de caída, sin entradas nuevas desde 20%; la pausa dura hasta el bloque siguiente. Sharpe "
         f"deflactado con N = {n} decisorias.", "", "## Veredicto", ""]
    for k, v in ROWS.items():
        if v[4] != "decisoria":
            continue
        ref = REFERENCE[k]
        L.append(f"- **{v[0]}: {'pasa' if passes(years, k) else 'no pasa'}.** Neto/caída "
                 + " ; ".join(str(y["rows"][k]["net_dd"]) for y in years)
                 + f" contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 {years[-1]['rows'][k]['dsr']} "
                 f"(listón {rd.PASS_DSR}). Sin freno: neto/caída "
                 + " ; ".join(str(y["rows"][ref]["net_dd"]) for y in years) + ".")
    for y in years:
        L += ["", f"## {y['label']}", "",
              "| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin freno (neto, caída) | Ops | "
              "Entradas a medio riesgo | Pausas | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | "
              "Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            ref = y["rows"].get(REFERENCE.get(k, ""))
            delta = (f"{r['net_pct'] - ref['net_pct']:+.1f} pts, {r['max_dd_pct'] - ref['max_dd_pct']:+.1f} pts"
                     if ref else "—")
            L.append(f"| {ROWS[k][0]} | {ROWS[k][4]} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | "
                     f"{delta} | {r['trades']} | {r['halved']} | {r['pauses']} | {r['win_rate']}% | "
                     f"{r['worst_trade_pct']:+.1f}% | {r['sharpe_anual']} | {r['dsr']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "La peor operación es sobre el capital del bloque. El capital diario está en el JSON. Un resultado pasado "
          "no promete uno futuro. El dinero real no cambia por este estudio."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS
    parser = argparse.ArgumentParser(description="Freno por caída de la cuenta sobre la mesa (investigación)")
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
    (args.salida / f"freno_caida_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"freno_caida_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
