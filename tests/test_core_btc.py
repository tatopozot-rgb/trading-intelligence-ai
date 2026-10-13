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
