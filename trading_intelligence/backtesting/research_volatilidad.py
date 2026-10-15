"""
"Volatility brake" for the desk (theory lesson 5, leader 2026-10-15), research only. Preregistered in
docs/research/volatilidad/PREREGISTRO.md before any run.

BTC's 7-day realized volatility (std of the last 7 closed daily log returns, known from the next day on) against
the 80th / 90th / 95th percentile of the same measure over the prior 365 days (rolling, the day itself excluded):
above it, the desk opens nothing new (open positions keep their stops). No data or no 365-day history: no brake.
The desk is replayed as in research_saturado, in two setups: the practice desk (regime b + events) and events only.
V90 in setup 1 decides. Public data only: no account, no key, no orders. Nothing here changes config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_saturado as rsat
from trading_intelligence.backtesting import two_way_backtest as tw

WINDOW, HISTORY = 7, 365
LEVELS = (80, 90, 95)
DECIDES = "V90"
FILTERS = ("base", *(f"V{q}" for q in LEVELS))
OUT_DIR = Path("docs/research/volatilidad")


def brake_days(btc_close: pd.Series, q: int) -> pd.Series:
    """Per UTC day D (index = day), True if the 7-day vol known on D is above the q-th percentile of the same
    measure over D-365..D-1. NaN-safe: unknown -> False."""
    lr = np.log(btc_close).diff()
    vol = lr.rolling(WINDOW, min_periods=WINDOW).std()  # at day j: uses closes up to j's close
    known = vol.shift(1)  # usable during day j+1
    thr = known.shift(1).rolling(HISTORY, min_periods=HISTORY).quantile(q / 100)
    return (known > thr).fillna(False).astype(bool)


def bar_mask(times: np.ndarray, days: pd.Series) -> np.ndarray:
    """Brake per 5-minute bar from the per-day flags (False where the day is unknown)."""
    day = pd.DatetimeIndex(pd.to_datetime(times, utc=True)).floor("D")
    return days.reindex(day).fillna(False).astype(bool).values


def add_masks(times: np.ndarray, btc_close: pd.Series) -> dict[str, float]:
    """Entry masks for V80/V90/V95 on top of each setup's event brake; returns the % of bars braked."""
    share = {}
    for q in LEVELS:
        blocked = bar_mask(times, brake_days(btc_close, q))
        share[f"V{q}"] = round(float(blocked.mean() * 100), 1)
        for s in rsat.SETUPS:
            base = rsat.ENTRY[(s, "base")]
            rsat.ENTRY[(s, f"V{q}")] = {n: np.where(blocked, 0, base[n]).astype(np.int8) for n in rsat.SYMS}
    return share


def verdict(years: list[dict]) -> list[str]:
    ok = all(rsat.helps(y["table"]["frenos"]["base"], y["table"]["frenos"][DECIDES]) for y in years)
    detail = "; ".join(f"{y['label']}: {y['table']['frenos'][DECIDES]['net_dd']} contra {y['table']['frenos']['base']['net_dd']}"
                       f" ({y['table']['frenos'][DECIDES]['trades']} de {y['table']['frenos']['base']['trades']} operaciones)"
                       for y in years)
    return [f"**El freno de volatilidad (V90) {'ayuda' if ok else 'no ayuda'}** en la mesa de práctica — neto/caída {detail}."]


def render(years: list[dict]) -> str:
    L = ["# \"Freno de volatilidad\" para la mesa", "",
         "Preregistrado en `docs/research/volatilidad/PREREGISTRO.md` antes de correr. Volatilidad de 7 días de BTC "
         "(desviación de los últimos 7 rendimientos logarítmicos diarios cerrados) contra su percentil 80 / 90 / 95 de "
         "los 365 días anteriores; por encima, sin entradas nuevas. La mesa (`mesa_r3`, reglas de hoy) repetida en "
         "sesiones de 30 días con 1.000 USDT. Decide V90 en la mesa de práctica (régimen b + eventos): ayuda si mejora "
         "el neto/caída de su base en los dos años sin quitar más de la mitad de las operaciones.", "",
         "## Veredicto", "", *verdict(years)]
    for y in years:
        L.append("")
        L.append(f"Tiempo con el freno puesto, {y['label']}: " + ", ".join(f"{k} {v}%" for k, v in y["braked_pct"].items()) + ".")
        for s, title in rsat.SETUPS.items():
            L += ["", f"## {y['label']} — {title}", "",
                  "| Filtro | Neto % | Máx. caída | Neto/caída | Ops | Trimestres (neto %) |", "|---|---|---|---|---|---|"]
            for f in FILTERS:
                r = y["table"][s][f]
                L.append(f"| {f} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | "
                         + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Advertencias: precio Spot como aproximación del perpetuo; la volatilidad realizada no es la implícita "
          "(DVOL) del que habla la teoría; el freno solo impide entradas. Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def btc_daily(start: datetime, end: datetime) -> pd.Series:
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    k = rdv.fetch_klines("BTCUSDT", "1d", start, end)
    return pd.Series(k["close"].values, index=pd.DatetimeIndex(k.index), dtype=float)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Freno de volatilidad (investigación preregistrada)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    first = datetime.fromisoformat(rsat.YEARS[0][0]).replace(tzinfo=timezone.utc)
    last = datetime.fromisoformat(rsat.YEARS[-1][1]).replace(tzinfo=timezone.utc)
    btc = btc_daily(first - timedelta(days=HISTORY + 30), last + timedelta(days=1))
    years = []
    for a, b in rsat.YEARS:
        end = datetime.fromisoformat(b).replace(tzinfo=timezone.utc)
        warm = datetime.fromisoformat(a).replace(tzinfo=timezone.utc) - timedelta(minutes=5 * tw.WARMUP)
        with Pool(max(1, args.workers)) as pool:
            loaded = pool.map(rm._load_symbol, [(s, warm.isoformat(), end.isoformat()) for s in args.simbolos])
        for sym, _, note, _ in loaded:
            print(f"{a}→{b} {sym}: {note}")
        extras = {s: x for s, a_, _, x in loaded if a_ is not None}
        times, rsat.SYMS = rm.align({s: x for s, x, _, _ in loaded if x is not None})
        rsat.build_masks(times, extras, extras["BTCUSDT"]["d1"])
        share = add_masks(times, btc)
        years.append({"label": f"{a} → {b}", "braked_pct": share, "table": rsat.evaluate(times, args.workers, FILTERS)})
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"volatilidad_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years)
    (args.salida / f"volatilidad_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
