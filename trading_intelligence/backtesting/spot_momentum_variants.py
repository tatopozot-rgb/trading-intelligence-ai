"""
EXPLORATORY Spot (long-only) variants of the two-way momentum strategy.

Research only. These are NOT pre-registered: they are variants run on data already
used in CHECKPOINT sections 45/61/65 (requested by the leader, 2026-10-09), so they
decide nothing on their own. Spot costs: 0.1% fee per side + 5 bps slippage, no funding.

  A  TSMOM as registered (sign of 28-day return, weekly, 40% vol target capped at 1x of
     the 1/N allocation), with shorts replaced by cash.
  B  Top-3 long-only: among symbols with a positive 28-day return, the 3 with the highest
     vol-scaled 28-day return (r28 / sigma). Each gets min(40%, (40%/sigma)/3) of equity,
     the rest stays in cash, and the total is capped at 100%.
  C  B + a 10% trailing stop on daily closes (exit at the next daily open, stay in cash
     until the next Monday).
  D  B + a 15% trailing stop, same rule.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import two_way_momentum as tw

SPOT_FEE = 0.001
SLIPPAGE = 0.0005
MAX_POSITIONS = 3
MAX_WEIGHT = 0.40
MIN_ORDER_USDT = 5.0
VARIANTS = {"A": None, "B": None, "C": 0.10, "D": 0.15}


def signal_inputs(closes: pd.DataFrame, opens: pd.DataFrame, monday: pd.Timestamp) -> dict[str, tuple[float, float]]:
    """symbol -> (28-day return, annualized 60-day vol) from closes up to the day before `monday`."""
    hist = closes.loc[: monday - pd.Timedelta(days=1)]
    out = {}
    for s in closes.columns:
        c = hist[s].dropna()
        if len(c) < tw.MIN_CLOSES or monday not in opens.index or math.isnan(opens.at[monday, s]):
            continue
        past = c.loc[: c.index[-1] - pd.Timedelta(days=tw.LOOKBACK_DAYS)]
        if past.empty:
            continue
        r28 = float(c.iloc[-1] / past.iloc[-1] - 1)
        sigma = float(np.log(c.iloc[-(tw.VOL_DAYS + 1):]).diff().dropna().std(ddof=1) * math.sqrt(365))
        out[s] = (r28, sigma)
    return out


def weights(variant: str, inputs: dict[str, tuple[float, float]]) -> dict[str, float]:
    if not inputs:
        return {}
    if variant == "A":
        n = len(inputs)
        return {s: (1 / n) * (1.0 if not sigma or math.isnan(sigma) else min(1.0, tw.TARGET_VOL / sigma))
                for s, (r, sigma) in inputs.items() if r > 0}
    ranked = sorted(((r / sigma if sigma else math.inf, s) for s, (r, sigma) in inputs.items() if r > 0), reverse=True)
    w = {}
    for _, s in ranked[:MAX_POSITIONS]:
        sigma = inputs[s][1]
        w[s] = min(MAX_WEIGHT, (tw.TARGET_VOL / sigma if sigma else 1.0) / MAX_POSITIONS)
    total = sum(w.values())
    return {s: v / total for s, v in w.items()} if total > 1 else w


@dataclass
class Result:
    weekly: list[float]
    pnls: list[float]
    turnover: list[float]
    max_dd_pct: float
    total_return: float
    stops: int


def simulate(closes: pd.DataFrame, opens: pd.DataFrame, weeks: list[pd.Timestamp], variant: str) -> Result:
    trail = VARIANTS[variant]
    cost = SPOT_FEE + SLIPPAGE
    equity = tw.INITIAL_EQUITY
    qty: dict[str, float] = {}
    last_px: dict[str, float] = {}
    peak: dict[str, float] = {}
    curve, weekly, pnls, turnover = [equity], [], [], []
    stops = 0
    for monday in weeks:
        for s, q in qty.items():  # mark to Monday open
            px = opens.at[monday, s]
            if not math.isnan(px):
                equity += q * (px - last_px[s])
                last_px[s] = px
        e0 = equity
        target = {s: w * e0 for s, w in weights(variant, signal_inputs(closes, opens, monday)).items()}
        traded = 0.0
        for s in set(qty) | set(target):
            px = opens.at[monday, s]
            if math.isnan(px):
                continue
            new_q = target.get(s, 0.0) / px
            delta = abs(new_q - qty.get(s, 0.0)) * px
            if delta:
                traded += delta
                equity -= delta * cost
            if new_q:
                if s not in qty:
                    peak[s] = px
                qty[s], last_px[s] = new_q, px
            else:
                qty.pop(s, None)
                peak.pop(s, None)
        pending_exit: list[str] = []
        for day in pd.date_range(monday, monday + pd.Timedelta(days=6), freq="1D"):
            for s in pending_exit:  # stop triggered on yesterday's close: sell at today's open
                px = opens.at[day, s]
                if math.isnan(px):
                    px = last_px[s]
                equity += qty[s] * (px - last_px[s]) - qty[s] * px * cost
                traded += qty[s] * px
                qty.pop(s)
                peak.pop(s, None)
                last_px[s] = px
            pending_exit = []
            for s in list(qty):
                px = closes.at[day, s]
                if math.isnan(px):
                    continue
                equity += qty[s] * (px - last_px[s])
                last_px[s] = px
                if trail is not None:
                    peak[s] = max(peak[s], px)
                    if px <= peak[s] * (1 - trail):
                        pending_exit.append(s)
                        stops += 1
            curve.append(equity)
        nxt = monday + pd.Timedelta(days=7)
        for s in pending_exit:  # a stop on Sunday's close exits at Monday's open (the rebalance price)
            px = opens.at[nxt, s] if nxt in opens.index and not math.isnan(opens.at[nxt, s]) else last_px[s]
            equity += qty[s] * (px - last_px[s]) - qty[s] * px * cost
            traded += qty[s] * px
            qty.pop(s)
            peak.pop(s, None)
            last_px[s] = px
        for s, q in qty.items():  # the week owns its gap to next Monday's open
            px = opens.at[nxt, s] if nxt in opens.index else math.nan
            if not math.isnan(px):
                equity += q * (px - last_px[s])
                last_px[s] = px
        weekly.append(equity / e0 - 1)
        pnls.append(equity - e0)
        turnover.append(traded / e0)
    peak_eq, worst = -math.inf, 0.0
    for v in curve + [equity]:
        peak_eq = max(peak_eq, v)
        worst = min(worst, (v - peak_eq) / peak_eq)
    return Result(weekly, pnls, turnover, worst * 100, equity / tw.INITIAL_EQUITY - 1, stops)


def run_period(closes: pd.DataFrame, opens: pd.DataFrame, start: str, end: str) -> dict:
    weeks = [m for m in tw.mondays(start, end) if signal_inputs(closes, opens, m)]
    chunks = [list(c) for c in np.array_split(np.array(weeks, dtype=object), tw.N_FOLDS) if len(c)]
    out: dict = {"weeks": len(weeks)}
    for v in VARIANTS:
        folds = [simulate(closes, opens, c, v) for c in chunks]
        s = tw.stats_of([r for f in folds for r in f.weekly])
        s["profit_factor"] = tw.stats_of([p for f in folds for p in f.pnls])["profit_factor"]
        s.update(folds_positive=sum(f.total_return > 0 for f in folds), folds=len(folds),
                 worst_fold_dd_pct=min(f.max_dd_pct for f in folds),
                 dd20=sum(f.max_dd_pct <= -20 for f in folds) / len(folds),
                 dd35=sum(f.max_dd_pct <= -35 for f in folds) / len(folds),
                 turnover_per_week=float(np.mean([t for f in folds for t in f.turnover])),
                 fold_returns=[f.total_return for f in folds], stops=sum(f.stops for f in folds))
        out[v] = s
    return out


def min_equity_for_a(closes: pd.DataFrame, opens: pd.DataFrame, start: str, end: str) -> dict:
    """Equity needed so every long position A opens is >= MIN_ORDER_USDT, per week."""
    need = []
    for m in tw.mondays(start, end):
        inputs = signal_inputs(closes, opens, m)
        w = weights("A", inputs)
        if w:
            need.append(MIN_ORDER_USDT / min(w.values()))
    q = np.quantile(need, [0.5, 0.9, 1.0]) if need else [math.nan] * 3
    return {"weeks": len(need), "median": float(q[0]), "p90": float(q[1]), "max": float(q[2])}


def render(label: str, res: dict, min_eq: dict) -> str:
    lines = [f"### {label}", "", f"{res['weeks']} weeks, 5 folds, fresh 10,000 each. EXPLORATORY: decides nothing.", "",
             "| Variant | Mean/week | Median | PF | p | Folds + | Worst fold DD | Folds ≤−20% | ≤−35% | Turnover/week | Stops |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for v in VARIANTS:
        s = res[v]
        lines.append(f"| {v} | {s['mean']:+.3%} | {s['median']:+.3%} | {s['profit_factor']:.2f} | {s['p_value']:.3f} | "
                     f"{s['folds_positive']}/{s['folds']} | {s['worst_fold_dd_pct']:.1f}% | {s['dd20']:.0%} | "
                     f"{s['dd35']:.0%} | {s['turnover_per_week']:.1%} | {s['stops']} |")
    lines += ["", "Fold returns: " + "; ".join(f"{v}: " + ", ".join(f"{r:+.0%}" for r in res[v]["fold_returns"])
                                              for v in VARIANTS),
              "", f"Minimum equity for A with every order ≥ {MIN_ORDER_USDT:.0f} USDT: median week "
              f"{min_eq['median']:,.0f}, 90% of weeks {min_eq['p90']:,.0f}, worst week {min_eq['max']:,.0f} USDT."]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EXPLORATORY spot momentum variants (research only)")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    data_start = (pd.Timestamp(tw.PRIMARY[0]) - pd.Timedelta(days=tw.MIN_CLOSES + tw.LOOKBACK_DAYS + 7)).date().isoformat()
    frames = {s: tw.fetch_daily(s, data_start, tw.SECONDARY[1]) for s in args.symbols}
    full = pd.date_range(min(f.index[0] for f in frames.values()), max(f.index[-1] for f in frames.values()), freq="1D")
    closes = pd.DataFrame({s: f["close"] for s, f in frames.items()}).reindex(full)
    opens = pd.DataFrame({s: f["open"] for s, f in frames.items()}).reindex(full)
    report = {}
    md = ["## EXPLORATORY Spot long-only momentum variants (not pre-registered; already-used data)",
          "Spot costs 0.1%/side + 5 bps, no funding. A = TSMOM shorts→cash; B = top-3 long; "
          "C = B + 10% trailing stop; D = B + 15% trailing stop."]
    for label, (s, e) in (("primary", tw.PRIMARY), ("secondary", tw.SECONDARY)):
        res, mq = run_period(closes, opens, s, e), min_equity_for_a(closes, opens, s, e)
        report[label] = {**res, "min_equity_A": mq}
        md.append(render(f"{label.upper()} {s} → {e}", res, mq))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "spot_variants.json").write_text(json.dumps(report, indent=1, default=str))
    text = "\n\n".join(md)
    (args.out / "spot_variants.md").write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
