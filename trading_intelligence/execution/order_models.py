"""Order request/result models shared by all exchange adapters."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Optional

OrderStatus = Literal["PENDING", "SUBMITTED", "FILLED", "REJECTED", "CANCELLED", "EXPIRED"]


@dataclass
class OrderRequest:
    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT", "STOP"]
    quantity: Decimal
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class OrderResult:
    client_order_id: str
    status: OrderStatus
    symbol: str
    side: Literal["BUY", "SELL"]
    requested_quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    fill_price: Optional[Decimal] = None
    fee: Decimal = Decimal("0")
    exchange_order_id: Optional[str] = None
    submitted_at: Optional[str] = None
    filled_at: Optional[str] = None
    reject_reason: Optional[str] = None


@dataclass
class Position:
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    entry_fee: Decimal
    position_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class AccountInfo:
    equity: Decimal
    cash_balance: Decimal
    positions: list[Position]
    is_paper: bool
