"""
"Experimento horarios": 2-hour UTC windows on 20-minute bars, PAPER only.

Pre-registered in docs/PREREG_HORARIOS.md before any result was seen; the constants
below are that document. Research only: public klines, no account, no key, no orders.

For one UTC day, every window (00:00, 02:00, ... 22:00 UTC) x symbol x strategy starts
flat, decides at :00/:20/:40 with the repo's own strategy classes on 20-minute bars,
and is force-closed at the window's last close. Costs: 0.1% per side + 5 bps slippage,
fixed 10 USDT per trade, reported as net % per trade.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
from scipy import stats

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.regime.detector import Regime, detect_regime
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.router import StrategyRouter, default_router
from trading_intelligence.strategy.strategies.bollinger_reversion import BollingerReversion

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
           "LINKUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT", "PAXGUSDT")
STRATEGIES = ("tendencia", "rango", "baseline")
BAR = pd.Timedelta(minutes=20)
WINDOW_HOURS = 2
WINDOWS = tuple(range(0, 24, WINDOW_HOURS))
BARS_PER_WINDOW = WINDOW_HOURS * 3
HISTORY_BARS = 500
WARMUP_DAYS = 8
FEE = 0.001
SLIP = 0.0005
NOTIONAL_USDT = 10.0
LOCAL_OFFSET_H = -5  # owner's probable local time (Ecuador)
FORWARD_START, FORWARD_END = date(2026, 10, 10), date(2026, 10, 23)
MIN_TRADES_PER_HALF = 7
BH_Q = 0.10
OUT_DIR = Path("docs/experimento_horarios")

Fetcher = Callable[[str, datetime, datetime], pd.DataFrame]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def fetch_5m(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    rdv.INTERVAL_MS.setdefault("5m", 300_000)
    return rdv.fetch_klines(symbol, "5m", start, end)


def to_20m(df5: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """20-minute bars opening at :00/:20/:40 UTC; bars missing any 5m bar are dropped."""
    g = df5.resample("20min", origin="epoch", label="left", closed="left")
    bars = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                         "close": g["close"].last(), "volume": g["volume"].sum(), "n": g["close"].count()})
    complete = bars[bars["n"] == 4].drop(columns="n")
    gaps = int((bars["n"] < 4).sum())
    return complete, gaps


# ---------------------------------------------------------------------------
# Strategies (repo classes, unchanged)
# ---------------------------------------------------------------------------

def router_for(strategy: str, symbol: str) -> Optional[StrategyRouter]:
    if strategy == "tendencia":
        return default_router(symbol, "20m")
    if strategy == "rango":
        router = StrategyRouter()
        router.register(Regime.RANGE, BollingerReversion(symbol, "20m"), min_confidence=0.5)
        return router
    return None


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry: float
    exit_time: pd.Timestamp
    exit: float
    reason: str

    @property
    def net_pct(self) -> float:
        qty = NOTIONAL_USDT / self.entry
        cost = NOTIONAL_USDT * (1 + FEE)
        pnl = qty * self.exit * (1 - FEE) - cost
        return pnl / cost * 100


def run_window(bars: pd.DataFrame, start: pd.Timestamp, strategy: str, symbol: str) -> list[Trade]:
    """One window: flat at `start`, force-closed at the close of the window's last bar."""
    window = bars.loc[start: start + WINDOW_HOURS * pd.Timedelta(hours=1) - BAR]
    if len(window) != BARS_PER_WINDOW or (window.index[-1] - window.index[0]) != (BARS_PER_WINDOW - 1) * BAR:
        return []  # a gap inside the window: skipped (counted in gaps)
    if strategy == "baseline":
        return [Trade(window.index[0], window["open"].iloc[0] * (1 + SLIP), window.index[-1] + BAR,
                      window["close"].iloc[-1] * (1 - SLIP), "fin de ventana")]
    router = router_for(strategy, symbol)
    assert router is not None
    pos = bars.index.get_loc(window.index[0])
    trades: list[Trade] = []
    open_: Optional[tuple[pd.Timestamp, float, float]] = None  # time, entry, stop
    opener: Optional[AbstractStrategy] = None
    # Decision k uses bars up to index pos-1+k (closed at window start + k*20min); fills at bar pos+k's open.
    for k in range(BARS_PER_WINDOW):
        i = pos + k
        bar = bars.iloc[i]
        hist = bars.iloc[max(0, i - HISTORY_BARS): i]  # closed bars only, as of this bar's open
        if open_ is None:
            routed = router.route(detect_regime(hist)).strategy
            proposal = routed.on_bar(hist) if routed is not None else None
            if proposal is not None and float(proposal.stop_price) < bar["open"]:
                open_, opener = (bars.index[i], bar["open"] * (1 + SLIP), float(proposal.stop_price)), routed
        elif open_ is not None and opener is not None:
            if opener.on_exit_signal(hist, Decimal(str(open_[1]))):
                trades.append(Trade(open_[0], open_[1], bars.index[i], bar["open"] * (1 - SLIP), "señal"))
                open_ = opener = None
                continue
        if open_ is not None and bar["low"] <= open_[2]:
            fill = bar["open"] * (1 - SLIP) if bar["open"] < open_[2] else open_[2] * (1 - 2 * SLIP)
            trades.append(Trade(open_[0], open_[1], bars.index[i], fill, "stop"))
            open_ = opener = None
    if open_ is not None:
        last = window.index[-1]
        trades.append(Trade(open_[0], open_[1], last + BAR, window["close"].iloc[-1] * (1 - SLIP), "fin de ventana"))
    return trades


def run_day(day: date, bars_by_symbol: dict[str, pd.DataFrame]) -> list[dict]:
    rows = []
    for h in WINDOWS:
        start = pd.Timestamp(datetime(day.year, day.month, day.day, h, tzinfo=timezone.utc))
        for symbol, bars in bars_by_symbol.items():
            for strategy in STRATEGIES:
                trades = run_window(bars, start, strategy, symbol)
                nets = [float(t.net_pct) for t in trades]
                rows.append({"date": day.isoformat(), "window_utc": h, "symbol": symbol, "strategy": strategy,
                             "trades": len(nets), "wins": int(sum(n > 0 for n in nets)), "net_pct": nets,
                             "net_sum": float(sum(nets)), "reasons": [t.reason for t in trades]})
    return rows


# ---------------------------------------------------------------------------
# Selection rule (applied once the 14 forward days exist)
# ---------------------------------------------------------------------------

def bh(pvalues: list[float], q: float = BH_Q) -> list[bool]:
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    cutoff = -1
    for rank, i in enumerate(order, 1):
        if pvalues[i] <= rank / m * q:
            cutoff = rank
    passed = [False] * m
    for rank, i in enumerate(order, 1):
        passed[i] = rank <= cutoff
    return passed


def one_sided_p(values: list[float]) -> float:
    if len(values) < MIN_TRADES_PER_HALF or np.mean(values) <= 0:
        return 1.0
    if np.std(values) == 0:
        return 0.0
    return float(stats.ttest_1samp(values, 0, alternative="greater").pvalue)


def select(rows: list[dict], key: Callable[[dict], tuple]) -> list[dict]:
    """Split-half candidates (days 1-7) -> confirmation (days 8-14) -> BH over all candidates."""
    mid = FORWARD_START + timedelta(days=7)
    halves: dict[tuple, tuple[list[float], list[float]]] = {}
    for r in rows:
        d = date.fromisoformat(r["date"])
        if not FORWARD_START <= d <= FORWARD_END:
            continue
        h1, h2 = halves.setdefault(key(r), ([], []))
        (h1 if d < mid else h2).extend(r["net_pct"])
    candidates = [(k, h1, h2) for k, (h1, h2) in halves.items()
                  if len(h1) >= MIN_TRADES_PER_HALF and np.mean(h1) > 0]
    pvals = [one_sided_p(h2) for _, _, h2 in candidates]
    passed = bh(pvals)
    return [{"cell": list(k), "half1_n": len(h1), "half1_mean": float(np.mean(h1)), "half2_n": len(h2),
             "half2_mean": float(np.mean(h2)) if h2 else None, "p": p, "qualifies": ok}
            for (k, h1, h2), p, ok in zip(candidates, pvals, passed)]


# ---------------------------------------------------------------------------
# Reports (Spanish)
# ---------------------------------------------------------------------------

def hour_label(h: int) -> str:
    local = (h + LOCAL_OFFSET_H) % 24
    return f"{h:02d}–{(h + WINDOW_HOURS) % 24:02d} UTC ({local:02d}–{(local + WINDOW_HOURS) % 24:02d} UTC−5)"


def heat_table(rows: list[dict], strategy: str) -> list[str]:
    acc: dict[tuple[int, str], list[float]] = {}
    for r in rows:
        if r["strategy"] == strategy:
            acc.setdefault((r["window_utc"], r["symbol"]), []).extend(r["net_pct"])
    syms = [s for s in SYMBOLS if any(k[1] == s for k in acc)]
    lines = ["| Ventana | " + " | ".join(s.replace("USDT", "") for s in syms) + " | Todas |",
             "|---|" + "---|" * (len(syms) + 1)]
    for h in WINDOWS:
        cells, allv = [], []
        for s in syms:
            v = acc.get((h, s), [])
            allv += v
            cells.append(f"{sum(v):+.2f}" if v else "·")
        lines.append(f"| {hour_label(h)} | " + " | ".join(cells) + f" | {sum(allv):+.2f} |")
    return lines


def top_bottom(rows: list[dict], n: int = 5) -> list[str]:
    acc: dict[tuple[int, str, str], list[float]] = {}
    for r in rows:
        if r["trades"]:
            acc.setdefault((r["window_utc"], r["symbol"], r["strategy"]), []).extend(r["net_pct"])
    ranked = sorted(acc.items(), key=lambda kv: sum(kv[1]), reverse=True)
    def fmt(kv: tuple[tuple[int, str, str], list[float]]) -> str:
        (h, sym, strat), v = kv
        return f"- {sym} · {strat} · {hour_label(h)}: {sum(v):+.2f}% neto en {len(v)} operación(es)"
    return (["**Mejores 5 (descriptivo, puede ser suerte):**", *map(fmt, ranked[:n]), "",
             "**Peores 5:**", *map(fmt, ranked[::-1][:n])])


def day_label(d: date) -> str:
    return "FORWARD (decide)" if FORWARD_START <= d <= FORWARD_END else "referencia: datos pasados"


def render_day(d: date, rows: list[dict], gaps: dict[str, int]) -> str:
    total = [x for r in rows for x in r["net_pct"]]
    lines = [f"# Experimento horarios — {d.isoformat()} ({day_label(d)})", "",
             "Simulación con datos públicos (PAPER): **sin cuenta, sin claves, sin órdenes reales**. "
             "Ventanas de 2 h, barras de 20 min, 10 USDT por operación, comisión 0.1% por lado + 5 bps. "
             "Las horas se muestran en UTC y en UTC−5 (hora probable del dueño, Ecuador). "
             "Regla de selección en `docs/PREREG_HORARIOS.md`.", "",
             f"- Operaciones del día: {len(total)} · neto total {sum(total):+.2f}% "
             f"(suma de % por operación)"]
    for s in STRATEGIES:
        v = [x for r in rows if r["strategy"] == s for x in r["net_pct"]]
        wins = sum(x > 0 for x in v)
        lines.append(f"- {s}: {len(v)} operaciones, ganadoras {wins}"
                     + (f" ({wins / len(v):.0%}), media {np.mean(v):+.3f}%" if v else ""))
    if any(gaps.values()):
        lines.append("- Huecos de datos (barras de 20 min incompletas): "
                     + ", ".join(f"{k} {v}" for k, v in gaps.items() if v))
    for s in STRATEGIES:
        lines += ["", f"## {s}: neto % por ventana × símbolo (día)", "", *heat_table(rows, s)]
    lines += ["", "## Mejores y peores celdas del día", "", *top_bottom(rows)]
    return "\n".join(lines) + "\n"


def render_summary(all_rows: list[dict]) -> tuple[str, dict]:
    fwd = [r for r in all_rows if FORWARD_START <= date.fromisoformat(r["date"]) <= FORWARD_END]
    ref = [r for r in all_rows if not FORWARD_START <= date.fromisoformat(r["date"]) <= FORWARD_END]
    fwd_days = sorted({r["date"] for r in fwd})
    lines = ["# Experimento horarios — resumen acumulado", "",
             f"Días forward (deciden): {len(fwd_days)}/14 · días de referencia: {len({r['date'] for r in ref})}", ""]
    summary: dict = {"forward_days": fwd_days}
    if len(fwd_days) == 14:
        cells = select(all_rows, lambda r: (r["window_utc"], r["symbol"], r["strategy"]))
        by_window = select(all_rows, lambda r: (r["window_utc"], "TODOS", r["strategy"]))
        by_symbol = select(all_rows, lambda r: ("TODAS", r["symbol"], r["strategy"]))
        summary.update(cells=cells, by_window=by_window, by_symbol=by_symbol)
        lines += ["## Resultado de la regla de selección (pre-registrada)", ""]
        for name, res in (("Celdas ventana×símbolo×estrategia", cells), ("Por ventana (todos los símbolos)", by_window),
                          ("Por símbolo (todas las ventanas)", by_symbol)):
            ok = [c for c in res if c["qualifies"]]
            lines.append(f"- **{name}:** {len(res)} candidatas, **{len(ok)} califican**")
            for c in ok:
                lines.append(f"  - {c['cell']}: mitad 1 {c['half1_mean']:+.3f}% (n={c['half1_n']}), "
                             f"mitad 2 {c['half2_mean']:+.3f}% (n={c['half2_n']}), p={c['p']:.4f}")
        if not any(c["qualifies"] for res in (cells, by_window, by_symbol) for c in res):
            lines.append("\n**Ninguna hora ni mercado resultó mejor que el azar.**")
    else:
        lines.append("La regla de selección se aplica cuando existan los 14 días forward (2026-10-10 → 2026-10-23).")
    for label, rows in (("FORWARD (decide)", fwd), ("referencia: datos pasados", ref)):
        if not rows:
            continue
        for s in STRATEGIES:
            lines += ["", f"## {label} — {s}: neto % acumulado por ventana × símbolo", "", *heat_table(rows, s)]
        lines += ["", f"## {label} — mejores y peores celdas", "", *top_bottom(rows)]
    lines += ["", "Las tablas y listas son descriptivas: con 468 celdas, algunas se ven bien por azar. "
              "Solo la regla pre-registrada puede declarar una hora o mercado mejor."]
    return "\n".join(lines) + "\n", summary


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_days(days: list[date], out_dir: Path = OUT_DIR, fetch: Fetcher = fetch_5m) -> None:
    start = datetime.combine(days[0], datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=WARMUP_DAYS)
    end = datetime.combine(days[-1], datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    bars = {s: to_20m(fetch(s, start, end))[0] for s in SYMBOLS}
    out_dir.mkdir(parents=True, exist_ok=True)
    for d in days:
        rows = run_day(d, bars)
        d0 = pd.Timestamp(d.isoformat(), tz="UTC")
        day_gaps = {s: 72 - int(((b.index >= d0) & (b.index < d0 + pd.Timedelta(days=1))).sum()) for s, b in bars.items()}
        (out_dir / f"{d.isoformat()}.json").write_text(json.dumps(
            {"date": d.isoformat(), "label": day_label(d), "rows": rows, "gaps": day_gaps}, ensure_ascii=False) + "\n")
        (out_dir / f"{d.isoformat()}.md").write_text(render_day(d, rows, day_gaps))
    all_rows = []
    for f in sorted(out_dir.glob("20??-??-??.json")):
        all_rows += json.loads(f.read_text())["rows"]
    md, summary = render_summary(all_rows)
    (out_dir / "resumen.md").write_text(md)
    (out_dir / "resumen.json").write_text(json.dumps(summary, default=str, ensure_ascii=False) + "\n")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Experimento horarios (PAPER, research only)")
    parser.add_argument("--start", help="first UTC date (default: yesterday)")
    parser.add_argument("--end", help="last UTC date, inclusive (default: --start)")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    first = date.fromisoformat(args.start) if args.start else datetime.now(timezone.utc).date() - timedelta(days=1)
    last = date.fromisoformat(args.end) if args.end else first
    if last >= datetime.now(timezone.utc).date():
        parser.error("only complete UTC days can be replayed")
    run_days([first + timedelta(days=i) for i in range((last - first).days + 1)], args.out)
    print((args.out / "resumen.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
