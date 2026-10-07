"""
Tests for PaperTradingRunner — the router -> RiskEngine -> PaperAdapter link.
Each invariant stated in the module docstring has a test here. The RiskEngine
and PaperAdapter are real (never mocked), per AGENTS.md.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from tests.synthetic_market import make_btc_like_ohlcv_4h, resample_to_1d
from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.order_models import OrderRequest
from trading_intelligence.execution.paper import PaperAdapter
from trading_intelligence.execution.paper_runner import (
    EXIT_STOP,
    EXIT_STRATEGY,
    PaperTradingRunner,
)
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.regime.detector import Regime
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.risk.models import RiskConfig
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal
from trading_intelligence.strategy.router import StrategyRouter, default_router

SYMBOL = "BTCUSDT"
WARMUP = 60


class _DataOnly(AbstractExchangeAdapter):
    def submit_order(self, order):
        raise AssertionError("paper must never forward orders")

    def cancel_order(self, client_order_id):
        raise AssertionError("not used")

    def get_position(self, symbol):
        return None

    def get_account_info(self):
        raise AssertionError("not used")

    def get_current_price(self, symbol):
        return Decimal("100")

    def get_ohlcv(self, symbol, timeframe, limit=500):
        return pd.DataFrame()

    def is_connected(self):
        return True

    def get_exchange_name(self):
        return "data_only"


class _Scripted(AbstractStrategy):
    """Proposes a BUY when len(data) == entry_at, signals exit at exit_at.
    Stop is a fixed percentage below the signal bar's close."""

    def __init__(self, entry_at: int, exit_at: Optional[int] = None, stop_pct: float = 0.05):
        super().__init__("scripted", SYMBOL, "1d", {})
        self.entry_at = entry_at
        self.exit_at = exit_at
        self.stop_pct = Decimal(str(stop_pct))

    def on_bar(self, data):
        if len(data) != self.entry_at:
            return None
        close = Decimal(str(float(data["close"].iloc[-1])))
        return TradeProposal(
            strategy_id="scripted", symbol=SYMBOL, side="BUY", entry_type="MARKET",
            stop_price=close * (1 - self.stop_pct), timeframe="1d", rationale="scripted",
            signal_strength=1.0, timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def on_exit_signal(self, data, entry_price):
        return self.exit_at is not None and len(data) == self.exit_at


def _bars(prices: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(prices), freq="1D")
    return pd.DataFrame(
        [{"open": o, "high": hi, "low": lo, "close": c, "volume": 1000.0} for o, hi, lo, c in prices],
        index=idx,
    )


def _flat(n: int, price: float = 100.0) -> list[tuple[float, float, float, float]]:
    return [(price, price * 1.001, price * 0.999, price)] * n


def _router_for(strategy: AbstractStrategy) -> StrategyRouter:
    router = StrategyRouter()
    for regime in Regime:
        router.register(regime, strategy)
    return router


def _risk(tmp_path: Path) -> RiskEngine:
    config = RiskConfig(
        max_position_size_pct=100.0, max_total_exposure_pct=100.0,
        max_correlated_exposure_pct=100.0, max_daily_turnover_pct=1000.0,
        max_trades_per_day=1000,
    )
    return RiskEngine(config, tmp_path / "risk.json", AuditLog(tmp_path / "audit"))


def _paper(tmp_path: Path, equity: str = "10000") -> PaperAdapter:
    return PaperAdapter(_DataOnly(), Decimal(equity), tmp_path / "paper.json")


def _runner(tmp_path: Path, strategy: AbstractStrategy, equity: str = "10000") -> PaperTradingRunner:
    return PaperTradingRunner(_router_for(strategy), _risk(tmp_path), _paper(tmp_path, equity))


def _entered_runner(tmp_path: Path, exit_at: Optional[int] = None) -> tuple[PaperTradingRunner, pd.DataFrame]:
    """Signal on bar 61, fill on bar 62; returns runner and the bars so far."""
    runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, exit_at=exit_at))
    data = _bars(_flat(WARMUP + 2))
    runner.run_replay(SYMBOL, data, warmup=WARMUP)
    return runner, data


class TestEntryPath:
    def test_entry_goes_through_risk_then_fills_next_bar_with_stop(self, tmp_path):
        runner, _ = _entered_runner(tmp_path)
        assert runner.paper.get_position(SYMBOL) is not None
        assert runner.risk_engine.open_position_count == 1
        stop = runner._stop_order_for(SYMBOL)
        assert stop is not None and stop.stop_price is not None
        assert stop.stop_price < Decimal("100")
        assert runner.reconcile() == []

    def test_entry_is_sized_by_the_risk_engine_not_the_strategy(self, tmp_path):
        runner, _ = _entered_runner(tmp_path)
        approved = [s for s in runner.steps if s.risk_decision and s.risk_decision.approved]
        assert len(approved) == 1
        assert runner.paper.get_position(SYMBOL).quantity == approved[0].risk_decision.quantity

    def test_kill_switch_blocks_every_entry(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1))
        runner.risk_engine.activate_kill_switch("test")
        steps = runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 4)), warmup=WARMUP)
        assert any(s.action == "RISK_REJECTED:KILL_SWITCH_ACTIVE" for s in steps)
        assert runner.paper.pending_orders == []
        assert runner.paper.get_position(SYMBOL) is None

    def test_risk_rejection_places_no_order(self, tmp_path):
        # 100% stop distance sizes to a position the 5% default cap rejects.
        config = RiskConfig(max_position_size_pct=1.0)
        risk = RiskEngine(config, tmp_path / "risk.json", AuditLog(tmp_path / "audit"))
        runner = PaperTradingRunner(
            _router_for(_Scripted(entry_at=WARMUP + 1, stop_pct=0.02)), risk, _paper(tmp_path),
        )
        steps = runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 3)), warmup=WARMUP)
        assert any(s.action.startswith("RISK_REJECTED") for s in steps)
        assert runner.paper.pending_orders == []

    def test_risk_engine_exception_fails_closed(self, tmp_path, monkeypatch):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1))

        def boom(*args, **kwargs):
            raise RuntimeError("risk engine exploded")

        monkeypatch.setattr(runner.risk_engine, "validate_order", boom)
        steps = runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 3)), warmup=WARMUP)
        assert any(s.action == "RISK_ERROR_NO_ORDER" for s in steps)
        assert runner.paper.pending_orders == []

    def test_empty_router_never_trades(self, tmp_path):
        runner = PaperTradingRunner(StrategyRouter(), _risk(tmp_path), _paper(tmp_path))
        steps = runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 10)), warmup=WARMUP)
        assert all(s.action.startswith("NO_TRADE") for s in steps)
        assert runner.paper.pending_orders == [] and runner.paper.positions == {}

    def test_gap_up_fill_that_is_unaffordable_clears_the_entry(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.01), equity="1000")
        prices = _flat(WARMUP + 1) + [(140.0, 141.0, 139.0, 140.0)]  # +40% gap at the fill bar
        runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        assert runner.paper.get_position(SYMBOL) is None
        assert runner.paper.cash == Decimal("1000")
        assert runner.risk_engine.open_position_count == 0
        assert runner._pending_entries == {}
        assert runner.reconcile() == []


class TestExitPath:
    def test_stop_hit_closes_registers_and_leaves_no_orders(self, tmp_path):
        runner, data = _entered_runner(tmp_path)
        crash = _bars(_flat(WARMUP + 2) + [(90.0, 91.0, 80.0, 85.0)])
        runner.process_bar(SYMBOL, crash)
        assert len(runner.closed_trades) == 1
        trade = runner.closed_trades[0]
        assert trade.exit_reason == EXIT_STOP and trade.pnl < 0
        assert runner.risk_engine.open_position_count == 0
        assert runner.paper.get_position(SYMBOL) is None
        assert runner.paper.pending_orders == []

    def test_strategy_exit_closes_and_cancels_the_stop(self, tmp_path):
        runner, _ = _entered_runner(tmp_path, exit_at=WARMUP + 3)
        runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 5)), warmup=WARMUP + 2)
        assert [t.exit_reason for t in runner.closed_trades] == [EXIT_STRATEGY]
        assert runner.paper.pending_orders == []
        assert runner.risk_engine.open_position_count == 0
        assert runner.reconcile() == []

    def test_cash_equals_initial_plus_realized_pnl_when_flat(self, tmp_path):
        runner, _ = _entered_runner(tmp_path, exit_at=WARMUP + 3)
        runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 6)), warmup=WARMUP + 2)
        assert runner.paper.positions == {}
        realized = sum((t.pnl for t in runner.closed_trades), Decimal("0"))
        assert abs(runner.paper.cash - (Decimal("10000") + realized)) < Decimal("0.0000001")


class TestReconciliationAndRecovery:
    def test_unregistered_paper_position_blocks_new_entries(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1))
        runner.paper.submit_order(OrderRequest(SYMBOL, "BUY", "MARKET", Decimal("1")))
        runner.paper.on_new_bar(SYMBOL, Decimal("100"), Decimal("100"), Decimal("100"),
                                Decimal("100"), "2026-01-01T00:00:00Z")
        problems = runner.reconcile()
        assert any("not registered in the RiskEngine" in p for p in problems)
        step = runner.process_bar("ETHUSDT", _bars(_flat(WARMUP + 1)))
        assert step.action == "ENTRIES_BLOCKED"

    def test_position_without_protective_stop_blocks_entries(self, tmp_path):
        runner, data = _entered_runner(tmp_path)
        runner.paper.cancel_order(runner._stop_order_for(SYMBOL).client_order_id)
        assert any("no protective STOP" in p for p in runner.reconcile())
        step = runner.process_bar("ETHUSDT", _bars(_flat(WARMUP + 1)))
        assert step.action == "ENTRIES_BLOCKED"

    def test_restart_keeps_the_protective_stop_and_still_closes_on_a_gap(self, tmp_path):
        runner, _ = _entered_runner(tmp_path)
        assert runner.paper.get_position(SYMBOL) is not None

        restarted = PaperTradingRunner(
            _router_for(_Scripted(entry_at=10**9)), _risk(tmp_path), _paper(tmp_path),
        )
        assert restarted.reconcile() == []
        assert SYMBOL in restarted._open_trades
        restarted.process_bar(SYMBOL, _bars(_flat(WARMUP + 2) + [(70.0, 72.0, 60.0, 65.0)]))
        assert [t.exit_reason for t in restarted.closed_trades] == [EXIT_STOP]
        assert restarted.risk_engine.open_position_count == 0
        assert restarted.paper.get_position(SYMBOL) is None


class TestEndToEndReplay:
    def test_default_router_replay_books_stay_consistent(self, tmp_path):
        data = resample_to_1d(make_btc_like_ohlcv_4h(6 * 365 * 4, seed=2))
        risk = _risk(tmp_path)
        paper = _paper(tmp_path)
        runner = PaperTradingRunner(default_router(), risk, paper)
        runner.run_replay(SYMBOL, data)

        assert len(runner.closed_trades) >= 1, "expected at least one full round trip"
        assert runner.reconcile() == []
        assert risk.open_position_count == len(paper.positions)
        # Every entry the runner submitted was approved by the RiskEngine first.
        submitted = [s for s in runner.steps if s.action == "ENTRY_SUBMITTED"]
        assert submitted and all(s.risk_decision and s.risk_decision.approved for s in submitted)
        if not paper.positions:
            realized = sum((t.pnl for t in runner.closed_trades), Decimal("0"))
            assert abs(paper.cash - (Decimal("10000") + realized)) < Decimal("0.0000001")
        assert paper.cash >= 0


@pytest.mark.parametrize("bad", [pd.DataFrame()])
def test_empty_data_is_a_noop(tmp_path, bad):
    runner = _runner(tmp_path, _Scripted(entry_at=1))
    assert runner.process_bar(SYMBOL, bad).action == "NO_DATA"
