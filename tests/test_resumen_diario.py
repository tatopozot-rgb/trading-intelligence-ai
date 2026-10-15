"""Telegram, the logical way (owner, 2026-10-15): practice bots send only alarms and one summary at 22:00 Ecuador;
the real bot sends one message when a trade opens and one when it closes, with the result."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from tests.test_two_way import NOW, FakeBroker
from trading_intelligence.live import binance_futures as F
from trading_intelligence.live import messages as M
from trading_intelligence.live import resumen_diario as R
from trading_intelligence.live import two_way as T


def _engine(tmp_path, sig, telegram, broker=None):
    broker = broker or FakeBroker()
    phone: list[str] = []
    console: list[str] = []
    auto = T.TwoWayAuto(broker, list(sig), tmp_path / "state.json", signal=lambda s, d, h=None, top=None: sig.get(s),
                        pause=lambda s: None, notify=phone.append, chatter=console.append, clock=lambda: NOW,
                        telegram=telegram)
    return auto, broker, phone, console


# --- what reaches the phone ----------------------------------------------------------------------------------

def test_practice_trades_stay_off_telegram_but_alarms_go_at_once(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    auto, b, phone, console = _engine(tmp_path, sig, T.PRACTICE_TELEGRAM)
    auto.step()
    assert b.pos and not phone and any("Abrí una COMPRA en SOL" in m for m in console)
    b.eq = Decimal("55")  # past the 45% loss limit
    auto.step()
    assert len(phone) == 1 and phone[0].startswith("🛑")


def test_real_money_tells_the_open_and_the_close_with_the_result(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    auto, b, phone, console = _engine(tmp_path, sig, T.REAL_TELEGRAM)
    auto.step()
    (opened,) = phone
    assert "Abrí una COMPRA en SOL" in opened and "Entrada: 100,00" in opened and "Stop: 97,00" in opened
    assert "Meta: 106,00" in opened and "pierdo unos 0,30 USDT (0,3% de la cuenta)" in opened
    assert "Calidad" not in opened  # the long detail stays on the console
    b.px = Decimal("106")
    b.pos.clear()  # the target closed it on Binance
    auto.watch()
    closed = phone[-1]
    assert "Cerré la COMPRA en SOL con GANANCIA" in closed and "llegó a la meta" in closed
    assert "+0,60 USDT (+0,6% de la cuenta)" in closed and "aprox." in closed  # the fake broker has no fills
    assert not any(m.startswith("📍") for m in phone)  # no status every 2 minutes on the phone
    result = [e for e in auto.state.events if e["kind"] == "RESULT"]
    assert result and result[0]["pnl"] == "0.60" and result[0]["why"] == "meta"


class FilledBroker(FakeBroker):
    def realized(self, symbol, info):
        return Decimal("-0.3125"), Decimal("96.9")


def test_the_exchange_own_result_is_used_when_the_broker_has_it(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    auto, b, phone, _ = _engine(tmp_path, sig, T.REAL_TELEGRAM, FilledBroker())
    auto.step()
    b.px = Decimal("97")
    b.pos.clear()
    auto.watch()
    closed = phone[-1]
    assert "con PÉRDIDA" in closed and "tocó el stop" in closed and "-0,31 USDT" in closed and "aprox." not in closed


def test_the_signal_turning_closes_with_its_reason(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    auto, b, phone, _ = _engine(tmp_path, sig, T.REAL_TELEGRAM)
    auto.step()
    b.px = Decimal("102")
    sig["SOLUSDT"] = "SELL"
    auto.step()
    assert any("cambió de dirección" in m and "+0,20 USDT" in m for m in phone)


def test_trade_messages_read_plainly():
    text = M.trade_opened("💰 Binance Futuros · DINERO REAL", "AVAXUSDT", "SELL", Decimal("25.5"), Decimal("26.3"),
                          Decimal("23.9"), Decimal("0.95"), Decimal("1.9"), Decimal("3"), "USDT")
    assert "VENTA EN CORTO en AVAX (gano si el precio baja)" in text and "3,0% de la cuenta" in text
    text = M.trade_closed("x", "AVAXUSDT", "SELL", "stop_ganancia", Decimal("0.42"), Decimal("1.33"), "USDT",
                          Decimal("25.5"), Decimal("25.1"), True)
    assert "GANANCIA" in text and "stop que seguía la ganancia" in text and "+1,3% de la cuenta" in text


# --- the brokers' exact results ------------------------------------------------------------------------------

class TradesMarket:
    def __init__(self, rows):
        self.rows, self.asked = rows, []

    def user_trades(self, symbol, since_ms):
        self.asked.append((symbol, since_ms))
        return self.rows


def test_real_futures_result_comes_from_binance_fills_net_of_fees():
    rows = [{"side": "BUY", "price": "100", "qty": "1", "realizedPnl": "0", "commission": "0.05",
             "commissionAsset": "USDT"},
            {"side": "SELL", "price": "104", "qty": "0.5", "realizedPnl": "2", "commission": "0.026",
             "commissionAsset": "USDT"},
            {"side": "SELL", "price": "106", "qty": "0.5", "realizedPnl": "3", "commission": "0.0265",
             "commissionAsset": "USDT"}]
    broker = F.FuturesBroker.__new__(F.FuturesBroker)
    broker.market = TradesMarket(rows)  # type: ignore[assignment]
    pnl, exit_price = broker.realized("SOLUSDT", {"side": "BUY", "opened": NOW.isoformat()})
    assert pnl == Decimal("4.8975") and exit_price == Decimal("105")
    assert broker.market.asked[0][1] == int(NOW.timestamp() * 1000) - 60_000
    broker.market = TradesMarket(rows[:1])  # type: ignore[assignment]
    assert broker.realized("SOLUSDT", {"side": "BUY", "opened": NOW.isoformat()}) is None  # no exit yet


def test_real_futures_result_without_opening_time_looks_back_seven_days_at_the_last_trade_only():
    rows = [{"side": "BUY", "price": "90", "qty": "1", "realizedPnl": "0", "commission": "0.04",
             "commissionAsset": "USDT", "time": 1},
            {"side": "SELL", "price": "95", "qty": "1", "realizedPnl": "5", "commission": "0.04",
             "commissionAsset": "USDT", "time": 2},  # an earlier trade on the same coin: not this one
            {"side": "BUY", "price": "100", "qty": "1", "realizedPnl": "0", "commission": "0.05",
             "commissionAsset": "USDT", "time": 3},
            {"side": "SELL", "price": "104", "qty": "1", "realizedPnl": "4", "commission": "0.05",
             "commissionAsset": "USDT", "time": 4}]
    broker = F.FuturesBroker.__new__(F.FuturesBroker)
    broker.market = TradesMarket(rows)  # type: ignore[assignment]
    before = int(time.time() * 1000)
    assert broker.realized("SOLUSDT", {"side": "BUY", "opened": ""}) == (Decimal("3.9"), Decimal("104"))
    since = broker.market.asked[0][1]
    assert before - 7 * 86_400_000 < since <= int(time.time() * 1000) - 7 * 86_400_000 + 60_000
    broker.market = TradesMarket(rows[3:])  # type: ignore[assignment]
    assert broker.realized("SOLUSDT", {"side": "BUY"}) is None  # entry older than the window: estimate instead
    broker.market = TradesMarket(rows[:3])  # type: ignore[assignment]
    assert broker.realized("SOLUSDT", {"side": "BUY"}) is None  # still open on Binance


def test_practice_futures_result_comes_from_its_own_book(tmp_path):
    broker = F.PaperFuturesBroker.__new__(F.PaperFuturesBroker)
    broker.book = {"closed": [{"symbol": "SOLUSDT", "pnl": "1.2", "exit": "106", "at": NOW.isoformat()}]}
    assert broker.realized("SOLUSDT", {"opened": (NOW - timedelta(hours=1)).isoformat()}) == \
        (Decimal("1.2"), Decimal("106"))
    assert broker.realized("SOLUSDT", {"opened": (NOW + timedelta(hours=1)).isoformat()}) is None


# --- the 22:00 summary ---------------------------------------------------------------------------------------

def _write(path: Path, data: dict, age: timedelta = timedelta(minutes=1), now: datetime = NOW) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    t = (now - age).timestamp()
    os.utime(path, (t, t))


def _runs(tmp_path: Path, now: datetime = NOW) -> Path:
    runs = tmp_path / "live_runs"
    at = (now - timedelta(hours=3)).isoformat()
    _write(runs / "futures_auto" / "shadow" / "state.json", {
        "name": "🧪 Binance Futuros · PRÁCTICA SIMULADO (dinero ficticio)", "capital": "37", "equity": "38.5",
        "currency": "USDT", "status": "RUNNING", "known": {"AVAXUSDT": {"side": "SELL"}},
        "events": [{"at": at, "kind": "OPEN", "text": "", "symbol": "SOLUSDT", "side": "BUY"},
                   {"at": at, "kind": "OPEN", "text": "SELL 2 AVAXUSDT @ 25 SL 26 TP 23"},
                   {"at": at, "kind": "CLOSED_BY_EXCHANGE", "text": "SOLUSDT"},
                   {"at": at, "kind": "RESULT", "text": "", "symbol": "SOLUSDT", "side": "BUY", "pnl": "1.50",
                    "exact": True},
                   {"at": (now - timedelta(days=2)).isoformat(), "kind": "OPEN", "text": "",
                    "symbol": "BTCUSDT", "side": "BUY"}]}, now=now)
    _write(runs / "xm_auto_cripto" / "state.json", {
        "name": "🧪 XM DEMO · Cripto (dinero virtual)", "capital": "10000", "equity": "9900", "currency": "USD",
        "status": "RUNNING", "known": {},
        "events": [{"at": at, "kind": "RESULT", "symbol": "BTCUSDT", "side": "SELL", "pnl": "-40", "exact": False},
                   {"at": at, "kind": "CLOSE", "text": ""}]}, now=now)
    _write(runs / "core_btc" / "paper.json", {"start_capital": 30, "cash": 0, "qty": 0.0005, "entry": 60000,
                                              "equity": 31.2, "trades": []}, age=timedelta(minutes=30), now=now)
    _write(runs / "xm_londres" / "state.json", {"day": "2026-10-12", "done": True, "moneda": "USD", "trades": [
        {"t": at, "accion": "entrada", "lado": "BUY"},
        {"t": at, "accion": "cierre", "pnl": "85.3", "estimado": True}]}, now=now)
    _write(runs / "futures_auto" / "real" / "state.json", {
        "name": "💰 Binance Futuros · DINERO REAL", "capital": "31.69", "equity": "32.1", "currency": "USDT",
        "status": "RUNNING", "known": {"ADAUSDT": {"side": "BUY"}},
        "events": [{"at": at, "kind": "RESULT", "symbol": "SOLUSDT", "side": "BUY", "pnl": "0.41", "exact": True}]},
           age=timedelta(hours=2), now=now)
    _write(runs / "futures_auto" / "real" / "orders.json", {"x": {}}, now=now)
    # the 3x practice account, from before the bots kept their name and their closes' results
    _write(runs / "futures_auto_3x" / "shadow" / "state.json", {
        "capital": "37", "status": "RUNNING", "known": {},
        "events": [{"at": at, "kind": "OPEN", "text": "BUY 1 ETHUSDT @ 2500 SL 2400 TP 2700"},
                   {"at": at, "kind": "CLOSED_BY_EXCHANGE", "text": "ETHUSDT"},
                   {"at": at, "kind": "CLOSE", "text": "XRPUSDT BUY: señal SELL"}]}, now=now)
    _write(runs / "futures_auto_3x" / "shadow" / "paper.json", {"cash": "40", "positions": {}, "closed": [
        {"symbol": "ETHUSDT", "pnl": "-0.75", "exit": "2400", "at": at},
        {"symbol": "XRPUSDT", "pnl": "0.20", "exit": "2.5", "at": (now - timedelta(days=2)).isoformat()}]}, now=now)
    _write(runs / "viejo" / "state.json", {"known": {}, "events": []}, age=timedelta(days=5), now=now)
    return runs


def test_the_summary_tells_each_practice_bot_and_a_conclusion(tmp_path):
    runs = _runs(tmp_path)
    text = R.render(R.find_bots(runs, NOW - timedelta(hours=24), NOW), NOW)
    assert text.startswith("🌙 Resumen del día") and "12-10-2026, 08:00 hora de Ecuador" in text
    assert "• Abrió 2: SOL compra, AVAX venta" in text  # old events without fields still read
    assert "• Cerró 1: SOL ✅ +1,50 USDT" in text and "+3,9% de la cuenta" in text
    assert "Desde que empezó: +4,1%" in text and "Sigue abierta: AVAX (venta)" in text
    assert "BTC compra" not in text  # two days ago: not today's
    assert "🧪 XM DEMO · Cripto\n• Cerró 1: BTC ❌ -40,00 USD aprox.\n" in text  # its CLOSE is the same trade
    assert "🧪 Futuros práctica 1x\n" in text  # "(dinero ficticio)" is said once, in the title
    assert "Núcleo BTC 50" in text and "Sin operaciones" in text and "Desde que empezó: +4,0%" in text
    assert "Londres oro" in text and "Oro ✅ +85,30 USD aprox." in text
    assert "viejo" not in text  # retired five days ago
    assert "💰 Dinero real" in text and "resultado +0,41 USDT" in text and "ADA (compra)" in text
    assert "⚠️ no da señales de vida" in text  # the real bot wrote its state 2 h ago
    assert "📌 Conclusión: día parejo en práctica (4 cerradas: 2 ganadas y 2 perdidas)" in text
    assert "El mejor fue 🧪 XM DEMO · Londres oro (+85,30 USD)" in text and "hoy abrió 0 y cerró 1" in text


def test_both_practice_futures_accounts_have_clear_names_and_old_closes_their_recorded_result(tmp_path):
    text = R.render(R.find_bots(_runs(tmp_path), NOW - timedelta(hours=24), NOW), NOW)
    assert "🧪 Futuros práctica 1x\n" in text and "🧪 Futuros práctica 3x\n" in text and "shadow" not in text
    assert "• Cerró 1: ETH ❌ -0,75 USDT\n" in text  # from the account's own book; XRP was two days ago
    assert "sin resultado" not in text


def test_each_sentence_of_the_conclusion_starts_with_a_capital_letter():
    loser = R.Bot("🧪 XM DEMO · Cripto", Path("x"), "motor", False, "USD", closed=[("BTC", Decimal("-40"), False)])
    other = R.Bot("🧪 Futuros práctica 1x", Path("y"), "motor", False, "USDT", closed=[("SOL", Decimal("-1"), True)])
    text = R.conclusion([loser, other])
    assert "no se toca nada real. El que más perdió fue 🧪 XM DEMO · Cripto (-40,00 USD)." in text


def test_a_quiet_day_says_so():
    assert "día tranquilo" in R.conclusion([R.Bot("x", Path("x"), "motor", False)])


def test_the_summary_window_starts_at_the_last_one_sent(tmp_path):
    runs = _runs(tmp_path)
    phone: list[str] = []
    R.daily(runs, runs / "resumen_diario", lambda t: phone.append(t) or True, NOW)
    assert "SOL ✅" in phone[0]
    later = NOW + timedelta(hours=24)
    assert R.window_start(runs / "resumen_diario", later) == NOW
    R.daily(runs, runs / "resumen_diario", lambda t: phone.append(t) or True, later)
    assert "SOL ✅" not in phone[1]  # already told yesterday


def test_a_bot_that_stops_answering_is_told_once_and_again_when_back(tmp_path):
    runs = _runs(tmp_path)
    phone: list[str] = []
    memory = runs / "resumen_diario"
    sent = R.watch(runs, memory, phone.append, NOW)
    assert len(sent) == 1 and "DINERO REAL" in sent[0] and sent[0].startswith("🚨")
    assert R.watch(runs, memory, phone.append, NOW) == []  # not every 10 minutes
    later = NOW + timedelta(minutes=10)
    _write(runs / "futures_auto" / "real" / "state.json",
           json.loads((runs / "futures_auto" / "real" / "state.json").read_text(encoding="utf-8")), now=later)
    _write(runs / "futures_auto" / "shadow" / "state.json",
           json.loads((runs / "futures_auto" / "shadow" / "state.json").read_text(encoding="utf-8")), now=later)
    _write(runs / "xm_auto_cripto" / "state.json",
           json.loads((runs / "xm_auto_cripto" / "state.json").read_text(encoding="utf-8")), now=later)
    _write(runs / "xm_londres" / "state.json",
           json.loads((runs / "xm_londres" / "state.json").read_text(encoding="utf-8")), now=later)
    back = R.watch(runs, memory, phone.append, later)
    assert back == ["✅ 💰 Binance Futuros · DINERO REAL: volvió a funcionar."]


def test_an_engine_that_ended_its_session_is_not_down(tmp_path):
    runs = tmp_path / "live_runs"
    _write(runs / "a" / "state.json", {"name": "A", "status": "STOPPED", "known": {}, "events": []},
           age=timedelta(hours=5))
    assert R.watch(runs, runs / "resumen_diario", lambda m: None, NOW) == []


def test_without_telegram_nothing_is_sent_and_it_says_why(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TI_TELEGRAM_TOKEN", raising=False)
    assert R.main(["enviar", "--runs", str(tmp_path)]) == 1
    assert "TI_TELEGRAM_TOKEN" in capsys.readouterr().out


def test_ver_prints_without_sending(tmp_path, capsys):
    runs = _runs(tmp_path, datetime.now(timezone.utc))
    assert R.main(["ver", "--runs", str(runs)]) == 0
    assert "Resumen del día" in capsys.readouterr().out
    assert not (runs / "resumen_diario" / "ultimo.json").exists()
