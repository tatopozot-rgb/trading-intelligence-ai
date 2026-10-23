"""
Welles Wilder's Parabolic SAR on BTC and ETH daily candles (leader, 2026-10-23), research only.

Preregistered in docs/research/sar/PREREGISTRO.md before any run; rules from docs/inteligencia/BOTS_PUBLICOS.md
(2026-10-23). Wilder's 0.02 / 0.02 / 0.20, never tuned. Long only: buy at the next open after a close above the SAR
when the previous close was below it; sell at the next open after any close below it. Three decisive rows (the
leader's rule of 2026-10-21): A both coins, B both coins, B on BTC alone. B adds the desk's brakes and an intraday
stop at the closer of the desk stop and the day's SAR level. Runs on research_macd.simulate. Public Binance data
only: no account, no key, no orders. Nothing touches config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_deflactado as rd
from trading_intelligence.backtesting import research_ichimoku as ri
from trading_intelligence.backtesting import research_macd as rmc

AF_START, AF_STEP, AF_MAX = 0.02, 0.02, 0.20
CAPITAL = rmc.CAPITAL
DECISIVE_N = 301
OUT_DIR = Path("docs/research/sar")
# key: (label, coins, brakes, decisive)
ROWS = {"a_juntas": ("A tal cual, BTC y ETH", ("btc", "eth"), False, True),
        "b_juntas": ("B con frenos, BTC y ETH", ("btc", "eth"), True, True),
        "b_btc": ("B con frenos, BTC solo", ("btc",), True, True)}


@dataclass
class Sar:
    sar: np.ndarray  # published value per day (the level, or the extreme point on a reversal day)
    level: np.ndarray  # the stop in force during the day, known at its open
    up: np.ndarray  # True when the day ends in a rising SAR


def parabolic(f: pd.DataFrame) -> Sar:
    h, lo, c = (f[k].to_numpy(float) for k in ("high", "low", "close"))
    n = len(c)
    sar, level, up = np.full(n, np.nan), np.full(n, np.nan), np.zeros(n, bool)
    if n < 2:
        return Sar(sar, level, up)
    rising = bool(c[1] >= c[0])
    s = lo[0] if rising else h[0]
    ep = h[0] if rising else lo[0]
    af = AF_START
    for i in range(1, n):
        if i > 1:
            s = s + af * (ep - s)
            s = min(s, lo[i - 1], lo[i - 2]) if rising else max(s, h[i - 1], h[i - 2])
        level[i] = s
        if rising and lo[i] <= s:
            rising, s, ep, af = False, ep, lo[i], AF_START
        elif not rising and h[i] >= s:
            rising, s, ep, af = True, ep, h[i], AF_START
        elif rising and h[i] > ep:
            ep, af = h[i], min(af + AF_STEP, AF_MAX)
        elif not rising and lo[i] < ep:
            ep, af = lo[i], min(af + AF_STEP, AF_MAX)
        sar[i], up[i] = s, rising
    return Sar(sar, level, up)


def signals(f: pd.DataFrame, p: Sar) -> rmc.Cross:
    c = f["close"].to_numpy(float)
    with np.errstate(invalid="ignore"):
        above, below = c > p.sar, c < p.sar
    enter = above & np.r_[False, below[:-1]]
    return rmc.Cross(enter, below)


def trail_levels(p: Sar) -> np.ndarray:
    """The day's level as a long stop, only on days that open in a rising SAR."""
    return np.where(np.r_[False, p.up[:-1]], p.level, np.nan)


def prepare(frames: dict[str, pd.DataFrame], funding: dict[str, pd.Series]) -> tuple[rmc.Market, dict]:
    mk = rmc.prepare(frames, funding)
    sars = {k: parabolic(f) for k, f in frames.items()}
    mk.cross = {k: signals(frames[k], s) for k, s in sars.items()}
    return mk, {k: trail_levels(s) for k, s in sars.items()}


def run_row(mk: rmc.Market, trails: dict, coins: tuple[str, ...], brakes: bool, a: str, b: str,
            stop_fn=rmc.desk_stop) -> tuple[list[ri.Book], pd.Series]:
    books, curves = [], []
    for k in coins:
        f = mk.frames[k]
        lo = max(1, int(f.index.searchsorted(pd.Timestamp(a, tz="UTC"))))
        hi = int(f.index.searchsorted(pd.Timestamp(b, tz="UTC")))
        book, eq = rmc.simulate(f, mk.cross[k], lo, hi, CAPITAL / len(coins), brakes, 1.0, mk.gate[k], mk.events[k],
                                mk.funding[k], stop_fn, trails[k] if brakes else None)
        books.append(book)
        curves.append(pd.Series(eq, index=f.index[lo:hi]))
    total = pd.concat(curves, axis=1).ffill().fillna(CAPITAL / len(coins)).sum(axis=1)
    return books, total


def year(mk: rmc.Market, trails: dict, a: str, b: str, n: int) -> dict:
    rows = {key: ri.summarize(*run_row(mk, trails, coins, brakes, a, b), n)
            for key, (_, coins, brakes, _) in ROWS.items()}
    return {"from": a, "to": b, "desk": rmc.DESK[a], "rows": rows, "hold_btc": ri.hold(mk.frames["btc"], a, b),
            "hold_eth": ri.hold(mk.frames["eth"], a, b)}


def passes(years: list[dict], key: str) -> bool:
    beats = all((y["rows"][key]["net_dd"] or -99) > y["desk"] for y in years)
    return beats and years[-1]["rows"][key]["dsr"] >= rd.PASS_DSR


def render(years: list[dict], n: int) -> str:
    L = ["# Parabolic SAR de Wilder en BTC y ETH diario", "",
         "Preregistro: `docs/research/sar/PREREGISTRO.md`, escrito antes de correr. 0,02 / 0,02 / 0,20 fijos, solo "
         "compras, órdenes en la apertura siguiente; 0,05% de comisión y 0,02% de deslizamiento por lado; financiación "
         "real; 1.000 USDT. B: stop dentro del día en el más cercano entre el de la mesa (`plan_exits`, 300 velas "
         "diarias) y el SAR, 2% de riesgo, régimen b y sin entradas en días FOMC/IPC. Sharpe deflactado con "
         f"N = {n} decisorias.", "", "## Veredicto", ""]
    for k, v in ROWS.items():
        L.append(f"- **{v[0]}: {'pasa' if passes(years, k) else 'no pasa'}.** Neto/caída "
                 + " ; ".join(str(y["rows"][k]["net_dd"]) for y in years)
                 + f" contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 {years[-1]['rows'][k]['dsr']} "
                 f"(listón {rd.PASS_DSR}); operaciones " + " ; ".join(str(y["rows"][k]["trades"]) for y in years)
                 + (" (muestra corta)" if any(y["rows"][k]["trades"] < 10 for y in years) else "") + ".")
    for y in years:
        hb, he = y["hold_btc"], y["hold_eth"]
        L += ["", f"## {y['from']} → {y['to']}", "",
              f"Mantener BTC: {hb['net_pct']:+.1f}% / caída {hb['max_dd_pct']}% (neto/caída {hb['net_dd']}). "
              f"Mantener ETH: {he['net_pct']:+.1f}% / caída {he['max_dd_pct']}%.", "",
              "| Fila | Neto % | Máx. caída | Neto/caída | Ops | Acierto | Media por op. | Días dentro | Salidas | "
              "Comisiones | Financiación | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            ex = ", ".join(f"{w} {c}" for w, c in sorted(r["exits"].items()))
            L.append(f"| {ROWS[k][0]} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | "
                     f"{r['win_rate']}% | {r['avg_trade_pct']:+.2f}% | {r['in_market_pct']}% | {ex} | {r['fees_usd']} | "
                     f"{r['funding_usd']} | {r['sharpe_anual']} | {r['dsr']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Las tres filas son decisorias. Precio del contado de Binance; financiación del perpetuo. La media por "
          "operación es sobre el capital de la moneda. El capital diario está en el JSON. Un resultado pasado no "
          "promete uno futuro. El dinero real no cambia por este estudio."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Parabolic SAR en BTC y ETH diario (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    frames, funding = rmc.load()
    mk, trails = prepare(frames, funding)
    years = [year(mk, trails, a, b, args.decisorias) for a, b in rmc.YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"sar_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"sar_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
