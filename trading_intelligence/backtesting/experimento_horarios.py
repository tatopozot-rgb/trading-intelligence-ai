"""
"Experimento horarios": time-of-day windows on 20-minute bars, PAPER only.

Pre-registered in docs/PREREG_HORARIOS.md (with Amendment 1) before any result was
seen; the constants below are that document. Research only: public klines, no account,
no key, no orders.

For one UTC day, every window x symbol x strategy starts flat, decides entries at
:00/:20/:40 on completed 20-minute bars with the repo's own strategy classes, and
monitors an open position every 3 minutes on 1-minute klines: the strategy's stop (on
1-minute lows), the strategy's own exit condition (on the in-progress 20-minute bar)
and a forced close at the window's end. Costs: 0.1% per side + 5 bps slippage, a
fixed 10 USDT per trade, reported as net % per trade.

Windows: the 12 two-hour UTC windows (exploratory search, BH) plus the owner's own
window, 07:00-10:00 Ecuador = 12:00-15:00 UTC (primary planned hypothesis).
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
from trading_intelligence.strategy.router import StrategyRouter, default_router
from trading_intelligence.strategy.strategies.bollinger_reversion import BollingerReversion

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
           "LINKUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT", "PAXGUSDT")
STRATEGIES = ("tendencia", "rango", "baseline")
BAR = pd.Timedelta(minutes=20)
MINUTE = pd.Timedelta(minutes=1)
CHECK_EVERY = pd.Timedelta(minutes=3)
# (window id, start hour UTC, length in hours, family)
WINDOWS = tuple((f"{h:02d}h", h, 2, "exploratoria") for h in range(0, 24, 2)) + (("dueno", 12, 3, "dueno"),)
HISTORY_BARS = 500
WARMUP_DAYS = 8
FEE = 0.001
SLIP = 0.0005
NOTIONAL_USDT = 10.0
LOCAL_OFFSET_H = -5  # Ecuador (owner confirmed)
FORWARD_START, FORWARD_END = date(2026, 10, 10), date(2026, 10, 23)
HALF2_START = date(2026, 10, 17)
SCOPES = {"lun-vie": (0, 1, 2, 3, 4), "lun-sab": (0, 1, 2, 3, 4, 5)}
PRIMARY_SCOPE = "lun-vie"
BH_Q = 0.10
OWNER_ALPHA = 0.05 / 3
WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
OUT_DIR = Path("docs/experimento_horarios")

Fetcher = Callable[[str, datetime, datetime], pd.DataFrame]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def fetch_1m(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    rdv.INTERVAL_MS.setdefault("1m", 60_000)
    return rdv.fetch_klines(symbol, "1m", start, end)


def to_20m(m1: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """20-minute bars opening at :00/:20/:40 UTC; a bar missing any minute is dropped."""
    g = m1.resample("20min", origin="epoch", label="left", closed="left")
    bars = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                         "close": g["close"].last(), "volume": g["volume"].sum(), "n": g["close"].count()})
    complete = bars[bars["n"] == 20].drop(columns="n")
    return complete, int((bars["n"] < 20).sum())


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
        cost = NOTIONAL_USDT * (1 + FEE)
        pnl = NOTIONAL_USDT / self.entry * self.exit * (1 - FEE) - cost
        return pnl / cost * 100


def _with_partial(bars: pd.DataFrame, m1: pd.DataFrame, t: pd.Timestamp) -> pd.DataFrame:
    """Completed 20m bars before t's bar, plus the in-progress bar built from minutes [bar start, t)."""
    bar_start = t.floor("20min")
    done = bars.loc[: bar_start - BAR].iloc[-HISTORY_BARS:]
    part = m1.loc[bar_start: t - MINUTE]
    if part.empty:
        return done
    row = pd.DataFrame({"open": [part["open"].iloc[0]], "high": [part["high"].max()], "low": [part["low"].min()],
                        "close": [part["close"].iloc[-1]], "volume": [part["volume"].sum()]}, index=[bar_start])
    return pd.concat([done.iloc[-(HISTORY_BARS - 1):], row])


def run_window(m1: pd.DataFrame, bars: pd.DataFrame, start: pd.Timestamp, hours: int,
               strategy: str, symbol: str) -> list[Trade]:
    """Flat at `start`; entries every 20 minutes; exits checked every 3 minutes; forced close at the end."""
    end = start + pd.Timedelta(hours=hours)
    window = bars.loc[start: end - BAR]
    if len(window) != hours * 3:
        return []  # a gap inside the window: skipped (counted)
    minutes = m1.loc[start: end - MINUTE]
    if strategy == "baseline":
        return [Trade(start, float(minutes["open"].iloc[0]) * (1 + SLIP), end,
                      float(minutes["close"].iloc[-1]) * (1 - SLIP), "fin de ventana")]
    router = router_for(strategy, symbol)
    assert router is not None
    opens, lows = minutes["open"], minutes["low"]
    trades: list[Trade] = []
    t = start
    while t < end:
        hist = bars.loc[: t - BAR].iloc[-HISTORY_BARS:]  # completed bars only
        routed = router.route(detect_regime(hist)).strategy
        proposal = routed.on_bar(hist) if routed is not None else None
        entry_open = float(opens.at[t])
        if routed is None or proposal is None or float(proposal.stop_price) >= entry_open:
            t += BAR
            continue
        stop, entry = float(proposal.stop_price), entry_open * (1 + SLIP)
        exited: Optional[Trade] = None
        m, next_check = t, t + CHECK_EVERY
        while m < end:
            if m == next_check:
                if routed.on_exit_signal(_with_partial(bars, m1, m), Decimal(str(entry))):
                    exited = Trade(t, entry, m, float(opens.at[m]) * (1 - SLIP), "señal")
                    break
                next_check += CHECK_EVERY
            o, lo = float(opens.at[m]), float(lows.at[m])
            if o < stop:
                exited = Trade(t, entry, m, o * (1 - SLIP), "stop")
                break
            if lo <= stop:
                exited = Trade(t, entry, m, stop * (1 - 2 * SLIP), "stop")
                break
            m += MINUTE
        if exited is None:
            trades.append(Trade(t, entry, end, float(minutes["close"].iloc[-1]) * (1 - SLIP), "fin de ventana"))
            break
        trades.append(exited)
        t = exited.exit_time.floor("20min") + BAR  # next entry decision: the next 20-minute boundary
    return trades


def run_day(day: date, data: dict[str, tuple[pd.DataFrame, pd.DataFrame]]) -> list[dict]:
    rows = []
    for wid, h, hours, family in WINDOWS:
        start = pd.Timestamp(datetime(day.year, day.month, day.day, h, tzinfo=timezone.utc))
        for symbol, (m1, bars) in data.items():
            for strategy in STRATEGIES:
                trades = run_window(m1, bars, start, hours, strategy, symbol)
                nets = [float(t.net_pct) for t in trades]
                rows.append({"date": day.isoformat(), "weekday": day.weekday(), "window": wid, "window_utc": h,
                             "hours": hours, "family": family, "symbol": symbol, "strategy": strategy,
                             "trades": len(nets), "wins": int(sum(n > 0 for n in nets)), "net_pct": nets,
                             "net_sum": float(sum(nets)), "reasons": [t.reason for t in trades]})
    return rows


# ---------------------------------------------------------------------------
# Selection rules (applied once the forward period is complete)
# ---------------------------------------------------------------------------

def bh(pvalues: list[float], q: float = BH_Q) -> list[bool]:
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    cutoff = 0
    for rank, i in enumerate(order, 1):
        if pvalues[i] <= rank / m * q:
            cutoff = rank
    passed = [False] * m
    for rank, i in enumerate(order, 1):
        passed[i] = rank <= cutoff
    return passed


def one_sided_p(values: list[float], min_n: int) -> float:
    if len(values) < min_n or np.mean(values) <= 0:
        return 1.0
    if np.std(values) == 0:
        return 0.0
    return float(stats.ttest_1samp(values, 0, alternative="greater").pvalue)


def halves(rows: list[dict], key: Callable[[dict], tuple], scope: str) -> dict[tuple, tuple[list[float], list[float]]]:
    out: dict[tuple, tuple[list[float], list[float]]] = {}
    for r in rows:
        d = date.fromisoformat(r["date"])
        if not FORWARD_START <= d <= FORWARD_END or d.weekday() not in SCOPES[scope]:
            continue
        h1, h2 = out.setdefault(key(r), ([], []))
        (h1 if d < HALF2_START else h2).extend(r["net_pct"])
    return out


def min_trades(scope: str) -> int:
    return len(SCOPES[scope])  # one trade per scope day in each half (the baseline's maximum)


def select(rows: list[dict], key: Callable[[dict], tuple], scope: str, *, denominator: str = "candidates",
           alpha: Optional[float] = None) -> list[dict]:
    """Split-half: candidates (half-1 mean > 0, n >= min) -> half-2 one-sided t-test ->
    BH at q over the candidates (or over all cells), or a fixed alpha for planned tests."""
    n_min = min_trades(scope)
    tested = []
    for k, (h1, h2) in halves(rows, key, scope).items():
        candidate = len(h1) >= n_min and float(np.mean(h1)) > 0
        if candidate or denominator == "all":
            tested.append((k, h1, h2, one_sided_p(h2, n_min) if candidate else 1.0))
    pvals = [p for *_, p in tested]
    passed = [p < alpha for p in pvals] if alpha is not None else bh(pvals)
    return [{"cell": list(k), "half1_n": len(h1), "half1_mean": float(np.mean(h1)) if h1 else None,
             "half2_n": len(h2), "half2_mean": float(np.mean(h2)) if h2 else None, "p": p, "qualifies": bool(ok)}
            for (k, h1, h2, p), ok in zip(tested, passed)]


SELECTIONS = {
    "dueno_pooled": "Ventana del dueño, todos los símbolos (principal, α = 0.0167)",
    "dueno_por_simbolo": "Ventana del dueño, por símbolo (BH q = 0.10 sobre 39)",
    "celdas": "Búsqueda: ventana × símbolo × estrategia (BH)",
    "por_ventana": "Búsqueda: por ventana (BH)",
    "por_simbolo": "Búsqueda: por símbolo (BH)",
}


def evaluate(rows: list[dict]) -> dict:
    expl = [r for r in rows if r["family"] == "exploratoria"]
    owner = [r for r in rows if r["family"] == "dueno"]
    return {scope: {
        "dueno_pooled": select(owner, lambda r: ("dueno", "TODOS", r["strategy"]), scope, denominator="all",
                               alpha=OWNER_ALPHA),
        "dueno_por_simbolo": select(owner, lambda r: ("dueno", r["symbol"], r["strategy"]), scope, denominator="all"),
        "celdas": select(expl, lambda r: (r["window"], r["symbol"], r["strategy"]), scope),
        "por_ventana": select(expl, lambda r: (r["window"], "TODOS", r["strategy"]), scope),
        "por_simbolo": select(expl, lambda r: ("TODAS", r["symbol"], r["strategy"]), scope),
    } for scope in SCOPES}


# ---------------------------------------------------------------------------
# Reports (Spanish, Ecuador time first)
# ---------------------------------------------------------------------------

def hour_label(h: int, hours: int = 2) -> str:
    local = (h + LOCAL_OFFSET_H) % 24
    return f"{local:02d}–{(local + hours) % 24:02d} Ecuador ({h:02d}–{(h + hours) % 24:02d} UTC)"


def window_label(wid: str) -> str:
    for w, h, hours, _ in WINDOWS:
        if w == wid:
            return hour_label(h, hours) + (" — ventana del dueño" if w == "dueno" else "")
    return wid


def heat_table(rows: list[dict], strategy: str) -> list[str]:
    acc: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        if r["strategy"] == strategy:
            acc.setdefault((r["window"], r["symbol"]), []).extend(r["net_pct"])
    syms = [s for s in SYMBOLS if any(k[1] == s for k in acc)]
    lines = ["| Ventana | " + " | ".join(s.replace("USDT", "") for s in syms) + " | Todas |",
             "|---|" + "---|" * (len(syms) + 1)]
    for wid, *_ in WINDOWS:
        cells, allv = [], []
        for s in syms:
            v = acc.get((wid, s), [])
            allv += v
            cells.append(f"{sum(v):+.2f}" if v else "·")
        lines.append(f"| {window_label(wid)} | " + " | ".join(cells) + f" | {sum(allv):+.2f} |")
    return lines


def weekday_table(rows: list[dict]) -> list[str]:
    lines = ["| Día | " + " | ".join(f"{s}: n / media %" for s in STRATEGIES) + " |",
             "|---|" + "---|" * len(STRATEGIES)]
    for wd, name in enumerate(WEEKDAYS_ES):
        cells = []
        for s in STRATEGIES:
            v = [x for r in rows if r["weekday"] == wd and r["strategy"] == s for x in r["net_pct"]]
            cells.append(f"{len(v)} / {np.mean(v):+.3f}" if v else "·")
        if any(c != "·" for c in cells):
            tag = " (no decide)" if wd == 6 else " (aparte)" if wd == 5 else ""
            lines.append(f"| {name}{tag} | " + " | ".join(cells) + " |")
    return lines


def top_bottom(rows: list[dict], n: int = 5) -> list[str]:
    acc: dict[tuple[str, str, str], list[float]] = {}
    for r in rows:
        if r["trades"]:
            acc.setdefault((r["window"], r["symbol"], r["strategy"]), []).extend(r["net_pct"])
    ranked = sorted(acc.items(), key=lambda kv: sum(kv[1]), reverse=True)

    def fmt(kv: tuple[tuple[str, str, str], list[float]]) -> str:
        (wid, sym, strat), v = kv
        return f"- {sym} · {strat} · {window_label(wid)}: {sum(v):+.2f}% neto en {len(v)} operación(es)"
    return ["**Mejores 5 (descriptivo, puede ser suerte):**", *map(fmt, ranked[:n]), "",
            "**Peores 5:**", *map(fmt, ranked[::-1][:n])]


def day_label(d: date) -> str:
    base = "FORWARD" if FORWARD_START <= d <= FORWARD_END else "referencia: datos pasados"
    scope = ("día hábil, cuenta para la decisión" if d.weekday() < 5 else
             "sábado: se reporta aparte" if d.weekday() == 5 else "domingo: se registra, no decide")
    return f"{WEEKDAYS_ES[d.weekday()]}; {base}; {scope}"


INTRO = ("Simulación con datos públicos (PAPER): **sin cuenta, sin claves, sin órdenes reales**. "
         "Entradas cada 20 min (velas de 20 min); con posición abierta se revisa la salida cada 3 min "
         "(velas de 1 min): stop de la estrategia, su condición de salida y cierre forzado al final de la ventana. "
         "10 USDT por operación, comisión 0.1% por lado + 5 bps. Horas en **Ecuador (UTC−5)**, UTC entre paréntesis. "
         "Reglas en `docs/PREREG_HORARIOS.md` (con la Enmienda 1).")


def render_day(d: date, rows: list[dict], gaps: dict[str, int]) -> str:
    lines = [f"# Experimento horarios — {d.isoformat()} ({day_label(d)})", "", INTRO, ""]
    for s in STRATEGIES:
        v = [x for r in rows if r["strategy"] == s and r["family"] == "exploratoria" for x in r["net_pct"]]
        o = [x for r in rows if r["strategy"] == s and r["family"] == "dueno" for x in r["net_pct"]]
        lines.append(f"- {s}: ventanas de 2 h {len(v)} operaciones"
                     + (f", ganadoras {sum(x > 0 for x in v) / len(v):.0%}, media {np.mean(v):+.3f}%" if v else "")
                     + f" · ventana del dueño {len(o)} operaciones"
                     + (f", media {np.mean(o):+.3f}%" if o else ""))
    if any(gaps.values()):
        lines.append("- Huecos de datos (velas de 20 min incompletas en el día): "
                     + ", ".join(f"{k} {v}" for k, v in gaps.items() if v))
    for s in STRATEGIES:
        lines += ["", f"## {s}: neto % por ventana × símbolo (día)", "", *heat_table(rows, s)]
    lines += ["", "## Mejores y peores celdas del día", "", *top_bottom(rows)]
    return "\n".join(lines) + "\n"


def render_summary(all_rows: list[dict]) -> tuple[str, dict]:
    def is_fwd(r: dict) -> bool:
        return FORWARD_START <= date.fromisoformat(r["date"]) <= FORWARD_END
    fwd = [r for r in all_rows if is_fwd(r)]
    ref = [r for r in all_rows if not is_fwd(r)]
    fwd_days = sorted({r["date"] for r in fwd})
    weekdays_done = sum(date.fromisoformat(d).weekday() < 5 for d in fwd_days)
    lines = ["# Experimento horarios — resumen acumulado", "", INTRO, "",
             f"Días forward: {len(fwd_days)}/14 (días hábiles lun–vie: {weekdays_done}/10) · "
             f"días de referencia: {len({r['date'] for r in ref})}", ""]
    summary: dict = {"forward_days": fwd_days, "weekdays_done": weekdays_done}
    complete = bool(fwd_days) and date.fromisoformat(fwd_days[-1]) >= FORWARD_END
    if complete:
        result = evaluate(all_rows)
        summary["selection"] = result
        lines += ["## Resultado de las reglas pre-registradas", ""]
        for scope in SCOPES:
            lines.append(f"### Alcance {scope}" + (" (decide)" if scope == PRIMARY_SCOPE
                                                   else " (alternativa, a elegir por el dueño)"))
            for k, label in SELECTIONS.items():
                ok = [c for c in result[scope][k] if c["qualifies"]]
                lines.append(f"- **{label}:** {len(ok)} califican")
                for c in ok:
                    lines.append(f"  - {c['cell']}: mitad 1 {c['half1_mean']:+.3f}% (n={c['half1_n']}), "
                                 f"mitad 2 {c['half2_mean']:+.3f}% (n={c['half2_n']}), p={c['p']:.4f}")
            if not any(c["qualifies"] for res in result[scope].values() for c in res):
                lines.append("- **Ninguna hora ni mercado resultó mejor que el azar en este alcance.**")
            lines.append("")
    else:
        lines.append("Las reglas se aplican cuando el período forward esté completo (2026-10-10 → 2026-10-23).")
    for label, rows in (("FORWARD", fwd), ("referencia: datos pasados", ref)):
        if not rows:
            continue
        decide = [r for r in rows if r["weekday"] < 5]
        lines += ["", f"## {label} — por día de la semana", "", *weekday_table(rows)]
        for s in STRATEGIES:
            lines += ["", f"## {label} — {s}: neto % acumulado lun–vie por ventana × símbolo", "",
                      *heat_table(decide, s)]
        lines += ["", f"## {label} — mejores y peores celdas (lun–vie)", "", *top_bottom(decide)]
    lines += ["", "Las tablas y listas son descriptivas: con cientos de celdas, algunas se ven bien por azar. "
              "Solo las reglas pre-registradas pueden declarar una hora o mercado mejor."]
    return "\n".join(lines) + "\n", summary


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_days(days: list[date], out_dir: Path = OUT_DIR, fetch: Fetcher = fetch_1m) -> None:
    start = datetime.combine(days[0], datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=WARMUP_DAYS)
    end = datetime.combine(days[-1], datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    data = {}
    for s in SYMBOLS:
        m1 = fetch(s, start, end)
        data[s] = (m1, to_20m(m1)[0])
    out_dir.mkdir(parents=True, exist_ok=True)
    for d in days:
        rows = run_day(d, data)
        d0 = pd.Timestamp(d.isoformat(), tz="UTC")
        gaps = {s: 72 - int(((b.index >= d0) & (b.index < d0 + pd.Timedelta(days=1))).sum())
                for s, (_, b) in data.items()}
        (out_dir / f"{d.isoformat()}.json").write_text(json.dumps(
            {"date": d.isoformat(), "label": day_label(d), "rows": rows, "gaps": gaps}, ensure_ascii=False) + "\n")
        (out_dir / f"{d.isoformat()}.md").write_text(render_day(d, rows, gaps))
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
