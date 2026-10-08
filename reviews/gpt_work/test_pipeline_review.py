"""Independent integration acceptance: no data downloads, accounts or trading runner.

Run: python test_pipeline_review.py <pinned-research-checkout-directory>
Uses synthetic, deliberately simple prices so discrepancies have exact causes.
"""
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(SOURCE))
import pandas as pd
from trading_intelligence.backtesting.backtest_engine import BacktestEngine
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal
from trading_intelligence.strategy.router import StrategyRouter
from trading_intelligence.regime.detector import Regime, RegimeSnapshot, Volatility
from trading_intelligence.learning.regime_performance import tag_trades_with_regime


class OneSignal(AbstractStrategy):
    def __init__(self, stop='90'):
        super().__init__('review-fixture', 'BTCUSDT', '1d', {})
        self.stop = Decimal(stop)

    def on_bar(self, data):
        if len(data) != 2:
            return None
        return TradeProposal(strategy_id=self.strategy_id, symbol=self.symbol,
                             side='BUY', entry_type='MARKET', stop_price=self.stop,
                             timeframe='1d', rationale='isolated test fixture',
                             signal_strength=1.0, timestamp=data.index[-1].isoformat())

    def on_exit_signal(self, data, entry_price):
        return False


def bars():
    return pd.DataFrame({'open': [100.0]*5, 'high': [101.0]*4+[111.0],
                         'low': [99.0]*5, 'close': [100.0]*4+[110.0],
                         'volume': [1000.0]*5},
                        index=pd.date_range('2026-01-01', periods=5, freq='D', tz='UTC'))


class PipelineAcceptance(unittest.TestCase):
    def run_fixture(self, **kwargs):
        return BacktestEngine(OneSignal(), initial_equity=Decimal('1000'),
                              slippage_factor=Decimal('0'), **kwargs).run(bars())

    def test_configured_fee_is_used_on_both_sides(self):
        result = self.run_fixture(taker_fee=Decimal('0.0005'))
        trade = result.trades[0]
        self.assertEqual(trade.entry_fee, trade.entry_price*trade.quantity*Decimal('0.0005'))
        self.assertEqual(trade.exit_fee, trade.exit_price*trade.quantity*Decimal('0.0005'))

    def test_final_equity_curve_matches_final_settlement(self):
        result = self.run_fixture()
        self.assertAlmostEqual(float(result.equity_curve.iloc[-1]), float(result.final_equity), places=8)

    def test_learning_uses_decision_bar_not_fill_bar_future_close(self):
        data = bars()
        result = self.run_fixture()
        trade = result.trades[0]
        self.assertEqual(trade.entry_bar, 2)  # signal at index1, next-open fill at2
        seen = []
        def record(window, **kwargs):
            seen.append(window.index[-1])
            return RegimeSnapshot(Regime.TREND_UP, Volatility.NORMAL, 0.8, {})
        with patch('trading_intelligence.learning.regime_performance.detect_regime', side_effect=record):
            tag_trades_with_regime(result.trades, data)
        self.assertEqual(seen, [data.index[trade.entry_bar-1]])

    def test_spot_position_cost_cannot_exceed_available_equity(self):
        engine = BacktestEngine(OneSignal('99.99'), initial_equity=Decimal('1000'),
                                slippage_factor=Decimal('0'))
        trade = engine.run(bars()).trades[0]
        self.assertLessEqual(trade.entry_price*trade.quantity + trade.entry_fee, Decimal('1000'))

    def test_nonfinite_confidence_does_not_route_a_strategy(self):
        router = StrategyRouter()
        router.register(Regime.TREND_UP, OneSignal(), min_confidence=0.5)
        for bad in (float('nan'), float('inf')):
            with self.subTest(confidence=bad):
                snapshot = RegimeSnapshot(Regime.TREND_UP, Volatility.NORMAL, bad, {})
                try:
                    decision = router.route(snapshot)
                except ValueError:
                    continue  # explicit invalid-input rejection is fail-closed too
                self.assertTrue(decision.is_no_trade)

    def test_unregistered_regime_remains_no_trade(self):
        router = StrategyRouter()
        router.register(Regime.TREND_UP, OneSignal(), min_confidence=0.5)
        self.assertTrue(router.route(RegimeSnapshot(Regime.NO_EDGE, Volatility.UNKNOWN, 0, {})).is_no_trade)


if __name__ == '__main__':
    print('REVIEW SOURCE:', SOURCE)
    unittest.main(verbosity=2)
