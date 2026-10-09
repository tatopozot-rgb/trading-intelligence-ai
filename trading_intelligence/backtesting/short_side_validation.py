"""
Short side of the 4h trend logic on REAL Binance klines (research only).

Pre-registered in docs/PREREG_SHORT_4H.md before any result was seen; every rule
there is implemented here and must not change after the first run.

BacktestEngine is spot/long-only by design, so this module carries its own small
event loop that reproduces the engine's execution model bar for bar (a test proves
that `simulate(mode="long")` with spot costs gives exactly the engine's trades),
and adds the mirrored short side plus futures-like costs.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from multiprocessing import Pool
from pathlib import Path
from typing import Optional

import pandas as pd
from scipy import stats

from trading_intelligence.analysis.indicators import ma_crossover_signal
from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting.backtest_engine import DEFAULT_RISK_PCT, SLIPPAGE_FACTOR
from trading_intelligence.regime.detector import Regime, detect_regime
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.router import StrategyRouter, default_router
from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover

TIMEFRAME = "4h"
START, END = "2022-10-01", "2026-10-01"
EXTRA_SYMBOLS = ("PAXGUSDT",)
FUTURES_FEE = Decimal("0.0005")
FUNDING_RATE = Decimal("0.0001")
FUNDING_HOURS = (0, 8, 16)
MODES = ("long", "short", "long+short")
MIN_TRADES = 30
GO_PROFIT_FACTOR = 1.3
MAX_P_VALUE = 0.05


class MirroredShortMACrossover(AbstractStrategy):
    """Mirror of DualMACrossover as default_router configures it: short on a bearish
    EMA 20/50 cross, stop at the highest high of the previous 10 bars, exit on a
    bullish cross. Research only: it never emits a TradeProposal (those are BUY-only)."""

    def __init__(self, symbol: str, timeframe: str = TIMEFRAME):
        params = {"fast_period": 20, "slow_period": 50, "ma_type": "ema", "stop_lookback": 10}
        super().__init__(f"ma_crossover_short_{symbol}_{timeframe}", symbol, timeframe, params)

    def on_bar(self, data: pd.DataFrame) -> None:
        raise NotImplementedError("use short_stop(); TradeProposal is long-only")

    def short_stop(self, data: pd.DataFrame) -> Optional[Decimal]:
        p = self.params
        if len(data) < max(p["slow_period"], p["stop_lookback"]) + 2:
            return None
        signal = ma_crossover_signal(data["close"], p["fast_period"], p["slow_period"], p["ma_type"])
        if signal.iloc[-1] != -1:
            return None
        stop = Decimal(str(data["high"].iloc[-(p["stop_lookback"] + 1):-1].max()))
        return stop if stop > Decimal(str(data["close"].iloc[-1])) else None

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        p = self.params
        if len(data) < p["slow_period"] + 2:
            return False
        signal = ma_crossover_signal(data["close"], p["fast_period"], p["slow_period"], p["ma_type"])
        return bool(signal.iloc[-1] == 1)


def short_router(symbol: str) -> StrategyRouter:
    router = StrategyRouter()
    strategy = MirroredShortMACrossover(symbol)
    router.register(Regime.TREND_DOWN, strategy, min_confidence=0.5)
    router.register(Regime.BREAKOUT_DOWN, strategy, min_confidence=0.0)
    return router


@dataclass
class Trade:
    side: str  # "long" | "short"
    entry_time: pd.Timestamp
    entry_price: Decimal
    quantity: Decimal
    stop_price: Decimal
    entry_fee: Decimal
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[Decimal] = None
    exit_reason: str = ""
    exit_fee: Decimal = Decimal("0")
    funding: Decimal = Decimal("0")

    @property
    def pnl(self) -> Decimal:
        if self.exit_price is None:
            return Decimal("0")
        move = self.exit_price - self.entry_price
        gross = (move if self.side == "long" else -move) * self.quantity
        return gross - self.entry_fee - self.exit_fee - self.funding

    @property
    def return_pct(self) -> float:
        cost = float(self.entry_price * self.quantity + self.entry_fee)
        return float(self.pnl) / cost if cost else 0.0


def funding_events(entry: pd.Timestamp, exit_: pd.Timestamp) -> int:
    """Funding timestamps t (00/08/16 UTC) with entry < t <= exit."""
    t = entry.floor("8h") + timedelta(hours=8)
    n = 0
    while t <= exit_:
        if t.hour in FUNDING_HOURS:
            n += 1
        t += timedelta(hours=8)
    return n


@dataclass
class Simulation:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    @property
    def max_drawdown_pct(self) -> float:
        peak, worst = -math.inf, 0.0
        for v in self.equity_curve:
            peak = max(peak, v)
            worst = min(worst, (v - peak) / peak)
        return worst * 100


def simulate(
    data: pd.DataFrame,
    symbol: str,
    mode: str,
    *,
    fee: Decimal = FUTURES_FEE,
    funding_rate: Decimal = FUNDING_RATE,
    slippage: Decimal = SLIPPAGE_FACTOR,
    history_bars: int = rdv.HISTORY_BARS,
    initial_equity: Decimal = Decimal("10000"),
) -> Simulation:
    """BacktestEngine's loop (same order of checks, fills and sizing), both directions."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    long_router = default_router(symbol, TIMEFRAME) if mode in ("long", "long+short") else None
    s_router = short_router(symbol) if mode in ("short", "long+short") else None
    equity = initial_equity
    sim = Simulation()
    open_trade: Optional[Trade] = None
    exit_strategy: Optional[AbstractStrategy] = None

    def close(trade: Trade, when: pd.Timestamp, price: Decimal, reason: str) -> Decimal:
        trade.exit_time, trade.exit_price, trade.exit_reason = when, price, reason
        trade.exit_fee = price * trade.quantity * fee
        if trade.side == "short":
            notional = trade.entry_price * trade.quantity
            trade.funding = notional * funding_rate * funding_events(trade.entry_time, when)
        return trade.pnl

    for i in range(1, len(data)):
        bar = data.iloc[i]
        historical = data.iloc[max(0, i + 1 - history_bars): i + 1]

        if open_trade is not None:
            bar_open = Decimal(str(bar["open"]))
            if open_trade.side == "long" and Decimal(str(bar["low"])) <= open_trade.stop_price:
                fill = (bar_open * (1 - slippage) if bar_open < open_trade.stop_price
                        else open_trade.stop_price * (1 - 2 * slippage))
                equity += close(open_trade, data.index[i], fill, "stop")
                open_trade = exit_strategy = None
            elif open_trade.side == "short" and Decimal(str(bar["high"])) >= open_trade.stop_price:
                fill = (bar_open * (1 + slippage) if bar_open > open_trade.stop_price
                        else open_trade.stop_price * (1 + 2 * slippage))
                equity += close(open_trade, data.index[i], fill, "stop")
                open_trade = exit_strategy = None

        if open_trade is None:
            side: Optional[str] = None
            stop: Optional[Decimal] = None
            strategy: Optional[AbstractStrategy] = None
            snapshot = detect_regime(historical)
            if long_router is not None:
                routed = long_router.route(snapshot).strategy
                if isinstance(routed, DualMACrossover):
                    proposal = routed.on_bar(historical)
                    if proposal is not None:
                        side, stop, strategy = "long", proposal.stop_price, routed
            if side is None and s_router is not None:
                routed = s_router.route(snapshot).strategy
                if isinstance(routed, MirroredShortMACrossover):
                    short_stop = routed.short_stop(historical)
                    if short_stop is not None:
                        side, stop, strategy = "short", short_stop, routed
            if side is not None and stop is not None:
                if i + 1 >= len(data):
                    break
                nxt_open = Decimal(str(data.iloc[i + 1]["open"]))
                fill = nxt_open * (1 + slippage) if side == "long" else nxt_open * (1 - slippage)
                qty = _size(equity, fill, stop, fee)
                if qty <= 0:
                    continue
                open_trade = Trade(side, data.index[i + 1], fill, qty, stop, fill * qty * fee)
                sim.trades.append(open_trade)
                exit_strategy = strategy
        elif open_trade is not None:
            assert exit_strategy is not None
            if exit_strategy.on_exit_signal(historical, open_trade.entry_price):
                sign = -1 if open_trade.side == "long" else 1
                if i + 1 < len(data):
                    fill = Decimal(str(data.iloc[i + 1]["open"])) * (1 + sign * slippage)
                else:
                    fill = Decimal(str(bar["close"])) * (1 + sign * slippage)
                equity += close(open_trade, data.index[min(i + 1, len(data) - 1)], fill, "signal")
                open_trade = exit_strategy = None

        sim.equity_curve.append(float(equity))

    if open_trade is not None:
        equity += close(open_trade, data.index[-1], Decimal(str(data.iloc[-1]["close"])), "end_of_data")
        sim.equity_curve.append(float(equity))
    return sim


def _size(equity: Decimal, entry: Decimal, stop: Decimal, fee: Decimal) -> Decimal:
    """BacktestEngine._size_position, with the stop distance taken on the trade's side."""
    risk_amount = equity * (DEFAULT_RISK_PCT / Decimal("100"))
    effective_stop = abs(entry - stop) / entry + 2 * fee
    if effective_stop <= 0:
        return Decimal("0")
    qty = min(risk_amount / (entry * effective_stop), equity / (entry * (1 + fee)))
    return qty.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)


def oos_windows(data: pd.DataFrame) -> list[pd.DataFrame]:
    n = len(data)
    is_size, oos_size = int(n * rdv.IS_PCT), int(n * rdv.OOS_PCT)
    return [data.iloc[is_size + k * oos_size: is_size + (k + 1) * oos_size]
            for k in range(rdv.MAX_FOLDS) if is_size + (k + 1) * oos_size <= n]


def run_symbol(symbol: str, data: pd.DataFrame) -> dict:
    out: dict = {"symbol": symbol, "bars": len(data), "first_bar": str(data.index[0]),
                 "gaps": rdv.count_gaps(data, TIMEFRAME), "modes": {}}
    for mode in MODES:
        folds = [simulate(window, symbol, mode) for window in oos_windows(data)]
        trades = [t for f in folds for t in f.trades if t.exit_price is not None]
        out["modes"][mode] = {
            "returns": [t.return_pct for t in trades],
            "pnls": [float(t.pnl) for t in trades],
            "sides": [t.side for t in trades],
            "funding": float(sum((t.funding for t in trades), Decimal("0"))),
            "fold_trades": [len(f.trades) for f in folds],
            "fold_mean": [sum(t.return_pct for t in f.trades) / len(f.trades) if f.trades else 0.0 for f in folds],
            "fold_max_dd_pct": [f.max_drawdown_pct for f in folds],
        }
    return out


def verdict(returns: list[float], pnls: list[float]) -> dict:
    wins, losses = sum(p for p in pnls if p > 0), abs(sum(p for p in pnls if p <= 0))
    pf = wins / losses if losses else (math.inf if wins else 0.0)
    mean = sum(returns) / len(returns) if returns else 0.0
    p = float(stats.ttest_1samp(returns, 0).pvalue) if len(returns) >= 2 else 1.0
    if math.isnan(p):
        p = 1.0
    if len(returns) >= MIN_TRADES and (mean <= 0 or pf < 1.0):
        outcome = "NO-GO"
    elif len(returns) >= MIN_TRADES and pf >= GO_PROFIT_FACTOR and mean > 0 and p < MAX_P_VALUE:
        outcome = "GO"
    else:
        outcome = "INCONCLUSIVE"
    return {"outcome": outcome, "trades": len(returns), "mean": mean,
            "median": float(pd.Series(returns).median()) if returns else 0.0,
            "win_rate": sum(1 for x in pnls if x > 0) / len(pnls) if pnls else 0.0,
            "profit_factor": pf, "p_value": p, "total_pnl": sum(pnls)}


def pool(symbols: list[dict], mode: str) -> dict:
    m = [s["modes"][mode] for s in symbols]
    result = verdict([r for x in m for r in x["returns"]], [p for x in m for p in x["pnls"]])
    result["worst_fold_dd_pct"] = min((d for x in m for d in x["fold_max_dd_pct"]), default=0.0)
    result["funding"] = sum(x["funding"] for x in m)
    result["short_trades"] = sum(x["sides"].count("short") for x in m)
    return result


def render(symbols: list[dict], excluded: dict[str, str]) -> str:
    lines = [f"## Short side of `tendencia` @ {TIMEFRAME} — {START} → {END} (docs/PREREG_SHORT_4H.md)", "",
             "Futures-like costs: 0.05%/side, 5 bps slippage, funding 0.01%/8h on shorts. "
             "OOS = last 50% in 5 cold folds, pooled over symbols.", "",
             "| Mode | Verdict | Trades | Win rate | Mean net/trade | Median | PF | p | Worst fold DD | Total OOS P&L | Funding |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for mode in MODES:
        v = pool(symbols, mode)
        lines.append(f"| {mode} | **{v['outcome']}** | {v['trades']} | {v['win_rate']:.1%} | {v['mean']:+.3%} | "
                     f"{v['median']:+.3%} | {v['profit_factor']:.2f} | {v['p_value']:.3f} | "
                     f"{v['worst_fold_dd_pct']:.1f}% | {v['total_pnl']:+,.0f} | {v['funding']:,.0f} |")
    lines += ["", "| Symbol | Bars | Gaps | " + " | ".join(f"{m} trades / mean" for m in MODES) + " |",
              "|---|---|---|" + "---|" * len(MODES)]
    for s in symbols:
        cells = []
        for mode in MODES:
            r = s["modes"][mode]["returns"]
            cells.append(f"{len(r)} / {sum(r) / len(r):+.2%}" if r else "0 / —")
        lines.append(f"| {s['symbol']} | {s['bars']} | {s['gaps']} | " + " | ".join(cells) + " |")
    lines += ["", "| Fold | " + " | ".join(f"{m} trades / mean" for m in MODES) + " |",
              "|---|" + "---|" * len(MODES)]
    for k in range(rdv.MAX_FOLDS):
        cells = []
        for mode in MODES:
            n = sum(s["modes"][mode]["fold_trades"][k] for s in symbols if len(s["modes"][mode]["fold_trades"]) > k)
            rs = [s["modes"][mode]["fold_mean"][k] * s["modes"][mode]["fold_trades"][k]
                  for s in symbols if len(s["modes"][mode]["fold_trades"]) > k]
            cells.append(f"{n} / {sum(rs) / n:+.2%}" if n else "0 / —")
        lines.append(f"| {k + 1} | " + " | ".join(cells) + " |")
    if excluded:
        lines += ["", "Excluded: " + "; ".join(f"{k} ({v})" for k, v in excluded.items())]
    return "\n".join(lines)


def _job(symbol: str) -> dict:
    started = time.time()
    start = datetime.fromisoformat(START).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(END).replace(tzinfo=timezone.utc)
    try:
        data = rdv.fetch_klines(symbol, TIMEFRAME, start, end)
    except ValueError as exc:
        return {"symbol": symbol, "excluded": f"no data: {exc}"[:200]}
    if data.index[0] > pd.Timestamp(start) + pd.Timedelta(days=1):
        return {"symbol": symbol, "excluded": f"first bar {data.index[0]} is after {START}"}
    out = run_symbol(symbol, data)
    out["seconds"] = round(time.time() - started, 1)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    symbols = list(dict.fromkeys([*args.symbols, *EXTRA_SYMBOLS]))
    with Pool(max(1, args.workers)) as p:
        results = p.map(_job, symbols)
    excluded = {r["symbol"]: r["excluded"] for r in results if "excluded" in r}
    kept = [r for r in results if "excluded" not in r]
    pooled = {mode: pool(kept, mode) for mode in MODES}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "short_side.json").write_text(json.dumps(
        {"start": START, "end": END, "pooled": pooled, "excluded": excluded, "symbols": kept}, indent=1, default=str))
    markdown = render(kept, excluded)
    (args.out / "short_side.md").write_text(markdown + "\n")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
