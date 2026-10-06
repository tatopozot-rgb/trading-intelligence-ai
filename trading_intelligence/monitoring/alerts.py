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

import json
import logging
import urllib.request
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


class WebhookAlertSink:
    """Posts a JSON payload to a configured webhook URL — a Slack or
    Discord incoming webhook, or any generic HTTP endpoint that accepts
    JSON. Uses only the standard library (no new dependency).

    The URL is never hardcoded here; the caller supplies it (e.g. read
    from an environment variable at startup — see
    docs/DEPLOYMENT_RUNBOOK.md). A delivery failure is logged and
    swallowed, never raised: a flaky notification channel must not crash
    the caller or block the real risk decision that triggered the alert.
    """

    def __init__(
        self,
        webhook_url: str,
        timeout_seconds: float = 5.0,
        payload_format: str = "generic",
    ):
        if payload_format not in ("generic", "slack"):
            raise ValueError(f"Unknown payload_format: {payload_format!r}")
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds
        self.payload_format = payload_format

    def send(self, severity: Severity, event: str, details: dict) -> None:
        payload = self._build_payload(severity, event, details)
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds):
                pass
        except Exception:
            logger.exception(
                "WebhookAlertSink failed to deliver %s (%s) to configured webhook",
                event, severity,
            )

    def _build_payload(self, severity: Severity, event: str, details: dict) -> dict:
        if self.payload_format == "slack":
            return {"text": f"[{severity}] {event}: {details}"}
        return {"severity": severity, "event": event, "details": details}
