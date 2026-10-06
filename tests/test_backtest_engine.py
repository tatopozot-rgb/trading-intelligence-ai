"""Smoke test for BacktestEngine — confirms the engine runs end-to-end."""
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting.backtest_engine import BacktestEngine
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal
from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover


class _FixedSignalStrategy(AbstractStrategy):
    """Test double: fires exactly one BUY signal at a chosen bar index, with a
    fixed stop price, and never emits an exit signal — isolates stop-fill
    behavior from any real indicator logic."""

    def __init__(self, signal_at_index: int, stop_price: Decimal):
        super().__init__(strategy_id="fixed_signal", symbol="TESTUSDT", timeframe="1d", params={})
        self.signal_at_index = signal_at_index
        self.stop_price = stop_price
        self._fired = False

    def on_bar(self, data: pd.DataFrame) -> Optional[TradeProposal]:
        if not self._fired and len(data) - 1 == self.signal_at_index:
            self._fired = True
            return TradeProposal(
                strategy_id=self.strategy_id, symbol=self.symbol, side="BUY",
                entry_type="MARKET", stop_price=self.stop_price, timeframe=self.timeframe,
                rationale="test", signal_strength=1.0, timestamp=str(data.index[-1]),
            )
        return None

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        return False


def _flat_ohlcv(opens, highs, lows, closes) -> pd.DataFrame:
    n = len(opens)
    idx = pd.date_range("2024-01-01", periods=n, freq="1D")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0] * n},
        index=idx,
    )


def _make_trending_ohlcv(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Synthetic trending price series for integration testing."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.015, n)  # slight upward drift
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


class TestBacktestEngineSmoke:
    def test_runs_without_error(self):
        data = _make_trending_ohlcv()
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        result.compute_metrics()
        assert isinstance(result.total_trades, int)
        assert result.total_trades >= 0

    def test_equity_curve_non_empty(self):
        data = _make_trending_ohlcv()
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        assert len(result.equity_curve) > 0

    def test_all_trades_have_exit(self):
        """Every trade in a completed backtest should have an exit."""
        data = _make_trending_ohlcv(n=300)
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 10, "slow_period": 30, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        for trade in result.trades:
            assert trade.exit_price is not None, f"Trade {trade.entry_time} has no exit"

    def test_fees_are_positive(self):
        data = _make_trending_ohlcv()
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        for trade in result.trades:
            if trade.exit_price is not None:
                assert trade.entry_fee >= 0
                assert trade.exit_fee >= 0

    def test_metrics_summary_string(self):
        data = _make_trending_ohlcv()
        strategy = DualMACrossover(
            "BTCUSDT", "1d",
            params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0},
        )
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)
        result.compute_metrics()
        s = result.summary()
        assert "Sharpe" in s
        assert "PF" in s


class TestEquityAccounting:
    """
    Real bug found by numeric verification before touching anything:
    entry_fee used to be deducted from equity immediately at entry, AND
    again inside BacktestTrade.pnl (added to equity once, at close) —
    double-charging it on every single trade. The existing smoke tests
    only checked `fees are positive` / `trades have an exit`, nothing
    exact enough to catch a bug of this shape.
    """

    def test_final_equity_matches_a_plain_ledger_not_double_charged_fee(self):
        """entry_fee must be subtracted from equity exactly once across
        the whole round trip, not once immediately and again via pnl."""
        data = _flat_ohlcv(
            opens=[100, 100, 100, 100, 100, 100],
            highs=[101, 101, 101, 101, 101, 111],
            lows=[99, 99, 99, 99, 99, 99],
            closes=[100, 100, 100, 100, 100, 110],
        )
        # stop_price=1 never triggers; the trade is forced closed at the
        # last bar's close (110) via "end_of_data" when data runs out.
        strategy = _FixedSignalStrategy(signal_at_index=3, stop_price=Decimal("1"))
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.exit_reason == "end_of_data"

        entry_fill = Decimal("100") * (Decimal("1") + Decimal("0.0005"))
        qty = engine._size_position(Decimal("10000"), entry_fill, Decimal("1"))
        entry_fee = entry_fill * qty * Decimal("0.001")
        exit_fill = Decimal("110")  # end_of_data uses the bar's close directly, no slippage
        exit_fee = exit_fill * qty * Decimal("0.001")
        gross = (exit_fill - entry_fill) * qty
        expected_final_equity = Decimal("10000") + gross - entry_fee - exit_fee

        assert trade.quantity == qty
        assert trade.entry_fee == entry_fee
        assert result.final_equity == expected_final_equity

    def test_losing_trade_equity_also_matches_ledger(self):
        """Same reconciliation on a losing trade, where the old bug's
        extra fee deduction would otherwise be masked by (or confused
        with) the trade's own loss."""
        data = _flat_ohlcv(
            opens=[100, 100, 100, 100, 100, 100],
            highs=[101, 101, 101, 101, 101, 101],
            lows=[99, 99, 99, 99, 99, 89],
            closes=[100, 100, 100, 100, 100, 90],
        )
        strategy = _FixedSignalStrategy(signal_at_index=3, stop_price=Decimal("1"))
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)

        trade = result.trades[0]
        assert trade.exit_reason == "end_of_data"

        entry_fill = Decimal("100") * (Decimal("1") + Decimal("0.0005"))
        qty = engine._size_position(Decimal("10000"), entry_fill, Decimal("1"))
        entry_fee = entry_fill * qty * Decimal("0.001")
        exit_fill = Decimal("90")
        exit_fee = exit_fill * qty * Decimal("0.001")
        gross = (exit_fill - entry_fill) * qty
        expected_final_equity = Decimal("10000") + gross - entry_fee - exit_fee

        assert result.final_equity == expected_final_equity


class TestStopFillEdgeCases:
    """
    Deterministic, exact-price tests for the gap-through stop model, per
    docs/PAPER_TRADING_SIMULATION_SPEC.md. These are not smoke tests — they
    assert the exact expected fill price for each scenario using a fixed
    (non-random) signal, isolated from any real strategy's indicator logic.
    """

    def test_stop_hit_on_the_entry_bar_itself(self):
        """
        Signal fires at bar 3 -> entry fills at bar 4's open (100). Bar 4's
        own low (90) also pierces the stop (95) — the very same bar is both
        the entry bar and the stop-exit bar. Bar 4's open (100) is still
        above the stop, so this is a normal touch, not a gap: fill = stop *
        (1 - 2x slippage), not the gap-through formula.
        """
        data = _flat_ohlcv(
            opens=[100, 100, 100, 100, 100],
            highs=[101, 101, 101, 101, 101],
            lows=[99, 99, 99, 99, 90],
            closes=[100, 100, 100, 100, 100],
        )
        strategy = _FixedSignalStrategy(signal_at_index=3, stop_price=Decimal("95"))
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.exit_reason == "stop"
        assert trade.entry_bar == 4
        assert trade.exit_bar == 4  # stop hit on the same bar entry filled
        expected_fill = Decimal("95") * (Decimal("1") - 2 * Decimal("0.0005"))
        assert trade.exit_price == expected_fill

    def test_gap_down_through_stop_fills_at_bar_open_not_at_stop(self):
        """
        Entry fills normally at bar 4's open (100, no gap). Bar 5 then gaps
        down: its open (70) is already below the stop (95) — a real crash,
        not a gradual touch. The engine must fill at bar 5's open (with 1x
        slippage), not at stop_price*(1-2x slippage)=~94.9 — using the flat
        formula here would understate the loss by ~25 points on this trade,
        which is exactly the kind of backtest optimism this project must
        not produce (see docs/PAPER_TRADING_SIMULATION_SPEC.md: "Core
        Principle: Pessimistic Assumptions").
        """
        data = _flat_ohlcv(
            opens=[100, 100, 100, 100, 100, 70],
            highs=[101, 101, 101, 101, 102, 71],
            lows=[99, 99, 99, 99, 98, 65],
            closes=[100, 100, 100, 100, 100, 68],
        )
        strategy = _FixedSignalStrategy(signal_at_index=3, stop_price=Decimal("95"))
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(data)

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.exit_reason == "stop"
        assert trade.entry_bar == 4
        assert trade.exit_bar == 5
        expected_fill = Decimal("70") * (Decimal("1") - Decimal("0.0005"))
        assert trade.exit_price == expected_fill
        # Sanity: the gap-through fill must be well below the naive
        # stop*(1-2x slippage) estimate — that's the whole point of the fix.
        naive_estimate = Decimal("95") * (Decimal("1") - 2 * Decimal("0.0005"))
        assert trade.exit_price < naive_estimate - Decimal("20")
