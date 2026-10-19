"""
Ichimoku cloud on BTC and ETH daily candles (leader, 2026-10-19), research only.

Preregistered in docs/research/ichimoku/PREREGISTRO.md before any run; rules from docs/inteligencia/BOTS_PUBLICOS.md
(2026-10-19). Classic 9/26/52, never tuned. Long only: buy when the close is above today's cloud, Tenkan is above
Kijun and the cloud 26 days ahead is green; sell when the close falls under the Kijun or into (or under) the cloud.
Orders at the next day's open. Version A as is (100%, 1x, no stop); version B with the desk's brakes (stop on the
Kijun with 2% risk, regime b, no entries on FOMC/CPI days). Desk costs and real funding. Public Binance data only:
no account, no key, no orders. Nothing touches config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_deflactado as rd
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import two_way_backtest as tw

TENKAN, KIJUN, SENKOU_B, SHIFT = 9, 26, 52, 26
FEE, SLIP = tw.FEE, 0.0002
DESK_RISK = 0.02
REGIME_SMA = 50
CAPITAL = 1000.0
DECISIVE_N = 280
YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
WARM_FROM = "2024-01-01"
DESK = {"2024-10-12": 1.67, "2025-10-13": -0.21}
SYMBOLS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
OUT_DIR = Path("docs/research/ichimoku")
# key: (label, coins, brakes, cost multiplier, decisive)
ROWS = {"a_btc": ("A tal cual, BTC", ("btc",), False, 1.0, True),
        "a_eth": ("A tal cual, ETH", ("eth",), False, 1.0, True),
        "a_juntas": ("A tal cual, BTC y ETH", ("btc", "eth"), False, 1.0, True),
        "b_btc": ("B con frenos, BTC", ("btc",), True, 1.0, True),
        "b_eth": ("B con frenos, ETH", ("eth",), True, 1.0, True),
        "b_juntas": ("B con frenos, BTC y ETH", ("btc", "eth"), True, 1.0, True),
        "a_juntas_x2": ("A juntas, costos ×2", ("btc", "eth"), False, 2.0, False),
        "b_juntas_x2": ("B juntas, costos ×2", ("btc", "eth"), True, 2.0, False)}


def midpoint(high: pd.Series, low: pd.Series, n: int) -> pd.Series:
    return (high.rolling(n).max() + low.rolling(n).min()) / 2


@dataclass
class Lines:
    tenkan: np.ndarray
    kijun: np.ndarray
    cloud_hi: np.ndarray  # today's cloud
    cloud_lo: np.ndarray
    ahead_green: np.ndarray  # the cloud drawn 26 days ahead, computed today
    enter: np.ndarray
    exit: np.ndarray


def ichimoku(f: pd.DataFrame) -> Lines:
    h, lo, c = f["high"], f["low"], f["close"]
    tenkan, kijun = midpoint(h, lo, TENKAN), midpoint(h, lo, KIJUN)
    a_raw, b_raw = (tenkan + kijun) / 2, midpoint(h, lo, SENKOU_B)
    a_now, b_now = a_raw.shift(SHIFT), b_raw.shift(SHIFT)
    hi_, lo_ = np.maximum(a_now, b_now).to_numpy(), np.minimum(a_now, b_now).to_numpy()  # NaN until both exist
    t, k, cc = tenkan.to_numpy(), kijun.to_numpy(), c.to_numpy()
    green = (a_raw > b_raw).to_numpy()
    with np.errstate(invalid="ignore"):
        enter = np.isfinite(hi_) & (cc > hi_) & (t > k) & green
        exit_ = np.isfinite(hi_) & ((cc < k) | (cc <= hi_))
    return Lines(t, k, hi_, lo_, green, enter, exit_)


@dataclass
class Book:
    cash: float
    trades: list[dict] = field(default_factory=list)
    fees: float = 0.0
    funding: float = 0.0
    pos: Optional[dict] = None


def simulate(f: pd.DataFrame, ln: Lines, lo: int, hi: int, capital: float, brakes: bool, mult: float = 1.0,
             gate: Optional[np.ndarray] = None, events: Optional[np.ndarray] = None,
             funding: Optional[np.ndarray] = None) -> tuple[Book, np.ndarray]:
    """One coin over days [lo, hi). Day j-1's close decides; day j's open acts."""
    o, low, c = (f[k].to_numpy(float) for k in ("open", "low", "close"))
    days = f.index
    fee, slip = FEE * mult, SLIP * mult
    book = Book(capital)
    eq = np.zeros(hi - lo)

    def close_pos(j: int, px: float, why: str) -> None:
        p = book.pos
        assert p is not None
        fill = px * (1 - slip)
        cost = fee * p["qty"] * fill
        pnl = p["qty"] * (fill - p["fill"]) - cost
        book.cash += pnl
        book.fees += cost
        net = pnl - p["fee"] - p["fund"]
        book.trades.append({"in": str(days[p["j"]].date()), "out": str(days[j].date()), "why": why,
                            "ret_pct": round(net / p["equity"] * 100, 3)})
        book.pos = None

    for j in range(lo, hi):
        exited = False
        if book.pos is not None:
            gate_off = brakes and gate is not None and not gate[j]
            if ln.exit[j - 1] or gate_off:
                close_pos(j, o[j], "régimen" if gate_off and not ln.exit[j - 1] else "señal")
                exited = True
        if book.pos is None and not exited and ln.enter[j - 1] and not ln.exit[j - 1]:
            ok = not brakes or ((gate is None or gate[j]) and (events is None or not events[j]))
            fill = o[j] * (1 + slip)
            stop = float(ln.kijun[j - 1])
            if ok and brakes and not (np.isfinite(stop) and stop < fill):
                ok = False
            if ok and book.cash > 0:
                qty = book.cash / (fill * (1 + fee))
                if brakes:
                    qty = min(qty, DESK_RISK * book.cash / (fill - stop))
                cost = fee * qty * fill
                book.cash -= cost
                book.fees += cost
                book.pos = {"j": j, "qty": qty, "fill": fill, "stop": stop if brakes else None, "fee": cost,
                            "fund": 0.0, "equity": book.cash + cost}
        p = book.pos
        if p is not None and p["stop"] is not None:
            if p["j"] < j and np.isfinite(ln.kijun[j - 1]):
                p["stop"] = max(p["stop"], float(ln.kijun[j - 1]))
            if o[j] <= p["stop"]:
                close_pos(j, o[j], "stop")
            elif low[j] <= p["stop"]:
                close_pos(j, p["stop"], "stop")
        p = book.pos
        if p is not None and funding is not None and np.isfinite(funding[j]):
            paid = float(funding[j]) / 100 * p["qty"] * c[j]
            book.cash -= paid
            book.funding += paid
            p["fund"] += paid
        p = book.pos
        eq[j - lo] = book.cash + (p["qty"] * (c[j] - p["fill"]) if p is not None else 0.0)
    if book.pos is not None:
        close_pos(hi - 1, c[hi - 1], "fin")
        eq[-1] = book.cash
    return book, eq


@dataclass
class Market:
    frames: dict[str, pd.DataFrame]
    lines: dict[str, Lines]
    gate: dict[str, np.ndarray]
    events: dict[str, np.ndarray]
    funding: dict[str, np.ndarray]


def regime_gate(btc_close: pd.Series, days: pd.DatetimeIndex) -> np.ndarray:
    """True on day j when BTC's close of day j-1 is above the mean of its last 50 closes (unknown: open)."""
    sma = btc_close.rolling(REGIME_SMA).mean()
    above = (btc_close > sma).where(sma.notna(), True).shift(1, fill_value=True)
    return above.reindex(days, fill_value=True).to_numpy(bool)


def event_days(days: pd.DatetimeIndex) -> np.ndarray:
    ev = {e.floor("D") for e in rm.macro_events()}
    return np.array([d in ev for d in days])


def daily_funding(rates: pd.Series, days: pd.DatetimeIndex) -> np.ndarray:
    """% paid each UTC day (sum of the 8-hour payments); the desk's 0.01% per 8 h where there is no data."""
    if rates is None or rates.empty:
        return np.full(len(days), 3 * tw.FUNDING_PER_8H * 100)
    per_day = rates.groupby(rates.index.floor("D")).sum()
    return per_day.reindex(days).fillna(3 * tw.FUNDING_PER_8H * 100).to_numpy(float)


def prepare(frames: dict[str, pd.DataFrame], funding: dict[str, pd.Series]) -> Market:
    btc = frames["btc"]["close"]
    return Market(frames, {k: ichimoku(f) for k, f in frames.items()},
                  {k: regime_gate(btc, f.index) for k, f in frames.items()},
                  {k: event_days(f.index) for k, f in frames.items()},
                  {k: daily_funding(funding.get(k, pd.Series(dtype=float)), f.index) for k, f in frames.items()})


def run_row(mk: Market, coins: tuple[str, ...], brakes: bool, mult: float, a: str, b: str) -> tuple[list[Book], pd.Series]:
    books, curves = [], []
    for k in coins:
        f = mk.frames[k]
        lo = max(1, int(f.index.searchsorted(pd.Timestamp(a, tz="UTC"))))
        hi = int(f.index.searchsorted(pd.Timestamp(b, tz="UTC")))
        book, eq = simulate(f, mk.lines[k], lo, hi, CAPITAL / len(coins), brakes, mult, mk.gate[k], mk.events[k],
                            mk.funding[k])
        books.append(book)
        curves.append(pd.Series(eq, index=f.index[lo:hi]))
    total = pd.concat(curves, axis=1).ffill().fillna(CAPITAL / len(coins)).sum(axis=1)
    return books, total


def max_dd_pct(eq: pd.Series, capital: float) -> float:
    path = pd.concat([pd.Series([capital]), eq.reset_index(drop=True)])
    return float((1 - path / path.cummax()).max() * 100)


def summarize(books: list[Book], eq: pd.Series, n: int, capital: float = CAPITAL) -> dict:
    trades = [t for b in books for t in b.trades]
    rets = [t["ret_pct"] for t in trades]
    net, dd = float(eq.iloc[-1] / capital * 100 - 100), max_dd_pct(eq, capital)
    r = rd.daily_returns(list(eq.to_numpy()), eq.index, capital)
    m = rd.moments(r)
    q = eq.groupby(eq.index.tz_localize(None).to_period("Q")).last()
    q0 = pd.concat([pd.Series([capital]), q.iloc[:-1].reset_index(drop=True)]).to_numpy()
    whys: dict[str, int] = {}
    for t in trades:
        whys[t["why"]] = whys.get(t["why"], 0) + 1
    in_market = sum(1 for b in books for t in b.trades
                    for _ in pd.date_range(t["in"], t["out"], inclusive="left")) / max(1, len(eq) * len(books))
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "trades": len(trades), "win_rate": round(float(np.mean([x > 0 for x in rets]) * 100), 1) if rets else 0.0,
            "avg_trade_pct": round(float(np.mean(rets)), 3) if rets else 0.0, "exits": whys,
            "in_market_pct": round(in_market * 100, 1),
            "fees_usd": round(sum(b.fees for b in books), 2), "funding_usd": round(sum(b.funding for b in books), 2),
            "sharpe_anual": round(m["sr_dia"] * np.sqrt(365), 2),
            "dsr": round(rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n, 1 / m["T"]), 3)
            if m["T"] > 2 and m["sr_dia"] != 0 else 0.0,
            "quarters": [round(float(v), 1) for v in (q.to_numpy() / q0 * 100 - 100)],
            "daily_equity": {str(d.date()): round(float(v), 2) for d, v in eq.items()}}


def hold(f: pd.DataFrame, a: str, b: str) -> dict:
    seg = f[(f.index >= pd.Timestamp(a, tz="UTC")) & (f.index < pd.Timestamp(b, tz="UTC"))]
    eq = seg["close"] / seg["open"].iloc[0] * CAPITAL
    net, dd = float(eq.iloc[-1] / CAPITAL * 100 - 100), max_dd_pct(eq, CAPITAL)
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None}


def year(mk: Market, a: str, b: str, n: int) -> dict:
    rows = {}
    for key, (_, coins, brakes, mult, _) in ROWS.items():
        books, eq = run_row(mk, coins, brakes, mult, a, b)
        rows[key] = summarize(books, eq, n)
    return {"from": a, "to": b, "desk": DESK[a], "rows": rows, "hold_btc": hold(mk.frames["btc"], a, b),
            "hold_eth": hold(mk.frames["eth"], a, b)}


def passes(years: list[dict], key: str) -> bool:
    beats = all((y["rows"][key]["net_dd"] or -99) > y["desk"] for y in years)
    return beats and years[-1]["rows"][key]["dsr"] >= rd.PASS_DSR


def render(years: list[dict], n: int) -> str:
    L = ["# Nube de Ichimoku en BTC y ETH diario", "",
         "Preregistro: `docs/research/ichimoku/PREREGISTRO.md`, escrito antes de correr. 9/26/52 fijos, solo compras, "
         "órdenes en la apertura siguiente; 0,05% de comisión y 0,02% de deslizamiento por lado; financiación real; "
         f"1.000 USDT. Sharpe deflactado con N = {n} decisorias.", "", "## Veredicto", ""]
    for k, v in ROWS.items():
        if not v[4]:
            continue
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
              "| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Ops | Acierto | Media por op. | Días dentro | Salidas | "
              "Comisiones | Financiación | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            ex = ", ".join(f"{w} {c}" for w, c in sorted(r["exits"].items()))
            L.append(f"| {ROWS[k][0]} | {'decisoria' if ROWS[k][4] else 'sensibilidad'} | {r['net_pct']:+.1f}% | "
                     f"{r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | {r['win_rate']}% | "
                     f"{r['avg_trade_pct']:+.2f}% | {r['in_market_pct']}% | {ex} | {r['fees_usd']} | "
                     f"{r['funding_usd']} | {r['sharpe_anual']} | {r['dsr']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Precio del contado de Binance; financiación del perpetuo. La media por operación es sobre el capital de "
          "la moneda. El capital diario está en el JSON. Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def load() -> tuple[dict[str, pd.DataFrame], dict[str, pd.Series]]:
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    frames = {k: rdv.fetch_klines(s, "1d", start, end) for k, s in SYMBOLS.items()}
    funding = {k: tw.fetch_funding(s, start, end) for k, s in SYMBOLS.items()}
    return frames, funding


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Nube de Ichimoku en BTC y ETH diario (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    frames, funding = load()
    mk = prepare(frames, funding)
    years = [year(mk, a, b, args.decisorias) for a, b in YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"ichimoku_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"ichimoku_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
