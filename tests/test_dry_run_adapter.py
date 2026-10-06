"""
Tests for DryRunAdapter — the execution gate for LIVE infrastructure that
validates everything and moves nothing. Uses a fake live adapter so no real
network or credentials are involved.
"""
from decimal import Decimal

import pandas as pd

from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.dry_run import DryRunAdapter
from trading_intelligence.execution.order_models import AccountInfo, OrderRequest, Position


class FakeLiveAdapter(AbstractExchangeAdapter):
    """Stand-in for a real adapter (e.g. BinanceSpotAdapter) with full
    lot/tick/notional filter support, so DryRunAdapter's validation path
    can be tested without any real exchange client."""

    def __init__(self):
        self.submit_order_calls = []  # must stay empty — proves nothing was forwarded
        self._lot_step = Decimal("0.001")
        self._tick_size = Decimal("0.01")
        self._min_notional = Decimal("10")

    def submit_order(self, order):
        self.submit_order_calls.append(order)  # the test fails if this is ever called
        raise AssertionError("DryRunAdapter must never forward submit_order to the live adapter")

    def cancel_order(self, client_order_id):
        raise AssertionError("DryRunAdapter must never forward cancel_order to the live adapter")

    def get_position(self, symbol):
        return Position(symbol=symbol, quantity=Decimal("1"), avg_entry_price=Decimal("100"),
                         entry_fee=Decimal("0.1"))

    def get_account_info(self):
        return AccountInfo(equity=Decimal("10000"), cash_balance=Decimal("10000"),
                            positions=[], is_paper=False)

    def get_current_price(self, symbol: str) -> Decimal:
        return Decimal("50000")

    def get_ohlcv(self, symbol, timeframe, limit=500):
        return pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]})

    def is_connected(self) -> bool:
        return True

    def get_exchange_name(self) -> str:
        return "fake_live"

    def round_to_lot_size(self, symbol: str, quantity: Decimal) -> Decimal:
        return (quantity // self._lot_step) * self._lot_step

    def round_to_tick_size(self, symbol: str, price: Decimal) -> Decimal:
        return (price // self._tick_size) * self._tick_size

    def meets_min_notional(self, symbol: str, price: Decimal, quantity: Decimal) -> bool:
        return price * quantity >= self._min_notional


class MinimalLiveAdapter(AbstractExchangeAdapter):
    """A live adapter with NO filter helpers at all — proves DryRunAdapter
    degrades gracefully rather than crashing when they're absent."""

    def submit_order(self, order):
        raise AssertionError("must never be called")

    def cancel_order(self, client_order_id):
        raise AssertionError("must never be called")

    def get_position(self, symbol):
        return None

    def get_account_info(self):
        return AccountInfo(equity=Decimal("1000"), cash_balance=Decimal("1000"), positions=[], is_paper=False)

    def get_current_price(self, symbol: str) -> Decimal:
        return Decimal("100")

    def get_ohlcv(self, symbol, timeframe, limit=500):
        return pd.DataFrame()

    def is_connected(self) -> bool:
        return False

    def get_exchange_name(self) -> str:
        return "minimal_live"


class TestReadOnlyPassthrough:
    def test_market_data_methods_pass_through(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        assert adapter.get_current_price("BTCUSDT") == Decimal("50000")
        assert adapter.is_connected() is True
        assert adapter.get_exchange_name() == "dry_run[fake_live]"

    def test_account_info_passes_through(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        info = adapter.get_account_info()
        assert info.equity == Decimal("10000")

    def test_position_passes_through(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        position = adapter.get_position("BTCUSDT")
        assert position is not None
        assert position.quantity == Decimal("1")


class TestOrderNeverForwarded:
    def test_market_order_never_calls_live_submit(self):
        fake_live = FakeLiveAdapter()
        adapter = DryRunAdapter(fake_live)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"))
        result = adapter.submit_order(order)
        assert fake_live.submit_order_calls == []
        assert result.status == "DRY_RUN"

    def test_cancel_never_forwarded_and_returns_false(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        assert adapter.cancel_order("some-id") is False

    def test_dry_run_log_records_the_attempt(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.01"))
        adapter.submit_order(order)
        assert len(adapter.dry_run_log) == 1
        assert adapter.dry_run_log[0].would_submit is True
        assert adapter.dry_run_log[0].order is order


class TestExchangeSideValidation:
    def test_zero_quantity_rejected(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0"))
        result = adapter.submit_order(order)
        assert result.status == "REJECTED"
        assert "quantity" in result.reject_reason

    def test_quantity_rounds_to_zero_rejected(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        # lot step is 0.001 — this rounds down to 0
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.0001"))
        result = adapter.submit_order(order)
        assert result.status == "REJECTED"
        assert "lot size" in result.reject_reason

    def test_limit_order_without_price_rejected(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=Decimal("1"))
        result = adapter.submit_order(order)
        assert result.status == "REJECTED"
        assert "limit_price" in result.reject_reason

    def test_limit_order_below_min_notional_rejected(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        # price * qty = 1 * 0.001 = 0.001, far below min_notional=10
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="LIMIT",
                              quantity=Decimal("0.001"), limit_price=Decimal("1"))
        result = adapter.submit_order(order)
        assert result.status == "REJECTED"
        assert "notional" in result.reject_reason

    def test_valid_limit_order_passes_as_dry_run(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="LIMIT",
                              quantity=Decimal("1"), limit_price=Decimal("50000"))
        result = adapter.submit_order(order)
        assert result.status == "DRY_RUN"

    def test_valid_market_order_passes_as_dry_run(self):
        adapter = DryRunAdapter(FakeLiveAdapter())
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("1"))
        result = adapter.submit_order(order)
        assert result.status == "DRY_RUN"
        assert result.client_order_id == order.client_order_id

    def test_market_order_rejected_when_exchange_flags_notional_applies_to_market(self):
        """Real bug found by GPT Work's independent review: a MARKET order
        has no limit_price, so meets_min_notional could never run for it —
        this used to silently skip the check entirely, even when the
        exchange's own filter says it applies to MARKET orders too. Must
        fail closed (reject) rather than silently pass an unverifiable case."""
        live = FakeLiveAdapter()
        live.market_notional_check_required = lambda symbol: True
        adapter = DryRunAdapter(live)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.001"))
        result = adapter.submit_order(order)
        assert result.status == "REJECTED"
        assert "notional" in result.reject_reason


class TestDegradesGracefullyWithoutFilterHelpers:
    """A live adapter with no round_to_lot_size/round_to_tick_size/meets_min_notional
    must not crash DryRunAdapter — it just skips those checks."""

    def test_market_order_without_any_filter_helpers(self):
        adapter = DryRunAdapter(MinimalLiveAdapter())
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("1"))
        result = adapter.submit_order(order)
        assert result.status == "DRY_RUN"

    def test_limit_order_without_any_filter_helpers(self):
        adapter = DryRunAdapter(MinimalLiveAdapter())
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="LIMIT",
                              quantity=Decimal("1"), limit_price=Decimal("100"))
        result = adapter.submit_order(order)
        assert result.status == "DRY_RUN"

    def test_read_only_methods_still_work(self):
        adapter = DryRunAdapter(MinimalLiveAdapter())
        assert adapter.is_connected() is False
        assert adapter.get_current_price("X") == Decimal("100")
