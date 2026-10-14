"""
"Crowded side" filter for the desk (leader, 2026-10-14), research only. Preregistered in
docs/research/saturado/PREREGISTRO.md before any run.

The desk (mesa_r3) is replayed exactly as research_mesa does it, over the two years of docs/research/mesa/, with
the practice brakes (BTC 50-day regime b, which closes positions, and the +-2 h FOMC/CPI event brake), then with
each candidate filter on top (entries only):
  L5 / L10 / L15: no new longs while open interest rose more than 5 / 10 / 15% in 24 h with price flat (+-2%);
  S12 / S24: no new shorts for 12 / 24 h after a long cascade (open interest -5% or more and price -3% or more
  in 24 h).
Under regime b the desk takes no shorts, so S12 / S24 are also measured with the event brake only.
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
import pandas as pd

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import two_way_backtest as tw

YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
EVENT_HOURS = 2  # as config/eventos.json
FLAT = 0.02
CASCADE_OI, CASCADE_PX = -0.05, -0.03
LONG_X = (5, 10, 15)
SHORT_N = (12, 24)
FILTERS = ("base", *(f"L{x}" for x in LONG_X), *(f"S{n}" for n in SHORT_N))
SETUPS = {"frenos": "régimen b + eventos (la mesa de práctica)", "eventos": "solo freno de eventos"}
OUT_DIR = Path("docs/research/saturado")
H = 3_600_000_000_000


def crowded_masks(close: np.ndarray, oi: np.ndarray, times: np.ndarray) -> dict[str, np.ndarray]:
    """Per filter, the allowed sides per bar (rm.LONG / rm.SHORT bits). Unknown open interest = no filter."""
    c = pd.Series(close).ffill().values
    o = pd.Series(oi).ffill().values
    oi24, px24 = rm.change_over(o, times, 24), rm.change_over(c, times, 24)
    known = np.isfinite(oi24) & np.isfinite(px24)
    out: dict[str, np.ndarray] = {}
    for x in LONG_X:
        crowded = known & (oi24 > x / 100) & (np.abs(px24) <= FLAT)
        out[f"L{x}"] = np.where(crowded, rm.SHORT, rm.BOTH).astype(np.int8)
    cascade = known & (oi24 <= CASCADE_OI) & (px24 <= CASCADE_PX)
    last = np.maximum.accumulate(np.where(cascade, times, np.iinfo(np.int64).min))
    for n in SHORT_N:
        recent = last >= times - n * H
        out[f"S{n}"] = np.where(recent, rm.LONG, rm.BOTH).astype(np.int8)
    return out


SYMS: dict[str, rm.Sym] = {}
REGIME: dict[str, np.ndarray] = {}
ENTRY: dict[tuple[str, str], dict[str, np.ndarray]] = {}  # (setup, filter) -> per symbol


def _block(task: tuple) -> tuple:
    setup, flt, lo, hi = task
    rep = rm.replay(SYMS, lo, hi, allow=REGIME if setup == "frenos" else None, entry_allow=ENTRY[(setup, flt)])
    return setup, flt, lo, rm.stats(rep), rep.curve


def evaluate(times: np.ndarray, workers: int) -> dict:
    bl = rm.blocks(len(times), tw.WARMUP)
    tasks = [(s, f, lo, hi) for s in SETUPS for f in FILTERS for lo, hi in bl]
    with Pool(max(1, workers)) as pool:
        out = pool.map(_block, tasks)
    res: dict[tuple[str, str], dict[int, tuple]] = {}
    for s, f, lo, st, curve in out:
        res.setdefault((s, f), {})[lo] = (st, curve)
    table: dict[str, dict[str, Any]] = {}
    for s in SETUPS:
        table[s] = {}
        for f in FILTERS:
            los = sorted(res[(s, f)])
            year = rm.chain([res[(s, f)][lo][0] for lo in los], [res[(s, f)][lo][1] for lo in los])
            quarters = []
            for q in range(0, len(los) - len(los) % 3, 3):
                ql = los[q:q + 3]
                quarters.append(rm.chain([res[(s, f)][lo][0] for lo in ql], [res[(s, f)][lo][1] for lo in ql])["net_pct"])
            table[s][f] = {**year, "quarters": quarters,
                           "long_n": sum(res[(s, f)][lo][0]["long_n"] for lo in los),
                           "short_n": sum(res[(s, f)][lo][0]["short_n"] for lo in los)}
    return table


def build_masks(times: np.ndarray, extras: dict[str, dict], btc_d1: Any) -> None:
    global REGIME
    REGIME = rm.gates(times, list(SYMS), btc_d1, {s: x["h4"] for s, x in extras.items()})["b"]
    events = np.where(rm.near_event(times, rm.macro_events(), EVENT_HOURS), 0, rm.BOTH).astype(np.int8)
    for s in SETUPS:
        ENTRY[(s, "base")] = {name: events for name in SYMS}
    per_sym: dict[str, dict[str, np.ndarray]] = {}
    for name, sym in SYMS.items():
        t, v = extras[name]["oi"]
        oi = np.full(len(times), np.nan)
        oi[np.searchsorted(times, t)] = v
        per_sym[name] = crowded_masks(sym.close, oi, times)
    for s in SETUPS:
        for f in FILTERS[1:]:
            ENTRY[(s, f)] = {name: (events & per_sym[name][f]).astype(np.int8) for name in SYMS}


def helps(base: dict, cand: dict) -> bool:
    return (cand["net_dd"] or -99) > (base["net_dd"] or -99) and cand["trades"] >= 0.5 * base["trades"]


def verdict(years: list[dict]) -> list[str]:
    lines = []
    for f in FILTERS[1:]:
        setup = "eventos" if f.startswith("S") else "frenos"
        ok = all(helps(y["table"][setup]["base"], y["table"][setup][f]) for y in years)
        detail = "; ".join(f"{y['label']}: {y['table'][setup][f]['net_dd']} contra {y['table'][setup]['base']['net_dd']}"
                           for y in years)
        lines.append(f"- **{f}** ({SETUPS[setup]}): {'ayuda' if ok else 'no ayuda'} — neto/caída {detail}.")
    return lines


def render(years: list[dict]) -> str:
    L = ["# Filtro de \"lado saturado\" para la mesa", "",
         "Preregistrado en `docs/research/saturado/PREREGISTRO.md` antes de correr. La mesa (`mesa_r3`) repetida "
         "exactamente como en `research_mesa`, velas de 5 minutos, costes y financiación reales, bloques de 30 días "
         "con 1.000 USDT. Interés abierto de los archivos `metrics` de data.binance.vision. Un filtro **ayuda** si "
         "mejora el neto/caída de su base en los dos años sin quitar más de la mitad de las operaciones. L5/L10/L15 "
         "se juzgan con los frenos de la práctica; S12/S24 con solo el freno de eventos (con el régimen b la mesa no "
         "abre cortos).", "", "## Veredicto", "", *verdict(years)]
    for y in years:
        for s, title in SETUPS.items():
            L += ["", f"## {y['label']} — {title}", "",
                  "| Filtro | Neto % | Máx. caída | Neto/caída | Ops | Largos | Cortos | Trimestres (neto %) |",
                  "|---|---|---|---|---|---|---|---|"]
            for f in FILTERS:
                r = y["table"][s][f]
                L.append(f"| {f} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | "
                         f"{r['long_n']} | {r['short_n']} | " + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Advertencias: precio Spot como aproximación del perpetuo; el freno de eventos usa las fechas FOMC/IPC "
          "de `research_mesa` con ±2 h; los filtros solo impiden entradas. Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS
    parser = argparse.ArgumentParser(description="Filtro de lado saturado (investigación preregistrada)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
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
        years.append({"label": f"{a} → {b}", "table": evaluate(times, args.workers)})
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"saturado_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years)
    (args.salida / f"saturado_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
