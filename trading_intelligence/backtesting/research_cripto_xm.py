"""
BTC London breakout re-tested with XM costs (leader, 2026-10-16), research only.

Preregistered in docs/research/cripto_xm/PREREGISTRO.md before any run. The rule is research_oro.london unchanged
(Asia range 00-07 UTC, entries 07-16 UTC, stop at the other side, target one range, out at 20:00 UTC, 1% risk, at
most 5x), on Binance BTCUSDT 1h candles as the price path. Only the costs change, to XM's BTCUSD as read in the demo
on 2026-10-16: no commission, a fixed spread of 40 USD per BTC (half on each side), no swap because nothing is held
overnight, and XM's lot (0.01 BTC minimum and step). Public data only: no account, no key, no orders.
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
from trading_intelligence.backtesting import research_oro as ro

SPREAD_USD = 40.0  # XM BTCUSD, per BTC
LOT_MIN = LOT_STEP = 0.01
DECISIVE_N = 259
DESK = {"2024-10-12": 1.67, "2025-10-13": -0.21}
OUT_DIR = Path("docs/research/cripto_xm")
ROWS = {"xm": ("Ruptura de Londres en BTC, costos de XM", 1.0, 1000.0),
        "xm2": ("Lo mismo, spread ×2", 2.0, 1000.0),
        "xm200": ("Costos de XM con 200 USD", 1.0, 200.0)}


@dataclass(frozen=True)
class XmCosts(ro.Costs):
    """XM BTCUSD: half the fixed spread per side, no commission, no swap intraday."""

    def fill(self, px: float, side: int, entering: bool) -> float:
        sign = side if entering else -side
        return px + sign * SPREAD_USD / 2 * self.mult

    def fees(self, notional_in: float, notional_out: float) -> float:
        return 0.0

    def carry(self, side: int, t_in: pd.Timestamp, t_out: pd.Timestamp, notional: float) -> float:
        return 0.0  # every position closes by 20:00 UTC, before XM's rollover


def lots(qty: float) -> float:
    """BTC rounded to XM's step; under half the minimum lot is no trade."""
    if qty < LOT_MIN / 2:
        return 0.0
    return max(LOT_MIN, round(qty / LOT_STEP) * LOT_STEP)


class LotBook(ro.Book):
    """research_oro.Book with the size rounded to XM lots (a size of zero skips the trade)."""

    def open(self, t: pd.Timestamp, side: int, px: float, stop: float, target: Optional[float] = None) -> bool:
        dist = abs(px - stop)
        if dist <= 0 or self.cash <= 0:
            return False
        qty = lots(min(ro.RISK * self.cash / dist, ro.MAX_NOTIONAL * self.cash / px))
        if qty * px > ro.MAX_NOTIONAL * self.cash:
            qty = 0.0
        if qty == 0:
            self.skipped = getattr(self, "skipped", 0) + 1
            return False
        self.pos = {"t": t, "side": side, "px": px, "fill": self.costs.fill(px, side, True), "qty": qty,
                    "stop": stop, "target": target}
        return True


def run(bars: pd.DataFrame, mult: float, capital: float) -> LotBook:
    old = ro.Book
    ro.Book = lambda costs: LotBook(costs, capital, capital)  # type: ignore[misc,assignment]
    try:
        book = ro.london(bars, XmCosts("btc", mult))
    finally:
        ro.Book = old  # type: ignore[misc]
    return book  # type: ignore[return-value]


def summarize(book: LotBook, idx: pd.DatetimeIndex, capital: float, n: int) -> dict:
    s = ro.stats(book)
    r = rd.daily_returns(book.equity, idx, capital)
    m = rd.moments(r)
    s["sharpe_anual"] = round(m["sr_dia"] * np.sqrt(365), 2)
    s["dsr"] = round(rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n, 1 / m["T"]), 3) \
        if m["T"] > 2 and m["sr_dia"] != 0 else 0.0
    s["skipped_lot"] = getattr(book, "skipped", 0)
    s["daily_equity"] = {str(d.date()): round(float(v), 2) for d, v in
                         pd.Series(book.equity, index=idx[-len(book.equity):]).groupby(lambda x: x.floor("D")).last().items()}
    return s


def year(hourly: pd.DataFrame, a: str, b: str, n: int) -> dict:
    seg = hourly[(hourly.index >= pd.Timestamp(a, tz="UTC")) & (hourly.index < pd.Timestamp(b, tz="UTC"))]
    rows = {k: summarize(run(seg, mult, cap), seg.index, cap, n) for k, (_, mult, cap) in ROWS.items()}
    return {"from": a, "to": b, "desk": DESK[a], "rows": rows}


def render(years: list[dict], n: int) -> str:
    beats = all((y["rows"]["xm"]["net_dd"] or -99) > y["desk"] for y in years)
    dsr = years[-1]["rows"]["xm"]["dsr"]
    ok = beats and dsr >= rd.PASS_DSR
    L = ["# Ruptura de Londres en BTC con los costos de XM", "",
         "Preregistro: `docs/research/cripto_xm/PREREGISTRO.md`, escrito antes de correr. La regla de `research_oro` sin "
         "cambios; solo cambian los costos: spread fijo de 40 USD por BTC, sin comisión, sin swap (todo cierra a las "
         f"20:00 UTC), lotes de 0,01 BTC. Sharpe deflactado con N = {n} decisorias.", "", "## Veredicto", "",
         f"- **{'Pasa' if ok else 'No pasa'}.** Neto/caída con 1.000 USD "
         + " ; ".join(str(y["rows"]["xm"]["net_dd"]) for y in years)
         + f" contra la mesa 1,67 ; −0,21 ({'gana' if beats else 'no gana'} los dos años); Sharpe deflactado 2025-26 "
         f"{dsr} (listón {rd.PASS_DSR}).",
         "- Antes, con costos de Binance: −14,8% / caída 25,49% y −17,8% / 22,35% (filas 271 del registro)."]
    for y in years:
        L += ["", f"## {y['from']} → {y['to']}", "",
              "| Fila | Neto % | Máx. caída | Neto/caída | Ops | Saltadas por lote | Acierto | Sharpe anual | "
              "Sharpe deflactado | Trimestres (neto %) |", "|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            L.append(f"| {ROWS[k][0]} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | "
                     f"{r['skipped_lot']} | {r['win_rate']}% | {r['sharpe_anual']} | {r['dsr']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "El camino del precio es el de Binance (BTCUSDT); el de XM puede diferir algo. El spread de 40 USD es el de "
          "hoy; con BTC más barato pesa más. El capital diario está en el JSON. Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ruptura de Londres en BTC con costos de XM (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    hourly, _ = ro.load(ro.ASSETS["btc"], weekdays_only=False)
    years = [year(hourly, a, b, args.decisorias) for a, b in ro.YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"cripto_xm_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"cripto_xm_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
