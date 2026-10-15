"""
Three public gold strategies, and the same rules on BTC, research only.

Preregistered in docs/research/oro/PREREGISTRO.md before any run. Gold = PAXGUSDT candles from Binance Spot with
Saturday and Sunday (UTC) dropped; BTC = BTCUSDT, every day. One position at a time per strategy and asset, 1% of
capital at risk per trade, size capped at 5x capital. Costs: gold like an XM Standard account (0.40 USD/oz spread
round trip, 0.05 USD slippage per side, swap per night open at 21:00 UTC, long -0.015%, short -0.005%, Wednesday x3);
BTC 0.05% fee and 0.02% slippage per side, 0.01% funding at 00/08/16 UTC (long pays, short receives).

  1. London breakout: Asian range 00:00-06:00 UTC; stop orders at its high/low from 07:00 to 15:00; stop at the other
     side, target 1x range; out at the 20:00 open. One trade a day.
  2. Turtle system 1 (daily): 20-day channel entry by stop, 2N stop (N = ATR 20 of the day before), 10-day exit.
  3. News fade: the 1h candle holding an FOMC/CPI release, if its range >= 2x ATR 14 (1h), is faded at the next open;
     stop at its extreme, target at its middle, out at the open of the 8th candle after entry.

Same candle touching stop and entry, or stop and target: the stop counts. Public data only.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from trading_intelligence.analysis import indicators as ind
from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_breakout as rb
from trading_intelligence.backtesting import research_mesa as rm

ASSETS = {"oro": "PAXGUSDT", "btc": "BTCUSDT"}
CAPITAL, RISK, MAX_NOTIONAL = 1000.0, 0.01, 5.0
ASIA_HOURS, ENTRY_HOURS, EXIT_HOUR = range(0, 7), range(7, 16), 20
TURTLE_IN, TURTLE_OUT, TURTLE_N, TURTLE_STOP = 20, 10, 20, 2.0
NEWS_ATR, NEWS_MULT, NEWS_BARS = 14, 2.0, 8
YEARS, WARM_FROM, DESK = rb.YEARS, rb.WARM_FROM, rb.DESK
STRATEGIES = {"londres": "Ruptura de Londres (1 h)", "tortugas": "Tortugas, tendencia diaria",
              "noticia": "Reversión tras noticia (1 h)"}
OUT_DIR = Path("docs/research/oro")


@dataclass(frozen=True)
class Costs:
    """Fills and carry for one asset; `mult` scales every cost (2.0 = the doubled-cost sensitivity)."""
    asset: str
    mult: float = 1.0

    def fill(self, px: float, side: int, entering: bool) -> float:
        """Price after spread/slippage: worse for the trader on both sides."""
        sign = side if entering else -side
        if self.asset == "oro":
            return px + sign * (0.20 + 0.05) * self.mult
        return px * (1 + sign * 0.0002 * self.mult)

    def fees(self, notional_in: float, notional_out: float) -> float:
        return 0.0 if self.asset == "oro" else 0.0005 * self.mult * (notional_in + notional_out)

    def carry(self, side: int, t_in: pd.Timestamp, t_out: pd.Timestamp, notional: float) -> float:
        """Money paid (positive) or received (negative) for holding from t_in to t_out."""
        if self.asset == "oro":
            nights = pd.date_range(t_in.floor("D"), t_out, freq="D") + pd.Timedelta(hours=21)
            nights = nights[(nights >= t_in) & (nights < t_out) & (nights.dayofweek < 5)]
            count = sum(3 if n.dayofweek == 2 else 1 for n in nights)
            rate = 0.00015 if side > 0 else 0.00005
            return notional * rate * count * self.mult
        events = pd.date_range(t_in.floor("D"), t_out, freq="8h")
        count = int(((events >= t_in) & (events < t_out)).sum())
        return side * notional * 0.0001 * count * self.mult


@dataclass
class Book:
    """One position at a time; equity marked at every candle close."""
    costs: Costs
    capital: float = CAPITAL
    cash: float = CAPITAL
    pos: Optional[dict] = None
    equity: list[float] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)

    def open(self, t: pd.Timestamp, side: int, px: float, stop: float, target: Optional[float] = None) -> bool:
        dist = abs(px - stop)
        if dist <= 0 or self.cash <= 0:
            return False
        qty = min(RISK * self.cash / dist, MAX_NOTIONAL * self.cash / px)
        self.pos = {"t": t, "side": side, "px": px, "fill": self.costs.fill(px, side, True), "qty": qty,
                    "stop": stop, "target": target}
        return True

    def close(self, t: pd.Timestamp, px: float, why: str) -> None:
        p = self.pos
        assert p is not None
        out = self.costs.fill(px, p["side"], False)
        n_in, n_out = p["qty"] * p["fill"], p["qty"] * out
        pnl = (p["side"] * p["qty"] * (out - p["fill"]) - self.costs.fees(n_in, n_out)
               - self.costs.carry(p["side"], p["t"], t, n_in))
        self.trades.append({"entry": str(p["t"]), "exit": str(t), "side": p["side"], "why": why,
                            "ret_pct": pnl / self.cash * 100})
        self.cash += pnl
        self.pos = None

    def mark(self, close: float) -> None:
        p = self.pos
        self.equity.append(self.cash + (p["side"] * p["qty"] * (close - p["fill"]) if p else 0.0))

    def check_exits(self, t: pd.Timestamp, o: float, h: float, lo: float, entry_bar: bool = False) -> bool:
        """Stop first (a gap past it fills at the open), then the target. True if closed."""
        p = self.pos
        if p is None:
            return False
        side, stop, target = p["side"], p["stop"], p["target"]
        if not entry_bar and side * (o - stop) <= 0:
            self.close(t, o, "stop")
        elif (side > 0 and lo <= stop) or (side < 0 and h >= stop):
            self.close(t, stop, "stop")
        elif target is not None and not entry_bar and side * (o - target) >= 0:
            self.close(t, o, "meta")
        elif target is not None and ((side > 0 and h >= target) or (side < 0 and lo <= target)):
            self.close(t, target, "meta")
        else:
            return False
        return True


def london(bars: pd.DataFrame, costs: Costs) -> Book:
    book = Book(costs)
    rng_hi = rng_lo = None
    day = None
    traded = False
    for t, (o, h, lo, c) in zip(bars.index, bars[["open", "high", "low", "close"]].itertuples(index=False)):
        if t.floor("D") != day:
            day, traded = t.floor("D"), False
            asia = bars.loc[day:day + pd.Timedelta(hours=6, minutes=59)]
            full = len(asia) == len(ASIA_HOURS) and asia.index.hour.min() == 0
            rng_hi, rng_lo = (asia["high"].max(), asia["low"].min()) if full else (None, None)
        if book.pos is not None and t.hour >= EXIT_HOUR:
            book.close(t, o, "hora")
        elif book.pos is not None:
            book.check_exits(t, o, h, lo)
        if (book.pos is None and not traded and rng_hi is not None and rng_lo is not None and rng_hi > rng_lo
                and t.hour in ENTRY_HOURS):
            r = rng_hi - rng_lo
            side = 1 if h >= rng_hi else (-1 if lo <= rng_lo else 0)
            if side:
                trig = rng_hi if side > 0 else rng_lo
                px = max(trig, o) if side > 0 else min(trig, o)
                stop = rng_lo if side > 0 else rng_hi
                if book.open(t, side, px, stop, px + side * r):
                    traded = True
                    book.check_exits(t, o, h, lo, entry_bar=True)
        book.mark(c)
    if book.pos is not None:
        book.close(bars.index[-1], float(bars["close"].iloc[-1]), "fin")
        book.equity[-1] = book.cash
    return book


def turtle(daily: pd.DataFrame, costs: Costs, start: int) -> Book:
    book = Book(costs)
    hi_in = daily["high"].shift(1).rolling(TURTLE_IN).max()
    lo_in = daily["low"].shift(1).rolling(TURTLE_IN).min()
    hi_out = daily["high"].shift(1).rolling(TURTLE_OUT).max()
    lo_out = daily["low"].shift(1).rolling(TURTLE_OUT).min()
    n = ind.atr(daily["high"], daily["low"], daily["close"], TURTLE_N).shift(1)
    for k in range(start, len(daily)):
        t = daily.index[k]
        o, h, lo, c = (float(daily[x].iloc[k]) for x in ("open", "high", "low", "close"))
        if book.pos is not None and not book.check_exits(t, o, h, lo):
            side = book.pos["side"]
            level = lo_out.iloc[k] if side > 0 else hi_out.iloc[k]
            if np.isfinite(level) and ((side > 0 and lo <= level) or (side < 0 and h >= level)):
                px = min(level, o) if side > 0 else max(level, o)
                book.close(t, px, "canal")
        if book.pos is None and np.isfinite([hi_in.iloc[k], lo_in.iloc[k], n.iloc[k]]).all():
            side = 1 if h >= hi_in.iloc[k] else (-1 if lo <= lo_in.iloc[k] else 0)
            if side:
                trig = hi_in.iloc[k] if side > 0 else lo_in.iloc[k]
                px = max(trig, o) if side > 0 else min(trig, o)
                if book.open(t, side, px, px - side * TURTLE_STOP * n.iloc[k]):
                    book.check_exits(t, o, h, lo, entry_bar=True)
        book.mark(c)
    if book.pos is not None:
        book.close(daily.index[-1], float(daily["close"].iloc[-1]), "fin")
        book.equity[-1] = book.cash
    return book


def news(bars: pd.DataFrame, costs: Costs, start: int, events: list[pd.Timestamp]) -> Book:
    book = Book(costs)
    atr = ind.atr(bars["high"], bars["low"], bars["close"], NEWS_ATR).shift(1)
    event_bars = {bars.index.searchsorted(e.floor("h"), "left") for e in events if e.floor("h") in bars.index}
    pending: Optional[tuple[int, float, float]] = None
    held = 0
    for k in range(start, len(bars)):
        t = bars.index[k]
        o, h, lo, c = (float(bars[x].iloc[k]) for x in ("open", "high", "low", "close"))
        if book.pos is not None:
            held += 1
            if held > NEWS_BARS:
                book.close(t, o, "hora")
            else:
                book.check_exits(t, o, h, lo)
        if pending is not None and book.pos is None:
            side, stop, target = pending
            if side * (target - o) > 0 and side * (o - stop) > 0 and book.open(t, side, o, stop, target):
                held = 1
                book.check_exits(t, o, h, lo, entry_bar=True)
        pending = None
        if k in event_bars and np.isfinite(atr.iloc[k]) and h - lo >= NEWS_MULT * atr.iloc[k] and c != o:
            side = -1 if c > o else 1
            pending = (side, h if side < 0 else lo, (h + lo) / 2)
        book.mark(c)
    if book.pos is not None:
        book.close(bars.index[-1], float(bars["close"].iloc[-1]), "fin")
        book.equity[-1] = book.cash
    return book


def stats(book: Book) -> dict:
    e = np.r_[book.capital, book.equity]
    peak = np.maximum.accumulate(e)
    dd = float(((peak - e) / peak).max() * 100)
    net = (e[-1] / book.capital - 1) * 100
    rets = [x["ret_pct"] for x in book.trades]
    T, a, q = len(book.equity), 0, []
    for i in range(4):
        b = min(T, a + (T - a) // (4 - i))
        q.append(round((e[b] / e[a] - 1) * 100, 2))
        a = b
    whys: dict[str, int] = {}
    for x in book.trades:
        whys[x["why"]] = whys.get(x["why"], 0) + 1
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "trades": len(rets), "win_rate": round(float(np.mean([x > 0 for x in rets]) * 100), 1) if rets else 0.0,
            "avg_trade_pct": round(float(np.mean(rets)), 3) if rets else 0.0,
            "longs": sum(1 for x in book.trades if x["side"] > 0), "shorts": sum(1 for x in book.trades if x["side"] < 0),
            "exits": whys, "quarters": q}


def passes(s: dict) -> bool:
    return s["net_pct"] > 0 and (s["net_dd"] or 0) >= 1.0 and sum(x >= 0 for x in s["quarters"]) >= 3


def run_year(hourly: pd.DataFrame, daily: pd.DataFrame, asset: str, a: str, b: str,
             events: list[pd.Timestamp]) -> dict:
    lo_t, hi_t = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
    h_year = hourly[(hourly.index >= lo_t) & (hourly.index < hi_t)]
    d_cut = daily[daily.index < hi_t]
    h_cut = hourly[hourly.index < hi_t]
    rows: dict[str, Any] = {}
    for mult, label in ((1.0, ""), (2.0, ", costes ×2")):
        costs = Costs(asset, mult)
        runs: dict[str, Callable[[], Book]] = {
            "londres": lambda: london(h_year, costs),
            "tortugas": lambda: turtle(d_cut, costs, int(d_cut.index.searchsorted(lo_t))),
            "noticia": lambda: news(h_cut, costs, int(h_cut.index.searchsorted(lo_t)), events),
        }
        for key, fn in runs.items():
            s = stats(fn())
            rows[key + label] = {**s, "pasa": passes(s)}
    d_year = daily[(daily.index >= lo_t) & (daily.index < hi_t)]
    bh = round((d_year["close"].iloc[-1] / d_year["open"].iloc[0] - 1) * 100, 2) if len(d_year) else None
    return {"from": a, "to": b, "rows": rows, "hold_pct": bh, "desk": DESK.get(a, {})}


def verdict(results: dict[str, list[dict]]) -> list[str]:
    lines = []
    for asset, years in results.items():
        for key, name in STRATEGIES.items():
            ok = all(y["rows"][key]["pasa"] for y in years)
            detail = "; ".join(f"{y['from'][:4]}-{y['to'][2:4]}: neto {y['rows'][key]['net_pct']:+.1f}%, neto/caída "
                               f"{y['rows'][key]['net_dd']}, {y['rows'][key]['trades']} ops" for y in years)
            short = any(y["rows"][key]["trades"] < 100 for y in years)
            lines.append(f"- **{asset.upper()}, {name}: {'pasa' if ok else 'no pasa'}**"
                         f"{' (muestra corta)' if short else ''} — {detail}.")
    return lines


def render(results: dict[str, list[dict]]) -> str:
    L = ["# Oro (y BTC con las mismas reglas): ruptura de Londres, Tortugas y reversión tras noticia", "",
         "Preregistrado en `docs/research/oro/PREREGISTRO.md` antes de correr. Oro = PAXGUSDT sin sábados ni domingos; "
         "costes como XM Standard. BTC = BTCUSDT con costes de Binance. 1% de riesgo por operación, tope 5 veces el "
         "capital. Pasa si en los dos años: neto positivo, neto/caída ≥ 1,0 y 3 de 4 trimestres sin pérdida.", "",
         "## Veredicto", "", *verdict(results)]
    for asset, years in results.items():
        for y in years:
            L += ["", f"## {asset.upper()} · {y['from']} → {y['to']} (comprar y mantener {y['hold_pct']}%; mesa de "
                  f"práctica neto/caída {y['desk'].get('líder')}, re-medida {y['desk'].get('re-medida')})", "",
                  "| Estrategia | Neto % | Máx. caída | Neto/caída | Ops | Largos | Cortos | Acierto | Media por op. | "
                  "Salidas | Trimestres (neto %) | Pasa |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for key, r in y["rows"].items():
                base = key.split(",")[0]
                name = STRATEGIES[base] + key[len(base):]
                ex = ", ".join(f"{k} {v}" for k, v in sorted(r["exits"].items()))
                L.append(f"| {name} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | "
                         f"{r['longs']} | {r['shorts']} | {r['win_rate']}% | {r['avg_trade_pct']:+.3f}% | {ex} | "
                         + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + f" | {'sí' if r['pasa'] else 'no'} |")
    L += ["", "Advertencias: PAXG como aproximación del oro de contado (cotiza en fin de semana; esas velas se quitan); "
          "los costes del oro son supuestos de una cuenta Standard de XM, por confirmar en la demo; la vela de 1 hora no "
          "dice qué se tocó primero (por eso cuenta el stop); el 'media por op.' es sobre el capital, no sobre el "
          "tamaño. Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def load(symbol: str, weekdays_only: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    hourly = rdv.fetch_klines(symbol, "1h", start, end)
    daily = rdv.fetch_klines(symbol, "1d", start, end)
    if weekdays_only:
        hourly = hourly[hourly.index.dayofweek < 5]
        daily = daily[daily.index.dayofweek < 5]
    return hourly, daily


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Oro y BTC: tres estrategias públicas (investigación)")
    parser.add_argument("--activos", nargs="+", default=list(ASSETS), choices=list(ASSETS))
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    events = rm.macro_events()
    results: dict[str, list[dict]] = {}
    for asset in args.activos:
        hourly, daily = load(ASSETS[asset], weekdays_only=asset == "oro")
        print(f"{asset}: {len(hourly)} velas de 1 h, {len(daily)} diarias")
        results[asset] = [run_year(hourly, daily, asset, a, b, events) for a, b in YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"oro_{stamp}.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    report = render(results)
    (args.salida / f"oro_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
