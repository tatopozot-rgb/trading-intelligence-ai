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
    # Plain Spanish for a non-programmer: the coin, the money, why, and what to do (nothing).
    assert sent[0].startswith("🟢 Compré BTC por 9,98 USDT a 100,00.") and "señal de compra" in sent[0]
    assert "simulado" not in sent[0] and "No tienes que hacer nada." in sent[0]
    assert sent[1].startswith("🛡️ Dejé un stop de protección en Binance para BTC en 95,00")
    loop.runner.paper.pending_orders[0].stop_price = Decimal("97")
    op.step(decide=True)  # the stop only moved: no new alert
    assert len(sent) == 2
    now[0] += SUMMARY_EVERY
    op.step(decide=False)
    assert len(sent) == 3 and sent[2].startswith("📊 Resumen de tu sesión: empezaste con 50,00 USDT")
    assert "BTC (+0,0%)" in sent[2] and "límite de pérdida es 10,00 USDT" in sent[2]
    trader.prices["BTCUSDT"] = Decimal("96")
    op.step(decide=False)
    assert sent[-1].startswith("🔴 Vendí BTC y recibí") and "perdiste" in sent[-1] and "stop loss" in sent[-1]
    assert "STOP_HIT" not in " ".join(sent)  # no internal codes reach the owner


def test_friendly_messages_read_like_a_person():
    from trading_intelligence.live import messages as M

    assert M.num(Decimal("61230.5")) == "61.230,50" and M.price(Decimal("0.123456")) == "0,1235"
    assert M.sell("ETHUSDT", Decimal("15.4"), Decimal("0.4"), "tendencia:CLOSE", True) == (
        "🔴 Vendí ETH y recibí 15,40 USDT. En esta operación ganaste 0,40 USDT ✅. "
        "Motivo: la estrategia dio señal de salida. No tienes que hacer nada.")
    assert "simulado, sin dinero real" in M.buy("BTCUSDT", Decimal("6"), None, "tendencia", False)
    assert "vas perdiendo 1,50 USDT" in M.summary(Decimal("38"), Decimal("36.5"), Decimal("13.3"), {}, True)
    assert "No tienes posiciones abiertas" in M.summary(Decimal("38"), Decimal("38"), Decimal("13.3"), {}, True)
    assert "\"continúa\"" in M.warning(Decimal("11.3"), Decimal("13.3"))
    assert M.finished("META_ALCANZADA: x", Decimal("38"), Decimal("40")).endswith("ganaste 2,00 USDT ✅.")
    assert M.reason("EXCHANGE_STOP:95") == "se activó el stop de protección que estaba puesto en Binance"
    assert M.reason("ALGO_NUEVO") == "ALGO_NUEVO"  # unknown codes are shown, never hidden


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


def test_an_emoji_on_a_windows_redirected_console_never_stops_an_alert(monkeypatch):
    import io

    # what python.exe gets when redirected; newline="\n" so the check is the same on Windows (no \r\n)
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\n")
    monkeypatch.setattr("sys.stdout", out)
    post = FakePost()
    T.make_notify(T.console, T.TelegramNotifier(TOKEN, "42", post))("📉 BTCUSDT -4.5% en 4h · régimen")
    out.flush()
    assert post.calls[0][1]["text"] == "📉 BTCUSDT -4.5% en 4h · régimen"  # the phone gets it intact
    assert out.buffer.getvalue().decode("cp1252") == "? BTCUSDT -4.5% en 4h · régimen\n"
    monkeypatch.setattr("sys.stdout", None)
    T.console("sin consola")  # pythonw / detached: nothing to write to, no error


def test_a_broken_console_does_not_lose_the_alert(monkeypatch):
    class Broken:
        encoding = "utf-8"

        def write(self, s):
            raise OSError("console gone")

        def flush(self):
            pass

    monkeypatch.setattr("sys.stdout", Broken())
    post = FakePost()
    T.make_notify(T.console, T.TelegramNotifier(TOKEN, "42", post))("AVISO")
    assert post.calls[0][1]["text"] == "AVISO"


def test_telegram_goes_before_the_console():
    post = FakePost()

    def failing_console(message):
        raise RuntimeError("console failed")

    with pytest.raises(RuntimeError):
        T.make_notify(failing_console, T.TelegramNotifier(TOKEN, "42", post))("STOP")
    assert post.calls and post.calls[0][1]["text"] == "STOP"
