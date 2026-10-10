"""
Two-way automatic engine, the same for every futures-like market. Owner, 2026-10-10: "el sistema
es el mismo, los 2 mercados son futuros" — XM (CFDs) and Binance USDⓈ-M Futures run this one
engine through a small broker adapter (xm_auto.XmBroker, binance_futures.FuturesBroker /
PaperFuturesBroker), so results can be compared market against market.

At each decision, for each instrument:
- Signal from the regime on the decision bars: trend or breakout up -> BUY; down -> SELL (a short
  sale); range or no edge -> no new entry (an open position keeps its own stop and target).
- An open position facing the opposite signal is closed; the next decision may open the other way.
- No position, a signal, room under max_open and the day not halted -> the broker's plan (stop and
  target read from the market for that side, size from a fixed risk), then the order with its stop
  loss and take profit resting on the exchange, so it stays protected with the PC off.
- Daily loss guard: when equity falls daily_loss_pct below the UTC day's starting equity, every
  position is closed and no new entry is made until the next UTC day (19:00 Ecuador).
- Risk per trade is fixed (risk_pct of equity at the stop): never raised after a loss.
- Cadence: every inside_every_min minutes inside the owner's windows, outside_every_min outside.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional, Protocol

import pandas as pd

from trading_intelligence.live.operator import in_windows, parse_windows
from trading_intelligence.live.telegram_notify import console

logger = logging.getLogger(__name__)

Signal = Callable[[str, pd.DataFrame], Optional[str]]  # (symbol, decision bars) -> BUY / SELL / None
DEFAULT_WINDOWS = ("07-10", "17-19")
MAX_EVENTS = 500


@dataclass(frozen=True)
class Position:
    symbol: str
    side: str  # BUY (long) or SELL (short)
    qty: Decimal
    ticket: str
    entry: Decimal = Decimal("0")


@dataclass(frozen=True)
class Plan:
    symbol: str
    side: str
    qty: Decimal
    price: Decimal
    sl: Decimal
    tp: Decimal
    risk_money: Decimal  # account currency lost if the stop is hit (before fees and slippage)


class Broker(Protocol):
    name: str  # "XM DEMO", "Binance Futuros", "Binance Futuros (SHADOW)"
    unit: str  # "lotes", "contratos"

    def equity(self) -> tuple[Decimal, str]: ...
    def positions(self) -> dict[str, Position]: ...
    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame: ...
    def plan(self, symbol: str, side: str, risk_pct: Decimal, timeframe: str) -> Plan: ...
    def open(self, plan: Plan) -> str: ...
    def close(self, position: Position) -> None: ...


def regime_signal(symbol: str, data: pd.DataFrame) -> Optional[str]:
    from trading_intelligence.regime.detector import Regime, detect_regime

    try:
        regime = detect_regime(data).regime
    except Exception:  # noqa: BLE001 - not enough history: no signal
        return None
    if regime in (Regime.TREND_UP, Regime.BREAKOUT_UP):
        return "BUY"
    if regime in (Regime.TREND_DOWN, Regime.BREAKOUT_DOWN):
        return "SELL"
    return None


@dataclass
class State:
    day: str = ""
    day_start_equity: str = "0"
    halted: bool = False
    known: dict[str, str] = field(default_factory=dict)  # symbol -> ticket of our open position
    events: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls()
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(d.get("day", ""), d.get("day_start_equity", "0"), bool(d.get("halted", False)),
                   {k: str(v) for k, v in d.get("known", {}).items()}, list(d.get("events", [])))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.__dict__, indent=1), encoding="utf-8")
        tmp.replace(path)


class TwoWayAuto:
    def __init__(self, broker: Broker, symbols: list[str], state_path: Path, *, timeframe: str = "5m",
                 risk_pct: Decimal = Decimal("0.5"), max_open: int = 3, daily_loss_pct: Decimal = Decimal("5"),
                 windows: Optional[list[str]] = None, inside_every_min: int = 2, outside_every_min: int = 5,
                 signal: Signal = regime_signal, notify: Callable[[str], None] = console,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        if max_open < 1 or not (0 < risk_pct <= 2) or not (0 < daily_loss_pct < 100):
            raise ValueError("max_open >= 1, risk_pct in (0, 2], daily_loss_pct in (0, 100)")
        self.broker, self.symbols, self.state_path = broker, list(symbols), Path(state_path)
        self.timeframe, self.risk_pct, self.max_open, self.daily_loss_pct = timeframe, risk_pct, max_open, daily_loss_pct
        self.windows = parse_windows(list(windows if windows is not None else DEFAULT_WINDOWS))
        self.inside_every_min, self.outside_every_min = inside_every_min, outside_every_min
        self.signal, self.notify, self.clock = signal, notify, clock
        self.state = State.load(self.state_path)
        self._last_slot: Optional[tuple[int, int]] = None
        self._noted: set[str] = set()

    def decision_due(self) -> bool:
        """Every inside_every_min minutes inside the owner's windows, every outside_every_min outside."""
        now = self.clock()
        period = self.inside_every_min if in_windows(self.windows, now) else self.outside_every_min
        slot = (period, int(now.timestamp() // (period * 60)))
        if slot == self._last_slot:
            return False
        self._last_slot = slot
        return True

    def _event(self, kind: str, text: str) -> None:
        self.state.events.append({"at": self.clock().isoformat(), "kind": kind, "text": text})
        del self.state.events[:-MAX_EVENTS]

    def _note_once(self, key: str, text: str) -> None:
        if key not in self._noted:
            self._noted.add(key)
            self._event("SKIP", text)

    def step(self) -> None:
        s, name = self.state, self.broker.name
        equity, currency = self.broker.equity()
        today = self.clock().date().isoformat()
        if s.day != today:
            s.day, s.day_start_equity, s.halted = today, str(equity), False
            self._noted.clear()
        ours = self.broker.positions()

        for sym, ticket in list(s.known.items()):
            if sym not in ours or ours[sym].ticket != ticket:
                del s.known[sym]
                self._event("CLOSED_BY_EXCHANGE", sym)
                self.notify(f"⚪ {name}: se cerró {sym} en el servidor (llegó a su stop o a su meta).")

        floor = Decimal(s.day_start_equity) * (1 - self.daily_loss_pct / 100)
        if not s.halted and equity <= floor:
            s.halted = True
            for sym, pos in ours.items():
                self.broker.close(pos)
                s.known.pop(sym, None)
            ours = self.broker.positions()
            self._event("DAY_HALTED", f"equity {equity} <= {floor:.2f}")
            self.notify(f"🛑 {name}: la cuenta perdió {self.daily_loss_pct}% hoy (equity {equity} {currency}). "
                        f"Cerré las posiciones y no abro nada más hasta mañana (19:00 de Ecuador).")

        for sym in self.symbols:
            try:
                self._decide(sym, ours, currency)
            except (RuntimeError, ValueError) as error:
                self._note_once(f"{sym}:{str(error)[:40]}", f"{sym}: {error}")
        self.state.save(self.state_path)

    def _decide(self, sym: str, ours: dict[str, Position], currency: str) -> None:
        s, name = self.state, self.broker.name
        signal = self.signal(sym, self.broker.candles(sym, self.timeframe, 500))
        pos = ours.get(sym)
        if pos is not None:
            if signal is not None and signal != pos.side:
                self.broker.close(pos)
                ours.pop(sym)
                s.known.pop(sym, None)
                self._event("CLOSE", f"{sym} {pos.side}: señal {signal}")
                self.notify(f"🔁 {name}: cerré la {'compra' if pos.side == 'BUY' else 'venta en corto'} de {sym}: "
                            f"el mercado cambió de dirección.")
            return
        if signal is None or s.halted or len(ours) >= self.max_open:
            return
        plan = self.broker.plan(sym, signal, self.risk_pct, self.timeframe)
        ticket = self.broker.open(plan)
        ours[sym] = Position(sym, plan.side, plan.qty, ticket, plan.price)
        s.known[sym] = ticket
        self._event("OPEN", f"{plan.side} {plan.qty} {sym} @ {plan.price} SL {plan.sl} TP {plan.tp}")
        verb = "Compré" if plan.side == "BUY" else "Vendí en corto"
        why = "el mercado está subiendo" if plan.side == "BUY" else "el mercado está bajando"
        self.notify(f"{'🟢' if plan.side == 'BUY' else '🔴'} {name}: {verb} {plan.qty} {self.broker.unit} de {sym} "
                    f"a {plan.price} porque {why}. Stop en {plan.sl}, meta en {plan.tp} (puestos en el servidor). "
                    f"Si toca el stop se pierden unos {plan.risk_money} {currency}.")

    def run(self, max_iterations: Optional[int] = None, sleep: Callable[[float], None] = time.sleep) -> None:
        n = 0
        while max_iterations is None or n < max_iterations:
            n += 1
            if self.decision_due():
                try:
                    self.step()
                except (RuntimeError, ValueError) as error:  # terminal closed, exchange down: retry next slot
                    logger.warning("%s: %s", self.broker.name, error)
                    self._note_once(f"step:{str(error)[:40]}", str(error))
                    self.state.save(self.state_path)
            sleep(20)
