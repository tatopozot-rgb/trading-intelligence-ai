"""Data models for strategy signals and trade proposals."""
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Optional


@dataclass
class SignalEvent:
    strategy_id: str
    symbol: str
    direction: Literal["BUY", "EXIT"]
    timeframe: str
    bar_time: str           # ISO timestamp of the signal bar close
    close_price: Decimal
    strength: float         # 0.0 – 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class TradeProposal:
    strategy_id: str
    symbol: str
    side: Literal["BUY"]   # spot-only: long only
    entry_type: Literal["MARKET", "LIMIT"]
    stop_price: Decimal     # REQUIRED — no stop, no proposal
    timeframe: str
    rationale: str
    signal_strength: float
    timestamp: str          # ISO timestamp when proposal was created
    entry_price: Optional[Decimal] = None   # for LIMIT; None for MARKET
    target_price: Optional[Decimal] = None  # optional
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class RiskDecision:
    """Placeholder until risk engine is implemented by Codex."""
    approved: bool
    reason: str
    quantity: Optional[Decimal] = None   # set only when approved
    proposal_id: str = ""
