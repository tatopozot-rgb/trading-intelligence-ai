"""Tests for trading_intelligence.learning.regime_performance."""
from decimal import Decimal

import numpy as np
import pandas as pd

from trading_intelligence.backtesting.backtest_engine import BacktestTrade
from trading_intelligence.learning.regime_performance import (
    MIN_TRADES_FOR_A_RECOMMENDATION,
    TaggedTrade,
    recommend_confidence_adjustments,
    summarize_by_regime,
    tag_trades_with_regime,
)
from trading_intelligence.regime.detector import Regime, RegimeSnapshot, Volatility


def _ohlcv(close: np.ndarray) -> pd.DataFrame:
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq="1D")
    return pd.DataFrame(
        {"open": close, "high": close + 0.3, "low": close - 0.3, "close": close,
         "volume": np.full(n, 1000.0)},
        index=idx,
    )


def _trade(entry_bar: int, pnl: float, *, closed: bool = True) -> BacktestTrade:
    t = BacktestTrade(
        symbol="BTCUSDT", strategy_id="s", entry_bar=entry_bar,
        entry_time=pd.Timestamp("2024-01-01"), entry_price=Decimal("100"),
        quantity=Decimal("1"), stop_price=Decimal("90"), target_price=None,
    )
    if closed:
        t.exit_bar = entry_bar + 1
        t.exit_price = Decimal("100") + Decimal(str(pnl))
        t.exit_reason = "signal"
    return t


def _snap(regime: Regime, confidence: float = 0.9) -> RegimeSnapshot:
    return RegimeSnapshot(regime=regime, volatility=Volatility.NORMAL, confidence=confidence, metrics={})


class TestTagTradesWithRegime:
    def test_tags_each_trade_using_only_data_up_to_its_entry_bar(self):
        rng = np.random.default_rng(1)
        close = 100 + np.arange(150) * 0.5 + rng.normal(0, 0.2, 150)
        data = _ohlcv(close)
        trade = _trade(entry_bar=140, pnl=5.0)
        tagged = tag_trades_with_regime([trade], data)
        assert len(tagged) == 1
        assert tagged[0].trade is trade
        assert tagged[0].regime_at_entry.regime in (Regime.TREND_UP, Regime.BREAKOUT_UP)

    def test_does_not_see_data_after_the_entry_bar(self):
        """A trend that reverses hard right after entry must not leak into the
        regime classification at entry — slicing must stop at entry_bar."""
        rng = np.random.default_rng(2)
        up = 100 + np.arange(100) * 0.5 + rng.normal(0, 0.2, 100)
        down = up[-1] - np.arange(50) * 2.0  # sharp reversal, well after entry
        close = np.concatenate([up, down])
        data = _ohlcv(close)
        trade = _trade(entry_bar=99, pnl=1.0)  # entry right before the reversal
        tagged = tag_trades_with_regime([trade], data)
        # If future data leaked in, this would likely read as a downtrend/breakdown.
        assert tagged[0].regime_at_entry.regime in (Regime.TREND_UP, Regime.BREAKOUT_UP)


class TestSummarizeByRegime:
    def test_aggregates_win_rate_and_pnl_per_regime(self):
        tagged = [
            TaggedTrade(trade=_trade(0, 10.0), regime_at_entry=_snap(Regime.TREND_UP)),
            TaggedTrade(trade=_trade(1, -5.0), regime_at_entry=_snap(Regime.TREND_UP)),
            TaggedTrade(trade=_trade(2, 3.0), regime_at_entry=_snap(Regime.RANGE)),
        ]
        summary = summarize_by_regime(tagged)
        assert summary[Regime.TREND_UP].trade_count == 2
        assert summary[Regime.TREND_UP].win_rate == 0.5
        assert summary[Regime.TREND_UP].total_pnl == 5.0
        assert summary[Regime.RANGE].trade_count == 1
        assert summary[Regime.RANGE].win_rate == 1.0

    def test_open_trades_do_not_dilute_win_rate_or_averages(self):
        tagged = [
            TaggedTrade(trade=_trade(0, 10.0), regime_at_entry=_snap(Regime.TREND_UP)),
            TaggedTrade(trade=_trade(1, 0.0, closed=False), regime_at_entry=_snap(Regime.TREND_UP)),
        ]
        summary = summarize_by_regime(tagged)
        perf = summary[Regime.TREND_UP]
        assert perf.trade_count == 2          # counts the open trade too
        assert perf.closed_trade_count == 1   # but only 1 closed
        assert perf.win_rate == 1.0            # not diluted to 0.5 by the open trade
        assert perf.avg_pnl == 10.0

    def test_empty_input_returns_empty_summary(self):
        assert summarize_by_regime([]) == {}


class TestRecommendConfidenceAdjustments:
    def test_too_few_trades_yields_no_strong_claim(self):
        tagged = [
            TaggedTrade(trade=_trade(i, -1.0), regime_at_entry=_snap(Regime.TREND_UP))
            for i in range(MIN_TRADES_FOR_A_RECOMMENDATION - 1)
        ]
        summary = summarize_by_regime(tagged)
        notes = recommend_confidence_adjustments(summary)
        assert any("too few" in n for n in notes)
        assert not any("underperforming" in n for n in notes)

    def test_poor_performance_with_enough_trades_is_flagged(self):
        tagged = [
            TaggedTrade(trade=_trade(i, -5.0), regime_at_entry=_snap(Regime.TREND_UP))
            for i in range(MIN_TRADES_FOR_A_RECOMMENDATION)
        ]
        summary = summarize_by_regime(tagged)
        notes = recommend_confidence_adjustments(summary)
        assert any("underperforming" in n for n in notes)

    def test_good_performance_raises_no_concern(self):
        tagged = [
            TaggedTrade(trade=_trade(i, 5.0), regime_at_entry=_snap(Regime.TREND_UP))
            for i in range(MIN_TRADES_FOR_A_RECOMMENDATION)
        ]
        summary = summarize_by_regime(tagged)
        notes = recommend_confidence_adjustments(summary)
        assert any("no concern raised" in n for n in notes)
        assert not any("underperforming" in n for n in notes)
