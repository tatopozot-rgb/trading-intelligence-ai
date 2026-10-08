"""Offline acceptance checks for the existing Binance/DryRun adapter boundary.

Usage: python test_exchange_readiness_review.py <root containing trading_intelligence>
Only synthetic credentials and injected fake clients are used; sockets are denied.
These tests deliberately fail until the owning team resolves the readiness gaps.
"""
from __future__ import annotations

import os
import socket
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(SOURCE))
sys.dont_write_bytecode = True

from trading_intelligence.execution.binance import BinanceSpotAdapter  # noqa: E402
from trading_intelligence.execution.dry_run import DryRunAdapter  # noqa: E402
from trading_intelligence.execution.order_models import OrderRequest  # noqa: E402


class FakeClient:
    def __init__(self, *, can_trade=True, free="0", locked="0"):
        self.can_trade = can_trade
        self.free = free
        self.locked = locked
        self.created = []

    def get_account(self):
        return {"permissions": ["SPOT"], "canTrade": self.can_trade,
                "balances": [{"asset": "BTC", "free": self.free, "locked": self.locked}]}

    def get_exchange_info(self):
        return {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
                            "filters": [
                                {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                {"filterType": "MIN_NOTIONAL", "minNotional": "10", "applyToMarket": True, "avgPriceMins": 0}]}]}

    def get_symbol_ticker(self, **kwargs):
        return {"price": "100"}

    def create_order(self, **kwargs):
        # Evidence recorder ONLY: no network and no real exchange dependency.
        self.created.append(kwargs)
        return {"orderId": "synthetic", "transactTime": 0}


class ExchangeReadinessReview(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK FORBIDDEN"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.factory = patch.object(BinanceSpotAdapter, "_get_client", lambda adapter: adapter._client)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def adapter(self, **kwargs):
        adapter = BinanceSpotAdapter(api_key="x", secret_key="y", testnet=True)
        adapter._client = FakeClient(**kwargs)
        return adapter

    def test_spot_category_is_not_can_trade_permission(self):
        adapter = self.adapter(can_trade=False)
        with self.assertRaises(RuntimeError, msg="canTrade=false must veto trading readiness"):
            adapter._verify_permissions(adapter._client)

    def test_locked_holdings_are_not_reported_as_flat(self):
        position = self.adapter(free="0", locked="0.5").get_position("BTCUSDT")
        self.assertIsNotNone(position, "locked holdings remain exposure during reconciliation")
        self.assertEqual(position.quantity, Decimal("0.5"))

    def test_unverified_session_cannot_reach_exchange_order_method(self):
        adapter = self.adapter()
        self.assertFalse(adapter._connected)
        try:
            adapter.submit_order(OrderRequest("BTCUSDT", "BUY", "MARKET", Decimal("0.2")))
        except RuntimeError:
            pass  # A fail-closed readiness exception is acceptable.
        self.assertEqual(adapter._client.created, [], "unverified session reached create_order")

    def test_market_below_min_notional_is_not_certified_by_dry_run(self):
        adapter = self.adapter()
        dry = DryRunAdapter(adapter)
        result = dry.submit_order(OrderRequest("BTCUSDT", "BUY", "MARKET", Decimal("0.001")))
        self.assertEqual(adapter._client.created, [])
        self.assertEqual(result.status, "REJECTED", "0.1 notional is below the synthetic exchange minimum of 10")

    def test_dry_run_intercepts_valid_limit_order(self):
        adapter = self.adapter()
        result = DryRunAdapter(adapter).submit_order(
            OrderRequest("BTCUSDT", "BUY", "LIMIT", Decimal("0.2"), limit_price=Decimal("100")))
        self.assertEqual(result.status, "DRY_RUN")
        self.assertEqual(adapter._client.created, [])

    def test_dry_run_rejects_subminimum_limit_order(self):
        adapter = self.adapter()
        result = DryRunAdapter(adapter).submit_order(
            OrderRequest("BTCUSDT", "BUY", "LIMIT", Decimal("0.001"), limit_price=Decimal("100")))
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(adapter._client.created, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
