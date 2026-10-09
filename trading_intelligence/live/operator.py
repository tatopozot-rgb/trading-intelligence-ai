"""
Operator for REAL trading (route B). Run on the owner's PC by Claude Code local; the
owner gives the orders in plain words and Claude Code local translates them:

  "trading sin parar con 50"      -> iniciar --capital 50 --perfil tendencia --real   (4h)
  "usa también rangos"            -> iniciar ... --perfil tendencia_rango
  "copia al trader X"             -> iniciar ... --perfil copiar  (+ lider --archivo ...)
  "continúa" (after the $2 warning) -> continuar
  "agrega 20"                     -> agregar --capital 20
  "para" / "para y cierra"        -> parar [--cerrar]
  "cómo vamos"                    -> estado / reporte --etapa medio

    python -m trading_intelligence.live.operator iniciar --capital 50 --perfil tendencia --real
    python -m trading_intelligence.live.operator estado

Without --real it runs in SHADOW: same decisions, simulated fills, no order sent.
Every order comes from the decision engine below, through the RiskEngine and the
owner's loss guard. Only one operator may run at a time.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Callable, Optional

from trading_intelligence.live import messages, mirror, telegram_notify
from trading_intelligence.live.binance_live import (
    Credentials,
    Fill,
    LiveError,
    SpotTrader,
    StopState,
    SymbolRules,
    Unreconciled,
)
from trading_intelligence.live.limits import LimitsNotApproved, OwnerLimits, load_limits
from trading_intelligence.live.session import STOPPED, Session

logger = logging.getLogger(__name__)
DEFAULT_DIR = Path("live_runs/current")
PROFILES = ("tendencia", "tendencia_rango", "copiar")
# Real-data walk-forward (CHECKPOINT section 45): at 1h both profiles LOSE after fees
# (-0.80% / -0.67% per trade, p < 0.01). 4h is positive but not proven (p ~ 0.09).
# Real orders are allowed only at a timeframe that has not been shown to lose, plus 20m and
# 5m: the owner chose them in writing on 2026-10-09 ("Todo a 20 min"; then "dentro de esos
# horarios es sin parar y fuera de esos horarios cada 20 minutos"), after being shown that
# the 20-minute reference backfill (docs/experimento_horarios/resumen.md) lost ~0.3-0.5% per
# trade after fees for every strategy. With windows, a 5m session decides at every 5m bar
# inside them and every OUTSIDE_WINDOW_EVERY outside them; stops are checked every minute.
REAL_TIMEFRAMES = frozenset({"4h", "20m", "5m"})
WINDOWED_TIMEFRAMES = frozenset({"5m", "20m"})
OUTSIDE_WINDOW_EVERY = timedelta(minutes=20)
ECUADOR_UTC_OFFSET_H = -5
# The owner's windows, Ecuador time, every day: his 07-10 and the 17-19 one he gave the leader.
OWNER_WINDOWS = ("07-10", "17-19")
DEFAULT_TIMEFRAME = "4h"
# Trailing stop defaults (owner may change per session with --trailing; 0 turns it off).
# Chosen, not validated by walk-forward: the research engine's opt-in trailing stop cut the
# survival bench's mean max drawdown from 34.7% to 23.0% (CHECKPOINT section 30).
DEFAULT_TRAILING_PCT = Decimal("3")
DEFAULT_TRAIL_AFTER_PCT = Decimal("2")
MID_REPORT_EVERY = timedelta(hours=12)
SUMMARY_EVERY = timedelta(hours=4)  # short status line to the owner (console and Telegram)

AGENTS_BY_PROFILE = {
    "tendencia": ["Detector de régimen", "Estrategia de tendencia (cruce de medias)", "Motor de riesgo (veto)",
                  "Guardia de pérdida del dueño", "Ejecución real (Binance Spot)"],
    "tendencia_rango": ["Detector de régimen", "Estrategia de tendencia (cruce de medias)",
                        "Estrategia de rango (Bollinger)", "Motor de riesgo (veto)",
                        "Guardia de pérdida del dueño", "Ejecución real (Binance Spot)"],
    "copiar": ["Revisión de top traders", "Posiciones del líder leídas en la app", "Guardia de pérdida del dueño",
               "Ejecución real (Binance Spot)"],
}
EXEC_REAL = "Ejecución real (Binance Spot)"
EXEC_SHADOW = "Ejecución simulada (SHADOW, sin órdenes)"
ALL_AGENTS = sorted({a for v in AGENTS_BY_PROFILE.values() for a in v} | {"Seguidor de copias (simulación)", EXEC_SHADOW})


class ShadowTrader:
    """Same interface as SpotTrader: public prices, simulated fills (0.1% fee), no order sent."""

    def __init__(self, price_fn: Callable[[str], Decimal], rules_fn: Callable[[str], SymbolRules],
                 free_usdt: Decimal = Decimal("1000000")) -> None:
        self._price, self._rules, self._free = price_fn, rules_fn, free_usdt
        self.key_checked = True
        self.sent: list[tuple[str, str, Decimal]] = []

    def price(self, symbol: str) -> Decimal:
        return self._price(symbol)

    def rules(self, symbol: str) -> SymbolRules:
        return self._rules(symbol)

    def free_balance(self, asset: str) -> Decimal:
        return self._free

    def unresolved(self) -> list[str]:
        return []

    def reconcile(self, fee_price: Callable[[str], Decimal]) -> list[Fill]:
        return []

    def market_order(self, symbol: str, side: str, quantity: Decimal, fee_price: Callable[[str], Decimal]) -> Fill:
        p = self._price(symbol)
        quote = quantity * p
        fee = quote * Decimal("0.001")
        self.sent.append((symbol, side, quantity))
        net_quote = quote + fee if side == "BUY" else quote - fee
        return Fill(f"shadow-{len(self.sent)}", symbol, side, "FILLED", quantity, net_quote, fee, p)

    # Guard stops are only simulated: the operator's own one-minute stop does the selling.
    def place_stop(self, symbol: str, quantity: Decimal, stop_price: Decimal) -> str:
        self.sent.append((symbol, "STOP_LOSS", quantity))
        return f"shadow-stop-{len(self.sent)}"

    def stop_status(self, symbol: str, client_id: str, fee_price: Callable[[str], Decimal]) -> StopState:
        return StopState("NEW")

    def cancel_stop(self, symbol: str, client_id: str, fee_price: Callable[[str], Decimal]) -> StopState:
        return StopState("CANCELED")


def parse_windows(spec: list[str]) -> list[tuple[int, int]]:
    """"07-10" (Ecuador hours) -> (start, length) in minutes of the UTC day."""
    out = []
    for item in spec:
        try:
            a, b = (int(x) for x in item.split("-"))
        except ValueError:
            raise ValueError(f"window {item!r}: use Ecuador hours like 07-10") from None
        if not (0 <= a <= 23 and 1 <= b <= 24 and a < b):
            raise ValueError(f"window {item!r}: hours 0-24, start before end")
        out.append((((a - ECUADOR_UTC_OFFSET_H) * 60) % 1440, (b - a) * 60))
    return out


def in_windows(windows: list[tuple[int, int]], now: datetime) -> bool:
    m = now.astimezone(timezone.utc).hour * 60 + now.astimezone(timezone.utc).minute
    return any((m - start) % 1440 < length for start, length in windows)


def engine_risk_overrides(limits: OwnerLimits) -> dict:
    """The decision engine's RiskConfig, aligned with the owner's limits so it never
    trips earlier than the owner's own guard (which acts on real money)."""
    loss = float(limits.loss_limit_pct)
    return {
        "max_position_size_pct": float(limits.max_position_pct),
        "max_total_exposure_pct": 100.0,
        "max_correlated_exposure_pct": float(limits.max_position_pct),
        "max_open_positions": limits.max_open_positions,
        "daily_loss_limit_pct": loss,
        "drawdown_pause_pct": loss * 0.95,
        "drawdown_halt_pct": loss,
        "max_daily_turnover_pct": 1000.0,
        "max_trades_per_day": 100,
    }


def router_factory(profile: str, timeframe: str) -> Callable[[str], object]:
    from trading_intelligence.strategy.router import default_router, router_with_range_reversion

    if profile == "tendencia_rango":
        return lambda sym: router_with_range_reversion(sym)
    return lambda sym: default_router(sym, timeframe)


def engine_targets(loop) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """(fraction of equity per symbol, protective stop per symbol) from the PAPER engine,
    counting entries already decided but not yet filled (the real account acts now)."""
    paper = loop.runner.paper
    equity = paper.last_known_equity()
    if equity <= 0:
        return {}, {}
    marks = getattr(paper, "_last_price", {})
    values: dict[str, Decimal] = {}
    stops: dict[str, Decimal] = {}
    for sym, pos in paper.positions.items():
        values[sym] = values.get(sym, Decimal("0")) + pos.quantity * marks.get(sym, pos.avg_entry_price)
    for order in paper.pending_orders:
        if order.side == "BUY" and order.order_type == "MARKET":
            values[order.symbol] = values.get(order.symbol, Decimal("0")) + order.quantity * marks.get(
                order.symbol, Decimal("0"))
            if order.attached_stop_price is not None:
                stops[order.symbol] = order.attached_stop_price
        elif order.side == "SELL" and order.order_type == "STOP" and order.stop_price is not None:
            stops[order.symbol] = order.stop_price
    return {s: v / equity for s, v in values.items() if v > 0}, stops


def leader_targets(path: Path, max_age: timedelta, now: datetime) -> tuple[dict[str, Decimal], Optional[str]]:
    """Positions of the copied lead trader, written by Claude Code local after reading the
    trader's page in the app: {"read_at": iso, "trader": id, "positions": {"BTCUSDT": 0.4}}.
    Stale or missing -> no target (exits still follow the guard and stops)."""
    if not path.exists():
        return {}, "LEADER_POSITIONS_MISSING"
    data = json.loads(path.read_text(encoding="utf-8"))
    read_at = datetime.fromisoformat(data["read_at"])
    if read_at.tzinfo is None or now - read_at > max_age:
        return {}, "LEADER_POSITIONS_STALE"
    out = {}
    for sym, frac in data.get("positions", {}).items():
        f = Decimal(str(frac))
        if not f.is_finite() or f < 0 or f > 1:
            return {}, "LEADER_POSITIONS_INVALID"
        out[str(sym)] = f
    return out, None


class Operator:
    def __init__(self, state_dir: Path, trader, limits: OwnerLimits, *, profile: str, timeframe: str,
                 symbols: list[str], loop=None, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 notify: Callable[[str], None] = print, real: bool = False,
                 end_at: Optional[datetime] = None, profit_target_pct: Optional[Decimal] = None,
                 trailing_pct: Decimal = DEFAULT_TRAILING_PCT, trail_after_pct: Decimal = DEFAULT_TRAIL_AFTER_PCT,
                 windows: Optional[list[str]] = None) -> None:
        self.dir = Path(state_dir)
        self.trader = trader
        self.limits = limits
        self.profile = profile
        self.timeframe = timeframe
        self.symbols = symbols
        self.loop = loop
        self.clock = clock
        self.notify = notify
        self.real = real
        self.end_at = end_at  # owner's "por N horas": close the session's positions and finish
        self.profit_target_pct = profit_target_pct  # owner's "hasta ganar N%": take the gain and finish
        self.trailing_pct = trailing_pct  # 0 = off
        self.trail_after_pct = trail_after_pct
        self.window_spec = list(windows or [])
        self.windows = parse_windows(self.window_spec)  # empty: decide at every bar, all day
        self._was_in_window: Optional[bool] = None
        self._last_slow_slot: Optional[int] = None
        self.session = Session.load(self.dir / "session.json")
        self.last_mid_report = self.clock()
        self.last_summary = self.clock()

    # --- one pass ------------------------------------------------------------------

    def _apply_owner_orders(self) -> None:
        """The owner's commands (continuar / agregar / adoptar) reach the RUNNING operator
        through its inbox. Writing session.json from another process does not work: this
        process keeps the session in memory and saves it every pass."""
        inbox = self.dir / INBOX
        if not inbox.exists():
            return
        taken = inbox.with_suffix(".taken")
        os.replace(inbox, taken)  # atomic: an order written meanwhile goes to a fresh inbox
        s = self.session
        for line in taken.read_text(encoding="utf-8").splitlines():
            try:
                order = json.loads(line)
                cmd = order["cmd"]
                if cmd == "continuar":
                    s.owner_continue()
                    self.notify("✅ Entendido: sigo operando hasta el límite de pérdida.")
                elif cmd == "agregar":
                    amount = Decimal(order["capital"])
                    s.add_capital(amount)
                    self.notify(f"✅ Sumé {messages.usdt(amount)} a la sesión. Capital ahora: {messages.usdt(s.capital)}.")
                elif cmd == "adoptar":
                    self.notify(self._adopt(order["simbolo"]))
                else:
                    s.note("OWNER", f"orden desconocida ignorada: {cmd}")
            except (ValueError, KeyError, TypeError, LiveError) as error:
                s.note("OWNER", f"orden no aplicada ({line[:80]}): {error}")
                self.notify(f"⚠️ No pude aplicar tu orden: {error}")
        taken.unlink()

    def _adopt(self, symbol: str) -> str:
        """Owner: "vas a trabajar con todo lo que tengamos": coins already in Spot join the
        session at their current value (capital grows by the same amount, so it is not a
        gain); from then on the strategy, the stops and the loss guard manage them."""
        s = self.session
        if symbol not in self.limits.allowed_symbols:
            return f"⚠️ {messages.coin(symbol)} no está entre las monedas aprobadas; no la sumé."
        if symbol in s.holdings:
            return f"La sesión ya opera {messages.coin(symbol)}; no hace falta sumarla."
        qty = self.trader.free_balance(symbol[:-4])
        price = self.trader.price(symbol)
        value = (qty * price).quantize(Decimal("0.01"))
        if qty <= 0:
            return f"No tienes {messages.coin(symbol)} libre en Spot para sumar."
        s.add_capital(value)
        s.record_buy(symbol, qty, value, Decimal("0"), "ADOPTED")
        rules = self.trader.rules(symbol)
        small = rules.floor_qty(qty) * price < rules.min_notional
        tail = (" Es menos del mínimo de venta de Binance (5 USDT): se venderá junto con la próxima compra de "
                f"{messages.coin(symbol)}, o con el comando pasar-a-usdt.") if small else ""
        return (f"✅ Sumé a la sesión tu {messages.coin(symbol)} ({qty}, unos {messages.usdt(value)}). Desde ahora "
                f"lo maneja el operador con sus reglas y stops.{tail}")

    def step(self, decide: bool) -> list[mirror.Action]:
        s = self.session
        actions: list[mirror.Action] = []
        self._apply_owner_orders()
        guarded_before = set(s.guard_stops)
        for fill in self.trader.reconcile(self.trader.price):
            mirror._apply_fill(s, fill, "RECONCILED")
            s.note("RECONCILED", f"{fill.side} {fill.symbol} {fill.executed_qty}")
        if self.trader.unresolved():
            s.note("WAIT", "orden sin conciliar: no se envía nada hasta resolverla")
            self._save()
            return actions
        try:
            for a in mirror.sync_guards(s, self.trader):  # executed on Binance while we were away?
                s.note("EXCHANGE_STOP", f"{a.symbol}: {a.reason}")
                actions.append(a)
        except LiveError as error:
            s.note("ERROR", f"guard stop check: {error}")

        targets: Optional[dict[str, Decimal]] = None  # None: no new decision this pass
        stops: dict[str, Decimal] = {}
        if decide:
            if self.profile == "copiar":
                read, problem = leader_targets(self.dir / "leader_positions.json", timedelta(hours=6), self.clock())
                if problem:
                    s.note("COPY", f"{problem}: no new decision; guard and stops keep working")
                else:
                    targets = read
            elif self.loop is not None:
                self.loop.tick()
                targets, stops = engine_targets(self.loop)
            self._last_stops = stops
        stops = stops or getattr(self, "_last_stops", {})

        needed = sorted(set(s.holdings) | set(targets or {}))
        prices = {sym: self.trader.price(sym) for sym in needed}
        if self.windows:
            inside = in_windows(self.windows, self.clock())
            if inside != self._was_in_window:
                if self._was_in_window is not None or inside:
                    self.notify(messages.window_open(self.window_spec, self._bar_minutes()) if inside
                                else messages.window_closed(int(OUTSIDE_WINDOW_EVERY.total_seconds() // 60)))
                self._was_in_window = inside
        stops = self._with_trailing(stops, prices)
        message = s.evaluate(prices, self.limits)
        if message:
            loss, limit = s.capital - s.equity(prices), self.limits.loss_limit_usd(s.capital)
            self.notify(messages.stopped(loss, limit) if s.status == STOPPED else messages.warning(loss, limit))
            (self.dir / "AVISO.txt").write_text(f"{self.clock().isoformat()} {message}\n", encoding="utf-8")
        try:
            if s.status == STOPPED and s.holdings:
                actions += mirror.flatten(s, self.trader, "LOSS_LIMIT")
            else:
                actions += mirror.enforce_stops(s, self.trader, stops, prices)
                if targets is not None and s.status != STOPPED:
                    prices = {sym: self.trader.price(sym) for sym in sorted(set(s.holdings) | set(targets))}
                    actions += mirror.apply_targets(s, self.trader, targets, self.limits, prices, self.profile)
                if s.holdings:
                    held_prices = {sym: self.trader.price(sym) for sym in s.holdings}
                    actions += mirror.place_guards(s, self.trader, stops, held_prices)
        except Unreconciled as error:
            s.note("UNCERTAIN", str(error))
        except LiveError as error:
            s.note("ERROR", str(error))
            self.notify(messages.error(str(error)))
        for a in actions:
            if a.kind == "SKIP":
                s.note("SKIP", f"{a.symbol}: {a.reason}")
            elif a.kind == "BUY":
                trade = self._trade_for(a)
                at = Decimal(trade["usdt"]) / Decimal(trade["qty"]) if trade and Decimal(trade["qty"]) > 0 else None
                self.notify(messages.buy(a.symbol, a.usdt, at, a.reason, self.real))
            elif a.kind == "SELL":
                trade = self._trade_for(a)
                pnl = Decimal(trade["pnl"]) if trade and trade.get("pnl") is not None else None
                self.notify(messages.sell(a.symbol, a.usdt, pnl, a.reason, self.real))
            elif a.kind == "GUARD" and a.symbol not in guarded_before:
                self.notify(messages.guard(a.symbol, Decimal(a.reason.split(":", 1)[-1])))
        if self.clock() - self.last_summary >= SUMMARY_EVERY:
            self.notify(self.summary(prices))
            self.last_summary = self.clock()
        if self.clock() - self.last_mid_report >= MID_REPORT_EVERY:
            self.write_report("medio")
            self.last_mid_report = self.clock()
        self._save()
        return actions

    def _bar_minutes(self) -> int:
        from trading_intelligence.execution.paper_loop import INTERVAL_SECONDS

        return INTERVAL_SECONDS[self.timeframe] // 60

    def decision_due(self) -> bool:
        """Owner: inside his windows "sin parar" (every bar), outside them every 20 minutes.
        Skipped bars are not lost: the engine replays them at its next tick."""
        now = self.clock()
        if not self.windows or in_windows(self.windows, now):
            return True
        slot = int((now.timestamp() - 30) // OUTSIDE_WINDOW_EVERY.total_seconds())
        if slot == self._last_slow_slot:
            return False
        self._last_slow_slot = slot
        return True

    def _with_trailing(self, stops: dict[str, Decimal], prices: dict[str, Decimal]) -> dict[str, Decimal]:
        """Owner: "estar en revisión continua hasta cumplir la meta de esa transacción". Every
        pass (each minute) the highest price since entry is tracked; once a position is up
        trail_after_pct, its stop follows that peak at trailing_pct below it. The effective stop
        is never lower than the engine's, and it also moves the guard stop resting on Binance."""
        out = dict(stops)
        s = self.session
        for sym in list(s.trail_peaks):
            if sym not in s.holdings:
                del s.trail_peaks[sym]
        if self.trailing_pct <= 0:
            return out
        for sym, held in s.holdings.items():
            price = prices.get(sym)
            if price is None:
                continue
            peak = max(s.trail_peaks.get(sym, price), price)
            s.trail_peaks[sym] = peak
            if held.avg_cost > 0 and peak >= held.avg_cost * (1 + self.trail_after_pct / 100):
                trail = peak * (1 - self.trailing_pct / 100)
                if trail > out.get(sym, Decimal("0")):
                    out[sym] = trail
        return out

    def only_dust_left(self) -> bool:
        """Nothing sellable remains (holdings under the exchange minimum cannot be sold)."""
        for sym, h in self.session.holdings.items():
            rules = self.trader.rules(sym)
            if rules.floor_qty(h.qty) * self.trader.price(sym) >= rules.min_notional:
                return False
        return True

    def _trade_for(self, action: mirror.Action) -> Optional[dict]:
        """The session's trade record behind an executed action (latest match), if any."""
        side = "BUY" if action.kind == "BUY" else "SELL"
        for trade in reversed(self.session.trades):
            if trade["side"] == side and trade["symbol"] == action.symbol and \
                    trade["reason"].split(":")[0] == action.reason.split(":")[0]:
                return trade
        return None

    def summary(self, prices: dict[str, Decimal]) -> str:
        s = self.session
        held = {sym: prices.get(sym) or self.trader.price(sym) for sym in s.holdings}
        change = {sym: (held[sym] / h.avg_cost - 1) * 100 if h.avg_cost > 0 else None
                  for sym, h in s.holdings.items()}
        return messages.summary(s.capital, s.equity(held), self.limits.loss_limit_usd(s.capital), change, self.real)

    def _save(self) -> None:
        self.session.save(self.dir / "session.json")
        prices = {sym: self.trader.price(sym) for sym in self.session.holdings}
        status = {
            "at": self.clock().isoformat(), "real": self.real, "profile": self.profile, "status": self.session.status,
            "capital": str(self.session.capital), "equity": str(self.session.equity(prices).quantize(Decimal("0.01"))),
            "loss_limit_usd": str(self.limits.loss_limit_usd(self.session.capital)),
            "warn_at_usd": str(self.limits.warn_at_usd(self.session.capital)),
            "holdings": {k: str(v.qty) for k, v in self.session.holdings.items()},
        }
        (self.dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")

    # --- reports (for the owner and GPT Work) --------------------------------------

    def write_report(self, stage: str) -> Path:
        from trading_intelligence.live.report import render_report

        decisions = []
        if self.loop is not None and (self.loop.state_path).exists():
            decisions = json.loads(self.loop.state_path.read_text(encoding="utf-8")).get("journal", [])
        prices = {sym: self.trader.price(sym) for sym in self.session.holdings}
        text = render_report(stage, self.session, prices, self.limits, real=self.real, profile=self.profile,
                             agents_used=[a if self.real or a != EXEC_REAL else EXEC_SHADOW
                                          for a in AGENTS_BY_PROFILE[self.profile]],
                             all_agents=ALL_AGENTS,
                             decisions=decisions, timeframe=self.timeframe, symbols=self.symbols)
        path = self.dir / f"reporte_{stage}_{self.clock().strftime('%Y%m%dT%H%M')}.md"
        path.write_text(text, encoding="utf-8")
        return path

    def finish_reason(self) -> Optional[str]:
        """The owner's own exits: a time box or a profit target on the session's equity.
        Both only ever close positions; neither can open one or raise risk."""
        if self.end_at is not None and self.clock() >= self.end_at:
            return f"TIEMPO_CUMPLIDO: terminó el plazo pedido por el dueño ({self.end_at.isoformat(timespec='minutes')})"
        if self.profit_target_pct is not None:
            prices = {sym: self.trader.price(sym) for sym in self.session.holdings}
            gain = self.session.equity(prices) - self.session.capital
            if gain >= self.session.capital * self.profit_target_pct / 100:
                return (f"META_ALCANZADA: ganancia {gain:.2f} USDT >= {self.profit_target_pct}% de "
                        f"{self.session.capital:.2f}; se toma la ganancia")
        return None

    def _finish(self, reason: str, close: bool) -> None:
        if not close:
            # Coins the owner keeps are his: no stop of this session may sell them later.
            for sym in sorted(self.session.guard_stops):
                try:
                    if not mirror.release_guard(self.session, self.trader, sym):
                        self.session.note("WARN", f"{sym}: guard stop could not be confirmed cancelled; "
                                                  "check open orders in Binance")
                except LiveError as error:
                    self.session.note("ERROR", f"{sym}: guard stop cancel failed: {error}")
        if close and self.session.holdings:
            try:
                mirror.flatten(self.session, self.trader, reason.split(":")[0])
            except Unreconciled as error:
                self.session.note("UNCERTAIN", str(error))
            except LiveError as error:
                self.session.note("ERROR", str(error))
                self.notify(messages.error(f"al cerrar: {error}"))
        self.session.status = STOPPED  # a finished session never buys again; a new one can start
        self.session.note("FIN", reason)
        left = {sym: self.trader.price(sym) for sym in self.session.holdings}
        self.notify(messages.finished(reason, self.session.capital, self.session.equity(left)))
        (self.dir / "AVISO.txt").write_text(f"{self.clock().isoformat()} {reason}\n", encoding="utf-8")
        self._save()
        self.write_report("final")

    def run(self, poll_seconds: float = 60.0, sleep: Callable[[float], None] = time.sleep,
            max_iterations: Optional[int] = None, start_report: bool = False) -> None:
        """start_report: write the start report right after the first decision pass, so it
        shows the market read (regime and decision per coin), not an empty page."""
        from trading_intelligence.execution.paper_loop import INTERVAL_SECONDS

        interval = INTERVAL_SECONDS[self.timeframe]
        last_bar: Optional[int] = None
        n = 0
        while max_iterations is None or n < max_iterations:
            if (self.dir / "STOP").exists():
                close = (self.dir / "STOP").read_text(encoding="utf-8").strip() == "cerrar"
                self._finish("OWNER_STOP: parada ordenada por el dueño" + (" con cierre" if close else ""), close)
                return
            reason = self.finish_reason()
            if reason:
                self._finish(reason, close=True)
                return
            # 30 s after a bar closes, so the exchange has published it.
            bar = int((self.clock().timestamp() - 30) // interval)
            decide = bar != last_bar and self.decision_due()
            self.step(decide)
            last_bar = bar
            if start_report and n == 0:
                path = self.write_report("inicio")
                logger.info("start report: %s", path)
                self.notify(messages.started(self.session.capital, self.limits.loss_limit_usd(self.session.capital),
                                             self.symbols, self.real))
            if self.session.status == STOPPED and self.only_dust_left():
                self.write_report("final")
                return
            n += 1
            if max_iterations is not None and n >= max_iterations:
                self.write_report("final")  # a bounded run (rehearsal) still leaves its summary
                return
            sleep(poll_seconds)


# --- CLI ------------------------------------------------------------------------------


BROKERS = ("binance", "xm")


def _xm_feed_and_trader():
    """XM through the owner's MT5 terminal: candles for the engine, a SHADOW trader on its prices.
    Lots are mapped to units of the underlying (lots x contract size) so the engine's sizing works."""
    from trading_intelligence.live.xm_mt5 import XmKlines, XmReader

    reader = XmReader()
    reader.connect()
    feed = XmKlines(reader)

    def rules(symbol: str) -> SymbolRules:
        sh = reader.sheet(symbol)
        return SymbolRules(step=sh.volume_step * sh.contract_size, min_qty=sh.volume_min * sh.contract_size,
                           min_notional=Decimal("0"))

    return feed, ShadowTrader(feed.get_current_price, rules)


def _trader(real: bool, journal: Path):
    if real:
        trader = SpotTrader(Credentials.from_env(), journal)
        trader.verify_key()
        return trader
    from trading_intelligence.data.binance_public_feed import BinancePublicKlines

    feed = BinancePublicKlines()
    public = SpotTrader(None, journal)  # public endpoints only: exchange rules
    return ShadowTrader(feed.get_current_price, public.rules)


# A running operator rewrites status.json every poll (60 s). A lock whose status is older
# than this was left by a process that died (crash, reboot, power cut).
STALE_LOCK_AFTER = timedelta(minutes=10)


class AlreadyRunning(SystemExit):
    pass


INBOX = "ORDENES.jsonl"  # the owner's commands for a running operator, applied each pass


def operator_running(state_dir: Path, now: Optional[datetime] = None) -> bool:
    """A live operator holds the lock and keeps beating (status.json every pass)."""
    lock = state_dir / "OPERATOR.lock"
    if not lock.exists():
        return False
    status = state_dir / "status.json"
    beat = datetime.fromtimestamp(max(lock.stat().st_mtime, status.stat().st_mtime if status.exists() else 0),
                                  tz=timezone.utc)
    return (now or datetime.now(timezone.utc)) - beat < STALE_LOCK_AFTER


def queue_owner_order(state_dir: Path, order: dict) -> None:
    with open(state_dir / INBOX, "a", encoding="utf-8") as inbox:
        inbox.write(json.dumps(order) + "\n")


def _lock(state_dir: Path, now: Optional[datetime] = None) -> Path:
    lock = state_dir / "OPERATOR.lock"
    now = now or datetime.now(timezone.utc)
    if lock.exists():
        status = state_dir / "status.json"
        beat = datetime.fromtimestamp(max(lock.stat().st_mtime, status.stat().st_mtime if status.exists() else 0),
                                      tz=timezone.utc)
        if now - beat < STALE_LOCK_AFTER:
            raise AlreadyRunning(f"another operator is running ({lock}, last heartbeat {beat.isoformat()})")
        logging.getLogger(__name__).warning("stale lock from a dead operator (last heartbeat %s): replacing it",
                                            beat.isoformat())
        lock.unlink()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise AlreadyRunning(f"another operator is running ({lock})")
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return lock


def check_connection(trader, limits: OwnerLimits, symbol: str, usdt: Decimal) -> list[str]:
    """Connection check with NO money: Binance's test endpoint validates the key, the
    signature and the order's filters without executing anything. Returns lines for the owner."""
    if symbol not in limits.allowed_symbols:
        return [f"{symbol} no está entre las monedas aprobadas; no se envió nada"]
    price, rules = trader.price(symbol), trader.rules(symbol)
    qty = rules.floor_qty(usdt / price)
    if qty <= 0 or qty < rules.min_qty or qty * price < rules.min_notional:
        return [f"{usdt} USDT queda bajo el mínimo de Binance para {symbol} ({rules.min_notional} USDT)"]
    trader.test_order(symbol, "BUY", qty)
    return ["clave verificada: trading permitido y retiros apagados",
            f"orden validada por Binance SIN ejecutarse: compra de {qty} {symbol} (unos {qty * price:.2f} USDT)",
            "conexión lista: no se movió dinero"]


TEST_TRADE_MAX_USDT = Decimal("10")  # a check of the order path, never a position
COIN_FEE = Decimal("0.001")  # Binance Spot taker fee when it is charged in the bought coin
SELL_MARGIN = Decimal("1.05")  # stay clear of the exchange minimum after small price moves


def sellable_buy_qty(rules, price: Decimal, usdt: Decimal) -> Decimal:
    """Smallest lot-aligned quantity worth at least `usdt` whose fee-net, rounded remainder
    can still be sold above the exchange minimum."""
    qty = max(rules.floor_qty(usdt / price), rules.min_qty)
    while rules.floor_qty(qty * (1 - COIN_FEE)) * price < rules.min_notional * SELL_MARGIN:
        qty += rules.step if rules.step > 0 else qty
    return qty


def to_usdt(trader, limits: OwnerLimits, symbol: str, session_holdings: set[str]) -> list[str]:
    """Owner: "transformar" a coin left in Spot (e.g. the test remainder) back to USDT.
    Sells all free units; if they are worth less than Binance's minimum sale, first buys the
    smallest top-up that makes the whole amount sellable. Never touches a coin the running
    session holds (its ledger would break)."""
    if symbol not in limits.allowed_symbols:
        return [f"{symbol} no está entre las monedas aprobadas; no se hizo nada"]
    if symbol in session_holdings:
        return [f"la sesión está operando {symbol}: se vende con sus reglas (o con 'parar --cerrar'); no se hizo nada"]
    asset, rules, price = symbol[:-4], trader.rules(symbol), trader.price(symbol)
    held = trader.free_balance(asset)
    lines = []
    if rules.floor_qty(held) * price < rules.min_notional * SELL_MARGIN:
        top_up = Decimal("0")
        while rules.floor_qty(held + top_up * (1 - COIN_FEE)) * price < rules.min_notional * SELL_MARGIN:
            top_up += rules.step if rules.step > 0 else max(held, rules.min_qty)
        top_up = max(top_up, rules.min_qty)
        while top_up * price < rules.min_notional:  # the top-up buy itself must clear the minimum
            top_up += rules.step if rules.step > 0 else top_up
        if top_up * price > TEST_TRADE_MAX_USDT:
            return [f"completar {asset} hasta el mínimo de venta costaría {top_up * price:.2f} USDT; no se hizo nada"]
        if trader.free_balance("USDT") < top_up * price * Decimal("1.01"):
            return ["USDT libre insuficiente para completar el mínimo de venta; no se hizo nada"]
        buy = trader.market_order(symbol, "BUY", top_up, trader.price)
        lines.append(f"compré {buy.executed_qty} {asset} (pagado {buy.quote_qty:.4f} USDT) para llegar al mínimo de venta")
        held = trader.free_balance(asset)  # the exchange's own number after the buy
    sell_qty = rules.floor_qty(held)
    sell = trader.market_order(symbol, "SELL", sell_qty, trader.price)
    lines.append(f"vendí {sell.executed_qty} {asset} y recibí {sell.quote_qty:.4f} USDT")
    lines.append(f"listo: tu {asset} pasó a USDT (queda un resto mínimo de {held - sell_qty} {asset} por redondeo)")
    return lines


def real_test_trade(trader, limits: OwnerLimits, symbol: str, usdt: Decimal) -> list[str]:
    """Owner, 2026-10-09: "haz la prueba real". The smallest real round trip: a market buy,
    then a market sell of exactly what that buy delivered (never other coins the owner holds).
    Journaled like every order: an unclear answer is looked up, never resent."""
    lines = check_connection(trader, limits, symbol, usdt)
    if not lines[-1].startswith("conexión lista"):
        return lines
    rules, price = trader.rules(symbol), trader.price(symbol)
    # The coin fee and the lot rounding shrink what can be sold back: buy enough that the sale
    # still clears Binance's minimum (2026-10-09: 6 USDT of BTC left 4.97 to sell, refused -1013).
    qty = sellable_buy_qty(rules, price, usdt)
    if qty * price > TEST_TRADE_MAX_USDT:
        return lines + [f"para que la venta supere el mínimo de Binance harían falta {qty * price:.2f} USDT, más "
                        f"que el tope de la prueba ({TEST_TRADE_MAX_USDT}); no se compró nada"]
    if trader.free_balance("USDT") < qty * price * Decimal("1.01"):
        return lines + ["USDT libre insuficiente para la prueba real; no se compró nada"]
    buy = trader.market_order(symbol, "BUY", qty, trader.price)
    lines.append(f"COMPRA real: {buy.executed_qty} {symbol} a {buy.avg_price} "
                 f"(pagado {buy.quote_qty:.4f} USDT, comisión {buy.fee_usdt:.4f} USDT)")
    # Net of the fee taken in the coin, and never more than Spot really holds.
    sell_qty = rules.floor_qty(min(buy.executed_qty, trader.free_balance(symbol[:-4])))
    try:
        sell = trader.market_order(symbol, "SELL", sell_qty, trader.price)
    except LiveError as error:
        return lines + [f"ATENCIÓN: la venta no se completó ({error}). Quedaron {buy.executed_qty} {symbol} "
                        "comprados: véndelos en la app de Binance o avisa a Claude local."]
    lines.append(f"VENTA real: {sell.executed_qty} {symbol} a {sell.avg_price} (recibido {sell.quote_qty:.4f} USDT)")
    lines.append(f"costo de la prueba: {buy.quote_qty - sell.quote_qty:.4f} USDT (comisiones y diferencia de "
                 f"precio); quedó sin vender por redondeo: {buy.executed_qty - sell_qty} {symbol}")
    lines.append("prueba real completa: el sistema compra y vende en tu cuenta")
    return lines


def fee_lines(trader, symbols: list[str]) -> list[str]:
    """Owner: "revisa cuando tengan todos los mercados promos de comisiones". Binance's own
    answer for THIS account (GET /api/v3/account/commission), promotions included."""
    lines = []
    for sym in symbols:
        try:
            data = trader.commission(sym)
        except LiveError as error:
            lines.append(f"{messages.coin(sym)}: no se pudo leer ({error})")
            continue
        std = data.get("standardCommission") or {}
        taker, maker = Decimal(str(std.get("taker", "0"))), Decimal(str(std.get("maker", "0")))
        disc = data.get("discount") or {}
        # Binance reports the multiplier paid with BNB (0.75 = you pay 75%, i.e. 25% off), not the discount.
        paid = Decimal(str(disc.get("discount", "1")))
        bnb = (f"; pagando con {disc.get('discountAsset')} baja un {(1 - paid) * 100:.0f}%"
               if disc.get("enabledForAccount") and disc.get("enabledForSymbol") and paid < 1 else "")
        promo = " ¡PROMOCIÓN: sin comisión!" if taker == 0 else ""
        lines.append(f"{messages.coin(sym)}: comisión {taker * 100:.3f}% (órdenes a mercado), "
                     f"{maker * 100:.3f}% (órdenes límite){bnb}.{promo}")
    return lines


CONVERT_FEE_BUFFER = Decimal("1.003")  # USDTUSD trades near 0.999; 0.1% fee; a little slack
MIN_CONVERSION_USD = Decimal("5")


def convert_for_capital(trader, capital: Decimal) -> str:
    """Owner-started (--convertir-usd): buys only the USDT the session capital still lacks,
    with the fiat USD already in Spot. Never more than the USD there, never below Binance's
    5 USD minimum. Moves nothing out of the account."""
    free_usdt = trader.free_balance("USDT")
    missing = capital - free_usdt
    if missing <= 0:
        return f"conversión: no hace falta (USDT libre {free_usdt})"
    free_usd = trader.free_balance("USD")
    usd = min(free_usd, missing * CONVERT_FEE_BUFFER).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if usd < MIN_CONVERSION_USD:
        return f"conversión: no posible (USD libre {free_usd}, faltan {missing} USDT; mínimo de Binance 5 USD)"
    got = trader.convert_usd_to_usdt(usd)
    return f"conversión: {usd} USD -> {got} USDT (USDT libre ahora {trader.free_balance('USDT')})"


def _launch(d: Path, limits: OwnerLimits, meta: dict, engine_equity: str, max_iterations: Optional[int]) -> None:
    """Runs the operator for the session described by meta.json (new or resumed)."""
    limits = limits.for_session(Decimal(str(meta["loss_limit_pct"])) if meta.get("loss_limit_pct") is not None else None)
    xm = meta.get("broker", "binance") == "xm"
    if xm:
        if meta["real"]:
            raise SystemExit("XM con dinero real todavía no existe (fase 2: cuenta DEMO; fase 3: límites XM del dueño)")
        from dataclasses import replace as _replace

        feed, trader = _xm_feed_and_trader()
        limits = _replace(limits, allowed_symbols=frozenset(meta["symbols"]))  # SHADOW: no money moves
    else:
        trader = _trader(meta["real"], d / "orders.json")
    loop = None
    if meta["profile"] != "copiar":
        from trading_intelligence.data.binance_public_feed import BinancePublicKlines
        from trading_intelligence.execution.paper_loop import build_loop

        # An existing engine state in d/engine is resumed (progress, positions, risk counters).
        loop = build_loop(meta["symbols"], meta["timeframe"], d / "engine",
                          market_data=feed if xm else BinancePublicKlines(),
                          paper_equity=engine_equity, risk_overrides=engine_risk_overrides(limits),
                          router_factory=router_factory(meta["profile"], meta["timeframe"]),
                          continuous_market=not xm)
    end_at = datetime.fromisoformat(meta["end_at"]) if meta.get("end_at") else None
    target = Decimal(meta["profit_target_pct"]) if meta.get("profit_target_pct") is not None else None
    op = Operator(d, trader, limits, profile=meta["profile"], timeframe=meta["timeframe"], symbols=meta["symbols"],
                  loop=loop, real=meta["real"], end_at=end_at, profit_target_pct=target,
                  notify=telegram_notify.make_notify(telegram_notify.console, telegram_notify.from_env()),
                  trailing_pct=Decimal(str(meta.get("trailing_pct", DEFAULT_TRAILING_PCT))),
                  windows=meta.get("windows"))
    op.run(max_iterations=max_iterations, start_report=True)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Real-trading operator (route B).")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    sub = parser.add_subparsers(dest="cmd", required=True)
    start = sub.add_parser("iniciar")
    start.add_argument("--capital", required=True)
    start.add_argument("--perfil", choices=PROFILES, default="tendencia")
    start.add_argument("--real", action="store_true", help="send real orders (without it: SHADOW)")
    start.add_argument("--simbolos", nargs="+")
    start.add_argument("--temporalidad", default=DEFAULT_TIMEFRAME)
    start.add_argument("--max-iteraciones", type=int)
    start.add_argument("--horas", type=float, help="finish after N hours, closing the session's positions")
    start.add_argument("--meta", help="finish when the session gains N%% of its capital, closing its positions")
    start.add_argument("--limite-perdida", help="this session's loss limit in %% (inside the owner's approved range)")
    start.add_argument("--trailing", default=str(DEFAULT_TRAILING_PCT),
                       help="trailing stop in %% below the peak once a position is up 2%%; 0 = off")
    start.add_argument("--ventanas", nargs="+",
                       help=f"trading windows in Ecuador hours, e.g. 07-10 17-19 (5m/20m default: {' '.join(OWNER_WINDOWS)}); "
                            "inside them it decides at every bar, outside them every 20 minutes")
    start.add_argument("--broker", choices=BROKERS, default="binance",
                       help="xm: candles and prices from your MT5 terminal (SHADOW only in phase 1); "
                            "give the MT5 symbol names with --simbolos")
    start.add_argument("--convertir-usd", action="store_true",
                       help="(with --real) first convert fiat USD in Spot to the USDT the capital needs")
    sub.add_parser("estado")
    sub.add_parser("continuar")
    add = sub.add_parser("agregar")
    add.add_argument("--capital", required=True)
    stop = sub.add_parser("parar")
    stop.add_argument("--cerrar", action="store_true")
    rep = sub.add_parser("reporte")
    rep.add_argument("--etapa", choices=("inicio", "medio", "final"), default="medio")
    probe = sub.add_parser("prueba", help="connection check with no money: Binance validates an order "
                                           "without executing it; --real does the smallest real buy+sell")
    probe.add_argument("--simbolo", default="BTCUSDT")
    probe.add_argument("--usdt", default="6")
    probe.add_argument("--real", action="store_true",
                       help=f"real round trip (at most {TEST_TRADE_MAX_USDT} USDT): buy, then sell what was bought")
    adopt = sub.add_parser("adoptar", help="add a coin already in Spot to the running session (it then manages it)")
    adopt.add_argument("--simbolo", required=True)
    convert = sub.add_parser("pasar-a-usdt", help="sell a coin left in Spot back to USDT (tops up to the minimum)")
    convert.add_argument("--simbolo", required=True)
    fees = sub.add_parser("comisiones", help="read-only: this account's commission per symbol, promotions included")
    fees.add_argument("--simbolos", nargs="+")
    resume = sub.add_parser("reanudar", help="resume the open session after a crash or reboot (safe to repeat)")
    resume.add_argument("--max-iteraciones", type=int)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    d: Path = args.dir
    d.mkdir(parents=True, exist_ok=True)
    session_path = d / "session.json"

    if args.cmd == "estado":
        print((d / "status.json").read_text(encoding="utf-8") if (d / "status.json").exists() else "sin sesión")
        return 0
    if args.cmd in ("continuar", "agregar", "adoptar"):
        order: dict = {"cmd": args.cmd}
        if args.cmd == "agregar":
            amount = Decimal(args.capital)
            if not amount.is_finite() or amount <= 0:
                parser.error("--capital must be positive")
            order["capital"] = str(amount)
        if args.cmd == "adoptar":
            order["simbolo"] = args.simbolo
        if operator_running(d):
            # The running operator owns session.json (it saves it every pass): it applies the order.
            queue_owner_order(d, order)
            print("orden registrada: el operador la aplica en su próxima vuelta (menos de 1 minuto) y te avisa")
            return 0
        if args.cmd == "adoptar":
            print("no hay operador en marcha: inicia o reanuda la sesión y repite 'adoptar'")
            return 1
        s = Session.load(session_path)
        s.owner_continue() if args.cmd == "continuar" else s.add_capital(Decimal(args.capital))
        s.save(session_path)
        print(f"ok: {s.status}, capital {s.capital}")
        return 0
    if args.cmd == "parar":
        (d / "STOP").write_text("cerrar" if args.cerrar else "parar", encoding="utf-8")
        print("orden de parada registrada; el operador se detiene en su próxima vuelta")
        return 0

    limits = load_limits()
    if args.cmd == "prueba":
        usdt = Decimal(args.usdt)
        if not usdt.is_finite() or usdt <= 0 or (args.real and usdt > TEST_TRADE_MAX_USDT):
            parser.error(f"--usdt must be positive (at most {TEST_TRADE_MAX_USDT} with --real)")
        probe_dir = d.parent / "prueba"  # its own journal, never a session's
        probe_dir.mkdir(parents=True, exist_ok=True)
        trader = SpotTrader(Credentials.from_env(), probe_dir / "orders.json")
        trader.verify_key()
        run_probe = real_test_trade if args.real else check_connection
        for line in run_probe(trader, limits, args.simbolo, usdt):
            telegram_notify.console(line)  # never crashes on a Windows cp1252 console
        return 0
    if args.cmd in ("pasar-a-usdt", "comisiones"):
        probe_dir = d.parent / "prueba"  # its own journal, never a session's
        probe_dir.mkdir(parents=True, exist_ok=True)
        trader = SpotTrader(Credentials.from_env(), probe_dir / "orders.json")
        trader.verify_key()
        if args.cmd == "comisiones":
            for line in fee_lines(trader, args.simbolos or sorted(limits.allowed_symbols)):
                telegram_notify.console(line)
            return 0
        held = set(Session.load(session_path).holdings) if session_path.exists() else set()
        for line in to_usdt(trader, limits, args.simbolo, held):
            telegram_notify.console(line)
        return 0
    if args.cmd == "reporte":
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        if meta.get("loss_limit_pct") is not None:
            limits = limits.for_session(Decimal(str(meta["loss_limit_pct"])))
        op = Operator(d, _trader(False, d / "orders.json"), limits, profile=meta["profile"],
                      timeframe=meta["timeframe"], symbols=meta["symbols"])
        print(op.write_report(args.etapa))
        return 0

    if args.cmd == "reanudar":
        # Same session, same owner authorization and limits: nothing new is decided here.
        if not session_path.exists() or not (d / "meta.json").exists():
            print("sin sesión que reanudar")
            return 0
        s = Session.load(session_path)
        finished = any(e.get("kind") == "FIN" for e in s.events)  # owner stop, time box or target
        if s.status == STOPPED and (finished or not s.holdings):
            # A finished session is never reopened; coins kept by "parar" (without "cerrar")
            # stay the owner's. Only a loss-limit stop interrupted mid-close is resumed, to close.
            print("la sesión terminó; no hay nada que reanudar")
            return 0
        try:
            lock = _lock(d)
        except AlreadyRunning as running:
            print(f"ya está corriendo: {running}")  # the watchdog calls this every few minutes
            return 0
        try:
            s.note("RESUMED", "operador reanudado tras una interrupción")
            s.save(session_path)
            (d / "STOP").unlink(missing_ok=True)
            _launch(d, limits, json.loads((d / "meta.json").read_text(encoding="utf-8")), str(s.capital),
                    args.max_iteraciones)
        finally:
            lock.unlink(missing_ok=True)
        return 0

    # iniciar
    capital = Decimal(args.capital)
    if capital <= 0:
        parser.error("capital must be positive")
    if args.broker == "xm":
        if args.real:
            parser.error("XM with real money does not exist yet: phase 1 is SHADOW (no orders). Phase 2 is the "
                         "DEMO account, phase 3 needs XM limits approved by the owner")
        if not args.simbolos:
            parser.error("--broker xm needs --simbolos with the exact MT5 names (e.g. GOLD EURUSD)")
        if args.perfil == "copiar":
            parser.error("copiar follows Binance traders; it does not apply to XM")
    if args.real and args.perfil != "copiar" and args.temporalidad not in REAL_TIMEFRAMES:
        parser.error(f"real orders at {args.temporalidad} refused: on real Binance data this configuration lost "
                     f"money after fees (CHECKPOINT section 45). Allowed for real: {sorted(REAL_TIMEFRAMES)}; "
                     "any timeframe is allowed without --real (SHADOW).")
    windows = args.ventanas or (list(OWNER_WINDOWS) if args.temporalidad in WINDOWED_TIMEFRAMES else None)
    if windows:
        try:
            parse_windows(windows)
        except ValueError as error:
            parser.error(str(error))
    if args.horas is not None and args.horas <= 0:
        parser.error("--horas must be positive")
    target = Decimal(args.meta) if args.meta is not None else None
    if target is not None and (not target.is_finite() or target <= 0):
        parser.error("--meta must be a positive percentage")
    session_loss = Decimal(args.limite_perdida) if args.limite_perdida is not None else None
    try:
        limits.for_session(session_loss)
    except LimitsNotApproved as error:
        parser.error(str(error))
    trailing = Decimal(args.trailing)
    if not trailing.is_finite() or not 0 <= trailing < 50:
        parser.error("--trailing must be between 0 and 50")
    if args.convertir_usd and not args.real:
        parser.error("--convertir-usd only makes sense with --real")
    symbols = args.simbolos or sorted(limits.allowed_symbols)
    if args.broker == "binance" and not set(symbols) <= limits.allowed_symbols:
        parser.error(f"symbols outside the approved list: {sorted(set(symbols) - limits.allowed_symbols)}")
    if session_path.exists() and Session.load(session_path).status != STOPPED:
        parser.error("a session is already open here: use estado / continuar / agregar / parar")
    lock = _lock(d)
    try:
        (d / "STOP").unlink(missing_ok=True)
        if (d / "engine").exists():  # a previous session's engine must not leak into this one
            import shutil

            shutil.rmtree(d / "engine")
        now = datetime.now(timezone.utc)
        end_at = now + timedelta(hours=args.horas) if args.horas is not None else None
        meta = {"profile": args.perfil, "timeframe": args.temporalidad, "symbols": symbols, "real": args.real,
                "end_at": end_at.isoformat() if end_at else None, "profit_target_pct": args.meta,
                "loss_limit_pct": str(session_loss) if session_loss is not None else None, "trailing_pct": str(trailing),
                "windows": windows, "broker": args.broker}
        if args.broker == "xm":
            from trading_intelligence.live.xm_mt5 import XmReader

            check = XmReader()  # the MT5 terminal must answer before any session state is written
            check.connect()
            for sym in symbols:
                check.sheet(sym)
            check.close()
        else:
            trader = _trader(args.real, d / "orders.json")  # verify the key before any session state is written
            if args.convertir_usd:
                print(convert_for_capital(trader, capital))
        Session(f"{now:%Y%m%dT%H%M%S}", args.perfil, now.isoformat(timespec="seconds"), capital).save(session_path)
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        _launch(d, limits, meta, str(capital), args.max_iteraciones)
    finally:
        lock.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
