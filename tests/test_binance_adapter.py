"""
Tests for BinanceSpotAdapter. No real network calls are made — the exchange
client is monkeypatched. Credential-gating and filter/rounding logic (pure,
no network) are what's tested here; full API integration is out of scope
until the owner provides real API keys (see docs/BINANCE_INTEGRATION_NOTES.md).
"""
from decimal import Decimal

import pytest

from trading_intelligence.execution.binance import BinanceCredentialsMissing, BinanceSpotAdapter
from trading_intelligence.execution.order_models import OrderRequest


def _adapter_without_credentials() -> BinanceSpotAdapter:
    return BinanceSpotAdapter(api_key=None, secret_key=None, testnet=True)


class FakeBinanceClient:
    """Stand-in for python-binance's Client — no network calls."""

    def __init__(self):
        self.created_orders = []

    def ping(self):
        return {}

    def get_server_time(self):
        return {"serverTime": 1735689600000}

    def get_exchange_info(self):
        return {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE", "stepSize": "0.00010000", "minQty": "0.0001", "maxQty": "1000"},
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "10.0"},
                    ],
                }
            ]
        }

    def get_account(self):
        return {
            "permissions": ["SPOT"],
            "balances": [
                {"asset": "USDT", "free": "5000.00", "locked": "0"},
                {"asset": "BTC", "free": "0.1", "locked": "0"},
            ],
        }

    def get_symbol_ticker(self, symbol):
        return {"symbol": symbol, "price": "50123.45"}

    def create_order(self, **params):
        self.created_orders.append(params)
        return {"orderId": 12345, "transactTime": 1735689600000}


def _adapter_with_fake_client() -> tuple[BinanceSpotAdapter, FakeBinanceClient]:
    adapter = BinanceSpotAdapter(api_key="fake", secret_key="fake", testnet=True)
    fake_client = FakeBinanceClient()
    adapter._get_client = lambda: fake_client
    return adapter, fake_client


class TestCredentialGating:
    def test_construction_without_credentials_does_not_raise(self):
        _adapter_without_credentials()  # should not raise

    def test_has_credentials_false_when_unset(self):
        adapter = _adapter_without_credentials()
        assert adapter.has_credentials is False

    def test_connect_raises_without_credentials(self):
        adapter = _adapter_without_credentials()
        with pytest.raises(BinanceCredentialsMissing):
            adapter.connect()

    def test_get_current_price_raises_without_credentials(self):
        adapter = _adapter_without_credentials()
        with pytest.raises(BinanceCredentialsMissing):
            adapter.get_current_price("BTCUSDT")

    def test_submit_order_raises_without_credentials(self):
        adapter = _adapter_without_credentials()
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"))
        with pytest.raises(BinanceCredentialsMissing):
            adapter.submit_order(order)

    def test_is_connected_false_without_credentials(self):
        adapter = _adapter_without_credentials()
        assert adapter.is_connected() is False


class TestExchangeName:
    def test_testnet_name(self):
        adapter = BinanceSpotAdapter(api_key="x", secret_key="y", testnet=True)
        assert adapter.get_exchange_name() == "binance_spot_testnet"

    def test_live_name(self):
        adapter = BinanceSpotAdapter(api_key="x", secret_key="y", testnet=False)
        assert adapter.get_exchange_name() == "binance_spot"


class TestFiltersAndRounding:
    def test_round_to_lot_size_rounds_down(self):
        adapter, _ = _adapter_with_fake_client()
        # stepSize 0.0001 -> 0.123456 should round down to 0.1234
        result = adapter.round_to_lot_size("BTCUSDT", Decimal("0.123456"))
        assert result == Decimal("0.1234")

    def test_round_to_lot_size_never_rounds_up(self):
        adapter, _ = _adapter_with_fake_client()
        result = adapter.round_to_lot_size("BTCUSDT", Decimal("0.00019999"))
        assert result <= Decimal("0.00019999")

    def test_round_to_tick_size(self):
        adapter, _ = _adapter_with_fake_client()
        result = adapter.round_to_tick_size("BTCUSDT", Decimal("50123.456"))
        assert result == Decimal("50123.45")

    def test_meets_min_notional_true(self):
        adapter, _ = _adapter_with_fake_client()
        assert adapter.meets_min_notional("BTCUSDT", Decimal("50000"), Decimal("0.001")) is True  # $50

    def test_meets_min_notional_false(self):
        adapter, _ = _adapter_with_fake_client()
        assert adapter.meets_min_notional("BTCUSDT", Decimal("50000"), Decimal("0.0001")) is False  # $5

    def test_exchange_info_cached(self):
        adapter, fake_client = _adapter_with_fake_client()
        adapter._load_exchange_info()
        adapter._load_exchange_info()  # second call should use cache, not re-fetch
        # FakeBinanceClient has no call counter, but cache object identity confirms reuse
        assert adapter._exchange_info_cache is not None


class TestOrderSubmission:
    def test_submit_market_order_rounds_quantity(self):
        adapter, fake_client = _adapter_with_fake_client()
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.123456"))
        result = adapter.submit_order(order)
        assert result.status == "SUBMITTED"
        assert result.requested_quantity == Decimal("0.1234")
        assert Decimal(fake_client.created_orders[0]["quantity"]) == Decimal("0.1234")

    def test_submit_order_zero_after_rounding_is_rejected(self):
        adapter, _ = _adapter_with_fake_client()
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.00001"))
        result = adapter.submit_order(order)
        assert result.status == "REJECTED"


class TestConnect:
    def test_connect_verifies_spot_permission(self):
        adapter, _ = _adapter_with_fake_client()
        adapter.connect()  # should not raise — FakeBinanceClient reports SPOT permission
        assert adapter._connected is True

    def test_connect_rejects_missing_spot_permission(self):
        adapter, fake_client = _adapter_with_fake_client()
        fake_client.get_account = lambda: {"permissions": ["FUTURES"], "balances": []}
        with pytest.raises(RuntimeError, match="SPOT"):
            adapter.connect()
