"""
Real slippage, signal against execution, in basis points (theme 7, leader, 2026-10-17), research only.

Read only: it reads the futures bots' state files and order journals and public Binance futures 1m candles. It
sends no order, needs no key, and its outputs carry prices, times and basis points only (no quantity, no result,
no balance), so they can go to the public repo.

Positive basis points are always against us. Each trade gives two numbers:

- entry: the fill against the reference at the signal. Real bot: Binance's average fill (orders.json) against the
  ask or bid the plan used (the OPEN event). Practice: the simulated fill (the ask or bid) against the open of that
  minute's 1m candle, a stand-in for the mid, so it is about half the spread.
- exit: the fill against the level that closed it. Real bot: Binance's average exit fill (from a read-only export,
  see ``load_real_exits``) against the stop or target. Practice fills at the level exactly by construction, so its
  exit is re-estimated with the 1m gap model: the first 1m candle after the entry that reaches the level fills at
  its open when it opened beyond the level, else at the level. That is a floor: slippage inside the minute is
  unseen.

Compared with the 0.02% (2 bp) per side the backtests assume (research_mesa.SLIPPAGE).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from trading_intelligence.data.binance_public_feed import _urllib_get

ASSUMED_BP = 2.0
FAPI = "https://fapi.binance.com"
OUT_DIR = Path("docs/research/deslizamiento")
MATCH_WINDOW = timedelta(minutes=5)
OPEN_TEXT = re.compile(r"@ (?P<px>[0-9.]+) SL (?P<sl>[0-9.]+) TP (?P<tp>[0-9.]+)")

Candles = Callable[[str, datetime, datetime], pd.DataFrame]


@dataclass
class Trade:
    fuente: str
    symbol: str
    side: str  # BUY or SELL (the entry side)
    opened: str
    closed: Optional[str]
    why: Optional[str]
    entry_ref: Optional[float]
    entry_fill: Optional[float]
    exit_ref: Optional[float]
    exit_fill: Optional[float]

    def entry_bp(self) -> Optional[float]:
        return bp(self.entry_ref, self.entry_fill, self.side, True)

    def exit_bp(self) -> Optional[float]:
        return bp(self.exit_ref, self.exit_fill, self.side, False)


def bp(ref: Optional[float], fill: Optional[float], side: str, entering: bool) -> Optional[float]:
    """Basis points against us: buying above the reference or selling below it is positive."""
    if not ref or fill is None:
        return None
    buying = (side == "BUY") == entering
    return (fill - ref) / ref * 1e4 * (1 if buying else -1)


def _ts(text: str) -> datetime:
    t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def fetch_1m(symbol: str, start: datetime, end: datetime, get: Callable[[str, float], bytes] = _urllib_get) -> pd.DataFrame:
    """Public USDⓈ-M futures 1m candles in [start, end), at most 1500 per call."""
    rows: list[list] = []
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    while cursor < end_ms:
        q = urllib.parse.urlencode({"symbol": symbol, "interval": "1m", "startTime": cursor, "endTime": end_ms - 1,
                                    "limit": 1500})
        page = json.loads(get(f"{FAPI}/fapi/v1/klines?{q}", 30.0))
        if not page:
            break
        rows += page
        cursor = int(page[-1][0]) + 60_000
    frame = pd.DataFrame([{"t": int(k[0]), "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                           "close": float(k[4])} for k in rows])
    if frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    frame["t"] = pd.to_datetime(frame["t"], unit="ms", utc=True)
    return frame.set_index("t")


def gap_fill(bars: pd.DataFrame, level: float, side: str, why: str) -> Optional[float]:
    """1m gap model for a stop or target exit: the first candle that reaches the level fills at its open if it
    opened beyond it (against us for a stop, for us for a target), else at the level."""
    long = side == "BUY"
    stop = why.startswith("stop")
    below = (long and stop) or (not long and not stop)  # the level is crossed going down
    for _, b in bars.iterrows():
        if below and b["low"] <= level:
            return min(float(b["open"]), level)
        if not below and b["high"] >= level:
            return max(float(b["open"]), level)
    return None


def paper_trades(state_path: Path, fuente: str, candles: Optional[Candles] = None) -> list[Trade]:
    """Closed trades of a PaperFuturesBroker book (its state file holds "closed")."""
    book = json.loads(Path(state_path).read_text(encoding="utf-8"))
    out = []
    for row in book.get("closed", []):
        side, why = str(row["side"]), str(row.get("why", ""))
        opened, closed = row.get("opened"), row.get("at")
        entry_ref = exit_ref = exit_fill = None
        exit_px = float(row["exit"])
        if candles is not None and opened and closed:
            t0, t1 = _ts(opened), _ts(closed)
            first = candles(row["symbol"], t0.replace(second=0, microsecond=0), t0 + timedelta(minutes=1))
            entry_ref = float(first["open"].iloc[0]) if len(first) else None
            if why in ("stop", "meta"):
                bars = candles(row["symbol"], t0.replace(second=0, microsecond=0) + timedelta(minutes=1),
                               t1 + timedelta(minutes=1))
                exit_ref, exit_fill = exit_px, gap_fill(bars, exit_px, side, why)
            else:  # closed at the bid or ask on a contrary signal
                last = candles(row["symbol"], t1.replace(second=0, microsecond=0), t1 + timedelta(minutes=1))
                exit_ref, exit_fill = (float(last["open"].iloc[0]) if len(last) else None), exit_px
        out.append(Trade(fuente, row["symbol"], side, str(opened), str(closed), why, entry_ref, float(row["entry"]),
                         exit_ref, exit_fill))
    return out


def load_real_exits(path: Optional[Path]) -> list[dict]:
    """A CSV exported read-only on the PC from Binance's own fills: symbol, closed, why, exit_ref, exit_fill
    (exit_ref is the stop or target that closed it; exit_fill the average exit price)."""
    if path is None or not Path(path).exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def real_trades(state_path: Path, orders_path: Path, exits: list[dict], fuente: str = "real") -> list[Trade]:
    """Entries of the real bot: each OPEN event (the plan's ask or bid) matched with the filled market order
    of the same symbol and side within MATCH_WINDOW (orders.json, Binance's avgPrice). Exits from ``exits``."""
    state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    orders = json.loads(Path(orders_path).read_text(encoding="utf-8")) if Path(orders_path).exists() else {}
    entries = [o for o in orders.values() if isinstance(o, dict) and o.get("state") == "FILLED"
               and not o.get("reduce_only") and float(o.get("avg") or 0) > 0]
    out = []
    for ev in state.get("events", []):
        m = OPEN_TEXT.search(str(ev.get("text", "")))
        if ev.get("kind") != "OPEN" or m is None:
            continue
        sym, side, at = str(ev.get("symbol")), str(ev.get("side")), _ts(ev["at"])
        near = [o for o in entries if o.get("symbol") == sym and o.get("side") == side
                and abs(_ts(o["at"]) - at) <= MATCH_WINDOW]
        fill = float(min(near, key=lambda o: abs(_ts(o["at"]) - at))["avg"]) if near else None
        later = sorted((x for x in exits if x.get("symbol") == sym and _ts(x["closed"]) > at),
                       key=lambda x: _ts(x["closed"]))
        x = later[0] if later else None
        out.append(Trade(fuente, sym, side, at.isoformat(), x["closed"] if x else None, x.get("why") if x else None,
                         float(m.group("px")), fill, float(x["exit_ref"]) if x else None,
                         float(x["exit_fill"]) if x else None))
    return out


def describe(values: list[Optional[float]], seed: int = 7) -> dict:
    v = np.array([x for x in values if x is not None], dtype=float)
    if len(v) == 0:
        return {"n": 0}
    boot = np.random.default_rng(seed).choice(v, size=(2000, len(v))).mean(axis=1) if len(v) > 1 else v
    return {"n": int(len(v)), "media_bp": round(float(v.mean()), 2), "mediana_bp": round(float(np.median(v)), 2),
            "p90_bp": round(float(np.percentile(v, 90)), 2), "peor_bp": round(float(v.max()), 2),
            "ic90_media_bp": [round(float(np.percentile(boot, 5)), 2), round(float(np.percentile(boot, 95)), 2)]}


def summarize(trades: list[Trade]) -> dict:
    out: dict[str, dict] = {}
    for fuente in sorted({t.fuente for t in trades}):
        ts = [t for t in trades if t.fuente == fuente]
        out[fuente] = {"entrada": describe([t.entry_bp() for t in ts]),
                       "salida": describe([t.exit_bp() for t in ts]),
                       "salida_por_motivo": {w: describe([t.exit_bp() for t in ts if t.why == w])
                                             for w in sorted({str(t.why) for t in ts if t.why})}}
    return out


def render(summary: dict, n_trades: int) -> str:
    L = ["# Deslizamiento real: señal contra ejecución", "",
         f"Método: `trading_intelligence/backtesting/research_deslizamiento.py`. {n_trades} operaciones. Puntos básicos "
         f"(1 pb = 0,01%); positivo es en contra. Supuesto de los backtests: {ASSUMED_BP:g} pb por lado.", "",
         "| Fuente | Lado | Ops | Media pb | IC 90% de la media | Mediana | P90 | Peor | ¿Peor que 2 pb? |",
         "|---|---|---|---|---|---|---|---|---|"]
    for fuente, s in summary.items():
        rows = [("entrada", s["entrada"]), ("salida", s["salida"])] + \
               [(f"salida · {w}", d) for w, d in s["salida_por_motivo"].items()]
        for lado, d in rows:
            if not d.get("n"):
                L.append(f"| {fuente} | {lado} | 0 | — | — | — | — | — | sin datos |")
                continue
            lo, hi = d["ic90_media_bp"]
            verdict = "sí" if lo > ASSUMED_BP else ("no" if hi < ASSUMED_BP else "no se sabe aún")
            L.append(f"| {fuente} | {lado} | {d['n']} | {d['media_bp']} | {lo} a {hi} | {d['mediana_bp']} | "
                     f"{d['p90_bp']} | {d['peor_bp']} | {verdict} |")
    L += ["", "Práctica: la entrada mide medio spread contra la apertura del minuto; la salida por stop o meta usa el "
          "modelo de hueco de 1 minuto (un piso: lo que pasa dentro del minuto no se ve). Real: los llenados de "
          "Binance. Con menos de 30 operaciones por fuente el intervalo es ancho y no decide nada."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Deslizamiento real, señal contra ejecución (solo lectura)")
    p.add_argument("--practica", nargs="*", default=[], metavar="NOMBRE=state.json",
                   help="libros de práctica, p. ej. practica_1x=live_runs\\futures_auto\\paper.json")
    p.add_argument("--real-estado", type=Path, help="state.json del bot real")
    p.add_argument("--real-ordenes", type=Path, help="orders.json del bot real")
    p.add_argument("--real-salidas", type=Path, help="CSV de salidas reales (symbol, closed, why, exit_ref, exit_fill)")
    p.add_argument("--sin-velas", action="store_true", help="no bajar velas de 1 minuto (práctica sin referencia)")
    p.add_argument("--salida", type=Path, default=OUT_DIR)
    args = p.parse_args(argv)
    candles = None if args.sin_velas else fetch_1m
    trades: list[Trade] = []
    for item in args.practica:
        name, _, path = item.partition("=")
        trades += paper_trades(Path(path), name, candles)
    if args.real_estado is not None:
        trades += real_trades(args.real_estado, args.real_ordenes or args.real_estado.with_name("orders.json"),
                              load_real_exits(args.real_salidas))
    summary = summarize(trades)
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    with open(args.salida / f"deslizamiento_{stamp}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[*asdict(trades[0]).keys(), "entry_bp", "exit_bp"] if trades else ["vacío"])
        w.writeheader()
        for t in trades:
            w.writerow({**asdict(t), "entry_bp": t.entry_bp(), "exit_bp": t.exit_bp()})
    (args.salida / f"deslizamiento_{stamp}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    report = render(summary, len(trades))
    (args.salida / f"deslizamiento_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
