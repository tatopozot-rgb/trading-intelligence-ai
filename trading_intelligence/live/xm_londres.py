"""
London breakout on GOLD, XM DEMO only, "en observación". Leader, 2026-10-15: the rule exactly as preregistered in
docs/research/oro/PREREGISTRO.md (strategy 1), no re-tuning, 1% of equity at risk, stop and target on every order.
It passed 2025-26 (+26.6%, net/drawdown 3.72) and failed 2024-25 (-7.7%), so it is measured forward on virtual money.

Leader, 2026-10-16: the same rule on BTCUSD, also in observation (docs/research/cripto_xm/: with XM's costs it wins
both years but its deflated Sharpe does not pass). Its own agent and MAGIC ("Londres BTCUSD"; gold keeps "Londres"),
weekends included as in the test, and 1% of a nominal 1,000 USD at risk (--capital-nominal), not of the equity of the
DEMO account the other agents share. The 5x size cap is of that same nominal capital, as in the test.

    python -m trading_intelligence.live.xm_londres            # one pass (Task Scheduler, every 5 minutes)
    python -m trading_intelligence.live.xm_londres resumen    # where it stands
    python -m trading_intelligence.live.xm_londres --simbolo BTCUSD --dir <xm-wt>/live_runs/xm_londres_btc --capital-nominal 1000 \
        --terminal <second MT5>/terminal64.exe   # its own DEMO account, in a second MT5 installation

Each pass, in UTC:
- Asian range = high and low of the 1h candles 00:00-06:00 of today (all 7 needed).
- 07:00-15:59: the first 5m candle since 07:00 that touches the range high (long) or low (short) decides the side;
  one entry per day, at market, stop at the other side of the range, target 1x the range beyond the broken level. A candle
  that touched both sides is the backtest's stop: no entry that day. Price already past the stop or the target: no
  entry that day.
- From 20:00 an open position is closed. Weekends: nothing on gold; crypto trades them (it quotes 7 days).

MT5 candle and tick times are XM server time (GMT+2/+3), not UTC: the offset is read from the last tick each pass.
Every order goes through XmDemoTrader: DEMO re-checked before each order, pre-entry check, MT5's order_check, own
MAGIC (only this agent's positions are touched), journal before sending. Never a real account.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from trading_intelligence.live.telegram_notify import console, from_env, make_notify
from trading_intelligence.live.xm_auto import agent_magic
from trading_intelligence.live.xm_demo import XmDemoTrader
from trading_intelligence.live.xm_mt5 import EntryCaps, XmError

AGENT, SYMBOL = "Londres", "GOLD"
RISK_PCT = Decimal("1")
ASIA_FROM, ENTRY_FROM, ENTRY_TO, EXIT_AT = 0, 7, 16, 20  # UTC hours; Asia is 00:00-06:59
MAX_LEVERAGE = Decimal("5")  # the backtest's cap: size at most 5x the capital
CAPS = EntryCaps(max_effective_leverage=MAX_LEVERAGE)
DEFAULT_DIR = Path("live_runs/xm_londres")
TAG = "🧪 XM DEMO · Londres oro (en observación)"
CRYPTO_PREFIXES = ("BTC", "ETH")


def is_crypto(symbol: str) -> bool:
    return symbol.upper().startswith(CRYPTO_PREFIXES)


def asset_name(symbol: str) -> str:
    """What the owner reads: "Oro" for gold, "BTC" for BTCUSD."""
    up = symbol.upper()
    if up.startswith(("GOLD", "XAU")):
        return "Oro"
    for prefix in CRYPTO_PREFIXES:
        if up.startswith(prefix):
            return prefix
    return symbol


def agent_name(symbol: str) -> str:
    """Gold keeps the agent (and MAGIC) it has traded with since 2026-10-15; any other symbol gets its own."""
    return AGENT if symbol == SYMBOL else f"{AGENT} {symbol}"


def tag_for(symbol: str) -> str:
    name = asset_name(symbol)
    return f"🧪 XM DEMO · Londres {name.lower() if name == 'Oro' else name} (en observación)"

Candles = Callable[[str, str, int], pd.DataFrame]


@dataclass(frozen=True)
class Setup:
    side: int  # 1 long, -1 short, 0 none yet
    high: float
    low: float
    note: str = ""


def server_offset_hours(tick_time: int, now: datetime) -> int:
    """XM server time minus UTC, in whole hours (GMT+2 in winter, GMT+3 in summer)."""
    hours = round((tick_time - now.timestamp()) / 3600)
    if not 0 <= hours <= 3:
        raise XmError(f"desfase de hora del servidor XM inesperado: {hours} h")
    return hours


def to_utc(frame: pd.DataFrame, offset_h: int) -> pd.DataFrame:
    out = frame.copy()
    out.index = pd.DatetimeIndex(out.index) - pd.Timedelta(hours=offset_h)
    return out


def asian_range(hourly: pd.DataFrame, day: pd.Timestamp) -> Optional[tuple[float, float]]:
    asia = hourly[(hourly.index >= day + pd.Timedelta(hours=ASIA_FROM)) & (hourly.index < day + pd.Timedelta(hours=ENTRY_FROM))]
    if len(asia) != ENTRY_FROM - ASIA_FROM or sorted(asia.index.hour) != list(range(ASIA_FROM, ENTRY_FROM)):
        return None
    hi, lo = float(asia["high"].max()), float(asia["low"].min())
    return (hi, lo) if hi > lo else None


def first_touch(five: pd.DataFrame, day: pd.Timestamp, now: datetime, hi: float, lo: float) -> Setup:
    """The side of the first 5m candle since 07:00 (closed or forming) that touched the range."""
    window = five[(five.index >= day + pd.Timedelta(hours=ENTRY_FROM)) & (five.index <= pd.Timestamp(now))]
    for t, row in window.iterrows():
        up, down = row["high"] >= hi, row["low"] <= lo
        if up and down:
            return Setup(0, hi, lo, f"la vela de {t:%H:%M} UTC tocó los dos lados: no entro hoy")
        if up or down:
            return Setup(1 if up else -1, hi, lo)
    return Setup(0, hi, lo)


class LondonBot:
    def __init__(self, trader: XmDemoTrader, state_path: Path, notify: Callable[[str], None],
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 candles: Optional[Candles] = None, offset: Optional[Callable[[], int]] = None,
                 symbol: str = SYMBOL, risk_pct: Decimal = RISK_PCT,
                 alarm: Optional[Callable[[str], None]] = None, nominal: Optional[Decimal] = None,
                 weekends: Optional[bool] = None) -> None:
        # notify: the day's trades (the console; the owner reads them in the 22:00 summary, live/resumen_diario.py);
        # alarm: what goes to Telegram at once (an order XM refused)
        self.trader, self.state_path, self.notify, self.clock = trader, Path(state_path), notify, clock
        self.alarm = alarm or notify
        self.symbol, self.risk_pct = symbol, risk_pct
        # nominal: risk and size cap are of this capital, not of the shared DEMO account's equity
        if nominal is not None and nominal <= 0:
            raise ValueError("el capital nominal tiene que ser positivo")
        self.nominal = nominal
        self.weekends = is_crypto(symbol) if weekends is None else weekends
        self.tag = tag_for(symbol)
        self.candles = candles or trader.reader.candles
        self.offset = offset or self._tick_offset
        self.state: dict[str, Any] = (json.loads(self.state_path.read_text(encoding="utf-8"))
                                      if self.state_path.exists() else {"day": "", "done": False, "trades": []})
        self.state["simbolo"] = symbol  # live/resumen_diario.py names the asset from it
        if nominal is not None:
            self.state["capital_nominal"] = str(nominal)

    def _tick_offset(self) -> int:
        tick = self.trader.reader._mt5.symbol_info_tick(self.symbol)  # type: ignore[operator]
        if tick is None:
            raise XmError(f"{self.symbol}: MT5 no tiene cotización")
        return server_offset_hours(int(getattr(tick, "time")), self.clock())

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=1), encoding="utf-8")

    def _done(self, note: str) -> str:
        self.state["done"] = True
        self.state["note"] = note
        return note

    def step(self) -> str:
        now = self.clock()
        day = pd.Timestamp(now).floor("D")
        if self.state.get("day") != str(day.date()):
            self.state.update({"day": str(day.date()), "done": False, "note": ""})
        pos = self.trader.positions().get(self.symbol)
        try:
            if pos is None and self.state.get("open"):  # its stop or its target closed it on XM's server
                self._closed(now, "servidor", None)
            if pos is not None:
                if now.hour >= EXIT_AT:
                    self.trader.close(self.symbol, int(getattr(pos, "ticket")))
                    result = ""
                    if self.state.get("open"):
                        result = f" ({self._closed(now, 'cierre 20:00', self._mid()):+.2f} aprox.)"
                    else:  # opened before the results were recorded
                        self.state["trades"].append({"t": now.isoformat(), "accion": "cierre 20:00",
                                                     "ticket": str(getattr(pos, "ticket"))})
                    msg = f"{self.tag}: 20:00 UTC, cierro la posición {getattr(pos, 'ticket')}{result}."
                    self.notify(msg)
                    return msg
                return "posición abierta: stop y meta descansan en XM"
            if (now.weekday() >= 5 and not self.weekends) or self.state["done"] or not ENTRY_FROM <= now.hour < ENTRY_TO:
                return "fuera de horario o ya operé hoy"
            offset = self.offset()
            hourly = to_utc(self.candles(self.symbol, "1h", 48), offset)
            rng = asian_range(hourly, day)
            if rng is None:
                return self._done("sin rango asiático completo hoy: no opero")
            hi, lo = rng
            setup = first_touch(to_utc(self.candles(self.symbol, "5m", 200), offset), day, now, hi, lo)
            if setup.note:
                self.notify(f"{self.tag}: {setup.note}.")
                return self._done(setup.note)
            if setup.side == 0:
                return f"esperando ruptura del rango {lo:.2f}-{hi:.2f}"
            return self._enter(setup, now)
        finally:
            self._save()

    def _enter(self, s: Setup, now: datetime) -> str:
        sheet = self.trader.reader.sheet(self.symbol)
        price = float(sheet.ask if s.side > 0 else sheet.bid)
        r = s.high - s.low
        stop = s.low if s.side > 0 else s.high
        target = (s.high if s.side > 0 else s.low) + s.side * r  # 1x the range from the breakout level
        if s.side * (price - stop) <= 0 or s.side * (target - price) <= 0:
            return self._done(f"el precio {price:.2f} ya pasó el stop o la meta: no entro hoy")
        side = "BUY" if s.side > 0 else "SELL"
        sl_pct = Decimal(str(abs(price - stop) / price * 100)).quantize(Decimal("0.0001"))
        tp_pct = Decimal(str(abs(target - price) / price * 100)).quantize(Decimal("0.0001"))
        try:
            risk_pct, caps = self._sizing()
            plan = self.trader.plan(self.symbol, side, sl_pct, tp_pct, risk_pct=risk_pct, caps=caps)
            opened = self.trader.open(plan)
        except XmError as error:
            note = f"no entro: {error}"
            self.alarm(f"⚠️ {self.tag}: {note}")
            return self._done(note)
        self.state["trades"].append({"t": now.isoformat(), "accion": "entrada", "lado": side, "lotes": str(plan.lots),
                                     "precio": str(plan.price), "sl": str(plan.sl), "tp": str(plan.tp),
                                     "rango": [s.low, s.high], "orden": str(opened.get("order"))})
        try:
            self.state["moneda"] = str(self.trader._demo_account().currency)  # for the 22:00 summary
        except XmError:
            pass
        self.state["open"] = {"lado": side, "precio": str(plan.price), "sl": str(plan.sl), "tp": str(plan.tp),
                              "riesgo": str(plan.risk_money)}
        msg = (f"{self.tag}: rompió el rango asiático {s.low:.2f}-{s.high:.2f} → {'COMPRO' if s.side > 0 else 'VENDO'} "
               f"{plan.lots} lotes a {plan.price} · stop {plan.sl} · meta {plan.tp} · riesgo {plan.risk_money}.")
        self.notify(msg)
        self._done("operé hoy")
        return msg

    def _sizing(self) -> tuple[Decimal, EntryCaps]:
        """Risk % and caps as XmDemoTrader takes them (of the account's equity). With a nominal capital they are
        rescaled so the money at risk is risk_pct of the nominal and the size at most 5x the nominal."""
        if self.nominal is None:
            return self.risk_pct, CAPS
        equity = self.trader._demo_account().equity
        if equity <= 0:
            raise XmError("equity cero en la cuenta DEMO")
        scale = self.nominal / equity
        return self.risk_pct * scale, replace(CAPS, max_effective_leverage=MAX_LEVERAGE * scale)

    def _mid(self) -> Optional[Decimal]:
        try:
            sheet = self.trader.reader.sheet(self.symbol)
            return (Decimal(str(sheet.bid)) + Decimal(str(sheet.ask))) / 2
        except (XmError, ValueError, ArithmeticError):
            return None

    def _closed(self, now: datetime, how: str, exit_price: Optional[Decimal]) -> Decimal:
        """Records the result of the open trade, estimated from its exit (the account is shared with the other
        XM agents, so its equity does not tell this bot's result): at the stop or the target, whichever is nearer
        the price now, when XM's server closed it."""
        o = self.state.pop("open")
        entry, sl, tp, risk = (Decimal(o[k]) for k in ("precio", "sl", "tp", "riesgo"))
        sign = 1 if o["lado"] == "BUY" else -1
        price = self._mid()
        if exit_price is None:
            near = price if price is not None else entry
            exit_price = tp if abs(tp - near) < abs(sl - near) else sl
        if how == "servidor":
            how = "meta" if exit_price == tp else "stop"
        per_point = risk / abs(entry - sl) if entry != sl else Decimal("0")
        pnl = (sign * (exit_price - entry) * per_point).quantize(Decimal("0.01"))
        self.state["trades"].append({"t": now.isoformat(), "accion": "cierre", "motivo": how, "lado": o["lado"],
                                     "salida": str(exit_price), "pnl": str(pnl), "estimado": True})
        return pnl

    def summary(self) -> str:
        acc = self.trader._demo_account()
        entries = [t for t in self.state.get("trades", []) if t.get("accion") == "entrada"]
        pos = self.trader.positions().get(self.symbol)
        now = "con posición abierta" if pos is not None else "sin posición"
        base = f" Riesgo {self.risk_pct}% de {self.nominal} nominales." if self.nominal is not None else ""
        return (f"{self.tag}: {len(entries)} entradas desde el inicio, {now}.{base} "
                f"Equity de la cuenta DEMO {acc.equity} {acc.currency}.")


def main(argv: Optional[list[str]] = None, mt5: Optional[object] = None) -> int:
    parser = argparse.ArgumentParser(description="XM DEMO: ruptura de Londres en oro o BTC (en observación, sin dinero real)")
    parser.add_argument("cmd", nargs="?", choices=("revisar", "resumen"), default="revisar")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--simbolo", default=SYMBOL, help="nombre exacto en MT5 (GOLD o BTCUSD)")
    parser.add_argument("--capital-nominal", type=Decimal, default=None,
                        help="arriesga 1%% de este capital (USD) y no de la equity de la cuenta DEMO compartida")
    parser.add_argument("--terminal", default=None,
                        help="terminal64.exe de otra instalación de MT5 (otra cuenta DEMO); sin ella, la de siempre")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    trader = XmDemoTrader(args.dir / "orders.json", mt5, magic=agent_magic(agent_name(args.simbolo)),
                           terminal=args.terminal)
    telegram = make_notify(console, from_env())
    notify = telegram if args.cmd == "resumen" else console  # its trades go in the 22:00 summary
    try:
        trader.connect()
        bot = LondonBot(trader, args.dir / "state.json", notify, symbol=args.simbolo, alarm=telegram,
                        nominal=args.capital_nominal)
        if args.cmd == "resumen":
            notify(bot.summary())
        else:
            print(bot.step())
    except (XmError, ValueError) as error:
        print(f"XM DEMO Londres: {error}")
        return 1
    finally:
        try:
            trader.reader.close()
        except Exception:  # noqa: BLE001 - closing a terminal that never opened
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
