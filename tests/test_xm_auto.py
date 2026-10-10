"""XM automatic operator: both directions, SL/TP on the server, daily loss guard, owner's cadence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tests.test_xm_demo import TradingMt5
from tests.test_xm_mt5 import NOW
from trading_intelligence.live import xm_auto as A
from trading_intelligence.live import xm_demo as D
from trading_intelligence.live.xm_mt5 import XmReader


def _auto(tmp_path, signals, equity=1_000_000.0, clock=lambda: NOW, tick_age=5, **kw):
    """signals: symbol -> BUY / SELL / None; the test changes it between decisions."""
    m = TradingMt5(equity=equity, tick_age=tick_age)
    t = D.XmDemoTrader(tmp_path / "orders.json", m, reader=XmReader(m, clock=lambda: NOW))
    t.connect()
    sent: list[str] = []
    auto = A.XmAuto(t, list(signals), tmp_path / "state.json", signal=lambda sym, data: signals.get(sym),
                    notify=sent.append, clock=clock, **kw)
    return auto, m, sent


def test_a_rising_market_buys_and_a_falling_one_sells_short_with_sl_and_tp_on_the_server(tmp_path):
    auto, m, sent = _auto(tmp_path, {"EURUSD": "BUY", "GOLD": "SELL"})
    auto.step()
    by = {r["symbol"]: r for r in m.sent}
    assert by["EURUSD"]["type"] == 0 and by["EURUSD"]["sl"] < by["EURUSD"]["price"] < by["EURUSD"]["tp"]
    assert by["GOLD"]["type"] == 1 and by["GOLD"]["tp"] < by["GOLD"]["price"] < by["GOLD"]["sl"]
    assert all(r["magic"] == D.MAGIC for r in m.sent)
    assert set(auto.state.known) == {"EURUSD", "GOLD"}
    assert any("Compré" in s and "subiendo" in s for s in sent) and any("Vendí en corto" in s and "bajando" in s for s in sent)


def test_the_opposite_signal_closes_and_the_next_decision_turns_around(tmp_path):
    sig = {"EURUSD": "BUY"}
    auto, m, sent = _auto(tmp_path, sig)
    auto.step()
    sig["EURUSD"] = "SELL"
    auto.step()  # closes the buy, opens nothing in the same pass
    assert "position" in m.sent[-1] and not m.positions and "EURUSD" not in auto.state.known
    assert any("cerré la compra de EURUSD" in s for s in sent)
    auto.step()
    assert m.positions[0].type == 1  # now short


def test_no_signal_no_entry_and_max_open_is_respected(tmp_path):
    sig = {"EURUSD": None, "GOLD": None, "SILVER": None}
    auto, m, _ = _auto(tmp_path, sig, max_open=1)
    auto.step()
    assert m.sent == []
    sig.update(EURUSD="BUY", GOLD="SELL")
    auto.step()
    assert len(m.positions) == 1


def test_a_position_closed_by_its_stop_or_target_on_the_server_is_reported(tmp_path):
    sig = {"EURUSD": "BUY"}
    auto, m, sent = _auto(tmp_path, sig)
    auto.step()
    m.positions.clear()  # XM's server executed the SL or the TP
    sig["EURUSD"] = None
    auto.step()
    assert "EURUSD" not in auto.state.known and any("se cerró EURUSD en el servidor" in s for s in sent)


def test_the_daily_loss_guard_closes_and_stops_entries_until_the_next_day(tmp_path):
    now = {"t": NOW}
    sig = {"EURUSD": "BUY", "GOLD": None}
    auto, m, sent = _auto(tmp_path, sig, clock=lambda: now["t"], daily_loss_pct=Decimal("5"))
    auto.step()
    m.equity = 940_000.0  # -6% today
    sig["GOLD"] = "SELL"
    auto.step()
    assert auto.state.halted and not m.positions and any("perdió 5% hoy" in s for s in sent)
    auto.step()
    assert not m.positions  # still halted
    now["t"] = NOW + timedelta(days=1)
    auto.step()
    assert not auto.state.halted and m.positions  # a new day, with that day's equity as the base


def test_risk_is_never_raised_after_a_loss(tmp_path):
    auto, m, _ = _auto(tmp_path, {"EURUSD": "BUY"})
    auto.step()
    first = m.sent[-1]["volume"]
    m.positions.clear()
    m.equity = 990_000.0
    auto.step()
    assert m.sent[-1]["volume"] <= first


def test_a_closed_market_is_skipped_and_noted_once(tmp_path):
    auto, m, _ = _auto(tmp_path, {"EURUSD": "BUY"}, tick_age=10_000)
    auto.step()
    auto.step()
    assert m.sent == []
    skips = [e for e in auto.state.events if e["kind"] == "SKIP"]
    assert len(skips) == 1 and "mercado cerrado" in skips[0]["text"]


def test_the_owners_cadence_two_minutes_inside_his_windows_five_outside(tmp_path):
    t = {"now": datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc)}  # 08:00 Ecuador: inside 07-10
    auto, _, _ = _auto(tmp_path, {"EURUSD": None}, clock=lambda: t["now"])
    due = []
    for minute in range(10):
        t["now"] = datetime(2026, 10, 12, 13, minute, 5, tzinfo=timezone.utc)
        due.append(auto.decision_due())
    assert sum(due) == 5
    due = []
    for minute in range(10):
        t["now"] = datetime(2026, 10, 12, 4, minute, 5, tzinfo=timezone.utc)  # 23:00 Ecuador: outside
        due.append(auto.decision_due())
    assert sum(due) == 2


def test_state_survives_a_restart(tmp_path):
    auto, m, _ = _auto(tmp_path, {"EURUSD": "BUY"})
    auto.step()
    again = A.State.load(tmp_path / "state.json")
    assert again.known == auto.state.known and again.day == NOW.date().isoformat()


def test_the_cli_runs_one_decision_on_a_demo_account(tmp_path, capsys):
    m = TradingMt5(equity=1_000_000.0)
    assert A.main(["--simbolos", "EURUSD", "--dir", str(tmp_path), "--una-vez"], mt5=m) == 0
    assert "XM DEMO" in capsys.readouterr().out
    assert (tmp_path / "state.json").exists()


def test_the_cli_refuses_a_real_account(tmp_path, capsys):
    m = TradingMt5(mode=2)
    assert A.main(["--dir", str(tmp_path), "--una-vez"], mt5=m) == 1
    assert "DEMO" in capsys.readouterr().out and m.sent == []
