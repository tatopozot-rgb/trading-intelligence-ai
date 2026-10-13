"""Market alarm: detects a crash or explosion, repeats until the owner answers, trades only on ACEPTO."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd

from trading_intelligence.live import alarma as A
from trading_intelligence.live import telegram_notify as T
from trading_intelligence.live.two_way import Plan

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def _bars(last_hour_pct: float = 0.0, n: int = 300) -> pd.DataFrame:
    closes = np.full(n, 100.0)
    closes[-12:] = np.linspace(100.0, 100.0 * (1 + last_hour_pct / 100), 12)
    closes[-13] = 100.0
    return pd.DataFrame({"close": closes})


class Feed:
    def __init__(self, moves: dict[str, float]) -> None:
        self.moves = moves

    def get_ohlcv(self, symbol, timeframe, limit=500):
        return _bars(self.moves.get(symbol, 0.0))


class Chat:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.inbox: list[tuple[int, str]] = []

    def send(self, text):
        self.sent.append(text)
        return True

    def replies(self, offset=0):
        return [(u, t) for u, t in self.inbox if u >= offset]


class Broker:
    name = "🧪 práctica"

    def __init__(self) -> None:
        self.opened: list[Plan] = []

    def positions(self):
        return {}

    def plan(self, symbol, side, risk_pct, timeframe):
        sl = Decimal("97") if side == "BUY" else Decimal("103")
        return Plan(symbol, side, Decimal("1"), Decimal("100"), sl, Decimal("101"), Decimal("3"))

    def open(self, plan):
        self.opened.append(plan)
        return plan.symbol


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self):
        return self.now


def _alarm(tmp_path, moves, env=None):
    chat, broker, clock = Chat(), Broker(), Clock()
    alarm = A.Alarm(Feed(moves), ["BTCUSDT", "ETHUSDT", "SOLUSDT"], chat, broker, tmp_path / "a.json",
                    Decimal("1"), console=lambda m: None, env=env or {}, clock=clock)
    return alarm, chat, broker, clock


def test_detect_a_crash_an_explosion_and_calm():
    crash = A.detect({"BTCUSDT": _bars(-8), "ETHUSDT": _bars(-5)})
    assert crash is not None and crash.direction == "down" and crash.symbol == "BTCUSDT" and "1 hora" in crash.text
    boom = A.detect({"BTCUSDT": _bars(2), "ETHUSDT": _bars(9)})
    assert boom is not None and boom.direction == "up" and boom.symbol == "ETHUSDT"
    assert A.detect({"BTCUSDT": _bars(-2), "ETHUSDT": _bars(1)}) is None
    breadth = A.detect({"BTCUSDT": _bars(-6.5), "ETHUSDT": _bars(-6.2), "SOLUSDT": _bars(-6.1), "XRPUSDT": _bars(1)})
    assert breadth is not None and breadth.direction == "down" and "monedas" in breadth.text


def test_the_alarm_repeats_until_the_owner_accepts_and_then_trades(tmp_path):
    alarm, chat, broker, clock = _alarm(tmp_path, {"BTCUSDT": -8})
    assert alarm.step() == "alarma"
    code = alarm.state["incident"]["code"]
    assert "ALARMA DE MERCADO" in chat.sent[0] and f"ACEPTO {code}" in chat.sent[0] and "VENTA EN CORTO" in chat.sent[0]
    clock.now += timedelta(seconds=30)
    assert alarm.step() == "esperando"  # not yet a minute
    clock.now += timedelta(seconds=31)
    assert alarm.step() == "repetida" and "(aviso 2)" in chat.sent[-1]
    chat.inbox.append((10, "ACEPTO 0000" if code != "0000" else "ACEPTO 1111"))  # a wrong code does nothing
    clock.now += timedelta(seconds=61)
    assert alarm.step() == "repetida" and not broker.opened
    chat.inbox.append((11, f"acepto {code}"))
    result = alarm.step()
    assert broker.opened and broker.opened[0].side == "SELL" and "abierta" in result
    assert broker.opened[0].tp == Decimal("91")  # 3 times the 3-point risk below 100
    assert alarm.state["incident"] is None
    assert json.loads((tmp_path / "a.json").read_text())["incident"] is None


def test_no_and_visto_and_expiry(tmp_path):
    alarm, chat, broker, clock = _alarm(tmp_path, {"ETHUSDT": 10})
    alarm.step()
    code = alarm.state["incident"]["code"]
    chat.inbox.append((1, f"VISTO {code}"))
    assert alarm.step() == "visto"
    clock.now += timedelta(minutes=5)
    assert alarm.step() == "esperando"  # seen: no more repeats
    clock.now += timedelta(hours=1)
    assert "sin respuesta" in alarm.step() and not broker.opened
    clock.now += timedelta(hours=3)  # after the cooldown a new shock rings again
    assert alarm.step() == "alarma"
    code = alarm.state["incident"]["code"]
    chat.inbox.append((2, f"NO {code}"))
    assert "no se opera" in alarm.step() and not broker.opened


def test_old_messages_never_accept_a_new_alarm(tmp_path):
    alarm, chat, broker, clock = _alarm(tmp_path, {"BTCUSDT": -8})
    for guess in range(1000, 10000, 1):  # an old flood of every possible code
        chat.inbox.append((guess, f"ACEPTO {guess}"))
    alarm.step()
    alarm.step()
    assert not broker.opened


def test_a_cooldown_keeps_one_crash_from_ringing_twice(tmp_path):
    alarm, chat, broker, clock = _alarm(tmp_path, {"BTCUSDT": -8})
    alarm.step()
    code = alarm.state["incident"]["code"]
    chat.inbox.append((1, f"NO {code}"))
    alarm.step()
    clock.now += timedelta(minutes=10)
    assert alarm.step() is None  # same crash, inside the 2 h cooldown


def test_pushover_only_with_both_variables():
    calls: list[str] = []
    assert A.pushover("x", {}, post=lambda u, b: calls.append(u)) is False
    assert A.pushover("x", {"TI_PUSHOVER_TOKEN": "t", "TI_PUSHOVER_USER": "u"}, post=lambda u, b: calls.append(u))
    assert calls == ["https://api.pushover.net/1/messages.json"]


def test_telegram_replies_only_from_the_owners_chat():
    answer = {"ok": True, "result": [
        {"update_id": 5, "message": {"chat": {"id": 123}, "text": "ACEPTO 1234"}},
        {"update_id": 6, "message": {"chat": {"id": 999}, "text": "ACEPTO 1234"}},
    ]}
    urls: list[str] = []

    def post(url, body, timeout):
        urls.append(url)
        return answer

    n = T.TelegramNotifier("123456:" + "A" * 35, "123", post)
    assert n.replies(5) == [(5, "ACEPTO 1234")] and "offset=5" in urls[0]


def test_the_alarm_passes_owner_orders_to_the_bots(tmp_path):
    from trading_intelligence.live import ordenes as O

    chat, broker, clock = Chat(), Broker(), Clock()
    q = tmp_path / "ordenes.jsonl"
    alarm = A.Alarm(Feed({}), ["BTCUSDT"], chat, broker, tmp_path / "a.json", Decimal("1"),
                    console=lambda m: None, env={}, clock=clock, orders_path=q)
    chat.inbox.append((1, "META TRX 5"))
    chat.inbox.append((2, "hola"))
    alarm.step()
    assert any("Orden recibida" in m for m in chat.sent)
    cursor = tmp_path / "c"
    cursor.write_text("0")
    orders = O.pending(q, cursor, clock.now)
    assert len(orders) == 1 and orders[0].symbol == "TRXUSDT" and orders[0].value == Decimal("5")
    assert alarm.state["offset"] == 3
