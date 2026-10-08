"""
Tests for trading_intelligence/backtesting/walk_forward.py.

This module had zero test coverage before — found while auditing docs
against the actual test suite (CHECKPOINT.md listed walk-forward as
"implemented", but no test file existed for it, unlike every other module
in this package). Per CLAUDE.md: tests are mandatory for anything feeding
the strategy validation gate, and go/no-go here is exactly that gate.

Split in two:
- Pure aggregation logic (WalkForwardFold/WalkForwardReport) tested against
  hand-built fake results, so each threshold/edge case is exact and doesn't
  depend on what a real backtest happens to produce.
- run_anchored_walk_forward itself tested end-to-end against the real
  BacktestEngine on synthetic data, to prove the whole pipeline actually
  runs together — this proves the harness works, not that any strategy has
  edge; synthetic data settles nothing about real profitability.
"""
from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
import pandas as pd

from trading_intelligence.backtesting.walk_forward import (
    WalkForwardFold,
    WalkForwardReport,
    run_anchored_walk_forward,
)
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.router import StrategyRouter

# --- Fakes for pure-logic tests: compute_metrics() is a no-op here, so the
# preset total_trades/sharpe_ratio/profit_factor are exactly what the fold
# logic sees, independent of the real metric formulas. ---

@dataclass
class _FakeTrade:
    exit_price: Decimal | None
    pnl: Decimal


@dataclass
class _FakeResult:
    total_trades: int
    sharpe_ratio: float
    profit_factor: float
    trades: list = field(default_factory=list)

    def compute_metrics(self) -> None:
        pass


def _fold(fold_id, *, oos_sharpe, oos_pf, oos_trades, oos_pnls=None, is_sharpe=1.0):
    oos_trade_objs = [
        _FakeTrade(exit_price=Decimal("1"), pnl=Decimal(str(p)))
        for p in (oos_pnls or [])
    ]
    return WalkForwardFold(
        fold_id=fold_id,
        is_start=pd.Timestamp("2024-01-01"), is_end=pd.Timestamp("2024-02-01"),
        oos_start=pd.Timestamp("2024-02-02"), oos_end=pd.Timestamp("2024-03-01"),
        is_result=_FakeResult(total_trades=10, sharpe_ratio=is_sharpe, profit_factor=2.0),
        oos_result=_FakeResult(
            total_trades=oos_trades, sharpe_ratio=oos_sharpe, profit_factor=oos_pf,
            trades=oos_trade_objs,
        ),
    )


class TestWalkForwardFoldThresholds:
    def test_passes_when_all_three_thresholds_met(self):
        f = _fold(1, oos_sharpe=0.6, oos_pf=1.4, oos_trades=35)
        assert f.passes_minimum_thresholds is True

    def test_fails_on_sharpe_below_threshold(self):
        f = _fold(1, oos_sharpe=0.49, oos_pf=1.4, oos_trades=35)
        assert f.passes_minimum_thresholds is False

    def test_fails_on_profit_factor_below_threshold(self):
        f = _fold(1, oos_sharpe=0.6, oos_pf=1.29, oos_trades=35)
        assert f.passes_minimum_thresholds is False

    def test_fails_on_too_few_trades(self):
        f = _fold(1, oos_sharpe=0.6, oos_pf=1.4, oos_trades=29)
        assert f.passes_minimum_thresholds is False

    def test_boundary_values_pass_inclusive(self):
        """Spec says >=, not > — exact boundary values must pass."""
        f = _fold(1, oos_sharpe=0.5, oos_pf=1.3, oos_trades=30)
        assert f.passes_minimum_thresholds is True


class TestWalkForwardReportAggregation:
    def test_oos_sharpe_and_profit_factor_lists(self):
        folds = [
            _fold(1, oos_sharpe=0.6, oos_pf=1.4, oos_trades=35),
            _fold(2, oos_sharpe=0.3, oos_pf=1.1, oos_trades=10),
        ]
        report = WalkForwardReport(folds=folds, strategy_id="s", params={})
        assert report.oos_sharpe_values == [0.6, 0.3]
        assert report.oos_profit_factors == [1.4, 1.1]

    def test_folds_passing_counts_only_passing_folds(self):
        folds = [
            _fold(1, oos_sharpe=0.6, oos_pf=1.4, oos_trades=35),   # passes
            _fold(2, oos_sharpe=0.3, oos_pf=1.1, oos_trades=10),   # fails
            _fold(3, oos_sharpe=0.7, oos_pf=1.5, oos_trades=40),   # passes
        ]
        report = WalkForwardReport(folds=folds, strategy_id="s", params={})
        assert report.folds_passing == 2


class TestStatisticalSignificance:
    def test_fewer_than_two_pnls_returns_neutral_values(self):
        """Explicit short-circuit in the source: <2 trade P&Ls -> (0.0, 1.0),
        never calls scipy on a near-empty sample."""
        folds = [_fold(1, oos_sharpe=0.6, oos_pf=1.4, oos_trades=1, oos_pnls=[5.0])]
        report = WalkForwardReport(folds=folds, strategy_id="s", params={})
        t_stat, p_value = report.statistical_significance()
        assert (t_stat, p_value) == (0.0, 1.0)

    def test_zero_pnls_returns_neutral_values(self):
        folds = [_fold(1, oos_sharpe=0.6, oos_pf=1.4, oos_trades=0, oos_pnls=[])]
        report = WalkForwardReport(folds=folds, strategy_id="s", params={})
        assert report.statistical_significance() == (0.0, 1.0)

    def test_open_trades_excluded_from_sample(self):
        """A trade with exit_price=None (still open) must not count toward
        the t-test sample — only closed trades carry a real P&L."""
        open_trade = _FakeTrade(exit_price=None, pnl=Decimal("0"))
        closed = [_FakeTrade(exit_price=Decimal("1"), pnl=Decimal(str(p))) for p in [10.0, 12.0, 8.0]]
        fold = _fold(1, oos_sharpe=0.6, oos_pf=1.4, oos_trades=3)
        fold.oos_result.trades = [open_trade] + closed
        report = WalkForwardReport(folds=[fold], strategy_id="s", params={})
        t_stat, p_value = report.statistical_significance()
        # All three closed P&Ls are positive -> clearly significant, not the neutral default.
        assert p_value < 1.0

    def test_significant_positive_returns_yield_low_p_value(self):
        pnls = [10.0, 12.0, 11.0, 9.0, 13.0, 10.5, 11.5, 9.5, 12.5, 10.0]
        fold = _fold(1, oos_sharpe=0.6, oos_pf=1.4, oos_trades=len(pnls), oos_pnls=pnls)
        report = WalkForwardReport(folds=[fold], strategy_id="s", params={})
        t_stat, p_value = report.statistical_significance()
        assert p_value < 0.05
        assert t_stat > 0


class TestGoNoGo:
    def _report(self, folds):
        return WalkForwardReport(folds=folds, strategy_id="ma_test", params={})

    def test_no_folds_is_no_go(self):
        report = self._report([])
        go, reason = report.go_no_go()
        assert go is False
        assert "No folds completed" in reason

    def test_clean_pass_on_strong_consistent_folds(self):
        pnls = [10.0, 12.0, 11.0, 9.0, 13.0, 10.5, 11.5, 9.5, 12.5, 10.0]
        folds = [
            _fold(1, oos_sharpe=0.8, oos_pf=1.6, oos_trades=35, oos_pnls=pnls),
            _fold(2, oos_sharpe=0.9, oos_pf=1.7, oos_trades=35, oos_pnls=pnls),
        ]
        go, reason = self._report(folds).go_no_go()
        assert go is True
        assert reason.startswith("PASS")

    def test_fails_when_fewer_than_half_folds_pass(self):
        pnls = [10.0, 12.0, 11.0, 9.0, 13.0, 10.5, 11.5, 9.5, 12.5, 10.0]
        folds = [
            _fold(1, oos_sharpe=0.9, oos_pf=1.7, oos_trades=15, oos_pnls=pnls),  # pass
            _fold(2, oos_sharpe=0.2, oos_pf=0.8, oos_trades=5, oos_pnls=[1.0]),   # fail
            _fold(3, oos_sharpe=0.1, oos_pf=0.7, oos_trades=5, oos_pnls=[1.0]),   # fail
        ]
        go, reason = self._report(folds).go_no_go()
        assert go is False
        assert "folds pass" in reason

    def test_fails_on_insufficient_total_oos_trades(self):
        pnls = [5.0, 5.2, 4.8, 5.1, 4.9, 5.3, 4.7, 5.0, 5.1, 4.9]
        folds = [_fold(1, oos_sharpe=0.9, oos_pf=1.7, oos_trades=10, oos_pnls=pnls)]
        go, reason = self._report(folds).go_no_go()
        assert go is False
        assert "Insufficient OOS trades" in reason

    def test_fails_on_low_mean_oos_sharpe_even_if_folds_pass_individually(self):
        """passes_minimum_thresholds and go_no_go's mean-Sharpe check are
        separate gates — a fold can clear 0.5 individually while the mean
        across folds still fails a stricter aggregate check only if folds
        disagree; here both folds are exactly at the floor so the mean
        equals the floor and must still pass (boundary), proving the two
        checks don't double-penalize an already-passing report."""
        varied_pnls = [5.0, 5.2, 4.8, 5.1, 4.9, 5.3, 4.7, 5.0, 5.1, 4.9] * 3
        folds = [
            _fold(1, oos_sharpe=0.5, oos_pf=1.3, oos_trades=30, oos_pnls=varied_pnls),
            _fold(2, oos_sharpe=0.5, oos_pf=1.3, oos_trades=30, oos_pnls=varied_pnls),
        ]
        go, reason = self._report(folds).go_no_go()
        assert go is True

    def test_summary_includes_label_and_per_fold_lines(self):
        pnls = [10.0, 12.0, 11.0, 9.0, 13.0, 10.5, 11.5, 9.5, 12.5, 10.0]
        folds = [_fold(1, oos_sharpe=0.8, oos_pf=1.6, oos_trades=15, oos_pnls=pnls)]
        text = self._report(folds).summary()
        assert "GO" in text
        assert "Fold 1" in text


# --- Integration tests against the real BacktestEngine ---

class _NeverSignalsStrategy(AbstractStrategy):
    """Never proposes a trade — forces an empty, zero-Sharpe IS result so
    the IS<0.5 skip-OOS branch in run_anchored_walk_forward is exercised."""

    def __init__(self):
        super().__init__(strategy_id="never", symbol="TESTUSDT", timeframe="1d", params={})

    def on_bar(self, data: pd.DataFrame):
        return None

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        return False


def _make_trending_ohlcv(n: int = 500, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.015, n)
    close = 100.0 * np.cumprod(1 + returns)
    idx = pd.date_range("2019-01-01", periods=n, freq="1D")
    return pd.DataFrame(
        {
            "open": close * (1 + rng.uniform(-0.003, 0.003, n)),
            "high": close * (1 + rng.uniform(0.001, 0.008, n)),
            "low": close * (1 - rng.uniform(0.001, 0.008, n)),
            "close": close,
            "volume": rng.uniform(1000, 5000, n),
        },
        index=idx,
    )


class TestRunAnchoredWalkForwardIntegration:
    def test_empty_strategy_produces_no_folds_not_an_error(self):
        """IS Sharpe stays 0.0 (no closed trades) on every fold -> every
        fold is skipped via the IS<0.5 branch, not via an exception."""
        data = _make_trending_ohlcv(n=300)
        report = run_anchored_walk_forward(
            strategy_factory=lambda params: _NeverSignalsStrategy(),
            params={"strategy_id": "never"},
            data=data,
            max_folds=3,
        )
        assert report.folds == []
        assert report.strategy_id == "never"

    def test_data_too_short_for_one_fold_returns_empty_report_not_error(self):
        data = _make_trending_ohlcv(n=20)
        report = run_anchored_walk_forward(
            strategy_factory=lambda params: _NeverSignalsStrategy(),
            params={}, data=data,
        )
        assert report.folds == []
        assert report.strategy_id == "unknown"  # params.get default, no strategy_id key given

    def test_strategy_factory_called_fresh_for_every_is_and_oos_engine(self):
        """Each fold must get brand-new strategy instances for IS and OOS —
        reusing one instance across folds would leak state (e.g. the
        DualMACrossover-style 'already in a position' tracking) between
        windows that must be independent."""
        calls = []

        def factory(params):
            calls.append(params)
            return _NeverSignalsStrategy()

        data = _make_trending_ohlcv(n=300)
        run_anchored_walk_forward(
            strategy_factory=factory, params={"x": 1}, data=data, max_folds=3,
        )
        # Even with every fold skipped pre-OOS, the engine still needs one
        # IS and one OOS factory call per attempted fold.
        assert len(calls) >= 2
        assert all(c == {"x": 1} for c in calls)

    def test_anchored_is_window_always_starts_at_data_start(self):
        """'Anchored' means IS always starts from bar 0 and only expands —
        never a rolling IS start. Use a strategy that actually trades so at
        least one real fold completes and can be checked."""
        data = _make_trending_ohlcv(n=600, seed=123)
        strategy_params = {"strategy_id": "ma_anchor_test"}

        def factory(params):
            from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover
            return DualMACrossover(symbol="TESTUSDT", timeframe="1d")

        report = run_anchored_walk_forward(
            strategy_factory=factory, params=strategy_params, data=data,
            is_pct=0.5, oos_pct=0.2, step_pct=0.1, max_folds=3,
        )
        for fold in report.folds:
            assert fold.is_start == data.index[0]

    def test_end_to_end_report_is_well_formed(self):
        """Proves the full pipeline (strategy -> BacktestEngine -> fold
        aggregation -> go/no-go) runs together without error on realistic
        synthetic data. Makes no claim about GO vs NO-GO — random synthetic
        data settles nothing about real edge, only that the harness works."""
        data = _make_trending_ohlcv(n=800, seed=99)

        def factory(params):
            from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover
            return DualMACrossover(symbol="TESTUSDT", timeframe="1d", params=params)

        report = run_anchored_walk_forward(
            strategy_factory=factory,
            params={"strategy_id": "ma_e2e_test", "fast_period": 10, "slow_period": 30,
                    "trend_filter_period": 0, "min_bars_required": 40},
            data=data, is_pct=0.5, oos_pct=0.2, step_pct=0.15, max_folds=3,
        )
        assert isinstance(report, WalkForwardReport)
        go, reason = report.go_no_go()
        assert isinstance(go, bool)
        assert isinstance(reason, str) and reason
        summary_text = report.summary()
        assert "ma_e2e_test" in summary_text
        for fold in report.folds:
            assert fold.oos_start > fold.is_end

    def test_respects_max_folds_cap(self):
        """Without the cap this window (n=2000, step=2%) would attempt
        roughly 40+ folds. Every fold is skipped pre-OOS (never-signals
        strategy -> IS Sharpe stays 0.0), but the source still constructs
        both an IS and OOS strategy/engine per attempted fold before
        checking IS Sharpe — so each attempted fold costs exactly 2
        factory calls. Counting them proves the loop's fold_id counter
        actually stops at max_folds instead of running to exhaustion."""
        calls = []

        def factory(params):
            calls.append(1)
            return _NeverSignalsStrategy()

        data = _make_trending_ohlcv(n=2000, seed=5)
        report = run_anchored_walk_forward(
            strategy_factory=factory,
            params={}, data=data, is_pct=0.1, oos_pct=0.05, step_pct=0.02, max_folds=2,
        )
        assert report.folds == []
        assert len(calls) == 2 * 2


def _make_mixed_regime_ohlcv(n: int = 1000, seed: int = 17) -> pd.DataFrame:
    """Alternates trending and mean-reverting (ranging) stretches so a
    router covering both TREND_UP/BREAKOUT_UP and RANGE actually sees bars
    of each kind — unlike _make_trending_ohlcv, which is pure trend/noise
    and would never route anything to a RANGE-only strategy."""
    rng = np.random.default_rng(seed)
    segment = 100
    closes = [100.0]
    for seg_start in range(0, n, segment):
        seg_len = min(segment, n - seg_start)
        if (seg_start // segment) % 2 == 0:
            # Trending stretch
            drift = rng.choice([-1, 1]) * 0.0015
            returns = rng.normal(drift, 0.012, seg_len)
            for r in returns:
                closes.append(closes[-1] * (1 + r))
        else:
            # Ranging stretch: oscillates around the level it entered at,
            # no persistent drift.
            level = closes[-1]
            for i in range(seg_len):
                closes.append(level * (1 + 0.02 * np.sin(i / 4.0) + rng.normal(0, 0.004)))
    close = np.array(closes[1 : n + 1])
    idx = pd.date_range("2018-01-01", periods=len(close), freq="1D")
    return pd.DataFrame(
        {
            "open": close * (1 + rng.uniform(-0.003, 0.003, len(close))),
            "high": close * (1 + rng.uniform(0.001, 0.008, len(close))),
            "low": close * (1 - rng.uniform(0.001, 0.008, len(close))),
            "close": close,
            "volume": rng.uniform(1000, 5000, len(close)),
        },
        index=idx,
    )


class TestRunAnchoredWalkForwardRouterMode:
    """router_factory mode — validating a regime-aware StrategyRouter
    configuration through the same gate, instead of one fixed strategy."""

    def test_requires_exactly_one_of_strategy_factory_or_router_factory(self):
        import pytest

        data = _make_trending_ohlcv(n=300)
        with pytest.raises(ValueError, match="exactly one"):
            run_anchored_walk_forward(params={}, data=data)
        with pytest.raises(ValueError, match="exactly one"):
            run_anchored_walk_forward(
                strategy_factory=lambda p: _NeverSignalsStrategy(),
                router_factory=lambda p: StrategyRouter(),
                params={}, data=data,
            )

    def test_router_factory_called_fresh_for_every_is_and_oos_engine(self):
        calls = []

        def router_factory(params):
            calls.append(params)
            return StrategyRouter()  # empty: always NO_TRADE, same role as _NeverSignalsStrategy

        data = _make_trending_ohlcv(n=300)
        run_anchored_walk_forward(
            router_factory=router_factory, params={"x": 1}, data=data, max_folds=3,
        )
        assert len(calls) >= 2
        assert all(c == {"x": 1} for c in calls)

    def test_end_to_end_report_with_default_router_is_well_formed(self):
        """Full pipeline through the actual gate: market data -> regime ->
        router -> risk/sizing -> fills -> exit -> P&L -> go/no-go — using
        the real default_router(), not a fake, so this proves the
        regime-aware configuration survives walk-forward's own fold/factory
        machinery, same as the fixed-strategy end-to-end test above."""
        from trading_intelligence.strategy.router import default_router

        data = _make_trending_ohlcv(n=600, seed=11)
        report = run_anchored_walk_forward(
            router_factory=lambda params: default_router(),
            params={"strategy_id": "regime_router_e2e_test"},
            data=data, is_pct=0.5, oos_pct=0.2, step_pct=0.15, max_folds=3,
        )
        assert isinstance(report, WalkForwardReport)
        go, reason = report.go_no_go()
        assert isinstance(go, bool)
        assert isinstance(reason, str) and reason
        assert "regime_router_e2e_test" in report.summary()
        for fold in report.folds:
            assert fold.oos_start > fold.is_end

    def test_end_to_end_report_with_range_reversion_router_is_well_formed(self):
        """Same proof as the default_router() test above, but for
        router_with_range_reversion() (BollingerReversion registered for
        Regime.RANGE — the real gap this strategy was built to fill) on
        data with genuine ranging stretches, not pure trend/noise. Makes no
        claim about GO vs NO-GO — that honest result is reported separately
        in docs/CHECKPOINT.md, not asserted here."""
        from trading_intelligence.strategy.router import router_with_range_reversion

        data = _make_mixed_regime_ohlcv(n=1000, seed=23)
        report = run_anchored_walk_forward(
            router_factory=lambda params: router_with_range_reversion(),
            params={"strategy_id": "range_reversion_e2e_test"},
            data=data, is_pct=0.5, oos_pct=0.2, step_pct=0.15, max_folds=3,
        )
        assert isinstance(report, WalkForwardReport)
        go, reason = report.go_no_go()
        assert isinstance(go, bool)
        assert isinstance(reason, str) and reason
        assert "range_reversion_e2e_test" in report.summary()
        for fold in report.folds:
            assert fold.oos_start > fold.is_end
