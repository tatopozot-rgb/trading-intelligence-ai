"""
Tests for RiskEngine — every reject reason, boundary conditions, restart
persistence. Per AGENTS.md: risk engine tests are mandatory and the engine
must never be mocked in these tests.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.risk.engine import (
    REASON_CORRELATED_EXPOSURE_EXCEEDED,
    REASON_DAILY_LOSS_LIMIT_REACHED,
    REASON_DAILY_TRADE_LIMIT_REACHED,
    REASON_DRAWDOWN_PAUSE_ACTIVE,
    REASON_EXPOSURE_LIMIT_EXCEEDED,
    REASON_FILL_AT_OR_BELOW_STOP,
    REASON_FILL_EXCEEDS_POSITION_CAP,
    REASON_FILL_RISK_EXCEEDS_BUDGET,
    REASON_INVALID_REFERENCE_PRICE,
    REASON_KILL_SWITCH_ACTIVE,
    REASON_MAX_POSITION_SIZE_EXCEEDED,
    REASON_MAX_POSITIONS_REACHED,
    REASON_NO_STOP_LOSS_DEFINED,
    REASON_OK,
    REASON_POSITION_SIZE_ZERO,
    REASON_STOP_TOO_TIGHT,
    RiskEngine,
)
from trading_intelligence.risk.models import RiskConfig
from trading_intelligence.strategy.models import TradeProposal


def _proposal(
    symbol: str = "BTCUSDT",
    entry_price: Decimal = Decimal("50000"),
    stop_price: Decimal = Decimal("49000"),
) -> TradeProposal:
    return TradeProposal(
        strategy_id="test_strategy",
        symbol=symbol,
        side="BUY",
        entry_type="MARKET",
        stop_price=stop_price,
        timeframe="1h",
        rationale="test",
        signal_strength=1.0,
        timestamp="2026-01-01T00:00:00Z",
        entry_price=entry_price,
    )


def _engine(tmp_path: Path, **config_overrides) -> RiskEngine:
    config = RiskConfig(**config_overrides)
    audit_log = AuditLog(tmp_path / "audit")
    return RiskEngine(config, tmp_path / "risk_state.json", audit_log)


def _loose_engine(tmp_path: Path, **config_overrides) -> RiskEngine:
    """
    Engine with generous position/exposure caps. With the spec's own defaults
    (max_risk_per_trade_pct=1%, a realistic 2% stop), fixed-fractional sizing
    produces a position_value around 45% of equity — which trips the default
    max_position_size_pct (5%) and max_correlated_exposure_pct (10%) caps on
    almost any order. Tests that aren't specifically exercising those two caps
    use this helper so they isolate the behavior they're actually testing.
    """
    overrides = {
        "max_position_size_pct": 100.0,
        "max_total_exposure_pct": 100.0,
        "max_correlated_exposure_pct": 100.0,
        # Previously unenforced (real bug, now fixed — see engine.py's
        # Step 9b), so this helper never needed to loosen it before.
        "max_daily_turnover_pct": 1000.0,
        **config_overrides,
    }
    return _engine(tmp_path, **overrides)


class TestRiskConfigValidation:
    def test_valid_config(self):
        RiskConfig()  # should not raise

    def test_invalid_risk_pct(self):
        with pytest.raises(ValueError, match="max_risk_per_trade_pct"):
            RiskConfig(max_risk_per_trade_pct=0)

    def test_invalid_drawdown_ordering(self):
        with pytest.raises(ValueError, match="drawdown_pause_pct"):
            RiskConfig(drawdown_pause_pct=20, drawdown_halt_pct=10)

    def test_invalid_max_open_positions(self):
        with pytest.raises(ValueError, match="max_open_positions"):
            RiskConfig(max_open_positions=0)


class TestApproval:
    def test_basic_approval(self, tmp_path):
        engine = _loose_engine(tmp_path)
        decision = engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert decision.approved
        assert decision.reason == REASON_OK
        assert decision.quantity is not None
        assert decision.quantity > 0

    def test_approval_logs_audit_entry(self, tmp_path):
        engine = _loose_engine(tmp_path)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"))
        entries = engine.audit_log.read_all()
        assert len(entries) == 1
        assert entries[0]["decision"] == "APPROVED"
        assert entries[0]["event"] == "RISK_DECISION"


class TestKillSwitch:
    def test_kill_switch_blocks_all_orders(self, tmp_path):
        engine = _engine(tmp_path)
        engine.activate_kill_switch("manual test halt")
        decision = engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_KILL_SWITCH_ACTIVE

    def test_kill_switch_active_in_config_at_startup(self, tmp_path):
        config = RiskConfig(kill_switch_active=True)
        audit_log = AuditLog(tmp_path / "audit")
        engine = RiskEngine(config, tmp_path / "risk_state.json", audit_log)
        assert engine.state.kill_switch is True

    def test_clear_requires_confirmation(self, tmp_path):
        engine = _engine(tmp_path)
        engine.activate_kill_switch("test")
        with pytest.raises(ValueError, match="operator_confirmation"):
            engine.clear_kill_switch()
        assert engine.state.kill_switch is True

    def test_clear_with_confirmation_works(self, tmp_path):
        engine = _loose_engine(tmp_path)
        engine.activate_kill_switch("test")
        engine.clear_kill_switch(operator_confirmation=True)
        assert engine.state.kill_switch is False
        decision = engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert decision.approved

    def test_kill_switch_persists_across_restart(self, tmp_path):
        engine1 = _engine(tmp_path)
        engine1.activate_kill_switch("persisted halt")
        audit_log2 = AuditLog(tmp_path / "audit")
        engine2 = RiskEngine(engine1.config, tmp_path / "risk_state.json", audit_log2)
        assert engine2.state.kill_switch is True
        assert engine2.state.kill_switch_reason == "persisted halt"

    def test_connectivity_loss_triggers_kill_switch(self, tmp_path):
        engine = _engine(tmp_path, max_connectivity_gap_seconds=60)
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        engine.check_connectivity(is_connected=True, now=t0)
        t1 = datetime(2026, 1, 1, 12, 2, 0, tzinfo=timezone.utc)  # 120s later
        engine.check_connectivity(is_connected=False, now=t1)
        assert engine.state.kill_switch is True

    def test_connectivity_brief_gap_does_not_trigger(self, tmp_path):
        engine = _engine(tmp_path, max_connectivity_gap_seconds=60)
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        engine.check_connectivity(is_connected=True, now=t0)
        t1 = datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc)  # 30s later
        engine.check_connectivity(is_connected=False, now=t1)
        assert engine.state.kill_switch is False


class TestStopLossValidation:
    def test_no_stop_loss_rejected(self, tmp_path):
        engine = _engine(tmp_path)
        proposal = _proposal()
        proposal.stop_price = None
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_NO_STOP_LOSS_DEFINED

    def test_zero_reference_price_rejected_with_invalid_reference_price_not_no_stop_loss(self, tmp_path):
        """A MARKET proposal (entry_price=None) falls back to reference_price.
        A non-positive reference_price (bad feed, data glitch) must be
        rejected under its own reason, not mislabeled as a missing stop —
        the stop IS defined here; the entry/reference price is what's
        invalid. This also guards the division in stop_distance_pct just
        below, which would ZeroDivisionError on entry_price == 0."""
        engine = _engine(tmp_path)
        proposal = _proposal(entry_price=None)
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("0"))
        assert not decision.approved
        assert decision.reason == REASON_INVALID_REFERENCE_PRICE

    def test_negative_reference_price_rejected_with_invalid_reference_price(self, tmp_path):
        engine = _engine(tmp_path)
        proposal = _proposal(entry_price=None)
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("-100"))
        assert not decision.approved
        assert decision.reason == REASON_INVALID_REFERENCE_PRICE

    def test_non_positive_entry_price_on_the_proposal_itself_rejected(self, tmp_path):
        """A LIMIT-style proposal carrying its own non-positive entry_price
        (not falling back to reference_price) must be caught the same way."""
        engine = _engine(tmp_path)
        proposal = _proposal(entry_price=Decimal("0"))
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_INVALID_REFERENCE_PRICE

    def test_stop_too_tight_rejected(self, tmp_path):
        engine = _engine(tmp_path, min_stop_distance_pct=0.5)
        # Stop distance of 0.1% is below the 0.5% minimum
        proposal = _proposal(entry_price=Decimal("50000"), stop_price=Decimal("49950"))
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_STOP_TOO_TIGHT

    def test_stop_exactly_at_minimum_is_rejected(self, tmp_path):
        """Boundary: spec says '> minimum_viable_distance', so exactly-equal is rejected."""
        engine = _engine(tmp_path, min_stop_distance_pct=2.0)
        proposal = _proposal(entry_price=Decimal("50000"), stop_price=Decimal("49000"))  # exactly 2%
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_STOP_TOO_TIGHT

    def test_stop_just_above_minimum_passes(self, tmp_path):
        engine = _loose_engine(tmp_path, min_stop_distance_pct=2.0)
        proposal = _proposal(entry_price=Decimal("50000"), stop_price=Decimal("48990"))  # 2.02%
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert decision.approved


class TestPositionSizing:
    def test_zero_equity_rejected(self, tmp_path):
        engine = _engine(tmp_path)
        decision = engine.validate_order(_proposal(), equity=Decimal("0"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_POSITION_SIZE_ZERO

    def test_oversized_position_capped_and_rejected(self, tmp_path):
        """High risk_pct + tight-but-valid stop -> position value exceeds max_position_size_pct cap."""
        engine = _engine(tmp_path, max_risk_per_trade_pct=50.0, max_position_size_pct=5.0,
                          min_stop_distance_pct=0.5)
        proposal = _proposal(entry_price=Decimal("50000"), stop_price=Decimal("49500"))  # 1% stop
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_MAX_POSITION_SIZE_EXCEEDED

    def test_sizing_matches_fixed_fractional_formula(self, tmp_path):
        engine = _loose_engine(tmp_path, max_risk_per_trade_pct=1.0, include_fees_in_risk_calc=True,
                                taker_fee_rate=0.001)
        equity = Decimal("10000")
        entry = Decimal("50000")
        stop = Decimal("49000")  # 2% stop distance
        decision = engine.validate_order(_proposal(entry_price=entry, stop_price=stop),
                                          equity=equity, reference_price=entry)
        assert decision.approved
        risk_amount = equity * Decimal("1.0") / 100
        stop_distance_pct = abs(entry - stop) / entry
        effective_stop_distance = stop_distance_pct + 2 * Decimal("0.001")
        expected_qty = risk_amount / (entry * effective_stop_distance)
        expected_qty = expected_qty.quantize(Decimal("0.00000001"))
        assert abs(decision.quantity - expected_qty) < Decimal("0.0001")


class TestPositionAndExposureLimits:
    def test_max_open_positions_reached(self, tmp_path):
        engine = _engine(tmp_path, max_open_positions=2, max_total_exposure_pct=100.0,
                          max_correlated_exposure_pct=100.0, max_position_size_pct=100.0)
        engine.register_position_opened("p1", "BTCUSDT", Decimal("100"))
        engine.register_position_opened("p2", "ETHUSDT", Decimal("100"))
        decision = engine.validate_order(_proposal(symbol="BNBUSDT"), equity=Decimal("10000"),
                                          reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_MAX_POSITIONS_REACHED

    def test_daily_trade_limit_reached(self, tmp_path):
        engine = _loose_engine(tmp_path, max_trades_per_day=2, max_open_positions=100)
        day1 = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        # Roll the trading day first — register_position_opened doesn't call
        # _maybe_roll_day itself, so without this the first validate_order
        # call below would roll the day and reset daily_trade_count to 0.
        engine.validate_order(_proposal(symbol="INIT"), equity=Decimal("10000"),
                               reference_price=Decimal("50000"), now=day1)
        engine.register_position_opened("p1", "BTCUSDT", Decimal("100"))
        engine.register_position_closed("p1", Decimal("10"))
        engine.register_position_opened("p2", "ETHUSDT", Decimal("100"))
        engine.register_position_closed("p2", Decimal("-5"))
        # Both positions closed (slots free), but 2 trades already opened today
        decision = engine.validate_order(_proposal(symbol="BNBUSDT"), equity=Decimal("10000"),
                                          reference_price=Decimal("50000"), now=day1)
        assert not decision.approved
        assert decision.reason == REASON_DAILY_TRADE_LIMIT_REACHED

    def test_total_exposure_limit_exceeded(self, tmp_path):
        engine = _engine(tmp_path, max_total_exposure_pct=1.0, max_open_positions=100,
                          max_correlated_exposure_pct=100.0, max_position_size_pct=100.0,
                          max_daily_turnover_pct=1000.0)
        # Pre-existing exposure already consumes the 1% budget (equity=10000 -> budget=100)
        engine.register_position_opened("p1", "ETHUSDT", Decimal("95"))
        decision = engine.validate_order(_proposal(symbol="BTCUSDT", entry_price=Decimal("50000"),
                                                     stop_price=Decimal("49000")),
                                          equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_EXPOSURE_LIMIT_EXCEEDED

    def test_correlated_exposure_limit_exceeded(self, tmp_path):
        """Same-symbol exposure limited by max_correlated_exposure_pct even though
        max_total_exposure_pct has plenty of room left."""
        engine = _engine(tmp_path, max_total_exposure_pct=50.0, max_correlated_exposure_pct=1.0,
                          max_open_positions=100, max_position_size_pct=100.0,
                          max_daily_turnover_pct=1000.0)
        engine.register_position_opened("p1", "BTCUSDT", Decimal("95"))  # consumes ~1% correlated budget
        decision = engine.validate_order(_proposal(symbol="BTCUSDT", entry_price=Decimal("50000"),
                                                     stop_price=Decimal("49000")),
                                          equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_CORRELATED_EXPOSURE_EXCEEDED

    def test_different_symbol_not_blocked_by_correlated_limit(self, tmp_path):
        # max_correlated_exposure_pct loose enough that a single fresh trade's
        # own position_value doesn't trip it on its own — isolates the "this
        # symbol has no prior exposure" behavior from the sizing/cap tension.
        engine = _loose_engine(tmp_path, max_correlated_exposure_pct=90.0)
        engine.register_position_opened("p1", "BTCUSDT", Decimal("95"))
        decision = engine.validate_order(_proposal(symbol="ETHUSDT", entry_price=Decimal("3000"),
                                                     stop_price=Decimal("2940")),
                                          equity=Decimal("10000"), reference_price=Decimal("3000"))
        # ETHUSDT has no prior correlated exposure, should not be blocked by that check
        assert decision.reason != REASON_CORRELATED_EXPOSURE_EXCEEDED


class TestDailyLossLimit:
    def test_daily_loss_limit_halts_trading(self, tmp_path):
        engine = _engine(tmp_path, daily_loss_limit_pct=2.0)
        day1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        # First call establishes equity_at_day_start = 10000
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)

        day1_later = datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
        # Equity drops 3% intraday -> daily loss limit breached
        decision = engine.validate_order(_proposal(), equity=Decimal("9700"),
                                          reference_price=Decimal("50000"), now=day1_later)
        assert not decision.approved
        assert decision.reason == REASON_DAILY_LOSS_LIMIT_REACHED

    def test_daily_loss_resets_next_day(self, tmp_path):
        engine = _loose_engine(tmp_path, daily_loss_limit_pct=2.0)
        day1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)
        day1_later = datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("9700"), reference_price=Decimal("50000"), now=day1_later)

        day2 = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
        decision = engine.validate_order(_proposal(), equity=Decimal("9700"),
                                          reference_price=Decimal("50000"), now=day2)
        assert decision.approved


class TestDrawdownControls:
    def test_drawdown_pause_blocks_new_orders(self, tmp_path):
        engine = _engine(tmp_path, drawdown_pause_pct=8.0, drawdown_halt_pct=15.0)
        day1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)

        day2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
        # 10% drawdown from peak of 10000 -> >= 8% pause threshold, < 15% halt threshold
        decision = engine.validate_order(_proposal(), equity=Decimal("9000"),
                                          reference_price=Decimal("50000"), now=day2)
        assert not decision.approved
        assert decision.reason == REASON_DRAWDOWN_PAUSE_ACTIVE

    def test_drawdown_halt_activates_kill_switch(self, tmp_path):
        engine = _engine(tmp_path, drawdown_pause_pct=8.0, drawdown_halt_pct=15.0)
        day1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)

        day2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
        # 20% drawdown -> >= 15% halt threshold -> kill switch activates
        decision = engine.validate_order(_proposal(), equity=Decimal("8000"),
                                          reference_price=Decimal("50000"), now=day2)
        assert not decision.approved
        assert decision.reason == REASON_KILL_SWITCH_ACTIVE
        assert engine.state.kill_switch is True

    def test_drawdown_recovery_unpauses(self, tmp_path):
        engine = _loose_engine(tmp_path, drawdown_pause_pct=8.0, drawdown_halt_pct=15.0)
        day1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)
        day2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("9000"), reference_price=Decimal("50000"), now=day2)
        assert engine.state.drawdown_paused is True

        day3 = datetime(2026, 1, 3, tzinfo=timezone.utc)
        decision = engine.validate_order(_proposal(), equity=Decimal("9999"),
                                          reference_price=Decimal("50000"), now=day3)
        assert engine.state.drawdown_paused is False
        assert decision.approved


class TestStopPriceSanity:
    """Real bugs found by GPT Work's independent review: Step 5's
    abs(entry - stop) treated direction as irrelevant, so a non-positive
    stop or a stop on the wrong side of entry passed as long as its
    absolute distance wasn't 'too tight'."""

    def test_stop_above_entry_rejected(self, tmp_path):
        from trading_intelligence.risk.engine import REASON_INVALID_STOP_DIRECTION
        engine = _loose_engine(tmp_path)
        proposal = _proposal(entry_price=Decimal("100"), stop_price=Decimal("120"))
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("100"))
        assert not decision.approved
        assert decision.reason == REASON_INVALID_STOP_DIRECTION

    def test_stop_equal_to_entry_rejected(self, tmp_path):
        from trading_intelligence.risk.engine import REASON_INVALID_STOP_DIRECTION
        engine = _loose_engine(tmp_path)
        proposal = _proposal(entry_price=Decimal("100"), stop_price=Decimal("100"))
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("100"))
        assert not decision.approved
        assert decision.reason == REASON_INVALID_STOP_DIRECTION

    def test_negative_stop_rejected(self, tmp_path):
        from trading_intelligence.risk.engine import REASON_INVALID_STOP_PRICE
        engine = _loose_engine(tmp_path)
        proposal = _proposal(entry_price=Decimal("100"), stop_price=Decimal("-1"))
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("100"))
        assert not decision.approved
        assert decision.reason == REASON_INVALID_STOP_PRICE

    def test_zero_stop_rejected(self, tmp_path):
        from trading_intelligence.risk.engine import REASON_INVALID_STOP_PRICE
        engine = _loose_engine(tmp_path)
        proposal = _proposal(entry_price=Decimal("100"), stop_price=Decimal("0"))
        decision = engine.validate_order(proposal, equity=Decimal("10000"), reference_price=Decimal("100"))
        assert not decision.approved
        assert decision.reason == REASON_INVALID_STOP_PRICE

    def test_valid_long_stop_below_entry_still_passes(self, tmp_path):
        engine = _loose_engine(tmp_path)
        decision = engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert decision.approved


class TestDailyTurnoverLimit:
    """Real bug found by GPT Work's independent review: max_daily_turnover_pct
    existed in RiskConfig and daily_turnover was tracked on every opened
    position, but validate_order() never actually checked one against the
    other — a configured hard limit that silently enforced nothing."""

    def test_configured_turnover_ceiling_is_a_hard_limit(self, tmp_path):
        from trading_intelligence.risk.engine import REASON_DAILY_TURNOVER_LIMIT_EXCEEDED
        # Equity 1000, ceiling 1% = 10. Default risk/stop sizing for this
        # proposal produces ~19.92 notional — comfortably over the ceiling.
        engine = _engine(tmp_path, max_daily_turnover_pct=1.0, max_position_size_pct=100.0,
                          max_total_exposure_pct=100.0, max_correlated_exposure_pct=100.0)
        decision = engine.validate_order(_proposal(), equity=Decimal("1000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_DAILY_TURNOVER_LIMIT_EXCEEDED

    def test_turnover_accumulates_across_positions_opened_same_day(self, tmp_path):
        from trading_intelligence.risk.engine import REASON_DAILY_TURNOVER_LIMIT_EXCEEDED
        engine = _engine(tmp_path, max_daily_turnover_pct=1.0, max_position_size_pct=100.0,
                          max_total_exposure_pct=100.0, max_correlated_exposure_pct=100.0,
                          max_open_positions=100)
        engine.register_position_opened("p1", "ETHUSDT", Decimal("9.9"))  # consumes most of the 1% budget
        decision = engine.validate_order(_proposal(), equity=Decimal("1000"), reference_price=Decimal("50000"))
        assert not decision.approved
        assert decision.reason == REASON_DAILY_TURNOVER_LIMIT_EXCEEDED

    def test_under_ceiling_still_approves(self, tmp_path):
        engine = _loose_engine(tmp_path)  # max_daily_turnover_pct loosened to 1000.0
        decision = engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert decision.approved


class _RecordingSink:
    def __init__(self):
        self.alerts: list[tuple[str, str]] = []

    def send(self, severity, event, details):
        self.alerts.append((severity, event))


class TestObserveEquity:
    """Real gap: drawdown and the daily loss limit were only evaluated inside
    validate_order(), i.e. only when a NEW signal arrived. A position bleeding
    through a crash with no fresh signals never tripped the halt."""

    def _engine(self, tmp_path, **kw):
        sink = _RecordingSink()
        config = RiskConfig(**kw)
        engine = RiskEngine(config, tmp_path / "risk_state.json", AuditLog(tmp_path / "audit"), sink)
        return engine, sink

    def test_drawdown_halt_trips_without_any_proposal(self, tmp_path):
        engine, _ = self._engine(tmp_path)
        engine.observe_equity(Decimal("10000"), now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        engine.observe_equity(Decimal("8000"), now=datetime(2026, 1, 2, tzinfo=timezone.utc))
        assert engine.state.kill_switch is True
        assert "Drawdown halt" in engine.state.kill_switch_reason
        decision = engine.validate_order(_proposal(), equity=Decimal("8000"),
                                          reference_price=Decimal("50000"),
                                          now=datetime(2026, 1, 3, tzinfo=timezone.utc))
        assert decision.reason == REASON_KILL_SWITCH_ACTIVE

    def test_transient_drawdown_that_recovers_before_the_next_signal_is_still_seen(self, tmp_path):
        """Seen only via observation: by the time a signal arrives equity is back
        near the peak, so validate_order alone would have approved it."""
        engine, _ = self._engine(tmp_path)
        engine.observe_equity(Decimal("10000"), now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        engine.observe_equity(Decimal("8400"), now=datetime(2026, 1, 2, tzinfo=timezone.utc))
        decision = engine.validate_order(_proposal(), equity=Decimal("10000"),
                                          reference_price=Decimal("50000"),
                                          now=datetime(2026, 1, 3, tzinfo=timezone.utc))
        assert not decision.approved
        assert decision.reason == REASON_KILL_SWITCH_ACTIVE, "a halt must not self-clear on recovery"

    def test_pause_tier_follows_observation_and_clears_on_recovery(self, tmp_path):
        engine, _ = self._engine(tmp_path)
        engine.observe_equity(Decimal("10000"), now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        engine.observe_equity(Decimal("9000"), now=datetime(2026, 1, 2, tzinfo=timezone.utc))
        assert engine.state.drawdown_paused is True and engine.state.kill_switch is False
        engine.observe_equity(Decimal("9999"), now=datetime(2026, 1, 3, tzinfo=timezone.utc))
        assert engine.state.drawdown_paused is False

    def test_daily_loss_limit_trips_without_any_proposal(self, tmp_path):
        engine, _ = self._engine(tmp_path, daily_loss_limit_pct=2.0)
        day = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        engine.observe_equity(Decimal("10000"), now=day)
        engine.observe_equity(Decimal("9700"), now=datetime(2026, 1, 1, 15, tzinfo=timezone.utc))
        assert engine.state.trading_day_halted is True
        # ...and it resets on the next trading day, as before.
        engine.observe_equity(Decimal("9700"), now=datetime(2026, 1, 2, 10, tzinfo=timezone.utc))
        assert engine.state.trading_day_halted is False

    def test_halt_alert_and_audit_fire_once_not_on_every_bar(self, tmp_path):
        engine, sink = self._engine(tmp_path)
        engine.observe_equity(Decimal("10000"), now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        for hour in range(10):
            engine.observe_equity(Decimal("7000"), now=datetime(2026, 1, 2, hour, tzinfo=timezone.utc))
        halts = [a for a in sink.alerts if a[1] == "DRAWDOWN_HALT_TRIGGERED"]
        assert len(halts) == 1
        audited = [e for e in engine.audit_log.read_all() if e["event"] == "DRAWDOWN_HALT_TRIGGERED"]
        assert len(audited) == 1

    def test_equity_history_stays_one_entry_per_day(self, tmp_path):
        engine, _ = self._engine(tmp_path)
        for hour in range(20):
            engine.observe_equity(Decimal(10000 + hour), now=datetime(2026, 1, 1, hour, tzinfo=timezone.utc))
        assert len(engine.state.equity_history) == 1
        assert Decimal(engine.state.equity_history[0][1]) == Decimal("10019"), "keeps the day's peak"

    def test_peak_is_preserved_when_equity_falls_within_the_same_day(self, tmp_path):
        engine, _ = self._engine(tmp_path, drawdown_pause_pct=8.0, drawdown_halt_pct=15.0)
        engine.observe_equity(Decimal("10000"), now=datetime(2026, 1, 1, 9, tzinfo=timezone.utc))
        engine.observe_equity(Decimal("9100"), now=datetime(2026, 1, 1, 17, tzinfo=timezone.utc))
        assert engine.state.drawdown_paused is True, "9% below the day's own peak must register"


class TestPositionReservations:
    """An entry is approved on one bar and fills on the next. Reservations make
    the approval count against every limit immediately."""

    def _engine(self, tmp_path, **kw):
        return _loose_engine(tmp_path, **kw)

    def test_reservation_counts_toward_open_positions_and_exposure(self, tmp_path):
        engine = self._engine(tmp_path, max_open_positions=1)
        engine.reserve_position("r1", "ETHUSDT", Decimal("500"))
        assert engine.open_position_count == 1
        assert engine.total_open_exposure == Decimal("500")
        decision = engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"))
        assert decision.reason == REASON_MAX_POSITIONS_REACHED

    def test_reservation_counts_toward_correlated_exposure(self, tmp_path):
        engine = self._engine(tmp_path, max_correlated_exposure_pct=1.0, max_open_positions=100)
        engine.reserve_position("r1", "BTCUSDT", Decimal("95"))
        decision = engine.validate_order(_proposal(symbol="BTCUSDT"), equity=Decimal("10000"),
                                          reference_price=Decimal("50000"))
        assert decision.reason == REASON_CORRELATED_EXPOSURE_EXCEEDED

    def test_confirm_swaps_reservation_for_the_real_position_and_trues_up_turnover(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.reserve_position("r1", "BTCUSDT", Decimal("1000"))
        engine.confirm_reservation("r1", "pos-1", "BTCUSDT", Decimal("1100"))
        assert engine.reservation_ids() == []
        assert list(engine.state.open_positions) == ["pos-1"]
        assert engine.state.open_positions["pos-1"]["notional_value"] == "1100"
        assert Decimal(engine.state.daily_turnover) == Decimal("1100")
        assert engine.state.daily_trade_count == 1, "confirming must not double-count the trade"

    def test_release_gives_back_slot_exposure_count_and_turnover(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.reserve_position("r1", "BTCUSDT", Decimal("1000"))
        assert engine.release_reservation("r1") is True
        assert engine.open_position_count == 0
        assert engine.total_open_exposure == Decimal("0")
        assert engine.state.daily_trade_count == 0
        assert Decimal(engine.state.daily_turnover) == Decimal("0")

    def test_release_of_unknown_or_real_position_is_a_noop(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.register_position_opened("pos-1", "BTCUSDT", Decimal("100"))
        assert engine.release_reservation("missing") is False
        assert engine.release_reservation("pos-1") is False, "a real position is not a reservation"
        assert engine.open_position_count == 1

    def test_reservations_survive_restart(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.reserve_position("r1", "BTCUSDT", Decimal("250"))
        again = RiskEngine(engine.config, tmp_path / "risk_state.json", AuditLog(tmp_path / "audit"))
        assert again.reservation_ids() == ["r1"]
        assert again.open_position_count == 1


DAY1 = datetime(2026, 10, 1, 23, 55, tzinfo=timezone.utc)
DAY2 = DAY1 + timedelta(minutes=5)  # 00:00 the next day
EQUITY = Decimal("10000")


class TestReservationDayBoundary:
    """The daily counters reset at day roll. A reservation made on an earlier
    day must neither debit (release) nor under-charge (confirm) the new day.
    Found by GPT Work's independent review of the runner."""

    def _engine(self, tmp_path):
        return _loose_engine(tmp_path)

    def _reserve_yesterday_and_today(self, engine):
        engine.advance_clock(EQUITY, DAY1)
        engine.reserve_position("yesterday", "BTCUSDT", Decimal("100"))
        engine.advance_clock(EQUITY, DAY2)
        engine.reserve_position("today", "ETHUSDT", Decimal("200"))
        assert (engine.state.daily_trade_count, Decimal(engine.state.daily_turnover)) == (1, Decimal("200"))

    def test_releasing_an_old_day_reservation_leaves_todays_budget_alone(self, tmp_path):
        engine = self._engine(tmp_path)
        self._reserve_yesterday_and_today(engine)
        assert engine.release_reservation("yesterday") is True
        assert (engine.state.daily_trade_count, Decimal(engine.state.daily_turnover)) == (1, Decimal("200"))
        assert engine.reservation_ids() == ["today"], "its slot and exposure are still freed"

    def test_confirming_an_old_day_reservation_charges_the_whole_fill_to_today(self, tmp_path):
        engine = self._engine(tmp_path)
        self._reserve_yesterday_and_today(engine)
        engine.confirm_reservation("yesterday", "pos-1", "BTCUSDT", Decimal("120"))
        assert (engine.state.daily_trade_count, Decimal(engine.state.daily_turnover)) == (2, Decimal("320"))

    def test_the_day_tag_survives_a_restart(self, tmp_path):
        engine = self._engine(tmp_path)
        self._reserve_yesterday_and_today(engine)
        again = RiskEngine(engine.config, tmp_path / "risk_state.json", AuditLog(tmp_path / "audit"))
        assert again.release_reservation("yesterday") is True
        assert (again.state.daily_trade_count, Decimal(again.state.daily_turnover)) == (1, Decimal("200"))

    def test_a_reservation_persisted_without_a_day_is_treated_as_same_day(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.advance_clock(EQUITY, DAY1)
        engine.reserve_position("legacy", "BTCUSDT", Decimal("100"))
        del engine.state.open_positions["legacy"]["day"]
        assert engine.release_reservation("legacy") is True
        assert (engine.state.daily_trade_count, Decimal(engine.state.daily_turnover)) == (0, Decimal("0"))

    def test_same_day_release_still_gives_back_its_own_charge(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.advance_clock(EQUITY, DAY1)
        engine.reserve_position("one", "BTCUSDT", Decimal("100"))
        engine.reserve_position("two", "ETHUSDT", Decimal("200"))
        engine.release_reservation("one")
        assert (engine.state.daily_trade_count, Decimal(engine.state.daily_turnover)) == (1, Decimal("200"))


class TestAdvanceClock:
    def test_rolls_the_day_with_the_pre_bar_equity_as_day_start(self, tmp_path):
        engine = _loose_engine(tmp_path)
        engine.advance_clock(EQUITY, DAY1)
        engine.reserve_position("r1", "BTCUSDT", Decimal("100"))
        engine.advance_clock(Decimal("9900"), DAY2)
        assert engine.state.current_day == "2026-10-02"
        assert engine.state.equity_at_day_start == "9900"
        assert (engine.state.daily_trade_count, engine.state.daily_turnover) == (0, "0")

    def test_is_a_noop_within_the_same_day(self, tmp_path):
        engine = _loose_engine(tmp_path)
        engine.advance_clock(EQUITY, DAY1)
        engine.reserve_position("r1", "BTCUSDT", Decimal("100"))
        engine.advance_clock(Decimal("5000"), DAY1 - timedelta(minutes=1))
        assert engine.state.equity_at_day_start == "10000"
        assert engine.state.daily_trade_count == 1

    def test_a_one_bar_loss_trips_the_daily_limit_on_one_bar_per_day_data(self, tmp_path):
        """With one bar per day the day used to start at the AFTER-bar equity,
        so the daily loss limit could never see a single-bar loss."""
        engine = _loose_engine(tmp_path, daily_loss_limit_pct=2.0)
        engine.advance_clock(EQUITY, DAY1)
        engine.observe_equity(EQUITY, now=DAY1)
        engine.advance_clock(EQUITY, DAY2)  # the bar opens: day starts at the last mark
        engine.observe_equity(Decimal("9700"), now=DAY2)  # the bar closes 3% down
        assert engine.state.trading_day_halted is True
        assert engine.entry_block_reason() == REASON_DAILY_LOSS_LIMIT_REACHED


class TestEntryBlockReason:
    def test_none_when_nothing_is_halted(self, tmp_path):
        assert _loose_engine(tmp_path).entry_block_reason() is None

    def test_kill_switch(self, tmp_path):
        engine = _loose_engine(tmp_path)
        engine.activate_kill_switch("test")
        assert engine.entry_block_reason() == REASON_KILL_SWITCH_ACTIVE

    def test_daily_loss_halt(self, tmp_path):
        engine = _loose_engine(tmp_path)
        engine.state.trading_day_halted = True
        assert engine.entry_block_reason() == REASON_DAILY_LOSS_LIMIT_REACHED

    def test_drawdown_pause(self, tmp_path):
        engine = _loose_engine(tmp_path)
        engine.state.drawdown_paused = True
        assert engine.entry_block_reason() == REASON_DRAWDOWN_PAUSE_ACTIVE

    def test_kill_switch_wins_over_the_other_gates(self, tmp_path):
        engine = _loose_engine(tmp_path)
        engine.activate_kill_switch("test")
        engine.state.trading_day_halted = True
        engine.state.drawdown_paused = True
        assert engine.entry_block_reason() == REASON_KILL_SWITCH_ACTIVE


class TestFillValidation:
    """An entry is approved against the last close but fills at the next open.
    validate_fill re-checks the approval against the price it really fills at."""

    STOP = Decimal("95")
    QTY = Decimal("19.23076923")  # what 1% risk sizes to for entry 100 / stop 95 incl. fees

    def _engine(self, tmp_path, **kw):
        return _engine(tmp_path, max_position_size_pct=25.0, **kw)

    def test_sizing_assumption_matches_the_engine(self, tmp_path):
        qty, _ = self._engine(tmp_path)._size_position(EQUITY, Decimal("100"), self.STOP)
        assert qty == self.QTY

    def test_fill_at_the_reference_price_passes(self, tmp_path):
        engine = self._engine(tmp_path)
        assert engine.validate_fill(self.QTY, self.STOP, Decimal("100"), EQUITY) is None

    def test_ordinary_slippage_passes_with_the_default_tolerance(self, tmp_path):
        engine = self._engine(tmp_path)
        assert engine.validate_fill(self.QTY, self.STOP, Decimal("100.5"), EQUITY) is None

    def test_a_gap_that_multiplies_the_risk_is_vetoed(self, tmp_path):
        engine = self._engine(tmp_path)
        reason = engine.validate_fill(self.QTY, self.STOP, Decimal("110"), EQUITY)
        assert reason == REASON_FILL_RISK_EXCEEDS_BUDGET

    def test_the_overshoot_tolerance_is_exact_at_its_boundary(self, tmp_path):
        # loss at stop = qty*(fill-95) + 2*0.001*qty*fill ; budget = 100.
        zero = self._engine(tmp_path, max_fill_risk_overshoot_pct=0.0)
        assert zero.validate_fill(self.QTY, self.STOP, Decimal("100"), EQUITY) is None
        assert zero.validate_fill(self.QTY, self.STOP, Decimal("100.02"), EQUITY) == REASON_FILL_RISK_EXCEEDS_BUDGET
        loose = self._engine(tmp_path, max_fill_risk_overshoot_pct=25.0)
        assert loose.validate_fill(self.QTY, self.STOP, Decimal("100.02"), EQUITY) is None
        assert loose.validate_fill(self.QTY, self.STOP, Decimal("101.2"), EQUITY) is None
        assert loose.validate_fill(self.QTY, self.STOP, Decimal("101.3"), EQUITY) == REASON_FILL_RISK_EXCEEDS_BUDGET

    def test_a_fill_that_pushes_the_position_over_its_cap_is_vetoed(self, tmp_path):
        engine = _engine(tmp_path, max_position_size_pct=5.0)  # cap 500 on 10000
        qty, stop = Decimal("4.9"), Decimal("80")  # far stop: risk is not what trips
        assert engine.validate_fill(qty, stop, Decimal("100"), EQUITY) is None
        assert engine.validate_fill(qty, stop, Decimal("103"), EQUITY) == REASON_FILL_EXCEEDS_POSITION_CAP

    def test_a_fill_at_or_below_the_stop_is_vetoed(self, tmp_path):
        engine = self._engine(tmp_path)
        assert engine.validate_fill(self.QTY, self.STOP, Decimal("95"), EQUITY) == REASON_FILL_AT_OR_BELOW_STOP
        assert engine.validate_fill(self.QTY, self.STOP, Decimal("90"), EQUITY) == REASON_FILL_AT_OR_BELOW_STOP
        assert engine.validate_fill(self.QTY, self.STOP, Decimal("95.01"), EQUITY) is None

    def test_a_veto_is_audited_and_a_pass_is_not(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.validate_fill(self.QTY, self.STOP, Decimal("100"), EQUITY)
        engine.validate_fill(self.QTY, self.STOP, Decimal("110"), EQUITY)
        vetoes = [r for r in engine.audit_log.read_all() if r.get("event") == "FILL_VETOED"]
        assert [v["reason"] for v in vetoes] == [REASON_FILL_RISK_EXCEEDS_BUDGET]

    def test_negative_overshoot_is_refused(self):
        with pytest.raises(ValueError, match="max_fill_risk_overshoot_pct"):
            RiskConfig(max_fill_risk_overshoot_pct=-1.0)
