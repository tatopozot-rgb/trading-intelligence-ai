"""Independent failing acceptance checks for PR #8 reservation/fill lifecycle.

Run: python -B test_reservation_review.py <snapshot-directory>
Initially reviewed against a0941e3; rerun against an explicit source snapshot.
Synthetic fixtures only; real RiskEngine/PaperAdapter/PaperTradingRunner.
No production policy change, no duplicate-bar or adapter-journal review.
"""
from __future__ import annotations

import logging
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(SOURCE))
import pandas as pd

from trading_intelligence.execution.paper import PaperAdapter
from trading_intelligence.execution.paper_runner import PaperTradingRunner
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.regime.detector import Regime
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.risk.models import RiskConfig
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal
from trading_intelligence.strategy.router import StrategyRouter

SYMBOL = "BTCUSDT"
CAPITAL = Decimal("10000")
T0 = datetime(2026, 10, 1, 23, 55, tzinfo=timezone.utc)


class NoIO:
    def __getattr__(self, name):
        raise AssertionError(f"No external adapter operation permitted: {name}")


class OneSignal(AbstractStrategy):
    def __init__(self):
        super().__init__("reservation-review", SYMBOL, "5m", {})

    def on_bar(self, data):
        if len(data) != 61:
            return None
        return TradeProposal(
            strategy_id=self.strategy_id, symbol=SYMBOL, side="BUY", entry_type="MARKET",
            stop_price=Decimal("95"), timeframe="5m", rationale="synthetic test only",
            signal_strength=1.0, timestamp=data.index[-1].isoformat(),
        )

    def on_exit_signal(self, data, entry_price):
        return False


def bars(n: int, last_price: float = 100.0, *, cross_midnight: bool = False) -> pd.DataFrame:
    start = "2026-10-01T18:55:00Z" if cross_midnight else "2026-10-01T00:00:00Z"
    values = [100.0] * n
    values[-1] = last_price
    return pd.DataFrame(
        [{"open": p, "high": p * 1.001, "low": p * .999, "close": p, "volume": 1000.0}
         for p in values], index=pd.date_range(start, periods=n, freq="5min"),
    )


class ReservationAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="reservation-review-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for item in (
            patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")),
            patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")),
            patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Network forbidden")),
        ):
            item.start()
            self.addCleanup(item.stop)
        # Fixture limits: no operational configuration is changed.
        self.config = RiskConfig(
            max_position_size_pct=25.0, max_total_exposure_pct=25.0,
            max_correlated_exposure_pct=25.0, max_daily_turnover_pct=30.0,
        )
        self.risk = self.new_risk()
        self.paper = PaperAdapter(NoIO(), CAPITAL, self.root / "paper.json")
        router = StrategyRouter()
        signal = OneSignal()
        for regime in Regime:
            router.register(regime, signal)
        self.runner = PaperTradingRunner(router, self.risk, self.paper)

    def new_risk(self) -> RiskEngine:
        return RiskEngine(self.config, self.root / "risk.json", AuditLog(self.root / "audit"))

    def approve(self, *, cross_midnight: bool = False) -> None:
        result = self.runner.process_bar(SYMBOL, bars(61, cross_midnight=cross_midnight))
        self.assertEqual(result.action, "ENTRY_SUBMITTED", "fixture must obtain real approval")
        self.assertEqual(len(self.risk.reservation_ids()), 1)
        self.assertIsNone(self.paper.get_position(SYMBOL))

    def test_pending_entry_cannot_fill_after_kill_switch(self) -> None:
        self.approve()
        self.risk.activate_kill_switch("injected halt between decision and execution")
        self.runner.process_bar(SYMBOL, bars(62))
        self.assertIsNone(self.paper.get_position(SYMBOL),
                          "An already active kill switch must stop an unfilled entry")

    def test_affordable_gap_cannot_exceed_entry_notional_cap(self) -> None:
        self.approve()
        reserved = self.risk.total_open_exposure
        self.runner.process_bar(SYMBOL, bars(62, 150.0))
        actual = self.risk.total_open_exposure
        self.assertGreaterEqual(self.paper.cash, 0, "cash suffices; this is not an affordability rejection")
        self.assertLessEqual(actual, CAPITAL * Decimal(".25"),
                             f"reserved={reserved}, actual entry notional={actual}; cap=2500")

    def test_affordable_gap_cannot_exceed_approved_stop_risk(self) -> None:
        self.approve()
        self.runner.process_bar(SYMBOL, bars(62, 150.0))
        position = self.paper.get_position(SYMBOL)
        if position is None:  # rejecting the unsafe fill is valid fail-closed behavior
            return
        # Best-case exit AT the stop, before any stop slippage; excess here
        # cannot be blamed on a later adverse gap through a stop.
        stop = self.runner._stop_order_for(SYMBOL)
        self.assertIsNotNone(stop)
        loss_at_stop = ((position.avg_entry_price - stop.stop_price) * position.quantity
                        + position.entry_fee + stop.stop_price * position.quantity * self.paper.taker_fee)
        self.assertLessEqual(loss_at_stop, CAPITAL * Decimal(".01"),
                             f"risk from actual entry to fixed stop={loss_at_stop}; approved budget=100")

    def test_small_gap_cannot_exceed_total_exposure_cap(self) -> None:
        # Isolate the total cap from the single-position and fill-risk checks.
        # The values are synthetic fixture boundaries, never deployment policy.
        self.risk.config = RiskConfig(
            max_position_size_pct=25.0, max_total_exposure_pct=19.3,
            max_correlated_exposure_pct=25.0, max_daily_turnover_pct=30.0,
            max_fill_risk_overshoot_pct=100.0,
        )
        self.approve()
        self.runner.process_bar(SYMBOL, bars(62, 100.5))
        self.assertLessEqual(
            self.risk.total_open_exposure, CAPITAL * Decimal(".193"),
            "a small approved-to-fill gap crossed the configured portfolio exposure cap",
        )

    def test_small_gap_cannot_exceed_correlated_exposure_cap(self) -> None:
        self.risk.config = RiskConfig(
            max_position_size_pct=25.0, max_total_exposure_pct=25.0,
            max_correlated_exposure_pct=19.3, max_daily_turnover_pct=30.0,
            max_fill_risk_overshoot_pct=100.0,
        )
        self.approve()
        self.runner.process_bar(SYMBOL, bars(62, 100.5))
        self.assertLessEqual(
            self.risk._correlated_exposure(SYMBOL), CAPITAL * Decimal(".193"),
            "a small approved-to-fill gap crossed the configured correlation cap",
        )

    def test_small_gap_cannot_exceed_daily_turnover_cap(self) -> None:
        self.risk.config = RiskConfig(
            max_position_size_pct=25.0, max_total_exposure_pct=25.0,
            max_correlated_exposure_pct=25.0, max_daily_turnover_pct=19.3,
            max_fill_risk_overshoot_pct=100.0,
        )
        self.approve()
        self.runner.process_bar(SYMBOL, bars(62, 100.5))
        self.assertLessEqual(
            Decimal(self.risk.state.daily_turnover), CAPITAL * Decimal(".193"),
            "actual fill turnover exceeded the configured daily turnover cap",
        )

    def test_midnight_fill_is_counted_in_its_execution_day(self) -> None:
        self.approve(cross_midnight=True)
        self.runner.process_bar(SYMBOL, bars(62, cross_midnight=True))
        position = self.paper.get_position(SYMBOL)
        self.assertIsNotNone(position)
        self.assertEqual(self.risk.state.current_day, "2026-10-02")
        actual_notional = position.avg_entry_price * position.quantity
        self.assertEqual((self.risk.state.daily_trade_count, Decimal(self.risk.state.daily_turnover)),
                         (1, actual_notional), "observe_equity reset the fill just accounted by confirm_reservation")

    def test_release_old_reservation_cannot_erase_new_day_budget_after_reload(self) -> None:
        self.risk.observe_equity(CAPITAL, now=T0)
        self.risk.reserve_position("yesterday", SYMBOL, Decimal("100"))
        self.risk.observe_equity(CAPITAL, now=T0 + timedelta(minutes=5))
        self.risk.reserve_position("today", "ETHUSDT", Decimal("200"))
        # Reload only RiskState; deliberately excludes PaperAdapter journaling.
        restarted_risk = self.new_risk()
        self.assertTrue(restarted_risk.release_reservation("yesterday"))
        self.assertEqual((restarted_risk.state.daily_trade_count,
                          Decimal(restarted_risk.state.daily_turnover)),
                         (1, Decimal("200")), "old reservation debits today's unrelated reservation")

    def test_confirm_old_reservation_is_fully_charged_to_new_day(self) -> None:
        self.risk.observe_equity(CAPITAL, now=T0)
        self.risk.reserve_position("yesterday", SYMBOL, Decimal("100"))
        self.risk.observe_equity(CAPITAL, now=T0 + timedelta(minutes=5))
        self.risk.reserve_position("today", "ETHUSDT", Decimal("200"))
        restarted_risk = self.new_risk()
        restarted_risk.confirm_reservation("yesterday", "filled-today", SYMBOL, Decimal("120"))
        self.assertEqual((restarted_risk.state.daily_trade_count,
                          Decimal(restarted_risk.state.daily_turnover)),
                         (2, Decimal("320")), "new day gets only the fill-minus-yesterday delta")

    def test_risk_confirmation_failure_cannot_leave_actual_fill_unprotected(self) -> None:
        self.approve()
        with patch.object(self.risk, "confirm_reservation", side_effect=OSError("injected risk save failure")):
            try:
                self.runner.process_bar(SYMBOL, bars(62))
            except OSError:
                pass  # aborting the step is acceptable; leaving a filled BUY naked is not
        position = self.paper.get_position(SYMBOL)
        if position is not None:
            self.assertIsNotNone(self.runner._stop_order_for(SYMBOL),
                                  "risk bookkeeping failed after cash/position changed, before STOP submission")

    def test_same_day_release_preserves_unrelated_reservation_control(self) -> None:
        self.risk.observe_equity(CAPITAL, now=T0)
        self.risk.reserve_position("one", SYMBOL, Decimal("100"))
        self.risk.reserve_position("two", "ETHUSDT", Decimal("200"))
        self.assertTrue(self.risk.release_reservation("one"))
        self.assertEqual((self.risk.state.daily_trade_count, Decimal(self.risk.state.daily_turnover)),
                         (1, Decimal("200")))


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    print("RESERVATION REVIEW SOURCE:", SOURCE, flush=True)
    unittest.main(verbosity=2)
