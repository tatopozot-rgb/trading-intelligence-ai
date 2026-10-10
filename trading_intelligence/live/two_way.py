"""
Two-way automatic engine, the same for every futures-like market. Owner, 2026-10-10: "el sistema
es el mismo, los 2 mercados son futuros" and, for futures, "usar los mismos porcentajes y mismo
horario que el anterior programado ... lo mismo pero para futuros y debe ser mejor analizado y
24/7". XM (CFDs) and Binance USDⓈ-M Futures run this one engine through a small broker adapter
(xm_auto.XmBroker, binance_futures.FuturesBroker / PaperFuturesBroker).

The Spot program's rules, kept:
- Cadence: every 2 minutes inside the owner's windows (07-10 and 17-19 Ecuador), every 5 outside,
  every day.
- Signal: the "tendencia_rango" logic (strategy/two_way_signals.py) mirrored for selling short, and
  never against the 1-hour trend. An open position facing the opposite signal is closed; the next
  decision may open the other way.
- Stop and target read from the market at each entry (exit_plan, band 3-15% for crypto), resting on
  the exchange so they protect the position with the PC off.
- The stop follows the gain: from +1R (R = the entry's stop distance) it trails R/2 behind the
  price, and never moves back.
- Session loss limit (45% by default, inside the owner's 20-50% band): new entries pause and the
  owner is asked warn_before USD before it ("continuar" resumes); at the limit everything closes.
- Profit goal (58% by default): when reached, everything closes and the session ends.
- Size from the broker: 1% of equity at risk per trade, each position at most 40% of equity,
  3 positions at most; risk never raised after a loss.
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
from trading_intelligence.strategy.two_way_signals import signal_for

logger = logging.getLogger(__name__)

Signal = Callable[[str, pd.DataFrame, Optional[pd.DataFrame]], Optional[str]]
DEFAULT_WINDOWS = ("07-10", "17-19")
MAX_EVENTS = 500
TRAIL_START_R, TRAIL_DISTANCE_R = Decimal("1"), Decimal("0.5")  # as on Spot
RUNNING, WAITING_OWNER, STOPPED, GOAL = "RUNNING", "WAITING_OWNER", "STOPPED", "GOAL"
CONTINUE_FILE = "CONTINUAR"


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
    unit: str  # "lotes", "unidades"

    def equity(self) -> tuple[Decimal, str]: ...
    def positions(self) -> dict[str, Position]: ...
    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame: ...
    def plan(self, symbol: str, side: str, risk_pct: Decimal, timeframe: str) -> Plan: ...
    def open(self, plan: Plan) -> str: ...
    def close(self, position: Position) -> None: ...
    def move_stop(self, position: Position, stop: Decimal, target: Decimal) -> None: ...


def regime_signal(symbol: str, data: pd.DataFrame, htf: Optional[pd.DataFrame] = None) -> Optional[str]:
    """The regime alone (kept for comparison; the default is two_way_signals' tendencia_rango_1h)."""
    return signal_for("regimen")(symbol, data, htf)


@dataclass
class State:
    capital: str = "0"  # the session's starting equity: the base of the loss limit and of the goal
    status: str = RUNNING
    warn_acknowledged: bool = False
    day: str = ""
    day_start_equity: str = "0"
    halted: bool = False
    known: dict[str, dict] = field(default_factory=dict)  # symbol -> ticket, side, entry, stop, target, r
    events: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls()
        d = json.loads(path.read_text(encoding="utf-8"))
        known = {k: (v if isinstance(v, dict) else {"ticket": str(v)}) for k, v in d.get("known", {}).items()}
        return cls(d.get("capital", "0"), d.get("status", RUNNING), bool(d.get("warn_acknowledged", False)),
                   d.get("day", ""), d.get("day_start_equity", "0"), bool(d.get("halted", False)), known,
                   list(d.get("events", [])))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.__dict__, indent=1), encoding="utf-8")
        tmp.replace(path)


class TwoWayAuto:
    def __init__(self, broker: Broker, symbols: list[str], state_path: Path, *, timeframe: str = "5m",
                 risk_pct: Decimal = Decimal("1"), max_open: int = 3, loss_limit_pct: Decimal = Decimal("45"),
                 warn_before: Decimal = Decimal("2"), profit_target_pct: Optional[Decimal] = Decimal("58"),
                 daily_loss_pct: Optional[Decimal] = None, trailing: bool = True,
                 confirm_timeframe: Optional[str] = "1h", windows: Optional[list[str]] = None,
                 inside_every_min: int = 2, outside_every_min: int = 5, signal: Optional[Signal] = None,
                 notify: Callable[[str], None] = console,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        if max_open < 1 or not (0 < risk_pct <= 2) or not (0 < loss_limit_pct <= 100):
            raise ValueError("max_open >= 1, risk_pct in (0, 2], loss_limit_pct in (0, 100]")
        if daily_loss_pct is not None and not (0 < daily_loss_pct < 100):
            raise ValueError("daily_loss_pct in (0, 100)")
        self.broker, self.symbols, self.state_path = broker, list(symbols), Path(state_path)
        self.timeframe, self.risk_pct, self.max_open = timeframe, risk_pct, max_open
        self.loss_limit_pct, self.warn_before, self.profit_target_pct = loss_limit_pct, warn_before, profit_target_pct
        self.daily_loss_pct, self.trailing, self.confirm_timeframe = daily_loss_pct, trailing, confirm_timeframe
        self.windows = parse_windows(list(windows if windows is not None else DEFAULT_WINDOWS))
        self.inside_every_min, self.outside_every_min = inside_every_min, outside_every_min
        self.signal: Signal = signal or signal_for()
        self.notify, self.clock = notify, clock
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

    def _close_all(self, ours: dict[str, Position]) -> None:
        for sym, pos in ours.items():
            self.broker.close(pos)
            self.state.known.pop(sym, None)

    def _guard(self, equity: Decimal, currency: str, ours: dict[str, Position]) -> dict[str, Position]:
        """Session loss limit (with the owner asked first), profit goal, optional daily stop."""
        s, name = self.state, self.broker.name
        if (self.state_path.parent / CONTINUE_FILE).exists():
            (self.state_path.parent / CONTINUE_FILE).unlink()
            if s.status == WAITING_OWNER:
                s.status, s.warn_acknowledged = RUNNING, True
                self._event("OWNER", "continuar")
                self.notify(f"✅ {name}: entendido, sigo operando hasta el límite de pérdida.")
        capital = Decimal(s.capital)
        loss, limit = capital - equity, capital * self.loss_limit_pct / 100
        if s.status not in (STOPPED, GOAL) and loss >= limit:
            s.status = STOPPED
            self._close_all(ours)
            self._event("STOPPED", f"pérdida {loss:.2f} >= {limit:.2f}")
            self.notify(f"🛑 {name}: la pérdida llegó al límite de {self.loss_limit_pct}% ({loss:.2f} {currency}). "
                        f"Cerré todas las posiciones y la sesión terminó.")
            return self.broker.positions()
        if s.status == RUNNING and not s.warn_acknowledged and loss > 0 and loss >= limit - self.warn_before:
            s.status = WAITING_OWNER
            self._event("WAITING_OWNER", f"pérdida {loss:.2f}, límite {limit:.2f}")
            self.notify(f"⚠️ {name}: la pérdida es {loss:.2f} {currency}, a {limit - loss:.2f} del límite. "
                        f"No abro operaciones nuevas (las abiertas siguen con su stop). ¿Continuar? Dile a Claude "
                        f"local: continuar.")
        if self.profit_target_pct is not None and s.status in (RUNNING, WAITING_OWNER) \
                and equity - capital >= capital * self.profit_target_pct / 100:
            s.status = GOAL
            self._close_all(ours)
            self._event("GOAL", f"ganancia {equity - capital:.2f}")
            self.notify(f"🏆 {name}: ¡meta cumplida! Ganancia de {equity - capital:.2f} {currency} "
                        f"(+{self.profit_target_pct}%). Cerré todo y la sesión terminó.")
            return self.broker.positions()
        if self.daily_loss_pct is not None:
            floor = Decimal(s.day_start_equity) * (1 - self.daily_loss_pct / 100)
            if not s.halted and equity <= floor:
                s.halted = True
                self._close_all(ours)
                self._event("DAY_HALTED", f"equity {equity} <= {floor:.2f}")
                self.notify(f"🛑 {name}: la cuenta perdió {self.daily_loss_pct}% hoy (equity {equity} {currency}). "
                            f"Cerré las posiciones y no abro nada más hasta mañana (19:00 de Ecuador).")
                return self.broker.positions()
        return ours

    def step(self) -> None:
        s, name = self.state, self.broker.name
        equity, currency = self.broker.equity()
        if Decimal(s.capital) <= 0:
            s.capital = str(equity)
        today = self.clock().date().isoformat()
        if s.day != today:
            s.day, s.day_start_equity, s.halted = today, str(equity), False
            self._noted.clear()
        ours = self.broker.positions()
        for sym, info in list(s.known.items()):
            if sym not in ours or ours[sym].ticket != info.get("ticket"):
                del s.known[sym]
                self._event("CLOSED_BY_EXCHANGE", sym)
                self.notify(f"⚪ {name}: se cerró {sym} en el servidor (llegó a su stop o a su meta).")
        ours = self._guard(equity, currency, ours)
        for sym in self.symbols:
            try:
                self._decide(sym, ours, currency)
            except (RuntimeError, ValueError) as error:
                self._note_once(f"{sym}:{str(error)[:40]}", f"{sym}: {error}")
        self.state.save(self.state_path)

    def _trail(self, pos: Position, price: Decimal) -> None:
        info = self.state.known.get(pos.symbol, {})
        if not self.trailing or "r" not in info:
            return
        r, entry, stop = Decimal(info["r"]), Decimal(info["entry"]), Decimal(info["stop"])
        long = pos.side == "BUY"
        gain = price - entry if long else entry - price
        if r <= 0 or gain < TRAIL_START_R * r:
            return
        new = price - TRAIL_DISTANCE_R * r if long else price + TRAIL_DISTANCE_R * r
        if (long and new > stop) or (not long and new < stop):
            self.broker.move_stop(pos, new, Decimal(info["target"]))
            info["stop"] = str(new)
            self._event("TRAIL", f"{pos.symbol} stop {new}")

    def _decide(self, sym: str, ours: dict[str, Position], currency: str) -> None:
        s, name = self.state, self.broker.name
        data = self.broker.candles(sym, self.timeframe, 500)
        htf = self.broker.candles(sym, self.confirm_timeframe, 200) if self.confirm_timeframe else None
        signal = self.signal(sym, data, htf)
        pos = ours.get(sym)
        if pos is not None:
            if signal is not None and signal != pos.side:
                self.broker.close(pos)
                ours.pop(sym)
                s.known.pop(sym, None)
                self._event("CLOSE", f"{sym} {pos.side}: señal {signal}")
                self.notify(f"🔁 {name}: cerré la {'compra' if pos.side == 'BUY' else 'venta en corto'} de {sym}: "
                            f"el mercado cambió de dirección.")
            else:
                self._trail(pos, Decimal(str(data["close"].iloc[-1])))
            return
        if signal is None or s.status != RUNNING or s.halted or len(ours) >= self.max_open:
            return
        plan = self.broker.plan(sym, signal, self.risk_pct, self.timeframe)
        ticket = self.broker.open(plan)
        ours[sym] = Position(sym, plan.side, plan.qty, ticket, plan.price)
        s.known[sym] = {"ticket": ticket, "side": plan.side, "entry": str(plan.price), "stop": str(plan.sl),
                        "target": str(plan.tp), "r": str(abs(plan.price - plan.sl))}
        self._event("OPEN", f"{plan.side} {plan.qty} {sym} @ {plan.price} SL {plan.sl} TP {plan.tp}")
        verb = "Compré" if plan.side == "BUY" else "Vendí en corto"
        why = "el mercado está subiendo" if plan.side == "BUY" else "el mercado está bajando"
        self.notify(f"{'🟢' if plan.side == 'BUY' else '🔴'} {name}: {verb} {plan.qty} {self.broker.unit} de {sym} "
                    f"a {plan.price} porque {why}. Stop en {plan.sl}, meta en {plan.tp} (puestos en el servidor). "
                    f"Si toca el stop se pierden unos {plan.risk_money} {currency}.")

    def run(self, max_iterations: Optional[int] = None, sleep: Callable[[float], None] = time.sleep) -> None:
        n = 0
        while (max_iterations is None or n < max_iterations) and self.state.status not in (STOPPED, GOAL):
            n += 1
            if self.decision_due():
                try:
                    self.step()
                except (RuntimeError, ValueError) as error:  # terminal closed, exchange down: retry next slot
                    logger.warning("%s: %s", self.broker.name, error)
                    self._note_once(f"step:{str(error)[:40]}", str(error))
                    self.state.save(self.state_path)
            sleep(20)


def owner_continue(state_dir: Path) -> None:
    """The owner's "continuar": the running engine picks it up at its next decision."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / CONTINUE_FILE).write_text("continuar\n", encoding="utf-8")
