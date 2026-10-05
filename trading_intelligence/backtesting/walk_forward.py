"""
Walk-forward analysis — anchored and rolling windows.

Per STRATEGY_VALIDATION_FRAMEWORK.md:
  - IS Sharpe >= 0.5 required to proceed to OOS
  - OOS Sharpe >= 0.5 required to pass
  - Profit Factor >= 1.3 (after fees) required to pass
  - Minimum 30 OOS trades required for statistical validity
  - p < 0.05 on trade returns (one-sample t-test, H0: mean=0)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from trading_intelligence.backtesting.backtest_engine import BacktestEngine, BacktestResult
from trading_intelligence.strategy.base import AbstractStrategy

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardFold:
    fold_id: int
    is_start: pd.Timestamp
    is_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp
    is_result: BacktestResult
    oos_result: BacktestResult

    @property
    def passes_minimum_thresholds(self) -> bool:
        """OOS must pass all thresholds."""
        oos = self.oos_result
        oos.compute_metrics()
        return (
            oos.sharpe_ratio >= 0.5
            and oos.profit_factor >= 1.3
            and oos.total_trades >= 30
        )


@dataclass
class WalkForwardReport:
    folds: list[WalkForwardFold]
    strategy_id: str
    params: dict

    @property
    def oos_sharpe_values(self) -> list[float]:
        return [f.oos_result.sharpe_ratio for f in self.folds]

    @property
    def oos_profit_factors(self) -> list[float]:
        return [f.oos_result.profit_factor for f in self.folds]

    @property
    def folds_passing(self) -> int:
        return sum(1 for f in self.folds if f.passes_minimum_thresholds)

    def statistical_significance(self) -> tuple[float, float]:
        """
        t-test on all OOS trade P&L values. H0: mean = 0.
        Returns (t_statistic, p_value).
        """
        all_pnls = []
        for fold in self.folds:
            for trade in fold.oos_result.trades:
                if trade.exit_price is not None:
                    all_pnls.append(float(trade.pnl))
        if len(all_pnls) < 2:
            return 0.0, 1.0
        t_stat, p_value = stats.ttest_1samp(all_pnls, 0)
        return float(t_stat), float(p_value)

    def go_no_go(self) -> tuple[bool, str]:
        """
        Apply go/no-go decision matrix from STRATEGY_VALIDATION_FRAMEWORK.md.
        Returns (go: bool, reason: str).
        """
        total_folds = len(self.folds)
        if total_folds == 0:
            return False, "No folds completed"

        passing_pct = self.folds_passing / total_folds
        t_stat, p_value = self.statistical_significance()

        all_oos_trades = sum(
            fold.oos_result.total_trades for fold in self.folds
        )

        reasons = []
        go = True

        if passing_pct < 0.5:
            go = False
            reasons.append(
                f"Only {self.folds_passing}/{total_folds} folds pass thresholds "
                f"({passing_pct:.0%} < 50%)"
            )

        if p_value >= 0.05:
            go = False
            reasons.append(
                f"No statistical significance: p={p_value:.3f} >= 0.05"
            )

        if all_oos_trades < 30:
            go = False
            reasons.append(
                f"Insufficient OOS trades: {all_oos_trades} < 30 required"
            )

        mean_oos_sharpe = (
            sum(self.oos_sharpe_values) / len(self.oos_sharpe_values)
            if self.oos_sharpe_values else 0.0
        )
        if mean_oos_sharpe < 0.5:
            go = False
            reasons.append(
                f"Mean OOS Sharpe {mean_oos_sharpe:.2f} < 0.5 required"
            )

        if go:
            return True, (
                f"PASS: {passing_pct:.0%} folds pass, p={p_value:.3f}, "
                f"OOS trades={all_oos_trades}, mean Sharpe={mean_oos_sharpe:.2f}"
            )
        return False, " | ".join(reasons)

    def summary(self) -> str:
        go, reason = self.go_no_go()
        label = "GO" if go else "NO-GO"
        lines = [
            f"Walk-Forward: {self.strategy_id} — {label}",
            f"Reason: {reason}",
            f"Folds: {len(self.folds)} total, {self.folds_passing} passing",
        ]
        for i, fold in enumerate(self.folds, 1):
            oos = fold.oos_result
            lines.append(
                f"  Fold {i}: OOS Sharpe={oos.sharpe_ratio:.2f}, "
                f"PF={oos.profit_factor:.2f}, Trades={oos.total_trades}"
            )
        return "\n".join(lines)


def run_anchored_walk_forward(
    strategy_factory,          # callable(params) -> AbstractStrategy
    params: dict,
    data: pd.DataFrame,
    initial_equity: Decimal = Decimal("10000"),
    is_pct: float = 0.6,       # IS window as fraction of total data
    oos_pct: float = 0.2,      # OOS window
    step_pct: float = 0.1,     # step size for rolling folds
    max_folds: int = 5,
) -> WalkForwardReport:
    """
    Anchored walk-forward: IS always starts from the beginning.
    IS expands, OOS slides forward.

    is_pct, oos_pct, step_pct are fractions of total data length.
    """
    n = len(data)
    is_size = int(n * is_pct)
    oos_size = int(n * oos_pct)
    step = max(1, int(n * step_pct))

    folds: list[WalkForwardFold] = []
    fold_id = 0
    oos_start_idx = is_size

    while oos_start_idx + oos_size <= n and fold_id < max_folds:
        oos_end_idx = oos_start_idx + oos_size
        is_data = data.iloc[:oos_start_idx]
        oos_data = data.iloc[oos_start_idx:oos_end_idx]

        is_strategy = strategy_factory(params)
        oos_strategy = strategy_factory(params)

        is_engine = BacktestEngine(is_strategy, initial_equity=initial_equity)
        oos_engine = BacktestEngine(oos_strategy, initial_equity=initial_equity)

        is_result = is_engine.run(is_data)
        is_result.compute_metrics()

        if is_result.sharpe_ratio < 0.5:
            logger.info(
                "Fold %d: IS Sharpe %.2f < 0.5 — skipping OOS",
                fold_id + 1, is_result.sharpe_ratio,
            )
            oos_start_idx += step
            fold_id += 1
            continue

        oos_result = oos_engine.run(oos_data)
        oos_result.compute_metrics()

        folds.append(
            WalkForwardFold(
                fold_id=fold_id + 1,
                is_start=is_data.index[0],
                is_end=is_data.index[-1],
                oos_start=oos_data.index[0],
                oos_end=oos_data.index[-1],
                is_result=is_result,
                oos_result=oos_result,
            )
        )

        oos_start_idx += step
        fold_id += 1

    return WalkForwardReport(folds=folds, strategy_id=params.get("strategy_id", "unknown"), params=params)
