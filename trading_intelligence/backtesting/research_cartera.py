"""
Portfolio: the practice desk (mesa_r3 + regime brake b + event brake) plus EWMAC, research only.
Preregistered in docs/research/cartera/PREREGISTRO.md before any run.

The desk is replayed on 5-minute bars in its 30-day sessions (each starts with its own capital) exactly as
research_saturado's "frenos / base" setup; each session becomes a daily curve (equity at each UTC day close over
the session's starting equity, flat after an early stop) and the sessions are chained. EWMAC is the preregistered
rule's continuous daily equity over the same 360 days. At each session start the portfolio is split again with
fixed weights (50/50 and 70/30 desk/EWMAC), paying 0.07% on what moves between legs. Public data only.
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

from trading_intelligence.backtesting import research_ewmac as ew
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_saturado as rsat
from trading_intelligence.backtesting import two_way_backtest as tw

YEARS = rsat.YEARS
WEIGHTS = (0.5, 0.7)  # desk share
MOVE_COST = tw.FEE + 0.0002
MAX_DD = 35.0
BARS_PER_DAY = 288
OUT_DIR = Path("docs/research/cartera")


def session_daily(curve: list[float], days: int, capital: float = rm.CAPITAL) -> np.ndarray:
    """Equity at each day's close over the session's capital; flat after an early end."""
    c = np.asarray(curve if curve else [capital], dtype=float)
    out = np.empty(days)
    for d in range(days):
        k = (d + 1) * BARS_PER_DAY - 1
        out[d] = c[min(k, len(c) - 1)]
    return out / capital


def portfolio(desk: list[np.ndarray], ewmac: np.ndarray, w: float) -> tuple[np.ndarray, float]:
    """Daily portfolio value (starts at 1). `desk`: one relative curve per session; `ewmac`: daily equity at each
    close over the same days (its base before day 0 is ew.CAPITAL). Returns the curve and the total rebalancing
    cost (fraction of the starting value)."""
    value, out, cost, day = 1.0, [], 0.0, 0
    leg_d = w
    for j, sess in enumerate(desk):
        n = len(sess)
        if j > 0:  # back to the fixed weights; what moves between legs pays fees + slippage
            c = abs(leg_d - w * value) * MOVE_COST
            value -= c
            cost += c
        leg_d, leg_e = w * value, (1 - w) * value
        e0 = ewmac[day - 1] if day > 0 else ew.CAPITAL
        for i in range(n):
            out.append(leg_d * sess[i] + leg_e * ewmac[day + i] / e0)
        leg_d, leg_e = leg_d * sess[-1], leg_e * ewmac[day + n - 1] / e0
        value = leg_d + leg_e
        day += n
    return np.array(out), cost


def chained(desk: list[np.ndarray]) -> np.ndarray:
    level, out = 1.0, []
    for s in desk:
        out.extend((level * s).tolist())
        level *= s[-1]
    return np.array(out)


def curve_stats(curve: np.ndarray) -> dict:
    e = np.r_[1.0, curve]
    peak = np.maximum.accumulate(e)
    dd = float(((peak - e) / peak).max() * 100)
    net = (e[-1] - 1) * 100
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None}


def quarters(curve: np.ndarray, days_per_q: int = 90) -> list[float]:
    e = np.r_[1.0, curve]
    out = []
    for q in range(len(curve) // days_per_q):
        a, b = q * days_per_q, (q + 1) * days_per_q
        out.append(round((e[b] / e[a] - 1) * 100, 2))
    return out


def judge(year: dict) -> dict:
    desk = year["rows"]["mesa de práctica"]
    out = {}
    for w in WEIGHTS:
        r = year["rows"][f"cartera {int(w * 100)}/{int(round((1 - w) * 100))}"]
        out[f"{int(w * 100)}/{int(round((1 - w) * 100))}"] = {
            "beats_desk": (r["net_dd"] or -99) > (desk["net_dd"] or -99), "dd_ok": r["max_dd_pct"] < MAX_DD}
    return out


def verdict(years: list[dict]) -> list[str]:
    lines = []
    for w in WEIGHTS:
        key = f"{int(w * 100)}/{int(round((1 - w) * 100))}"
        ok = all(y["judge"][key]["beats_desk"] and y["judge"][key]["dd_ok"] for y in years)
        detail = "; ".join(f"{y['label']}: neto/caída {y['rows'][f'cartera {key}']['net_dd']} contra "
                           f"{y['rows']['mesa de práctica']['net_dd']}, caída {y['rows'][f'cartera {key}']['max_dd_pct']}%"
                           for y in years)
        lines.append(f"- **Cartera {key} (mesa/EWMAC): {'pasa' if ok else 'no pasa'}** — {detail}.")
    return lines


def render(years: list[dict]) -> str:
    L = ["# Cartera: mesa de práctica + EWMAC", "",
         "Preregistrada en `docs/research/cartera/PREREGISTRO.md` antes de correr. Mesa de práctica = `mesa_r3` con "
         "freno de régimen b y freno de eventos (±2 h), sin inclinación del tamaño por sentimiento, en sesiones de 30 "
         "días: cada sesión se vuelve una curva diaria (capital al cierre de cada día UTC sobre el capital de inicio "
         "de la sesión) y las sesiones se encadenan. EWMAC = la regla preregistrada, curva diaria continua en los "
         "mismos 360 días. Rebalanceo al inicio de cada sesión, 0,07% sobre lo que se mueve. Pasa si, en los dos "
         "años, el neto/caída supera a la mesa sola y la caída máxima queda bajo 35%.", "", "## Veredicto", "",
         *verdict(years)]
    for y in years:
        L += ["", f"## {y['label']}", "", "| Curva | Neto % | Máx. caída | Neto/caída | Trimestres (neto %) |",
              "|---|---|---|---|---|"]
        for name, r in y["rows"].items():
            L.append(f"| {name} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
        L.append(f"\nBTC comprar y mantener: {y['btc_pct']}%. Correlación diaria mesa/EWMAC: {y['corr']}. "
                 f"Costes de rebalanceo: " + ", ".join(f"{k} {v}%" for k, v in y["rebalance_cost_pct"].items()) + ".")
    L += ["", "Advertencias: Spot como aproximación del perpetuo; la mesa empieza cada sesión con su capital y EWMAC "
          "corre continuo, así que la cartera se rehace cada 30 días; sin costes de mover dinero entre cuentas más "
          "allá del 0,07%. Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def desk_sessions(a: str, b: str, symbols: list[str], workers: int) -> tuple[list[np.ndarray], list[dict]]:
    end = datetime.fromisoformat(b).replace(tzinfo=timezone.utc)
    warm = datetime.fromisoformat(a).replace(tzinfo=timezone.utc) - timedelta(minutes=5 * tw.WARMUP)
    with Pool(max(1, workers)) as pool:
        loaded = pool.map(rm._load_symbol, [(s, warm.isoformat(), end.isoformat()) for s in symbols])
    for sym, _, note, _ in loaded:
        print(f"{a}→{b} {sym}: {note}")
    extras = {s: x for s, a_, _, x in loaded if a_ is not None}
    times, rsat.SYMS = rm.align({s: x for s, x, _, _ in loaded if x is not None})
    rsat.build_masks(times, extras, extras["BTCUSDT"]["d1"])
    bl = rm.blocks(len(times), tw.WARMUP)
    with Pool(max(1, workers)) as pool:
        out = pool.map(rsat._block, [("frenos", "base", lo, hi) for lo, hi in bl])
    out.sort(key=lambda x: x[2])
    return [session_daily(curve, rm.BLOCK_DAYS) for *_, curve in out], [st for _, _, _, st, _ in out]


def year(a: str, d: ew.Data, desk: list[np.ndarray]) -> dict:
    start = int(d.days.searchsorted(pd.Timestamp(a, tz="UTC")))
    n = sum(len(s) for s in desk)
    r = ew.simulate(d, start, start + n)
    eq = r.equity
    rows: dict[str, Any] = {}
    dc = chained(desk)
    rows["mesa de práctica"] = {**curve_stats(dc), "quarters": quarters(dc)}
    ec = eq / ew.CAPITAL
    rows["EWMAC"] = {**curve_stats(ec), "quarters": quarters(ec)}
    costs = {}
    for w in WEIGHTS:
        pc, cost = portfolio(desk, eq, w)
        key = f"{int(w * 100)}/{int(round((1 - w) * 100))}"
        rows[f"cartera {key}"] = {**curve_stats(pc), "quarters": quarters(pc)}
        costs[key] = round(cost * 100, 3)
    btc = d.names.index("BTCUSDT")
    bh = round((d.close[btc, start + n - 1] / d.close[btc, start - 1] - 1) * 100, 2)
    corr = float(np.corrcoef(np.diff(np.r_[1.0, dc]) / np.r_[1.0, dc][:-1], np.diff(np.r_[1.0, ec]) / np.r_[1.0, ec][:-1])[0, 1])
    y = {"label": f"{a} → {str(d.days[start + n - 1].date())}", "rows": rows, "btc_pct": bh, "corr": round(corr, 2),
         "rebalance_cost_pct": costs}
    y["judge"] = judge(y)
    return y


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cartera mesa de práctica + EWMAC (investigación preregistrada)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(ew.WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=1)
    with Pool(max(1, args.workers)) as pool:
        d = ew.build(pool.map(ew._load, [(s, start.isoformat(), end.isoformat()) for s in args.simbolos]))
    years = []
    for a, b in YEARS:
        desk, _ = desk_sessions(a, b, args.simbolos, args.workers)
        years.append(year(a, d, desk))
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"cartera_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years)
    (args.salida / f"cartera_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
