"""
Half the risk when the US 10-year yield and the dollar are both above their 50-day means (leader, 2026-10-21),
research only.

Preregistered in docs/research/riesgo_macro/PREREGISTRO.md before any run. The desk as in
docs/research/salida_regimen/ (regime b with exit, +-2 h events, Binance costs, 30-day blocks chained, 1,000 USDT)
in 1x and 3x; while DGS10 and the DXY are both above the mean of their last 50 readings, new entries take half the
risk. Each reading is used only from the moment it was public (DGS10 from D+2, Yahoo from D+1, DTWEXBGS from D+8).
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

from trading_intelligence.backtesting import research_deflactado as rd
from trading_intelligence.backtesting import research_freno_caida as rf
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_opciones_xsp as ro
from trading_intelligence.backtesting import research_real as rr
from trading_intelligence.backtesting import two_way_backtest as tw

YEARS = rr.YEARS
CAPITAL = 1000.0
DECISIVE_N = 296
DESK = rf.DESK
SMA = 50
OUT_DIR = Path("docs/research/riesgo_macro")
# (name, kind, url, days until the reading is public)
BOND = (("FRED DGS10", "csv", ro.FRED.format("DGS10"), 2), ("Yahoo ^TNX", "yahoo", ro.YAHOO.format("%5ETNX"), 1))
DOLLAR = (("Yahoo DX-Y.NYB", "yahoo", ro.YAHOO.format("DX-Y.NYB"), 1),
          ("FRED DTWEXBGS", "csv", ro.FRED.format("DTWEXBGS"), 8))
# key: (label, sizing, macro rule on, kind)
ROWS = {"m1x": ("1x con riesgo a la mitad por bono y dólar", rm.SIZINGS[0], True, "decisoria"),
        "m3x": ("3x con riesgo a la mitad por bono y dólar", rm.SIZINGS[4], True, "decisoria"),
        "ref1x": ("1x sin la regla (referencia)", rm.SIZINGS[0], False, "referencia"),
        "ref3x": ("3x sin la regla (referencia)", rm.SIZINGS[4], False, "referencia")}
REFERENCE = {"m1x": "ref1x", "m3x": "ref3x"}

SYMS: dict[str, Any] = {}
REGIME: dict[str, np.ndarray] = {}
EVENTS: dict[str, np.ndarray] = {}
SCALE: Optional[np.ndarray] = None


def fetch(sources: tuple) -> tuple[pd.Series, str, int]:
    for name, kind, url, lag in sources:
        try:
            text = ro._get(url)
            out = ro.parse_yahoo(text) if kind == "yahoo" else ro.parse_close(text)
            if len(out) > 300:
                print(f"datos: {name}")
                return out, name, lag
        except Exception as exc:  # noqa: BLE001 - next source
            print(f"fuente sin respuesta: {name} ({type(exc).__name__})")
    raise RuntimeError("no data source answered")


def above(series: pd.Series, lag_days: int) -> pd.Series:
    """True/False per reading (above the mean of the last 50 readings), indexed by when it became public."""
    s = series.dropna().astype(float)
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    up = (s > s.rolling(SMA).mean()).where(s.rolling(SMA).count() >= SMA)
    up.index = (up.index + pd.Timedelta(days=lag_days)).tz_localize("UTC")
    return up.dropna().astype(bool)


def tight_at(times: np.ndarray, bond_up: pd.Series, dollar_up: pd.Series) -> np.ndarray:
    """Per 5-minute bar: both last public readings are above their means (unknown counts as not tight)."""
    t = pd.DatetimeIndex(pd.to_datetime(times, utc=True))

    def asof(up: pd.Series) -> np.ndarray:
        avail = up.index.as_unit("ns").asi8
        j = np.searchsorted(avail, t.as_unit("ns").asi8, side="right") - 1
        vals = up.to_numpy(bool)
        return np.where(j >= 0, vals[np.clip(j, 0, None)], False)

    return asof(bond_up) & asof(dollar_up)


def _row(task: tuple) -> tuple:
    key, bounds = task
    _, sizing, on, _ = ROWS[key]
    scale = np.where(SCALE, 0.5, 1.0) if on and SCALE is not None else None
    return key, rf.run_chained(SYMS, bounds, CAPITAL, sizing, False, True, allow=REGIME, entry_allow=EVENTS,
                               risk_scale=scale)


def evaluate(times: np.ndarray, workers: int, n_decisive: int) -> dict:
    bounds = rm.blocks(len(times), tw.WARMUP)
    first = bounds[0][0]
    with Pool(max(1, min(workers, len(ROWS)))) as pool:
        out = pool.map(_row, [(k, bounds) for k in ROWS])
    rows: dict[str, Any] = {k: rr.summarize(o, times, first, CAPITAL, n_decisive) for k, o in out}
    assert SCALE is not None
    days = pd.DatetimeIndex(pd.to_datetime(times[first:], utc=True)).floor("D")
    rows["_tight_days"] = int(pd.Series(SCALE[first:], index=days).groupby(level=0).max().sum())
    rows["_days"] = int(days.nunique())
    return rows


def build_masks(times: np.ndarray, extras: dict[str, dict], btc_d1: Any) -> None:
    global REGIME, EVENTS
    REGIME = rm.gates(times, list(SYMS), btc_d1, {s: x["h4"] for s, x in extras.items()})["b"]
    events = np.where(rm.near_event(times, rm.macro_events(), rr.EVENT_HOURS), 0, rm.BOTH).astype(np.int8)
    EVENTS = {name: events for name in SYMS}


def passes(years: list[dict], key: str) -> bool:
    beats = all((y["rows"][key]["net_dd"] or -99) > y["desk"] for y in years)
    return beats and years[-1]["rows"][key]["dsr"] >= rd.PASS_DSR


def render(years: list[dict], n: int, sources: str) -> str:
    L = ["# Riesgo a la mitad cuando suben el bono a 10 años y el dólar", "",
         "Preregistro: `docs/research/riesgo_macro/PREREGISTRO.md`, escrito antes de correr. La mesa con régimen b "
         "(con salida) y eventos ±2 h, costos de Binance Futuros y mínimos por orden; bloques de 30 días encadenados, "
         "1.000 USDT. Mientras el bono y el dólar están los dos sobre su media de 50 datos, cada entrada nueva arriesga "
         f"la mitad. Fuentes: {sources}. Sharpe deflactado con N = {n} decisorias.", "", "## Veredicto", ""]
    for k, v in ROWS.items():
        if v[3] != "decisoria":
            continue
        ref = REFERENCE[k]
        L.append(f"- **{v[0]}: {'pasa' if passes(years, k) else 'no pasa'}.** Neto/caída "
                 + " ; ".join(str(y["rows"][k]["net_dd"]) for y in years)
                 + f" contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 {years[-1]['rows'][k]['dsr']} "
                 f"(listón {rd.PASS_DSR}). Sin la regla: neto/caída "
                 + " ; ".join(str(y["rows"][ref]["net_dd"]) for y in years) + ".")
    for y in years:
        L += ["", f"## {y['label']} (regla activa {y['rows']['_tight_days']} de {y['rows']['_days']} días)", "",
              "| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin la regla (neto, caída) | Ops | "
              "Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            if k.startswith("_"):
                continue
            ref = y["rows"].get(REFERENCE.get(k, ""))
            delta = (f"{r['net_pct'] - ref['net_pct']:+.1f} pts, {r['max_dd_pct'] - ref['max_dd_pct']:+.1f} pts"
                     if ref else "—")
            L.append(f"| {ROWS[k][0]} | {ROWS[k][3]} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | "
                     f"{delta} | {r['trades']} | {r['win_rate']}% | {r['worst_trade_pct']:+.1f}% | "
                     f"{r['sharpe_anual']} | {r['dsr']} | " + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "La peor operación es sobre el capital del bloque. El capital diario está en el JSON. Un resultado pasado "
          "no promete uno futuro. El dinero real no cambia por este estudio."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS, SCALE
    parser = argparse.ArgumentParser(description="Riesgo a la mitad por bono y dólar sobre la mesa (investigación)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    bond, bond_name, bond_lag = fetch(BOND)
    dollar, dollar_name, dollar_lag = fetch(DOLLAR)
    bond_up, dollar_up = above(bond, bond_lag), above(dollar, dollar_lag)
    sources = f"bono {bond_name} (desde D+{bond_lag}), dólar {dollar_name} (desde D+{dollar_lag})"
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
        SCALE = tight_at(times, bond_up, dollar_up)
        years.append({"label": f"{a} → {b}", "desk": DESK[a], "rows": evaluate(times, args.workers, args.decisorias)})
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"riesgo_macro_{stamp}.json").write_text(json.dumps({"sources": sources, "years": years},
                                                                       indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias, sources)
    (args.salida / f"riesgo_macro_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
