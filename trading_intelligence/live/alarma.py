"""
Market alarm: when the market crashes or explodes, the owner is told again and again until he answers,
and a trade is opened ONLY if he accepts it. Owner, 2026-10-13: "si el mercado va a explotar como cuando
fueron las torres gemelas, me notifiques como loco hasta yo atender y aceptar la operación".

    python -m trading_intelligence.live.alarma                   # practice account (fictitious money)
    python -m trading_intelligence.live.alarma --modo real       # real money: only with the owner's phrase

What counts as a shock (public 5-minute Binance prices, checked every minute):
- BTC or ETH moving at least 4% in 15 minutes, 7% in 1 hour or 12% in 24 hours, up or down;
- or at least 70% of the watched coins moving 6% or more in 1 hour in the same direction.
Nobody can see a 9/11 coming; this sees it within a minute or two of the move starting.

What happens:
1. A Telegram alarm with what moved, a trade proposal (with the move, 1x, the desk's stop, target 3 times
   the risk, the smallest risk the owner approved) and a 4-digit code.
2. The same alarm again every minute until the owner answers from HIS chat:
   "ACEPTO <code>" opens the trade at the price of that moment; "NO <code>" drops it;
   "VISTO <code>" stops the repeats and the proposal stays open until it expires (1 hour).
   The alarm is also the owner's Telegram inbox for orders on open positions ("CIERRA TRX", "META TRX 5"):
   it hands them to every running bot through live/ordenes.py.
   Optional: with TI_PUSHOVER_TOKEN and TI_PUSHOVER_USER set, a Pushover emergency alert also rings the
   phone every 30 seconds until he acknowledges it (Pushover repeats it on its side).
3. No answer in an hour: the alarm expires and nothing is traded.

Safety: messages from any other chat are ignored; the code changes with every alarm; the trade goes through
the futures broker with its stop on the exchange and the limits in config/futures_limits.json; no
withdrawals, no transfers; real mode needs the futures key and the owner's phrase to Claude local to start.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol, Sequence

import pandas as pd

from trading_intelligence.live import desk as D
from trading_intelligence.live import ordenes as O
from trading_intelligence.live import telegram_notify

logger = logging.getLogger(__name__)

LEADERS = ("BTCUSDT", "ETHUSDT")
# (label, 5-minute bars back, threshold %)
WINDOWS = (("15 minutos", 3, 4.0), ("1 hora", 12, 7.0), ("24 horas", 288, 12.0))
BREADTH_PCT, BREADTH_SHARE, BREADTH_BARS = 6.0, 0.7, 12
REPEAT = timedelta(minutes=1)
EXPIRE = timedelta(hours=1)
COOLDOWN = timedelta(hours=2)  # after an alarm in one direction, the next one in that direction waits
LOOP_SECONDS = 60
DEFAULT_STATE = Path("live_runs/alarma.json")
PUSHOVER_HOST = "api.pushover.net"


class Feed(Protocol):
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame: ...


class Replies(Protocol):
    def send(self, text: str) -> bool: ...
    def replies(self, offset: int = 0) -> list[tuple[int, str]]: ...


@dataclass(frozen=True)
class Shock:
    direction: str  # "up" or "down"
    symbol: str  # the coin to trade: the leader that moved the most
    text: str


def _pct(closes: list[float], back: int) -> Optional[float]:
    if len(closes) <= back or closes[-1 - back] <= 0:
        return None
    return (closes[-1] / closes[-1 - back] - 1) * 100


def detect(bars: Mapping[str, pd.DataFrame]) -> Optional[Shock]:
    """The biggest shock right now, or None. ``bars`` are 5-minute klines per symbol (latest last)."""
    best: Optional[tuple[float, str, str, float]] = None  # (size over threshold, symbol, window, pct)
    for sym in LEADERS:
        if sym not in bars:
            continue
        closes = bars[sym]["close"].astype(float).tolist()
        for label, back, threshold in WINDOWS:
            pct = _pct(closes, back)
            if pct is not None and abs(pct) >= threshold and (best is None or abs(pct) / threshold > best[0]):
                best = (abs(pct) / threshold, sym, label, pct)
    hour = {s: _pct(b["close"].astype(float).tolist(), BREADTH_BARS) for s, b in bars.items()}
    moved = [p for p in hour.values() if p is not None]
    up = sum(1 for p in moved if p >= BREADTH_PCT)
    down = sum(1 for p in moved if p <= -BREADTH_PCT)
    if best is not None:
        _, sym, label, pct = best
        direction = "up" if pct > 0 else "down"
        word = "SUBE" if pct > 0 else "CAE"
        return Shock(direction, sym, f"{sym} {word} {pct:+.1f}% en {label}")
    if moved and max(up, down) >= BREADTH_SHARE * len(moved):
        direction = "up" if up >= down else "down"
        sym = max(LEADERS, key=lambda s: abs(hour.get(s) or 0.0))
        word = "suben" if direction == "up" else "caen"
        return Shock(direction, sym, f"{max(up, down)} de {len(moved)} monedas {word} {BREADTH_PCT:.0f}% o más en 1 hora")
    return None


def pushover(text: str, env: Mapping[str, str], post: Optional[Callable[[str, bytes], None]] = None) -> bool:
    """Emergency Pushover alert (priority 2: it rings every 30 s until acknowledged, for up to 1 hour)."""
    token, user = env.get("TI_PUSHOVER_TOKEN", "").strip(), env.get("TI_PUSHOVER_USER", "").strip()
    if not token or not user:
        return False
    body = urllib.parse.urlencode({"token": token, "user": user, "title": "ALARMA DE MERCADO", "message": text[:1000],
                                   "priority": 2, "retry": 30, "expire": 3600}).encode()
    try:
        if post is not None:
            post(f"https://{PUSHOVER_HOST}/1/messages.json", body)
        else:
            req = urllib.request.Request(f"https://{PUSHOVER_HOST}/1/messages.json", data=body, method="POST")
            urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as error:  # noqa: BLE001 - Telegram still repeats the alarm
        logger.warning("Pushover unreachable (%s)", type(error).__name__)
        return False


class Alarm:
    """One alarm at a time, kept in a JSON file so a restart neither loses it nor repeats an old one."""

    def __init__(self, feed: Feed, symbols: Sequence[str], chat: Replies, broker: object, state_path: Path,
                 risk_pct: Decimal, console: Callable[[str], None] = telegram_notify.console,
                 env: Optional[Mapping[str, str]] = None, orders_path: Optional[Path] = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.feed, self.symbols, self.chat, self.broker = feed, list(symbols), chat, broker
        self.state_path, self.risk_pct, self.console, self.clock = Path(state_path), risk_pct, console, clock
        self.env = os.environ if env is None else env
        self.orders_path = orders_path  # the owner's CIERRA / META orders go here for every bot (live/ordenes.py)
        self.state = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return {"offset": 0, "incident": None, "last": {}}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
        tmp.replace(self.state_path)

    def _say(self, text: str) -> None:
        self.chat.send(text)
        self.console(text)

    def _message(self, inc: dict, repeat: int) -> str:
        side = "COMPRA (largo)" if inc["direction"] == "up" else "VENTA EN CORTO"
        head = "🚨🚨🚨 ALARMA DE MERCADO" + (f" (aviso {repeat})" if repeat > 1 else "")
        return (f"{head}\n{inc['text']}.\n\nPropuesta en {self.broker_name()}: {side} de {inc['symbol']}, 1x, con stop en "
                f"Binance y meta a 3 veces el riesgo; riesgo {self.risk_pct}% de la cuenta.\n\n"
                f"Responde:\nACEPTO {inc['code']} → abro la operación al precio de ese momento\n"
                f"NO {inc['code']} → no se opera\nVISTO {inc['code']} → dejo de insistir (la propuesta sigue 1 hora)")

    def broker_name(self) -> str:
        return str(getattr(self.broker, "name", "la cuenta"))

    def step(self) -> Optional[str]:
        """One pass: answers first, then repeats, then a new shock. Returns what happened (for logs/tests)."""
        now = self.clock()
        texts = self._inbox(now)  # read every pass: old messages never accept a later alarm
        inc = self.state.get("incident")
        if inc:
            return self._follow(inc, now, texts)
        bars = {}
        for sym in self.symbols:
            try:
                bars[sym] = self.feed.get_ohlcv(sym, "5m", 300)
            except Exception as error:  # noqa: BLE001 - one coin missing never blinds the alarm
                logger.warning("%s: no prices (%s)", sym, type(error).__name__)
        shock = detect(bars)
        if shock is None:
            return None
        last = self.state.get("last", {}).get(shock.direction)
        if last and now - datetime.fromisoformat(last) < COOLDOWN:
            return None
        inc = {"code": f"{1000 + secrets.randbelow(9000)}", "direction": shock.direction, "symbol": shock.symbol,
               "text": shock.text, "started": now.isoformat(), "last_sent": now.isoformat(), "sent": 1, "seen": False}
        self.state["incident"] = inc
        self.state.setdefault("last", {})[shock.direction] = now.isoformat()
        self._save()
        self._say(self._message(inc, 1))
        pushover(f"{shock.text}. Responde en Telegram: ACEPTO {inc['code']} / NO {inc['code']}", self.env)
        return "alarma"

    def _inbox(self, now: datetime) -> list[str]:
        """The owner's new messages. Orders on open positions (CIERRA / META) are passed to every bot; the rest
        are returned for the alarm itself."""
        texts = []
        for update_id, text in self.chat.replies(int(self.state.get("offset", 0))):
            self.state["offset"] = max(int(self.state.get("offset", 0)), update_id + 1)
            order = O.parse(text)
            if order is None:
                texts.append(text)
                continue
            kind, symbol, value, is_price = order
            if self.orders_path is not None:
                O.enqueue(self.orders_path, kind, symbol, value, is_price, now)
            what = (f"cerrar {symbol} ya" if kind == "CIERRA" else
                    f"cerrar {symbol} {'al precio ' + str(value) if is_price else f'al ganar {value}%'}")
            self._say(f"📨 Orden recibida: {what}. El bot que tiene esa posición la aplica en menos de un minuto y te "
                      f"confirma cuando la cuenta lo muestre. Si ningún bot la tiene abierta, no cambia nada.")
            own = self.broker.positions().get(symbol) if kind == "CIERRA" else None  # type: ignore[attr-defined]
            if own is not None:
                self.broker.close(own)  # type: ignore[attr-defined]
                self._say(f"✋ Alarma · {self.broker_name()}: cerré {symbol} como ordenaste.")
        self._save()
        return texts

    def _follow(self, inc: dict, now: datetime, texts: list[str]) -> str:
        for text in texts:
            words = text.strip().upper().split()
            if len(words) != 2 or words[1] != inc["code"]:
                continue
            if words[0] == "ACEPTO":
                return self._close(self._execute(inc))
            if words[0] == "NO":
                return self._close(f"✅ Alarma {inc['code']}: no se opera, como pediste.")
            if words[0] == "VISTO":
                inc["seen"] = True
                self._save()
                self._say(f"👀 Alarma {inc['code']}: dejo de insistir. Para operar, responde ACEPTO {inc['code']} "
                          f"antes de {(datetime.fromisoformat(inc['started']) + EXPIRE):%H:%M} UTC.")
                return "visto"
        if now - datetime.fromisoformat(inc["started"]) >= EXPIRE:
            return self._close(f"⌛ Alarma {inc['code']}: pasó una hora sin respuesta. No se operó nada.")
        if not inc.get("seen") and now - datetime.fromisoformat(inc["last_sent"]) >= REPEAT:
            inc["sent"] = int(inc.get("sent", 1)) + 1
            inc["last_sent"] = now.isoformat()
            self._save()
            self._say(self._message(inc, inc["sent"]))
            return "repetida"
        self._save()
        return "esperando"

    def _execute(self, inc: dict) -> str:
        side = "BUY" if inc["direction"] == "up" else "SELL"
        try:
            if inc["symbol"] in self.broker.positions():  # type: ignore[attr-defined]
                return f"⚠️ Alarma {inc['code']}: ya hay una posición en {inc['symbol']}; no abro otra."
            plan = self.broker.plan(inc["symbol"], side, self.risk_pct, "5m")  # type: ignore[attr-defined]
            rules = D.DeskRules.load()  # the desk's target: 3 times the risk
            plan = replace(plan, tp=D.shape_target(plan.price, plan.tp, side, rules, False, plan.sl))
            if plan.qty <= 0:
                return f"⚠️ Alarma {inc['code']}: el tamaño queda bajo el mínimo de Binance; no se operó."
            self.broker.open(plan)  # type: ignore[attr-defined]
        except Exception as error:  # noqa: BLE001 - the owner must hear about any failure
            return f"❌ Alarma {inc['code']}: no se pudo abrir ({error}). No hay operación."
        word = "COMPRA" if side == "BUY" else "VENTA EN CORTO"
        return (f"✅ Alarma {inc['code']}: {word} de {plan.symbol} abierta en {self.broker_name()}. Cantidad {plan.qty}, "
                f"precio {plan.price}, stop {plan.sl}, meta {plan.tp}; si salta el stop se pierden {plan.risk_money}.")

    def _close(self, text: str) -> str:
        self.state["incident"] = None
        self._save()
        self._say(text)
        return text


def main(argv: Optional[Sequence[str]] = None, env: Optional[Mapping[str, str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Alarma de mercado: avisa sin parar y solo opera si el dueño acepta")
    parser.add_argument("--modo", choices=("shadow", "real"), default="shadow")
    parser.add_argument("--capital", default="30", help="SHADOW: capital simulado en USDT")
    parser.add_argument("--dir", type=Path, default=Path("live_runs/alarma"))
    parser.add_argument("--una-vez", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    env = os.environ if env is None else env
    from trading_intelligence.data.binance_public_feed import BinancePublicKlines
    from trading_intelligence.live import binance_futures as F

    chat = telegram_notify.from_env(env)
    if chat is None:
        print("La alarma necesita Telegram (TI_TELEGRAM_TOKEN y TI_TELEGRAM_CHAT_ID): sin eso no puede avisar.")
        return 1
    limits = F.load_futures_limits()
    d = args.dir / args.modo
    if args.modo == "real":
        market = F.FuturesMarket(F.FuturesCredentials.from_env(env), d / "orders.json")
        broker: object = F.FuturesBroker(market, limits)
        market.verify()
    else:
        broker = F.PaperFuturesBroker(F.FuturesMarket(None), Decimal(args.capital), d / "paper.json",
                                      leverage=limits.max_leverage, max_position_pct=limits.max_position_pct)
    alarm = Alarm(BinancePublicKlines(), list(limits.symbols), chat, broker, d / "alarma.json", limits.risk_min_pct,
                  env=env, orders_path=O.DEFAULT_ORDERS)
    print(f"Alarma de mercado activa en {getattr(broker, 'name', args.modo)}: reviso cada {LOOP_SECONDS} s. "
          f"Órdenes por Telegram: CIERRA <moneda>, META <moneda> <% de ganancia>.", flush=True)
    while True:
        try:
            alarm.step()
        except Exception as error:  # noqa: BLE001 - the alarm must keep watching
            logger.warning("alarm pass failed (%s)", type(error).__name__)
        if args.una_vez:
            return 0
        time.sleep(LOOP_SECONDS if not alarm.state.get("incident") else 15)


if __name__ == "__main__":
    raise SystemExit(main())
