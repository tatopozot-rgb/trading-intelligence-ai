"""
XM automatic operator, both directions. Owner, 2026-10-10, choosing "A": work XM the way the
market works (buy when it rises, sell short when it falls), 24/7, every 2 minutes inside his
windows (07-10 and 17-19 Ecuador) and every 5 minutes outside them.

DEMO only: every order goes through XmDemoTrader, which re-reads the account and refuses a REAL
one. Real money is phase 3: the owner's phrase written to Claude local plus XM limits he approves.

At each decision, for each instrument:
- Signal from the regime on the decision bars: trend or breakout up -> BUY; down -> SELL; range or
  no edge -> no new entry (an open position keeps its own stop and target).
- An open position of ours (by MAGIC) facing the opposite signal is closed; the next decision may
  open the other way.
- No position, a signal, room under max_open and the day not halted -> plan (exit_plan read from
  the market for that side, XM's stop band), the pre-entry check (spread, minimum lot, margin,
  market open), then the order with its stop loss and take profit resting on XM's server, so the
  position stays protected with the PC off.
- Daily loss guard: when equity falls daily_loss_pct below the UTC day's starting equity, our
  positions are closed and no new entry is made until the next UTC day (19:00 Ecuador).
- Risk per trade is fixed (risk_pct of equity at the stop): never raised after a loss.
- A closed market (forex at the weekend) is skipped and noted once.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from trading_intelligence.live.operator import in_windows, parse_windows
from trading_intelligence.live.telegram_notify import console, from_env, make_notify
from trading_intelligence.live.xm_demo import DEFAULT_RISK_PCT, XmDemoTrader
from trading_intelligence.live.xm_mt5 import EntryCaps, XmError

logger = logging.getLogger(__name__)

Signal = Callable[[str, pd.DataFrame], Optional[str]]  # (symbol, decision bars) -> BUY / SELL / None
DEFAULT_SYMBOLS = ("EURUSD", "GOLD", "BTCUSD")
DEFAULT_WINDOWS = ("07-10", "17-19")
MAX_EVENTS = 500


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


def side_of(position: object) -> str:
    return "BUY" if int(getattr(position, "type")) == 0 else "SELL"


@dataclass
class State:
    day: str = ""
    day_start_equity: str = "0"
    halted: bool = False
    known: dict[str, int] = field(default_factory=dict)  # symbol -> ticket of our open position
    events: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls()
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(d.get("day", ""), d.get("day_start_equity", "0"), bool(d.get("halted", False)),
                   {k: int(v) for k, v in d.get("known", {}).items()}, list(d.get("events", [])))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.__dict__, indent=1), encoding="utf-8")
        tmp.replace(path)


class XmAuto:
    def __init__(self, trader: XmDemoTrader, symbols: list[str], state_path: Path, *, timeframe: str = "5m",
                 risk_pct: Decimal = DEFAULT_RISK_PCT, max_open: int = 3, daily_loss_pct: Decimal = Decimal("5"),
                 windows: Optional[list[str]] = None, inside_every_min: int = 2, outside_every_min: int = 5,
                 signal: Signal = regime_signal, notify: Callable[[str], None] = console,
                 caps: EntryCaps = EntryCaps(),
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        if max_open < 1 or not (0 < risk_pct <= 2) or not (0 < daily_loss_pct < 100):
            raise ValueError("max_open >= 1, risk_pct in (0, 2], daily_loss_pct in (0, 100)")
        self.trader, self.symbols, self.state_path = trader, list(symbols), Path(state_path)
        self.timeframe, self.risk_pct, self.max_open, self.daily_loss_pct = timeframe, risk_pct, max_open, daily_loss_pct
        self.windows = parse_windows(list(windows if windows is not None else DEFAULT_WINDOWS))
        self.inside_every_min, self.outside_every_min = inside_every_min, outside_every_min
        self.signal, self.notify, self.caps, self.clock = signal, notify, caps, clock
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
        s = self.state
        acc = self.trader._demo_account()
        today = self.clock().date().isoformat()
        if s.day != today:
            s.day, s.day_start_equity, s.halted = today, str(acc.equity), False
            self._noted.clear()
        ours = self.trader.positions()

        for sym, ticket in list(s.known.items()):
            if sym not in ours or int(getattr(ours[sym], "ticket", -1)) != ticket:
                del s.known[sym]
                self._event("CLOSED_BY_SERVER", sym)
                self.notify(f"⚪ XM DEMO: se cerró {sym} en el servidor de XM (llegó a su stop o a su meta).")

        floor = Decimal(s.day_start_equity) * (1 - self.daily_loss_pct / 100)
        if not s.halted and acc.equity <= floor:
            s.halted = True
            for sym, pos in ours.items():
                self.trader.close(sym, int(getattr(pos, "ticket")))
                s.known.pop(sym, None)
            ours = self.trader.positions()
            self._event("DAY_HALTED", f"equity {acc.equity} <= {floor:.2f}")
            self.notify(f"🛑 XM DEMO: la cuenta perdió {self.daily_loss_pct}% hoy (equity {acc.equity} {acc.currency}). "
                        f"Cerré las posiciones y no abro nada más hasta mañana (19:00 de Ecuador).")

        for sym in self.symbols:
            try:
                self._decide(sym, ours, acc.currency)
            except (XmError, ValueError) as error:
                self._note_once(f"{sym}:{str(error)[:40]}", f"{sym}: {error}")
        self.state.save(self.state_path)

    def _decide(self, sym: str, ours: dict[str, object], currency: str) -> None:
        s = self.state
        signal = self.signal(sym, self.trader.reader.candles(sym, self.timeframe, 500))
        pos = ours.get(sym)
        if pos is not None:
            if signal is not None and signal != side_of(pos):
                self.trader.close(sym, int(getattr(pos, "ticket")))
                ours.pop(sym)
                s.known.pop(sym, None)
                self._event("CLOSE", f"{sym} {side_of(pos)}: señal {signal}")
                self.notify(f"🔁 XM DEMO: cerré la {'compra' if side_of(pos) == 'BUY' else 'venta en corto'} de {sym}: "
                            f"el mercado cambió de dirección.")
            return
        if signal is None or s.halted or len(ours) >= self.max_open:
            return
        plan = self.trader.plan(sym, signal, risk_pct=self.risk_pct, caps=self.caps, timeframe=self.timeframe)
        opened = self.trader.open(plan)
        now_ours = self.trader.positions()
        ticket = int(getattr(now_ours[sym], "ticket")) if sym in now_ours else int(opened["order"])
        ours[sym] = now_ours.get(sym, object())
        s.known[sym] = ticket
        self._event("OPEN", f"{plan.side} {plan.lots} {sym} @ {plan.price} SL {plan.sl} TP {plan.tp}")
        verb = "Compré" if plan.side == "BUY" else "Vendí en corto"
        why = "el mercado está subiendo" if plan.side == "BUY" else "el mercado está bajando"
        self.notify(f"{'🟢' if plan.side == 'BUY' else '🔴'} XM DEMO: {verb} {plan.lots} lotes de {sym} a {plan.price} "
                    f"porque {why}. Stop en {plan.sl}, meta en {plan.tp} (puestos en el servidor de XM). "
                    f"Si toca el stop se pierden unos {plan.risk_money} {currency}.")

    def run(self, max_iterations: Optional[int] = None, sleep: Callable[[float], None] = time.sleep) -> None:
        n = 0
        while max_iterations is None or n < max_iterations:
            n += 1
            if self.decision_due():
                try:
                    self.step()
                except XmError as error:  # terminal closed, account changed: retry next slot
                    logger.warning("XM: %s", error)
                    self._note_once(f"step:{str(error)[:40]}", str(error))
                    self.state.save(self.state_path)
            sleep(20)


def main(argv: Optional[list[str]] = None, mt5: Optional[object] = None) -> int:
    parser = argparse.ArgumentParser(description="XM DEMO: operador automático en los dos sentidos (compra y venta)")
    parser.add_argument("--simbolos", nargs="+", default=list(DEFAULT_SYMBOLS), help="nombres exactos de MT5")
    parser.add_argument("--temporalidad", default="5m")
    parser.add_argument("--ventanas", nargs="*", default=list(DEFAULT_WINDOWS), help="horas de Ecuador, p. ej. 07-10")
    parser.add_argument("--cada-dentro", type=int, default=2, help="minutos entre decisiones dentro de las ventanas")
    parser.add_argument("--cada-fuera", type=int, default=5, help="minutos entre decisiones fuera de las ventanas")
    parser.add_argument("--riesgo", default=str(DEFAULT_RISK_PCT), help="%% de la equity que se pierde si toca el stop")
    parser.add_argument("--max-posiciones", type=int, default=3)
    parser.add_argument("--perdida-diaria", default="5", help="%% de pérdida del día que detiene las entradas")
    parser.add_argument("--dir", type=Path, default=Path("live_runs/xm_auto"))
    parser.add_argument("--una-vez", action="store_true", help="una sola decisión y salir")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    trader = XmDemoTrader(args.dir / "orders.json", mt5)
    try:
        acc = trader.connect()
        auto = XmAuto(trader, args.simbolos, args.dir / "state.json", timeframe=args.temporalidad,
                      risk_pct=Decimal(args.riesgo), max_open=args.max_posiciones,
                      daily_loss_pct=Decimal(args.perdida_diaria), windows=args.ventanas,
                      inside_every_min=args.cada_dentro, outside_every_min=args.cada_fuera,
                      notify=make_notify(console, from_env()))
        print(f"XM DEMO · equity {acc.equity} {acc.currency} · {', '.join(args.simbolos)} · "
              f"cada {args.cada_dentro} min en {' '.join(args.ventanas)} (Ecuador), cada {args.cada_fuera} fuera")
        if args.una_vez:
            auto.step()
        else:
            auto.run()
    except (XmError, ValueError) as error:
        print(f"XM DEMO: {error}")
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        try:
            trader.reader.close()
        except Exception:  # noqa: BLE001 - closing a terminal that never opened
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
