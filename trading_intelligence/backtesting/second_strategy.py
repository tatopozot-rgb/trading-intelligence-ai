"""
Second futures strategy next to the desk (research only: public data, no key, no orders).

Leader's task, 2026-10-11: find an independent strategy for more, uncorrelated trades. Three
candidates on 5-minute bars, the desk's sizing, fees and real funding:
  a) funding:  fade the crowded side at a funding settlement when |funding| >= theta and the top
               traders agree with the crowd (funding > 0 and ratio > 1 -> SELL; < 0 and < 1 -> BUY);
               desk exits (strategy/exit_plan.py, stop 3-15%), plus a time exit after H hours.
  b) ruptura:  BTC and ETH; Asia range 00:00-07:00 UTC, entries 07:00-12:00 UTC on a 5m close
               beyond the range, stop at the opposite side or the middle, target k x risk,
               flat at 20:00 UTC; one trade per symbol per day.
  c) scout:    a 15-minute move >= m% with 5m volume >= v x its 20-bar average (the Scout's alert);
               enter with the move, stop where the move started, time exit after H.
Fit: a small fixed grid per candidate, the best net P&L on the first 60% of 90 days (>= 10 trades).
Test: those parameters on the last 40%. Only a test with >= 30 trades is reported as evidence.
Sizing as the desk (two_way_backtest): risk 1-15% by quality, position <= 50% of equity, 1x, 3
positions, min notional. Fees 0.05% per side, real funding per bar (0.01%/8h when missing).
A stop and a target in the same bar count as the stop.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
from scipy import stats

from trading_intelligence.backtesting import two_way_backtest as tw
from trading_intelligence.strategy.exit_plan import plan_exits

DAYS, FIT_FRACTION, MIN_TEST_TRADES, MIN_FIT_TRADES = 90, 0.6, 30, 10
CAPITAL = 1000.0  # research capital: large enough that minimum notionals do not hide signals
BAR = pd.Timedelta(minutes=5)
GRIDS: dict[str, list[dict]] = {
    "funding": [{"theta": t, "hours": h} for t, h in itertools.product((0.015, 0.025, 0.04), (8, 24))],
    "ruptura": [{"stop": s, "k": k} for s, k in itertools.product(("opuesto", "medio"), (1.0, 1.5, 2.0))],
    "scout": [{"move": m, "vol": v, "hours": h} for m, v, h in itertools.product((1.0, 1.5), (2.0, 3.0), (1, 4))],
}
RUPTURA_SYMBOLS = ("BTCUSDT", "ETHUSDT")
OUT_DIR = Path("docs/research")


@dataclass(frozen=True)
class Signal:
    i: int  # entry bar (fills at this bar's open)
    symbol: str
    side: str
    quality: float
    stop: float
    target: Optional[float]
    exit_i: int  # forced exit at this bar's close


@dataclass
class Data:
    times: pd.DatetimeIndex
    bars: dict[str, pd.DataFrame]  # aligned to `times` (NaN where missing)
    funding: dict[str, pd.Series]  # % per 8h at settlement times
    top: dict[str, pd.Series]


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def _plan(bars: pd.DataFrame, i: int, side: str) -> Optional[tuple[float, float]]:
    window = bars.iloc[max(0, i - tw.WINDOW): i].dropna()
    if len(window) < 50:
        return None
    try:
        plan = plan_exits(window, Decimal(str(window["close"].iloc[-1])), side=side)
    except ValueError:
        return None
    return float(plan.stop), float(plan.target)


def funding_signals(d: Data, theta: float, hours: int) -> list[Signal]:
    out = []
    for sym, fund in d.funding.items():
        bars = d.bars[sym]
        for t, f in fund.items():
            if abs(f) < theta:
                continue
            ratio = tw._asof(d.top.get(sym), t)
            if ratio is None or (f > 0) != (ratio > 1):
                continue
            side = "SELL" if f > 0 else "BUY"
            i = int(d.times.searchsorted(t, side="left"))
            if i >= len(d.times) or math.isnan(bars["open"].iloc[i]):
                continue
            plan = _plan(bars, i, side)
            if plan is None:
                continue
            out.append(Signal(i, sym, side, min(1.0, abs(f) / (2 * theta)), plan[0], plan[1],
                              min(len(d.times) - 1, i + hours * 12 - 1)))
    return out


def ruptura_signals(d: Data, stop: str, k: float) -> list[Signal]:
    out = []
    for sym in RUPTURA_SYMBOLS:
        if sym not in d.bars:
            continue
        bars = d.bars[sym]
        for day in pd.date_range(d.times[0].normalize(), d.times[-1].normalize(), freq="1D"):
            asia = bars.loc[day: day + pd.Timedelta(hours=7) - BAR].dropna()
            if len(asia) < 80:
                continue
            hi, lo = float(asia["high"].max()), float(asia["low"].min())
            session = bars.loc[day + pd.Timedelta(hours=7): day + pd.Timedelta(hours=12) - BAR]
            for t, row in session.iterrows():
                c = row["close"]
                side = "BUY" if c > hi else "SELL" if c < lo else None
                if side is None:
                    continue
                i = int(d.times.searchsorted(t)) + 1  # decided on this bar's close, filled at the next open
                end = int(d.times.searchsorted(day + pd.Timedelta(hours=20))) - 1
                if i >= len(d.times) or i > end:
                    break
                sl = (lo if side == "BUY" else hi) if stop == "opuesto" else (hi + lo) / 2
                entry = float(bars["open"].iloc[i])
                risk = abs(entry - sl)
                if risk <= 0 or (side == "BUY" and sl >= entry) or (side == "SELL" and sl <= entry):
                    break
                tp = entry + k * risk if side == "BUY" else entry - k * risk
                out.append(Signal(i, sym, side, 0.5, sl, tp, end))
                break  # one trade per symbol per day
    return out


def scout_signals(d: Data, move: float, vol: float, hours: int) -> list[Signal]:
    out = []
    for sym, bars in d.bars.items():
        c, o, v = bars["close"].values, bars["open"].values, bars["volume"].values
        avg = pd.Series(v).rolling(20).mean().shift(1).values
        last = -10**9
        for i in range(23, len(bars) - 1):
            if i - last < hours * 12:  # one signal per symbol per holding period
                continue
            base = o[i - 2]
            if not (base > 0 and avg[i] > 0) or math.isnan(c[i]):
                continue
            ret = (c[i] / base - 1) * 100
            if abs(ret) < move or v[i] < vol * avg[i]:
                continue
            side = "BUY" if ret > 0 else "SELL"
            out.append(Signal(i + 1, sym, side, min(1.0, v[i] / avg[i] / (2 * vol)), float(base), None,
                              min(len(bars) - 1, i + hours * 12)))
            last = i
    return out


GENERATORS: dict[str, Callable[..., list[Signal]]] = {
    "funding": funding_signals, "ruptura": ruptura_signals, "scout": scout_signals}


# ---------------------------------------------------------------------------
# Portfolio simulation (the desk's sizing)
# ---------------------------------------------------------------------------

@dataclass
class _Pos:
    s: Signal
    qty: float
    entry: float
    fee_in: float
    funding: float = 0.0


@dataclass
class Run:
    trades: list[dict] = field(default_factory=list)
    curve: list[float] = field(default_factory=list)
    skipped: int = 0


def simulate(d: Data, signals: list[Signal], lo: int, hi: int, capital: float = CAPITAL) -> Run:
    """Entries with lo <= i < hi; everything is closed by bar hi - 1."""
    by_i: dict[int, list[Signal]] = {}
    for s in signals:
        if lo <= s.i < hi:
            by_i.setdefault(s.i, []).append(s)
    run = Run()
    cash = capital
    pos: dict[str, _Pos] = {}
    funding_at = {sym: f for sym, f in d.funding.items()}
    for i in range(lo, hi):
        t = d.times[i]
        for sym in list(pos):
            p = pos[sym]
            bar = d.bars[sym].iloc[i]
            if math.isnan(bar["close"]):
                continue
            long = p.s.side == "BUY"
            f = tw._asof(funding_at.get(sym), t)
            rate = f / 100 if f is not None else tw.FUNDING_PER_8H
            p.funding += p.qty * bar["close"] * rate * tw.BAR_HOURS / 8 * (1 if long else -1)
            hit_sl = bar["low"] <= p.s.stop if long else bar["high"] >= p.s.stop
            hit_tp = p.s.target is not None and (bar["high"] >= p.s.target if long else bar["low"] <= p.s.target)
            price, why = None, ""
            if hit_sl:
                price, why = p.s.stop, "stop"
            elif hit_tp:
                price, why = p.s.target, "meta"
            elif i >= p.s.exit_i or i == hi - 1:
                price, why = float(bar["close"]), "tiempo"
            if price is None:
                continue
            gross = (price - p.entry) * p.qty if long else (p.entry - price) * p.qty
            fee_out = price * p.qty * tw.FEE
            pnl = gross - fee_out - p.fee_in - p.funding
            cash += gross - fee_out - p.funding
            run.trades.append({"symbol": sym, "side": p.s.side, "entry_at": d.times[p.s.i].isoformat(),
                               "exit_at": t.isoformat(), "why": why, "pnl": pnl,
                               "ret_pct": pnl / (p.qty * p.entry) * 100})
            del pos[sym]
        marks = {s: float(d.bars[s]["close"].iloc[i]) for s in pos if not math.isnan(d.bars[s]["close"].iloc[i])}
        equity = cash + sum(((marks.get(s, p.entry) - p.entry) * p.qty if p.s.side == "BUY"
                             else (p.entry - marks.get(s, p.entry)) * p.qty) for s, p in pos.items())
        run.curve.append(equity)
        for s in by_i.get(i, []):
            if s.symbol in pos or len(pos) >= tw.MAX_OPEN or i >= hi - 1:
                continue
            entry = float(d.bars[s.symbol]["open"].iloc[i])
            dist = abs(entry - s.stop)
            if math.isnan(entry) or dist <= 0 or (s.side == "BUY") != (s.stop < entry):
                continue
            risk = tw.RISK_MIN + (tw.RISK_MAX - tw.RISK_MIN) * s.quality
            used = sum(p.qty * p.entry for p in pos.values())
            qty = min(equity * risk / dist, equity * tw.MAX_POSITION / entry,
                      max(0.0, tw.LEVERAGE * equity - used) * 0.95 / entry)
            if qty * entry < tw.MIN_NOTIONAL.get(s.symbol, tw.DEFAULT_MIN_NOTIONAL):
                run.skipped += 1
                continue
            fee_in = qty * entry * tw.FEE
            cash -= fee_in
            pos[s.symbol] = _Pos(s, qty, entry, fee_in)
    return run


def summarize(run: Run, capital: float = CAPITAL) -> dict:
    pnl = [t["pnl"] for t in run.trades]
    rets = [t["ret_pct"] for t in run.trades]
    wins, losses = sum(p for p in pnl if p > 0), abs(sum(p for p in pnl if p <= 0))
    curve = np.array(run.curve or [capital])
    peak = np.maximum.accumulate(curve)
    p_value = float(stats.ttest_1samp(rets, 0).pvalue) if len(rets) >= 2 else 1.0
    return {"trades": len(pnl), "win_rate": round(sum(p > 0 for p in pnl) / len(pnl) * 100, 1) if pnl else 0.0,
            "net_pct": round(sum(pnl) / capital * 100, 2),
            "mean_ret_pct": round(float(np.mean(rets)), 3) if rets else 0.0,
            "profit_factor": round(wins / losses, 2) if losses else (math.inf if wins else 0.0),
            "p_value": round(1.0 if math.isnan(p_value) else p_value, 4),
            "max_dd_pct": round(float(((peak - curve) / peak).max() * 100), 2), "skipped_min_notional": run.skipped,
            "buy": sum(1 for t in run.trades if t["side"] == "BUY"),
            "sell": sum(1 for t in run.trades if t["side"] == "SELL")}


def daily_pnl(trades: list[dict]) -> pd.Series:
    if not trades:
        return pd.Series(dtype=float)
    s = pd.Series([t["pnl"] for t in trades], index=pd.to_datetime([t["exit_at"] for t in trades], utc=True))
    return s.groupby(s.index.floor("1D")).sum()


def split_index(d: Data) -> tuple[int, int]:
    """(first bar after the warm-up, first bar of the test window)."""
    base = min(tw.WARMUP, len(d.times) // 4)
    return base, base + int((len(d.times) - base) * FIT_FRACTION)


def evaluate(d: Data, desk_daily: Optional[pd.Series] = None) -> dict:
    n = len(d.times)
    base, split = split_index(d)
    out: dict = {"fit": [str(d.times[base]), str(d.times[split - 1])], "test": [str(d.times[split]), str(d.times[-1])],
                 "candidates": {}}
    for name, grid in GRIDS.items():
        fits = []
        for params in grid:
            sigs = GENERATORS[name](d, **params)
            fits.append((params, sigs, summarize(simulate(d, sigs, base, split))))
        eligible = [f for f in fits if f[2]["trades"] >= MIN_FIT_TRADES]
        if not eligible:
            out["candidates"][name] = {"fit_grid": [{**p, **s} for p, _, s in fits], "chosen": None,
                                       "verdict": f"sin parámetros con >= {MIN_FIT_TRADES} operaciones en el ajuste"}
            continue
        params, sigs, fit = max(eligible, key=lambda f: f[2]["net_pct"])
        test_run = simulate(d, sigs, split, n)
        test = summarize(test_run)
        corr = None
        if desk_daily is not None and not desk_daily.empty:
            days = pd.date_range(d.times[split].normalize(), d.times[-1].normalize(), freq="1D")
            a = daily_pnl(test_run.trades).reindex(days, fill_value=0.0)
            b = desk_daily.reindex(days, fill_value=0.0)
            if a.std() > 0 and b.std() > 0:
                corr = round(float(np.corrcoef(a, b)[0, 1]), 3)
        if test["trades"] < MIN_TEST_TRADES:
            verdict = f"insuficiente: {test['trades']} operaciones fuera de muestra (< {MIN_TEST_TRADES})"
        elif test["net_pct"] > 0 and test["profit_factor"] >= 1.3 and test["p_value"] < 0.05:
            verdict = "se sostiene fuera de muestra"
        elif test["net_pct"] > 0:
            verdict = "positiva fuera de muestra, pero sin significancia"
        else:
            verdict = "no se sostiene fuera de muestra (pierde)"
        out["candidates"][name] = {"fit_grid": [{**p, **s} for p, _, s in fits], "chosen": params, "fit": fit,
                                   "test": test, "corr_with_desk": corr, "verdict": verdict}
    return out


# ---------------------------------------------------------------------------
# Data, desk and report
# ---------------------------------------------------------------------------

def load(days: int, end: datetime, symbols: list[str], fetcher: tw.Fetcher = tw.fetch) -> Data:
    start = end - timedelta(days=days)
    warm = start - timedelta(minutes=5 * tw.WARMUP)
    times = pd.date_range(warm, end - BAR, freq="5min", tz="UTC")
    bars, funding, top = {}, {}, {}
    for sym in symbols:
        try:
            bars[sym] = fetcher(sym, "5m", warm, end).reindex(times)
        except Exception as error:  # noqa: BLE001 - one symbol's data must not stop the others
            print(f"{sym}: sin datos ({type(error).__name__})")
            continue
        funding[sym] = tw.fetch_funding(sym, warm, end)
        top[sym] = tw.fetch_top_traders(sym, warm, end)
        print(f"{sym}: {int(bars[sym]['close'].notna().sum())} velas, financiación {len(funding[sym])}, "
              f"top traders {len(top[sym])}")
    return Data(times, bars, funding, top)


def desk_daily_pnl(d: Data, fetcher: tw.Fetcher = tw.fetch) -> pd.Series:
    """The live desk ('mesa') replayed over the test window, as daily P&L, for the correlation."""
    _, split = split_index(d)
    start, end = d.times[split].to_pydatetime(), (d.times[-1] + BAR).to_pydatetime()
    prepared = {}
    for sym, bars in d.bars.items():
        warm = start - timedelta(minutes=5 * tw.WARMUP)
        m5 = bars.loc[warm:].dropna()
        try:
            h1 = fetcher(sym, "1h", warm - timedelta(hours=tw.SLOW + 5), end)
        except Exception:  # noqa: BLE001
            continue
        prepared[sym] = tw.prepare(m5, h1, tw.WARMUP, d.top.get(sym), d.funding.get(sym))
    res = tw.simulate(prepared, "mesa", CAPITAL)
    trades = [{"pnl": t["pnl"], "exit_at": t["at"]} for t in res.trades]
    return daily_pnl(trades)


def render(result: dict, meta: dict) -> str:
    lines = [f"# Segunda estrategia de futuros junto a la mesa ({meta['desde']} a {meta['hasta']})", "",
             "Investigación con datos públicos (sin cuenta, sin órdenes). Velas de 5 min (precio Spot como aproximación "
             "del perpetuo), comisión 0,05% por lado y financiación real. Tamaño como la mesa: riesgo 1-15% según la "
             "calidad, posición máx. 50%, 1x, 3 posiciones. Capital de estudio 1.000 USDT. "
             f"Ajuste en el primer 60% ({result['fit'][0][:10]} a {result['fit'][1][:10]}); prueba en el último 40% "
             f"({result['test'][0][:10]} a {result['test'][1][:10]}). Solo cuenta lo que se sostiene fuera de muestra "
             f"con al menos {MIN_TEST_TRADES} operaciones.", "",
             "| Candidata | Parámetros elegidos | Ajuste: ops / neto % | Prueba: ops | Acierto | Neto % | Media/op | PF | p | "
             "Máx. caída | Correlación con la mesa | Veredicto |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, c in result["candidates"].items():
        if c["chosen"] is None:
            lines.append(f"| {name} | — | — | — | — | — | — | — | — | — | — | {c['verdict']} |")
            continue
        f, t = c["fit"], c["test"]
        lines.append(f"| {name} | {c['chosen']} | {f['trades']} / {f['net_pct']:+.2f}% | {t['trades']} | "
                     f"{t['win_rate']}% | {t['net_pct']:+.2f}% | {t['mean_ret_pct']:+.3f}% | {t['profit_factor']} | "
                     f"{t['p_value']} | {t['max_dd_pct']}% | {c['corr_with_desk']} | {c['verdict']} |")
    good = [n for n, c in result["candidates"].items() if c["verdict"] == "se sostiene fuera de muestra"]
    lines += ["", "## Nota", ""]
    if good:
        best = max(good, key=lambda n: result["candidates"][n]["test"]["net_pct"])
        c = result["candidates"][best]
        lines.append(f"**{best}** se sostiene fuera de muestra con {c['test']['trades']} operaciones "
                     f"(neto {c['test']['net_pct']:+.2f}%, p={c['test']['p_value']}). Vale un bot de práctica con "
                     f"los parámetros {c['chosen']}. Correlación diaria con la mesa: {c['corr_with_desk']}.")
    else:
        lines.append("**Ninguna candidata se sostiene fuera de muestra** con 30 operaciones o más. No se recomienda un "
                     "bot de práctica con estas reglas; si se quiere seguir midiendo, la menos mala puede correr solo en "
                     "práctica, sin dinero real.")
    lines += ["", "Advertencias: 90 días son un solo tipo de mercado; elegir el mejor de una cuadrícula en el ajuste "
              "infla el resultado del ajuste (por eso solo cuenta la prueba); el precio Spot aproxima al perpetuo; un stop "
              "y una meta en la misma vela cuentan como stop. Un resultado pasado no promete uno futuro."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Segunda estrategia de futuros (investigación)")
    parser.add_argument("--dias", type=int, default=DAYS)
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--sin-mesa", action="store_true", help="skip the desk correlation (faster)")
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    d = load(args.dias, end, args.simbolos)
    desk = None if args.sin_mesa else desk_daily_pnl(d)
    result = evaluate(d, desk)
    meta = {"desde": (end - timedelta(days=args.dias)).date().isoformat(), "hasta": end.date().isoformat(),
            "simbolos": list(d.bars)}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = end.date().isoformat()
    (args.salida / f"segunda_estrategia_{stamp}.json").write_text(
        json.dumps({"meta": meta, **result}, indent=1, default=str), encoding="utf-8")
    report = render(result, meta)
    (args.salida / f"segunda_estrategia_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
