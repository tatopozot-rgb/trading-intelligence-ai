"""
PaperTradingRunner lifecycle: chronology, the fill bar, halts and gaps between
approval and fill, and bookkeeping failures. Each test pins a defect that GPT
Work's independent review (PR #8) demonstrated against the runner. The
RiskEngine and PaperAdapter are real, never mocked.
"""
import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tests.test_paper_runner import (
    SYMBOL,
    WARMUP,
    _bars,
    _entered_runner,
    _flat,
    _paper,
    _risk,
    _router_for,
    _runner,
    _Scripted,
)
from trading_intelligence.execution.paper_runner import EXIT_STOP, EXIT_STRATEGY, PaperTradingRunner
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.risk.models import RiskConfig


def _signalled(tmp_path: Path, **kw) -> tuple[PaperTradingRunner, pd.DataFrame]:
    """Signal on bar 61 (an entry is approved, reserved and PENDING); no fill yet."""
    runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, **kw))
    data = _bars(_flat(WARMUP + 1))
    runner.run_replay(SYMBOL, data, warmup=WARMUP)
    assert SYMBOL in runner._pending_entries, "fixture must leave an approved, unfilled entry"
    assert len(runner.risk_engine.reservation_ids()) == 1
    return runner, data


def _series(
    prices: list[tuple[float, float, float, float]], start: str = "2026-01-01 00:00", freq: str = "1h",
) -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(prices), freq=freq)
    return pd.DataFrame(
        [{"open": o, "high": hi, "low": lo, "close": c, "volume": 1000.0} for o, hi, lo, c in prices],
        index=idx,
    )


class TestChronology:
    def test_a_duplicate_bar_cannot_fill_the_order_decided_after_it(self, tmp_path):
        runner, data = _signalled(tmp_path)
        cash = runner.paper.cash
        step = runner.process_bar(SYMBOL, data)
        assert step.action == "STALE_BAR_IGNORED"
        assert runner.paper.get_position(SYMBOL) is None
        assert runner.paper.cash == cash
        assert SYMBOL in runner._pending_entries, "the order is still waiting for the genuinely next bar"
        runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))
        assert runner.paper.get_position(SYMBOL) is not None

    def test_an_older_bar_cannot_execute_a_future_decision(self, tmp_path):
        runner, _ = _signalled(tmp_path)
        step = runner.process_bar(SYMBOL, _bars(_flat(WARMUP)))
        assert step.action == "STALE_BAR_IGNORED"
        assert runner.paper.get_position(SYMBOL) is None

    def test_a_stale_bar_changes_no_state(self, tmp_path):
        runner, data = _signalled(tmp_path)
        before = (runner.paper.cash, list(runner.paper.pending_orders), runner.risk_engine.reservation_ids(),
                  dict(runner.risk_engine.state.open_positions))
        runner.process_bar(SYMBOL, data)
        after = (runner.paper.cash, list(runner.paper.pending_orders), runner.risk_engine.reservation_ids(),
                 dict(runner.risk_engine.state.open_positions))
        assert before == after

    def test_a_stale_symbol_does_not_stop_the_others_in_the_same_call(self, tmp_path):
        runner, data = _signalled(tmp_path)
        fresh = _bars(_flat(WARMUP + 2))
        steps = runner.process_bars({SYMBOL: data, "ETHUSDT": fresh})
        by_symbol = {s.symbol: s.action for s in steps}
        assert by_symbol[SYMBOL] == "STALE_BAR_IGNORED"
        assert by_symbol["ETHUSDT"] != "STALE_BAR_IGNORED"

    def test_the_next_bar_is_accepted_after_a_stale_one(self, tmp_path):
        runner, data = _signalled(tmp_path)
        runner.process_bar(SYMBOL, data)
        step = runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))
        assert step.action != "STALE_BAR_IGNORED"


class TestTheFillBar:
    def test_a_stop_crossed_inside_the_fill_bar_closes_the_position_in_that_bar(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.05))  # stop 95
        # Opens at 100 (fills), trades down to 90 within the same bar.
        prices = _flat(WARMUP + 1) + [(100.0, 101.0, 90.0, 92.0)]
        steps = runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        assert runner.paper.get_position(SYMBOL) is None
        assert [t.exit_reason for t in runner.closed_trades] == [EXIT_STOP]
        sides = [f.side for f in steps[-1].fills if f.status == "FILLED"]
        assert sides == ["BUY", "SELL"], "both legs happened in the fill bar and are reported in its step"
        assert runner.risk_engine.open_position_count == 0
        assert runner.paper.pending_orders == []
        assert runner.reconcile() == []

    def test_the_stop_exit_in_the_fill_bar_pays_the_stop_price_not_the_low(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.05))
        prices = _flat(WARMUP + 1) + [(100.0, 101.0, 90.0, 92.0)]
        runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        expected = Decimal("95.0") * (1 - 2 * runner.paper.slippage_rate)
        assert abs(runner.closed_trades[0].exit_price - expected) < Decimal("0.0001")

    def test_a_low_just_above_the_stop_leaves_the_position_open(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.05))
        prices = _flat(WARMUP + 1) + [(100.0, 101.0, 95.5, 99.0)]
        runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        assert runner.paper.get_position(SYMBOL) is not None
        assert runner.closed_trades == []
        assert runner.reconcile() == []

    def test_cash_identity_holds_after_a_same_bar_stop(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.05))
        prices = _flat(WARMUP + 1) + [(100.0, 101.0, 90.0, 92.0)]
        runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        assert runner.paper.cash == Decimal("10000") + runner.closed_trades[0].pnl


class TestHaltBetweenApprovalAndFill:
    def _next_bar_result(self, runner):
        step = runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))
        assert runner.paper.get_position(SYMBOL) is None, "a halted entry must never fill"
        assert runner.paper.pending_orders == []
        assert runner.risk_engine.reservation_ids() == []
        assert runner.risk_engine.open_position_count == 0
        assert runner.paper.cash == Decimal("10000")
        assert runner._pending_entries == {}
        assert runner.reconcile() == []
        return step

    def test_a_kill_switch_cancels_the_unfilled_entry(self, tmp_path):
        runner, _ = _signalled(tmp_path)
        runner.risk_engine.activate_kill_switch("injected halt between decision and execution")
        step = self._next_bar_result(runner)
        assert step.notes == ["ENTRY_CANCELLED:KILL_SWITCH_ACTIVE"]

    def test_a_drawdown_pause_cancels_the_unfilled_entry(self, tmp_path):
        runner, _ = _signalled(tmp_path)
        runner.risk_engine.state.drawdown_paused = True
        step = self._next_bar_result(runner)
        assert step.notes == ["ENTRY_CANCELLED:DRAWDOWN_PAUSE_ACTIVE"]

    def test_a_daily_loss_halt_cancels_the_unfilled_entry(self, tmp_path):
        # Hourly bars stay inside one trading day, so the halt is still in force.
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1))
        runner.run_replay(SYMBOL, _series(_flat(WARMUP + 1)), warmup=WARMUP)
        assert SYMBOL in runner._pending_entries
        runner.risk_engine.state.trading_day_halted = True
        step = runner.process_bar(SYMBOL, _series(_flat(WARMUP + 2)))
        assert step.notes == ["ENTRY_CANCELLED:DAILY_LOSS_LIMIT_REACHED"]
        assert runner.paper.get_position(SYMBOL) is None
        assert runner.risk_engine.reservation_ids() == []

    def test_a_halt_never_stops_a_protective_stop_from_closing(self, tmp_path):
        runner, _ = _entered_runner(tmp_path)
        runner.risk_engine.activate_kill_switch("manual halt")
        runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2) + [(90.0, 91.0, 80.0, 85.0)]))
        assert [t.exit_reason for t in runner.closed_trades] == [EXIT_STOP]
        assert runner.paper.get_position(SYMBOL) is None

    def test_a_halt_lifted_in_time_lets_the_entry_fill(self, tmp_path):
        runner, _ = _signalled(tmp_path)
        runner.risk_engine.activate_kill_switch("brief halt")
        runner.risk_engine.clear_kill_switch(operator_confirmation=True)
        runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))
        assert runner.paper.get_position(SYMBOL) is not None

    def test_the_veto_fails_closed_when_the_risk_engine_errors(self, tmp_path, monkeypatch):
        runner, _ = _signalled(tmp_path)

        def boom(*args, **kwargs):
            raise RuntimeError("risk engine exploded")

        monkeypatch.setattr(runner.risk_engine, "entry_block_reason", boom)
        step = runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))
        assert step.notes == ["ENTRY_CANCELLED:RISK_ERROR"]
        assert runner.paper.get_position(SYMBOL) is None
        assert runner.risk_engine.reservation_ids() == []


class TestGapBetweenApprovalAndFill:
    def test_a_gap_that_multiplies_the_risk_cancels_the_entry(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.05))
        prices = _flat(WARMUP + 1) + [(150.0, 151.0, 149.0, 150.0)]  # +50% over the approved 100
        steps = runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        assert steps[-1].notes == ["ENTRY_CANCELLED:FILL_RISK_EXCEEDS_BUDGET"]
        assert runner.paper.get_position(SYMBOL) is None
        assert runner.paper.cash == Decimal("10000")
        assert runner.risk_engine.open_position_count == 0
        assert runner.risk_engine.reservation_ids() == []
        assert runner.reconcile() == []

    def test_an_open_below_the_stop_cancels_the_entry(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.05))
        prices = _flat(WARMUP + 1) + [(90.0, 91.0, 88.0, 89.0)]  # opens beneath the 95 stop
        steps = runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        assert steps[-1].notes == ["ENTRY_CANCELLED:FILL_AT_OR_BELOW_STOP"]
        assert runner.paper.get_position(SYMBOL) is None
        assert runner.closed_trades == []

    def test_a_modest_gap_inside_the_tolerance_still_fills(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.05))
        prices = _flat(WARMUP + 1) + [(100.5, 101.5, 100.0, 101.0)]  # +0.5%: risk +10%
        steps = runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        assert steps[-1].notes == []
        assert runner.paper.get_position(SYMBOL) is not None

    def test_a_cancelled_entry_does_not_poison_the_next_signal(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.05))
        prices = _flat(WARMUP + 1) + [(150.0, 151.0, 149.0, 150.0)] + _flat(2, 150.0)
        runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        assert runner.risk_engine.reservation_ids() == []
        assert runner.reconcile() == []

    def test_the_veto_is_audited(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1, stop_pct=0.05))
        runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 1) + [(150.0, 151.0, 149.0, 150.0)]), warmup=WARMUP)
        events = [r["event"] for r in runner.risk_engine.audit_log.read_all()]
        assert "FILL_VETOED" in events


class TestTradingDayAttribution:
    def test_a_fill_on_the_new_day_is_counted_on_the_new_day(self, tmp_path):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1))
        # 61 five-minute bars ending 23:55; the fill bar is 00:00 the next day.
        start = "2025-12-31 18:55"
        runner.run_replay(SYMBOL, _series(_flat(WARMUP + 1), start, "5min"), warmup=WARMUP)
        assert SYMBOL in runner._pending_entries
        runner.process_bar(SYMBOL, _series(_flat(WARMUP + 2), start, "5min"))
        position = runner.paper.get_position(SYMBOL)
        assert position is not None
        state = runner.risk_engine.state
        assert state.current_day == "2026-01-01"
        assert state.daily_trade_count == 1
        assert Decimal(state.daily_turnover) == position.avg_entry_price * position.quantity


class TestRiskClockFailureBeforeFill:
    def test_a_failed_clock_advance_cancels_the_already_pending_entry(self, tmp_path, monkeypatch):
        """Found by GPT Work (PR #8): blocking NEW signals was not enough; a BUY queued on the
        previous bar still filled while the risk state it depends on was known to be broken."""
        runner, _ = _signalled(tmp_path)

        def boom(*args, **kwargs):
            raise OSError("synthetic disk fault")

        monkeypatch.setattr(runner.risk_engine, "advance_clock", boom)
        step = runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))
        assert runner.paper.get_position(SYMBOL) is None
        assert step.notes == ["ENTRY_CANCELLED:RISK_CLOCK_ERROR"]
        assert runner.paper.pending_orders == []
        assert runner.risk_engine.reservation_ids() == []
        assert runner._pending_entries == {}
        assert runner.paper.cash == Decimal("10000")

    def test_a_working_clock_still_lets_the_entry_fill(self, tmp_path):
        runner, _ = _signalled(tmp_path)
        runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))
        assert runner.paper.get_position(SYMBOL) is not None

    def test_protective_stops_are_not_cancelled_when_the_clock_fails(self, tmp_path, monkeypatch):
        runner, _ = _entered_runner(tmp_path)

        def boom(*args, **kwargs):
            raise OSError("synthetic disk fault")

        monkeypatch.setattr(runner.risk_engine, "advance_clock", boom)
        runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2) + [(90.0, 91.0, 80.0, 85.0)]))
        assert [t.exit_reason for t in runner.closed_trades] == [EXIT_STOP], "exits are never blocked"


class TestBookkeepingFailures:
    def test_a_failed_risk_confirmation_never_leaves_the_fill_without_its_stop(self, tmp_path, monkeypatch):
        runner, _ = _signalled(tmp_path)

        def boom(*args, **kwargs):
            raise OSError("injected risk save failure")

        monkeypatch.setattr(runner.risk_engine, "confirm_reservation", boom)
        runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))  # must not raise
        assert runner.paper.get_position(SYMBOL) is not None
        assert runner._stop_order_for(SYMBOL) is not None, "the fill must be protected before any bookkeeping"

    def test_a_failed_risk_confirmation_blocks_new_entries_until_the_books_agree(self, tmp_path, monkeypatch):
        runner, _ = _signalled(tmp_path)

        def boom(*args, **kwargs):
            raise OSError("injected risk save failure")

        monkeypatch.setattr(runner.risk_engine, "confirm_reservation", boom)
        runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))
        problems = runner.reconcile()
        assert any("not registered in the RiskEngine" in p for p in problems)
        step = runner.process_bar("ETHUSDT", _bars(_flat(WARMUP + 1)))
        assert step.action == "ENTRIES_BLOCKED"

    def test_a_failed_close_registration_does_not_lose_the_closed_trade(self, tmp_path, monkeypatch):
        runner, _ = _entered_runner(tmp_path)

        def boom(*args, **kwargs):
            raise OSError("injected risk save failure")

        monkeypatch.setattr(runner.risk_engine, "register_position_closed", boom)
        runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2) + [(90.0, 91.0, 80.0, 85.0)]))  # must not raise
        assert len(runner.closed_trades) == 1
        assert runner.paper.get_position(SYMBOL) is None
        assert any("has no paper position" in p for p in runner.reconcile()), "the books now disagree: blocked"

    def test_a_failed_clock_advance_blocks_entries(self, tmp_path, monkeypatch):
        runner = _runner(tmp_path, _Scripted(entry_at=WARMUP + 1))

        def boom(*args, **kwargs):
            raise RuntimeError("cannot advance")

        monkeypatch.setattr(runner.risk_engine, "advance_clock", boom)
        steps = runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 3)), warmup=WARMUP)
        assert all(s.action == "ENTRIES_BLOCKED" for s in steps)
        assert "failed to advance its clock" in steps[0].blocked_by[0]


class TestRestartBetweenApprovalAndFill:
    def test_a_pending_entry_does_not_survive_a_restart_nor_double_fill(self, tmp_path):
        runner, _ = _signalled(tmp_path)
        restarted = PaperTradingRunner(
            _router_for(_Scripted(entry_at=10**9)), _risk(tmp_path), _paper(tmp_path),
        )
        assert restarted.paper.pending_orders == []
        assert restarted.risk_engine.reservation_ids() == []
        restarted.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))
        assert restarted.paper.get_position(SYMBOL) is None


@pytest.mark.parametrize("bars_after", [1, 2])
def test_replaying_the_whole_history_after_the_run_is_inert(tmp_path, bars_after):
    runner, data = _entered_runner(tmp_path)
    snapshot = (runner.paper.cash, dict(runner.paper.positions), runner.risk_engine.open_position_count)
    for _ in range(bars_after):
        assert runner.process_bar(SYMBOL, data).action == "STALE_BAR_IGNORED"
    assert (runner.paper.cash, dict(runner.paper.positions), runner.risk_engine.open_position_count) == snapshot


class TestOneEquityPerTimestamp:
    def test_every_fill_check_in_a_timestamp_sees_the_same_equity(self, tmp_path, monkeypatch):
        """Found by the lifecycle fuzzer: equity was re-read per symbol, so the first
        symbol's fill (cash spent, its mark moved) changed the cap and risk budget the
        next symbol was vetted against, and the limits depended on symbol order."""
        runner = PaperTradingRunner(
            lambda sym: _router_for(_Scripted(entry_at=WARMUP + 1, symbol=sym)), _risk(tmp_path), _paper(tmp_path),
        )
        flat = _bars(_flat(WARMUP + 1))
        runner.process_bars({"AAAUSDT": flat, "BBBUSDT": flat})  # both signal and are approved
        assert len(runner._pending_entries) == 2

        seen: list[Decimal] = []
        original = RiskEngine.validate_fill

        def spy(self, quantity, stop_price, fill_price, equity, **kwargs):
            seen.append(equity)
            return original(self, quantity, stop_price, fill_price, equity, **kwargs)

        monkeypatch.setattr(RiskEngine, "validate_fill", spy)
        nxt = _bars(_flat(WARMUP + 2))
        runner.process_bars({"AAAUSDT": nxt, "BBBUSDT": nxt})
        assert len(seen) == 2
        assert seen[0] == seen[1], f"the second symbol was vetted against a different equity: {seen}"
        assert len(runner.paper.positions) == 2, "fixture must actually fill both entries"


class TestMarketValueExposure:
    def _runner(self, tmp_path, basis):
        risk = RiskEngine(
            RiskConfig(max_position_size_pct=100.0, max_total_exposure_pct=100.0, max_correlated_exposure_pct=100.0,
                       max_daily_turnover_pct=1000.0, max_trades_per_day=1000, exposure_basis=basis),
            tmp_path / "risk.json", AuditLog(tmp_path / "audit"),
        )
        return PaperTradingRunner(_router_for(_Scripted(entry_at=WARMUP + 1)), risk, _paper(tmp_path))

    def test_a_winning_position_is_reported_to_the_risk_engine_at_market_value(self, tmp_path):
        runner = self._runner(tmp_path, "entry_or_market")
        prices = _flat(WARMUP + 1) + _flat(1) + [(120.0, 121.0, 119.0, 120.0)]
        runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        position = runner.paper.get_position(SYMBOL)
        assert position is not None
        assert runner.risk_engine.total_open_exposure == position.quantity * Decimal("120.0")
        assert runner.risk_engine.total_open_exposure > position.quantity * position.avg_entry_price

    def test_the_default_keeps_counting_the_entry_notional(self, tmp_path):
        runner = self._runner(tmp_path, "entry")
        prices = _flat(WARMUP + 1) + _flat(1) + [(120.0, 121.0, 119.0, 120.0)]
        runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        position = runner.paper.get_position(SYMBOL)
        assert runner.risk_engine.total_open_exposure == position.quantity * position.avg_entry_price

    def test_a_failure_to_update_marks_blocks_entries(self, tmp_path, monkeypatch):
        runner = self._runner(tmp_path, "entry_or_market")

        def boom(*args, **kwargs):
            raise RuntimeError("cannot mark")

        monkeypatch.setattr(runner.risk_engine, "update_marks", boom)
        steps = runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 3)), warmup=WARMUP)
        assert all(s.action == "ENTRIES_BLOCKED" for s in steps)
        assert "update position marks" in steps[0].blocked_by[0]


class TestStrategyBindingAcrossRestarts:
    """Before this, a restart left every open position managed by its persisted STOP
    only: the strategy's own exit signal was gone. With PaperLoop restarts are routine."""

    def _runner(self, tmp_path, strategy, state=True):
        return PaperTradingRunner(
            _router_for(strategy), _risk(tmp_path), _paper(tmp_path),
            state_path=(tmp_path / "runner.json") if state else None,
        )

    def _enter(self, tmp_path, state=True):
        runner = self._runner(tmp_path, _Scripted(entry_at=WARMUP + 1, exit_at=WARMUP + 4), state)
        runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 2)), warmup=WARMUP)
        assert runner.paper.get_position(SYMBOL) is not None
        return runner

    def test_the_strategy_is_reattached_and_its_exit_still_fires(self, tmp_path):
        self._enter(tmp_path)
        restarted = self._runner(tmp_path, _Scripted(entry_at=10**9, exit_at=WARMUP + 4))
        assert restarted._open_trades[SYMBOL].strategy is not None
        restarted.run_replay(SYMBOL, _bars(_flat(WARMUP + 5)), warmup=WARMUP + 2)
        assert [t.exit_reason for t in restarted.closed_trades] == [EXIT_STRATEGY]
        assert restarted.reconcile() == []

    def test_without_a_state_path_nothing_changes(self, tmp_path):
        self._enter(tmp_path, state=False)
        restarted = self._runner(tmp_path, _Scripted(entry_at=10**9, exit_at=WARMUP + 4), state=False)
        assert restarted._open_trades[SYMBOL].strategy is None

    def test_a_strategy_no_longer_routed_falls_back_to_the_stop(self, tmp_path):
        self._enter(tmp_path)
        other = _Scripted(entry_at=10**9)
        other.strategy_id = "something-else"
        restarted = self._runner(tmp_path, other)
        assert restarted._open_trades[SYMBOL].strategy is None
        assert restarted._stop_order_for(SYMBOL) is not None
        assert restarted.reconcile() == []

    def test_an_unreadable_bindings_file_falls_back_to_the_stop(self, tmp_path):
        self._enter(tmp_path)
        (tmp_path / "runner.json").write_text("{not json")
        restarted = self._runner(tmp_path, _Scripted(entry_at=10**9, exit_at=WARMUP + 4))
        assert restarted._open_trades[SYMBOL].strategy is None
        assert restarted.reconcile() == []

    def test_a_binding_for_another_position_is_not_reused(self, tmp_path):
        self._enter(tmp_path)
        data = json.loads((tmp_path / "runner.json").read_text())
        data["bindings"][SYMBOL]["position_id"] = "an-older-position"
        (tmp_path / "runner.json").write_text(json.dumps(data))
        restarted = self._runner(tmp_path, _Scripted(entry_at=10**9, exit_at=WARMUP + 4))
        assert restarted._open_trades[SYMBOL].strategy is None

    def test_a_closed_position_leaves_no_binding_behind(self, tmp_path):
        runner = self._enter(tmp_path)
        runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2) + [(90.0, 91.0, 80.0, 85.0)]))
        assert runner.closed_trades
        assert json.loads((tmp_path / "runner.json").read_text())["bindings"] == {}

    def test_a_failure_to_save_bindings_never_interrupts_a_fill(self, tmp_path, monkeypatch):
        runner = self._runner(tmp_path, _Scripted(entry_at=WARMUP + 1))
        blocker = tmp_path / "blocker"
        blocker.write_text("a file where a directory should be")
        monkeypatch.setattr(runner, "state_path", blocker / "runner.json")  # only this save can fail
        runner.run_replay(SYMBOL, _bars(_flat(WARMUP + 2)), warmup=WARMUP)
        assert runner.paper.get_position(SYMBOL) is not None
        assert runner._stop_order_for(SYMBOL) is not None


class TestPortfolioCapsAtTheFill:
    def test_a_small_gap_that_breaches_the_total_cap_cancels_the_entry(self, tmp_path):
        """Found by GPT Work (PR #8): approval used the reserved notional; the fill did not."""
        risk = RiskEngine(
            RiskConfig(max_position_size_pct=25.0, max_total_exposure_pct=19.3, max_correlated_exposure_pct=25.0,
                       max_daily_turnover_pct=30.0, max_fill_risk_overshoot_pct=100.0),
            tmp_path / "risk.json", AuditLog(tmp_path / "audit"),
        )
        runner = PaperTradingRunner(_router_for(_Scripted(entry_at=WARMUP + 1, stop_pct=0.05)), risk, _paper(tmp_path))
        prices = _flat(WARMUP + 1) + [(100.5, 101.0, 100.0, 100.5)]  # +0.5%: approved ~1923, fills ~1934 > 1930
        steps = runner.run_replay(SYMBOL, _bars(prices), warmup=WARMUP)
        assert steps[-1].notes == ["ENTRY_CANCELLED:FILL_EXCEEDS_TOTAL_EXPOSURE"]
        assert runner.paper.get_position(SYMBOL) is None
        assert risk.total_open_exposure == Decimal("0")
        assert runner.reconcile() == []


class TestCrashBetweenFillAndProtection:
    def test_a_crash_right_after_the_fill_restarts_with_the_stop_in_place(self, tmp_path, monkeypatch):
        """GPT Work (PR #8): the fill used to be persisted before the STOP. A process exit in
        between restarted into a naked position."""
        runner, _ = _signalled(tmp_path)
        original = runner.paper.on_new_bar

        def power_loss_after_fill(*args, **kwargs):
            results = original(*args, **kwargs)
            if any(r.side == "BUY" and r.status == "FILLED" for r in results):
                raise SystemExit("synthetic power loss before the runner saw the fill")
            return results

        monkeypatch.setattr(runner.paper, "on_new_bar", power_loss_after_fill)
        with pytest.raises(SystemExit):
            runner.process_bar(SYMBOL, _bars(_flat(WARMUP + 2)))

        restarted = PaperTradingRunner(_router_for(_Scripted(entry_at=10**9)), _risk(tmp_path), _paper(tmp_path))
        assert restarted.paper.get_position(SYMBOL) is not None
        stop = restarted._stop_order_for(SYMBOL)
        assert stop is not None, "the fill and its protective STOP are persisted together"
        assert stop.stop_price == Decimal("95.0")
