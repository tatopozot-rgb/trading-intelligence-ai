"""
Alert sinks for critical risk events (kill switch, drawdown halt, daily
loss limit). Default is logging-only — no external dependency, no
credentials, nothing to misconfigure. Swap in a real integration (Slack,
email, SMS) later by implementing AlertSink; RiskEngine itself never
changes.

Per docs/DEPLOYMENT_RUNBOOK.md's "Known Gaps": before unattended LIVE
operation, a real notification channel (not just logs) is required here.
"""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

Severity = str  # "WARNING" | "CRITICAL" — kept as str, not Literal, so a
# future sink can define its own severities without touching this module.


class AlertSink(Protocol):
    def send(self, severity: Severity, event: str, details: dict) -> None: ...


class LoggingAlertSink:
    """Default sink: logs at CRITICAL/WARNING. Always available, never fails
    to construct, never requires credentials."""

    def send(self, severity: Severity, event: str, details: dict) -> None:
        log_fn = logger.critical if severity == "CRITICAL" else logger.warning
        log_fn("ALERT [%s] %s: %s", severity, event, details)


class CompositeAlertSink:
    """Fan out to multiple sinks (e.g. logging + a real channel later).
    A failing sink is logged and does not prevent the others from firing —
    an alerting bug must never become a reason a kill-switch event goes
    unlogged everywhere."""

    def __init__(self, sinks: list[AlertSink]):
        self.sinks = sinks

    def send(self, severity: Severity, event: str, details: dict) -> None:
        for sink in self.sinks:
            try:
                sink.send(severity, event, details)
            except Exception:
                logger.exception("Alert sink %r failed to send %s", sink, event)


class NullAlertSink:
    """No-op sink, for tests that want to assert nothing was configured."""

    def send(self, severity: Severity, event: str, details: dict) -> None:
        pass
