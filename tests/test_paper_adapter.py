"""Tests for PaperAdapter — fills, position accounting, state persistence."""
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.order_models import AccountInfo, OrderRequest
from trading_intelligence.execution.paper import PaperAdapter


class FakeMarketDataAdapter(AbstractExchangeAdapter):
    """Minimal stand-in for BinanceSpotAdapter used read-only for market data."""

    def __init__(self, price: Decimal = Decimal("50000")):
        self._price = price
        self._connected = True

    def submit_order(self, order):
        raise AssertionError("PaperAdapter must never forward orders to market data adapter")

    def cancel_order(self, client_order_id):
        raise AssertionError("not used")

    def get_position(self, symbol):
        return None

    def get_account_info(self):
        raise AssertionError("not used")

    def get_current_price(self, symbol: str) -> Decimal:
        return self._price

    def get_ohlcv(self, symbol, timeframe, limit=500):
        return pd.DataFrame()

    def is_connected(self) -> bool:
        return self._connected

    def get_exchange_name(self) -> str:
        return "fake_market_data"


def _adapter(tmp_path: Path, equity: Decimal = Decimal("10000")) -> PaperAdapter:
    return PaperAdapter(
        market_data_adapter=FakeMarketDataAdapter(),
        initial_equity=equity,
        state_path=tmp_path / "paper_state.json",
    )


class TestOrderSubmission:
    def test_submit_market_order_is_pending_until_next_bar(self, tmp_path):
        adapter = _adapter(tmp_path)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        result = adapter.submit_order(order)
        assert result.status == "SUBMITTED"
        assert adapter.get_position("BTCUSDT") is None  # not filled yet

    def test_zero_quantity_rejected(self, tmp_path):
        adapter = _adapter(tmp_path)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0"))
        result = adapter.submit_order(order)
        assert result.status == "REJECTED"

    def test_cancel_pending_order(self, tmp_path):
        adapter = _adapter(tmp_path)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(order)
        assert adapter.cancel_order(order.client_order_id) is True
        assert adapter.cancel_order(order.client_order_id) is False  # already cancelled


class TestNextBarFill:
    def test_market_buy_fills_at_next_bar_open_with_slippage(self, tmp_path):
        adapter = _adapter(tmp_path)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(order)

        filled = adapter.on_new_bar(
            "BTCUSDT", open_=Decimal("50000"), high=Decimal("50500"),
            low=Decimal("49500"), close=Decimal("50200"), bar_time="2026-01-01T01:00:00Z",
        )
        assert len(filled) == 1
        assert filled[0].status == "FILLED"
        expected_price = Decimal("50000") * (1 + Decimal("0.0005"))
        assert filled[0].fill_price == expected_price

        position = adapter.get_position("BTCUSDT")
        assert position is not None
        assert position.quantity == Decimal("0.1")

    def test_buy_reduces_cash_by_cost_plus_fee(self, tmp_path):
        adapter = _adapter(tmp_path, equity=Decimal("10000"))
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(order)
        adapter.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50500"), Decimal("49500"),
                            Decimal("50200"), "2026-01-01T01:00:00Z")

        fill_price = Decimal("50000") * Decimal("1.0005")
        fee = fill_price * Decimal("0.1") * Decimal("0.001")
        expected_cash = Decimal("10000") - (fill_price * Decimal("0.1") + fee)
        assert adapter.cash == expected_cash

    def test_sell_closes_position_with_realized_pnl(self, tmp_path):
        adapter = _adapter(tmp_path)
        buy = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(buy)
        adapter.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50500"), Decimal("49500"),
                            Decimal("50200"), "2026-01-01T01:00:00Z")

        sell = OrderRequest(symbol="BTCUSDT", side="SELL", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(sell)
        filled = adapter.on_new_bar("BTCUSDT", Decimal("52000"), Decimal("52500"), Decimal("51500"),
                                     Decimal("52200"), "2026-01-01T02:00:00Z")

        assert adapter.get_position("BTCUSDT") is None
        assert filled[-1].status == "FILLED"
        # Bought ~50025, sold ~51974 -> profitable trade
        assert adapter.cash > Decimal("10000")

    def test_full_sell_credits_cash_by_exact_sale_proceeds(self, tmp_path):
        """Real bug found by auditing: _apply_sell used to credit
        `entry_cost + realized_pnl` instead of the actual sale proceeds,
        which double-charges the entry fee's share on every sell
        (realized_pnl already has it subtracted once). Cash must equal a
        plain ledger: starting cash, minus the buy's full cost (price +
        fee), plus the sell's full proceeds (price - fee) — nothing more
        clever needed, and nothing less."""
        adapter = _adapter(tmp_path, equity=Decimal("10000"))
        buy = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(buy)
        adapter.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50500"), Decimal("49500"),
                            Decimal("50200"), "2026-01-01T01:00:00Z")

        sell = OrderRequest(symbol="BTCUSDT", side="SELL", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(sell)
        adapter.on_new_bar("BTCUSDT", Decimal("52000"), Decimal("52500"), Decimal("51500"),
                            Decimal("52200"), "2026-01-01T02:00:00Z")

        buy_fill = Decimal("50000") * Decimal("1.0005")
        buy_fee = buy_fill * Decimal("0.1") * Decimal("0.001")
        sell_fill = Decimal("52000") * (Decimal("1") - Decimal("0.0005"))
        sell_fee = sell_fill * Decimal("0.1") * Decimal("0.001")
        expected_cash = Decimal("10000") - (buy_fill * Decimal("0.1") + buy_fee) + (sell_fill * Decimal("0.1") - sell_fee)
        assert adapter.cash == expected_cash

    def test_partial_sell_credits_only_that_portions_proceeds(self, tmp_path):
        """A partial sell must credit cash by exactly that slice's sale
        proceeds — the still-open remainder's cost basis stays spent
        (tied up in the position) until it too is sold, same as a real
        brokerage account."""
        adapter = _adapter(tmp_path, equity=Decimal("10000"))
        buy = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("1"))
        adapter.submit_order(buy)
        adapter.on_new_bar("BTCUSDT", Decimal("100"), Decimal("101"), Decimal("99"),
                            Decimal("100"), "2026-01-01T01:00:00Z")
        cash_after_buy = adapter.cash

        sell = OrderRequest(symbol="BTCUSDT", side="SELL", order_type="MARKET", quantity=Decimal("0.4"))
        adapter.submit_order(sell)
        adapter.on_new_bar("BTCUSDT", Decimal("110"), Decimal("111"), Decimal("109"),
                            Decimal("110"), "2026-01-01T02:00:00Z")

        sell_fill = Decimal("110") * (Decimal("1") - Decimal("0.0005"))
        sell_fee = sell_fill * Decimal("0.4") * Decimal("0.001")
        proceeds = sell_fill * Decimal("0.4") - sell_fee
        assert adapter.cash == cash_after_buy + proceeds
        assert adapter.get_position("BTCUSDT").quantity == Decimal("0.6")

    def test_sell_more_than_held_raises(self, tmp_path):
        adapter = _adapter(tmp_path)
        buy = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(buy)
        adapter.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50500"), Decimal("49500"),
                            Decimal("50200"), "2026-01-01T01:00:00Z")

        sell = OrderRequest(symbol="BTCUSDT", side="SELL", order_type="MARKET", quantity=Decimal("1.0"))
        adapter.submit_order(sell)
        with pytest.raises(ValueError, match="insufficient"):
            adapter.on_new_bar("BTCUSDT", Decimal("52000"), Decimal("52500"), Decimal("51500"),
                                Decimal("52200"), "2026-01-01T02:00:00Z")


class TestLimitOrders:
    def test_limit_buy_fills_when_price_touches(self, tmp_path):
        adapter = _adapter(tmp_path)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="LIMIT",
                              quantity=Decimal("0.1"), limit_price=Decimal("49000"))
        adapter.submit_order(order)
        filled = adapter.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50200"),
                                     Decimal("48500"), Decimal("49800"), "2026-01-01T01:00:00Z")
        assert len(filled) == 1
        assert filled[0].status == "FILLED"
        assert filled[0].fill_price == Decimal("49000")  # worse of open(50000)/limit(49000) = limit

    def test_limit_buy_does_not_fill_when_price_does_not_touch(self, tmp_path):
        adapter = _adapter(tmp_path)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="LIMIT",
                              quantity=Decimal("0.1"), limit_price=Decimal("40000"))
        adapter.submit_order(order)
        filled = adapter.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50200"),
                                     Decimal("48500"), Decimal("49800"), "2026-01-01T01:00:00Z")
        assert len(filled) == 1
        assert filled[0].status == "PENDING"
        assert adapter.get_position("BTCUSDT") is None


class TestStopOrders:
    def test_stop_triggers_with_gap_through_slippage(self, tmp_path):
        adapter = _adapter(tmp_path)
        buy = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(buy)
        adapter.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50500"), Decimal("49500"),
                            Decimal("50200"), "2026-01-01T01:00:00Z")

        stop = OrderRequest(symbol="BTCUSDT", side="SELL", order_type="STOP",
                             quantity=Decimal("0.1"), stop_price=Decimal("49000"))
        adapter.submit_order(stop)

        # Next bar gaps down through the stop
        filled = adapter.on_new_bar("BTCUSDT", Decimal("48000"), Decimal("48200"),
                                     Decimal("47500"), Decimal("47800"), "2026-01-01T02:00:00Z")
        stop_fills = [f for f in filled if f.side == "SELL"]
        assert len(stop_fills) == 1
        assert stop_fills[0].fill_price < Decimal("48000")  # slippage applied on gap fill
        assert adapter.get_position("BTCUSDT") is None


class TestAccountInfo:
    def test_equity_includes_open_position_value(self, tmp_path):
        adapter = _adapter(tmp_path, equity=Decimal("10000"))
        buy = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        adapter.submit_order(buy)
        adapter.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50500"), Decimal("49500"),
                            Decimal("50200"), "2026-01-01T01:00:00Z")

        info: AccountInfo = adapter.get_account_info()
        assert info.is_paper is True
        assert len(info.positions) == 1
        # equity = cash + mark-to-market position value; should be close to 10000 minus fees
        assert info.equity > Decimal("9900")
        assert info.equity < Decimal("10100")


class TestStatePersistence:
    def test_state_survives_restart(self, tmp_path):
        state_path = tmp_path / "paper_state.json"
        adapter1 = PaperAdapter(FakeMarketDataAdapter(), Decimal("10000"), state_path=state_path)
        buy = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.1"))
        adapter1.submit_order(buy)
        adapter1.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50500"), Decimal("49500"),
                             Decimal("50200"), "2026-01-01T01:00:00Z")

        adapter2 = PaperAdapter(FakeMarketDataAdapter(), Decimal("999999"), state_path=state_path)
        # Loaded state should override the constructor's initial_equity
        assert adapter2.cash == adapter1.cash
        position = adapter2.get_position("BTCUSDT")
        assert position is not None
        assert position.quantity == Decimal("0.1")

    def test_pending_order_survives_restart(self, tmp_path):
        """Real bug found by GPT Work's independent review: _save_state only
        persisted cash/positions — a pending entry (and, worse, a protective
        STOP on an open position) silently vanished on restart."""
        state_path = tmp_path / "paper_state.json"
        adapter1 = PaperAdapter(FakeMarketDataAdapter(), Decimal("10000"), state_path=state_path)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="LIMIT",
                              quantity=Decimal("0.1"), limit_price=Decimal("49000"),
                              client_order_id="fixture-pending")
        adapter1.submit_order(order)

        adapter2 = PaperAdapter(FakeMarketDataAdapter(), Decimal("999999"), state_path=state_path)
        assert [o.client_order_id for o in adapter2.pending_orders] == ["fixture-pending"]
        assert adapter2.pending_orders[0].limit_price == Decimal("49000")

    def test_protective_stop_survives_restart_and_still_closes_on_gap(self, tmp_path):
        state_path = tmp_path / "paper_state.json"
        adapter1 = PaperAdapter(FakeMarketDataAdapter(), Decimal("10000"), state_path=state_path)
        adapter1.submit_order(OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET",
                                            quantity=Decimal("0.1"), client_order_id="fixture-buy"))
        adapter1.on_new_bar("BTCUSDT", Decimal("50000"), Decimal("50500"), Decimal("49500"),
                            Decimal("50200"), "2026-01-01T01:00:00Z")
        adapter1.submit_order(OrderRequest(symbol="BTCUSDT", side="SELL", order_type="STOP",
                                            quantity=Decimal("0.1"), stop_price=Decimal("48000"),
                                            client_order_id="fixture-stop"))

        adapter2 = PaperAdapter(FakeMarketDataAdapter(), Decimal("999999"), state_path=state_path)
        adapter2.on_new_bar("BTCUSDT", Decimal("47000"), Decimal("47000"), Decimal("46000"),
                            Decimal("46500"), "2026-01-02T00:00:00Z")
        assert adapter2.get_position("BTCUSDT") is None, "restart must not discard the protective STOP"


class TestOrderIdempotency:
    def test_duplicate_client_order_id_does_not_double_fill(self, tmp_path):
        """Real bug found by GPT Work's independent review: resubmitting the
        identical OrderRequest filled it twice."""
        adapter = _adapter(tmp_path)
        order = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET",
                              quantity=Decimal("1"), client_order_id="fixture-dup")
        first = adapter.submit_order(order)
        second = adapter.submit_order(order)
        assert first.status == "SUBMITTED"
        assert second.status == "REJECTED"
        adapter.on_new_bar("BTCUSDT", Decimal("100"), Decimal("100"), Decimal("100"),
                           Decimal("100"), "2026-01-01T00:00:00Z")
        assert adapter.get_position("BTCUSDT").quantity == Decimal("1")


class TestGapFillAffordability:
    def test_gap_fill_cannot_create_negative_cash(self, tmp_path):
        """Real bug found by GPT Work's independent review: a BUY affordable
        at decision-time price could still fill at a gapped-up next-bar
        open with no affordability check at all, driving cash negative."""
        adapter = _adapter(tmp_path, equity=Decimal("1000"))
        # Affordable at ~100 (900 + fees); not at a gap to 200.
        adapter.submit_order(OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET",
                                           quantity=Decimal("9"), client_order_id="fixture-gap"))
        results = adapter.on_new_bar("BTCUSDT", Decimal("200"), Decimal("210"), Decimal("195"),
                                      Decimal("205"), "2026-01-01T00:00:00Z")
        assert results[0].status == "REJECTED"
        assert adapter.cash == Decimal("1000")
        assert adapter.get_position("BTCUSDT") is None

    def test_affordable_fill_still_succeeds(self, tmp_path):
        adapter = _adapter(tmp_path, equity=Decimal("1000"))
        adapter.submit_order(OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET",
                                           quantity=Decimal("1"), client_order_id="fixture-ok"))
        results = adapter.on_new_bar("BTCUSDT", Decimal("100"), Decimal("105"), Decimal("95"),
                                      Decimal("100"), "2026-01-01T00:00:00Z")
        assert results[0].status == "FILLED"
        assert adapter.cash < Decimal("1000")
        assert adapter.cash > Decimal("0")


class TestIdempotencySurvivesRestart:
    """The first idempotency fix kept its memory only in order_history, which
    is not persisted: a retry after a restart looked new and doubled the fill
    (GPT Work's lifecycle review)."""

    @staticmethod
    def _order(client_order_id):
        return OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET",
                            quantity=Decimal("1"), client_order_id=client_order_id)

    @staticmethod
    def _fill(adapter, when):
        adapter.on_new_bar("BTCUSDT", Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), when)

    def test_a_retried_pending_order_is_rejected_after_restart(self, tmp_path):
        first = _adapter(tmp_path)
        first.submit_order(self._order("retry-pending"))
        restored = _adapter(tmp_path)
        assert restored.submit_order(self._order("retry-pending")).status == "REJECTED"
        self._fill(restored, "2026-01-02T00:00:00Z")
        assert restored.get_position("BTCUSDT").quantity == Decimal("1")

    def test_a_retried_filled_order_is_rejected_after_restart(self, tmp_path):
        first = _adapter(tmp_path)
        first.submit_order(self._order("retry-filled"))
        self._fill(first, "2026-01-02T00:00:00Z")
        restored = _adapter(tmp_path)
        assert restored.submit_order(self._order("retry-filled")).status == "REJECTED"
        self._fill(restored, "2026-01-03T00:00:00Z")
        assert restored.get_position("BTCUSDT").quantity == Decimal("1")

    def test_a_cancelled_id_can_be_used_again_even_after_restart(self, tmp_path):
        first = _adapter(tmp_path)
        first.submit_order(self._order("retry-cancelled"))
        assert first.cancel_order("retry-cancelled") is True
        restored = _adapter(tmp_path)
        assert restored.submit_order(self._order("retry-cancelled")).status == "SUBMITTED"

    def test_a_state_file_from_before_the_fix_still_protects_its_pending_orders(self, tmp_path):
        import json

        first = _adapter(tmp_path)
        first.submit_order(self._order("legacy-pending"))
        path = tmp_path / "paper_state.json"
        data = json.loads(path.read_text())
        del data["used_order_ids"]
        path.write_text(json.dumps(data))
        restored = _adapter(tmp_path)
        assert restored.submit_order(self._order("legacy-pending")).status == "REJECTED"


class TestStopsInsideTheFillBar:
    def _buy_at_open(self, adapter, low):
        adapter.submit_order(OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET",
                                          quantity=Decimal("1"), client_order_id="buy"))
        adapter.on_new_bar("BTCUSDT", Decimal("100"), Decimal("101"), low, Decimal("99"), "2026-01-02T00:00:00Z")

    def test_a_stop_submitted_after_the_fill_is_checked_against_that_same_bar(self, tmp_path):
        adapter = _adapter(tmp_path)
        self._buy_at_open(adapter, low=Decimal("90"))
        adapter.submit_order(OrderRequest(symbol="BTCUSDT", side="SELL", order_type="STOP",
                                          quantity=Decimal("1"), stop_price=Decimal("95"), client_order_id="stop"))
        assert adapter.get_position("BTCUSDT") is not None
        fills = adapter.evaluate_stops("BTCUSDT")
        assert [f.client_order_id for f in fills] == ["stop"]
        assert adapter.get_position("BTCUSDT") is None
        assert fills[0].fill_price == Decimal("95") * (1 - 2 * adapter.slippage_rate)

    def test_a_low_above_the_stop_does_not_trigger_it(self, tmp_path):
        adapter = _adapter(tmp_path)
        self._buy_at_open(adapter, low=Decimal("95.01"))
        adapter.submit_order(OrderRequest(symbol="BTCUSDT", side="SELL", order_type="STOP",
                                          quantity=Decimal("1"), stop_price=Decimal("95"), client_order_id="stop"))
        assert adapter.evaluate_stops("BTCUSDT") == []
        assert adapter.get_position("BTCUSDT") is not None

    def test_without_a_current_bar_it_is_a_noop(self, tmp_path):
        adapter = _adapter(tmp_path)
        self._buy_at_open(adapter, low=Decimal("90"))
        adapter.submit_order(OrderRequest(symbol="BTCUSDT", side="SELL", order_type="STOP",
                                          quantity=Decimal("1"), stop_price=Decimal("95"), client_order_id="stop"))
        restarted = _adapter(tmp_path)  # the bar is in memory only
        assert restarted.evaluate_stops("BTCUSDT") == []
        assert restarted.get_position("BTCUSDT") is not None


class TestPriceHelpers:
    def test_market_fill_price_applies_slippage_against_the_trader(self, tmp_path):
        adapter = _adapter(tmp_path)
        assert adapter.market_fill_price("BUY", Decimal("100")) == Decimal("100") * (1 + adapter.slippage_rate)
        assert adapter.market_fill_price("SELL", Decimal("100")) == Decimal("100") * (1 - adapter.slippage_rate)

    def test_last_known_equity_never_asks_the_market_data_adapter(self, tmp_path):
        adapter = _adapter(tmp_path)  # FakeMarketDataAdapter quotes 50000 for everything
        adapter.submit_order(OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET",
                                          quantity=Decimal("1"), client_order_id="buy"))
        adapter.on_new_bar("BTCUSDT", Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), "t1")
        restarted = _adapter(tmp_path)  # no marks yet: position carried at its entry price
        position = restarted.get_position("BTCUSDT")
        assert restarted.last_known_equity() == restarted.cash + position.avg_entry_price * position.quantity
        assert restarted.get_account_info().equity != restarted.last_known_equity()
