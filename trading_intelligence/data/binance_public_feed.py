"""
Binance PUBLIC market data, nothing else: no account, no API key, no order
endpoint, no third-party dependency (standard library HTTP only).

Default host is `data-api.binance.vision`, Binance's public market-data-only
endpoint. Klines are returned exactly as the exchange reports them, including
the still-forming last bar; PaperLoop drops that bar itself.

Every method that could touch an account or an order raises: this adapter can
be handed to PaperAdapter / PaperLoop as their market-data source and can never
become an execution path by mistake.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from decimal import Decimal
from typing import Callable, Optional

import pandas as pd

from trading_intelligence.execution.base import AbstractExchangeAdapter

DEFAULT_BASE_URL = "https://data-api.binance.vision"
_SYMBOL = re.compile(r"^[A-Z0-9]{2,20}$")
_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}


def _check_kline(symbol: str, row: dict) -> None:
    """A bar that cannot have happened is a data error, never a price to trade on.
    Found by GPT Work (PR #8): NaN/Infinity, a high below open or close, and a
    negative volume used to pass."""
    o, h, low, c, v = row["open"], row["high"], row["low"], row["close"], row["volume"]
    if not all(math.isfinite(x) for x in (o, h, low, c, v)):
        raise ValueError(f"non-finite kline for {symbol} at {row['open_time']}")
    if min(o, h, low, c) <= 0 or v < 0:
        raise ValueError(f"impossible OHLCV for {symbol} at {row['open_time']}: non-positive price or negative volume")
    if h < max(o, c, low) or low > min(o, c, h):
        raise ValueError(f"impossible OHLC for {symbol} at {row['open_time']}: high/low do not bound open/close")


class MarketDataOnly(RuntimeError):
    """Raised by every account/order method: this adapter cannot trade."""


def _urllib_get(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "trading-intelligence-paper/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https host is fixed/validated)
        return response.read()


class BinancePublicKlines(AbstractExchangeAdapter):
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 15.0,
        fetch: Optional[Callable[[str, float], bytes]] = None,
    ):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"base_url must be an https URL, got {base_url!r}")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._fetch = fetch or _urllib_get

    def _get(self, path: str, params: dict) -> object:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}" if params else f"{self.base_url}{path}"
        return json.loads(self._fetch(url, self.timeout))

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        if not _SYMBOL.match(symbol):
            raise ValueError(f"invalid symbol {symbol!r}")
        if timeframe not in _INTERVALS:
            raise ValueError(f"invalid interval {timeframe!r}")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be in [1, 1000]")
        payload = self._get("/api/v3/klines", {"symbol": symbol, "interval": timeframe, "limit": limit})
        if not isinstance(payload, list):
            raise ValueError(f"unexpected klines payload for {symbol}: {str(payload)[:200]}")
        rows = []
        for k in payload:
            if not isinstance(k, list) or len(k) < 6:
                raise ValueError(f"malformed kline for {symbol}: {str(k)[:200]}")
            rows.append({
                "open_time": int(k[0]),
                "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                "close": float(k[4]), "volume": float(k[5]),
            })
        for row in rows:
            _check_kline(symbol, row)
        frame = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume"])
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        return frame.set_index("open_time")

    def get_current_price(self, symbol: str) -> Decimal:
        if not _SYMBOL.match(symbol):
            raise ValueError(f"invalid symbol {symbol!r}")
        payload = self._get("/api/v3/ticker/price", {"symbol": symbol})
        if not isinstance(payload, dict) or "price" not in payload:
            raise ValueError(f"unexpected price payload for {symbol}")
        price = Decimal(str(payload["price"]))
        if not price.is_finite() or price <= 0:
            raise ValueError(f"impossible price for {symbol}: {payload['price']!r}")
        return price

    def is_connected(self) -> bool:
        try:
            self._get("/api/v3/ping", {})
            return True
        except Exception:
            return False

    def get_exchange_name(self) -> str:
        return "binance_public_data"

    # ------------------------------------------------------------------
    # Never an execution path
    # ------------------------------------------------------------------

    def submit_order(self, order):
        raise MarketDataOnly("BinancePublicKlines is market data only; it cannot place orders")

    def cancel_order(self, client_order_id):
        raise MarketDataOnly("BinancePublicKlines is market data only; it cannot cancel orders")

    def get_position(self, symbol):
        raise MarketDataOnly("BinancePublicKlines has no account")

    def get_account_info(self):
        raise MarketDataOnly("BinancePublicKlines has no account")
