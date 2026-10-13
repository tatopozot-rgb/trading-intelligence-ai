"""Core BTC paper bot: buys above the 50-day mean on closed daily bars, sells below, once per day."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from trading_intelligence.live import core_btc as C


class Feed:
    def __init__(self, closes: list[float], start: datetime) -> None:
        self.closes, self.start = closes, start

    def get_ohlcv(self, symbol, timeframe, limit=500):
        if timeframe == "1h":
            return pd.DataFrame({"close": [self.closes[-1]] * 2})
        idx = pd.date_range(self.start, periods=len(self.closes), freq="1D", tz="UTC")
        return pd.DataFrame({"close": self.closes}, index=idx).tail(limit)


def _now(feed: Feed) -> datetime:  # an hour into the day after the last bar: that bar is still forming
    return feed.start + timedelta(days=len(feed.closes) - 1, hours=1)


def test_buys_above_the_mean_once_per_day_and_sells_below(tmp_path):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    feed = Feed(list(np.linspace(100, 160, 60)) + [999.0], start)  # last bar forming: ignored by the signal
    sent: list[str] = []
    clock = {"now": _now(feed)}
    core = C.CoreBTC(feed, tmp_path / "p.json", 30.0, sent.append, clock=lambda: clock["now"])
    assert "COMPRO" in core.step()
    assert core.state["qty"] > 0 and core.state["cash"] == 0
    assert core.step() is None  # same closed day: nothing new
    feed.closes = feed.closes[:-1] + [100.0, 999.0]  # a crash closes below the 50-day mean
    clock["now"] += timedelta(days=1)
    msg = core.step()
    assert msg and "VENDO" in msg and core.state["qty"] == 0 and len(core.state["trades"]) == 2
    assert len(sent) == 2
    reloaded = C.CoreBTC(feed, tmp_path / "p.json", 30.0, sent.append, clock=lambda: clock["now"])
    assert reloaded.state["trades"] == core.state["trades"]


def test_stays_in_cash_below_the_mean_and_without_history(tmp_path):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    down = Feed(list(np.linspace(160, 100, 60)) + [100.0], start)
    core = C.CoreBTC(down, tmp_path / "a.json", 30.0, lambda m: None, clock=lambda: _now(down))
    assert core.step() is None and core.state["qty"] == 0
    short = Feed([100.0] * 20, start)
    core2 = C.CoreBTC(short, tmp_path / "b.json", 30.0, lambda m: None, clock=lambda: _now(short))
    assert core2.step() is None and core2.state["qty"] == 0


def test_summary_reports_the_paper_account(tmp_path):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    feed = Feed([100.0] * 61, start)
    core = C.CoreBTC(feed, tmp_path / "s.json", 30.0, lambda m: None, clock=lambda: _now(feed))
    assert "efectivo" in core.summary() and "30.00" in core.summary()


def test_the_two_mean_variant_needs_both_means(tmp_path):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # a long fall then a short rally: above the 50-day mean, still below the 200-day mean
    feed = Feed(list(np.linspace(200, 100, 180)) + list(np.linspace(100, 130, 40)) + [130.0], start)
    assert C.wants_long(C.closed_daily(feed.get_ohlcv("BTCUSDT", "1d"), _now(feed))) is True
    core = C.CoreBTC(feed, tmp_path / "v.json", 30.0, lambda m: None, clock=lambda: _now(feed), means=(50, 200))
    assert core.step() is None and core.state["qty"] == 0


class FakeSpot:
    """Binance Spot double: fills at the feed price, 0.1% fee in USDT, a STOP_LOSS that can be triggered."""

    def __init__(self, usdt: float = 1000.0) -> None:
        from decimal import Decimal

        from trading_intelligence.live.binance_live import SymbolRules

        self.D = Decimal
        self.px = Decimal("100")
        self.usdt, self.btc = Decimal(str(usdt)), Decimal("0")
        self.rules_ = SymbolRules(Decimal("0.00001"), Decimal("0.00001"), Decimal("5"), Decimal("0.01"), True)
        self.orders: list[tuple] = []
        self.stop: dict | None = None

    def unresolved(self):
        return []

    def reconcile(self, fee_price):
        return []

    def rules(self, symbol):
        return self.rules_

    def price(self, symbol):
        return self.px

    def free_balance(self, asset):
        return self.usdt if asset == "USDT" else (self.btc if not self.stop else self.D("0"))

    def _fill(self, side, qty, price):
        from trading_intelligence.live.binance_live import Fill

        quote = qty * price
        fee = quote * self.D("0.001")
        if side == "BUY":
            self.usdt -= quote + fee
            self.btc += qty
            return Fill("c", "BTCUSDT", side, "FILLED", qty, quote + fee, fee, price)
        self.usdt += quote - fee
        self.btc -= qty
        return Fill("c", "BTCUSDT", side, "FILLED", qty, quote - fee, fee, price)

    def market_order(self, symbol, side, qty, fee_price):
        assert not (side == "SELL" and self.stop), "the resting stop holds the BTC"
        self.orders.append((side, qty))
        return self._fill(side, qty, self.px)

    def place_stop(self, symbol, qty, stop):
        self.stop = {"qty": qty, "stop": stop, "fill": None}
        return "s1"

    def trigger_stop(self):
        self.stop["fill"] = self._fill("SELL", self.stop["qty"], self.stop["stop"])

    def stop_status(self, symbol, cid, fee_price):
        from trading_intelligence.live.binance_live import StopState

        if self.stop and self.stop["fill"]:
            fill, self.stop = self.stop["fill"], None
            return StopState("FILLED", fill)
        return StopState("NEW")

    def cancel_stop(self, symbol, cid, fee_price):
        from trading_intelligence.live.binance_live import StopState

        fill = self.stop["fill"] if self.stop else None
        self.stop = None
        return StopState("FILLED", fill) if fill else StopState("CANCELED")


def _limits():
    from decimal import Decimal

    from trading_intelligence.live.limits import OwnerLimits

    return OwnerLimits(Decimal("35"), Decimal("2"), Decimal("40"), 3, frozenset({"BTCUSDT"}))


def test_real_mode_buys_inside_the_owner_limits_with_a_guard_stop_and_sells_on_the_signal(tmp_path):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    feed = Feed(list(np.linspace(60, 100, 60)) + [999.0], start)
    spot, sent = FakeSpot(), []
    clock = {"now": _now(feed)}
    core = C.CoreBTC(feed, tmp_path / "r.json", 100.0, sent.append, clock=lambda: clock["now"],
                     trader=spot, limits=_limits())
    msg = core.step()
    assert msg and "DINERO REAL" in msg and "COMPRO" in msg and "stop de protección" in msg
    side, qty = spot.orders[0]
    assert side == "BUY" and float(qty) * 100 <= 40  # at most 40% of the 100 USDT session capital
    assert float(spot.stop["stop"]) == 85.0
    assert core.step() is None  # same day, stop resting: nothing to do
    feed.closes = feed.closes[:-1] + [50.0, 999.0]  # closes below its mean
    spot.px = spot.D("50")
    clock["now"] += timedelta(days=1)
    msg = core.step()
    assert msg and "VENDO" in msg and spot.stop is None and spot.orders[-1][0] == "SELL" and core.state["qty"] == 0


def test_real_mode_records_the_guard_stop_when_binance_sold(tmp_path):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    feed = Feed(list(np.linspace(60, 100, 60)) + [999.0], start)
    spot = FakeSpot()
    clock = {"now": _now(feed)}
    core = C.CoreBTC(feed, tmp_path / "g.json", 100.0, lambda m: None, clock=lambda: clock["now"],
                     trader=spot, limits=_limits())
    core.step()
    spot.trigger_stop()  # a crash while the PC was off
    clock["now"] += timedelta(hours=1)
    msg = core.step()
    assert msg and "stop de protección" in msg and core.state["qty"] == 0 and len(spot.orders) == 1
    assert core.state["trades"][-1]["why"] == "stop"


def test_real_mode_refuses_below_the_binance_minimum(tmp_path):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    feed = Feed(list(np.linspace(60, 100, 60)) + [999.0], start)
    spot = FakeSpot()
    core = C.CoreBTC(feed, tmp_path / "m.json", 10.0, lambda m: None, clock=lambda: _now(feed),
                     trader=spot, limits=_limits())
    msg = core.step()  # 40% of 10 USDT is under the 5 USDT minimum
    assert msg and "no compro" in msg and not spot.orders
