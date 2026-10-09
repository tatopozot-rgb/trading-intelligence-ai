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

from trading_intelligence.live import mirror
from trading_intelligence.live.binance_live import (
    Credentials,
    Fill,
    LiveError,
    SpotTrader,
    StopState,
    SymbolRules,
    Unreconciled,
)
from trading_intelligence.live.limits import OwnerLimits, load_limits
from trading_intelligence.live.session import STOPPED, Session

logger = logging.getLogger(__name__)
DEFAULT_DIR = Path("live_runs/current")
PROFILES = ("tendencia", "tendencia_rango", "copiar")
# Real-data walk-forward (CHECKPOINT section 45): at 1h both profiles LOSE after fees
# (-0.80% / -0.67% per trade, p < 0.01). 4h is positive but not proven (p ~ 0.09).
# Real orders are allowed only at a timeframe that has not been shown to lose.
REAL_TIMEFRAMES = frozenset({"4h"})
DEFAULT_TIMEFRAME = "4h"
MID_REPORT_EVERY = timedelta(hours=12)

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
                 end_at: Optional[datetime] = None, profit_target_pct: Optional[Decimal] = None) -> None:
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
        self.session = Session.load(self.dir / "session.json")
        self.last_mid_report = self.clock()

    # --- one pass ------------------------------------------------------------------

    def step(self, decide: bool) -> list[mirror.Action]:
        s = self.session
        actions: list[mirror.Action] = []
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
        message = s.evaluate(prices, self.limits)
        if message:
            self.notify(message)
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
            self.notify(f"ERROR de ejecución: {error}")
        for a in actions:
            if a.kind == "SKIP":
                s.note("SKIP", f"{a.symbol}: {a.reason}")
        if self.clock() - self.last_mid_report >= MID_REPORT_EVERY:
            self.write_report("medio")
            self.last_mid_report = self.clock()
        self._save()
        return actions

    def only_dust_left(self) -> bool:
        """Nothing sellable remains (holdings under the exchange minimum cannot be sold)."""
        for sym, h in self.session.holdings.items():
            rules = self.trader.rules(sym)
            if rules.floor_qty(h.qty) * self.trader.price(sym) >= rules.min_notional:
                return False
        return True

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
                self.notify(f"ERROR de ejecución al cerrar: {error}")
        self.session.status = STOPPED  # a finished session never buys again; a new one can start
        self.session.note("FIN", reason)
        self.notify(reason)
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
            decide = bar != last_bar
            self.step(decide)
            last_bar = bar
            if start_report and n == 0:
                self.notify(str(self.write_report("inicio")))
            if self.session.status == STOPPED and self.only_dust_left():
                self.write_report("final")
                return
            n += 1
            if max_iterations is not None and n >= max_iterations:
                self.write_report("final")  # a bounded run (rehearsal) still leaves its summary
                return
            sleep(poll_seconds)


# --- CLI ------------------------------------------------------------------------------


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
    trader = _trader(meta["real"], d / "orders.json")
    loop = None
    if meta["profile"] != "copiar":
        from trading_intelligence.data.binance_public_feed import BinancePublicKlines
        from trading_intelligence.execution.paper_loop import build_loop

        # An existing engine state in d/engine is resumed (progress, positions, risk counters).
        loop = build_loop(meta["symbols"], meta["timeframe"], d / "engine", market_data=BinancePublicKlines(),
                          paper_equity=engine_equity, risk_overrides=engine_risk_overrides(limits),
                          router_factory=router_factory(meta["profile"], meta["timeframe"]))
    end_at = datetime.fromisoformat(meta["end_at"]) if meta.get("end_at") else None
    target = Decimal(meta["profit_target_pct"]) if meta.get("profit_target_pct") is not None else None
    op = Operator(d, trader, limits, profile=meta["profile"], timeframe=meta["timeframe"], symbols=meta["symbols"],
                  loop=loop, real=meta["real"], end_at=end_at, profit_target_pct=target)
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
    if args.cmd in ("continuar", "agregar"):
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
    if args.cmd == "reporte":
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
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
    if args.real and args.perfil != "copiar" and args.temporalidad not in REAL_TIMEFRAMES:
        parser.error(f"real orders at {args.temporalidad} refused: on real Binance data this configuration lost "
                     f"money after fees (CHECKPOINT section 45). Allowed for real: {sorted(REAL_TIMEFRAMES)}; "
                     "any timeframe is allowed without --real (SHADOW).")
    if args.horas is not None and args.horas <= 0:
        parser.error("--horas must be positive")
    target = Decimal(args.meta) if args.meta is not None else None
    if target is not None and (not target.is_finite() or target <= 0):
        parser.error("--meta must be a positive percentage")
    if args.convertir_usd and not args.real:
        parser.error("--convertir-usd only makes sense with --real")
    symbols = args.simbolos or sorted(limits.allowed_symbols)
    if not set(symbols) <= limits.allowed_symbols:
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
                "end_at": end_at.isoformat() if end_at else None, "profit_target_pct": args.meta}
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
