"""Market watcher: alerts on strong moves and regime changes, once each, never trades."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from trading_intelligence.live import market_watch as W
from trading_intelligence.regime.detector import Regime, RegimeSnapshot, Volatility

NOW = datetime(2026, 10, 9, 13, 5, tzinfo=timezone.utc)


def _frame(closes, step, end):
    idx = pd.date_range(end=pd.Timestamp(end, tz="UTC"), periods=len(closes), freq=step)
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1.0}, index=idx)


class FakeFeed:
    def __init__(self):
        self.closes = {}  # symbol -> 15m closes
        self.fail = set()
        self.calls = []

    def set_move(self, sym, pct_4h=0.0, pct_1h=0.0, pct_24h=0.0, price=100.0):
        closes = [price] * 100
        closes[-1 - 96] = price / (1 + pct_24h / 100)
        closes[-1 - 16] = price / (1 + pct_4h / 100)
        closes[-1 - 4] = price / (1 + pct_1h / 100)
        self.closes[sym] = closes

    def get_ohlcv(self, symbol, timeframe, limit=500):
        self.calls.append((symbol, timeframe))
        if symbol in self.fail:
            raise OSError("down")
        if timeframe == "15m":
            return _frame(self.closes.get(symbol, [100.0] * 100), "15min", "2026-10-09 13:00")
        return _frame([100.0] * limit, "4h", "2026-10-09 12:00")  # last bar (12:00) still forming at 13:05


@pytest.fixture
def regimes(monkeypatch):
    """symbol-independent regime returned for the last closed bar; records what it was given."""
    box = {"regime": Regime.TREND_UP, "seen": []}

    def fake(data):
        box["seen"].append(data.index[-1])
        return RegimeSnapshot(box["regime"], Volatility.NORMAL, 0.8, {})

    monkeypatch.setattr(W, "detect_regime", fake)
    return box


def _watch(tmp_path, feed, now=NOW, symbols=("BTCUSDT",)):
    sent = []
    clock = [now]
    w = W.MarketWatch(feed, list(symbols), tmp_path / "w.json", sent.append, clock=lambda: clock[0])
    return w, sent, clock


def test_a_strong_fall_is_alerted_once_with_price_and_regime(tmp_path, regimes):
    regimes["regime"] = Regime.TREND_DOWN
    feed = FakeFeed()
    feed.set_move("BTCUSDT", pct_4h=-4.5)
    w, sent, clock = _watch(tmp_path, feed)
    w.check()
    assert sent == ["[Vigilante] 📉 BTCUSDT -4.5% en 4h (precio 100.00). Régimen 4h: tendencia bajista."]
    clock[0] += timedelta(minutes=15)
    w.check()
    assert len(sent) == 1  # same move: not repeated
    feed.set_move("BTCUSDT", pct_4h=-8.5)
    w.check()
    assert len(sent) == 2 and "FUERTE" in sent[-1]  # it doubled: told again
    clock[0] += W.COOLDOWN
    feed.set_move("BTCUSDT", pct_4h=-4.5)
    w.check()
    assert len(sent) == 3  # after the cooldown a new move counts again


def test_each_window_and_direction_has_its_own_threshold(tmp_path, regimes):
    feed = FakeFeed()
    feed.set_move("BTCUSDT", pct_1h=2.6, pct_4h=3.9, pct_24h=-7.1)
    w, sent, _ = _watch(tmp_path, feed)
    w.check()
    assert any("+2.6% en 1h" in m for m in sent) and any("-7.1% en 24h" in m for m in sent)
    assert not any("% en 4h " in m for m in sent) and len(sent) == 2


def test_small_moves_say_nothing(tmp_path, regimes):
    feed = FakeFeed()
    feed.set_move("BTCUSDT", pct_1h=2.4, pct_4h=-3.9, pct_24h=6.9)
    w, sent, _ = _watch(tmp_path, feed)
    assert w.check() == [] and sent == []


def test_regime_changes_are_alerted_on_closed_bars_only(tmp_path, regimes):
    feed = FakeFeed()
    w, sent, clock = _watch(tmp_path, feed)
    w.check()
    assert sent == []  # first pass only records the regime
    assert regimes["seen"][-1] == pd.Timestamp("2026-10-09 08:00", tz="UTC")  # the forming 12:00 bar is dropped
    regimes["regime"] = Regime.TREND_DOWN
    w.check()
    assert sent == []  # same closed bar: a different reading is not a new bar
    feed_later = FakeFeed()
    w.feed = feed_later
    feed_later.get_ohlcv = lambda s, tf, limit=500: (
        _frame([100.0] * 100, "15min", "2026-10-09 17:00") if tf == "15m"
        else _frame([100.0] * limit, "4h", "2026-10-09 16:00"))
    clock[0] = NOW + timedelta(hours=4)
    w.check()
    assert sent == ["[Vigilante] 🔄 BTCUSDT cambió a tendencia bajista en la vela de 4h (antes: tendencia alcista)."]


def test_a_change_into_range_or_no_edge_is_not_alerted(tmp_path, regimes):
    feed = FakeFeed()
    w, sent, clock = _watch(tmp_path, feed)
    w.check()
    regimes["regime"] = Regime.RANGE
    w.state["regimes"]["BTCUSDT"]["bar"] = "older"
    w.check()
    assert sent == [] and w.state["regimes"]["BTCUSDT"]["regime"] == "RANGE"


def test_state_survives_a_restart(tmp_path, regimes):
    feed = FakeFeed()
    feed.set_move("BTCUSDT", pct_4h=5)
    w, sent, _ = _watch(tmp_path, feed)
    w.check()
    w2, sent2, _ = _watch(tmp_path, feed)
    w2.check()
    assert len(sent) == 1 and sent2 == []


def test_one_coin_without_data_does_not_stop_the_others(tmp_path, regimes):
    feed = FakeFeed()
    feed.fail.add("ETHUSDT")
    feed.set_move("BTCUSDT", pct_4h=-5)
    w, sent, _ = _watch(tmp_path, feed, symbols=("ETHUSDT", "BTCUSDT"))
    w.check()
    assert len(sent) == 1 and "BTCUSDT" in sent[0]
    feed.fail.add("BTCUSDT")
    w.check()
    assert sent[-1].endswith("Binance no respondió para ninguna moneda en esta vuelta.")


def test_a_corrupt_state_file_starts_clean(tmp_path, regimes):
    (tmp_path / "w.json").write_text("{not json")
    w, _, _ = _watch(tmp_path, FakeFeed())
    assert w.state == {"alerts": {}, "regimes": {}}


def test_summary_lists_every_coin(tmp_path, regimes):
    feed = FakeFeed()
    feed.fail.add("ETHUSDT")
    feed.set_move("BTCUSDT", pct_1h=1, pct_4h=-2, pct_24h=3)
    w, _, _ = _watch(tmp_path, feed, symbols=("BTCUSDT", "ETHUSDT"))
    text = w.summary()
    assert "BTCUSDT: +1.0% / -2.0% / +3.0% · tendencia alcista" in text and "ETHUSDT: sin datos (OSError)" in text


def test_the_watcher_never_touches_orders_or_keys():
    import inspect

    src = inspect.getsource(W)
    for word in ("market_order", "place_stop", "SpotTrader", "Credentials", "BINANCE_TRADE"):
        assert word not in src
    assert "PAXGUSDT" in W.watched_symbols() and "BTCUSDT" in W.watched_symbols()
