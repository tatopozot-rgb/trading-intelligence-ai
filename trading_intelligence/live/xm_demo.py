"""
XM phase 2: orders on a DEMO account only. Owner, 2026-10-09: "Señal → BUY o SELL → XM/MT5 →
posición con margen → SL / TP / gestión automática → P&L"; Trading Intelligence decides what,
the risk engine decides how much, MT5 only executes.

Hard rules, each enforced in code:
- DEMO only: the account mode is re-read before every order; a REAL or CONTEST account refuses.
  Real money needs the owner's phrase and XM limits he approves (phase 3, not built).
- Every order carries a stop loss AND a take profit, on the right side of the price and outside
  the broker's minimum stop distance.
- The pre-entry check (xm_mt5.check_entry: spread, minimum lot, margin, market open) runs first.
- Size comes from risk: lots = (equity x risk%) / (loss per lot at the stop), rounded DOWN to the
  lot step, then capped so exposure <= max effective leverage x equity. Below the minimum lot:
  no trade (never rounded up into more risk).
- MT5's own order_check validates margin and parameters before order_send.
- Journal before sending; an unclear answer is reconciled from the account's positions by the
  order comment, never blindly resent.
"""
from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Optional

from trading_intelligence.live.xm_mt5 import (
    READS,
    Account,
    EntryCaps,
    Sheet,
    XmError,
    XmReader,
    _dec,
    check_entry,
    load_mt5,
)

DEMO_CALLS = READS | {"order_check", "order_send"}
TRADE_ACTION_DEAL = 1
ORDER_TYPE = {"BUY": 0, "SELL": 1}
ORDER_TIME_GTC = 0
FILLING_FOK, FILLING_IOC, FILLING_RETURN = 0, 1, 2
RETCODE_DONE, RETCODE_PLACED = 10009, 10008
RETCODE_CHECK_OK = 0
MAGIC = 26101009  # marks this automator's orders in MT5
DEFAULT_RISK_PCT = Decimal("0.5")  # of equity lost if the stop is hit
DEVIATION_POINTS = 20


class NotDemo(XmError):
    pass


class _DemoGate:
    __slots__ = ("_m",)

    def __init__(self, module: object) -> None:
        self._m = module

    def __getattr__(self, name: str) -> object:
        if name not in DEMO_CALLS:
            raise XmError(f"función MT5 no permitida: {name}")
        return getattr(self._m, name)


@dataclass(frozen=True)
class Plan:
    symbol: str
    side: str
    lots: Decimal
    price: Decimal
    sl: Decimal
    tp: Decimal
    risk_money: Decimal  # account currency lost if SL is hit (before spread/slippage)
    exposure: Decimal  # account currency


def size_lots(sheet: Sheet, account: Account, stop_distance: Decimal, risk_pct: Decimal,
              caps: EntryCaps = EntryCaps(), value_per_unit_lot: Optional[Decimal] = None) -> Decimal:
    """Lots for a risk of risk_pct of equity at stop_distance (price units); 0 when even the minimum
    lot would risk more, or expose more than the leverage cap."""
    if stop_distance <= 0 or account.equity <= 0:
        return Decimal("0")
    mid = (sheet.bid + sheet.ask) / 2
    per_lot_unit = value_per_unit_lot if value_per_unit_lot is not None else sheet.min_lot_notional / (
        mid * sheet.volume_min)
    loss_per_lot = stop_distance * per_lot_unit
    lots = account.equity * risk_pct / 100 / loss_per_lot
    max_by_leverage = caps.max_effective_leverage * account.equity / (mid * per_lot_unit)
    lots = min(lots, max_by_leverage, sheet.volume_max)
    step = sheet.volume_step
    lots = (lots / step).to_integral_value(rounding=ROUND_DOWN) * step
    return lots if lots >= sheet.volume_min else Decimal("0")


class XmDemoTrader:
    def __init__(self, journal: Path, mt5: Optional[object] = None, reader: Optional[XmReader] = None) -> None:
        module = load_mt5() if mt5 is None else mt5
        self._mt5 = _DemoGate(module)
        self.reader = reader or XmReader(module)
        self.journal = Path(journal)

    def connect(self) -> Account:
        self.reader.connect()
        return self._demo_account()

    def _demo_account(self) -> Account:
        acc = self.reader.account()
        if acc.mode != "DEMO":
            raise NotDemo(f"la cuenta activa en MT5 es {acc.mode}: las órdenes de la fase 2 son solo en DEMO")
        return acc

    def plan(self, symbol: str, side: str, sl_pct: Decimal, tp_pct: Decimal,
             risk_pct: Decimal = DEFAULT_RISK_PCT, caps: EntryCaps = EntryCaps()) -> Plan:
        acc = self._demo_account()
        sheet = self.reader.sheet(symbol)
        refused = check_entry(sheet, side, acc, caps)
        if refused:
            raise XmError("entrada no autorizada: " + "; ".join(refused))
        if not (0 < sl_pct < 50 and 0 < tp_pct < 100):
            raise ValueError("sl_pct and tp_pct must be positive percentages")
        price = sheet.ask if side == "BUY" else sheet.bid
        sign = 1 if side == "BUY" else -1
        digits_q = sheet.point
        sl = (price * (1 - sign * sl_pct / 100)).quantize(digits_q)
        tp = (price * (1 + sign * tp_pct / 100)).quantize(digits_q)
        min_gap = sheet.stops_level_points * sheet.point
        if abs(price - sl) <= min_gap or abs(tp - price) <= min_gap:
            raise XmError(f"SL/TP demasiado cerca del precio: el bróker exige más de {min_gap}")
        lots = size_lots(sheet, acc, abs(price - sl), risk_pct, caps)
        if lots <= 0:
            raise XmError(f"con equity {acc.equity} y riesgo {risk_pct}% ni el lote mínimo ({sheet.volume_min}) cabe "
                          f"con el stop a {sl_pct}%: no se opera")
        mid = (sheet.bid + sheet.ask) / 2
        per_lot_unit = sheet.min_lot_notional / (mid * sheet.volume_min)
        return Plan(symbol, side, lots, price, sl, tp, (abs(price - sl) * per_lot_unit * lots).quantize(Decimal("0.01")),
                    (mid * per_lot_unit * lots).quantize(Decimal("0.01")))

    def _filling(self, symbol: str) -> int:
        mode = int(getattr(self._mt5.symbol_info(symbol), "filling_mode", 0))  # type: ignore[operator]
        return FILLING_IOC if mode & 2 else FILLING_FOK if mode & 1 else FILLING_RETURN

    def _record(self, entry: dict) -> None:
        rows = json.loads(self.journal.read_text(encoding="utf-8")) if self.journal.exists() else []
        rows.append(entry)
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        self.journal.write_text(json.dumps(rows, indent=1), encoding="utf-8")

    def _send(self, request: dict) -> dict:
        self._demo_account()  # the logged-in account can change between calls
        check = self._mt5.order_check(request)  # type: ignore[operator]
        if check is None or int(getattr(check, "retcode", -1)) != RETCODE_CHECK_OK:
            raise XmError(f"MT5 rechazó la orden al validarla: {getattr(check, 'comment', 'sin respuesta')}")
        self._record({"state": "SENDING", "request": {k: v for k, v in request.items()}})
        result = self._mt5.order_send(request)  # type: ignore[operator]
        if result is None:
            found = [p for p in (self._mt5.positions_get(symbol=request["symbol"]) or ())  # type: ignore[operator]
                     if getattr(p, "comment", "") == request["comment"]]
            self._record({"state": "UNCLEAR", "comment": request["comment"], "found": len(found)})
            raise XmError("respuesta de MT5 dudosa: revisé las posiciones y no reenvío la orden")
        code = int(getattr(result, "retcode", -1))
        out = {"state": "DONE" if code in (RETCODE_DONE, RETCODE_PLACED) else "REJECTED", "retcode": code,
               "order": getattr(result, "order", None), "deal": getattr(result, "deal", None),
               "volume": getattr(result, "volume", None), "price": getattr(result, "price", None),
               "comment": request["comment"]}
        self._record(out)
        if out["state"] != "DONE":
            raise XmError(f"MT5 rechazó la orden (código {code}: {getattr(result, 'comment', '')})")
        return out

    def open(self, plan: Plan) -> dict:
        client = "TI-" + uuid.uuid4().hex[:12]
        return self._send({"action": TRADE_ACTION_DEAL, "symbol": plan.symbol, "volume": float(plan.lots),
                           "type": ORDER_TYPE[plan.side], "price": float(plan.price), "sl": float(plan.sl),
                           "tp": float(plan.tp), "deviation": DEVIATION_POINTS, "magic": MAGIC, "comment": client,
                           "type_time": ORDER_TIME_GTC, "type_filling": self._filling(plan.symbol)})

    def close(self, symbol: str, ticket: int) -> dict:
        pos = [p for p in (self._mt5.positions_get(symbol=symbol) or ())  # type: ignore[operator]
               if int(getattr(p, "ticket", -1)) == ticket]
        if not pos:
            raise XmError(f"no encuentro la posición {ticket} en {symbol}")
        p = pos[0]
        side = "SELL" if int(p.type) == 0 else "BUY"
        sheet = self.reader.sheet(symbol)
        price = sheet.bid if side == "SELL" else sheet.ask
        return self._send({"action": TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(_dec(p.volume, "volumen")),
                           "type": ORDER_TYPE[side], "position": ticket, "price": float(price),
                           "deviation": DEVIATION_POINTS, "magic": MAGIC, "comment": "TI-close-" + str(ticket)[-8:],
                           "type_time": ORDER_TIME_GTC, "type_filling": self._filling(symbol)})


def main(argv: Optional[list[str]] = None, mt5: Optional[object] = None) -> int:
    parser = argparse.ArgumentParser(description="XM fase 2: prueba en cuenta DEMO (abre con SL y TP y cierra)")
    parser.add_argument("--simbolo", required=True)
    parser.add_argument("--lado", choices=("BUY", "SELL"), default="BUY")
    parser.add_argument("--sl", default="0.5", help="stop loss en %% del precio")
    parser.add_argument("--tp", default="1.0", help="take profit en %% del precio")
    parser.add_argument("--riesgo", default=str(DEFAULT_RISK_PCT), help="%% de la equity que se pierde si toca el SL")
    parser.add_argument("--mantener", action="store_true", help="dejar la posición abierta (con su SL y TP)")
    parser.add_argument("--diario", default="live_runs/xm_demo/orders.json")
    args = parser.parse_args(argv)
    trader = XmDemoTrader(Path(args.diario), mt5)
    try:
        acc = trader.connect()
        plan = trader.plan(args.simbolo, args.lado, Decimal(args.sl), Decimal(args.tp), Decimal(args.riesgo))
        print(f"Cuenta DEMO · equity {acc.equity} {acc.currency}")
        print(f"Plan: {plan.side} {plan.lots} lotes de {plan.symbol} a {plan.price} · SL {plan.sl} · TP {plan.tp} · "
              f"riesgo {plan.risk_money} · exposición {plan.exposure} {acc.currency}")
        opened = trader.open(plan)
        print(f"Abierta: orden {opened['order']} a {opened['price']}")
        if not args.mantener:
            ticket = int(opened["order"])
            closed = trader.close(plan.symbol, ticket)
            print(f"Cerrada: orden {closed['order']} a {closed['price']}")
    except (XmError, ValueError) as error:
        print(f"XM DEMO: {error}")
        return 1
    finally:
        try:
            trader.reader.close()
        except Exception:  # noqa: BLE001 - closing a terminal that never opened
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
