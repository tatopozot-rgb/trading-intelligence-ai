"""
MACD crossover on BTC and ETH daily candles (leader, 2026-10-20), research only.

Preregistered in docs/research/macd/PREREGISTRO.md before any run; rules from docs/inteligencia/BOTS_PUBLICOS.md
(2026-10-20). Classic 12/26/9, never tuned. Long only: buy at the next open after the MACD crosses above its signal,
sell at the next open after it crosses below. Version A as is (100%, 1x, no stop); version B with the desk's brakes
(the desk stop from plan_exits over 300 closed daily candles with 2% risk, regime b, no entries on FOMC/CPI days).
Desk costs and real funding. Shares the daily helpers of research_ichimoku. Public Binance data only: no account,
no key, no orders. Nothing touches config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_ichimoku as ri
from trading_intelligence.backtesting import two_way_backtest as tw
from trading_intelligence.strategy.exit_plan import plan_exits

FAST, SLOW, SIGNAL = 12, 26, 9
FEE, SLIP = tw.FEE, 0.0002
DESK_RISK, DESK_WINDOW = 0.02, 300
CAPITAL = 1000.0
DECISIVE_N = 288
YEARS = ri.YEARS
WARM_FROM = "2023-10-01"
DESK = ri.DESK
SYMBOLS = ri.SYMBOLS
OUT_DIR = Path("docs/research/macd")
ROWS = ri.ROWS  # same eight rows: A/B on BTC, ETH and both, plus both at costs x2


@dataclass
class Cross:
    up: np.ndarray  # True on the close where the MACD crosses above its signal
    down: np.ndarray


def macd(close: pd.Series) -> Cross:
    line = close.ewm(span=FAST, adjust=False).mean() - close.ewm(span=SLOW, adjust=False).mean()
    sig = line.ewm(span=SIGNAL, adjust=False).mean()
    above = (line > sig).to_numpy()
    below = (line < sig).to_numpy()
    prev_above, prev_below = np.r_[False, above[:-1]], np.r_[False, below[:-1]]
    up = above & ~prev_above
    down = below & ~prev_below
    up[0] = down[0] = False
    return Cross(up, down)


def desk_stop(f: pd.DataFrame, j: int, px: float) -> float:
    window = f.iloc[max(0, j - DESK_WINDOW):j]  # closed candles only
    return float(plan_exits(window, Decimal(str(px)), side="BUY").stop)


def simulate(f: pd.DataFrame, x: Cross, lo: int, hi: int, capital: float, brakes: bool, mult: float = 1.0,
             gate: Optional[np.ndarray] = None, events: Optional[np.ndarray] = None,
             funding: Optional[np.ndarray] = None, stop_fn=desk_stop) -> tuple[ri.Book, np.ndarray]:
    """One coin over days [lo, hi). Day j-1's close decides; day j's open acts."""
    o, low, c = (f[k].to_numpy(float) for k in ("open", "low", "close"))
    days = f.index
    fee, slip = FEE * mult, SLIP * mult
    book = ri.Book(capital)
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
            if x.down[j - 1] or gate_off:
                close_pos(j, o[j], "régimen" if gate_off and not x.down[j - 1] else "señal")
                exited = True
        if book.pos is None and not exited and x.up[j - 1]:
            ok = not brakes or ((gate is None or gate[j]) and (events is None or not events[j]))
            fill = o[j] * (1 + slip)
            stop = stop_fn(f, j, fill) if ok and brakes else None
            if stop is not None and not (np.isfinite(stop) and stop < fill):
                ok = False
            if ok and book.cash > 0:
                qty = book.cash / (fill * (1 + fee))
                if stop is not None:
                    qty = min(qty, DESK_RISK * book.cash / (fill - stop))
                cost = fee * qty * fill
                book.cash -= cost
                book.fees += cost
                book.pos = {"j": j, "qty": qty, "fill": fill, "stop": stop, "fee": cost, "fund": 0.0,
                            "equity": book.cash + cost}
        p = book.pos
        if p is not None and p["stop"] is not None:
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
    cross: dict[str, Cross]
    gate: dict[str, np.ndarray]
    events: dict[str, np.ndarray]
    funding: dict[str, np.ndarray]


def prepare(frames: dict[str, pd.DataFrame], funding: dict[str, pd.Series]) -> Market:
    btc = frames["btc"]["close"]
    return Market(frames, {k: macd(f["close"]) for k, f in frames.items()},
                  {k: ri.regime_gate(btc, f.index) for k, f in frames.items()},
                  {k: ri.event_days(f.index) for k, f in frames.items()},
                  {k: ri.daily_funding(funding.get(k, pd.Series(dtype=float)), f.index) for k, f in frames.items()})


def run_row(mk: Market, coins: tuple[str, ...], brakes: bool, mult: float, a: str, b: str,
            stop_fn=desk_stop) -> tuple[list[ri.Book], pd.Series]:
    books, curves = [], []
    for k in coins:
        f = mk.frames[k]
        lo = max(1, int(f.index.searchsorted(pd.Timestamp(a, tz="UTC"))))
        hi = int(f.index.searchsorted(pd.Timestamp(b, tz="UTC")))
        book, eq = simulate(f, mk.cross[k], lo, hi, CAPITAL / len(coins), brakes, mult, mk.gate[k], mk.events[k],
                            mk.funding[k], stop_fn)
        books.append(book)
        curves.append(pd.Series(eq, index=f.index[lo:hi]))
    total = pd.concat(curves, axis=1).ffill().fillna(CAPITAL / len(coins)).sum(axis=1)
    return books, total


def year(mk: Market, a: str, b: str, n: int) -> dict:
    rows = {}
    for key, (_, coins, brakes, mult, _) in ROWS.items():
        books, eq = run_row(mk, coins, brakes, mult, a, b)
        rows[key] = ri.summarize(books, eq, n)
    return {"from": a, "to": b, "desk": DESK[a], "rows": rows, "hold_btc": ri.hold(mk.frames["btc"], a, b),
            "hold_eth": ri.hold(mk.frames["eth"], a, b)}


def render(years: list[dict], n: int) -> str:
    body = ri.render(years, n)
    head = ("# Cruce del MACD en BTC y ETH diario\n\n"
            "Preregistro: `docs/research/macd/PREREGISTRO.md`, escrito antes de correr. 12/26/9 fijos, solo compras, "
            "órdenes en la apertura siguiente; 0,05% de comisión y 0,02% de deslizamiento por lado; financiación real; "
            f"1.000 USDT. B: stop de la mesa (`plan_exits`, 300 velas diarias) con 2% de riesgo, régimen b y sin "
            f"entradas en días FOMC/IPC. Sharpe deflactado con N = {n} decisorias.\n")
    return head + body[body.index("\n## Veredicto"):]


def load() -> tuple[dict[str, pd.DataFrame], dict[str, pd.Series]]:
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    frames = {k: rdv.fetch_klines(s, "1d", start, end) for k, s in SYMBOLS.items()}
    funding = {k: tw.fetch_funding(s, start, end) for k, s in SYMBOLS.items()}
    return frames, funding


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cruce del MACD en BTC y ETH diario (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    frames, funding = load()
    mk = prepare(frames, funding)
    years = [year(mk, a, b, args.decisorias) for a, b in YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"macd_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"macd_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
