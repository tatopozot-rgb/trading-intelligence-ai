"""
XM through MetaTrader 5: the second broker, same automator. Owner, 2026-10-09: "conectemos
nuestro automatizador a XM ... no reestructurar todo, solo cambiar de broker"; "que el bot lea
automáticamente spread, tamaño mínimo, margen y swap de cada instrumento antes de autorizar
una entrada".

Phase 1 (this module): READ-ONLY.
- Market data from the MT5 terminal: candles feed the same decision engine as Binance.
- Instrument sheet ("ficha"): spread, lot rules, contract size, notional and margin of the
  minimum lot, overnight swap, and whether the market is open.
- Pre-entry check: an entry is authorized only if the sheet passes the owner's caps.
- No order path exists here: the connection only exposes the read functions listed in READS.
  Orders come in phase 2 (DEMO account first); real money needs the owner's phrase and
  XM-specific limits approved by him.

Credentials: the owner logs in to the MT5 terminal himself. initialize() is called WITHOUT
login, password or server, so no credential ever passes through this code.
Windows only: the MetaTrader5 package talks to the terminal on the same PC (Claude local).
"""
from __future__ import annotations

import argparse
import importlib
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pandas as pd

from trading_intelligence.execution.base import AbstractExchangeAdapter

READS = frozenset({"initialize", "shutdown", "last_error", "account_info", "positions_get", "symbol_info",
                   "symbol_info_tick", "symbol_select", "symbols_get", "copy_rates_from_pos", "order_calc_margin"})
ACCOUNT_MODES = {0: "DEMO", 1: "CONCURSO", 2: "REAL"}
ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
# SYMBOL_TRADE_MODE_*: what the broker allows on the instrument right now.
TRADE_MODES = {0: "DESHABILITADO", 1: "SOLO_COMPRA", 2: "SOLO_VENTA", 3: "SOLO_CIERRE", 4: "COMPLETO"}
# MT5 TIMEFRAME_* constants (MetaQuotes documentation); MT5 serves 20m natively.
TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "20m": 20, "30m": 30, "1h": 16385, "4h": 16388, "1d": 16408}
SYMBOL = re.compile(r"^[A-Za-z0-9._#-]{1,32}$")
MAX_TICK_AGE_S = 300  # a quote older than this means the market is closed (weekend, holiday, session break)


class XmError(RuntimeError):
    pass


class OrdersDisabled(XmError):
    pass


def load_mt5() -> object:
    try:
        return importlib.import_module("MetaTrader5")
    except ModuleNotFoundError:
        raise XmError("El paquete MetaTrader5 no está instalado en este Python (pip install MetaTrader5).") from None
    except (ImportError, OSError):
        raise XmError("Windows no permitió cargar el paquete MetaTrader5 (posible Smart App Control). "
                      "No desactives protecciones: avisa al líder.") from None


class _ReadOnly:
    """The only door to the MetaTrader5 package: anything outside READS raises."""
    __slots__ = ("_m",)

    def __init__(self, module: object) -> None:
        self._m = module

    def __getattr__(self, name: str) -> object:
        if name not in READS:
            raise OrdersDisabled(f"función MT5 no permitida en la fase de solo lectura: {name}")
        return getattr(self._m, name)


def _dec(value: object, what: str) -> Decimal:
    if type(value) not in (int, float) or not math.isfinite(value):  # type: ignore[arg-type]
        raise XmError(f"MT5 devolvió un dato inesperado para {what}")
    return Decimal(str(value))


@dataclass(frozen=True)
class Account:
    mode: str  # DEMO / CONCURSO / REAL
    currency: str
    leverage: int  # what the broker allows (e.g. 1000); never what the automator uses
    balance: Decimal
    equity: Decimal
    free_margin: Decimal
    trade_allowed: bool


@dataclass(frozen=True)
class Sheet:
    """Everything the bot reads about one instrument before it may enter (the owner's list)."""
    symbol: str
    trade_mode: str
    bid: Decimal
    ask: Decimal
    spread: Decimal  # ask - bid, in price
    spread_pct: Decimal  # of the mid price: the round-trip cost of a CFD on XM's spread accounts
    volume_min: Decimal  # lots
    volume_step: Decimal
    volume_max: Decimal
    contract_size: Decimal  # units of the underlying per lot
    min_lot_notional: Decimal  # exposure of the minimum lot, in the account currency
    min_lot_margin: Decimal  # margin MT5 asks for the minimum lot (BUY), in the account currency
    swap_long: Decimal  # overnight financing per lot, in the units of swap_mode
    swap_short: Decimal
    swap_mode: int
    stops_level_points: int  # closest a stop may sit to the price
    point: Decimal
    quote_age_s: int

    @property
    def market_open(self) -> bool:
        return self.trade_mode != "DESHABILITADO" and self.quote_age_s <= MAX_TICK_AGE_S


class XmReader:
    def __init__(self, mt5: Optional[object] = None, clock=lambda: datetime.now(timezone.utc)) -> None:
        self._mt5 = _ReadOnly(load_mt5() if mt5 is None else mt5)
        self._clock = clock
        self._connected = False

    def connect(self) -> None:
        """Attaches to the terminal the owner already opened and logged in to."""
        if self._mt5.initialize() is not True:  # type: ignore[operator]
            raise XmError("La terminal MT5 no respondió: ábrela e inicia sesión en tu cuenta XM.")
        self._connected = True
        self.account()  # fails here if no account is logged in

    def close(self) -> None:
        self._connected = False
        self._mt5.shutdown()  # type: ignore[operator]

    def account(self) -> Account:
        if not self._connected:
            raise XmError("sin conexión con la terminal MT5")
        info = self._mt5.account_info()  # type: ignore[operator]
        if info is None:
            raise XmError("La terminal MT5 no tiene una cuenta con sesión iniciada.")
        mode = ACCOUNT_MODES.get(getattr(info, "trade_mode", None))  # type: ignore[arg-type]
        currency, leverage = getattr(info, "currency", None), getattr(info, "leverage", None)
        if mode is None or type(currency) is not str or not re.fullmatch(r"[A-Z]{3,5}", currency) \
                or type(leverage) is not int or leverage <= 0:
            raise XmError("datos de cuenta MT5 con formato inesperado")
        return Account(mode, currency, leverage, _dec(info.balance, "balance"), _dec(info.equity, "equity"),
                       _dec(info.margin_free, "margen libre"), bool(getattr(info, "trade_allowed", False)))

    def _info(self, symbol: str):
        if not SYMBOL.match(symbol):
            raise ValueError(f"símbolo MT5 inválido: {symbol!r}")
        if not self._connected:
            raise XmError("sin conexión con la terminal MT5")
        self._mt5.symbol_select(symbol, True)  # type: ignore[operator]  # adds it to Market Watch
        info = self._mt5.symbol_info(symbol)  # type: ignore[operator]
        if info is None:
            raise XmError(f"{symbol} no está disponible en esta cuenta XM (revisa el nombre exacto en MT5)")
        return info

    def sheet(self, symbol: str) -> Sheet:
        info = self._info(symbol)
        tick = self._mt5.symbol_info_tick(symbol)  # type: ignore[operator]
        if tick is None:
            raise XmError(f"{symbol}: MT5 no tiene cotización")
        bid, ask = _dec(tick.bid, "bid"), _dec(tick.ask, "ask")
        if bid <= 0 or ask < bid:
            raise XmError(f"{symbol}: cotización imposible (bid {bid}, ask {ask})")
        mid = (bid + ask) / 2
        vmin, contract = _dec(info.volume_min, "lote mínimo"), _dec(info.trade_contract_size, "tamaño de contrato")
        tick_value, tick_size = _dec(info.trade_tick_value, "valor del tick"), _dec(info.trade_tick_size, "tick")
        if tick_size <= 0 or vmin <= 0:
            raise XmError(f"{symbol}: reglas de lote o tick imposibles")
        # value of a 1.0 price move for one lot, in the account currency, from the broker's own tick value
        notional = mid * vmin * tick_value / tick_size
        margin = self._mt5.order_calc_margin(ORDER_TYPE_BUY, symbol, float(vmin), float(ask))  # type: ignore[operator]
        age = int(self._clock().timestamp() - int(getattr(tick, "time", 0)))
        return Sheet(symbol, TRADE_MODES.get(getattr(info, "trade_mode", -1), "DESCONOCIDO"), bid, ask, ask - bid,
                     (ask - bid) / mid * 100, vmin, _dec(info.volume_step, "paso de lote"),
                     _dec(info.volume_max, "lote máximo"), contract, notional,
                     _dec(margin, "margen") if margin is not None else Decimal("NaN"),
                     _dec(info.swap_long, "swap compra"), _dec(info.swap_short, "swap venta"),
                     int(getattr(info, "swap_mode", -1)), int(getattr(info, "trade_stops_level", 0)),
                     _dec(info.point, "punto"), max(age, 0))

    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"temporalidad no soportada en MT5: {timeframe}")
        self._info(symbol)
        rates = self._mt5.copy_rates_from_pos(symbol, TIMEFRAMES[timeframe], 0, count)  # type: ignore[operator]
        if rates is None or len(rates) == 0:
            raise XmError(f"{symbol}: MT5 no devolvió velas {timeframe}")
        frame = pd.DataFrame({"open_time": [int(r["time"]) for r in rates],
                              "open": [float(r["open"]) for r in rates], "high": [float(r["high"]) for r in rates],
                              "low": [float(r["low"]) for r in rates], "close": [float(r["close"]) for r in rates],
                              "volume": [float(r["tick_volume"]) for r in rates]})
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="s", utc=True)
        return frame.set_index("open_time")


@dataclass(frozen=True)
class EntryCaps:
    """The automator's own caps, far below what XM allows (1:1000 is the broker's ceiling, not ours).
    Defaults are a proposal for the owner; real money uses the values he approves."""
    max_spread_pct: Decimal = Decimal("0.15")  # a wider spread eats a short-term edge
    max_effective_leverage: Decimal = Decimal("2")  # exposure of one position / equity
    max_margin_pct_of_free: Decimal = Decimal("20")


def check_entry(sheet: Sheet, side: str, account: Account, caps: EntryCaps = EntryCaps()) -> list[str]:
    """Reasons to refuse an entry; empty = authorized. The owner's rule: read spread, minimum
    size, margin and swap of the instrument before authorizing an entry."""
    no: list[str] = []
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if not account.trade_allowed:
        no.append("la cuenta no tiene el trading permitido en MT5")
    if not sheet.market_open:
        no.append(f"mercado cerrado o sin cotización reciente ({sheet.quote_age_s} s)")
    allowed = {"COMPLETO": ("BUY", "SELL"), "SOLO_COMPRA": ("BUY",), "SOLO_VENTA": ("SELL",)}
    if side not in allowed.get(sheet.trade_mode, ()):
        no.append(f"el bróker no permite {side} ahora ({sheet.trade_mode})")
    if sheet.spread_pct > caps.max_spread_pct:
        no.append(f"spread {sheet.spread_pct:.3f}% > máximo {caps.max_spread_pct}%")
    if account.equity <= 0:
        no.append("equity cero")
    elif sheet.min_lot_notional / account.equity > caps.max_effective_leverage:
        no.append(f"el lote mínimo expone {sheet.min_lot_notional:.2f} {account.currency}: apalancamiento efectivo "
                  f"{sheet.min_lot_notional / account.equity:.1f}x > máximo {caps.max_effective_leverage}x "
                  f"con tu equity de {account.equity:.2f}")
    if not sheet.min_lot_margin.is_finite():
        no.append("MT5 no calculó el margen del lote mínimo")
    elif sheet.min_lot_margin > account.free_margin * caps.max_margin_pct_of_free / 100:
        no.append(f"margen del lote mínimo {sheet.min_lot_margin:.2f} > {caps.max_margin_pct_of_free}% "
                  f"del margen libre ({account.free_margin:.2f})")
    # A negative swap is a cost, not a refusal: it is shown in the sheet for overnight holds.
    return no


class XmKlines(AbstractExchangeAdapter):
    """MT5 candles for the decision engine (PaperLoop), so the same strategies read XM markets."""

    def __init__(self, reader: XmReader) -> None:
        self.reader = reader

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        return self.reader.candles(symbol, timeframe, limit)

    def get_current_price(self, symbol: str) -> Decimal:
        s = self.reader.sheet(symbol)
        return (s.bid + s.ask) / 2

    def is_connected(self) -> bool:
        try:
            self.reader.account()
            return True
        except XmError:
            return False

    def get_exchange_name(self) -> str:
        return "xm_mt5"

    def submit_order(self, order):
        raise OrdersDisabled("XmKlines es solo datos de mercado")

    def cancel_order(self, client_order_id):
        raise OrdersDisabled("XmKlines es solo datos de mercado")

    def get_position(self, symbol):
        raise OrdersDisabled("XmKlines es solo datos de mercado")

    def get_account_info(self):
        raise OrdersDisabled("XmKlines es solo datos de mercado")


def sheet_lines(sheet: Sheet, account: Account, caps: EntryCaps = EntryCaps()) -> list[str]:
    buy, sell = check_entry(sheet, "BUY", account, caps), check_entry(sheet, "SELL", account, caps)
    lines = [
        f"{sheet.symbol}: {'abierto' if sheet.market_open else 'CERRADO'} · modo {sheet.trade_mode}",
        f"  precio {sheet.bid} / {sheet.ask} · spread {sheet.spread} ({sheet.spread_pct:.3f}%)",
        f"  lote mínimo {sheet.volume_min} (paso {sheet.volume_step}, contrato {sheet.contract_size}) → expone "
        f"{sheet.min_lot_notional:.2f} {account.currency}, margen {sheet.min_lot_margin:.2f} {account.currency}",
        f"  swap por noche: compra {sheet.swap_long} · venta {sheet.swap_short} (modo {sheet.swap_mode})",
        f"  COMPRA: {'AUTORIZADA' if not buy else 'NO — ' + '; '.join(buy)}",
        f"  VENTA: {'AUTORIZADA' if not sell else 'NO — ' + '; '.join(sell)}",
    ]
    return lines


def main(argv: Optional[list[str]] = None, mt5: Optional[object] = None) -> int:
    parser = argparse.ArgumentParser(description="XM / MT5, solo lectura: cuenta, fichas de instrumentos y velas")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("cuenta")
    f = sub.add_parser("fichas", help="spread, lote mínimo, margen y swap; y si se autorizaría una entrada")
    f.add_argument("simbolos", nargs="+")
    v = sub.add_parser("velas")
    v.add_argument("simbolo")
    v.add_argument("--temporalidad", default="20m", choices=sorted(TIMEFRAMES))
    v.add_argument("--cantidad", type=int, default=5)
    args = parser.parse_args(argv)
    reader = XmReader(mt5)
    try:
        reader.connect()
        acc = reader.account()
        if args.cmd == "cuenta":
            print(f"Cuenta {acc.mode} · {acc.currency} · apalancamiento que permite XM 1:{acc.leverage} "
                  f"(el automatizador usa como máximo {EntryCaps().max_effective_leverage}x)")
            print(f"Balance {acc.balance} · equity {acc.equity} · margen libre {acc.free_margin} · "
                  f"trading {'permitido' if acc.trade_allowed else 'NO permitido'}")
        elif args.cmd == "fichas":
            for sym in args.simbolos:
                try:
                    for line in sheet_lines(reader.sheet(sym), acc):
                        print(line)
                except XmError as error:
                    print(f"{sym}: {error}")
        else:
            print(reader.candles(args.simbolo, args.temporalidad, args.cantidad).to_string())
    except XmError as error:
        print(f"XM: {error}", file=sys.stderr)
        return 1
    finally:
        try:
            reader.close()
        except Exception:  # noqa: BLE001 - closing a terminal that never opened
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
