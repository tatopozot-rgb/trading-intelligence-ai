"""
Does the desk's sentiment score predict anything? (leader, 2026-10-13), research only.

The desk's Sentiment rule refuses a trade when the mood, against the side, is at or below -0.5. The
research_mesa audit found it never fires. Here, with the same public data:

A. Desk entries, two years (2024-10 to 2026-10): every distinct setup of the live desk (mesa_r3 signal on
   5-minute bars), its mood as the desk computes it (funding + top traders; no Fear & Greed history) turned
   into a "lean" for the side (+ = the mood agrees with the trade), and the trade's forward 24 h return.
   Buckets by lean, per side; Spearman correlation; and the desk replayed with the threshold at -0.5,
   -0.3, -0.2, -0.1 and switched off, over the same 30-day blocks.
B. Long history, 2020 to now: the funding part of the mood (the only part with history before the
   top-trader archive), sampled once a day per coin, against the coin's forward 24 h return.

Setups one per symbol per 24 h at most, so forward windows do not overlap. Public data only.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats as st

from trading_intelligence.backtesting import research_carry as rc
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import two_way_backtest as tw
from trading_intelligence.live import desk as D

AHEAD = 288  # 24 h of 5-minute bars
EDGES = (-1.01, -0.5, -0.3, -0.1, 0.1, 0.3, 0.5, 1.01)
THRESHOLDS = (None, -0.5, -0.3, -0.2, -0.1)  # None: rule off
OUT_DIR = Path("docs/research/sentimiento")
YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-12", "2026-10-12"))


def bucket_label(i: int) -> str:
    lo, hi = max(-1.0, EDGES[i]), min(1.0, EDGES[i + 1])
    return f"{lo:+.1f} a {hi:+.1f}"


def setups(syms: dict[str, rm.Sym], lo: int, hi: int) -> list[dict]:
    """First bar of each run of a signal (same symbol and side), at most one per symbol per 24 h."""
    out = []
    for name, s in syms.items():
        prev_side, last_k = 0, -10**9
        for k in range(lo, min(hi, len(s.close) - AHEAD)):
            side = int(s.side[k])
            if side == 0 or math.isnan(s.close[k]) or math.isnan(s.stop[k]):
                prev_side = 0
                continue
            if side == prev_side or k - last_k < AHEAD:
                prev_side = side
                continue
            prev_side, last_k = side, k
            c1 = s.close[k + AHEAD]
            if math.isnan(c1):
                continue
            lean = float(s.mood[k]) if side > 0 else -float(s.mood[k])
            out.append({"symbol": name, "k": k, "side": side, "lean": lean,
                        "ret": side * (c1 / s.close[k] - 1) * 100})
    return out


def describe(rows: list[dict], key: str = "lean") -> dict:
    """Per bucket: n, mean, median, hit rate, t; overall Spearman."""
    vals = np.array([r[key] for r in rows], dtype=float)
    rets = np.array([r["ret"] for r in rows], dtype=float)
    buckets = []
    for i in range(len(EDGES) - 1):
        m = (vals > EDGES[i]) & (vals <= EDGES[i + 1])
        x = rets[m]
        t = float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else None
        buckets.append({"bucket": bucket_label(i), "n": int(m.sum()),
                        "mean_pct": round(float(x.mean()), 3) if len(x) else None,
                        "median_pct": round(float(np.median(x)), 3) if len(x) else None,
                        "hit_pct": round(float((x > 0).mean() * 100), 1) if len(x) else None,
                        "t": round(t, 2) if t is not None else None})
    rho, p = (st.spearmanr(vals, rets) if len(rows) > 10 and np.ptp(vals) > 0 else (float("nan"), float("nan")))
    return {"n": len(rows), "buckets": buckets, "spearman": None if math.isnan(rho) else round(float(rho), 3),
            "p_value": None if math.isnan(p) else round(float(p), 4),
            "mean_pct": round(float(rets.mean()), 3) if len(rets) else None}


# ---------------------------------------------------------------------------
# Threshold replay (desk replayed exactly, only the sentiment threshold changes)
# ---------------------------------------------------------------------------

SYMS: dict[str, rm.Sym] = {}


def _replay(task: tuple) -> tuple:
    th, lo, hi = task
    rules = D.DeskRules.load()
    on = frozenset(rm.RULES) if th is not None else frozenset(rm.RULES) - {"sentimiento"}
    if th is not None:
        rules = replace(rules, min_sentiment_against=th)
    rep = rm.replay(SYMS, lo, hi, rules_on=on, rules=rules)
    return th, lo, rm.stats(rep), rep.curve


def threshold_table(times: np.ndarray, workers: int) -> dict:
    bl = rm.blocks(len(times), tw.WARMUP)
    with Pool(max(1, workers)) as pool:
        out = pool.map(_replay, [(th, lo, hi) for th in THRESHOLDS for lo, hi in bl])
    res: dict[Any, dict] = {}
    for th, lo, s, curve in out:
        res.setdefault(th, {})[lo] = (s, curve)
    table = {}
    for th in THRESHOLDS:
        los = sorted(res[th])
        table["apagada" if th is None else f"{th:g}"] = rm.chain([res[th][lo][0] for lo in los],
                                                                  [res[th][lo][1] for lo in los])
    return table


# ---------------------------------------------------------------------------
# B. Long history: the funding part of the mood vs the next 24 h
# ---------------------------------------------------------------------------

def funding_rows(name: str, spot: pd.Series, fund: pd.Series) -> list[dict]:
    """One row per coin per day at 00:00 UTC: funding mood part (as the desk computes it) and next-24 h return."""
    if spot.empty or fund.empty:
        return []
    days = pd.date_range(spot.index[0].ceil("D"), spot.index[-1].floor("D") - pd.Timedelta(days=1), freq="D")
    s = spot.reindex(spot.index.union(days)).ffill()
    f_idx = pd.DatetimeIndex(fund.index)
    rows = []
    for d in days:
        j = int(f_idx.searchsorted(d, side="right")) - 1
        if j < 0 or (d - f_idx[j]) > pd.Timedelta(hours=9):
            continue
        rate = float(fund.iloc[j])
        p0, p1 = s.get(d), s.get(d + pd.Timedelta(days=1))
        if p0 is None or p1 is None or not (p0 > 0 and p1 > 0):
            continue
        mood_f = D.sentiment(rate, None, None).score  # 0.4 x clip(-rate / 0.1)
        rows.append({"symbol": name, "day": str(d.date()), "rate": rate, "lean": mood_f / 0.4,
                     "ret": (p1 / p0 - 1) * 100})
    return rows


def _load_history(args: tuple) -> tuple[str, list[dict], str]:
    sym, start_iso, end_iso = args
    start, end = datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso)
    try:
        spot = rc.fetch_spot_1h(sym, start, end)
    except Exception as error:  # noqa: BLE001
        return sym, [], f"sin datos ({type(error).__name__})"
    fund = tw.fetch_funding(sym, start, end)
    rows = funding_rows(sym, spot, fund)
    return sym, rows, f"{len(rows)} días con financiación"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def predictive(desc: dict) -> bool:
    return desc["p_value"] is not None and desc["p_value"] < 0.05 and (desc["spearman"] or 0) > 0


def verdict(res: dict) -> list[str]:
    years = res["years"]
    hits = [(y["label"], side) for y in years for side in ("BUY", "SELL") if predictive(y["by_side"][side])]
    agree = all(predictive(y["all"]) for y in years)
    lines = []
    if agree:
        lines.append("**El sentimiento predice algo:** correlación positiva y significativa (p < 0,05) entre el "
                     "acuerdo del sentimiento con la operación y su resultado a 24 h en los dos años.")
    else:
        lines.append("**El sentimiento no predice nada útil:** la correlación entre el acuerdo del sentimiento con la "
                     "operación y su resultado a 24 h no es positiva y significativa en los dos años"
                     + (f" (solo en: {', '.join(f'{a} {b}' for a, b in hits)})" if hits else "") + ".")
    best = {y["label"]: max(y["thresholds"].items(), key=lambda kv: kv[1]["net_dd"] or -99)[0] for y in years}
    lines.append("Mejor umbral por neto/caída en la mesa repetida: "
                 + "; ".join(f"{k}: {v}" for k, v in best.items()) + ".")
    h = res.get("history")
    if h:
        lines.append(f"Financiación sola, {h['desde']} a {h['hasta']} ({h['all']['n']} días-moneda): Spearman "
                     f"{h['all']['spearman']} (p {h['all']['p_value']}) entre el componente de financiación del sentimiento "
                     "y la subida de las 24 h siguientes.")
    return lines


def _table(desc: dict) -> list[str]:
    out = ["| Acuerdo (lean) | n | Media 24 h % | Mediana % | Acierto | t |", "|---|---|---|---|---|---|"]
    for b in desc["buckets"]:
        out.append(f"| {b['bucket']} | {b['n']} | {b['mean_pct']} | {b['median_pct']} | {b['hit_pct']} | {b['t']} |")
    out.append(f"\nSpearman {desc['spearman']} (p {desc['p_value']}), n {desc['n']}, media {desc['mean_pct']}%.")
    return out


def render(res: dict) -> str:
    L = ["# ¿Predice algo el sentimiento de la mesa?", "",
         "Investigación con datos públicos. El sentimiento de la mesa (`desk.sentiment`): financiación (40%) y top "
         "traders (40%); el Miedo y Codicia (20%) no tiene historia aquí. \"Acuerdo\" (lean) = el sentimiento con el "
         "signo de la operación: positivo si favorece al lado de la operación. Resultado = el movimiento a 24 h a "
         "favor de la operación (sin stops ni costes). Una configuración por moneda cada 24 h como máximo.", "",
         "## Veredicto", "", *verdict(res)]
    for y in res["years"]:
        L += ["", f"## A. Entradas de la mesa, {y['label']}", "", "### Todas", "", *_table(y["all"])]
        for side, name in (("BUY", "Largos"), ("SELL", "Cortos")):
            L += ["", f"### {name}", "", *_table(y["by_side"][side])]
        L += ["", "### La mesa repetida con otro umbral del Escéptico de sentimiento (bloques de 30 días encadenados)", "",
              "| Umbral | Neto % | Máx. caída | Neto/caída | Ops |", "|---|---|---|---|---|"]
        for th, s in y["thresholds"].items():
            L.append(f"| {th} | {s['net_pct']:+.1f}% | {s['max_dd_pct']}% | {s['net_dd']} | {s['trades']} |")
    h = res.get("history")
    if h:
        L += ["", f"## B. Financiación sola, {h['desde']} a {h['hasta']} (una fila por moneda y día, 00:00 UTC)", "",
              "\"Acuerdo\" = componente de financiación del sentimiento para un largo (financiación negativa = "
              "acuerdo positivo). Resultado = subida del spot en las 24 h siguientes.", "", *_table(h["all"])]
        L += ["", "| Año | n | Spearman | p |", "|---|---|---|---|"]
        for yr, d in h["by_year"].items():
            L.append(f"| {yr} | {d['n']} | {d['spearman']} | {d['p_value']} |")
    L += ["", "Advertencias: el resultado a 24 h no es el de la operación con stop y meta (eso está en la tabla de "
          "umbrales); los datos de top traders cubren solo los dos años de la parte A; el Miedo y Codicia no entra."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS
    parser = argparse.ArgumentParser(description="¿Predice algo el sentimiento? (investigación)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--historia-desde", default="2020-01-01")
    parser.add_argument("--sin-mesa", action="store_true", help="solo la parte B (rápida)")
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    res: dict[str, Any] = {"years": []}
    if not args.sin_mesa:
        for a, b in YEARS:
            end = datetime.fromisoformat(b).replace(tzinfo=timezone.utc)
            warm = datetime.fromisoformat(a).replace(tzinfo=timezone.utc) - timedelta(minutes=5 * tw.WARMUP)
            with Pool(max(1, args.workers)) as pool:
                loaded = pool.map(rm._load_symbol, [(s, warm.isoformat(), end.isoformat()) for s in args.simbolos])
            for sym, _, note, _ in loaded:
                print(f"{a}→{b} {sym}: {note}")
            times, SYMS = rm.align({s: x for s, x, _, _ in loaded if x is not None})
            rows = setups(SYMS, tw.WARMUP, len(times))
            res["years"].append({"label": f"{a} a {b}", "all": describe(rows),
                                 "by_side": {side: describe([r for r in rows if r["side"] == (1 if side == "BUY" else -1)])
                                             for side in ("BUY", "SELL")},
                                 "thresholds": threshold_table(times, args.workers)})
    start = datetime.fromisoformat(args.historia_desde).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    with Pool(max(1, args.workers)) as pool:
        hist = pool.map(_load_history, [(s, start.isoformat(), now.isoformat()) for s in args.simbolos])
    rows = [r for _, rr, _ in hist for r in rr]
    for sym, _, note in hist:
        print(f"historia {sym}: {note}")
    if rows:
        by_year = {}
        for yr in sorted({r["day"][:4] for r in rows}):
            by_year[yr] = describe([r for r in rows if r["day"].startswith(yr)])
        res["history"] = {"desde": min(r["day"] for r in rows), "hasta": max(r["day"] for r in rows),
                          "all": describe(rows), "by_year": by_year}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = now.date().isoformat()
    (args.salida / f"sentimiento_{stamp}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    report = render(res)
    (args.salida / f"sentimiento_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
