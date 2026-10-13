"""Owner's Telegram orders: parsing, the shared queue with per-bot cursors, and the engine applying them."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from tests.test_two_way import NOW, FakeBroker, _engine
from trading_intelligence.live import ordenes as O
from trading_intelligence.live import two_way as T


def test_parse_close_and_target_orders():
    assert O.parse("cierra trx") == ("CIERRA", "TRXUSDT", None, False)
    assert O.parse("META TRX 5%") == ("META", "TRXUSDT", Decimal("5"), False)
    assert O.parse("meta btcusdt precio 90000") == ("META", "BTCUSDT", Decimal("90000"), True)
    assert O.parse("META TRX 0,5") == ("META", "TRXUSDT", Decimal("0.5"), False)
    for bad in ("CIERRA", "META TRX", "META TRX abc", "META TRX -3", "COMPRA TRX", "ACEPTO 1234", "META TRX X 5"):
        assert O.parse(bad) is None


def test_queue_cursor_and_stale_orders(tmp_path):
    q, c1, c2 = tmp_path / "o.jsonl", tmp_path / "a.cursor", tmp_path / "b.cursor"
    O.enqueue(q, "CIERRA", "TRXUSDT", None, False, NOW - timedelta(hours=1))  # before any bot looked
    assert O.pending(q, c1, NOW) == []  # a new bot starts from now
    O.enqueue(q, "META", "TRXUSDT", Decimal("5"), False, NOW - timedelta(minutes=20))  # stale
    O.enqueue(q, "CIERRA", "SOLUSDT", None, False, NOW)
    got = O.pending(q, c1, NOW)
    assert [o.symbol for o in got] == ["SOLUSDT"]
    assert O.pending(q, c1, NOW) == []  # each order once per bot
    c2.write_text("0")
    assert [o.kind for o in O.pending(q, c2, NOW)] == ["CIERRA"]  # another bot reads its own copy
    assert O.target_price(Decimal("100"), "BUY", Decimal("5"), False) == Decimal("105")
    assert O.target_price(Decimal("100"), "SELL", Decimal("5"), False) == Decimal("95")


def _holding(tmp_path, side="BUY"):
    sig = {"SOLUSDT": side}
    q = tmp_path / "ordenes.jsonl"
    auto, b, sent = _engine(tmp_path, sig, orders_path=q, watch_every_s=0)
    auto.step()
    assert "SOLUSDT" in b.pos
    sig["SOLUSDT"] = None
    auto.watch()  # the bot sets its cursor
    return auto, b, sent, q


def test_close_now_by_telegram(tmp_path):
    auto, b, sent, q = _holding(tmp_path)
    O.enqueue(q, "CIERRA", "SOLUSDT", None, False, NOW)
    auto.watch()
    assert "SOLUSDT" not in b.pos and "SOLUSDT" not in auto.state.known
    assert any("✋" in m and "ordenaste" in m for m in sent)


def test_target_by_telegram_closes_when_reached(tmp_path):
    auto, b, sent, q = _holding(tmp_path)
    O.enqueue(q, "META", "SOLUSDT", Decimal("2"), False, NOW)  # entry 100 -> 102
    auto.watch()
    assert auto.state.known["SOLUSDT"]["owner_target"] == "102.00"
    assert any("🎯" in m for m in sent)
    b.px = Decimal("102.5")
    auto.watch()
    assert "SOLUSDT" not in b.pos and any("llegó a tu meta" in m for m in sent)


def test_a_target_behind_the_price_is_refused_and_other_symbols_ignored(tmp_path):
    auto, b, sent, q = _holding(tmp_path)
    b.px = Decimal("110")
    O.enqueue(q, "META", "SOLUSDT", Decimal("5"), False, NOW)  # 105 is already behind 110
    O.enqueue(q, "CIERRA", "ETHUSDT", None, False, NOW)  # not this bot's position
    auto.watch()
    assert "SOLUSDT" in b.pos and "owner_target" not in auto.state.known["SOLUSDT"]
    assert any("ya quedó atrás" in m for m in sent)


def test_without_an_orders_file_nothing_changes(tmp_path):
    auto, b, sent = _engine(tmp_path, {"SOLUSDT": "BUY"}, watch_every_s=0)
    auto.step()
    auto.watch()
    assert "SOLUSDT" in b.pos and isinstance(auto, T.TwoWayAuto) and isinstance(b, FakeBroker)
