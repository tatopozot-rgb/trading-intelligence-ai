"""
Larry Connors' RSI-2 on the desk's 12 coins, research only.

Rules from docs/inteligencia/BOTS_PUBLICOS.md (2026-10-16), the rest preregistered in docs/research/rsi2/PREREGISTRO.md
before any run: daily UTC candles; long when the close is above its 200-day mean and Wilder's RSI(2) is below 10;
enter at the next open; exit at the open after the first close above the 5-day mean; no stop. At most 3 positions, a
third of the marked capital each, 1x; more signals than free slots: lowest RSI-2 first. Fees 0.05% and slippage 0.02%
per side, real funding for every UTC day held. Version A pure, version B with the desk brakes (regime b on the signal
day's BTC close; no entries on FOMC/CPI UTC days). Threshold 5 and the short mirror are sensitivity only.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_breakout as rb
from trading_intelligence.backtesting import two_way_backtest as tw

THRESHOLD, SENS_THRESHOLD = 10.0, 5.0
SLIP, FEE = rb.SLIP, rb.FEE
MAX_OPEN, CAPITAL = 3, 1000.0
TREND, EXIT_MEAN, RSI_N = 200, 5, 2
YEARS = rb.YEARS
WARM_FROM = "2024-01-01"  # 200-day mean ready before 2024-10-12
DESK = rb.DESK
OUT_DIR = Path("docs/research/rsi2")
DECISIVE = ("A pura, umbral 10", "B con frenos, umbral 10")


def rsi(close: np.ndarray, n: int = RSI_N) -> np.ndarray:
    """Wilder's RSI per row (exponential mean with alpha = 1/n); NaN until n changes exist."""
    out = np.full(close.shape, np.nan)
    for i, row in enumerate(close):
        s = pd.Series(row)
        diff = s.diff()
        gain = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        loss = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        with np.errstate(divide="ignore", invalid="ignore"):
            r = 100 - 100 / (1 + gain / loss)
        r[(loss == 0) & (gain > 0)] = 100.0
        r[(loss == 0) & (gain == 0)] = 50.0
        out[i] = r.values
    return out


def sma(close: np.ndarray, n: int) -> np.ndarray:
    return np.vstack([pd.Series(row).rolling(n, min_periods=n).mean().values for row in close])


@dataclass
class Ind:
    rsi: np.ndarray
    trend: np.ndarray
    exit_mean: np.ndarray


def indicators(d: rb.Data) -> Ind:
    return Ind(rsi(d.close), sma(d.close, TREND), sma(d.close, EXIT_MEAN))


def regime_ok(d: rb.Data, t: int) -> bool:
    """Regime b at the signal close t: BTC's close of day t above the mean of its last 50 closes (t included)."""
    return rb.regime_ok(d, t + 1)


def simulate(d: rb.Data, ind: Ind, start: int, end: int, threshold: float = THRESHOLD, brakes: bool = False,
             side: int = 1, capital: float = CAPITAL) -> rb.Result:
    events = rb.event_days(d.days) if brakes else np.zeros(len(d.days), bool)
    cash, eq, trades = capital, [], []
    pos: dict[int, dict] = {}  # coin -> {qty, fill, notional, t_in, pnl so far}
    to_open: list[tuple[int, float]] = []  # (coin, notional) decided at the previous close
    to_close: set[int] = set()

    def close_at(i: int, px: float, t: int) -> None:
        nonlocal cash
        p = pos.pop(i)
        out = px * (1 - SLIP * side)
        pnl = side * p["qty"] * (out - p["fill"]) - FEE * p["qty"] * out
        cash += pnl
        ret = (p["pnl"] + pnl) / p["notional"] * 100
        trades.append({"day": str(d.days[p["t_in"]].date()), "out": str(d.days[t].date()), "symbol": d.names[i],
                       "side": side, "ret_pct": ret, "days": t - p["t_in"]})

    for t in range(start, end):
        for i in sorted(to_close):  # exits decided at yesterday's close, at today's open
            if i in pos and np.isfinite(d.open[i, t]):
                close_at(i, d.open[i, t], t)
                to_close.discard(i)
        for i, notional in to_open:
            o = d.open[i, t]
            if i in pos or not np.isfinite(o) or len(pos) >= MAX_OPEN:
                continue
            fill = o * (1 + SLIP * side)
            pos[i] = {"qty": notional / fill, "fill": fill, "notional": notional, "t_in": t, "pnl": -FEE * notional}
            cash -= FEE * notional
        to_open = []
        for i, p in pos.items():  # funding of the UTC day on the size at today's open
            ref = d.open[i, t] if np.isfinite(d.open[i, t]) else p["fill"]
            fee = side * p["qty"] * ref * d.funding[i, t] / 100
            cash -= fee
            p["pnl"] -= fee
        marks = {i: d.close[i, t] if np.isfinite(d.close[i, t]) else p["fill"] for i, p in pos.items()}
        equity = cash + sum(side * p["qty"] * (marks[i] - p["fill"]) for i, p in pos.items())
        last = t == end - 1 or t + 1 >= len(d.days)
        if last:
            for i in list(pos):
                close_at(i, marks[i], t)
            equity = cash
            eq.append(equity)
            continue
        for i in pos:
            c, m = d.close[i, t], ind.exit_mean[i, t]
            if np.isfinite(c) and np.isfinite(m) and side * (c - m) > 0:
                to_close.add(i)
        if brakes and (events[t + 1] or not regime_ok(d, t)):
            eq.append(equity)
            continue
        cands = []
        for i in range(len(d.names)):
            if i in pos:
                continue
            c, tr, r = d.close[i, t], ind.trend[i, t], ind.rsi[i, t]
            if not np.isfinite([c, tr, r]).all():
                continue
            if (side > 0 and c > tr and r < threshold) or (side < 0 and c < tr and r > 100 - threshold):
                cands.append((side * r, i))
        free = MAX_OPEN - len(pos) + len(to_close & set(pos))
        to_open = [(i, equity / MAX_OPEN) for _, i in sorted(cands)[:max(0, free)]]
        eq.append(equity)
    return rb.Result(np.array(eq), trades)


def stats(r: rb.Result) -> dict:
    s = rb.stats(r)
    rets = [x["ret_pct"] for x in r.trades]
    worst = min(r.trades, key=lambda x: x["ret_pct"]) if r.trades else None
    s.pop("both_hit", None)
    return {**s, "quarters": rb.quarter_nets(r),
            "worst": ({k: worst[k] for k in ("symbol", "day", "out", "days")} | {"ret_pct": round(worst["ret_pct"], 2)}
                      if worst else None),
            "avg_days": round(float(np.mean([x["days"] for x in r.trades])), 1) if r.trades else 0.0,
            "best_pct": round(max(rets), 2) if rets else 0.0}


def year(d: rb.Data, ind: Ind, a: str, b: str) -> dict:
    start = int(d.days.searchsorted(pd.Timestamp(a, tz="UTC")))
    end = int(d.days.searchsorted(pd.Timestamp(b, tz="UTC")))
    runs = {"A pura, umbral 10": (THRESHOLD, False, 1), "B con frenos, umbral 10": (THRESHOLD, True, 1),
            "A pura, umbral 5": (SENS_THRESHOLD, False, 1), "B con frenos, umbral 5": (SENS_THRESHOLD, True, 1),
            "Espejo en corto (A), umbral 10": (THRESHOLD, False, -1)}
    rows: dict[str, Any] = {name: stats(simulate(d, ind, start, end, th, br, sd)) for name, (th, br, sd) in runs.items()}
    btc = d.names.index("BTCUSDT") if "BTCUSDT" in d.names else None
    bh = round((d.close[btc, end - 1] / d.close[btc, start - 1] - 1) * 100, 2) if btc is not None else None
    ref = DESK.get(a, {})
    judge = {v: {name: (rows[v]["net_dd"] or -99) > val for name, val in ref.items()} for v in DECISIVE}
    return {"from": a, "to": b, "rows": rows, "btc_pct": bh, "desk": ref, "judge": judge}


def verdict(years: list[dict]) -> list[str]:
    lines = []
    for v in DECISIVE:
        ok_leader = all(y["judge"][v].get("líder", False) for y in years)
        ok_now = all(y["judge"][v].get("re-medida", False) for y in years)
        detail = "; ".join(f"{y['from']} → {y['to']}: {y['rows'][v]['net_dd']} contra {y['desk'].get('líder')} "
                           f"(re-medida {y['desk'].get('re-medida')})" for y in years)
        word = "pasa" if ok_leader else "no pasa"
        extra = "" if ok_leader == ok_now else (" (contra la mesa re-medida: " + ("pasa" if ok_now else "no pasa") + ")")
        lines.append(f"- **{v}: {word}**{extra}. Neto/caída {detail}.")
    for y in years:
        for v in DECISIVE:
            n = y["rows"][v]["trades"]
            if n < 100:
                lines.append(f"- {v}, {y['from']} → {y['to']}: {n} operaciones, muestra corta.")
    return lines


def render(years: list[dict], meta: dict) -> str:
    L = ["# RSI-2 de Larry Connors en las 12 monedas de la mesa", "",
         "Reglas del líder (`docs/inteligencia/BOTS_PUBLICOS.md`) y preregistro (`docs/research/rsi2/PREREGISTRO.md`), "
         "escritos antes de correr. Velas diarias de Spot, solo largos, sin stop, 3 posiciones de un tercio del capital, "
         "1x. Comisión 0,05% y deslizamiento 0,02% por lado, financiación real. El umbral 10 decide; el umbral 5 y el "
         "espejo en corto solo muestran la sensibilidad. Monedas: " + ", ".join(meta["simbolos"]) + ".", "",
         "## Veredicto", "", *verdict(years)]
    for y in years:
        L += ["", f"## {y['from']} → {y['to']} (BTC comprar y mantener {y['btc_pct']}%; mesa de práctica neto/caída "
              f"{y['desk'].get('líder')}, re-medida {y['desk'].get('re-medida')})", "",
              "| Versión | Neto % | Máx. caída | Neto/caída | Ops | Acierto | Media por op. | Días medios | "
              "Peor operación | Trimestres (neto %) |", "|---|---|---|---|---|---|---|---|---|---|"]
        for name, r in y["rows"].items():
            w = r["worst"]
            worst = f"{w['ret_pct']:+.1f}% ({w['symbol']}, {w['day']} → {w['out']})" if w else "—"
            L.append(f"| {name} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | "
                     f"{r['win_rate']}% | {r['avg_trade_pct']:+.3f}% | {r['avg_days']} | {worst} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "La media por operación y la peor operación son sobre el tamaño de la posición (un tercio del capital), "
          "con costes y financiación.", "",
          "Advertencias: Spot como aproximación del perpetuo; la financiación se cobra sobre el tamaño a la apertura de "
          "cada día; la mesa de práctica se cita de `docs/research/mesa/` y `docs/research/saturado/`. Un resultado "
          "pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="RSI-2 de Larry Connors (investigación)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    with Pool(max(1, args.workers)) as pool:
        loaded = pool.map(rb._load, [(s, start.isoformat(), end.isoformat()) for s in args.simbolos])
    for s, _, _, note in loaded:
        print(f"{s}: {note}")
    d = rb.build(loaded)
    ind = indicators(d)
    years = [year(d, ind, a, b) for a, b in YEARS]
    meta = {"simbolos": d.names}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"rsi2_{stamp}.json").write_text(json.dumps({"meta": meta, "years": years}, indent=1, default=str),
                                                    encoding="utf-8")
    report = render(years, meta)
    (args.salida / f"rsi2_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
