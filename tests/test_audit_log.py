"""
Tests for AuditLog's own behavior — it previously had no dedicated test
file, only incidental coverage via test_risk_engine.py's one
"test_approval_logs_audit_entry" (which exercises RiskEngine's call site,
not AuditLog's own rotation/format/round-trip/failure-handling contract).

Found while auditing for the same kind of gap walk_forward.py had: this
module's own docstring claimed a failure-handling behavior ("failures are
re-raised as RuntimeError after being written to stderr-equivalent") that
the code didn't actually implement — a raw OSError propagated unconverted
and unlogged. Fixed alongside these tests.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from trading_intelligence.persistence.audit_log import AuditLog


@dataclass
class _FakeRecord:
    symbol: str
    qty: Decimal


class TestAppendAndReadRoundTrip:
    def test_append_then_read_all_round_trips(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append({"event": "APPROVED", "symbol": "BTCUSDT"})
        log.append({"event": "REJECTED", "symbol": "ETHUSDT"})
        entries = log.read_all()
        assert [e["event"] for e in entries] == ["APPROVED", "REJECTED"]

    def test_append_sets_logged_at_when_missing(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append({"event": "X"})
        entry = log.read_all()[0]
        assert "logged_at" in entry
        datetime.fromisoformat(entry["logged_at"])  # must be a real ISO timestamp

    def test_append_preserves_caller_supplied_logged_at(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append({"event": "X", "logged_at": "2020-01-01T00:00:00+00:00"})
        entry = log.read_all()[0]
        assert entry["logged_at"] == "2020-01-01T00:00:00+00:00"

    def test_each_record_is_one_line(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append({"event": "A"})
        log.append({"event": "B"})
        path = log._current_file()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert all(json.loads(line) for line in lines)

    def test_read_all_returns_empty_list_when_file_missing(self, tmp_path):
        log = AuditLog(tmp_path)
        assert log.read_all() == []

    def test_read_all_for_specific_date_reads_that_file_not_today(self, tmp_path):
        log = AuditLog(tmp_path)
        (tmp_path / "audit_2020-06-15.jsonl").write_text(
            json.dumps({"event": "OLD"}) + "\n", encoding="utf-8"
        )
        log.append({"event": "TODAY"})
        assert [e["event"] for e in log.read_all(date="2020-06-15")] == ["OLD"]
        assert [e["event"] for e in log.read_all()] == ["TODAY"]

    def test_read_all_skips_blank_lines(self, tmp_path):
        log = AuditLog(tmp_path)
        path = log._current_file()
        path.write_text('{"event": "A"}\n\n{"event": "B"}\n', encoding="utf-8")
        assert [e["event"] for e in log.read_all()] == ["A", "B"]


class TestDailyRotation:
    def test_current_file_name_includes_the_date(self, tmp_path):
        log = AuditLog(tmp_path)
        path = log._current_file(now=datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc))
        assert path.name == "audit_2026-03-07.jsonl"

    def test_different_dates_produce_different_files(self, tmp_path):
        log = AuditLog(tmp_path)
        day1 = log._current_file(now=datetime(2026, 3, 7, 23, 59, tzinfo=timezone.utc))
        day2 = log._current_file(now=datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc))
        assert day1 != day2

    def test_append_rotates_to_a_new_file_on_a_new_day(self, tmp_path):
        """append() always stamps with the real current time (no inject
        point of its own), so rotation itself is exercised by patching the
        module's datetime rather than passing `now` — the one case where
        reaching into the module is the only way to test real behavior,
        not a shortcut around it."""
        log = AuditLog(tmp_path)
        with patch("trading_intelligence.persistence.audit_log.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            log.append({"event": "DAY1"})
            mock_dt.now.return_value = datetime(2026, 1, 2, tzinfo=timezone.utc)
            log.append({"event": "DAY2"})
        assert (tmp_path / "audit_2026-01-01.jsonl").exists()
        assert (tmp_path / "audit_2026-01-02.jsonl").exists()


class TestJSONEncoding:
    def test_decimal_serialized_as_string_not_float(self, tmp_path):
        """A Decimal must round-trip as an exact string, never silently
        become a lossy float through default JSON encoding."""
        log = AuditLog(tmp_path)
        log.append({"event": "X", "qty": Decimal("0.1")})
        raw_line = log._current_file().read_text(encoding="utf-8").strip()
        assert '"qty": "0.1"' in raw_line
        assert log.read_all()[0]["qty"] == "0.1"

    def test_dataclass_serialized_via_asdict(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append({"event": "X", "detail": _FakeRecord(symbol="BTCUSDT", qty=Decimal("2"))})
        entry = log.read_all()[0]
        assert entry["detail"] == {"symbol": "BTCUSDT", "qty": "2"}

    def test_keys_are_sorted_for_deterministic_diffs(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append({"zebra": 1, "alpha": 2, "event": "X"})
        raw_line = log._current_file().read_text(encoding="utf-8").strip()
        assert raw_line.index('"alpha"') < raw_line.index('"event"') < raw_line.index('"zebra"')


class TestWriteFailureHandling:
    def test_io_failure_is_logged_then_raised_as_runtime_error(self, tmp_path, caplog):
        log = AuditLog(tmp_path)
        with patch("builtins.open", side_effect=OSError("disk full")):
            with caplog.at_level(logging.CRITICAL):
                with pytest.raises(RuntimeError) as exc_info:
                    log.append({"event": "X"})
        assert isinstance(exc_info.value.__cause__, OSError)
        assert "disk full" in caplog.text

    def test_failure_is_never_silently_swallowed(self, tmp_path):
        """The docstring's own words: a write failure must never just
        vanish — it always surfaces as an exception, never a quiet no-op."""
        log = AuditLog(tmp_path)
        with patch("builtins.open", side_effect=OSError("permission denied")):
            with pytest.raises(RuntimeError, match="permission denied|AuditLog failed"):
                log.append({"event": "X"})
