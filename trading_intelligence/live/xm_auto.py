"""
XM automatic operator, both directions. Owner, 2026-10-10, choosing "A": work XM the way the
market works (buy when it rises, sell short when it falls), 24/7, every 2 minutes inside his
windows (07-10 and 17-19 Ecuador) and every 5 minutes outside them.

The decisions are the shared two-way engine (live/two_way.py), the same one Binance Futures uses;
this module is XM's broker adapter and its command line.

DEMO only: every order goes through XmDemoTrader, which re-reads the account and refuses a REAL
one. Real money is phase 3: the owner's phrase written to Claude local plus XM limits he approves.
Before an entry the pre-entry check reads spread, minimum lot, margin and market hours; stop and
target come from the market for that side inside XM's own band, and rest on XM's server. Only
positions carrying this automator's MAGIC are touched: never the owner's manual trades. A closed
market (forex at the weekend) is skipped and noted once.
"""
from __future__ import annotations

import argparse
import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd

from trading_intelligence.live.desk import DeskRules
from trading_intelligence.live.desk import _get as desk_get
from trading_intelligence.live.telegram_notify import console, from_env, make_notify
from trading_intelligence.live.two_way import (
    DEFAULT_WINDOWS,
    Plan,
    Position,
    Signal,
    TwoWayAuto,
    owner_continue,
)
from trading_intelligence.live.xm_demo import XmDemoTrader
from trading_intelligence.live.xm_mt5 import EntryCaps, XmError
from trading_intelligence.strategy.two_way_signals import DEFAULT_VARIANT, VARIANTS, signal_for

DEFAULT_SYMBOLS = ("EURUSD", "GOLD", "BTCUSD")


class XmBroker:
    name, unit = "XM DEMO", "lotes"

    def __init__(self, trader: XmDemoTrader, caps: EntryCaps = EntryCaps()) -> None:
        self.trader, self.caps = trader, caps

    def equity(self) -> tuple[Decimal, str]:
        acc = self.trader._demo_account()
        return acc.equity, acc.currency

    def positions(self) -> dict[str, Position]:
        return {sym: Position(sym, "BUY" if int(getattr(p, "type")) == 0 else "SELL",
                              Decimal(str(getattr(p, "volume", 0))), str(getattr(p, "ticket")),
                              Decimal(str(getattr(p, "price_open", 0))))
                for sym, p in self.trader.positions().items()}

    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        return self.trader.reader.candles(symbol, timeframe, count)

    def plan(self, symbol: str, side: str, risk_pct: Decimal, timeframe: str) -> Plan:
        p = self.trader.plan(symbol, side, risk_pct=risk_pct, caps=self.caps, timeframe=timeframe)
        self._last = p
        return Plan(p.symbol, p.side, p.lots, p.price, p.sl, p.tp, p.risk_money)

    def open(self, plan: Plan) -> str:
        opened = self.trader.open(self._last)
        now = self.trader.positions()
        return str(getattr(now[plan.symbol], "ticket")) if plan.symbol in now else str(opened["order"])

    def close(self, position: Position) -> None:
        self.trader.close(position.symbol, int(position.ticket))

    def move_stop(self, position: Position, stop: Decimal, target: Decimal) -> None:
        self.trader.move_stop(position.symbol, int(position.ticket), stop, target)

    def price(self, symbol: str) -> Decimal:
        sheet = self.trader.reader.sheet(symbol)
        return (sheet.bid + sheet.ask) / 2


def XmAuto(trader: XmDemoTrader, symbols: list[str], state_path: Path, *, caps: EntryCaps = EntryCaps(),
           signal: Optional[Signal] = None, **kw) -> TwoWayAuto:
    return TwoWayAuto(XmBroker(trader, caps), symbols, state_path, signal=signal, **kw)


def main(argv: Optional[list[str]] = None, mt5: Optional[object] = None) -> int:
    parser = argparse.ArgumentParser(description="XM DEMO: operador automático en los dos sentidos (compra y venta)")
    parser.add_argument("accion", nargs="?", choices=("operar", "continuar"), default="operar",
                        help="continuar: el dueño ordena seguir tras el aviso de pérdida")
    parser.add_argument("--simbolos", nargs="+", default=list(DEFAULT_SYMBOLS), help="nombres exactos de MT5")
    parser.add_argument("--temporalidad", default="5m")
    parser.add_argument("--ventanas", nargs="*", default=list(DEFAULT_WINDOWS), help="horas de Ecuador, p. ej. 07-10")
    parser.add_argument("--cada-dentro", type=float, default=0.5, help="minutos entre decisiones dentro de las ventanas (0.5 = sin parar, cada 30 s)")
    parser.add_argument("--cada-fuera", type=float, default=5, help="minutos entre decisiones fuera de las ventanas")
    parser.add_argument("--riesgo-min", default="1", help="%% de la equity en riesgo con la señal más débil")
    parser.add_argument("--riesgo-max", default="15", help="%% de la equity en riesgo con la señal más fuerte")
    parser.add_argument("--max-posiciones", type=int, default=3)
    parser.add_argument("--limite-perdida", default="45", help="%% de la sesión (banda del dueño 20-50)")
    parser.add_argument("--aviso", default="2", help="se pregunta al dueño esta cantidad antes del límite")
    parser.add_argument("--meta", default="58", help="%% de ganancia que cierra todo y termina la sesión")
    parser.add_argument("--senal", choices=VARIANTS, default=DEFAULT_VARIANT, help="lógica de entrada")
    parser.add_argument("--dir", type=Path, default=Path("live_runs/xm_auto"))
    parser.add_argument("--diario", type=Path, help="carpeta del diario de la mesa (p. ej. la del vault de Obsidian)")
    parser.add_argument("--sin-mesa", action="store_true", help="sin Scout, Escéptico ni sentimiento (no recomendado)")
    parser.add_argument("--una-vez", action="store_true", help="una sola decisión y salir")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.accion == "continuar":
        owner_continue(args.dir)
        print("orden registrada: el operador la aplica en su próxima decisión")
        return 0
    if not Decimal("20") <= Decimal(args.limite_perdida) <= Decimal("50"):
        print("XM DEMO: el límite de pérdida debe estar entre 20 y 50% (banda del dueño)")
        return 1
    trader = XmDemoTrader(args.dir / "orders.json", mt5)
    try:
        acc = trader.connect()
        auto = XmAuto(trader, args.simbolos, args.dir / "state.json", timeframe=args.temporalidad,
                      risk_min_pct=Decimal(args.riesgo_min), risk_max_pct=Decimal(args.riesgo_max),
                      max_open=args.max_posiciones,
                      loss_limit_pct=Decimal(args.limite_perdida), warn_before=Decimal(args.aviso),
                      profit_target_pct=Decimal(args.meta), signal=signal_for(args.senal), windows=args.ventanas,
                      inside_every_min=args.cada_dentro, outside_every_min=args.cada_fuera,
                      notify=make_notify(console, from_env()),
                      desk_rules=None if args.sin_mesa else DeskRules.load(), journal_dir=args.diario or args.dir / "mesa",
                      news_get=None if args.sin_mesa else desk_get)
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
