"""
Two-way time-series momentum (long AND short) on daily Binance data — research only.

Pre-registered in docs/PREREG_TWO_WAY.md before any result was seen. Every rule
there is implemented here; the constants below are that document and must not
change after the first run.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
from scipy import stats

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.data.binance_public_feed import _urllib_get

LOOKBACK_DAYS = 28
VOL_DAYS = 60
MIN_CLOSES = VOL_DAYS + 1
TARGET_VOL = 0.40
FEE = 0.0005
SLIPPAGE = 0.0005
FALLBACK_RATE = 0.0001
FALLBACK_EVENTS_PER_DAY = 3
LEVERAGES = (1, 2, 3)
N_FOLDS = 5
INITIAL_EQUITY = 10_000.0
DD_LEVELS = (-20.0, -35.0, -50.0)
PRIMARY = ("2019-01-01", "2022-10-01")
SECONDARY = ("2022-10-01", "2026-10-01")  # already seen in sections 45/61: reported, decides nothing
EXTRA_SYMBOLS = ("PAXGUSDT",)
FAPI = "https://fapi.binance.com"
VISION = "https://data.binance.vision"

Getter = Callable[[str, float], bytes]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def fetch_daily(symbol: str, start: str, end: str, get: Getter = _urllib_get) -> pd.DataFrame:
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    s = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    e = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    return rdv.fetch_klines(symbol, "1d", s, e, get=get)[["open", "close"]]


def fetch_funding(symbol: str, start: str, end: str, get: Getter = _urllib_get) -> tuple[pd.Series, str]:
    """Real USDⓈ-M funding rates (time -> rate) and the source used; empty series if none."""
    s_ms = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    e_ms = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp() * 1000)
    rates: dict[int, float] = {}
    try:
        cursor = s_ms
        while cursor < e_ms:
            q = urllib.parse.urlencode({"symbol": symbol, "startTime": cursor, "endTime": e_ms - 1, "limit": 1000})
            rows = json.loads(get(f"{FAPI}/fapi/v1/fundingRate?{q}", 30.0))
            if not isinstance(rows, list) or not rows:
                break
            for r in rows:
                rates[int(r["fundingTime"])] = float(r["fundingRate"])
            nxt = int(rows[-1]["fundingTime"]) + 1
            if nxt <= cursor:
                break
            cursor = nxt
        if rates:
            return _series(rates), "fapi"
    except Exception:  # noqa: BLE001 - any failure falls through to the next source
        rates = {}
    month = datetime.fromisoformat(start).replace(day=1)
    stop = datetime.fromisoformat(end)
    while month < stop:
        url = f"{VISION}/data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month:%Y-%m}.zip"
        try:
            blob = get(url, 30.0)
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                text = zf.read(zf.namelist()[0]).decode()
            for row in csv.reader(io.StringIO(text)):
                if row and row[0].isdigit():
                    t = int(row[0])
                    if s_ms <= t < e_ms:
                        rates[t] = float(row[-1])
        except Exception:  # noqa: BLE001 - a missing month (e.g. before listing) is not an error
            pass
        month = (month + timedelta(days=32)).replace(day=1)
    return (_series(rates), "data.binance.vision") if rates else (pd.Series(dtype=float), "fallback")


def _series(rates: dict[int, float]) -> pd.Series:
    idx = pd.to_datetime(sorted(rates), unit="ms", utc=True)
    return pd.Series([rates[k] for k in sorted(rates)], index=idx, dtype=float)


def daily_funding(rates: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """Rate to charge longs on day d = sum of funding events t in (d, d+1day];
    fallback days (before the first or after the last published rate) are NaN and handled
    by the caller."""
    out = pd.Series(np.nan, index=days)
    if rates.empty:
        return out
    bucket = (rates.index - pd.Timedelta(microseconds=1)).floor("1D")
    summed = rates.groupby(bucket).sum()
    # Days after the last published rate are NOT known to be zero: they fall back too.
    covered = (days >= rates.index[0].floor("1D")) & (days <= bucket.max())
    out[covered] = 0.0
    out.loc[out.index.intersection(summed.index)] = summed.reindex(out.index.intersection(summed.index))
    return out


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@dataclass
class Week:
    start: pd.Timestamp
    ret: float
    pnl: float
    long_pnl: float
    short_pnl: float
    equity_start: float
    symbol_returns: dict[str, float] = field(default_factory=dict)
    costs: float = 0.0    # fees + slippage paid this week (accounting only; added for forward PAPER)
    funding: float = 0.0  # funding paid this week (negative = received)


@dataclass
class FoldResult:
    weeks: list[Week]
    max_dd_pct: float
    ruined: bool
    total_return: float
    funding: float


def mondays(start: str, end: str) -> list[pd.Timestamp]:
    s, e = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    first = s + pd.Timedelta(days=(7 - s.weekday()) % 7)
    out = []
    m = first
    while m + pd.Timedelta(days=7) <= e:
        out.append(m)
        m += pd.Timedelta(days=7)
    return out


def targets(closes: pd.DataFrame, opens: pd.DataFrame, monday: pd.Timestamp, alloc_equity: float,
            leverage: float, benchmark: bool = False) -> dict[str, float]:
    """Target notionals (signed) per eligible symbol, using closes up to the day before `monday`."""
    hist = closes.loc[: monday - pd.Timedelta(days=1)]
    eligible = [s for s in closes.columns
                if hist[s].notna().sum() >= MIN_CLOSES and monday in opens.index and not math.isnan(opens.at[monday, s])]
    if not eligible:
        return {}
    alloc = alloc_equity / len(eligible)
    out = {}
    for s in eligible:
        c = hist[s].dropna()
        if benchmark:
            out[s] = leverage * alloc
            continue
        past = c.loc[: c.index[-1] - pd.Timedelta(days=LOOKBACK_DAYS)]
        if past.empty:
            out[s] = 0.0
            continue
        sign = float(np.sign(c.iloc[-1] / past.iloc[-1] - 1))
        logret = np.log(c.iloc[-(VOL_DAYS + 1):]).diff().dropna()
        sigma = float(logret.std(ddof=1) * math.sqrt(365))
        scale = 1.0 if not sigma or math.isnan(sigma) else min(1.0, TARGET_VOL / sigma)
        out[s] = sign * leverage * alloc * scale
    return out


def simulate_fold(closes: pd.DataFrame, opens: pd.DataFrame, funding: dict[str, pd.Series],
                  weeks: list[pd.Timestamp], leverage: float, *, benchmark: bool = False) -> FoldResult:
    equity = INITIAL_EQUITY
    qty: dict[str, float] = {s: 0.0 for s in closes.columns}
    last_px: dict[str, float] = {}
    curve: list[float] = [equity]
    out: list[Week] = []
    funding_paid = 0.0
    ruined = False
    for monday in weeks:
        week_end = monday + pd.Timedelta(days=7)
        # Mark to this Monday's open, then rebalance there.
        for s in qty:
            px = opens.at[monday, s] if monday in opens.index else math.nan
            if not math.isnan(px):
                if qty[s] and s in last_px:
                    equity += qty[s] * (px - last_px[s])
                last_px[s] = px
        if equity <= 0:
            ruined = True
            break
        e0 = equity
        tgt = targets(closes, opens, monday, e0, leverage, benchmark)
        sym_pnl = {s: 0.0 for s in qty}
        week_costs = week_funding = 0.0
        long_pnl = short_pnl = 0.0
        for s in qty:
            px = last_px.get(s)
            new_q = tgt.get(s, 0.0) / px if px else 0.0
            old_q = qty[s]
            if new_q == old_q or px is None:
                continue
            # closing portion is charged to the old side, opening portion to the new side
            if old_q and (np.sign(old_q) != np.sign(new_q) or abs(new_q) < abs(old_q)):
                closed = abs(old_q) if np.sign(old_q) != np.sign(new_q) else abs(old_q) - abs(new_q)
                c = closed * px * (FEE + SLIPPAGE)
                if old_q > 0:
                    long_pnl -= c
                else:
                    short_pnl -= c
                sym_pnl[s] -= c
                equity -= c
                week_costs += c
            opened = abs(new_q) if np.sign(old_q) != np.sign(new_q) else max(0.0, abs(new_q) - abs(old_q))
            if opened:
                c = opened * px * (FEE + SLIPPAGE)
                if new_q > 0:
                    long_pnl -= c
                else:
                    short_pnl -= c
                sym_pnl[s] -= c
                equity -= c
                week_costs += c
            qty[s] = new_q
        # Hold the week, marking at each daily close; funding on each day's close.
        for day in pd.date_range(monday, week_end - pd.Timedelta(days=1), freq="1D"):
            for s in qty:
                if not qty[s]:
                    continue
                px = closes.at[day, s] if day in closes.index else math.nan
                if math.isnan(px):
                    continue
                move = qty[s] * (px - last_px[s])
                last_px[s] = px
                if benchmark:
                    fund = 0.0
                else:
                    rate = funding[s].get(day, math.nan) if s in funding else math.nan
                    if math.isnan(rate):
                        fund = -abs(qty[s]) * px * FALLBACK_RATE * FALLBACK_EVENTS_PER_DAY
                    else:
                        fund = -qty[s] * px * rate
                funding_paid -= fund
                week_funding -= fund
                equity += move + fund
                sym_pnl[s] += move + fund
                if qty[s] > 0:
                    long_pnl += move + fund
                else:
                    short_pnl += move + fund
            curve.append(equity)
            if equity <= 0:
                ruined = True
                break
        # Mark to next Monday's open so the week owns its whole Sunday-close -> Monday-open gap.
        if not ruined:
            for s in qty:
                px = opens.at[week_end, s] if week_end in opens.index else math.nan
                if qty[s] and not math.isnan(px):
                    d = qty[s] * (px - last_px[s])
                    equity += d
                    sym_pnl[s] += d
                    if qty[s] > 0:
                        long_pnl += d
                    else:
                        short_pnl += d
        alloc = e0 / max(1, len(tgt))
        pnl = equity - e0
        out.append(Week(monday, pnl / e0, pnl, long_pnl, short_pnl, e0,
                        {s: sym_pnl[s] / alloc for s in tgt if tgt[s] or sym_pnl[s]}, week_costs, week_funding))
        if ruined:
            break
    if ruined:
        equity = max(equity, 0.0)
        curve.append(equity)
    peak, worst = -math.inf, 0.0
    for v in curve:
        peak = max(peak, v)
        worst = min(worst, (v - peak) / peak if peak > 0 else -1.0)
    return FoldResult(out, worst * 100, ruined, equity / INITIAL_EQUITY - 1, funding_paid)


# ---------------------------------------------------------------------------
# Statistics and verdict
# ---------------------------------------------------------------------------

def stats_of(values: list[float]) -> dict:
    pos, neg = sum(v for v in values if v > 0), abs(sum(v for v in values if v < 0))
    pf = pos / neg if neg else (math.inf if pos else 0.0)
    mean = float(np.mean(values)) if values else 0.0
    p = float(stats.ttest_1samp(values, 0).pvalue) if len(values) >= 2 else 1.0
    if math.isnan(p):
        p = 1.0
    return {"n": len(values), "mean": mean, "median": float(np.median(values)) if values else 0.0,
            "profit_factor": pf, "p_value": p}


def verdict(folds: list[FoldResult]) -> dict:
    weekly = [w.ret for f in folds for w in f.weeks]
    pnls = [w.pnl for f in folds for w in f.weeks]
    s = stats_of(weekly)
    s["profit_factor"] = stats_of(pnls)["profit_factor"]
    s["folds_positive"] = sum(1 for f in folds if f.total_return > 0)
    if s["n"] >= 30 and (s["mean"] <= 0 or s["profit_factor"] < 1.0):
        s["outcome"] = "NO-GO"
    elif (s["n"] >= 30 and s["profit_factor"] >= 1.3 and s["mean"] > 0 and s["p_value"] < 0.05
          and s["folds_positive"] >= 3):
        s["outcome"] = "GO"
    else:
        s["outcome"] = "INCONCLUSIVE"
    return s


def summarize(folds: list[FoldResult]) -> dict:
    v = verdict(folds)
    v["worst_fold_dd_pct"] = min(f.max_dd_pct for f in folds)
    v["fold_dd_hits"] = {str(lvl): sum(1 for f in folds if f.max_dd_pct <= lvl) / len(folds) for lvl in DD_LEVELS}
    v["ruined_folds"] = sum(f.ruined for f in folds)
    v["fold_returns"] = [f.total_return for f in folds]
    v["fold_dd"] = [f.max_dd_pct for f in folds]
    v["funding_paid"] = sum(f.funding for f in folds)
    v["long"] = stats_of([w.long_pnl / w.equity_start for f in folds for w in f.weeks])
    v["short"] = stats_of([w.short_pnl / w.equity_start for f in folds for w in f.weeks])
    v["long"]["profit_factor"] = stats_of([w.long_pnl for f in folds for w in f.weeks])["profit_factor"]
    v["short"]["profit_factor"] = stats_of([w.short_pnl for f in folds for w in f.weeks])["profit_factor"]
    per_symbol: dict[str, list[float]] = {}
    for f in folds:
        for w in f.weeks:
            for sym, r in w.symbol_returns.items():
                per_symbol.setdefault(sym, []).append(r)
    v["per_symbol"] = {sym: {"weeks": len(r), "mean": float(np.mean(r))} for sym, r in sorted(per_symbol.items())}
    return v


def run_period(closes: pd.DataFrame, opens: pd.DataFrame, funding: dict[str, pd.Series],
               start: str, end: str) -> dict:
    weeks = [m for m in mondays(start, end) if targets(closes, opens, m, 1.0, 1.0)]
    chunks = [list(c) for c in np.array_split(np.array(weeks, dtype=object), N_FOLDS) if len(c)]
    out: dict = {"weeks": len(weeks), "first_week": str(weeks[0]) if weeks else None,
                 "fold_starts": [str(c[0]) for c in chunks]}
    for lev in LEVERAGES:
        out[f"{lev}x"] = summarize([simulate_fold(closes, opens, funding, c, lev) for c in chunks])
    bench = [simulate_fold(closes, opens, funding, c, 1, benchmark=True) for c in chunks]
    out["benchmark_buy_hold"] = summarize(bench)
    return out


def render(label: str, res: dict, sources: dict[str, str]) -> str:
    lines = [f"### {label}", "",
             f"{res['weeks']} weekly rebalances from {res['first_week']}; folds start {', '.join(res['fold_starts'])}.", "",
             "| Leverage | Verdict | Weeks | Mean/week | Median | PF | p | Folds + | Worst fold DD | Folds ≤−20% | ≤−35% | ≤−50% | Ruined | Funding paid |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key in [f"{lv}x" for lv in LEVERAGES] + ["benchmark_buy_hold"]:
        v = res[key]
        h = v["fold_dd_hits"]
        lines.append(f"| {key} | {v['outcome'] if key != 'benchmark_buy_hold' else '(benchmark)'} | {v['n']} | "
                     f"{v['mean']:+.3%} | {v['median']:+.3%} | {v['profit_factor']:.2f} | {v['p_value']:.3f} | "
                     f"{v['folds_positive']}/{len(v['fold_returns'])} | {v['worst_fold_dd_pct']:.1f}% | "
                     f"{h['-20.0']:.0%} | {h['-35.0']:.0%} | {h['-50.0']:.0%} | {v['ruined_folds']} | {v['funding_paid']:,.0f} |")
    one = res["1x"]
    lines += ["", "**1x, long vs short contributions (weekly P&L / equity at week start):**", "",
              "| Side | Mean/week | PF | p |", "|---|---|---|---|"]
    for side in ("long", "short"):
        s = one[side]
        lines.append(f"| {side} | {s['mean']:+.3%} | {s['profit_factor']:.2f} | {s['p_value']:.3f} |")
    lines += ["", "| Fold (1x) | Return | Max DD |", "|---|---|---|"]
    for i, (r, d) in enumerate(zip(one["fold_returns"], one["fold_dd"]), 1):
        lines.append(f"| {i} | {r:+.1%} | {d:.1f}% |")
    lines += ["", "| Symbol (1x) | Symbol-weeks | Mean return on allocation | Funding source |", "|---|---|---|---|"]
    for sym, s in one["per_symbol"].items():
        lines.append(f"| {sym} | {s['weeks']} | {s['mean']:+.3%} | {sources.get(sym, '?')} |")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    symbols = list(dict.fromkeys([*args.symbols, *EXTRA_SYMBOLS]))
    data_start = (pd.Timestamp(PRIMARY[0]) - pd.Timedelta(days=MIN_CLOSES + LOOKBACK_DAYS + 7)).date().isoformat()
    frames, funding, sources, missing = {}, {}, {}, {}
    for s in symbols:
        try:
            frames[s] = fetch_daily(s, data_start, SECONDARY[1])
        except ValueError as exc:
            missing[s] = str(exc)[:200]
            continue
        rates, sources[s] = fetch_funding(s, PRIMARY[0], SECONDARY[1])
        days = pd.date_range(frames[s].index[0], frames[s].index[-1], freq="1D")
        funding[s] = daily_funding(rates, days)
    closes = pd.DataFrame({s: f["close"] for s, f in frames.items()})
    opens = pd.DataFrame({s: f["open"] for s, f in frames.items()})
    full = pd.date_range(closes.index[0], closes.index[-1], freq="1D")
    closes, opens = closes.reindex(full), opens.reindex(full)
    # Missing daily bars between a symbol's own first and last bar (not the days before it listed).
    gaps = {s: int(closes[s].loc[closes[s].first_valid_index():closes[s].last_valid_index()].isna().sum())
            for s in closes}
    report = {"primary": run_period(closes, opens, funding, *PRIMARY),
              "secondary_already_seen": run_period(closes, opens, funding, *SECONDARY),
              "funding_sources": sources, "missing": missing, "gaps": gaps,
              "first_bar": {s: str(closes[s].first_valid_index()) for s in closes}}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "two_way.json").write_text(json.dumps(report, indent=1, default=str))
    md = "\n\n".join([
        "## Two-way time-series momentum (docs/PREREG_TWO_WAY.md)",
        "Daily Binance spot prices as perp proxy; 0.05%/side + 5 bps; funding real where available "
        "(sign: longs pay positive rates), else 0.01%/8h both sides. Verdict on 1x, primary period only.",
        render(f"PRIMARY {PRIMARY[0]} → {PRIMARY[1]} (never used before)", report["primary"], sources),
        render(f"SECONDARY {SECONDARY[0]} → {SECONDARY[1]} (ALREADY SEEN in sections 45/61 — decides nothing)",
               report["secondary_already_seen"], sources),
        "First bars: " + ", ".join(f"{s} {d[:10]}" for s, d in report["first_bar"].items())
        + ("\n\nMissing: " + "; ".join(f"{k} ({v})" for k, v in missing.items()) if missing else "")
        + "\n\nGaps (missing daily bars after listing): " + ", ".join(f"{k} {v}" for k, v in gaps.items() if v),
    ])
    (args.out / "two_way.md").write_text(md + "\n")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
