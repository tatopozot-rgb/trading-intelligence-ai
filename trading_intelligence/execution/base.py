"""
AbstractExchangeAdapter — the interface every exchange backend implements.

Strategy/risk layers never instantiate an adapter directly; they receive one
via dependency injection, so paper/live switching is a configuration change,
never a code change. Per docs/SYSTEM_ARCHITECTURE.md.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

import pandas as pd

from trading_intelligence.execution.order_models import AccountInfo, OrderRequest, OrderResult, Position


class AbstractExchangeAdapter(ABC):
    """Common interface for BinanceSpotAdapter, PaperAdapter, and future adapters (XM/MT5)."""

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> OrderResult:
        """Submit an order. The caller MUST have already passed RiskEngine.validate_order()."""
        ...

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> bool:
        """Cancel a pending order. Returns True if cancelled, False if already filled/gone."""
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None:
        """Current open position for symbol, or None if flat."""
        ...

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """Current equity, cash balance, and all open positions."""
        ...

    @abstractmethod
    def get_current_price(self, symbol: str) -> Decimal:
        """Latest traded price for symbol."""
        ...

    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        """Historical OHLCV bars, most recent last. Columns: open, high, low, close, volume."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Connectivity check. The risk engine's connectivity watchdog depends on this."""
        ...

    @abstractmethod
    def get_exchange_name(self) -> str:
        """e.g. 'binance_spot', 'paper', 'xm_mt5'."""
        ...
