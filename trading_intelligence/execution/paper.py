"""
PaperAdapter — simulates fills, never sends orders to a real exchange.

Per docs/PAPER_TRADING_SIMULATION_SPEC.md and docs/SYSTEM_ARCHITECTURE.md:
"PaperAdapter: wraps any adapter, intercepts orders, simulates fills."

Market data (OHLCV, current price, connectivity) is proxied from a wrapped
AbstractExchangeAdapter (e.g. BinanceSpotAdapter used read-only). Orders are
NEVER forwarded to that adapter — they are queued and filled internally using
the next-bar execution model: an order submitted after bar T's close fills at
bar T+1's open, when on_new_bar() is called with that next bar.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Optional

import pandas as pd

from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.order_models import (
    AccountInfo,
    OrderRequest,
    OrderResult,
    Position,
)

logger = logging.getLogger(__name__)

TAKER_FEE = Decimal("0.001")
SLIPPAGE_RATE = Decimal("0.0005")  # 5 bps, per spec


@dataclass
class _Bar:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    time: str


class PaperAdapter(AbstractExchangeAdapter):
    def __init__(
        self,
        market_data_adapter: AbstractExchangeAdapter,
        initial_equity: Decimal,
        state_path: Optional[Path] = None,
        taker_fee: Decimal = TAKER_FEE,
        slippage_rate: Decimal = SLIPPAGE_RATE,
    ):
        self._market_data_adapter = market_data_adapter
        self.taker_fee = taker_fee
        self.slippage_rate = slippage_rate
        self.state_path = Path(state_path) if state_path else None

        self.cash: Decimal = initial_equity
        self.positions: dict[str, Position] = {}
        self.pending_orders: list[OrderRequest] = []
        self.order_history: list[OrderResult] = []
        self._last_price: dict[str, Decimal] = {}

        if self.state_path and self.state_path.exists():
            self._load_state()

    # ------------------------------------------------------------------
    # Market data — proxied, read-only
    # ------------------------------------------------------------------

    def get_current_price(self, symbol: str) -> Decimal:
        if symbol in self._last_price:
            return self._last_price[symbol]
        return self._market_data_adapter.get_current_price(symbol)

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        return self._market_data_adapter.get_ohlcv(symbol, timeframe, limit)

    def is_connected(self) -> bool:
        return self._market_data_adapter.is_connected()

    def get_exchange_name(self) -> str:
        return f"paper[{self._market_data_adapter.get_exchange_name()}]"

    # ------------------------------------------------------------------
    # Order submission — intercepted, never forwarded
    # ------------------------------------------------------------------

    def submit_order(self, order: OrderRequest) -> OrderResult:
        if order.quantity <= 0:
            result = OrderResult(
                client_order_id=order.client_order_id, status="REJECTED", symbol=order.symbol,
                side=order.side, requested_quantity=order.quantity,
                reject_reason="quantity must be > 0",
            )
            self.order_history.append(result)
            return result

        if self._is_duplicate_order(order.client_order_id):
            result = OrderResult(
                client_order_id=order.client_order_id, status="REJECTED", symbol=order.symbol,
                side=order.side, requested_quantity=order.quantity,
                reject_reason="duplicate client_order_id — already submitted",
            )
            self.order_history.append(result)
            return result

        self.pending_orders.append(order)
        result = OrderResult(
            client_order_id=order.client_order_id,
            status="SUBMITTED",
            symbol=order.symbol,
            side=order.side,
            requested_quantity=order.quantity,
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )
        self.order_history.append(result)
        self._save_state()
        return result

    def _is_duplicate_order(self, client_order_id: str) -> bool:
        """A client_order_id already live (pending or filled) must not be
        accepted again — the caller is expected to retry with a new id,
        not resend the same submission. Found by GPT Work's independent
        review: re-submitting the identical order doubled the fill."""
        return any(
            r.client_order_id == client_order_id and r.status in ("SUBMITTED", "PENDING", "FILLED")
            for r in self.order_history
        )

    def cancel_order(self, client_order_id: str) -> bool:
        before = len(self.pending_orders)
        self.pending_orders = [o for o in self.pending_orders if o.client_order_id != client_order_id]
        cancelled = len(self.pending_orders) < before
        if cancelled:
            for r in self.order_history:
                if r.client_order_id == client_order_id:
                    r.status = "CANCELLED"
            self._save_state()
        return cancelled

    # ------------------------------------------------------------------
    # Next-bar execution — call this when a new bar closes for `symbol`
    # ------------------------------------------------------------------

    def on_new_bar(
        self, symbol: str, open_: Decimal, high: Decimal, low: Decimal, close: Decimal, bar_time: str
    ) -> list[OrderResult]:
        """
        Fills pending orders for `symbol` at this bar's open ± slippage, and
        checks stop triggers for any open position. Must be called once per
        new completed bar, in chronological order.
        """
        bar = _Bar(open=open_, high=high, low=low, close=close, time=bar_time)
        filled: list[OrderResult] = []

        # STOP orders are handled exclusively by _maybe_trigger_stop below —
        # they must NOT fill unconditionally through the MARKET/LIMIT path.
        remaining_pending: list[OrderRequest] = []
        for order in list(self.pending_orders):  # snapshot — _fill_order never mutates this list
            if order.symbol != symbol or order.order_type == "STOP":
                remaining_pending.append(order)
                continue
            result = self._fill_order(order, bar)
            filled.append(result)
            if result.status == "PENDING":
                remaining_pending.append(order)  # LIMIT order: condition not met yet, requeue
        self.pending_orders = remaining_pending

        # Stop-loss check on open position (gap-through model)
        position = self.positions.get(symbol)
        if position is not None:
            stop_result = self._maybe_trigger_stop(symbol, position, bar)
            if stop_result is not None:
                filled.append(stop_result)

        self._last_price[symbol] = bar.close
        self._save_state()
        return filled

    def _fill_order(self, order: OrderRequest, bar: _Bar) -> OrderResult:
        now = datetime.now(timezone.utc).isoformat()

        if order.order_type == "MARKET":
            if order.side == "BUY":
                fill_price = bar.open * (1 + self.slippage_rate)
            else:
                fill_price = bar.open * (1 - self.slippage_rate)
        else:  # LIMIT — STOP orders never reach this method (see on_new_bar)
            limit_fill = self._limit_fill_price(order, bar)
            if limit_fill is None:
                return OrderResult(
                    client_order_id=order.client_order_id, status="PENDING", symbol=order.symbol,
                    side=order.side, requested_quantity=order.quantity,
                )
            fill_price = limit_fill

        quantity = order.quantity.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        fee = fill_price * quantity * self.taker_fee

        if order.side == "BUY":
            # A MARKET/LIMIT BUY fills at the NEXT bar's open, which can gap
            # away from the price the caller checked affordability against
            # at decision time. Found by GPT Work's independent review:
            # submitting a BUY affordable at the current price, then a large
            # gap up before the fill bar, used to debit cash past zero with
            # no check at all. Fail closed instead of ever going negative.
            cost_basis = fill_price * quantity + fee
            if cost_basis > self.cash:
                result = OrderResult(
                    client_order_id=order.client_order_id, status="REJECTED", symbol=order.symbol,
                    side=order.side, requested_quantity=order.quantity,
                    reject_reason=(
                        f"insufficient cash at fill price: needs {cost_basis}, have {self.cash}"
                    ),
                )
                for r in self.order_history:
                    if r.client_order_id == order.client_order_id:
                        r.status = result.status
                        r.reject_reason = result.reject_reason
                return result
            self._apply_buy(order.symbol, quantity, fill_price, fee)
        else:
            self._apply_sell(order.symbol, quantity, fill_price, fee)

        result = OrderResult(
            client_order_id=order.client_order_id,
            status="FILLED",
            symbol=order.symbol,
            side=order.side,
            requested_quantity=order.quantity,
            filled_quantity=quantity,
            fill_price=fill_price,
            fee=fee,
            filled_at=now,
        )
        for r in self.order_history:
            if r.client_order_id == order.client_order_id:
                r.status = result.status
                r.filled_quantity = result.filled_quantity
                r.fill_price = result.fill_price
                r.fee = result.fee
                r.filled_at = result.filled_at
        return result

    def _limit_fill_price(self, order: OrderRequest, bar: _Bar) -> Optional[Decimal]:
        """Conservative limit fill per spec: fills at the worse of open/limit."""
        if order.limit_price is None:
            return None
        if order.side == "BUY":
            if bar.low <= order.limit_price:
                return min(bar.open, order.limit_price)
            return None
        else:
            if bar.high >= order.limit_price:
                return max(bar.open, order.limit_price)
            return None

    def _maybe_trigger_stop(self, symbol: str, position: Position, bar: _Bar) -> Optional[OrderResult]:
        """
        This adapter does not independently track a stop price — the
        execution loop is responsible for submitting a STOP-type SELL order
        when a position opens. This method exists for stop orders submitted
        via submit_order(order_type="STOP"); gap-through slippage is applied.
        """
        for order in list(self.pending_orders):
            if order.symbol != symbol or order.order_type != "STOP":
                continue
            if order.side == "SELL" and order.stop_price is not None and bar.low <= order.stop_price:
                if bar.open < order.stop_price:
                    fill_price = bar.open * (1 - self.slippage_rate)  # gapped through
                else:
                    fill_price = order.stop_price * (1 - 2 * self.slippage_rate)
                quantity = order.quantity
                fee = fill_price * quantity * self.taker_fee
                self._apply_sell(symbol, quantity, fill_price, fee)
                self.pending_orders.remove(order)
                result = OrderResult(
                    client_order_id=order.client_order_id, status="FILLED", symbol=symbol,
                    side="SELL", requested_quantity=quantity, filled_quantity=quantity,
                    fill_price=fill_price, fee=fee, filled_at=datetime.now(timezone.utc).isoformat(),
                )
                for r in self.order_history:
                    if r.client_order_id == order.client_order_id:
                        r.status, r.filled_quantity, r.fill_price, r.fee, r.filled_at = (
                            result.status, result.filled_quantity, result.fill_price,
                            result.fee, result.filled_at,
                        )
                return result
        return None

    # ------------------------------------------------------------------
    # Position accounting — per docs/PAPER_TRADING_SIMULATION_SPEC.md
    # ------------------------------------------------------------------

    def _apply_buy(self, symbol: str, quantity: Decimal, fill_price: Decimal, fee: Decimal) -> None:
        cost_basis = fill_price * quantity + fee
        self.cash -= cost_basis
        existing = self.positions.get(symbol)
        if existing is None:
            self.positions[symbol] = Position(
                symbol=symbol, quantity=quantity, avg_entry_price=fill_price, entry_fee=fee,
            )
        else:
            total_qty = existing.quantity + quantity
            existing.avg_entry_price = (
                (existing.avg_entry_price * existing.quantity + fill_price * quantity) / total_qty
            )
            existing.quantity = total_qty
            existing.entry_fee += fee

    def _apply_sell(self, symbol: str, quantity: Decimal, fill_price: Decimal, fee: Decimal) -> Decimal:
        position = self.positions.get(symbol)
        if position is None or position.quantity < quantity:
            raise ValueError(f"Cannot sell {quantity} {symbol} — insufficient open position")

        proceeds = fill_price * quantity - fee
        entry_cost = position.avg_entry_price * quantity
        entry_fee_share = position.entry_fee * (quantity / position.quantity)
        realized_pnl = proceeds - entry_cost - entry_fee_share

        # Credit exactly what was received for this sale — the entry cost
        # was already debited from cash in full back at _apply_buy(), so
        # there is nothing separate to "return" here. `entry_cost +
        # realized_pnl` looks equivalent but isn't: realized_pnl already
        # has entry_fee_share subtracted once, so adding entry_cost back
        # on top double-charges that fee share on every sell.
        self.cash += proceeds

        position.quantity -= quantity
        position.entry_fee -= entry_fee_share
        if position.quantity <= Decimal("0.00000001"):
            del self.positions[symbol]

        return realized_pnl

    # ------------------------------------------------------------------
    # Account state
    # ------------------------------------------------------------------

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def get_account_info(self) -> AccountInfo:
        position_value = sum(
            (self.get_current_price(p.symbol) * p.quantity for p in self.positions.values()),
            Decimal("0"),
        )
        equity = self.cash + position_value
        return AccountInfo(
            equity=equity, cash_balance=self.cash,
            positions=list(self.positions.values()), is_paper=True,
        )

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cash": str(self.cash),
            "positions": {
                sym: {
                    "quantity": str(p.quantity),
                    "avg_entry_price": str(p.avg_entry_price),
                    "entry_fee": str(p.entry_fee),
                    "position_id": p.position_id,
                }
                for sym, p in self.positions.items()
            },
            # Found by GPT Work's independent review: this previously only
            # persisted cash/positions — a pending entry or protective STOP
            # silently vanished on restart, leaving an open position with no
            # stop watching it.
            "pending_orders": [
                {
                    "symbol": o.symbol, "side": o.side, "order_type": o.order_type,
                    "quantity": str(o.quantity),
                    "limit_price": str(o.limit_price) if o.limit_price is not None else None,
                    "stop_price": str(o.stop_price) if o.stop_price is not None else None,
                    "client_order_id": o.client_order_id,
                }
                for o in self.pending_orders
            ],
        }
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.state_path)

    def _load_state(self) -> None:
        assert self.state_path is not None  # only called when state_path is set (see __init__)
        data = json.loads(self.state_path.read_text())
        self.cash = Decimal(data["cash"])
        self.positions = {
            sym: Position(
                symbol=sym, quantity=Decimal(p["quantity"]),
                avg_entry_price=Decimal(p["avg_entry_price"]),
                entry_fee=Decimal(p["entry_fee"]), position_id=p["position_id"],
            )
            for sym, p in data["positions"].items()
        }
        # .get(..., []) — state files saved before this fix have no key.
        self.pending_orders = [
            OrderRequest(
                symbol=o["symbol"], side=o["side"], order_type=o["order_type"],
                quantity=Decimal(o["quantity"]),
                limit_price=Decimal(o["limit_price"]) if o.get("limit_price") is not None else None,
                stop_price=Decimal(o["stop_price"]) if o.get("stop_price") is not None else None,
                client_order_id=o["client_order_id"],
            )
            for o in data.get("pending_orders", [])
        ]
