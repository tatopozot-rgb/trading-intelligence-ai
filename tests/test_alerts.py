"""
Tests for the alert sink abstraction and its wiring into RiskEngine.
Per docs/DEPLOYMENT_RUNBOOK.md: before unattended LIVE operation, a real
notification channel is required here — these tests prove the wiring is
correct so swapping LoggingAlertSink for a real one is a safe, isolated change.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trading_intelligence.monitoring.alerts import (
    CompositeAlertSink,
    LoggingAlertSink,
    NullAlertSink,
)
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.risk.models import RiskConfig
from trading_intelligence.strategy.models import TradeProposal


class RecordingAlertSink:
    def __init__(self):
        self.alerts: list[tuple[str, str, dict]] = []

    def send(self, severity, event, details):
        self.alerts.append((severity, event, details))


class FailingAlertSink:
    def send(self, severity, event, details):
        raise RuntimeError("simulated sink failure")


def _proposal(entry_price=Decimal("50000"), stop_price=Decimal("49000")) -> TradeProposal:
    return TradeProposal(
        strategy_id="test", symbol="BTCUSDT", side="BUY", entry_type="MARKET",
        stop_price=stop_price, timeframe="1h", rationale="test", signal_strength=1.0,
        timestamp="2026-01-01T00:00:00Z", entry_price=entry_price,
    )


def _engine(tmp_path: Path, alert_sink=None, **config_overrides) -> RiskEngine:
    config = RiskConfig(**{
        "max_position_size_pct": 100.0, "max_total_exposure_pct": 100.0,
        "max_correlated_exposure_pct": 100.0, **config_overrides,
    })
    audit_log = AuditLog(tmp_path / "audit")
    return RiskEngine(config, tmp_path / "risk_state.json", audit_log, alert_sink=alert_sink)


class TestAlertSinkDefault:
    def test_defaults_to_logging_sink_when_none_given(self, tmp_path):
        engine = _engine(tmp_path)
        assert isinstance(engine.alert_sink, LoggingAlertSink)

    def test_logging_sink_does_not_raise(self, caplog):
        sink = LoggingAlertSink()
        sink.send("CRITICAL", "TEST_EVENT", {"x": 1})  # should not raise
        assert "TEST_EVENT" in caplog.text


class TestKillSwitchAlerts:
    def test_manual_activation_alerts_critical(self, tmp_path):
        sink = RecordingAlertSink()
        engine = _engine(tmp_path, alert_sink=sink)
        engine.activate_kill_switch("manual test")
        assert ("CRITICAL", "KILL_SWITCH_ACTIVATED", {"reason": "manual test"}) in sink.alerts

    def test_clearing_does_not_alert(self, tmp_path):
        sink = RecordingAlertSink()
        engine = _engine(tmp_path, alert_sink=sink)
        engine.activate_kill_switch("test")
        sink.alerts.clear()
        engine.clear_kill_switch(operator_confirmation=True)
        assert sink.alerts == []

    def test_connectivity_loss_alerts_critical(self, tmp_path):
        sink = RecordingAlertSink()
        engine = _engine(tmp_path, alert_sink=sink, max_connectivity_gap_seconds=60)
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        engine.check_connectivity(is_connected=True, now=t0)
        t1 = datetime(2026, 1, 1, 12, 2, 0, tzinfo=timezone.utc)
        engine.check_connectivity(is_connected=False, now=t1)
        events = [a[1] for a in sink.alerts]
        assert "KILL_SWITCH_ACTIVATED" in events


class TestDrawdownAlerts:
    def test_drawdown_pause_alerts_warning(self, tmp_path):
        sink = RecordingAlertSink()
        engine = _engine(tmp_path, alert_sink=sink, drawdown_pause_pct=8.0, drawdown_halt_pct=15.0)
        day1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)
        day2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("9000"), reference_price=Decimal("50000"), now=day2)
        warnings = [a for a in sink.alerts if a[1] == "DRAWDOWN_PAUSE_TRIGGERED"]
        assert len(warnings) == 1
        assert warnings[0][0] == "WARNING"

    def test_drawdown_halt_alerts_critical_and_kill_switch(self, tmp_path):
        sink = RecordingAlertSink()
        engine = _engine(tmp_path, alert_sink=sink, drawdown_pause_pct=8.0, drawdown_halt_pct=15.0)
        day1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)
        day2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("8000"), reference_price=Decimal("50000"), now=day2)
        events = [a[1] for a in sink.alerts]
        assert "DRAWDOWN_HALT_TRIGGERED" in events
        assert "KILL_SWITCH_ACTIVATED" in events  # halt also activates the kill switch

    def test_drawdown_pause_does_not_repeat_alert_every_call(self, tmp_path):
        """Once paused, staying paused on subsequent calls must not re-alert."""
        sink = RecordingAlertSink()
        engine = _engine(tmp_path, alert_sink=sink, drawdown_pause_pct=8.0, drawdown_halt_pct=50.0)
        day1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)
        day2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("9000"), reference_price=Decimal("50000"), now=day2)
        day3 = datetime(2026, 1, 3, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("9000"), reference_price=Decimal("50000"), now=day3)
        pause_alerts = [a for a in sink.alerts if a[1] == "DRAWDOWN_PAUSE_TRIGGERED"]
        assert len(pause_alerts) == 1


class TestDailyLossAlerts:
    def test_daily_loss_limit_alerts_warning(self, tmp_path):
        sink = RecordingAlertSink()
        engine = _engine(tmp_path, alert_sink=sink, daily_loss_limit_pct=2.0)
        day1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)
        day1_later = datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("9700"), reference_price=Decimal("50000"), now=day1_later)
        warnings = [a for a in sink.alerts if a[1] == "DAILY_LOSS_LIMIT_REACHED"]
        assert len(warnings) == 1
        assert warnings[0][0] == "WARNING"

    def test_daily_loss_does_not_repeat_alert_same_day(self, tmp_path):
        sink = RecordingAlertSink()
        engine = _engine(tmp_path, alert_sink=sink, daily_loss_limit_pct=2.0)
        day1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("10000"), reference_price=Decimal("50000"), now=day1)
        later1 = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("9700"), reference_price=Decimal("50000"), now=later1)
        later2 = datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
        engine.validate_order(_proposal(), equity=Decimal("9700"), reference_price=Decimal("50000"), now=later2)
        warnings = [a for a in sink.alerts if a[1] == "DAILY_LOSS_LIMIT_REACHED"]
        assert len(warnings) == 1


class TestCompositeAlertSink:
    def test_fans_out_to_all_sinks(self):
        recorder1, recorder2 = RecordingAlertSink(), RecordingAlertSink()
        composite = CompositeAlertSink([recorder1, recorder2])
        composite.send("CRITICAL", "EVENT", {"a": 1})
        assert recorder1.alerts == [("CRITICAL", "EVENT", {"a": 1})]
        assert recorder2.alerts == [("CRITICAL", "EVENT", {"a": 1})]

    def test_one_failing_sink_does_not_block_others(self):
        recorder = RecordingAlertSink()
        composite = CompositeAlertSink([FailingAlertSink(), recorder])
        composite.send("CRITICAL", "EVENT", {})  # should not raise
        assert recorder.alerts == [("CRITICAL", "EVENT", {})]

    def test_risk_engine_with_composite_sink(self, tmp_path):
        recorder = RecordingAlertSink()
        composite = CompositeAlertSink([LoggingAlertSink(), recorder])
        engine = _engine(tmp_path, alert_sink=composite)
        engine.activate_kill_switch("test")
        assert any(a[1] == "KILL_SWITCH_ACTIVATED" for a in recorder.alerts)


class TestNullAlertSink:
    def test_never_raises_and_records_nothing(self):
        sink = NullAlertSink()
        sink.send("CRITICAL", "ANYTHING", {"k": "v"})  # should not raise
