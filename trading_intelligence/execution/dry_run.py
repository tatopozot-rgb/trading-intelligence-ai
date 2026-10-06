"""
DryRunAdapter — wraps a real exchange adapter for LIVE-infrastructure
testing without ever moving money.

Per the project's LIVE-readiness goal: everything that doesn't move real
money should be built and tested now (auth, connectivity, order
construction, exchange-side filter validation) — only actually sending an
order is deferred until LIVE_ACTIVATION_APPROVAL. Every read-only method
passes through to the wrapped adapter, so auth, connectivity, and real
market data genuinely get exercised. submit_order and cancel_order are
intercepted: the order is validated as thoroughly as the wrapped adapter
allows, then recorded — NEVER forwarded to the exchange.

This is NOT a replacement for RiskEngine approval. The caller must still
pass every order through RiskEngine.validate_order() before it ever reaches
this adapter — this layer only does exchange-side validation (lot size,
tick size, min notional) and logging.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pandas as pd

from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.order_models import AccountInfo, OrderRequest, OrderResult, Position

logger = logging.getLogger(__name__)


@dataclass
class DryRunLogEntry:
    order: OrderRequest
    would_submit: bool
    reason: str
    logged_at: str


class DryRunAdapter(AbstractExchangeAdapter):
    """Drop-in replacement for a live adapter during the "everything except
    moving money" phase. Safe to construct anywhere — it only ever reads."""

    def __init__(self, live_adapter: AbstractExchangeAdapter):
        self._live = live_adapter
        self.dry_run_log: list[DryRunLogEntry] = []

    # ------------------------------------------------------------------
    # Read-only passthrough — exercises the REAL connection, no money moved
    # ------------------------------------------------------------------

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._live.get_position(symbol)

    def get_account_info(self) -> AccountInfo:
        return self._live.get_account_info()

    def get_current_price(self, symbol: str) -> Decimal:
        return self._live.get_current_price(symbol)

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        return self._live.get_ohlcv(symbol, timeframe, limit)

    def is_connected(self) -> bool:
        return self._live.is_connected()

    def get_exchange_name(self) -> str:
        return f"dry_run[{self._live.get_exchange_name()}]"

    # ------------------------------------------------------------------
    # Order methods — intercepted, NEVER forwarded to the real exchange
    # ------------------------------------------------------------------

    def submit_order(self, order: OrderRequest) -> OrderResult:
        validation_reason = self._validate_against_live_filters(order)
        now = datetime.now(timezone.utc).isoformat()

        entry = DryRunLogEntry(
            order=order,
            would_submit=validation_reason is None,
            reason=validation_reason or "passed all available exchange-side checks",
            logged_at=now,
        )
        self.dry_run_log.append(entry)
        logger.info(
            "DRY RUN %s %s %s %s qty=%s — %s",
            "REJECTED" if validation_reason else "WOULD SUBMIT",
            order.side, order.order_type, order.symbol, order.quantity, entry.reason,
        )

        if validation_reason is not None:
            return OrderResult(
                client_order_id=order.client_order_id, status="REJECTED", symbol=order.symbol,
                side=order.side, requested_quantity=order.quantity, reject_reason=validation_reason,
            )
        return OrderResult(
            client_order_id=order.client_order_id, status="DRY_RUN", symbol=order.symbol,
            side=order.side, requested_quantity=order.quantity, submitted_at=now,
        )

    def cancel_order(self, client_order_id: str) -> bool:
        """Nothing was ever really submitted, so there is nothing to cancel."""
        logger.info("DRY RUN cancel requested for %s — no real order exists", client_order_id)
        return False

    def _validate_against_live_filters(self, order: OrderRequest) -> Optional[str]:
        """
        Runs whatever pre-trade validation the wrapped adapter exposes
        (e.g. BinanceSpotAdapter's lot/tick/notional rounding) without ever
        calling its submit_order. Returns a rejection reason, or None if it
        passes (or the wrapped adapter exposes no such checks — passing
        with no checks available is still logged plainly as such).
        """
        if order.quantity <= 0:
            return "quantity must be > 0"

        round_to_lot_size = getattr(self._live, "round_to_lot_size", None)
        if round_to_lot_size is not None:
            rounded_qty = round_to_lot_size(order.symbol, order.quantity)
            if rounded_qty <= 0:
                return "quantity rounds to zero after exchange lot size filter"
        else:
            rounded_qty = order.quantity

        if order.order_type == "LIMIT":
            if order.limit_price is None:
                return "LIMIT order requires limit_price"
            round_to_tick_size = getattr(self._live, "round_to_tick_size", None)
            price = round_to_tick_size(order.symbol, order.limit_price) if round_to_tick_size else order.limit_price

            meets_min_notional = getattr(self._live, "meets_min_notional", None)
            if meets_min_notional is not None and not meets_min_notional(order.symbol, price, rounded_qty):
                return "order value below exchange minimum notional"

        return None
