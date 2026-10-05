"""
Tests for RiskEngine — every reject reason, boundary conditions, restart
persistence. Per AGENTS.md: risk engine tests are mandatory and the engine
must never be mocked in these tests.
"""
from datetime import datetime, timezone
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
                          max_correlated_exposure_pct=100.0, max_position_size_pct=100.0)
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
                          max_open_positions=100, max_position_size_pct=100.0)
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
