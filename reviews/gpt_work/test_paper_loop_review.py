"""Offline cross-review of the cloud PaperLoop against a pinned source checkout.

Run: python -B test_paper_loop_review.py <research-source-directory>
Synthetic OHLCV and clock only; no exchange calls, credentials, or live orders.
"""
from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(sys.argv.pop(1)).resolve()))
sys.dont_write_bytecode = True
import pandas as pd  # noqa: E402
from trading_intelligence.execution.paper import PaperAdapter  # noqa: E402
from trading_intelligence.execution.paper_loop import PaperLoop  # noqa: E402
from trading_intelligence.execution.paper_runner import PaperTradingRunner  # noqa: E402
from trading_intelligence.persistence.audit_log import AuditLog  # noqa: E402
from trading_intelligence.regime.detector import Regime  # noqa: E402
from trading_intelligence.risk.engine import RiskEngine  # noqa: E402
from trading_intelligence.risk.models import RiskConfig  # noqa: E402
from trading_intelligence.strategy.base import AbstractStrategy  # noqa: E402
from trading_intelligence.strategy.models import TradeProposal  # noqa: E402
from trading_intelligence.strategy.router import StrategyRouter  # noqa: E402


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = "BTCUSDT"


class DataOnly:
    def get_current_price(self, symbol: str) -> Decimal:
        return Decimal("100")

    def submit_order(self, order) -> None:
        raise AssertionError("No exchange order permitted")


class NoSignal(AbstractStrategy):
    def __init__(self) -> None:
        super().__init__("no-signal-review", SYMBOL, "1h", {})

    def on_bar(self, data):
        return None

    def on_exit_signal(self, data, entry_price):
        return False


class OneSignal(NoSignal):
    def on_bar(self, data):
        if len(data) != 61:
            return None
        return TradeProposal(
            strategy_id=self.strategy_id, symbol=SYMBOL, side="BUY",
            entry_type="MARKET", stop_price=Decimal("95"), timeframe="1h",
            rationale="synthetic crash-window review", signal_strength=1.0,
            timestamp=data.index[-1].isoformat(),
        )


class FrozenFeed:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.now = START

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        assert symbol == SYMBOL and timeframe == "1h"
        return self.frame[self.frame.index <= pd.Timestamp(self.now.replace(tzinfo=None))].iloc[-limit:]


def flat_bars(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
        index=pd.date_range(START.replace(tzinfo=None), periods=n, freq="1h"),
    )


class PaperLoopAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="gpt-paper-loop-review-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        guard = patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK FORBIDDEN"))
        guard.start()
        self.addCleanup(guard.stop)
        self.feed = FrozenFeed(flat_bars(70))
        paper = PaperAdapter(DataOnly(), Decimal("10000"), self.root / "paper.json")
        risk = RiskEngine(RiskConfig(), self.root / "risk.json", AuditLog(self.root / "audit"))
        router = StrategyRouter()
        for regime in Regime:
            router.register(regime, NoSignal())
        runner = PaperTradingRunner(router, risk, paper)
        self.loop = PaperLoop(
            runner, self.feed, [SYMBOL], "1h", self.root / "loop.json",
            clock=lambda: self.feed.now,
        )

    def initial_tick(self) -> None:
        self.feed.now = START + timedelta(hours=61)
        report = self.loop.tick()
        self.assertEqual(report.processed, [(START + timedelta(hours=60)).isoformat()])

    def test_internal_missing_bar_cannot_be_silently_skipped(self) -> None:
        self.initial_tick()
        # bar61 is present, bar62 is missing, bar63 is present and closed.
        missing = pd.Timestamp((START + timedelta(hours=62)).replace(tzinfo=None))
        self.feed.frame = self.feed.frame.drop(missing)
        self.feed.now = START + timedelta(hours=64)
        report = self.loop.tick()
        self.assertIsNotNone(
            report.gap_halt,
            f"internal missing bar was skipped without a halt: processed={report.processed}",
        )
        self.assertTrue(self.loop.runner.risk_engine.state.kill_switch)

    def test_contiguous_catch_up_control_processes_every_closed_bar(self) -> None:
        self.initial_tick()
        self.feed.now = START + timedelta(hours=64)
        report = self.loop.tick()
        self.assertEqual(
            report.processed,
            [(START + timedelta(hours=i)).isoformat() for i in (61, 62, 63)],
        )
        self.assertIsNone(report.gap_halt)
        self.assertFalse(self.loop.runner.risk_engine.state.kill_switch)

    def test_successful_but_frozen_feed_is_not_treated_as_fresh_market_data(self) -> None:
        self.initial_tick()
        # A successful HTTP/fetch path can still return stale content. Without
        # bar freshness, protective paper STOPS cannot observe market movement.
        self.feed.frame = self.feed.frame.iloc[:61]
        self.feed.now = START + timedelta(hours=65)
        report = self.loop.tick()
        self.assertEqual(report.processed, [])
        self.assertTrue(
            report.gap_halt or self.loop.runner.risk_engine.state.kill_switch,
            "multiple expected closes elapsed, but a frozen feed was classified healthy",
        )

    def test_restart_after_persisted_buy_before_stop_recovers_protection(self) -> None:
        paper = self.loop.runner.paper
        risk = self.loop.runner.risk_engine
        risk.config = RiskConfig(
            max_position_size_pct=25.0, max_total_exposure_pct=25.0,
            max_correlated_exposure_pct=25.0, max_daily_turnover_pct=30.0,
        )
        router = StrategyRouter()
        for regime in Regime:
            router.register(regime, OneSignal())
        self.loop.runner = PaperTradingRunner(router, risk, paper)
        self.feed.now = START + timedelta(hours=61)
        first = self.loop.tick()
        self.assertTrue(any("ENTRY_SUBMITTED" in a for a in first.actions))

        original_on_bar = paper.on_new_bar

        def crash_after_adapter_persists_fill(*args, **kwargs):
            result = original_on_bar(*args, **kwargs)
            if any(r.side == "BUY" and r.status == "FILLED" for r in result):
                raise SystemExit("synthetic power loss before protective STOP")
            return result

        self.feed.now = START + timedelta(hours=62)
        with patch.object(paper, "on_new_bar", side_effect=crash_after_adapter_persists_fill):
            with self.assertRaises(SystemExit):
                self.loop.tick()

        restored_paper = PaperAdapter(DataOnly(), Decimal("10000"), self.root / "paper.json")
        restored_risk = RiskEngine(risk.config, self.root / "risk.json", AuditLog(self.root / "audit"))
        try:
            restored = PaperTradingRunner(router, restored_risk, restored_paper)
        except RuntimeError as exc:
            # Explicitly refusing to resume a naked position is an acceptable
            # alternative to reconstructing the approved STOP automatically.
            self.assertIn("unprotected", str(exc).lower())
            return
        position = restored_paper.get_position(SYMBOL)
        self.assertIsNotNone(position, "fixture must persist the completed BUY")
        self.assertIsNotNone(
            restored._stop_order_for(SYMBOL),
            "a persisted BUY survived restart without its approved protective STOP",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
