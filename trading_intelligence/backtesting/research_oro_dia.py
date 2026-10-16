"""
Intraday gold without swap, research only.

Preregistered in docs/research/oro_dia/PREREGISTRO.md before any run. PAXGUSDT 15-minute candles without weekends,
XM GOLD costs (0.40 spread, 0.05 slippage per side), every position closed at the open of the 20:00 UTC candle, so no
night is held. Toby Crabel's opening range breakout from the New York open (9:30 in New York, in UTC each day) with a
30- and a 60-minute range, stop at the other side, 1% risk, size capped at 5x; and intraday momentum (Gao, Han, Li and
Zhou, 2018): the sign of the move from yesterday's 20:00 UTC candle close to 30 minutes after the New York open, held
from 19:00 to 20:00 UTC at 1x. Judged per docs/research/PROTOCOLO.md.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_deflactado as rd
from trading_intelligence.backtesting import research_oro as ro

SYMBOL = "PAXGUSDT"
YEARS = ro.YEARS
WARM_FROM = "2024-06-01"
NY = ZoneInfo("America/New_York")
BAR = pd.Timedelta(minutes=15)
ENTRY_UNTIL, MOM_IN, EXIT_AT = 18, 19, 20  # UTC hours
DECISIVE_N = 257
DESK = {"2024-10-12": {"líder": 1.67, "re-medida": 1.73}, "2025-10-13": {"líder": -0.21, "re-medida": 0.20}}
OUT_DIR = Path("docs/research/oro_dia")
RULES = {"orb30": "Rango de apertura de NY, 30 min", "orb60": "Rango de apertura de NY, 60 min",
         "impulso": "Impulso dentro del día (19:00-20:00 UTC)"}


def ny_open(day: pd.Timestamp) -> pd.Timestamp:
    """09:30 in New York on that calendar day, in UTC."""
    local = datetime(day.year, day.month, day.day, 9, 30, tzinfo=NY)
    return pd.Timestamp(local).tz_convert("UTC")


def _rows(bars: pd.DataFrame):
    return zip(bars.index, bars[["open", "high", "low", "close"]].itertuples(index=False))


def orb(bars: pd.DataFrame, costs: ro.Costs, minutes: int) -> ro.Book:
    book = ro.Book(costs)
    day: Optional[pd.Timestamp] = None
    rng: Optional[tuple[float, float]] = None
    start_entries = None
    traded = False
    for t, (o, h, lo, c) in _rows(bars):
        if t.floor("D") != day:
            day, traded = t.floor("D"), False
            op = ny_open(day)
            first = bars.loc[op:op + pd.Timedelta(minutes=minutes) - BAR]
            full = len(first) == minutes // 15 and first.index[0] == op if len(first) else False
            rng = (float(first["high"].max()), float(first["low"].min())) if full else None
            start_entries = op + pd.Timedelta(minutes=minutes)
        if book.pos is not None and t.hour >= EXIT_AT:
            book.close(t, o, "hora")
        elif book.pos is not None:
            book.check_exits(t, o, h, lo)
        if (book.pos is None and not traded and rng is not None and rng[0] > rng[1] and start_entries is not None
                and t >= start_entries and t.hour < ENTRY_UNTIL):
            hi, low = rng
            side = 1 if h >= hi else (-1 if lo <= low else 0)
            if side:
                trig = hi if side > 0 else low
                px = max(trig, o) if side > 0 else min(trig, o)
                if book.open(t, side, px, low if side > 0 else hi):
                    traded = True
                    book.check_exits(t, o, h, lo, entry_bar=True)
        book.mark(c)
    if book.pos is not None:
        book.close(bars.index[-1], float(bars["close"].iloc[-1]), "fin")
        book.equity[-1] = book.cash
    return book


def open_full(book: ro.Book, t: pd.Timestamp, side: int, px: float) -> None:
    """A position of 100% of the cash, 1x, no stop."""
    fill = book.costs.fill(px, side, True)
    book.pos = {"t": t, "side": side, "px": px, "fill": fill, "qty": book.cash / fill, "stop": None, "target": None}


def momentum(bars: pd.DataFrame, costs: ro.Costs) -> ro.Book:
    book = ro.Book(costs)
    ref_close: dict[pd.Timestamp, float] = {}
    for t, row in bars[bars.index.hour == EXIT_AT].iterrows():
        if t.minute == 0:
            ref_close[t.floor("D")] = float(row["close"])
    days = sorted(ref_close)
    day: Optional[pd.Timestamp] = None
    side = 0
    for t, (o, h, lo, c) in _rows(bars):
        if t.floor("D") != day:
            day, side = t.floor("D"), 0
            mark_t = ny_open(day) + pd.Timedelta(minutes=15)  # the candle that closes 30 min after the open
            k = int(np.searchsorted(days, day)) - 1  # yesterday's (last trading day's) 20:00 close
            ref = ref_close[days[k]] if k >= 0 else None
            if ref is not None and mark_t in bars.index:
                move = float(bars.at[mark_t, "close"]) - ref
                side = int(np.sign(move))
        if book.pos is not None and t.hour >= EXIT_AT:
            book.close(t, o, "hora")
        if book.pos is None and side and t.hour == MOM_IN and t.minute == 0:
            open_full(book, t, side, o)
            side = 0
        book.mark(c)
    if book.pos is not None:
        book.close(bars.index[-1], float(bars["close"].iloc[-1]), "fin")
        book.equity[-1] = book.cash
    return book


def run_rule(rule: str, bars: pd.DataFrame, costs: ro.Costs) -> ro.Book:
    if rule == "orb30":
        return orb(bars, costs, 30)
    if rule == "orb60":
        return orb(bars, costs, 60)
    return momentum(bars, costs)


def year(bars: pd.DataFrame, a: str, b: str, n_decisive: int) -> dict:
    lo_t, hi_t = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
    seg = bars[(bars.index >= lo_t) & (bars.index < hi_t)]
    rows: dict[str, Any] = {}
    for rule in RULES:
        for mult, label in ((1.0, ""), (2.0, ", costes ×2")):
            book = run_rule(rule, seg, ro.Costs("oro", mult))
            s = ro.stats(book)
            r = rd.daily_returns(book.equity, seg.index)
            m = rd.moments(r)
            s.update({"sharpe_anual": round(m["sr_anual"], 2),
                      "dsr": round(rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n_decisive,
                                                      1 / m["T"]), 3),
                      "daily_equity": {str(d.date()): round(float(v), 2) for d, v in
                                       pd.Series(book.equity, index=seg.index[-len(book.equity):])
                                       .groupby(lambda x: x.floor("D")).last().items()}})
            rows[rule + label] = s
    hold = round((seg["close"].iloc[-1] / seg["open"].iloc[0] - 1) * 100, 2) if len(seg) else None
    return {"from": a, "to": b, "rows": rows, "hold_pct": hold, "desk": DESK.get(a, {})}


def verdict(years: list[dict]) -> list[str]:
    lines = []
    for rule, name in RULES.items():
        beats = all((y["rows"][rule]["net_dd"] or -99) > y["desk"]["líder"] for y in years)
        beats_now = all((y["rows"][rule]["net_dd"] or -99) > y["desk"]["re-medida"] for y in years)
        dsr = years[-1]["rows"][rule]["dsr"]
        ok = beats and dsr >= rd.PASS_DSR
        nd = " ; ".join(str(y["rows"][rule]["net_dd"]) for y in years)
        extra = "" if beats == beats_now else f"; contra la mesa re-medida {'gana' if beats_now else 'no gana'}"
        lines.append(f"- **{name}: {'pasa' if ok else 'no pasa'}.** Neto/caída {nd} contra 1,67 ; −0,21 "
                     f"({'gana' if beats else 'no gana'} los dos años{extra}); Sharpe deflactado 2025-26 {dsr} "
                     f"(listón {rd.PASS_DSR}).")
    for y in years:
        for rule, name in RULES.items():
            if y["rows"][rule]["trades"] < 100:
                lines.append(f"- {name}, {y['from']} → {y['to']}: {y['rows'][rule]['trades']} operaciones, muestra corta.")
    return lines


def render(years: list[dict], n_decisive: int) -> str:
    L = ["# Oro solo dentro del día, sin swap", "",
         "Preregistro: `docs/research/oro_dia/PREREGISTRO.md`, escrito antes de correr. Velas de 15 minutos de PAXGUSDT "
         "sin fines de semana; costes de GOLD en XM (diferencial 0,40 y 0,05 de deslizamiento por lado); todo cierra a "
         f"las 20:00 UTC, sin noches. Sharpe deflactado con N = {n_decisive} decisorias.", "", "## Veredicto", "",
         *verdict(years)]
    for y in years:
        L += ["", f"## {y['from']} → {y['to']} (oro comprar y mantener {y['hold_pct']}%; mesa de práctica neto/caída "
              f"{y['desk'].get('líder')}, re-medida {y['desk'].get('re-medida')})", "",
              "| Regla | Neto % | Máx. caída | Neto/caída | Ops | Largos | Cortos | Acierto | Media por op. | Salidas | "
              "Sharpe anual | Sharpe deflactado | Trimestres (neto %) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for key, r in y["rows"].items():
            base, _, extra = key.partition(",")
            name = RULES[base] + ("," + extra if extra else "")
            exits = ", ".join(f"{k} {v}" for k, v in r["exits"].items())
            L.append(f"| {name} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | {r['longs']} | "
                     f"{r['shorts']} | {r['win_rate']}% | {r['avg_trade_pct']:+.3f}% | {exits} | {r['sharpe_anual']} | "
                     f"{r['dsr']} | " + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "La media por operación es sobre el capital. PAXG cotiza en Binance, no en el COMEX: la apertura de Nueva "
          "York puede pesar menos que en el oro de XM. El capital diario está en el JSON. Un resultado pasado no promete "
          "uno futuro."]
    return "\n".join(L) + "\n"


def load() -> pd.DataFrame:
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    rdv.INTERVAL_MS.setdefault("15m", 900_000)
    bars = rdv.fetch_klines(SYMBOL, "15m", start, end)
    return bars[bars.index.dayofweek < 5]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Oro dentro del día sin swap (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    bars = load()
    print(f"{SYMBOL}: {len(bars)} velas de 15 min")
    years = [year(bars, a, b, args.decisorias) for a, b in YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"oro_dia_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"oro_dia_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
