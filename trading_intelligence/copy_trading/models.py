"""Data model for copy trading: who a trader is, what their record shows, and what
they do (leader events)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class Market(str, Enum):
    SPOT = "SPOT"
    USDM_FUTURES = "USDM_FUTURES"


class LeaderAction(str, Enum):
    OPEN = "OPEN"
    INCREASE = "INCREASE"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class ReportedStats:
    """What a lead-trader page in the Binance app shows, as reported (percentages as
    displayed, e.g. 12.5 = 12.5%). Used when no daily series is available."""

    roi_pct_by_days: dict[int, Decimal]  # e.g. {7: 1.2, 30: 4.0, 90: 9.5, 180: 21.0}
    max_drawdown_pct: Decimal
    lead_days: int
    trades: int
    win_rate_pct: Optional[Decimal] = None


@dataclass(frozen=True)
class TraderRecord:
    """What is known about one lead trader at `captured_at`, from one source.

    `daily_returns` is the trader's daily return series as fractions (0.012 = +1.2%),
    oldest first, ending at `captured_at`. Traders that stopped leading (`active=False`)
    MUST be kept in the universe: dropping them is survivorship bias.
    """

    trader_id: str
    name: str
    market: Market
    source: str
    captured_at: datetime
    active: bool
    daily_returns: tuple[Decimal, ...]
    profit_share_pct: Decimal = Decimal("10")
    aum_usd: Optional[Decimal] = None
    copiers: Optional[int] = None
    max_leverage: Decimal = Decimal("1")
    symbol_share: dict[str, Decimal] = field(default_factory=dict)  # share of traded notional per symbol
    closed_trade_pnls: tuple[Decimal, ...] = ()  # realized PnL per closed trade, for concentration
    reported: Optional[ReportedStats] = None  # app figures, when no daily series exists

    @property
    def history_days(self) -> int:
        if not self.daily_returns and self.reported is not None:
            return self.reported.lead_days
        return len(self.daily_returns)

    @property
    def start_date(self) -> date:
        return date.fromordinal(self.captured_at.date().toordinal() - self.history_days + 1)


@dataclass(frozen=True)
class LeaderEvent:
    """A change in a leader's position. `target_fraction` is the leader's position
    notional AFTER the event as a fraction of the leader's portfolio equity (0 after a
    CLOSE). Copying a target, not a delta, means a missed or failed event is healed by
    the next one instead of compounding."""

    trader_id: str
    ts: datetime
    symbol: str
    action: LeaderAction
    side: Side
    price: Decimal
    target_fraction: Decimal
    leverage: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.price <= 0 or not self.price.is_finite():
            raise ValueError(f"leader event price must be finite and > 0, got {self.price}")
        if self.target_fraction < 0 or not self.target_fraction.is_finite():
            raise ValueError(f"target_fraction must be finite and >= 0, got {self.target_fraction}")
        if self.action is LeaderAction.CLOSE and self.target_fraction != 0:
            raise ValueError("a CLOSE event must have target_fraction 0")
        if self.leverage < 1:
            raise ValueError("leverage must be >= 1")
