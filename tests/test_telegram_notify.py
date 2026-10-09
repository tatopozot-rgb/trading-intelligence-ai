"""Telegram alerts: best effort, private, never leak the token, never stop the operator."""
from __future__ import annotations

import json
import logging
import urllib.error
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading_intelligence.live import telegram_notify as T

TOKEN = "123456789:" + "A" * 35


class FakePost:
    def __init__(self, answer=None, error=None):
        self.calls, self.answer, self.error = [], answer if answer is not None else {"ok": True}, error

    def __call__(self, url, body, timeout):
        self.calls.append((url, json.loads(body) if body else None))
        if self.error:
            raise self.error
        return self.answer


def test_a_message_goes_to_the_owners_chat_only():
    post = FakePost()
    assert T.TelegramNotifier(TOKEN, "42", post).send("COMPRA BTCUSDT")
    url, body = post.calls[0]
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert body["chat_id"] == "42" and body["text"] == "COMPRA BTCUSDT"


def test_failures_never_raise_and_never_log_the_token(caplog):
    caplog.set_level(logging.WARNING)
    for error in (urllib.error.HTTPError(f"https://api.telegram.org/bot{TOKEN}/x", 401, "no", {}, None),
                  OSError(f"down bot{TOKEN}"), TimeoutError()):
        assert T.TelegramNotifier(TOKEN, "42", FakePost(error=error)).send("x") is False
    assert T.TelegramNotifier(TOKEN, "42", FakePost(answer={"ok": False})).send("x") is False
    assert caplog.records and TOKEN not in caplog.text and TOKEN.split(":")[1] not in caplog.text
    assert TOKEN not in repr(T.TelegramNotifier(TOKEN, "42", FakePost()))


def test_long_messages_are_cut_to_what_telegram_accepts():
    post = FakePost()
    T.TelegramNotifier(TOKEN, "42", post).send("x" * 10000)
    assert len(post.calls[0][1]["text"]) == T.MAX_CHARS


@pytest.mark.parametrize("token,chat", [("bad", "42"), (TOKEN, "abc"), (TOKEN + "/../x", "42"), (TOKEN, "4 2")])
def test_malformed_settings_are_refused(token, chat):
    with pytest.raises(ValueError):
        T.TelegramNotifier(token, chat, FakePost())


def test_alerts_are_off_without_both_variables():
    assert T.from_env({}) is None and T.from_env({T.TOKEN_VAR: TOKEN}) is None
    assert T.from_env({T.TOKEN_VAR: "bad", T.CHAT_VAR: "42"}) is None
    assert T.from_env({T.TOKEN_VAR: TOKEN, T.CHAT_VAR: " 42 "}).chat_id == "42"


def test_notify_always_prints_and_also_sends_when_configured():
    printed, post = [], FakePost(error=OSError())  # Telegram down: the console still gets it
    T.make_notify(printed.append, T.TelegramNotifier(TOKEN, "42", post), "[TI] ")("AVISO")
    assert printed == ["AVISO"] and post.calls[0][1]["text"] == "[TI] AVISO"
    base = printed.append
    assert T.make_notify(base, None) is base


def test_only_the_telegram_host_is_contacted():
    with pytest.raises(ValueError):
        T.urllib_post("https://evil.example/bot1/sendMessage", b"{}", 1)
    with pytest.raises(ValueError):
        T.urllib_post("http://api.telegram.org/bot1/sendMessage", b"{}", 1)


def test_chat_id_lookup_lists_who_wrote_to_the_bot():
    post = FakePost(answer={"ok": True, "result": [{"message": {"chat": {"id": 42}}},
                                                   {"message": {"chat": {"id": 42}}},
                                                   {"edited_message": {}}, {"message": {"chat": {"id": -7}}}]})
    assert T.TelegramNotifier(TOKEN, "0", post).recent_chat_ids() == ["42", "-7"]
    assert post.calls[0][0].endswith("/getUpdates") and post.calls[0][1] is None


# --- the operator's alerts -------------------------------------------------------------


def test_the_operator_alerts_each_trade_each_new_guard_and_a_periodic_summary(tmp_path):
    from tests.test_live_operator import LIMITS, FakeLoop, GuardTrader
    from trading_intelligence.execution.order_models import OrderRequest, Position
    from trading_intelligence.live.operator import SUMMARY_EVERY, Operator
    from trading_intelligence.live.session import Session

    now = [datetime(2026, 10, 9, 12, tzinfo=timezone.utc)]
    sent: list[str] = []
    trader = GuardTrader({"BTCUSDT": Decimal("100")})
    loop = FakeLoop(tmp_path)
    loop.runner.paper.positions["BTCUSDT"] = Position("BTCUSDT", Decimal("0.1"), Decimal("100"), Decimal("0"))
    loop.runner.paper._last_price["BTCUSDT"] = Decimal("100")
    loop.runner.paper.pending_orders.append(OrderRequest("BTCUSDT", "SELL", "STOP", Decimal("0.1"),
                                                         stop_price=Decimal("95.009")))
    Session("s1", "tendencia", "t", Decimal("50")).save(tmp_path / "session.json")
    op = Operator(tmp_path, trader, LIMITS, profile="tendencia", timeframe="1h", symbols=["BTCUSDT"], loop=loop,
                  clock=lambda: now[0], notify=sent.append, real=True, trailing_pct=Decimal("0"))
    op.step(decide=True)
    assert sent[0].startswith("[REAL] COMPRA BTCUSDT") and sent[1] == "[REAL] stop puesto en Binance: BTCUSDT 95.00"
    loop.runner.paper.pending_orders[0].stop_price = Decimal("97")
    op.step(decide=True)  # the stop only moved: no new alert
    assert len(sent) == 2
    now[0] += SUMMARY_EVERY
    op.step(decide=False)
    assert len(sent) == 3 and sent[2].startswith("[REAL] resumen:") and "BTCUSDT" in sent[2]
    trader.prices["BTCUSDT"] = Decimal("96")
    op.step(decide=False)
    assert sent[-1].startswith("[REAL] VENTA BTCUSDT") and "STOP" in sent[-1]


def test_a_launched_session_alerts_by_telegram_when_configured(tmp_path, monkeypatch):
    from trading_intelligence.live import operator as O
    from trading_intelligence.live.limits import load_limits

    post = FakePost()
    got = []

    class Spy:
        def __init__(self, d, trader, limits, **kw):
            got.append(kw["notify"])

        def run(self, **kw):
            got[-1]("AVISO de prueba")

    monkeypatch.setattr(O, "_trader", lambda real, journal: None)
    monkeypatch.setattr(O, "Operator", Spy)
    monkeypatch.setattr(T, "urllib_post", post)
    monkeypatch.setenv(T.TOKEN_VAR, TOKEN)
    monkeypatch.setenv(T.CHAT_VAR, "42")
    meta = {"profile": "copiar", "timeframe": "4h", "symbols": ["BTCUSDT"], "real": True}
    O._launch(tmp_path, load_limits(), meta, "100", 1)
    assert post.calls and post.calls[0][1] == {"chat_id": "42", "text": "AVISO de prueba",
                                               "disable_web_page_preview": True}
