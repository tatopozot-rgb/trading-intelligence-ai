"""
PaperLoop: continuous PAPER operation on polled bars. The RiskEngine,
PaperAdapter and runner are real; only the market-data feed and the clock are
fakes. The feed, like Binance, also returns the still-forming bar.
"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tests.test_paper_runner import WARMUP, _flat, _paper, _risk, _router_for, _Scripted
from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.paper_loop import PaperLoop
from trading_intelligence.execution.paper_runner import EXIT_STOP, PaperTradingRunner

SYMBOL = "BTCUSDT"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def _frame(prices: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range(START.replace(tzinfo=None), periods=len(prices), freq="1h")  # naive, like Binance
    return pd.DataFrame(
        [{"open": o, "high": hi, "low": lo, "close": c, "volume": 1.0} for o, hi, lo, c in prices], index=idx,
    )


class FakeFeed(AbstractExchangeAdapter):
    """Returns every bar whose open time has passed, including the forming one."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames
        self.now = START
        self.fail = False
        self.calls = 0

    def get_ohlcv(self, symbol, timeframe, limit=500):
        self.calls += 1
        if self.fail:
            raise ConnectionError("feed down")
        frame = self.frames[symbol]
        return frame[frame.index <= pd.Timestamp(self.now.replace(tzinfo=None))].iloc[-limit:]

    def submit_order(self, order):
        raise AssertionError("the market-data feed must never receive an order")

    def cancel_order(self, client_order_id):
        raise AssertionError("not used")

    def get_position(self, symbol):
        return None

    def get_account_info(self):
        raise AssertionError("not used")

    def get_current_price(self, symbol):
        return Decimal("100")

    def is_connected(self):
        return not self.fail

    def get_exchange_name(self):
        return "fake_feed"


def _ts(i: int) -> str:
    return (START + i * HOUR).isoformat()


def _build(tmp_path: Path, feed: FakeFeed, *, entry_at: int = WARMUP + 1, symbols=(SYMBOL,), **kw) -> PaperLoop:
    runner = PaperTradingRunner(
        lambda sym: _router_for(_Scripted(entry_at=entry_at, stop_pct=0.05, symbol=sym)),
        _risk(tmp_path), _paper(tmp_path),
    )
    return PaperLoop(runner, feed, list(symbols), "1h", tmp_path / "loop.json", clock=lambda: feed.now, **kw)


def _at(feed: FakeFeed, hours: float) -> None:
    feed.now = START + timedelta(hours=hours)


@pytest.fixture
def flat_feed():
    return FakeFeed({SYMBOL: _frame(_flat(WARMUP + 20))})


class TestClosedBarsOnly:
    def test_the_forming_bar_is_never_processed(self, tmp_path, flat_feed):
        loop = _build(tmp_path, flat_feed)
        _at(flat_feed, WARMUP + 1)  # bar 60 just closed; bar 61 is forming and visible
        report = loop.tick()
        assert report.processed == [_ts(WARMUP)]
        assert report.actions == [f"{SYMBOL}@{_ts(WARMUP)}:ENTRY_SUBMITTED"]

    def test_a_first_run_starts_at_the_latest_closed_bar(self, tmp_path, flat_feed):
        loop = _build(tmp_path, flat_feed, entry_at=10**9)
        _at(flat_feed, WARMUP + 10.5)
        assert loop.tick().processed == [_ts(WARMUP + 9)], "history is context, not replayed as live"

    def test_polling_the_same_bar_twice_processes_it_once(self, tmp_path, flat_feed):
        loop = _build(tmp_path, flat_feed)
        _at(flat_feed, WARMUP + 1)
        loop.tick()
        steps = len(loop.runner.steps)
        _at(flat_feed, WARMUP + 1.5)
        assert loop.tick().processed == []
        assert len(loop.runner.steps) == steps

    def test_the_next_closed_bar_fills_the_entry(self, tmp_path, flat_feed):
        loop = _build(tmp_path, flat_feed)
        _at(flat_feed, WARMUP + 1)
        loop.tick()
        _at(flat_feed, WARMUP + 2)
        assert loop.tick().processed == [_ts(WARMUP + 1)]
        assert loop.runner.paper.get_position(SYMBOL) is not None


class TestCatchUpAfterAnOutage:
    def _crash_feed(self) -> FakeFeed:
        prices = _flat(WARMUP + 1) + _flat(2) + [(99.0, 99.5, 80.0, 82.0)] + _flat(10, 82.0)
        return FakeFeed({SYMBOL: _frame(prices)})  # the stop (95) is crossed on bar 63

    def test_missed_bars_are_replayed_in_order(self, tmp_path):
        feed = self._crash_feed()
        loop = _build(tmp_path, feed)
        _at(feed, WARMUP + 1)
        loop.tick()  # entry approved on bar 60
        _at(feed, WARMUP + 6)  # down for bars 61..65
        report = loop.tick()
        assert report.processed == [_ts(i) for i in range(WARMUP + 1, WARMUP + 6)]

    def test_a_stop_crossed_during_the_outage_exits_on_the_bar_it_was_crossed(self, tmp_path):
        feed = self._crash_feed()
        loop = _build(tmp_path, feed)
        _at(feed, WARMUP + 1)
        loop.tick()
        _at(feed, WARMUP + 6)
        loop.tick()
        trades = loop.runner.closed_trades
        assert [t.exit_reason for t in trades] == [EXIT_STOP]
        assert trades[0].closed_at == _ts(WARMUP + 3)
        assert abs(trades[0].exit_price - Decimal("95") * (1 - 2 * loop.runner.paper.slippage_rate)) < Decimal("0.01")

    def test_progress_survives_a_restart_and_resumes_where_it_stopped(self, tmp_path):
        feed = self._crash_feed()
        loop = _build(tmp_path, feed)
        _at(feed, WARMUP + 2)
        loop.tick()
        saved = json.loads((tmp_path / "loop.json").read_text())
        assert saved["last_processed"] == _ts(WARMUP + 1)

        restarted = _build(tmp_path, feed, entry_at=10**9)
        _at(feed, WARMUP + 5)
        assert restarted.tick().processed == [_ts(WARMUP + 2), _ts(WARMUP + 3), _ts(WARMUP + 4)]

    def test_an_outage_longer_than_the_fetched_history_trips_the_kill_switch(self, tmp_path, flat_feed):
        loop = _build(tmp_path, flat_feed, entry_at=10**9, fetch_limit=5)
        _at(flat_feed, WARMUP + 1)
        loop.tick()
        _at(flat_feed, WARMUP + 15)  # 14 bars missed, only 5 fetched
        report = loop.tick()
        assert report.gap_halt is not None
        risk = loop.runner.risk_engine
        assert risk.state.kill_switch is True
        assert "data gap" in risk.state.kill_switch_reason
        assert report.processed, "the bars that ARE available still get processed (exits keep working)"


class TestFeedFailures:
    def test_a_failed_fetch_processes_nothing_and_is_reported(self, tmp_path, flat_feed):
        loop = _build(tmp_path, flat_feed)
        _at(flat_feed, WARMUP + 1)
        flat_feed.fail = True
        report = loop.tick()
        assert report.processed == [] and report.fetch_error is not None
        assert loop.consecutive_fetch_errors == 1
        assert loop.runner.steps == []
        status = json.loads((tmp_path / "loop.json").read_text())["status"]
        assert status["consecutive_fetch_errors"] == 1

    def test_a_long_outage_trips_the_connectivity_kill_switch(self, tmp_path, flat_feed):
        loop = _build(tmp_path, flat_feed, entry_at=10**9)
        _at(flat_feed, WARMUP + 1)
        loop.tick()  # a successful fetch is recorded
        flat_feed.fail = True
        _at(flat_feed, WARMUP + 2)
        loop.tick()
        assert loop.runner.risk_engine.state.kill_switch is True
        assert "Connectivity" in loop.runner.risk_engine.state.kill_switch_reason

    def test_recovery_resets_the_error_count_and_catches_up(self, tmp_path, flat_feed):
        loop = _build(tmp_path, flat_feed, entry_at=10**9)
        _at(flat_feed, WARMUP + 1)
        loop.tick()
        flat_feed.fail = True
        _at(flat_feed, WARMUP + 1.01)
        loop.tick()
        flat_feed.fail = False
        _at(flat_feed, WARMUP + 3)
        report = loop.tick()
        assert loop.consecutive_fetch_errors == 0
        assert report.processed == [_ts(WARMUP + 1), _ts(WARMUP + 2)]


class TestPortfolio:
    def test_a_lagging_symbol_holds_the_timestamp_back_until_it_arrives(self, tmp_path):
        full = _frame(_flat(WARMUP + 5))
        feed = FakeFeed({"AAAUSDT": full, "BBBUSDT": full.iloc[: WARMUP + 1]})  # BBB lacks bars 61+
        loop = _build(tmp_path, feed, entry_at=10**9, symbols=("AAAUSDT", "BBBUSDT"))
        _at(feed, WARMUP + 3)
        assert loop.tick().processed == [_ts(WARMUP)]
        feed.frames["BBBUSDT"] = full
        assert loop.tick().processed == [_ts(WARMUP + 1), _ts(WARMUP + 2)]


class TestGuards:
    def test_refuses_anything_but_a_paper_adapter(self, tmp_path, flat_feed):
        runner = PaperTradingRunner(_router_for(_Scripted(entry_at=10**9)), _risk(tmp_path), _paper(tmp_path))
        runner.paper = object()  # type: ignore[assignment]
        with pytest.raises(TypeError, match="PAPER only"):
            PaperLoop(runner, flat_feed, [SYMBOL], "1h", tmp_path / "loop.json")

    def test_refuses_to_resume_a_state_file_written_for_another_setup(self, tmp_path, flat_feed):
        (tmp_path / "loop.json").write_text(json.dumps({"symbols": ["ETHUSDT"], "timeframe": "1h", "last_processed": None}))
        with pytest.raises(ValueError, match="refusing to resume"):
            _build(tmp_path, flat_feed)

    def test_rejects_an_unknown_timeframe(self, tmp_path, flat_feed):
        runner = PaperTradingRunner(_router_for(_Scripted(entry_at=10**9)), _risk(tmp_path), _paper(tmp_path))
        with pytest.raises(ValueError, match="timeframe"):
            PaperLoop(runner, flat_feed, [SYMBOL], "7m", tmp_path / "loop.json")


class TestRun:
    def test_run_polls_then_sleeps_until_just_after_the_next_close(self, tmp_path, flat_feed):
        slept: list[float] = []

        def fake_sleep(seconds: float) -> None:
            slept.append(seconds)
            flat_feed.now += timedelta(seconds=seconds)

        loop = _build(tmp_path, flat_feed, entry_at=10**9, sleep=fake_sleep, close_grace_seconds=5)
        _at(flat_feed, WARMUP + 1.25)
        assert loop.run(max_ticks=3) == 3
        assert slept[0] == pytest.approx(0.75 * 3600 + 5)
        assert loop.last_processed == START + (WARMUP + 2) * HOUR

    def test_a_stop_file_stops_the_loop_before_polling(self, tmp_path, flat_feed):
        stop = tmp_path / "STOP"
        stop.write_text("")
        loop = _build(tmp_path, flat_feed, stop_file=stop)
        assert loop.run(max_ticks=5) == 0
        assert flat_feed.calls == 0


def test_status_reports_what_an_operator_needs(tmp_path, flat_feed):
    loop = _build(tmp_path, flat_feed)
    _at(flat_feed, WARMUP + 1)
    loop.tick()
    status = json.loads((tmp_path / "loop.json").read_text())["status"]
    assert set(status) >= {"last_tick", "equity", "cash", "open_positions", "kill_switch", "books_disagree"}
    assert status["books_disagree"] == []
    assert Decimal(status["equity"]) == Decimal("10000")

