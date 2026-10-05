"""
BinanceSpotAdapter — real exchange integration via python-binance.

Per docs/BINANCE_INTEGRATION_NOTES.md. NOT usable until BINANCE_API_KEY /
BINANCE_SECRET_KEY are provided by the owner — construction succeeds but any
network method raises RuntimeError until configured. No code path here can
place a live order without passing through RiskEngine.validate_order() first
(enforced by the execution loop, not by this adapter).

Withdrawal permission must NEVER be enabled on the API key (see spec).
"""
from __future__ import annotations

import logging
import os
import time
from decimal import Decimal
from typing import Optional

import pandas as pd

from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.order_models import AccountInfo, OrderRequest, OrderResult, Position

logger = logging.getLogger(__name__)

PRIORITY_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
TIME_SYNC_TOLERANCE_MS = 1000


class BinanceCredentialsMissing(RuntimeError):
    """Raised when a network operation is attempted without API credentials configured."""


class BinanceSpotAdapter(AbstractExchangeAdapter):
    """
    Thin wrapper around python-binance's Client. Never instantiates the
    client until first network call, so construction is always safe (e.g.
    for CI, for type-checking) even with no credentials present.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        testnet: bool = True,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("BINANCE_API_KEY")
        self.secret_key = secret_key or os.environ.get("BINANCE_SECRET_KEY")
        self.testnet = testnet if "BINANCE_TESTNET" not in os.environ else (
            os.environ["BINANCE_TESTNET"].lower() == "true"
        )
        self.base_url = base_url or os.environ.get("BINANCE_BASE_URL")

        self._client = None  # lazily constructed python-binance Client
        self._exchange_info_cache: Optional[dict] = None
        self._exchange_info_cached_at: float = 0.0
        self._server_time_offset_ms: int = 0
        self._connected = False

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _require_credentials(self) -> None:
        if not self.has_credentials:
            raise BinanceCredentialsMissing(
                "BINANCE_API_KEY / BINANCE_SECRET_KEY not configured. "
                "This adapter cannot reach the exchange until the owner provides them."
            )

    def _get_client(self):
        self._require_credentials()
        if self._client is None:
            from binance.client import Client  # local import: no hard dependency until used

            kwargs = {"api_key": self.api_key, "api_secret": self.secret_key, "testnet": self.testnet}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = Client(**kwargs)
        return self._client

    # ------------------------------------------------------------------
    # Startup sequence (per docs/BINANCE_INTEGRATION_NOTES.md)
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        1. Verify connectivity (ping)
        2. Sync server time
        3. Load exchangeInfo (cache 1h)
        4. Verify API key permissions (read + trading required, NOT withdraw)
        """
        client = self._get_client()
        client.ping()
        server_time = client.get_server_time()["serverTime"]
        self._server_time_offset_ms = server_time - int(time.time() * 1000)

        self._load_exchange_info(force=True)
        self._verify_permissions(client)
        self._connected = True
        logger.info("BinanceSpotAdapter connected (testnet=%s)", self.testnet)

    def _verify_permissions(self, client) -> None:
        account = client.get_account()
        permissions = account.get("permissions", [])
        if "SPOT" not in permissions:
            raise RuntimeError(f"API key missing SPOT trading permission: {permissions}")
        # python-binance's get_account() does not expose withdrawal permission
        # directly in all API versions — this must be manually verified by the
        # owner in the Binance UI when creating the key (see spec: NO withdrawal
        # permission, ever). We cannot programmatically guarantee its absence.
        logger.info("Binance API key permissions verified: %s", permissions)

    def _load_exchange_info(self, force: bool = False) -> dict:
        now = time.time()
        if not force and self._exchange_info_cache and (now - self._exchange_info_cached_at) < 3600:
            return self._exchange_info_cache
        client = self._get_client()
        self._exchange_info_cache = client.get_exchange_info()
        self._exchange_info_cached_at = now
        return self._exchange_info_cache

    def _symbol_filters(self, symbol: str) -> dict:
        info = self._load_exchange_info()
        for s in info["symbols"]:
            if s["symbol"] == symbol:
                return {f["filterType"]: f for f in s["filters"]}
        raise ValueError(f"Symbol {symbol} not found in exchangeInfo")

    def round_to_lot_size(self, symbol: str, quantity: Decimal) -> Decimal:
        filters = self._symbol_filters(symbol)
        step_size = Decimal(filters["LOT_SIZE"]["stepSize"])
        if step_size == 0:
            return quantity
        return (quantity // step_size) * step_size  # round DOWN to step, never up

    def round_to_tick_size(self, symbol: str, price: Decimal) -> Decimal:
        filters = self._symbol_filters(symbol)
        tick_size = Decimal(filters["PRICE_FILTER"]["tickSize"])
        if tick_size == 0:
            return price
        return (price // tick_size) * tick_size

    def meets_min_notional(self, symbol: str, price: Decimal, quantity: Decimal) -> bool:
        filters = self._symbol_filters(symbol)
        min_notional = Decimal(filters.get("MIN_NOTIONAL", {}).get("minNotional", "0"))
        return (price * quantity) >= min_notional

    # ------------------------------------------------------------------
    # AbstractExchangeAdapter interface
    # ------------------------------------------------------------------

    def submit_order(self, order: OrderRequest) -> OrderResult:
        client = self._get_client()
        quantity = self.round_to_lot_size(order.symbol, order.quantity)
        if quantity <= 0:
            return OrderResult(
                client_order_id=order.client_order_id, status="REJECTED", symbol=order.symbol,
                side=order.side, requested_quantity=order.quantity,
                reject_reason="quantity rounds to zero after lot size filter",
            )

        params = {
            "symbol": order.symbol,
            "side": order.side,
            "type": order.order_type,
            "quantity": str(quantity),
            "newClientOrderId": order.client_order_id,
        }
        if order.order_type == "LIMIT":
            if order.limit_price is None:
                return OrderResult(
                    client_order_id=order.client_order_id, status="REJECTED", symbol=order.symbol,
                    side=order.side, requested_quantity=order.quantity,
                    reject_reason="LIMIT order requires limit_price",
                )
            params["price"] = str(self.round_to_tick_size(order.symbol, order.limit_price))
            params["timeInForce"] = "GTC"

        response = client.create_order(**params)
        return OrderResult(
            client_order_id=order.client_order_id,
            status="SUBMITTED",
            symbol=order.symbol,
            side=order.side,
            requested_quantity=quantity,
            exchange_order_id=str(response.get("orderId")),
            submitted_at=str(response.get("transactTime")),
        )

    def cancel_order(self, client_order_id: str) -> bool:
        raise NotImplementedError(
            "cancel_order requires tracking symbol per client_order_id — "
            "implement once order tracking (persistence layer) is in place"
        )

    def get_position(self, symbol: str) -> Optional[Position]:
        client = self._get_client()
        base_asset = symbol.replace("USDT", "").replace("BUSD", "")
        account = client.get_account()
        for balance in account["balances"]:
            if balance["asset"] == base_asset:
                free = Decimal(balance["free"])
                if free > 0:
                    return Position(
                        symbol=symbol, quantity=free,
                        avg_entry_price=Decimal("0"),  # not tracked by exchange; use trade DB
                        entry_fee=Decimal("0"),
                    )
        return None

    def get_account_info(self) -> AccountInfo:
        client = self._get_client()
        account = client.get_account()
        cash_balance = Decimal("0")
        for balance in account["balances"]:
            if balance["asset"] == "USDT":
                cash_balance = Decimal(balance["free"])
        return AccountInfo(
            equity=cash_balance,  # mark-to-market of positions added by caller
            cash_balance=cash_balance,
            positions=[],
            is_paper=False,
        )

    def get_current_price(self, symbol: str) -> Decimal:
        client = self._get_client()
        ticker = client.get_symbol_ticker(symbol=symbol)
        return Decimal(ticker["price"])

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        client = self._get_client()
        klines = client.get_klines(symbol=symbol, interval=timeframe, limit=limit)
        df = pd.DataFrame(
            klines,
            columns=[
                "open_time", "open", "high", "low", "close", "volume", "close_time",
                "quote_asset_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
            ],
        )
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df.set_index("open_time")
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        return df[["open", "high", "low", "close", "volume"]]

    def is_connected(self) -> bool:
        if not self.has_credentials:
            return False
        try:
            self._get_client().ping()
            return True
        except Exception:
            logger.exception("Binance connectivity check failed")
            return False

    def get_exchange_name(self) -> str:
        return "binance_spot_testnet" if self.testnet else "binance_spot"
