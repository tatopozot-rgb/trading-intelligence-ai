"""
Two-way automatic engine, the same for every futures-like market. Owner, 2026-10-10: "el sistema
es el mismo, los 2 mercados son futuros" and, for futures, "usar los mismos porcentajes y mismo
horario que el anterior programado ... lo mismo pero para futuros y debe ser mejor analizado y
24/7". XM (CFDs) and Binance USDⓈ-M Futures run this one engine through a small broker adapter
(xm_auto.XmBroker, binance_futures.FuturesBroker / PaperFuturesBroker).

The Spot program's rules, kept:
- Cadence (owner, 2026-10-10): inside his windows (07-10 and 17-19 Ecuador) "sin parar" — a decision
  every 30 s; outside them every 5 minutes; every day. On top of that the desk's Scout watches every
  symbol every loop, 24/7, and alerts the Chief, who evaluates that symbol at once.
- Open positions: each one's bot checks it on the exchange every 30 s (trailing stop included) and
  reports its state by Telegram every 2 minutes.
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
- Size (owner, 2026-10-10: "1% de riesgo esta mal debe ser por lo menos 1 al 15% ... el máximo por
  posición hasta el 50%"): the risk of each trade goes from risk_min (1%) to risk_max (15%) of equity
  with the signal's quality (strategy/two_way_signals.quality: regime clarity, 1-hour trend and Binance's
  top traders agreeing). It depends only on the market, never on past wins or losses (no martingale).
  The broker caps each position at 50% of equity and all positions together at what the margin allows,
  so with a 3-15% stop one trade can lose at most 7.5% of equity at 1x. 3 positions at most.

Two more rules from the owner, 2026-10-10:
- "si se abren 2 posiciones cada uno tiene un bot diferente": every open position has its own bot
  (PositionBot). Between decisions, every loop (20 s), each bot checks its own position on the exchange,
  moves its trailing stop and reports under its own name.
- "el telegram no puede enviar cosas falsas, debe estar verificado 2 veces al final en la cuenta": a
  message that a position opened or closed is sent only after two separate reads of the account agree;
  otherwise the message says plainly that it is not confirmed yet.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional, Protocol

import pandas as pd

from trading_intelligence.live import desk as D
from trading_intelligence.live import ordenes as O
from trading_intelligence.live.operator import in_windows, parse_windows
from trading_intelligence.live.telegram_notify import console
from trading_intelligence.strategy.two_way_signals import signal_for

logger = logging.getLogger(__name__)

# (symbol, decision bars, 1-hour bars, top=top traders' ratio) -> "BUY"/"SELL", (side, quality 0-1) or None
Signal = Callable[..., object]
DEFAULT_WINDOWS = ("07-10", "17-19")
MAX_EVENTS = 500
TRAIL_START_R, TRAIL_DISTANCE_R = Decimal("1"), Decimal("0.5")  # as on Spot
RUNNING, WAITING_OWNER, STOPPED, GOAL, PAUSED_API = "RUNNING", "WAITING_OWNER", "STOPPED", "GOAL", "PAUSED_API"
API_FAILURES_TO_PAUSE = 3  # kill switch: this many failed passes in a row stop new entries until one works
VETO_QUIET = timedelta(minutes=30)  # a vetoed symbol/side is not re-proposed for this long
REGIME_SYMBOL = "BTCUSDT"  # the regime brake reads BTC's daily bars
VETO_TRACK = timedelta(hours=24)  # a veto's outcome is scored for this long
CONTINUE_FILE = "CONTINUAR"
VERIFY_PAUSE_S = 2.0  # between the two account reads that confirm a message


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
    def price(self, symbol: str) -> Decimal: ...


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
    vetoes: list[dict] = field(default_factory=list)  # the Skeptic's refusals, scored later
    veto_score: dict = field(default_factory=lambda: {"evitó pérdida": 0, "dejó pasar ganancia": 0, "sin resultado": 0})
    month: str = ""  # the goal is monthly (owner, 2026-10-11): it starts again from this equity each month
    month_start_equity: str = "0"

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls()
        d = json.loads(path.read_text(encoding="utf-8"))
        known = {k: (v if isinstance(v, dict) else {"ticket": str(v)}) for k, v in d.get("known", {}).items()}
        state = cls(d.get("capital", "0"), d.get("status", RUNNING), bool(d.get("warn_acknowledged", False)),
                    d.get("day", ""), d.get("day_start_equity", "0"), bool(d.get("halted", False)), known,
                    list(d.get("events", [])), list(d.get("vetoes", [])))
        state.veto_score.update(d.get("veto_score", {}))
        state.month, state.month_start_equity = d.get("month", ""), d.get("month_start_equity", "0")
        return state

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.__dict__, indent=1), encoding="utf-8")
        tmp.replace(path)


class TwoWayAuto:
    def __init__(self, broker: Broker, symbols: list[str], state_path: Path, *, timeframe: str = "5m",
                 risk_min_pct: Decimal = Decimal("1"), risk_max_pct: Decimal = Decimal("15"), max_open: int = 3,
                 loss_limit_pct: Decimal = Decimal("45"),
                 warn_before: Decimal = Decimal("2"), profit_target_pct: Optional[Decimal] = Decimal("58"),
                 daily_loss_pct: Optional[Decimal] = None, trailing: bool = True,
                 confirm_timeframe: Optional[str] = "1h", windows: Optional[list[str]] = None,
                 inside_every_min: float = 0.5, outside_every_min: float = 5, signal: Optional[Signal] = None,
                 desk_rules: Optional[D.DeskRules] = None, journal_dir: Optional[Path] = None,
                 news_get: Optional[D.Getter] = None, watch_every_s: int = 30, report_every_s: int = 120,
                 notify: Callable[[str], None] = console, chatter: Callable[[str], None] = console,
                 goal_usd: Optional[Decimal] = None, heartbeat_every_s: Optional[int] = None,
                 orders_path: Optional[Path] = None, pause: Callable[[float], None] = time.sleep,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        if max_open < 1 or not (0 < risk_min_pct <= risk_max_pct <= 15) or not (0 < loss_limit_pct <= 100):
            raise ValueError("max_open >= 1, 0 < risk_min_pct <= risk_max_pct <= 15, loss_limit_pct in (0, 100]")
        if daily_loss_pct is not None and not (0 < daily_loss_pct < 100):
            raise ValueError("daily_loss_pct in (0, 100)")
        self.broker, self.symbols, self.state_path = broker, list(symbols), Path(state_path)
        self.timeframe, self.max_open = timeframe, max_open
        self.risk_min_pct, self.risk_max_pct = risk_min_pct, risk_max_pct
        self.loss_limit_pct, self.warn_before, self.profit_target_pct = loss_limit_pct, warn_before, profit_target_pct
        self.daily_loss_pct, self.trailing, self.confirm_timeframe = daily_loss_pct, trailing, confirm_timeframe
        self.windows = parse_windows(list(windows if windows is not None else DEFAULT_WINDOWS))
        self.inside_every_min, self.outside_every_min = inside_every_min, outside_every_min
        self.signal: Signal = signal or signal_for()
        # notify reaches Telegram and carries only what the account confirmed twice; chatter (the Scout, the
        # Skeptic, a stop being moved) stays on the console and in the desk journal (owner, 2026-10-11: "que el bot
        # de telegram envíe solo cosas ciertas revisadas")
        self.notify, self.chatter, self.pause, self.clock = notify, chatter, pause, clock
        self.goal_usd = goal_usd
        # a short "still alive" summary to Telegram (owner, 2026-10-11: "no he recibido una sola notificación")
        self.heartbeat_every_s = heartbeat_every_s
        self._last_heartbeat: Optional[datetime] = None
        self.desk_rules, self.journal_dir, self.news_get = desk_rules, journal_dir, news_get
        self.watch_every_s, self.report_every_s = watch_every_s, report_every_s
        self.state = State.load(self.state_path)
        self._last_slot: Optional[tuple[float, int]] = None
        self._noted: set[str] = set()
        self._last_watch: Optional[datetime] = None
        self._last_report: dict[str, datetime] = {}
        self._last_scout: dict[str, datetime] = {}
        self._last_veto: dict[str, tuple[str, datetime]] = {}
        self._rally_seen: dict[str, tuple[datetime, Optional[D.Alert]]] = {}
        self._fng: tuple[Optional[datetime], Optional[int]] = (None, None)
        self._regime: tuple[Optional[datetime], Optional[bool]] = (None, None)
        self.orders_path = orders_path  # the owner's Telegram orders (live/ordenes.py), written by the alarm
        self._failures = 0

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
        if s.status in (STOPPED, GOAL) and ours:  # a close that failed (exchange down) is retried every pass
            self._close_all(ours)
            ours = self.broker.positions()
        capital = Decimal(s.capital)
        loss, limit = capital - equity, capital * self.loss_limit_pct / 100
        month_start = Decimal(s.month_start_equity) if Decimal(s.month_start_equity) > 0 else capital
        goal = self.goal_usd if self.goal_usd is not None else (
            month_start * self.profit_target_pct / 100 if self.profit_target_pct is not None else None)
        loss_hit = (s.status not in (STOPPED, GOAL) and loss >= limit) or \
            (s.status == RUNNING and not s.warn_acknowledged and loss > 0 and loss >= limit - self.warn_before)
        goal_hit = goal is not None and s.status in (RUNNING, WAITING_OWNER) and equity - month_start >= goal
        if loss_hit or goal_hit:  # a warning, a stop or the goal is told only if a second read of the account agrees
            self.pause(VERIFY_PAUSE_S)
            second = self.broker.equity()[0]
            # the less extreme read: the higher equity for a loss, the lower one for the goal
            equity = max(equity, second) if loss_hit else min(equity, second)
            loss = capital - equity
        if s.status not in (STOPPED, GOAL) and loss >= limit:
            s.status = STOPPED
            self._close_all(ours)
            self._event("STOPPED", f"pérdida {loss:.2f} >= {limit:.2f}")
            self.notify(f"🛑 {name}: la pérdida llegó al límite de {self.loss_limit_pct}% ({loss:.2f} {currency}). "
                        f"Cerré todas las posiciones y la sesión terminó. Revisado 2 veces en la cuenta.")
            return self.broker.positions()
        if s.status == RUNNING and not s.warn_acknowledged and loss > 0 and loss >= limit - self.warn_before:
            s.status = WAITING_OWNER
            self._event("WAITING_OWNER", f"pérdida {loss:.2f}, límite {limit:.2f}")
            self.notify(f"⚠️ {name}: la pérdida es {loss:.2f} {currency}, a {limit - loss:.2f} del límite "
                        f"(revisado 2 veces en la cuenta). No abro operaciones nuevas (las abiertas siguen con su "
                        f"stop). ¿Continuar? Dile a Claude local: continuar.")
        if goal is not None and s.status in (RUNNING, WAITING_OWNER) and equity - month_start >= goal:
            s.status = GOAL
            self._close_all(ours)
            self._event("GOAL", f"ganancia del mes {equity - month_start:.2f}")
            self.notify(f"🏆 {name}: ¡meta del mes cumplida! Ganancia de {equity - month_start:.2f} {currency} este "
                        f"mes (meta {goal:.2f}). Cerré todo y vuelvo a operar el día 1 del mes que viene. "
                        f"Revisado 2 veces en la cuenta.")
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
        s = self.state
        equity, currency = self.broker.equity()
        if Decimal(s.capital) <= 0:
            s.capital = str(equity)
        month = self.clock().strftime("%Y-%m")
        if s.month != month:
            resumed = s.status == GOAL  # also a GOAL left by the old session goal (before 2026-10-11)
            s.month, s.month_start_equity = month, str(equity)
            if resumed:
                s.status = RUNNING
                self._event("MONTH", f"nuevo mes desde {equity}")
                self.notify(f"🗓️ {self.broker.name}: empieza {month}. Retomo las operaciones; la meta del mes cuenta "
                            f"desde {equity} {currency}.")
        today = self.clock().date().isoformat()
        if s.day != today:
            s.day, s.day_start_equity, s.halted = today, str(equity), False
            self._noted.clear()
        ours = self._reconcile()
        ours = self._guard(equity, currency, ours)
        for sym in self.symbols:
            try:
                self._decide(sym, ours, currency)
            except (RuntimeError, ValueError) as error:
                self._note_once(f"{sym}:{str(error)[:40]}", f"{sym}: {error}")
        self.state.save(self.state_path)

    # --- verification: nothing reaches Telegram unless the account shows it twice -----------------

    def _verified(self, symbol: str, open_: bool) -> bool:
        """Two separate reads of the account must both show the position open (or both gone)."""
        for i in range(2):
            if i:
                self.pause(VERIFY_PAUSE_S)
            if (symbol in self.broker.positions()) != open_:
                return False
        return True

    def _reconcile(self) -> dict[str, Position]:
        """A position the exchange closed (its stop or target) is announced only when confirmed twice."""
        ours = self.broker.positions()
        for sym, info in list(self.state.known.items()):
            if sym in ours and ours[sym].ticket == info.get("ticket"):
                continue
            if self._verified(sym, open_=False) or (sym in ours and ours[sym].ticket != info.get("ticket")):
                del self.state.known[sym]
                self._event("CLOSED_BY_EXCHANGE", sym)
                self.notify(f"⚪ 🤖 Bot {sym} · {self.broker.name}: la posición se cerró en el servidor (llegó a su "
                            f"stop o a su meta). Verificado 2 veces en la cuenta.")
            ours = self.broker.positions()
        return ours

    # --- one bot per open position ---------------------------------------------------------------------

    def watch(self) -> None:
        """Every 30 s: each open position's bot checks it on the exchange, moves its trailing stop and
        reports every 2 minutes; the Skeptic's past vetoes are scored; the Scout scans every symbol."""
        now = self.clock()
        if self._last_watch is not None and (now - self._last_watch).total_seconds() < self.watch_every_s:
            return
        self._last_watch = now
        try:
            self._owner_orders(now)
            if self.state.known:
                ours = self._reconcile()
                for sym in list(self.state.known):
                    pos = ours.get(sym)
                    if pos is None:
                        continue
                    price = self.broker.price(sym)
                    if self._owner_target_hit(pos, price):
                        continue
                    self._trail(pos, price)
                    self._report(pos, price, now)
            self._score_vetoes()
            if self.desk_rules is not None:
                self._scout(now)
            self._heartbeat(now)
        except (RuntimeError, ValueError) as error:
            self._note_once(f"watch:{str(error)[:40]}", f"bots: {error}")
        self.state.save(self.state_path)

    def _owner_orders(self, now: datetime) -> None:
        """The owner's Telegram orders for positions this bot holds: close now, or close at a gain he names."""
        if self.orders_path is None:
            return
        name = self.broker.name
        for order in O.pending(self.orders_path, self.state_path.parent / "ordenes.cursor", now):
            info = self.state.known.get(order.symbol)
            pos = self.broker.positions().get(order.symbol)
            if info is None or pos is None or pos.ticket != info.get("ticket"):
                continue  # not this bot's position; another bot (or none) holds it
            if order.kind == "CIERRA":
                self._close_by_owner(pos, "como ordenaste por Telegram")
            elif order.kind == "META" and order.value is not None:
                entry = Decimal(str(info.get("entry", pos.entry)))
                target = O.target_price(entry, pos.side, order.value, order.is_price)
                price = self.broker.price(order.symbol)
                ahead = target > price if pos.side == "BUY" else target < price
                if not ahead:
                    self.notify(f"⚠️ 🤖 Bot {order.symbol} · {name}: la meta {target:.6g} ya quedó atrás del precio "
                                f"({price}); si quieres salir ahora escribe CIERRA {order.symbol.removesuffix('USDT')}.")
                    continue
                info["owner_target"] = str(target)
                self._event("OWNER_TARGET", f"{order.symbol} {target}")
                self.notify(f"🎯 🤖 Bot {order.symbol} · {name}: cierro la {'compra' if pos.side == 'BUY' else 'venta en corto'} "
                            f"cuando llegue a {target:.6g} (precio ahora {price}), como ordenaste. El stop sigue puesto.")

    def _owner_target_hit(self, pos: Position, price: Decimal) -> bool:
        info = self.state.known.get(pos.symbol, {})
        target = info.get("owner_target")
        if target is None:
            return False
        hit = price >= Decimal(target) if pos.side == "BUY" else price <= Decimal(target)
        if hit:
            self._close_by_owner(pos, f"llegó a tu meta de {Decimal(target):.6g}")
        return hit

    def _close_by_owner(self, pos: Position, why: str) -> None:
        self.broker.close(pos)
        self.state.known.pop(pos.symbol, None)
        self._event("CLOSE", f"{pos.symbol} {pos.side}: orden del dueño")
        confirmed = self._verified(pos.symbol, open_=False)
        self.notify(f"✋ 🤖 Bot {pos.symbol} · {self.broker.name}: cerré la {'compra' if pos.side == 'BUY' else 'venta en corto'} "
                    f"{why}. " + ("Verificado 2 veces en la cuenta." if confirmed else
                                  "⚠️ La cuenta todavía la muestra abierta: la reviso en la próxima vuelta."))

    def _heartbeat(self, now: datetime) -> None:
        """Every few hours: the account's equity (two reads that agree), open positions and what the desk did."""
        if self.heartbeat_every_s is None:
            return
        if self._last_heartbeat is None:
            self._last_heartbeat = now  # the first one after a full interval, not at start-up
            return
        if (now - self._last_heartbeat).total_seconds() < self.heartbeat_every_s:
            return
        since = self._last_heartbeat
        first, currency = self.broker.equity()
        self.pause(VERIFY_PAUSE_S)
        second, _ = self.broker.equity()
        if first != second and abs(first - second) > max(abs(first), Decimal("1")) * Decimal("0.01"):
            return  # the two reads disagree: try again next pass rather than send a wrong number
        self._last_heartbeat = now
        recent = [e for e in self.state.events if e.get("at", "") >= since.isoformat()]
        count = {k: sum(1 for e in recent if e.get("kind") == k) for k in ("OPEN", "CLOSE", "CLOSED_BY_EXCHANGE", "VETO")}
        open_now = self.broker.positions()
        hours = round(self.heartbeat_every_s / 3600)
        status = {RUNNING: "operando", WAITING_OWNER: "esperando tu 'continuar'", GOAL: "meta del mes cumplida",
                  STOPPED: "detenido", PAUSED_API: "en pausa por fallos de conexión"}.get(self.state.status,
                                                                                           self.state.status)
        self.notify(f"🫀 {self.broker.name}: {status}. Saldo {min(first, second)} {currency} (revisado 2 veces). "
                    f"Posiciones abiertas: {len(open_now)}. En las últimas {hours} h: {count['OPEN']} entradas, "
                    f"{count['CLOSE'] + count['CLOSED_BY_EXCHANGE']} cierres y {count['VETO']} propuestas rechazadas "
                    f"por el Escéptico.")

    def _report(self, pos: Position, price: Decimal, now: datetime) -> None:
        last = self._last_report.get(pos.symbol)
        if last is not None and (now - last).total_seconds() < self.report_every_s:
            return
        self._last_report[pos.symbol] = now
        if not self._verified(pos.symbol, open_=True):
            return  # the account did not show it twice: the reconciliation will tell what happened
        info = self.state.known.get(pos.symbol, {})
        entry = Decimal(info.get("entry", pos.entry or price))
        pnl = (price - entry) * pos.qty if pos.side == "BUY" else (entry - price) * pos.qty
        r = Decimal(info.get("r", "0"))
        in_r = f" ({(pnl / (r * pos.qty)):+.2f}R)" if r > 0 and pos.qty > 0 else ""
        self.notify(f"📍 🤖 Bot {pos.symbol} · {self.broker.name}: {'compra' if pos.side == 'BUY' else 'venta en corto'} "
                    f"abierta a {entry}, precio {price:.6g}, resultado {pnl:+.2f}{in_r}. Stop {info.get('stop', '?')}, "
                    f"meta {info.get('target', '?')}. Posición confirmada en la cuenta.")

    def _score_vetoes(self) -> None:
        """Did the Skeptic's refusal avoid a loss? A refused long that would have hit its stop first did."""
        now = self.clock()
        for v in list(self.state.vetoes):
            if v.get("outcome"):
                continue
            if now - datetime.fromisoformat(v["at"]) > VETO_TRACK:
                v["outcome"] = "sin resultado"
            else:
                price = self.broker.price(v["symbol"])
                long = v["side"] == "BUY"
                stop, target = Decimal(v["stop"]), Decimal(v["target"])
                if (long and price <= stop) or (not long and price >= stop):
                    v["outcome"] = "evitó pérdida"
                elif (long and price >= target) or (not long and price <= target):
                    v["outcome"] = "dejó pasar ganancia"
            if v.get("outcome"):
                self.state.veto_score[v["outcome"]] = self.state.veto_score.get(v["outcome"], 0) + 1
                self._journal("Resultado de un veto del Escéptico",
                              [f"{v['symbol']} {v['side']}: {v['outcome']}", f"motivo: {'; '.join(v['reasons'])}"])
        self.state.vetoes = [v for v in self.state.vetoes if not v.get("outcome")][-200:]

    def _scout(self, now: datetime) -> None:
        """24/7: unusual volume or a sharp move -> the Chief evaluates that symbol right now."""
        assert self.desk_rules is not None
        ours = self.broker.positions()
        for sym in self.symbols:
            if sym in ours:
                continue
            last = self._last_scout.get(sym)
            if last is not None and now - last < timedelta(minutes=self.desk_rules.scout_alert_every_min):
                continue
            try:
                alert = D.scout(sym, self.broker.candles(sym, self.timeframe, 40), self.desk_rules)
            except (RuntimeError, ValueError):
                continue
            if alert is None:
                continue
            self._last_scout[sym] = now
            self._event("SCOUT", f"{sym}: {alert.text}")
            self._journal(f"Scout → Chief: {sym}", [alert.text])
            self.chatter(f"📡 Scout · {self.broker.name}: {sym} con {alert.text}. Le aviso al Chief para que lo "
                        f"evalúe ahora.")
            if self.state.status == RUNNING:
                try:
                    equity, currency = self.broker.equity()
                    self._decide(sym, ours, currency)
                except (RuntimeError, ValueError) as error:
                    self._note_once(f"{sym}:{str(error)[:40]}", f"{sym}: {error}")

    def _journal(self, title: str, lines: list[str]) -> None:
        if self.journal_dir is not None:
            D.journal(self.journal_dir, self.clock(), title, lines)

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
            if not info.get("trail_told"):
                info["trail_told"] = True
                self.chatter(f"🛡️ 🤖 Bot {pos.symbol} · {self.broker.name}: la operación ya gana más de lo que "
                            f"arriesgaba; el stop sube a {new} y seguirá la ganancia.")

    def _rally(self, sym: str) -> Optional[D.Alert]:
        """Daily bars, checked at most once an hour per coin: is this coin in a bull run?"""
        assert self.desk_rules is not None
        now = self.clock()
        cached = self._rally_seen.get(sym)
        if cached is not None and now - cached[0] < timedelta(hours=1):
            return cached[1]
        try:
            daily = self.broker.candles(sym, "1d", self.desk_rules.rally_lookback_days + 25)
            alert = D.rally(sym, daily, self.desk_rules)
        except Exception as error:  # noqa: BLE001 - no daily data must not stop a trade
            logger.warning("%s: sin velas diarias para el modo alcista (%s)", sym, error)
            alert = None
        self._rally_seen[sym] = (now, alert)
        return alert

    def _regime_up(self) -> Optional[bool]:
        """The regime brake (desk rule regime_btc_sma): is BTC above its N-day mean on closed daily bars? Checked at
        most once an hour; None (no brake) when the rule is off or BTC's daily bars cannot be read."""
        if self.desk_rules is None or self.desk_rules.regime_btc_sma is None:
            return None
        now = self.clock()
        at, before = self._regime
        if at is not None and now - at < timedelta(hours=1):
            return before
        days = self.desk_rules.regime_btc_sma
        try:
            up = D.btc_regime_up(self.broker.candles(REGIME_SYMBOL, "1d", days + 5), days, now)
        except Exception as error:  # noqa: BLE001 - no BTC data: no brake, like the research
            logger.warning("régimen: sin velas diarias de BTC (%s)", error)
            up = None
        if up is not None and before is not None and up != before:
            self.chatter(f"🧭 {self.broker.name}: BTC cerró {'sobre' if up else 'bajo'} su media de {days} días. "
                         + ("Vuelvo a buscar compras." if up else "Freno de riesgo: no abro nada y cierro lo abierto."))
        self._regime = (now, up)
        return up

    def risk_for(self, quality: float) -> Decimal:
        """1% to 15% of equity with the signal's quality (0-1); never with past wins or losses."""
        q = Decimal(str(max(0.0, min(1.0, quality))))
        return (self.risk_min_pct + (self.risk_max_pct - self.risk_min_pct) * q).quantize(Decimal("0.01"))

    def _signal(self, sym: str) -> tuple[Optional[str], float, pd.DataFrame]:
        data = self.broker.candles(sym, self.timeframe, 500)
        htf = self.broker.candles(sym, self.confirm_timeframe, 200) if self.confirm_timeframe else None
        top_reader = getattr(self.broker, "top_traders", None)
        top = top_reader(sym) if top_reader is not None else None
        out = self.signal(sym, data, htf, top=top)
        if isinstance(out, tuple):
            return out[0], float(out[1]), data
        return out, 0.0, data  # type: ignore[return-value]

    def _mood(self, sym: str) -> tuple[Optional[D.Mood], Optional[float]]:
        """Sentiment: funding, top traders, Fear & Greed (cached 30 min). None without the desk."""
        if self.desk_rules is None:
            return None, None
        funding_reader = getattr(self.broker, "funding", None)
        top_reader = getattr(self.broker, "top_traders", None)
        funding = funding_reader(sym) if funding_reader is not None else None
        top = top_reader(sym) if top_reader is not None else None
        at, fng = self._fng
        if self.news_get is not None and (at is None or self.clock() - at > timedelta(minutes=30)):
            fng = D.fear_greed(self.news_get)
            self._fng = (self.clock(), fng)
        return D.sentiment(funding, top, fng), funding

    def _decide(self, sym: str, ours: dict[str, Position], currency: str) -> None:
        s, name = self.state, self.broker.name
        signal, quality, data = self._signal(sym)
        pos = ours.get(sym)
        up = self._regime_up()
        if pos is not None and up is not None and (pos.side == "SELL" or not up):
            self.broker.close(pos)  # the regime brake: only longs, and only while BTC is above its mean
            ours.pop(sym)
            s.known.pop(sym, None)
            self._event("CLOSE", f"{sym} {pos.side}: freno de régimen")
            confirmed = self._verified(sym, open_=False)
            self.notify(f"🧭 🤖 Bot {sym} · {name}: cerré la {'compra' if pos.side == 'BUY' else 'venta en corto'} por el "
                        f"freno de riesgo (solo compras, y solo con BTC sobre su media). "
                        + ("Verificado 2 veces en la cuenta." if confirmed else
                           "⚠️ La cuenta todavía la muestra abierta: la reviso en la próxima vuelta."))
            return
        if pos is not None:
            riding = pos.side == "BUY" and bool(s.known.get(sym, {}).get("rally"))
            if signal is not None and signal != pos.side and not riding:  # a bull run ends only at the trailing stop
                self.broker.close(pos)
                ours.pop(sym)
                s.known.pop(sym, None)
                self._event("CLOSE", f"{sym} {pos.side}: señal {signal}")
                confirmed = self._verified(sym, open_=False)
                self.notify(f"🔁 🤖 Bot {sym} · {name}: cerré la {'compra' if pos.side == 'BUY' else 'venta en corto'}: "
                            f"el mercado cambió de dirección. "
                            + ("Verificado 2 veces en la cuenta." if confirmed else
                               "⚠️ La cuenta todavía la muestra abierta: la reviso en la próxima vuelta."))
            else:
                self._trail(pos, Decimal(str(data["close"].iloc[-1])))
            return
        if signal is None or s.status != RUNNING or s.halted or len(ours) >= self.max_open:
            return
        if up is not None and (signal == "SELL" or not up):
            return  # the regime brake keeps the desk flat
        quiet = self._last_veto.get(sym)
        if quiet is not None and quiet[0] == signal and self.clock() - quiet[1] < VETO_QUIET:
            return  # refused minutes ago for this same side: not re-proposed every 30 s
        mood, funding = self._mood(sym)
        # No sentiment tilt on the size (Quant, 2026-10-13, docs/research/sentimiento/): where the mood "agreed"
        # most, longs did slightly worse at 24 h. The mood still feeds the Skeptic and the journal.
        risk = self.risk_for(quality)
        plan = self.broker.plan(sym, signal, risk, self.timeframe)
        run = self._rally(sym) if signal == "BUY" and self.desk_rules is not None else None
        if self.desk_rules is not None:  # take profit at 3-5%, or let a bull run go with the trailing stop
            plan = replace(plan, tp=D.shape_target(plan.price, plan.tp, plan.side, self.desk_rules, run is not None,
                                                  plan.sl))
        headlines = D.news(sym, self.news_get) if (self.desk_rules is not None and self.news_get is not None) else []
        if self.desk_rules is not None and mood is not None:
            verdict = D.skeptic(signal, plan.price, plan.sl, plan.tp, mood, funding, self.desk_rules)
            if not verdict.approved:
                self._last_veto[sym] = (signal, self.clock())
                s.vetoes.append({"symbol": sym, "side": signal, "entry": str(plan.price), "stop": str(plan.sl),
                                 "target": str(plan.tp), "reasons": list(verdict.reasons),
                                 "at": self.clock().isoformat()})
                self._event("VETO", f"{sym} {signal}: {'; '.join(verdict.reasons)}")
                self._journal(f"Escéptico rechaza {signal} {sym}", [
                    f"plan: entrada {plan.price}, stop {plan.sl}, meta {plan.tp}, riesgo {risk}%",
                    f"sentimiento {mood.score:+.2f} {mood.parts}", *[f"motivo: {r}" for r in verdict.reasons],
                    *[f"noticia: [{h.title}]({h.link}) · {h.source} · {h.published}" for h in headlines]])
                self.chatter(f"🧐 Escéptico · {name}: rechazo {'la compra' if signal == 'BUY' else 'la venta en corto'} "
                            f"de {sym}: {'; '.join(verdict.reasons)}. Queda anotado y mediré si el veto acertó.")
                return
        ticket = self.broker.open(plan)
        ours[sym] = Position(sym, plan.side, plan.qty, ticket, plan.price)
        s.known[sym] = {"ticket": ticket, "side": plan.side, "entry": str(plan.price), "stop": str(plan.sl),
                        "target": str(plan.tp), "r": str(abs(plan.price - plan.sl)), "risk_pct": str(risk),
                        "quality": quality, "rally": run is not None}
        self._event("OPEN", f"{plan.side} {plan.qty} {sym} @ {plan.price} SL {plan.sl} TP {plan.tp} "
                            f"riesgo {risk}% calidad {quality}")
        self._journal(f"Chief ejecuta {plan.side} {sym}", [
            f"entrada {plan.price}, stop {plan.sl}, meta {plan.tp}, cantidad {plan.qty}, riesgo {risk}% "
            f"(calidad {quality:.0%}), pérdida máxima {plan.risk_money} {currency}",
            *([f"sentimiento {mood.score:+.2f} {mood.parts}"] if mood is not None else []),
            *[f"noticia: [{h.title}]({h.link}) · {h.source} · {h.published}" for h in headlines]])
        if not self._verified(sym, open_=True):
            self.notify(f"⚠️ 🤖 Bot {sym} · {name}: envié la orden pero la cuenta no la muestra 2 veces seguidas. "
                        f"No la doy por abierta hasta verla; la reviso en la próxima vuelta.")
            return
        verb = "Compré" if plan.side == "BUY" else "Vendí en corto"
        why = "el mercado está subiendo" if plan.side == "BUY" else "el mercado está bajando"
        if run is not None:
            why = (f"{sym} está en {run.text}. 🚀 Modo alcista: no cierro en la meta; el stop sigue la ganancia "
                   f"y la operación queda abierta mientras siga subiendo")
        self.notify(f"{'🟢' if plan.side == 'BUY' else '🔴'} 🤖 Bot {sym} · {name}: {verb} {plan.qty} {self.broker.unit} "
                    f"a {plan.price} porque {why} (calidad de la señal {quality:.0%}, riesgo {risk}%). Stop en {plan.sl}, "
                    f"meta en {plan.tp}, puestos en el servidor. Si toca el stop se pierden unos {plan.risk_money} "
                    f"{currency}. Verificado 2 veces en la cuenta.")

    def run(self, max_iterations: Optional[int] = None, sleep: Callable[[float], None] = time.sleep) -> None:
        n = 0
        while (max_iterations is None or n < max_iterations) and self.state.status != STOPPED:
            n += 1
            if self.decision_due():
                try:
                    self.step()
                    if self.state.status == PAUSED_API:
                        self.state.status = RUNNING
                        self.notify(f"✅ {self.broker.name}: la conexión volvió; retomo las entradas nuevas.")
                    self._failures = 0
                except (RuntimeError, ValueError) as error:  # terminal closed, exchange down: retry next slot
                    logger.warning("%s: %s", self.broker.name, error)
                    self._note_once(f"step:{str(error)[:40]}", str(error))
                    self._failures += 1
                    if self._failures >= API_FAILURES_TO_PAUSE and self.state.status == RUNNING:
                        self.state.status = PAUSED_API  # kill switch: no new entries while the API fails
                        self.notify(f"🛑 {self.broker.name}: {self._failures} fallos seguidos de conexión. No abro "
                                    f"nada nuevo hasta que vuelva; los stops siguen puestos en el servidor.")
                    self.state.save(self.state_path)
            self.watch()  # each position's bot, the veto scoring and the Scout, every 30 s
            sleep(10)


def owner_continue(state_dir: Path) -> None:
    """The owner's "continuar": the running engine picks it up at its next decision."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / CONTINUE_FILE).write_text("continuar\n", encoding="utf-8")
