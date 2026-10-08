"""
Walk-forward validation of the live operator's profiles on REAL Binance klines.

Research only: public klines from data-api.binance.vision (no account, no key,
no orders). Built to run on GitHub Actions, since the cloud container cannot
reach Binance; see .github/workflows/real-data-walk-forward.yml.

Protocol, fixed before any real-data result was seen:
  * Profiles exactly as trading_intelligence/live/operator.py builds them:
    tendencia -> default_router(symbol, timeframe);
    tendencia_rango -> router_with_range_reversion(symbol).
  * Each decision sees the trailing HISTORY_BARS (500) bars, like
    PaperTradingRunner. Costs: 0.1% fee per side, 5 bps slippage (BacktestEngine).
  * Anchored walk-forward per symbol: IS starts at bar 0; IS = first 50%, five
    consecutive non-overlapping OOS windows of 10% each, so the whole second
    half is out-of-sample. Each OOS engine starts cold (framework behavior).
  * Framework verdict per symbol: WalkForwardReport.go_no_go() over the folds
    whose IS Sharpe >= 0.5 (folds failing the IS gate are not counted).
  * Pooled verdict per profile x timeframe, over ALL OOS windows of all symbols
    (no IS gate, so the real out-of-sample expectancy is visible even when the
    gate skips everything). GO only if all hold: >= 30 trades, profit factor
    >= 1.3, mean net return per trade > 0 with t-test p < 0.05, and at least
    half the symbols GO under the framework verdict.
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from scipy import stats

from trading_intelligence.backtesting.backtest_engine import BacktestEngine, BacktestResult
from trading_intelligence.backtesting.walk_forward import WalkForwardFold, WalkForwardReport
from trading_intelligence.data.binance_public_feed import (
    DEFAULT_BASE_URL,
    _check_kline,
    _urllib_get,
)
from trading_intelligence.strategy.router import StrategyRouter

HISTORY_BARS = 500
IS_PCT = 0.5
OOS_PCT = 0.1
MAX_FOLDS = 5
IS_SHARPE_GATE = 0.5
MIN_POOLED_TRADES = 30
MIN_PROFIT_FACTOR = 1.3
MAX_P_VALUE = 0.05
INTERVAL_MS = {"1h": 3_600_000, "4h": 14_400_000}
PROFILES = ("tendencia", "tendencia_rango")


def profile_router(profile: str, symbol: str, timeframe: str) -> StrategyRouter:
    from trading_intelligence.strategy.router import default_router, router_with_range_reversion

    if profile == "tendencia_rango":
        return router_with_range_reversion(symbol)
    if profile == "tendencia":
        return default_router(symbol, timeframe)
    raise ValueError(f"unknown profile {profile!r}")


def fetch_klines(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    *,
    get: Callable[[str, float], bytes] = _urllib_get,
    base_url: str = DEFAULT_BASE_URL,
) -> pd.DataFrame:
    """Closed klines with open_time in [start, end), paginated 1000 at a time."""
    step = INTERVAL_MS[interval]
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    rows: dict[int, dict] = {}
    cursor = start_ms
    while cursor < end_ms:
        params = {"symbol": symbol, "interval": interval, "startTime": cursor,
                  "endTime": end_ms - 1, "limit": 1000}
        payload = json.loads(get(f"{base_url}/api/v3/klines?{urllib.parse.urlencode(params)}", 30.0))
        if not isinstance(payload, list):
            raise ValueError(f"unexpected klines payload for {symbol}: {str(payload)[:200]}")
        if not payload:
            break
        for k in payload:
            open_time = int(k[0])
            row = {"open_time": open_time, "open": float(k[1]), "high": float(k[2]),
                   "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])}
            _check_kline(symbol, row)
            if start_ms <= open_time < end_ms:
                rows[open_time] = row
        last = int(payload[-1][0])
        if last + step <= cursor:
            raise ValueError(f"klines for {symbol} did not advance past {cursor}")
        cursor = last + step
    frame = pd.DataFrame(sorted(rows.values(), key=lambda r: r["open_time"]))
    if frame.empty:
        raise ValueError(f"no klines for {symbol} {interval}")
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    return frame.set_index("open_time")


def count_gaps(data: pd.DataFrame, interval: str) -> int:
    expected = pd.Timedelta(milliseconds=INTERVAL_MS[interval])
    return int((data.index.to_series().diff().dropna() > expected).sum())


@dataclass
class FoldOutcome:
    fold: WalkForwardFold
    is_gate_passed: bool


def walk_forward_symbol(
    data: pd.DataFrame, router_factory: Callable[[], StrategyRouter], history_bars: int = HISTORY_BARS
) -> list[FoldOutcome]:
    n = len(data)
    is_size, oos_size = int(n * IS_PCT), int(n * OOS_PCT)
    outcomes = []
    for k in range(MAX_FOLDS):
        oos_start = is_size + k * oos_size
        oos_end = oos_start + oos_size
        if oos_end > n:
            break
        is_data, oos_data = data.iloc[:oos_start], data.iloc[oos_start:oos_end]
        results: list[BacktestResult] = []
        for window in (is_data, oos_data):
            result = BacktestEngine(router=router_factory(), history_bars=history_bars).run(window)
            result.compute_metrics()
            results.append(result)
        fold = WalkForwardFold(
            fold_id=k + 1, is_start=is_data.index[0], is_end=is_data.index[-1],
            oos_start=oos_data.index[0], oos_end=oos_data.index[-1],
            is_result=results[0], oos_result=results[1],
        )
        outcomes.append(FoldOutcome(fold, results[0].sharpe_ratio >= IS_SHARPE_GATE))
    return outcomes


def summarize_symbol(symbol: str, data: pd.DataFrame, outcomes: list[FoldOutcome], interval: str) -> dict:
    gated = WalkForwardReport([o.fold for o in outcomes if o.is_gate_passed], symbol, {})
    go, reason = gated.go_no_go()
    trades = [t for o in outcomes for t in o.fold.oos_result.trades if t.exit_price is not None]
    oos_close = data["close"].iloc[int(len(data) * IS_PCT):]
    return {
        "symbol": symbol,
        "bars": len(data),
        "first_bar": str(data.index[0]),
        "last_bar": str(data.index[-1]),
        "gaps": count_gaps(data, interval),
        "framework_go": go,
        "framework_reason": reason,
        "folds": len(outcomes),
        "folds_passing_is_gate": sum(o.is_gate_passed for o in outcomes),
        "oos_trade_returns": [t.return_pct for t in trades],
        "oos_trade_pnls": [float(t.pnl) for t in trades],
        "oos_fees": float(sum((t.entry_fee + t.exit_fee for t in trades), Decimal("0"))),
        "oos_sharpe_by_fold": [o.fold.oos_result.sharpe_ratio for o in outcomes],
        "oos_max_dd_pct_by_fold": [o.fold.oos_result.max_drawdown_pct for o in outcomes],
        "buy_hold_oos_return": float(oos_close.iloc[-1] / oos_close.iloc[0] - 1) if len(oos_close) > 1 else 0.0,
    }


def pool_verdict(symbols: list[dict]) -> dict:
    returns = [r for s in symbols for r in s["oos_trade_returns"]]
    pnls = [p for s in symbols for p in s["oos_trade_pnls"]]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_loss = abs(sum(losses))
    profit_factor = sum(wins) / gross_loss if gross_loss else (math.inf if wins else 0.0)
    mean_ret = sum(returns) / len(returns) if returns else 0.0
    p_value = float(stats.ttest_1samp(returns, 0).pvalue) if len(returns) >= 2 else 1.0
    if math.isnan(p_value):
        p_value = 1.0
    symbols_go = sum(s["framework_go"] for s in symbols)
    reasons = []
    if len(returns) < MIN_POOLED_TRADES:
        reasons.append(f"{len(returns)} OOS trades < {MIN_POOLED_TRADES}")
    if profit_factor < MIN_PROFIT_FACTOR:
        reasons.append(f"profit factor {profit_factor:.2f} < {MIN_PROFIT_FACTOR}")
    if not (mean_ret > 0 and p_value < MAX_P_VALUE):
        reasons.append(f"mean net return/trade {mean_ret:+.4%} (p={p_value:.3f}) not significantly > 0")
    if symbols_go * 2 < len(symbols):
        reasons.append(f"only {symbols_go}/{len(symbols)} symbols GO under the framework")
    dd = [d for s in symbols for d in s["oos_max_dd_pct_by_fold"]]
    return {
        "go": not reasons,
        "reasons": reasons,
        "oos_trades": len(returns),
        "win_rate": len(wins) / len(pnls) if pnls else 0.0,
        "mean_net_return_per_trade": mean_ret,
        "median_net_return_per_trade": float(pd.Series(returns).median()) if returns else 0.0,
        "profit_factor": profit_factor,
        "p_value": p_value,
        "worst_oos_fold_max_dd_pct": min(dd) if dd else 0.0,
        "symbols_go": symbols_go,
        "symbols": len(symbols),
        "oos_fees": sum(s["oos_fees"] for s in symbols),
        "mean_buy_hold_oos_return": sum(s["buy_hold_oos_return"] for s in symbols) / len(symbols) if symbols else 0.0,
    }


def _run_symbol(args: tuple[str, str, str, str, str]) -> dict:
    profile, symbol, interval, start, end = args
    started = time.time()
    data = fetch_klines(symbol, interval, datetime.fromisoformat(start), datetime.fromisoformat(end))
    outcomes = walk_forward_symbol(data, lambda: profile_router(profile, symbol, interval))
    summary = summarize_symbol(symbol, data, outcomes, interval)
    summary["seconds"] = round(time.time() - started, 1)
    return summary


def render_markdown(profile: str, interval: str, start: str, end: str, symbols: list[dict], pooled: dict) -> str:
    lines = [
        f"### {profile} @ {interval} — {'GO' if pooled['go'] else 'NO-GO'}",
        f"Data {start} → {end} (public Binance klines), OOS = last 50% in 5 folds, "
        f"window {HISTORY_BARS} bars, fee 0.1%/side, slippage 5 bps.",
        "",
        f"- OOS trades (all folds, all symbols): **{pooled['oos_trades']}**; win rate "
        f"{pooled['win_rate']:.1%}; mean net return/trade **{pooled['mean_net_return_per_trade']:+.3%}** "
        f"(median {pooled['median_net_return_per_trade']:+.3%}); profit factor {pooled['profit_factor']:.2f}; "
        f"t-test p={pooled['p_value']:.3f}",
        f"- Worst OOS-fold max drawdown {pooled['worst_oos_fold_max_dd_pct']:.1f}%; OOS fees "
        f"{pooled['oos_fees']:.2f} (on 10,000 per symbol); mean buy-and-hold over the same OOS "
        f"{pooled['mean_buy_hold_oos_return']:+.1%}",
        f"- Framework (IS-gated) GO symbols: {pooled['symbols_go']}/{pooled['symbols']}",
        f"- Verdict reasons: {'; '.join(pooled['reasons']) or 'all criteria met'}",
        "",
        "| Symbol | Bars | Gaps | OOS trades | Mean net/trade | Folds IS-gate | Framework | Buy&hold OOS |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in symbols:
        n = len(s["oos_trade_returns"])
        mean = sum(s["oos_trade_returns"]) / n if n else 0.0
        lines.append(
            f"| {s['symbol']} | {s['bars']} | {s['gaps']} | {n} | {mean:+.3%} | "
            f"{s['folds_passing_is_gate']}/{s['folds']} | {'GO' if s['framework_go'] else 'NO-GO'} | "
            f"{s['buy_hold_oos_return']:+.1%} |"
        )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--timeframe", choices=sorted(INTERVAL_MS), required=True)
    parser.add_argument("--start", required=True, help="ISO date, UTC, inclusive")
    parser.add_argument("--end", required=True, help="ISO date, UTC, exclusive")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc).isoformat()
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc).isoformat()
    jobs = [(args.profile, s, args.timeframe, start, end) for s in args.symbols]
    with Pool(max(1, args.workers)) as pool:
        symbols = pool.map(_run_symbol, jobs)
    pooled = pool_verdict(symbols)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.profile}_{args.timeframe}"
    (args.out / f"{stem}.json").write_text(json.dumps(
        {"profile": args.profile, "timeframe": args.timeframe, "start": start, "end": end,
         "pooled": pooled, "symbols": symbols}, indent=1, default=str))
    markdown = render_markdown(args.profile, args.timeframe, args.start, args.end, symbols, pooled)
    (args.out / f"{stem}.md").write_text(markdown + "\n")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
