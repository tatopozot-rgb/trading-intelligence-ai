"""Offline persistence/idempotency acceptance for the existing research PaperAdapter.

Run: python test_paper_recovery_review.py <research-source-directory>
Not a new runner, strategy, risk policy or live adapter. Uses synthetic replay only.
"""
from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(sys.argv.pop(1)).resolve()))
sys.dont_write_bytecode = True
from trading_intelligence.execution.paper import PaperAdapter  # noqa: E402
from trading_intelligence.execution.order_models import OrderRequest  # noqa: E402


class DataOnly:
    def get_current_price(self, symbol):
        return Decimal("100")

    def submit_order(self, order):
        raise AssertionError("Paper must never forward an order")

    def get_exchange_name(self):
        return "synthetic"


class PaperRecoveryAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gpt-paper-review-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "paper.json"
        guard = patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK FORBIDDEN"))
        guard.start()
        self.addCleanup(guard.stop)
        self.paper = self.new_adapter()

    def new_adapter(self):
        return PaperAdapter(DataOnly(), Decimal("1000"), self.path,
                            taker_fee=Decimal("0.001"), slippage_rate=Decimal("0"))

    def bar(self, adapter, *, price="100", timestamp="2026-01-02T00:00:00Z"):
        p = Decimal(price)
        return adapter.on_new_bar("BTCUSDT", p, p, p, p, timestamp)

    def buy(self, *, quantity="1", order_id="fixture-buy"):
        return OrderRequest("BTCUSDT", "BUY", "MARKET", Decimal(quantity), client_order_id=order_id)

    def test_duplicate_client_id_does_not_duplicate_fill(self):
        order = self.buy()
        self.paper.submit_order(order)
        self.paper.submit_order(order)
        self.bar(self.paper)
        self.assertEqual(self.paper.get_position("BTCUSDT").quantity, Decimal("1"))

    def test_pending_submission_survives_restart(self):
        self.paper.submit_order(self.buy())
        restarted = self.new_adapter()
        self.assertEqual([o.client_order_id for o in restarted.pending_orders], ["fixture-buy"])

    def test_protective_stop_survives_restart_and_closes_on_gap(self):
        self.paper.submit_order(self.buy())
        self.bar(self.paper)
        self.paper.submit_order(OrderRequest("BTCUSDT", "SELL", "STOP", Decimal("1"),
                                            stop_price=Decimal("90"), client_order_id="fixture-stop"))
        restarted = self.new_adapter()
        self.bar(restarted, price="80", timestamp="2026-01-03T00:00:00Z")
        self.assertIsNone(restarted.get_position("BTCUSDT"), "restart discarded protective STOP")

    def test_gap_fill_cannot_create_negative_spot_cash(self):
        # Affordable at decision-time price100 (900 + fees), not at next-open200.
        self.paper.submit_order(self.buy(quantity="9"))
        try:
            self.bar(self.paper, price="200")
        except ValueError:
            pass  # A fail-closed reject is valid; negative cash is not.
        self.assertGreaterEqual(self.paper.cash, Decimal("0"))

    def test_filled_position_and_cash_survive_restart(self):
        self.paper.submit_order(self.buy())
        self.bar(self.paper)
        restarted = self.new_adapter()
        self.assertEqual(restarted.cash, self.paper.cash)
        self.assertEqual(restarted.get_position("BTCUSDT").quantity, Decimal("1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
