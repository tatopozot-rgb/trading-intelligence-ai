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

from trading_intelligence.live.telegram_notify import console, from_env, make_notify
from trading_intelligence.live.two_way import (
    DEFAULT_WINDOWS,
    Plan,
    Position,
    Signal,
    TwoWayAuto,
    regime_signal,
)
from trading_intelligence.live.xm_demo import DEFAULT_RISK_PCT, XmDemoTrader
from trading_intelligence.live.xm_mt5 import EntryCaps, XmError

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


def XmAuto(trader: XmDemoTrader, symbols: list[str], state_path: Path, *, caps: EntryCaps = EntryCaps(),
           signal: Signal = regime_signal, **kw) -> TwoWayAuto:
    return TwoWayAuto(XmBroker(trader, caps), symbols, state_path, signal=signal, **kw)


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
