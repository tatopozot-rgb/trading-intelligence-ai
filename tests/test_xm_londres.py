"""XM DEMO London breakout on gold: Asian range, first touch, one entry a day with stop and target, out at 20:00."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from tests.test_xm_demo import TradingMt5
from trading_intelligence.live import xm_londres as L
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
