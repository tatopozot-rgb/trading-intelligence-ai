"""
freqtrade's FSupertrendStrategy on BTC and ETH (leader, 2026-10-18), research only.

Preregistered in docs/research/supertrend/PREREGISTRO.md before any run; rules from docs/inteligencia/BOTS_PUBLICOS.md
(2026-10-18) and the strategy's code at freqtrade-strategies b8a90be, parameters as published (no re-fit). 1h
candles, three "buy" Supertrends all up = long, three "sell" all down = short, exits on the second Supertrend of the
other set, a -26.5% stop, a time-based ROI table and a trailing stop. Version A as coded; version B with the desk's
brakes (the desk's 1R stop and 2% risk, regime b, no entries near FOMC/CPI). Desk costs and real funding. Public
Binance data only: no account, no key, no orders. Nothing touches config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_deflactado as rd
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import two_way_backtest as tw
from trading_intelligence.strategy.exit_plan import plan_exits

BUY = ((4, 8), (7, 9), (1, 8))  # (multiplier, period)
SELL = ((1, 16), (3, 18), (6, 18))
STOPLOSS = 0.265
ROI = ((2, 0.025), (1, 0.05), (0, 0.10))  # (age in whole hours at the candle's open, minimum profit)
TRAIL, TRAIL_OFFSET = 0.05, 0.10
FEE, SLIP = tw.FEE, 0.0002
DESK_RISK, DESK_WINDOW = 0.02, 300
CAPITAL = 1000.0
DECISIVE_N = 272
YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
WARM_FROM = "2024-06-01"
DESK = {"2024-10-12": 1.67, "2025-10-13": -0.21}
SYMBOLS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
OUT_DIR = Path("docs/research/supertrend")
# key: (label, coins, brakes, cost multiplier, decisive)
ROWS = {"a_btc": ("A tal cual, BTC", ("btc",), False, 1.0, True),
        "a_eth": ("A tal cual, ETH", ("eth",), False, 1.0, True),
        "a_juntas": ("A tal cual, BTC y ETH", ("btc", "eth"), False, 1.0, True),
        "b_btc": ("B con frenos, BTC", ("btc",), True, 1.0, True),
        "b_eth": ("B con frenos, ETH", ("eth",), True, 1.0, True),
        "b_juntas": ("B con frenos, BTC y ETH", ("btc", "eth"), True, 1.0, True),
        "a_juntas_x2": ("A juntas, costos ×2", ("btc", "eth"), False, 2.0, False),
        "b_juntas_x2": ("B juntas, costos ×2", ("btc", "eth"), True, 2.0, False)}


def supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray, m: int, p: int) -> np.ndarray:
    """+1 up, -1 down, 0 unknown: the strategy's own supertrend(), line by line."""
    n = len(close)
    prev_c = np.r_[np.nan, close[:-1]]
    tr = np.nanmax(np.vstack([high - low, np.abs(high - prev_c), np.abs(low - prev_c)]), axis=0)
    tr[0] = np.nan  # talib TRANGE starts at the second candle
    atr = pd.Series(tr).rolling(p).mean().to_numpy()
    mid = (high + low) / 2
    bub, blb = mid + m * atr, mid - m * atr
    fub, flb = np.zeros(n), np.zeros(n)
    for i in range(p, n):
        fub[i] = bub[i] if bub[i] < fub[i - 1] or close[i - 1] > fub[i - 1] else fub[i - 1]
        flb[i] = blb[i] if blb[i] > flb[i - 1] or close[i - 1] < flb[i - 1] else flb[i - 1]
    st = np.zeros(n)
    for i in range(p, n):
        if st[i - 1] == fub[i - 1] and close[i] <= fub[i]:
            st[i] = fub[i]
        elif st[i - 1] == fub[i - 1] and close[i] > fub[i]:
            st[i] = flb[i]
        elif st[i - 1] == flb[i - 1] and close[i] >= flb[i]:
            st[i] = flb[i]
        elif st[i - 1] == flb[i - 1] and close[i] < flb[i]:
            st[i] = fub[i]
        else:
            st[i] = 0.0
    with np.errstate(invalid="ignore"):
        return np.where(st > 0, np.where(close < st, -1, 1), 0).astype(np.int8)


@dataclass
class Signals:
    enter_long: np.ndarray
    enter_short: np.ndarray
    exit_long: np.ndarray
    exit_short: np.ndarray


def signals(f: pd.DataFrame) -> Signals:
    h, lo, c, v = (f[k].to_numpy(float) for k in ("high", "low", "close", "volume"))
    b = [supertrend(h, lo, c, m, p) for m, p in BUY]
    s = [supertrend(h, lo, c, m, p) for m, p in SELL]
    vol = v > 0
    return Signals((b[0] == 1) & (b[1] == 1) & (b[2] == 1) & vol, (s[0] == -1) & (s[1] == -1) & (s[2] == -1) & vol,
                   s[1] == -1, b[1] == 1)


def roi_at(age: int) -> float:
    return next(r for a, r in ROI if age >= a)


@dataclass
class Book:
    cash: float
    trades: list[dict] = field(default_factory=list)
    fees: float = 0.0
    funding: float = 0.0
    pos: Optional[dict] = None


def desk_stop(f: pd.DataFrame, j: int, px: float, side: int) -> float:
    window = f.iloc[max(0, j - DESK_WINDOW):j]  # closed candles only
    plan = plan_exits(window, Decimal(str(px)), side="BUY" if side > 0 else "SELL")
    return float(plan.stop)


def simulate(f: pd.DataFrame, sig: Signals, lo: int, hi: int, capital: float, brakes: bool, mult: float = 1.0,
             gate: Optional[np.ndarray] = None, events: Optional[np.ndarray] = None,
             funding: Optional[pd.Series] = None) -> tuple[Book, np.ndarray]:
    """One coin over candles [lo, hi). Signals of candle j-1 act at candle j's open."""
    o, h, low, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    times = f.index
    fee, slip = FEE * mult, SLIP * mult
    fund_t = funding.index.as_unit("ns").asi8 if funding is not None and len(funding) else np.array([], np.int64)
    fund_v = funding.to_numpy(float) if funding is not None and len(funding) else np.array([])
    book = Book(capital)
    eq = np.zeros(hi - lo)

    def close_pos(j: int, px: float, why: str) -> None:
        p = book.pos
        assert p is not None
        side, qty = p["side"], p["qty"]
        fill = px * (1 - slip * side)
        cost = fee * qty * fill
        pnl = side * qty * (fill - p["fill"]) - cost
        book.cash += pnl
        book.fees += cost
        net = pnl - p["fee"] + p["fund"]
        book.trades.append({"in": str(times[p["j"]]), "out": str(times[j]), "side": side, "why": why,
                            "ret_pct": round(net / p["equity"] * 100, 3)})
        book.pos = None

    for j in range(lo, hi):
        exited = False
        p = book.pos
        if p is not None:
            gate_off = brakes and p["side"] > 0 and gate is not None and gate[j] < 0
            if gate_off or (sig.exit_long[j - 1] if p["side"] > 0 else sig.exit_short[j - 1]):
                close_pos(j, o[j], "régimen" if gate_off else "señal")
                exited = True
        if book.pos is None and not exited and j - 1 >= 0:
            el, es = bool(sig.enter_long[j - 1]), bool(sig.enter_short[j - 1])
            side = 1 if el and not es and not sig.exit_long[j - 1] else \
                -1 if es and not el and not sig.exit_short[j - 1] else 0
            if brakes and side != 0:
                if side < 0 or (gate is not None and gate[j] < 0) or (events is not None and events[j]):
                    side = 0
            if side != 0 and book.cash > 0:
                fill = o[j] * (1 + slip * side)
                if brakes:
                    stop = desk_stop(f, j, o[j], side)
                    qty = min(DESK_RISK * book.cash / abs(fill - stop), book.cash / (fill * (1 + fee)))
                else:
                    stop = fill * (1 - STOPLOSS * side)
                    qty = book.cash / (fill * (1 + fee))
                cost = fee * qty * fill
                book.cash -= cost
                book.fees += cost
                book.pos = {"j": j, "side": side, "qty": qty, "fill": fill, "stop0": stop, "peak": fill,
                            "fee": cost, "fund": 0.0, "equity": book.cash + cost}
        p = book.pos
        if p is not None:
            side, fill = p["side"], p["fill"]
            age = j - p["j"]
            ext = p["peak"]  # best price of earlier candles
            gain = side * (ext - fill) / fill
            trail = ext * (1 - side * (TRAIL if gain >= TRAIL_OFFSET else STOPLOSS))
            stop = max(p["stop0"], trail) if side > 0 else min(p["stop0"], trail)
            target = fill * (1 + side * roi_at(age))
            if (side > 0 and o[j] <= stop) or (side < 0 and o[j] >= stop):
                close_pos(j, o[j], "stop")
            elif (side > 0 and low[j] <= stop) or (side < 0 and h[j] >= stop):
                close_pos(j, stop, "stop")
            elif (side > 0 and o[j] >= target) or (side < 0 and o[j] <= target):
                close_pos(j, o[j], "roi")
            elif (side > 0 and h[j] >= target) or (side < 0 and low[j] <= target):
                close_pos(j, target, "roi")
            else:
                p["peak"] = max(ext, h[j]) if side > 0 else min(ext, low[j])
                t0 = times[j].value
                a, b = np.searchsorted(fund_t, t0), np.searchsorted(fund_t, t0 + 3_600_000_000_000)
                if b > a:
                    paid = side * float(fund_v[a:b].sum()) / 100 * p["qty"] * c[j]
                    book.cash -= paid
                    book.funding += paid
                    p["fund"] -= paid
        p = book.pos
        eq[j - lo] = book.cash + (p["side"] * p["qty"] * (c[j] - p["fill"]) if p is not None else 0.0)
    if book.pos is not None:
        close_pos(hi - 1, c[hi - 1], "fin")
        eq[-1] = book.cash
    return book, eq


@dataclass
class Market:
    frames: dict[str, pd.DataFrame]
    sig: dict[str, Signals]
    gate: dict[str, np.ndarray]
    events: dict[str, np.ndarray]
    funding: dict[str, pd.Series]


def prepare(frames: dict[str, pd.DataFrame], btc_d1: pd.Series, funding: dict[str, pd.Series]) -> Market:
    ev = rm.macro_events()
    gate, events = {}, {}
    for k, f in frames.items():
        t = f.index.as_unit("ns").asi8
        g = rm.trend(btc_d1, pd.Timedelta(days=1), 50, t)
        gate[k] = np.where(np.isnan(g), 1, g)
        events[k] = rm.near_event(t, ev, rm.EVENT_HOURS)
    return Market(frames, {k: signals(f) for k, f in frames.items()}, gate, events, funding)


def run_row(mk: Market, coins: tuple[str, ...], brakes: bool, mult: float, a: str, b: str) -> tuple[list[Book], pd.Series]:
    books, curves = [], []
    for k in coins:
        f = mk.frames[k]
        lo = int(f.index.searchsorted(pd.Timestamp(a, tz="UTC")))
        hi = int(f.index.searchsorted(pd.Timestamp(b, tz="UTC")))
        book, eq = simulate(f, mk.sig[k], max(lo, 1), hi, CAPITAL / len(coins), brakes, mult, mk.gate[k],
                            mk.events[k], mk.funding.get(k))
        books.append(book)
        curves.append(pd.Series(eq, index=f.index[max(lo, 1):hi]))
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
    daily = eq.groupby(eq.index.floor("D")).last()
    q = daily.groupby(daily.index.tz_localize(None).to_period("Q")).last()
    q0 = pd.concat([pd.Series([capital]), q.iloc[:-1].reset_index(drop=True)]).to_numpy()
    whys: dict[str, int] = {}
    for t in trades:
        whys[t["why"]] = whys.get(t["why"], 0) + 1
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "trades": len(trades), "longs": sum(t["side"] > 0 for t in trades),
            "shorts": sum(t["side"] < 0 for t in trades),
            "win_rate": round(float(np.mean([x > 0 for x in rets]) * 100), 1) if rets else 0.0,
            "avg_trade_pct": round(float(np.mean(rets)), 3) if rets else 0.0, "exits": whys,
            "fees_usd": round(sum(b.fees for b in books), 2), "funding_usd": round(sum(b.funding for b in books), 2),
            "sharpe_anual": round(m["sr_dia"] * np.sqrt(365), 2),
            "dsr": round(rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n, 1 / m["T"]), 3)
            if m["T"] > 2 and m["sr_dia"] != 0 else 0.0,
            "quarters": [round(float(v), 1) for v in (q.to_numpy() / q0 * 100 - 100)],
            "daily_equity": {str(d.date()): round(float(v), 2) for d, v in daily.items()}}


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
    return {"from": a, "to": b, "desk": DESK[a], "rows": rows, "hold_btc": hold(mk.frames["btc"], a, b)}


def passes(years: list[dict], key: str) -> bool:
    beats = all((y["rows"][key]["net_dd"] or -99) > y["desk"] for y in years)
    return beats and years[-1]["rows"][key]["dsr"] >= rd.PASS_DSR


def render(years: list[dict], n: int) -> str:
    L = ["# Supertrend de freqtrade (FSupertrendStrategy) en BTC y ETH", "",
         "Preregistro: `docs/research/supertrend/PREREGISTRO.md`, escrito antes de correr. Parámetros del código tal "
         "cual (salieron de una optimización: riesgo alto de sobreajuste). Velas de 1 hora; 0,05% de comisión y 0,02% "
         f"de deslizamiento por lado; financiación real; 1.000 USDT. Sharpe deflactado con N = {n} decisorias.", "",
         "## Veredicto", ""]
    for k, v in ROWS.items():
        if not v[4]:
            continue
        L.append(f"- **{v[0]}: {'pasa' if passes(years, k) else 'no pasa'}.** Neto/caída "
                 + " ; ".join(str(y["rows"][k]["net_dd"]) for y in years)
                 + f" contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 {years[-1]['rows'][k]['dsr']} "
                 f"(listón {rd.PASS_DSR}); operaciones " + " ; ".join(str(y["rows"][k]["trades"]) for y in years)
                 + (" (muestra corta)" if any(y["rows"][k]["trades"] < 100 for y in years) else "") + ".")
    for y in years:
        hb = y["hold_btc"]
        L += ["", f"## {y['from']} → {y['to']}", "",
              f"Mantener BTC: {hb['net_pct']:+.1f}% / caída {hb['max_dd_pct']}% (neto/caída {hb['net_dd']}).", "",
              "| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Ops | Largos/cortos | Acierto | Media por op. | "
              "Salidas | Comisiones | Financiación | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            ex = ", ".join(f"{w} {c}" for w, c in sorted(r["exits"].items()))
            L.append(f"| {ROWS[k][0]} | {'decisoria' if ROWS[k][4] else 'sensibilidad'} | {r['net_pct']:+.1f}% | "
                     f"{r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | {r['longs']}/{r['shorts']} | "
                     f"{r['win_rate']}% | {r['avg_trade_pct']:+.3f}% | {ex} | {r['fees_usd']} | {r['funding_usd']} | "
                     f"{r['sharpe_anual']} | {r['dsr']} | " + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Precio del contado de Binance; financiación del perpetuo. En una vela que toca el stop y la meta cuenta el "
          "stop. La media por operación es sobre el capital de la moneda. El capital diario está en el JSON. Un "
          "resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def load() -> tuple[dict[str, pd.DataFrame], pd.Series, dict[str, pd.Series]]:
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    frames = {k: rdv.fetch_klines(s, "1h", start, end) for k, s in SYMBOLS.items()}
    btc_d1 = rdv.fetch_klines("BTCUSDT", "1d", start - timedelta(days=80), end)["close"]
    funding = {k: tw.fetch_funding(s, start, end) for k, s in SYMBOLS.items()}
    return frames, btc_d1, funding


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Supertrend de freqtrade en BTC y ETH (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    frames, btc_d1, funding = load()
    mk = prepare(frames, btc_d1, funding)
    years = [year(mk, a, b, args.decisorias) for a, b in YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"supertrend_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"supertrend_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
