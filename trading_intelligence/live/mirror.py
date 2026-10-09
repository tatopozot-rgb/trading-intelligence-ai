"""
Turns the decision engine's positions into real orders for one session.

Targets are fractions of equity per symbol (from the PAPER engine, or from a lead
trader's positions read live in the app). A real order is sent only when a position
must open, close, or change by a meaningful amount; buys are limited by the owner's
limits, the session's own cash and the account's free USDT; sells never exceed what
this session bought. Live stop: if the price is at or below the engine's protective
stop, the position is sold at once, without waiting for the next bar.

Guard stop: each position also has a STOP_LOSS order resting on Binance at the engine's
stop, so it is protected while the PC is off or the operator is down. Before the operator
sells a symbol it cancels that order; if Binance had already executed it, the operator
records that sale and sends nothing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping, Optional, Protocol

from trading_intelligence.live.binance_live import Fill, LiveError, StopState, SymbolRules
from trading_intelligence.live.limits import OwnerLimits
from trading_intelligence.live.session import Session

logger = logging.getLogger(__name__)
REBALANCE_THRESHOLD = Decimal("0.25")  # ignore drifts under 25% of the position


class Trader(Protocol):
    def price(self, symbol: str) -> Decimal: ...
    def rules(self, symbol: str) -> SymbolRules: ...
    def free_balance(self, asset: str) -> Decimal: ...
    def market_order(self, symbol: str, side: str, quantity: Decimal,
                     fee_price: Callable[[str], Decimal]) -> Fill: ...
    def place_stop(self, symbol: str, quantity: Decimal, stop_price: Decimal) -> str: ...
    def stop_status(self, symbol: str, client_id: str, fee_price: Callable[[str], Decimal]) -> StopState: ...
    def cancel_stop(self, symbol: str, client_id: str, fee_price: Callable[[str], Decimal]) -> StopState: ...


@dataclass
class Action:
    symbol: str
    kind: str  # BUY | SELL | SKIP
    reason: str
    usdt: Decimal = Decimal("0")


def _apply_fill(session: Session, fill: Fill, reason: str) -> None:
    if fill.executed_qty <= 0:
        return
    if fill.side == "BUY":
        session.record_buy(fill.symbol, fill.executed_qty, fill.quote_qty + fill.fee_other_usdt, fill.fee_usdt, reason)
    else:
        session.record_sell(fill.symbol, fill.executed_qty, fill.quote_qty - fill.fee_other_usdt, fill.fee_usdt, reason)


GONE = ("CANCELED", "EXPIRED", "REJECTED", "NOT_FOUND", "FILLED", "EXPIRED_IN_MATCH")


def _settle_guard(session: Session, symbol: str, state: StopState) -> bool:
    """Applies what Binance reports about a guard stop. True when the guard is gone."""
    if state.fill is not None and state.fill.executed_qty > 0:
        _apply_fill(session, state.fill, f"EXCHANGE_STOP:{session.guard_stops[symbol]['stop']}")
    if state.status in GONE:
        session.guard_stops.pop(symbol, None)
        return True
    return False


def release_guard(session: Session, trader: Trader, symbol: str) -> bool:
    """Cancels the symbol's guard stop before the operator trades it. True when no guard
    is left (cancelled, executed or absent); False when Binance's answer was unclear."""
    guard = session.guard_stops.get(symbol)
    if guard is None:
        return True
    if guard.get("id") is None:  # a refused placement: nothing rests on Binance
        session.guard_stops.pop(symbol)
        return True
    return _settle_guard(session, symbol, trader.cancel_stop(symbol, guard["id"], trader.price))


def sync_guards(session: Session, trader: Trader) -> list[Action]:
    """Each pass: did Binance execute a guard stop (PC off, or between polls)? Record it."""
    out = []
    for sym in sorted(session.guard_stops):
        guard = session.guard_stops[sym]
        if guard.get("id") is None:
            continue
        state = trader.stop_status(sym, guard["id"], trader.price)
        if state.fill is not None and state.fill.executed_qty > 0:
            out.append(Action(sym, "SELL", f"EXCHANGE_STOP:{guard['stop']}", state.fill.quote_qty))
        _settle_guard(session, sym, state)
    return out


def place_guards(session: Session, trader: Trader, stops: Mapping[str, Decimal],
                 prices: Mapping[str, Decimal]) -> list[Action]:
    """Keeps one guard stop per held symbol at the engine's stop, for the whole quantity held."""
    out = []
    for sym in sorted(session.holdings):
        stop = stops.get(sym)
        if stop is None:
            continue
        rules = trader.rules(sym)
        qty = rules.floor_qty(session.holdings[sym].qty)
        stop_px = rules.floor_price(stop)
        guard = session.guard_stops.get(sym)
        if guard is not None and Decimal(guard["qty"]) == qty and Decimal(guard["stop"]) == stop_px:
            continue
        if not rules.stop_loss or stop_px <= 0 or stop_px >= prices.get(sym, Decimal("0")):
            continue  # the operator's own one-minute stop still applies
        if qty <= 0 or qty < rules.min_qty or qty * stop_px < rules.min_notional:
            continue
        if not release_guard(session, trader, sym) or sym not in session.holdings:
            continue  # unclear answer, or the old guard executed: decide again next pass
        try:
            cid = trader.place_stop(sym, qty, stop_px)
        except LiveError as error:
            # Remembered with its qty and stop, so the same refused order is not re-sent every
            # minute; a new stop or quantity tries again. The one-minute operator stop still applies.
            session.guard_stops[sym] = {"id": None, "qty": str(qty), "stop": str(stop_px)}
            out.append(Action(sym, "SKIP", f"GUARD_STOP_NOT_PLACED:{error}"))
            continue
        session.guard_stops[sym] = {"id": cid, "qty": str(qty), "stop": str(stop_px)}
        out.append(Action(sym, "GUARD", f"GUARD_STOP_AT:{stop_px}"))
    return out


def sell(session: Session, trader: Trader, symbol: str, reason: str, *,
         qty: Optional[Decimal] = None) -> Action:
    if symbol in session.guard_stops:
        if not release_guard(session, trader, symbol):
            return Action(symbol, "SKIP", "GUARD_STOP_UNCLEAR:retry next pass")  # never sell twice
        if symbol not in session.holdings:
            return Action(symbol, "SELL", "EXCHANGE_STOP_ALREADY_EXECUTED")
        # A partly executed guard is cancelled now, so the rest is sold below, unprotected no more.
    held = session.holdings.get(symbol)
    if held is None:
        return Action(symbol, "SKIP", "NOTHING_HELD")
    rules = trader.rules(symbol)
    price = trader.price(symbol)
    want = held.qty if qty is None else min(qty, held.qty)
    q = rules.floor_qty(want)
    if q <= 0 or q < rules.min_qty or q * price < rules.min_notional:
        return Action(symbol, "SKIP", f"DUST_BELOW_EXCHANGE_MINIMUM:{(held.qty * price):.2f}")
    fill = trader.market_order(symbol, "SELL", q, trader.price)
    _apply_fill(session, fill, reason)
    return Action(symbol, "SELL", reason, fill.quote_qty)


def apply_targets(session: Session, trader: Trader, targets: Mapping[str, Decimal], limits: OwnerLimits,
                  prices: Mapping[str, Decimal], reason: str) -> list[Action]:
    """targets: symbol -> fraction of session equity (0 = no position)."""
    actions: list[Action] = []
    equity = session.equity(prices)
    symbols = sorted(set(targets) | set(session.holdings))
    # Sells first: they free cash for buys in the same pass.
    for sym in symbols:
        frac = targets.get(sym, Decimal("0"))
        held = session.holdings.get(sym)
        if held is None:
            continue
        current = held.qty * prices[sym]
        target = equity * min(frac, limits.max_position_pct / 100)
        if frac <= 0:
            actions.append(sell(session, trader, sym, f"{reason}:CLOSE"))
        elif current - target > current * REBALANCE_THRESHOLD:
            actions.append(sell(session, trader, sym, f"{reason}:REDUCE", qty=(current - target) / prices[sym]))
    for sym in symbols:
        frac = targets.get(sym, Decimal("0"))
        if frac <= 0:
            continue
        if sym not in limits.allowed_symbols:
            actions.append(Action(sym, "SKIP", "SYMBOL_NOT_APPROVED"))
            continue
        held = session.holdings.get(sym)
        current = held.qty * prices[sym] if held else Decimal("0")
        target = equity * min(frac, limits.max_position_pct / 100)
        gap = target - current
        if held is not None and gap <= target * REBALANCE_THRESHOLD:
            continue
        if held is not None and prices[sym] < held.avg_cost:
            actions.append(Action(sym, "SKIP", "NO_ADDING_TO_A_LOSING_POSITION"))
            continue
        if not session.may_buy:
            actions.append(Action(sym, "SKIP", f"SESSION_{session.status}"))
            continue
        if held is None and len(session.holdings) >= limits.max_open_positions:
            actions.append(Action(sym, "SKIP", "MAX_OPEN_POSITIONS"))
            continue
        spend = min(gap, session.available, trader.free_balance("USDT"))
        rules = trader.rules(sym)
        q = rules.floor_qty(spend * Decimal("0.998") / prices[sym])  # keep room for fees and price moves
        if q <= 0 or q < rules.min_qty or q * prices[sym] < rules.min_notional:
            actions.append(Action(sym, "SKIP", f"BELOW_EXCHANGE_MINIMUM:{spend:.2f}<{rules.min_notional}"))
            continue
        fill = trader.market_order(sym, "BUY", q, trader.price)
        _apply_fill(session, fill, f"{reason}:OPEN" if held is None else f"{reason}:ADD")
        actions.append(Action(sym, "BUY", reason, fill.quote_qty))
    return actions


def enforce_stops(session: Session, trader: Trader, stops: Mapping[str, Decimal],
                  prices: Mapping[str, Decimal]) -> list[Action]:
    out = []
    for sym, stop in stops.items():
        if sym in session.holdings and prices.get(sym, Decimal("Infinity")) <= stop:
            out.append(sell(session, trader, sym, f"STOP_HIT:{stop}"))
    return out


def flatten(session: Session, trader: Trader, reason: str) -> list[Action]:
    return [sell(session, trader, sym, reason) for sym in sorted(session.holdings)]
