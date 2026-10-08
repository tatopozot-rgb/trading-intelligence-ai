"""
Copy-trading risk: what to do with each leader event and each mark, on top of the
project's RiskEngine (kill switch, daily loss limit, drawdown pause/halt, open-position
and total-exposure caps stay final and non-bypassable).

A copied position in loss is not closed mechanically:
- loss within the temporary-drawdown envelope while the leader still holds -> HOLD;
- loss beyond the envelope -> HOLD and watch, unless the market regime has turned
  against the position, which invalidates the thesis -> EXIT;
- loss at the hard stop -> EXIT, whatever the leader or the regime say.

No martingale: a losing copy is never added to, and a leader who keeps adding to a
losing position is blocked (and our copy of it exited).

Every value in CopyRiskConfig is a PROPOSED research default, not an owner decision;
LIVE values are WAITING_FOR_USER.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from trading_intelligence.copy_trading.models import LeaderAction, LeaderEvent, Side
from trading_intelligence.risk.engine import RiskEngine

HOSTILE_TO_LONG = frozenset({"TREND_DOWN", "BREAKOUT_DOWN"})
HOSTILE_TO_SHORT = frozenset({"TREND_UP", "BREAKOUT_UP"})

# Decision actions
COPY_OPEN = "COPY_OPEN"
COPY_RESIZE = "COPY_RESIZE"
COPY_EXIT = "COPY_EXIT"
HOLD = "HOLD"
NO_TRADE = "NO_TRADE"
SKIP = "SKIP"
BLOCK_TRADER = "BLOCK_TRADER"


@dataclass(frozen=True)
class CopyRiskConfig:
    per_trader_allocation_pct: Decimal = Decimal("30")  # of our equity, per followed trader
    max_position_pct: Decimal = Decimal("15")  # any single copied position, of our equity
    max_leverage: Decimal = Decimal("1")
    hard_stop_loss_pct: Decimal = Decimal("12")
    temporary_drawdown_envelope_pct: Decimal = Decimal("6")
    martingale_max_losing_adds: int = 2
    trader_loss_budget_pct: Decimal = Decimal("5")  # realized loss following one trader, of starting equity
    allow_short: bool = False  # Binance Spot cannot short

    def __post_init__(self) -> None:
        for name in ("per_trader_allocation_pct", "max_position_pct", "hard_stop_loss_pct",
                     "temporary_drawdown_envelope_pct", "trader_loss_budget_pct"):
            v = getattr(self, name)
            if not v.is_finite() or v <= 0 or v > 100:
                raise ValueError(f"{name} must be in (0, 100], got {v}")
        if self.temporary_drawdown_envelope_pct >= self.hard_stop_loss_pct:
            raise ValueError("the temporary-drawdown envelope must be tighter than the hard stop")
        if self.max_leverage < 1 or self.martingale_max_losing_adds < 0:
            raise ValueError("max_leverage must be >= 1 and martingale_max_losing_adds >= 0")


@dataclass
class CopyDecision:
    action: str
    reason: str
    target_notional: Decimal = Decimal("0")


@dataclass
class PositionView:
    """What the policy needs to know about our copy of one (trader, symbol)."""

    notional: Decimal  # current market value
    avg_entry: Decimal
    side: Side


def loss_pct(view: PositionView, price: Decimal) -> Decimal:
    if view.avg_entry <= 0:
        return Decimal("0")
    move = (view.avg_entry - price) / view.avg_entry * 100
    return move if view.side is Side.LONG else -move


class CopyRiskPolicy:
    def __init__(self, config: CopyRiskConfig, engine: RiskEngine):
        self.config = config
        self.engine = engine

    def target_notional(self, equity: Decimal, event: LeaderEvent) -> tuple[Decimal, list[str]]:
        notes = []
        leverage = event.leverage
        if leverage > self.config.max_leverage:
            notes.append(f"LEVERAGE_CLIPPED:{event.leverage}->{self.config.max_leverage}")
            leverage = self.config.max_leverage
        target = equity * self.config.per_trader_allocation_pct / 100 * event.target_fraction * leverage
        cap = equity * self.config.max_position_pct / 100
        if target > cap:
            notes.append("POSITION_CAP")
            target = cap
        return target, notes

    def on_leader_event(
        self, event: LeaderEvent, equity: Decimal, current: Optional[PositionView], *,
        trader_followed: bool, trader_blocked: bool, leader_losing_adds: int, leader_underwater: bool,
        exposure_excluding_this: Decimal, exited_until_leader_closes: bool,
    ) -> CopyDecision:
        current_notional = current.notional if current else Decimal("0")
        if event.action is LeaderAction.CLOSE:
            if current is None:
                return CopyDecision(NO_TRADE, "NOTHING_TO_CLOSE")
            return CopyDecision(COPY_EXIT, "LEADER_CLOSED")
        if event.action is LeaderAction.REDUCE:
            if current is None:
                return CopyDecision(NO_TRADE, "NOTHING_TO_REDUCE")
            target, _ = self.target_notional(equity, event)
            # A reduction is never blocked and never turns into an increase.
            return CopyDecision(COPY_RESIZE, "LEADER_REDUCED", min(target, current_notional))

        # OPEN / INCREASE from here: new risk.
        if event.action is LeaderAction.INCREASE and leader_underwater:
            if leader_losing_adds + 1 > self.config.martingale_max_losing_adds:
                return CopyDecision(BLOCK_TRADER, "LEADER_MARTINGALE")
        if trader_blocked:
            return CopyDecision(NO_TRADE, "TRADER_BLOCKED")
        if not trader_followed:
            return CopyDecision(NO_TRADE, "TRADER_NOT_SELECTED")
        if exited_until_leader_closes:
            return CopyDecision(NO_TRADE, "EXITED_UNTIL_LEADER_CLOSES")
        if event.side is Side.SHORT and not self.config.allow_short:
            return CopyDecision(SKIP, "SHORT_NOT_SUPPORTED_ON_SPOT")
        if current is not None and current.side is not event.side:
            return CopyDecision(NO_TRADE, "SIDE_FLIP_NOT_COPIED")
        if current is not None and loss_pct(current, event.price) > 0:
            return CopyDecision(HOLD, "NO_ADDING_TO_A_LOSING_POSITION")
        block = self.engine.entry_block_reason()
        if block:
            return CopyDecision(NO_TRADE, f"RISK_ENGINE:{block}")
        if current is None and self.engine.open_position_count >= self.engine.config.max_open_positions:
            return CopyDecision(NO_TRADE, "RISK_ENGINE:MAX_OPEN_POSITIONS")

        target, notes = self.target_notional(equity, event)
        room = equity * Decimal(str(self.engine.config.max_total_exposure_pct)) / 100 - exposure_excluding_this
        if target > room:
            notes.append("TOTAL_EXPOSURE_CAP")
            target = max(room, Decimal("0"))
        if target <= current_notional:
            return CopyDecision(HOLD, "AT_OR_ABOVE_TARGET" + ("|" + "|".join(notes) if notes else ""), current_notional)
        action = COPY_OPEN if current is None else COPY_RESIZE
        reason = "LEADER_OPENED" if event.action is LeaderAction.OPEN else "LEADER_INCREASED"
        return CopyDecision(action, reason + ("|" + "|".join(notes) if notes else ""), target)

    def on_mark(self, view: PositionView, price: Decimal, regime: Optional[str]) -> CopyDecision:
        loss = loss_pct(view, price)
        if loss >= self.config.hard_stop_loss_pct:
            return CopyDecision(COPY_EXIT, "HARD_STOP")
        if loss <= self.config.temporary_drawdown_envelope_pct:
            return CopyDecision(HOLD, "TEMPORARY_DRAWDOWN" if loss > 0 else "IN_PROFIT", view.notional)
        hostile = HOSTILE_TO_LONG if view.side is Side.LONG else HOSTILE_TO_SHORT
        if regime in hostile:
            return CopyDecision(COPY_EXIT, f"THESIS_INVALIDATED_REGIME:{regime}")
        return CopyDecision(HOLD, "WATCH_BEYOND_ENVELOPE", view.notional)
