"""
Weekly spot grid bot ("Spot Grid") on BTC and ETH (leader, 2026-10-17), research only.

Preregistered in docs/research/grid/PREREGISTRO.md before any run; the rules are the leader's, fixed in
docs/inteligencia/BOTS_PUBLICOS.md. Every Monday 00:00 UTC the previous grid is closed at market and a new one is laid
out: the open price ±10%, 20 geometric steps, 1/20 of capital per step, buy at the lower level, sell that slice one
level up, nothing new outside the range, no stop, spot 1x. Public Binance 1h candles only: no account, no key, no
orders.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_deflactado as rd
from trading_intelligence.backtesting import research_oro as ro

STEPS = 20
CAPITAL = 1000.0
DECISIVE_N = 266
DESK = {"2024-10-12": 1.67, "2025-10-13": -0.21}
OUT_DIR = Path("docs/research/grid")
SYMBOLS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}


@dataclass(frozen=True)
class GridCosts:
    """fee per side on limit fills, a favorable fill edge on them, and the fee of the Monday market close."""

    fee: float = 0.001
    edge: float = 0.0
    close_fee: float = 0.001


BASE = GridCosts()
MAKER = GridCosts(fee=0.0002, edge=0.0001)

# key: (label, weights, width, costs, decisive)
ROWS = {"btc": ("BTC ±10%, 0,1% por lado", {"btc": 1.0}, 0.10, BASE, True),
        "eth": ("ETH ±10%, 0,1% por lado", {"eth": 1.0}, 0.10, BASE, True),
        "mitad": ("BTC y ETH a mitades ±10%, 0,1% por lado", {"btc": 0.5, "eth": 0.5}, 0.10, BASE, True),
        "btc_maker": ("BTC ±10%, mejor caso maker", {"btc": 1.0}, 0.10, MAKER, False),
        "eth_maker": ("ETH ±10%, mejor caso maker", {"eth": 1.0}, 0.10, MAKER, False),
        "mitad_maker": ("Mitades ±10%, mejor caso maker", {"btc": 0.5, "eth": 0.5}, 0.10, MAKER, False),
        "btc5": ("BTC ±5%", {"btc": 1.0}, 0.05, BASE, False),
        "eth5": ("ETH ±5%", {"eth": 1.0}, 0.05, BASE, False),
        "btc20": ("BTC ±20%", {"btc": 1.0}, 0.20, BASE, False),
        "eth20": ("ETH ±20%", {"eth": 1.0}, 0.20, BASE, False)}


def levels(p0: float, width: float, steps: int = STEPS) -> np.ndarray:
    lo, hi = p0 * (1 - width), p0 * (1 + width)
    return lo * (hi / lo) ** (np.arange(steps + 1) / steps)


class GridBook:
    """One asset's grid. Cell i buys at level i and sells at level i+1; cash and coins are tracked per book."""

    def __init__(self, width: float, costs: GridCosts, cash: float = 0.0) -> None:
        self.width, self.costs, self.cash = width, costs, cash
        self.lv = np.zeros(STEPS + 1)
        self.qty = np.zeros(STEPS)
        self.cost = np.zeros(STEPS)
        self.budget = 0.0
        self.ref = 0.0
        self.round_trip = self.inventory = self.fees = 0.0
        self.trips = self.buys = 0

    def close_all(self, px: float) -> None:
        held = self.qty > 0
        if held.any():
            gross = float(self.qty[held].sum()) * px
            fee = gross * self.costs.close_fee
            self.fees += fee
            self.inventory += gross - fee - float(self.cost[held].sum())
            self.cash += gross - fee
        self.qty[:] = 0.0
        self.cost[:] = 0.0

    def start(self, px: float, cash: float) -> None:
        """Lay out a new grid around px with this much cash (inventory must already be closed)."""
        self.cash = cash
        self.lv = levels(px, self.width)
        self.budget = cash / STEPS
        self.ref = px

    def step(self, high: float, low: float, close: float) -> None:
        sold = np.zeros(STEPS, dtype=bool)
        for i in np.flatnonzero(self.qty > 0):  # bought in an earlier candle
            up = self.lv[i + 1]
            if high > up:
                gross = self.qty[i] * up * (1 + self.costs.edge)
                fee = gross * self.costs.fee
                self.fees += fee
                self.round_trip += gross - fee - self.cost[i]
                self.cash += gross - fee
                self.qty[i] = self.cost[i] = 0.0
                self.trips += 1
                sold[i] = True
        for i in range(STEPS):
            lo = self.lv[i]
            if self.qty[i] > 0 or sold[i] or not (self.ref > lo > low):
                continue
            spend = min(self.budget, self.cash)
            if spend <= 0:
                break
            fill = lo * (1 - self.costs.edge)
            self.qty[i] = spend / (fill * (1 + self.costs.fee))
            self.fees += spend - self.qty[i] * fill
            self.cost[i] = spend
            self.cash -= spend
            self.buys += 1
        self.ref = close

    def value(self, px: float) -> float:
        return self.cash + float(self.qty.sum()) * px


def week_of(t: pd.Timestamp) -> pd.Timestamp:
    return (t - pd.Timedelta(days=t.dayofweek)).floor("D")


def run(frames: dict[str, pd.DataFrame], weights: dict[str, float], width: float, costs: GridCosts,
        capital: float = CAPITAL) -> tuple[dict[str, GridBook], pd.Series]:
    idx = None
    for k in weights:
        idx = frames[k].index if idx is None else idx.intersection(frames[k].index)
    assert idx is not None and len(idx) > 0
    books = {k: GridBook(width, costs) for k in weights}
    o = {k: frames[k]["open"].reindex(idx).to_numpy() for k in weights}
    h = {k: frames[k]["high"].reindex(idx).to_numpy() for k in weights}
    lo = {k: frames[k]["low"].reindex(idx).to_numpy() for k in weights}
    c = {k: frames[k]["close"].reindex(idx).to_numpy() for k in weights}
    equity = np.zeros(len(idx))
    week = None
    for j, t in enumerate(idx):
        w = week_of(t)
        if w != week:
            for k, b in books.items():
                b.close_all(o[k][j])
            total = capital if week is None else sum(b.cash for b in books.values())
            for k, b in books.items():
                b.start(o[k][j], total * weights[k])
            week = w
        for k, b in books.items():
            b.step(h[k][j], lo[k][j], c[k][j])
        equity[j] = sum(b.value(c[k][j]) for k, b in books.items())
    for k, b in books.items():
        b.close_all(c[k][-1])
    equity[-1] = sum(b.cash for b in books.values())
    return books, pd.Series(equity, index=idx)


def max_dd_pct(eq: pd.Series, capital: float) -> float:
    path = pd.concat([pd.Series([capital]), eq.reset_index(drop=True)])
    return float((1 - path / path.cummax()).max() * 100)


def summarize(books: dict[str, GridBook], eq: pd.Series, capital: float, n: int) -> dict:
    net = float(eq.iloc[-1] / capital * 100 - 100)
    dd = max_dd_pct(eq, capital)
    r = rd.daily_returns(list(eq.to_numpy()), eq.index, capital)
    m = rd.moments(r)
    daily = eq.groupby(eq.index.floor("D")).last()
    q = daily.groupby(daily.index.tz_localize(None).to_period("Q")).last()
    q_start = pd.concat([pd.Series([capital]), q.iloc[:-1].reset_index(drop=True)]).to_numpy()
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "round_trip_usd": round(sum(b.round_trip for b in books.values()), 2),
            "inventory_usd": round(sum(b.inventory for b in books.values()), 2),
            "fees_usd": round(sum(b.fees for b in books.values()), 2),
            "trips": sum(b.trips for b in books.values()), "buys": sum(b.buys for b in books.values()),
            "sharpe_anual": round(m["sr_dia"] * np.sqrt(365), 2),
            "dsr": round(rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n, 1 / m["T"]), 3)
            if m["T"] > 2 and m["sr_dia"] != 0 else 0.0,
            "quarters": [round(float(v), 1) for v in (q.to_numpy() / q_start * 100 - 100)],
            "daily_equity": {str(d.date()): round(float(v), 2) for d, v in daily.items()}}


def hold(frame: pd.DataFrame, capital: float = CAPITAL) -> dict:
    eq = frame["close"] / frame["open"].iloc[0] * capital
    net, dd = float(eq.iloc[-1] / capital * 100 - 100), max_dd_pct(eq, capital)
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None}


def year(frames: dict[str, pd.DataFrame], a: str, b: str, n: int) -> dict:
    lo_t, hi_t = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
    seg = {k: f[(f.index >= lo_t) & (f.index < hi_t)] for k, f in frames.items()}
    rows = {}
    for key, (_, weights, width, costs, _) in ROWS.items():
        books, eq = run(seg, weights, width, costs)
        rows[key] = summarize(books, eq, CAPITAL, n)
    return {"from": a, "to": b, "desk": DESK[a], "rows": rows, "hold": {k: hold(f) for k, f in seg.items()}}


def passes(years: list[dict], key: str) -> bool:
    beats = all((y["rows"][key]["net_dd"] or -99) > y["desk"] for y in years)
    return beats and years[-1]["rows"][key]["dsr"] >= rd.PASS_DSR


def render(years: list[dict], n: int) -> str:
    decisive = [k for k, v in ROWS.items() if v[4]]
    L = ["# Bot de cuadrícula semanal al contado (Spot Grid) en BTC y ETH", "",
         "Preregistro: `docs/research/grid/PREREGISTRO.md`, escrito antes de correr. Reglas del líder "
         "(`docs/inteligencia/BOTS_PUBLICOS.md`, 2026-10-17): cada lunes, precio ±10%, 20 escalones geométricos, 1/20 del "
         f"capital por escalón, sin stop, 1x; 1.000 USDT; 0,1% por lado. Sharpe deflactado con N = {n} decisorias.", "",
         "## Veredicto", ""]
    for k in decisive:
        L.append(f"- **{ROWS[k][0]}: {'pasa' if passes(years, k) else 'no pasa'}.** Neto/caída "
                 + " ; ".join(str(y["rows"][k]["net_dd"]) for y in years)
                 + f" contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 {years[-1]['rows'][k]['dsr']} "
                 f"(listón {rd.PASS_DSR}). Idas y vueltas "
                 + " ; ".join(f"{y['rows'][k]['round_trip_usd']:+.0f}" for y in years) + " USDT, inventario "
                 + " ; ".join(f"{y['rows'][k]['inventory_usd']:+.0f}" for y in years) + " USDT.")
    for y in years:
        hb = y["hold"].get("btc", {})
        L += ["", f"## {y['from']} → {y['to']}", "",
              f"Mantener BTC: {hb.get('net_pct', 0):+.1f}% / caída {hb.get('max_dd_pct')}% (neto/caída {hb.get('net_dd')}). "
              f"Mantener ETH: {y['hold'].get('eth', {}).get('net_pct', 0):+.1f}% / caída "
              f"{y['hold'].get('eth', {}).get('max_dd_pct')}%.", "",
              "| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Idas y vueltas (USDT) | Inventario (USDT) | "
              "Comisiones (USDT) | Idas y vueltas (n) | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, r in y["rows"].items():
            L.append(f"| {ROWS[k][0]} | {'decisoria' if ROWS[k][4] else 'sensibilidad'} | {r['net_pct']:+.1f}% | "
                     f"{r['max_dd_pct']}% | {r['net_dd']} | {r['round_trip_usd']:+.1f} | {r['inventory_usd']:+.1f} | "
                     f"{r['fees_usd']:.1f} | {r['trips']} | {r['sharpe_anual']} | {r['dsr']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Las órdenes se llenan solo si la vela cruza el nivel, y no hay compra y venta del mismo escalón en la misma "
          "vela. La comisión del cierre del lunes va dentro del inventario. El capital diario está en el JSON. Un "
          "resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def load() -> dict[str, pd.DataFrame]:
    start = datetime.fromisoformat(ro.YEARS[0][0]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(ro.YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    return {k: rdv.fetch_klines(s, "1h", start, end) for k, s in SYMBOLS.items()}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Bot de cuadrícula semanal en BTC y ETH (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    frames = load()
    years = [year(frames, a, b, args.decisorias) for a, b in ro.YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"grid_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"grid_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
