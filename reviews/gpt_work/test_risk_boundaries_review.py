"""Independent checks of existing research risk contracts; synthetic policy fixtures only.

python -B test_risk_boundaries_review.py <research-source-directory>
No runtime parameter is changed. No network or account is used.
"""
from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(sys.argv.pop(1)).resolve()))
from trading_intelligence.risk.engine import RiskEngine  # noqa: E402
from trading_intelligence.risk.models import RiskConfig  # noqa: E402
from trading_intelligence.monitoring.alerts import NullAlertSink  # noqa: E402
from trading_intelligence.persistence.audit_log import AuditLog  # noqa: E402
from trading_intelligence.strategy.models import TradeProposal  # noqa: E402

NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


class RiskBoundaryAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gpt-risk-review-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        guard = patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK FORBIDDEN"))
        guard.start()
        self.addCleanup(guard.stop)

    def engine(self, **kwargs):
        return RiskEngine(RiskConfig(**kwargs), self.root / "risk.json",
                          AuditLog(self.root / "audit"), NullAlertSink())

    def proposal(self, stop="50"):
        return TradeProposal("fixture", "BTCUSDT", "BUY", "MARKET", Decimal(stop),
                             "1d", "isolated contract fixture", 1.0, NOW.isoformat())

    def validate(self, engine, stop="50"):
        return engine.validate_order(self.proposal(stop), Decimal("1000"), Decimal("100"), now=NOW)

    def test_configured_daily_turnover_is_a_hard_limit(self):
        # Fixture ceiling1%=10; otherwise-legal position is19.92 notional.
        engine = self.engine(max_daily_turnover_pct=1.0)
        decision = self.validate(engine)
        self.assertFalse(decision.approved, "configured turnover limit does not veto entry")

    def test_buy_stop_above_entry_is_not_loss_protection(self):
        self.assertFalse(self.validate(self.engine(), "120").approved)

    def test_negative_stop_is_rejected(self):
        self.assertFalse(self.validate(self.engine(), "-1").approved)

    def test_kill_switch_remains_a_veto_after_restart(self):
        engine = self.engine()
        engine.activate_kill_switch("fixture only")
        decision = self.validate(self.engine())
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "KILL_SWITCH_ACTIVE")

    def test_valid_proposal_has_positive_size_and_audit(self):
        engine = self.engine()
        decision = self.validate(engine)
        self.assertTrue(decision.approved)
        self.assertGreater(decision.quantity, Decimal("0"))
        self.assertEqual(engine.audit_log.read_all()[-1]["decision"], "APPROVED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
