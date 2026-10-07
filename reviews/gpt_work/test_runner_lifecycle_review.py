"""Offline lifecycle acceptance for the existing research runner/adapter.

Run: python -B test_runner_lifecycle_review.py <research-source-directory>
Synthetic scripted signals only; fixture caps are not project policy.
No network, account, credentials, runtime changes or strategy optimization.
"""
from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(sys.argv.pop(1)).resolve()))
sys.dont_write_bytecode = True
import pandas as pd  # noqa: E402
from trading_intelligence.execution.order_models import OrderRequest  # noqa: E402
from trading_intelligence.execution.paper import PaperAdapter  # noqa: E402
from trading_intelligence.execution.paper_runner import PaperTradingRunner  # noqa: E402
from trading_intelligence.persistence.audit_log import AuditLog  # noqa: E402
from trading_intelligence.regime.detector import Regime  # noqa: E402
from trading_intelligence.risk.engine import RiskEngine  # noqa: E402
from trading_intelligence.risk.models import RiskConfig  # noqa: E402
from trading_intelligence.strategy.base import AbstractStrategy  # noqa: E402
from trading_intelligence.strategy.models import TradeProposal  # noqa: E402
from trading_intelligence.strategy.router import StrategyRouter  # noqa: E402


class DataOnly:
    def get_current_price(self, symbol: str) -> Decimal:
        return Decimal("100")

    def submit_order(self, order: OrderRequest) -> None:
        raise AssertionError("No exchange order allowed")


class OneSignal(AbstractStrategy):
    def __init__(self) -> None:
        super().__init__("lifecycle-fixture", "BTCUSDT", "1d", {})

    def on_bar(self, data: pd.DataFrame) -> TradeProposal | None:
        if len(data) != 61:
            return None
        return TradeProposal(
            strategy_id=self.strategy_id, symbol=self.symbol, side="BUY",
            entry_type="MARKET", stop_price=Decimal("95"), timeframe="1d",
            rationale="synthetic lifecycle test", signal_strength=1.0,
            timestamp=data.index[-1].isoformat(),
        )

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        return False


def bars(count: int, final_low: float = 99.0, final_close: float = 100.0) -> pd.DataFrame:
    frame = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
        index=pd.date_range("2026-01-01", periods=count, freq="1D", tz="UTC"),
    )
    frame.iloc[-1, frame.columns.get_loc("low")] = final_low
    frame.iloc[-1, frame.columns.get_loc("close")] = final_close
    return frame


class RunnerLifecycleAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="gpt-runner-review-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        guard = patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK FORBIDDEN"))
        guard.start()
        self.addCleanup(guard.stop)
        self.paper = self.new_paper()
        # Deliberately loose fixture-only caps isolate mechanics, not performance.
        config = RiskConfig(max_position_size_pct=100, max_total_exposure_pct=100,
                            max_correlated_exposure_pct=100, max_daily_turnover_pct=1000)
        self.risk = RiskEngine(config, self.root / "risk.json", AuditLog(self.root / "audit"))
        router = StrategyRouter()
        for regime in Regime:
            router.register(regime, OneSignal())
        self.runner = PaperTradingRunner(router, self.risk, self.paper)

    def new_paper(self) -> PaperAdapter:
        return PaperAdapter(DataOnly(), Decimal("10000"), self.root / "paper.json",
                            taker_fee=Decimal("0.001"), slippage_rate=Decimal("0"))

    def submit_signal(self) -> None:
        step = self.runner.process_bar("BTCUSDT", bars(61))
        self.assertEqual(step.action, "ENTRY_SUBMITTED", "fixture must actually submit a risk-approved order")
        self.assertIsNone(self.paper.get_position("BTCUSDT"))

    def test_duplicate_completed_bar_does_not_fill_its_own_signal(self) -> None:
        self.submit_signal()
        before = self.paper.cash
        try:
            self.runner.process_bar("BTCUSDT", bars(61))
        except ValueError:
            pass  # Explicitly rejecting duplicate input is also acceptable.
        self.assertIsNone(self.paper.get_position("BTCUSDT"), "same closed bar filled an order decided after its close")
        self.assertEqual(self.paper.cash, before)

    def test_older_bar_cannot_execute_a_future_signal(self) -> None:
        self.submit_signal()
        before = self.paper.cash
        try:
            self.runner.process_bar("BTCUSDT", bars(60))
        except ValueError:
            pass
        self.assertIsNone(self.paper.get_position("BTCUSDT"), "out-of-order bar executed a future decision")
        self.assertEqual(self.paper.cash, before)

    def test_entry_stop_is_effective_during_the_fill_bar(self) -> None:
        self.submit_signal()
        # Fill at open100, then known low80 crosses the approved stop95.
        # No ambiguous OHLC ordering: open necessarily precedes the intrabar low.
        self.runner.process_bar("BTCUSDT", bars(62, final_low=80, final_close=90))
        self.assertIsNone(self.paper.get_position("BTCUSDT"), "stop was not installed until after the entire fill bar")
        self.assertEqual(len(self.runner.closed_trades), 1)
        self.assertEqual(self.runner.closed_trades[0].exit_reason, "STOP")
        self.assertEqual(self.runner.reconcile(), [])

    def test_pending_order_retry_after_restart_cannot_duplicate(self) -> None:
        order = OrderRequest("BTCUSDT", "BUY", "MARKET", Decimal("1"), client_order_id="pending-retry")
        self.paper.submit_order(order)
        restored = self.new_paper()
        restored.submit_order(order)
        restored.on_new_bar("BTCUSDT", Decimal("100"), Decimal("101"), Decimal("99"),
                            Decimal("100"), "2026-01-02T00:00:00Z")
        self.assertEqual(restored.get_position("BTCUSDT").quantity, Decimal("1"), "restored pending id was accepted twice")

    def test_filled_order_retry_after_restart_cannot_duplicate(self) -> None:
        order = OrderRequest("BTCUSDT", "BUY", "MARKET", Decimal("1"), client_order_id="filled-retry")
        self.paper.submit_order(order)
        self.paper.on_new_bar("BTCUSDT", Decimal("100"), Decimal("101"), Decimal("99"),
                              Decimal("100"), "2026-01-02T00:00:00Z")
        restored = self.new_paper()
        restored.submit_order(order)
        restored.on_new_bar("BTCUSDT", Decimal("100"), Decimal("101"), Decimal("99"),
                            Decimal("100"), "2026-01-03T00:00:00Z")
        self.assertEqual(restored.get_position("BTCUSDT").quantity, Decimal("1"), "filled id history disappeared on restart")

    def test_ordinary_next_bar_fill_and_later_stop_preserve_cash_identity(self) -> None:
        self.submit_signal()
        self.runner.process_bar("BTCUSDT", bars(62))
        self.assertIsNotNone(self.paper.get_position("BTCUSDT"))
        self.assertEqual(self.runner.reconcile(), [])
        self.runner.process_bar("BTCUSDT", bars(63, final_low=80, final_close=90))
        self.assertIsNone(self.paper.get_position("BTCUSDT"))
        self.assertEqual(len(self.runner.closed_trades), 1)
        self.assertEqual(self.runner.reconcile(), [])
        self.assertEqual(self.paper.cash, Decimal("10000") + self.runner.closed_trades[0].pnl)


if __name__ == "__main__":
    unittest.main(verbosity=2)
