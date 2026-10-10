"""
A real-trading session: the capital the owner assigned, what the session bought with
it (only these holdings are ever sold: the owner's other coins are never touched),
realized P&L, fees, and the owner's loss guard.

Loss guard (owner's rule, 2026-10-08):
- loss >= (loss limit - warn_before_usd)  -> WAITING_OWNER: no new buys, exits still
  work, and the owner is asked whether to continue;
- owner says continue                       -> RUNNING until the hard limit;
- loss >= loss limit                        -> STOPPED: no new buys and every session
  position is closed. Restarting is the owner's decision.
The system never adds capital and never raises risk to recover a loss.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Optional

from trading_intelligence.live.limits import OwnerLimits

RUNNING, WAITING_OWNER, STOPPED = "RUNNING", "WAITING_OWNER", "STOPPED"


@dataclass
class Holding:
    qty: Decimal
    cost: Decimal  # USDT paid including fees, for the qty still held

    @property
    def avg_cost(self) -> Decimal:
        return self.cost / self.qty if self.qty > 0 else Decimal("0")


@dataclass
class Session:
    session_id: str
    profile: str
    started_at: str
    capital: Decimal
    status: str = RUNNING
    warn_acknowledged: bool = False
    realized_pnl: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    holdings: dict[str, Holding] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    peak_equity: Decimal = Decimal("0")
    # Protective stops resting on Binance: symbol -> {"id", "qty", "stop"}. They work even
    # when the owner's PC is off; the operator cancels one before it sells that symbol.
    guard_stops: dict[str, dict] = field(default_factory=dict)
    trail_peaks: dict[str, Decimal] = field(default_factory=dict)  # highest price since entry, per held symbol
    # Symbols the operator sold on its own (take profit, trailing stop) while the decision engine
    # still held them: no re-buy until the engine itself exits, or the mirror would buy right back.
    exited_early: list[str] = field(default_factory=list)
    # Exit plan read from the market when each position was opened: {"stop", "target", "kind", ...}.
    exit_plans: dict[str, dict] = field(default_factory=dict)

    # --- accounting -----------------------------------------------------------

    @property
    def invested(self) -> Decimal:
        return sum((h.cost for h in self.holdings.values()), Decimal("0"))

    @property
    def available(self) -> Decimal:
        """USDT this session may still spend: capital + realized P&L - cost of what it holds."""
        return self.capital + self.realized_pnl - self.invested

    def equity(self, prices: Mapping[str, Decimal]) -> Decimal:
        return self.available + sum((h.qty * prices[s] for s, h in self.holdings.items()), Decimal("0"))

    def loss(self, prices: Mapping[str, Decimal]) -> Decimal:
        return self.capital - self.equity(prices)

    def record_buy(self, symbol: str, qty: Decimal, cost_usdt: Decimal, fee_usdt: Decimal, reason: str) -> None:
        if symbol not in self.holdings:
            self.trail_peaks.pop(symbol, None)  # a new position starts its own peak
        h = self.holdings.setdefault(symbol, Holding(Decimal("0"), Decimal("0")))
        h.qty += qty
        h.cost += cost_usdt
        self.fees += fee_usdt
        self._trade("BUY", symbol, qty, cost_usdt, fee_usdt, reason, None)

    def record_sell(self, symbol: str, qty: Decimal, proceeds_usdt: Decimal, fee_usdt: Decimal, reason: str) -> Decimal:
        h = self.holdings[symbol]
        qty = min(qty, h.qty)
        cost_part = h.avg_cost * qty
        pnl = proceeds_usdt - cost_part
        h.qty -= qty
        h.cost -= cost_part
        if h.qty <= 0:
            del self.holdings[symbol]
            self.trail_peaks.pop(symbol, None)
        self.realized_pnl += pnl
        self.fees += fee_usdt
        self._trade("SELL", symbol, qty, proceeds_usdt, fee_usdt, reason, pnl)
        return pnl

    def _trade(self, side: str, symbol: str, qty: Decimal, usdt: Decimal, fee: Decimal, reason: str,
               pnl: Optional[Decimal]) -> None:
        self.trades.append({"at": _now(), "side": side, "symbol": symbol, "qty": str(qty), "usdt": str(usdt),
                            "fee_usdt": str(fee), "pnl": None if pnl is None else str(pnl), "reason": reason})

    def note(self, kind: str, text: str) -> None:
        self.events.append({"at": _now(), "kind": kind, "text": text})

    # --- guard --------------------------------------------------------------------

    def evaluate(self, prices: Mapping[str, Decimal], limits: OwnerLimits) -> Optional[str]:
        """Updates the status from the current loss. Returns a message for the owner
        when the status changes, else None."""
        equity = self.equity(prices)
        self.peak_equity = max(self.peak_equity, equity)
        loss = self.capital - equity
        limit = limits.loss_limit_usd(self.capital)
        warn = limits.warn_at_usd(self.capital)
        if self.status != STOPPED and loss >= limit:
            self.status = STOPPED
            msg = (f"STOP: pérdida {loss:.2f} USDT alcanzó el límite de {limit:.2f} USDT "
                   f"({limits.loss_limit_pct}% de {self.capital:.2f}). Se cierran las posiciones de la sesión.")
            self.note("STOPPED", msg)
            return msg
        if self.status == RUNNING and not self.warn_acknowledged and loss > 0 and loss >= warn:
            self.status = WAITING_OWNER
            msg = (f"AVISO: pérdida {loss:.2f} USDT; a {limit - loss:.2f} USDT del límite de {limit:.2f}. "
                   "Entradas nuevas en pausa (las salidas siguen). ¿Continuar? -> comando: continuar")
            self.note("WAITING_OWNER", msg)
            return msg
        return None

    def owner_continue(self) -> None:
        if self.status == STOPPED:
            raise ValueError("the session is STOPPED at the loss limit: start a new session to trade again")
        self.status = RUNNING
        self.warn_acknowledged = True
        self.note("OWNER", "el dueño ordenó continuar hasta el límite")

    def add_capital(self, amount: Decimal) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        self.capital += amount
        self.warn_acknowledged = False
        self.note("OWNER", f"el dueño asignó {amount} USDT más (capital {self.capital})")

    @property
    def may_buy(self) -> bool:
        return self.status == RUNNING

    # --- persistence ----------------------------------------------------------------

    def save(self, path: Path) -> None:
        data = asdict(self)
        data = json.loads(json.dumps(data, default=str))
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "Session":
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            session_id=d["session_id"], profile=d["profile"], started_at=d["started_at"],
            capital=Decimal(d["capital"]), status=d["status"], warn_acknowledged=d["warn_acknowledged"],
            realized_pnl=Decimal(d["realized_pnl"]), fees=Decimal(d["fees"]),
            holdings={s: Holding(Decimal(h["qty"]), Decimal(h["cost"])) for s, h in d["holdings"].items()},
            events=d["events"], trades=d["trades"], peak_equity=Decimal(d["peak_equity"]),
            guard_stops=dict(d.get("guard_stops", {})),  # absent in sessions saved before this field
            trail_peaks={k: Decimal(v) for k, v in d.get("trail_peaks", {}).items()},
            exited_early=list(d.get("exited_early", [])),
            exit_plans=dict(d.get("exit_plans", {})),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
