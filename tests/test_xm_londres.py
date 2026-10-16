"""XM DEMO London breakout on gold: Asian range, first touch, one entry a day with stop and target, out at 20:00."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from tests.test_xm_demo import TradingMt5
from trading_intelligence.live import xm_londres as L
from trading_intelligence.live.xm_auto import agent_magic
from trading_intelligence.live.xm_demo import NotDemo, XmDemoTrader
from trading_intelligence.live.xm_mt5 import XmError, XmReader

DAY = pd.Timestamp("2026-10-07", tz="UTC")  # a Wednesday


def _frames(touch_at=None, high=2601.0, low=2599.0, offset=0):
    """1h and 5m candles in XM server time (UTC + offset): Asian range 2590-2610, flat 2600 after."""
    h_idx = pd.date_range(DAY - pd.Timedelta(hours=24), DAY + pd.Timedelta(hours=23), freq="h")
    hourly = pd.DataFrame({"open": 2600.0, "high": 2601.0, "low": 2599.0, "close": 2600.0}, index=h_idx)
    hourly.loc[DAY + pd.Timedelta(hours=2), "high"] = 2610.0
    hourly.loc[DAY + pd.Timedelta(hours=5), "low"] = 2590.0
    f_idx = pd.date_range(DAY + pd.Timedelta(hours=6), DAY + pd.Timedelta(hours=23), freq="5min")
    five = pd.DataFrame({"open": 2600.0, "high": 2601.0, "low": 2599.0, "close": 2600.0}, index=f_idx)
    if touch_at is not None:
        five.loc[DAY + touch_at, ["high", "low"]] = [high, low]
    shift = pd.Timedelta(hours=offset)
    hourly.index, five.index = hourly.index + shift, five.index + shift
    return {"1h": hourly, "5m": five}


def _bot(tmp_path, at, frames, equity=10_000.0, mode=0, tick=(2600.0, 2600.35), offset=0):
    m = TradingMt5(equity=equity, mode=mode, now=at)
    from tests import test_xm_mt5 as X
    X.SYMBOLS["GOLD"]["tick"] = dict(bid=tick[0], ask=tick[1])
    trader = XmDemoTrader(tmp_path / "orders.json", m, reader=XmReader(m, clock=lambda: at))
    trader.connect()
    notes: list[str] = []
    bot = L.LondonBot(trader, tmp_path / "state.json", notes.append, clock=lambda: at,
                      candles=lambda s, tf, n: frames[tf], offset=lambda: offset)
    return bot, m, notes


@pytest.fixture(autouse=True)
def _restore_gold_tick():
    from tests import test_xm_mt5 as X
    saved = dict(X.SYMBOLS["GOLD"]["tick"])
    yield
    X.SYMBOLS["GOLD"]["tick"] = saved


def test_server_offset_reads_whole_hours_and_refuses_nonsense():
    now = datetime(2026, 10, 7, 9, tzinfo=timezone.utc)
    assert L.server_offset_hours(int(now.timestamp()) + 3 * 3600 - 20, now) == 3
    assert L.server_offset_hours(int(now.timestamp()) - 5, now) == 0
    with pytest.raises(XmError):
        L.server_offset_hours(int(now.timestamp()) + 7 * 3600, now)


def test_long_on_break_of_the_asian_high_with_stop_and_target(tmp_path):
    at = (DAY + pd.Timedelta(hours=8, minutes=7)).to_pydatetime()
    bot, m, notes = _bot(tmp_path, at, _frames(pd.Timedelta(hours=8, minutes=5), high=2611.0), tick=(2611.0, 2611.35))
    msg = bot.step()
    (order,) = m.sent
    assert order["type"] == 0 and order["sl"] == pytest.approx(2590.0, abs=0.02)
    assert order["tp"] == pytest.approx(2610.0 + 20.0, abs=0.02)
    assert "COMPRO" in msg and notes and bot.state["done"]
    assert bot.step() == "posición abierta: stop y meta descansan en XM" and len(m.sent) == 1


def test_one_entry_a_day_and_risk_is_one_percent(tmp_path):
    at = (DAY + pd.Timedelta(hours=9)).to_pydatetime()
    bot, m, _ = _bot(tmp_path, at, _frames(pd.Timedelta(hours=8), low=2589.0), tick=(2589.0, 2589.35))
    bot.step()
    (order,) = m.sent
    assert order["type"] == 1  # short below the Asian low
    risk = order["volume"] * 100 * abs(order["sl"] - order["price"])  # 1 lot = 100 oz
    assert risk <= 100.0 + 1e-6 and risk > 80.0  # 1% of 10,000, lots rounded down
    m.positions.clear()  # the stop or target closed it on XM's server
    bot.step()
    assert len(m.sent) == 1


def test_both_sides_in_one_candle_means_no_trade_today(tmp_path):
    at = (DAY + pd.Timedelta(hours=10)).to_pydatetime()
    bot, m, notes = _bot(tmp_path, at, _frames(pd.Timedelta(hours=9), high=2612.0, low=2588.0))
    assert "dos lados" in bot.step() and not m.sent and bot.state["done"]


def test_no_entry_when_price_already_passed_the_target(tmp_path):
    at = (DAY + pd.Timedelta(hours=11)).to_pydatetime()
    bot, m, _ = _bot(tmp_path, at, _frames(pd.Timedelta(hours=8), high=2611.0), tick=(2640.0, 2640.35))
    bot.step()
    assert not m.sent


def test_nothing_outside_the_window_or_at_the_weekend(tmp_path):
    early = (DAY + pd.Timedelta(hours=6, minutes=30)).to_pydatetime()
    bot, m, _ = _bot(tmp_path, early, _frames(pd.Timedelta(hours=6, minutes=30), high=2615.0))
    bot.step()
    saturday = (DAY + pd.Timedelta(days=3, hours=9)).to_pydatetime()
    bot2, m2, _ = _bot(tmp_path / "s", saturday, _frames())
    bot2.step()
    assert not m.sent and not m2.sent


def test_closes_its_position_at_20_utc(tmp_path):
    at = (DAY + pd.Timedelta(hours=8, minutes=7)).to_pydatetime()
    frames = _frames(pd.Timedelta(hours=8, minutes=5), high=2611.0)
    bot, m, _ = _bot(tmp_path, at, frames, tick=(2611.0, 2611.35))
    bot.step()
    late = (DAY + pd.Timedelta(hours=20, minutes=2)).to_pydatetime()
    bot.clock = lambda: late
    assert "20:00" in bot.step()
    assert len(m.sent) == 2 and "position" in m.sent[1] and not m.positions


def test_server_time_is_converted_to_utc(tmp_path):
    at = (DAY + pd.Timedelta(hours=8, minutes=7)).to_pydatetime()
    frames = _frames(pd.Timedelta(hours=8, minutes=5), high=2611.0, offset=3)
    bot, m, _ = _bot(tmp_path, at, frames, tick=(2611.0, 2611.35), offset=3)
    bot.step()
    assert len(m.sent) == 1 and m.sent[0]["sl"] == pytest.approx(2590.0, abs=0.02)


def test_a_real_account_never_trades(tmp_path):
    at = (DAY + pd.Timedelta(hours=8, minutes=7)).to_pydatetime()
    with pytest.raises(NotDemo):
        _bot(tmp_path, at, _frames(pd.Timedelta(hours=8, minutes=5), high=2611.0), mode=2)


def test_a_close_on_the_server_is_recorded_with_its_result_for_the_daily_summary(tmp_path):
    at = (DAY + pd.Timedelta(hours=8, minutes=7)).to_pydatetime()
    bot, m, _ = _bot(tmp_path, at, _frames(pd.Timedelta(hours=8, minutes=5), high=2611.0), tick=(2611.0, 2611.35))
    bot.step()
    from tests import test_xm_mt5 as X
    X.SYMBOLS["GOLD"]["tick"] = dict(bid=2630.0, ask=2630.35)  # at the target
    m.positions.clear()
    bot.step()
    close = bot.state["trades"][-1]
    assert close["accion"] == "cierre" and close["motivo"] == "meta" and close["estimado"]
    assert 0 < float(close["pnl"]) and "open" not in bot.state
    entry = bot.state["trades"][0]
    risk = float(entry["lotes"]) * 100 * abs(float(entry["sl"]) - float(entry["precio"]))
    assert float(close["pnl"]) == pytest.approx(risk * 19.0 / 21.35, rel=0.02)  # target 19 away, stop 21.35


def test_its_trades_stay_off_telegram_but_a_refused_order_is_an_alarm(tmp_path):
    at = (DAY + pd.Timedelta(hours=8, minutes=7)).to_pydatetime()
    bot, m, notes = _bot(tmp_path, at, _frames(pd.Timedelta(hours=8, minutes=5), high=2611.0), tick=(2611.0, 2611.35))
    phone: list[str] = []
    bot.alarm = phone.append
    bot.step()
    assert notes and not phone  # the entry: console only (it goes in the 22:00 summary)
    bot2, m2, notes2 = _bot(tmp_path / "b", at, _frames(pd.Timedelta(hours=8, minutes=5), high=2611.0),
                            tick=(2611.0, 2611.35), equity=1.0)
    bot2.alarm = phone.append
    bot2.step()
    assert not m2.sent and phone and phone[0].startswith("⚠️") and "no entro" in phone[0]


# BTCUSD (Leader, 2026-10-16): its own agent, weekends, 1% of a nominal 1,000 USD in a shared DEMO account
BTC = dict(info=dict(trade_mode=4, volume_min=0.01, volume_step=0.01, volume_max=100.0, trade_contract_size=1.0,
                     trade_tick_value=0.01, trade_tick_size=0.01, swap_long=-3452.0, swap_short=-2301.0, swap_mode=1,
                     trade_stops_level=0, point=0.01),
           tick=dict(bid=82000.0, ask=82040.0), margin=816.0)  # XM: margin 1:1 on crypto, spread 40 USD


def _btc_frames(day, touch_at, high, low=81999.0, asia=(82000.0, 81500.0)):
    mid = (asia[0] + asia[1]) / 2
    flat = {"open": mid, "high": mid + 1, "low": mid - 1, "close": mid}
    h_idx = pd.date_range(day - pd.Timedelta(hours=24), day + pd.Timedelta(hours=23), freq="h")
    hourly = pd.DataFrame(flat, index=h_idx)
    hourly.loc[day + pd.Timedelta(hours=2), "high"] = asia[0]
    hourly.loc[day + pd.Timedelta(hours=5), "low"] = asia[1]
    f_idx = pd.date_range(day + pd.Timedelta(hours=6), day + pd.Timedelta(hours=23), freq="5min")
    five = pd.DataFrame(flat, index=f_idx)
    five.loc[day + touch_at, ["high", "low"]] = [high, low]
    return {"1h": hourly, "5m": five}


@pytest.fixture
def btc():
    from tests import test_xm_mt5 as X
    X.SYMBOLS["BTCUSD"] = {k: dict(v) if isinstance(v, dict) else v for k, v in BTC.items()}
    yield X.SYMBOLS["BTCUSD"]
    X.SYMBOLS.pop("BTCUSD", None)


def _btc_bot(tmp_path, at, frames, equity=50_000.0, nominal=Decimal("1000")):
    m = TradingMt5(equity=equity, now=at)
    trader = XmDemoTrader(tmp_path / "orders.json", m, reader=XmReader(m, clock=lambda: at),
                          magic=agent_magic(L.agent_name("BTCUSD")))
    trader.connect()
    notes: list[str] = []
    bot = L.LondonBot(trader, tmp_path / "state.json", notes.append, clock=lambda: at,
                      candles=lambda s, tf, n: frames[tf], offset=lambda: 0, symbol="BTCUSD", nominal=nominal)
    return bot, m, notes


def test_btc_has_its_own_agent_and_gold_keeps_its_own():
    assert L.agent_name("GOLD") == "Londres" and L.agent_name("BTCUSD") == "Londres BTCUSD"
    assert agent_magic(L.agent_name("GOLD")) == agent_magic("Londres") != agent_magic(L.agent_name("BTCUSD"))
    assert L.tag_for("GOLD") == L.TAG and "Londres BTC " in L.tag_for("BTCUSD")


def test_btc_risks_one_percent_of_the_nominal_capital_not_of_the_shared_equity(tmp_path, btc):
    at = (DAY + pd.Timedelta(hours=8, minutes=7)).to_pydatetime()
    bot, m, notes = _btc_bot(tmp_path, at, _btc_frames(DAY, pd.Timedelta(hours=8, minutes=5), high=82010.0))
    msg = bot.step()
    (order,) = m.sent
    assert order["type"] == 0 and order["sl"] == pytest.approx(81500.0, abs=0.02)
    assert order["tp"] == pytest.approx(82500.0, abs=0.02)
    risk = order["volume"] * abs(order["price"] - order["sl"])  # 1 lot = 1 BTC
    assert order["volume"] == pytest.approx(0.01) and risk <= 10.0  # 1% of 1,000, not 500 of the 50,000 equity
    assert "Londres BTC" in msg and bot.state["simbolo"] == "BTCUSD" and bot.state["capital_nominal"] == "1000"
    assert m.sent[0]["magic"] == agent_magic("Londres BTCUSD")


def test_btc_size_is_capped_at_five_times_the_nominal(tmp_path, btc):
    at = (DAY + pd.Timedelta(hours=8, minutes=7)).to_pydatetime()
    frames = _btc_frames(DAY, pd.Timedelta(hours=8, minutes=5), high=82010.0, asia=(82000.0, 81900.0))
    bot, m, _ = _btc_bot(tmp_path, at, frames)
    bot.step()
    (order,) = m.sent
    # 10 USD over a 140 USD stop would be 0.07 BTC; 5x 1,000 at 82,020 allows 0.06
    assert order["volume"] == pytest.approx(0.06)


def test_btc_trades_the_weekend_and_gold_does_not(tmp_path, btc):
    saturday = DAY + pd.Timedelta(days=3)
    at = (saturday + pd.Timedelta(hours=8, minutes=7)).to_pydatetime()
    bot, m, _ = _btc_bot(tmp_path, at, _btc_frames(saturday, pd.Timedelta(hours=8, minutes=5), high=82010.0))
    bot.step()
    assert len(m.sent) == 1
    gold, mg, _ = _bot(tmp_path / "oro", at, _frames())
    assert not gold.weekends and gold.step() == "fuera de horario o ya operé hoy" and not mg.sent


def test_gold_without_a_nominal_still_risks_one_percent_of_equity(tmp_path):
    at = (DAY + pd.Timedelta(hours=9)).to_pydatetime()
    bot, m, _ = _bot(tmp_path, at, _frames(pd.Timedelta(hours=8), low=2589.0), tick=(2589.0, 2589.35))
    assert bot.nominal is None and bot._sizing() == (L.RISK_PCT, L.CAPS)
    assert bot.state["simbolo"] == "GOLD" and "capital_nominal" not in bot.state


def test_a_nominal_capital_must_be_positive(tmp_path, btc):
    at = (DAY + pd.Timedelta(hours=8)).to_pydatetime()
    with pytest.raises(ValueError):
        _btc_bot(tmp_path, at, _btc_frames(DAY, pd.Timedelta(hours=8), high=82010.0), nominal=Decimal("0"))
