"""
Post-trade learning: the OBSERVE -> ... -> EXIT -> P&L -> LEARN loop's
closing step — did a strategy actually perform well in the regime the
router placed it in?

Deliberately does NOT auto-adjust any live threshold. A regime that
looks weak in a given sample can look that way from variance, a short
sample, or a real edge that needs it; silently raising/lowering the
router's min_confidence from here would be an unreviewed, un-audited
risk-relevant change — the same category of thing this project's own
risk engine exists to prevent agents from doing to themselves. This
module produces evidence and a plain-language recommendation; a human
(or a reviewed PR) decides whether to act on it.

Does not modify BacktestEngine or StrategyRouter — it tags an existing
BacktestResult's trades with the regime that was active at each trade's
entry bar (re-running the already-tested detect_regime on the same data
slice the engine itself used, via the no-lookahead convention every
other module in this package follows: data up to and including the
entry bar, never beyond it) and aggregates from there.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from trading_intelligence.backtesting.backtest_engine import BacktestTrade
from trading_intelligence.regime.detector import Regime, RegimeSnapshot, detect_regime


@dataclass(frozen=True)
class TaggedTrade:
    trade: BacktestTrade
    regime_at_entry: RegimeSnapshot


def tag_trades_with_regime(
    trades: Sequence[BacktestTrade], data: pd.DataFrame, **detect_kwargs
) -> list[TaggedTrade]:
    """Classify the regime that actually caused each trade: the one the
    router saw at the SIGNAL bar, not the FILL bar. BacktestEngine fills
    one bar after the signal (`trade.entry_bar` is the fill bar, i+1) —
    slicing through `entry_bar` itself (as an earlier version of this
    function did) includes the fill bar's full OHLC, data that didn't
    exist yet at the instant the router made its decision (only that
    bar's open did, which is the fill price). Slicing through
    `entry_bar - 1` instead matches exactly what the router actually saw.
    """
    tagged = []
    for trade in trades:
        window = data.iloc[: trade.entry_bar]
        snapshot = detect_regime(window, **detect_kwargs)
        tagged.append(TaggedTrade(trade=trade, regime_at_entry=snapshot))
    return tagged


@dataclass(frozen=True)
class RegimePerformance:
    regime: Regime
    trade_count: int
    closed_trade_count: int
    win_rate: float
    avg_pnl: float
    total_pnl: float
    avg_confidence_at_entry: float


def summarize_by_regime(tagged_trades: Sequence[TaggedTrade]) -> dict[Regime, RegimePerformance]:
    """Per-regime realized performance. Only closed trades count toward
    win_rate/avg_pnl/total_pnl — an open trade's pnl is 0 by construction
    (BacktestTrade.pnl), which would silently dilute every average if
    counted as a loss or a breakeven."""
    by_regime: dict[Regime, list[TaggedTrade]] = {}
    for tt in tagged_trades:
        by_regime.setdefault(tt.regime_at_entry.regime, []).append(tt)

    summary: dict[Regime, RegimePerformance] = {}
    for regime, group in by_regime.items():
        closed = [tt for tt in group if tt.trade.exit_price is not None]
        pnls = [float(tt.trade.pnl) for tt in closed]
        wins = sum(1 for p in pnls if p > 0)
        summary[regime] = RegimePerformance(
            regime=regime,
            trade_count=len(group),
            closed_trade_count=len(closed),
            win_rate=wins / len(closed) if closed else 0.0,
            avg_pnl=sum(pnls) / len(pnls) if pnls else 0.0,
            total_pnl=sum(pnls),
            avg_confidence_at_entry=sum(tt.regime_at_entry.confidence for tt in group) / len(group),
        )
    return summary


# Below this trade count, a regime's win rate is evidence of nothing —
# flagging it as a recommendation would be noise, not learning.
MIN_TRADES_FOR_A_RECOMMENDATION = 20


def recommend_confidence_adjustments(
    summary: dict[Regime, RegimePerformance], *, poor_win_rate: float = 0.40
) -> list[str]:
    """Plain-language observations for a human to review — never applied
    automatically. See the module docstring for why."""
    notes = []
    for regime, perf in sorted(summary.items(), key=lambda kv: kv[0].value):
        if perf.closed_trade_count < MIN_TRADES_FOR_A_RECOMMENDATION:
            notes.append(
                f"{regime.value}: only {perf.closed_trade_count} closed trades — "
                f"too few to recommend anything; keep collecting evidence."
            )
            continue
        if perf.win_rate < poor_win_rate and perf.total_pnl < 0:
            notes.append(
                f"{regime.value}: {perf.closed_trade_count} trades, "
                f"{perf.win_rate:.0%} win rate, total PnL {perf.total_pnl:.2f} — "
                f"underperforming; consider raising the router's min_confidence "
                f"for this regime, or reviewing whether the routed strategy fits it."
            )
        else:
            notes.append(
                f"{regime.value}: {perf.closed_trade_count} trades, "
                f"{perf.win_rate:.0%} win rate, total PnL {perf.total_pnl:.2f} — "
                f"no concern raised by this sample."
            )
    return notes
