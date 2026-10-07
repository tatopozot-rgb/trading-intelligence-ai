"""
PaperLoop: runs a PaperTradingRunner continuously on closed bars polled from a
market-data adapter. PAPER only: orders go to the runner's PaperAdapter, which
never forwards anything; the market-data adapter is only ever asked for
`get_ohlcv`.

What the loop guarantees (each has a test):
  * Only CLOSED bars are processed. Exchanges return the still-forming bar as
    the last kline; a bar is closed once `open_time + interval <= now`.
  * Polling the same closed bar twice processes it once (the loop tracks the
    last processed timestamp, and the runner's own chronology guard backs it up).
  * Bars missed while the loop was down are replayed IN ORDER, one timestamp at
    a time, so an order fills at the right bar's open and a stop crossed during
    the outage is honoured on the bar where it was crossed.
  * Progress is persisted after every processed timestamp (crash-safe resume).
  * If the outage is longer than the history the exchange still returns, the
    missed bars cannot be replayed: the loop activates the kill switch (blocks
    new entries; never closes positions) and says why. Fail closed.
  * A failed fetch processes nothing and is reported to the RiskEngine's
    connectivity watchdog (which trips the kill switch after
    `max_connectivity_gap_seconds` without a successful fetch, per the spec).
  * A first run with no saved progress starts at the latest closed bar; it does
    not replay history as if it were live.

Several symbols are processed on the timestamps they ALL have (like
`run_portfolio_replay`): a symbol whose newest bar is late holds the others
back until it arrives, so every decision sees the whole portfolio.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.paper import PaperAdapter
from trading_intelligence.execution.paper_runner import PaperTradingRunner

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200, "1d": 86400,
}


@dataclass
class TickReport:
    at: str
    processed: list[str] = field(default_factory=list)  # bar timestamps processed this tick, in order
    actions: list[str] = field(default_factory=list)  # "<symbol>@<bar>:<action>" for every runner step
    fetch_error: Optional[str] = None
    gap_halt: Optional[str] = None


class PaperLoop:
    def __init__(
        self,
        runner: PaperTradingRunner,
        market_data: AbstractExchangeAdapter,
        symbols: list[str],
        timeframe: str,
        state_path: Path,
        *,
        fetch_limit: Optional[int] = None,
        clock: Optional[Callable[[], datetime]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        close_grace_seconds: float = 5.0,
        stop_file: Optional[Path] = None,
    ):
        if not isinstance(runner.paper, PaperAdapter):
            raise TypeError("PaperLoop only drives a PaperAdapter (PAPER only)")
        if timeframe not in INTERVAL_SECONDS:
            raise ValueError(f"unsupported timeframe {timeframe!r}")
        if not symbols:
            raise ValueError("at least one symbol is required")
        self.runner = runner
        self.market_data = market_data
        self.symbols = sorted(set(symbols))
        self.timeframe = timeframe
        self.interval = timedelta(seconds=INTERVAL_SECONDS[timeframe])
        self.state_path = Path(state_path)
        # Exchanges cap a kline request (Binance: 1000). The extra bars beyond the
        # decision window are what lets an outage be replayed.
        self.fetch_limit = fetch_limit or min(1000, runner.history_bars + 200)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep or time.sleep
        self.close_grace = timedelta(seconds=close_grace_seconds)
        self.stop_file = Path(stop_file) if stop_file else None
        self.last_processed: Optional[datetime] = None
        self.consecutive_fetch_errors = 0
        self._load_state()

    # ------------------------------------------------------------------
    # One poll
    # ------------------------------------------------------------------

    def tick(self) -> TickReport:
        now = self.clock()
        report = TickReport(at=now.isoformat())
        frames = self._fetch_closed(now, report)
        risk = self.runner.risk_engine
        try:
            risk.check_connectivity(frames is not None, now=now)
        except Exception:
            logger.exception("RiskEngine connectivity watchdog failed")
        if frames is None:
            self._save_state(now, report)
            return report

        common = self._common_timestamps(frames)
        if self.last_processed is None:
            pending = common[-1:]  # first run: start now, do not replay history as live
        else:
            pending = [t for t in common if t > self.last_processed]
            expected_next = self.last_processed + self.interval
            if pending and pending[0] > expected_next:
                report.gap_halt = (
                    f"bars from {expected_next.isoformat()} to {(pending[0] - self.interval).isoformat()} "
                    f"are older than the fetched history and cannot be replayed"
                )
                logger.error("Unreplayable data gap: %s — activating kill switch", report.gap_halt)
                if not risk.state.kill_switch:
                    risk.activate_kill_switch(f"PaperLoop data gap: {report.gap_halt}")

        for ts in pending:
            window = {sym: frame.loc[:ts] for sym, frame in frames.items()}
            for step in self.runner.process_bars(window):
                report.actions.append(f"{step.symbol}@{step.bar_time}:{step.action}")
            self.last_processed = ts
            report.processed.append(ts.isoformat())
            self._save_state(now, report)  # progress survives a crash mid catch-up
        if not pending:
            self._save_state(now, report)
        return report

    def _fetch_closed(self, now: datetime, report: TickReport) -> Optional[dict[str, pd.DataFrame]]:
        frames: dict[str, pd.DataFrame] = {}
        try:
            for symbol in self.symbols:
                raw = self.market_data.get_ohlcv(symbol, self.timeframe, limit=self.fetch_limit)
                frames[symbol] = self._closed_only(raw, now)
        except Exception as exc:  # network, rate limit, malformed payload: process nothing
            self.consecutive_fetch_errors += 1
            report.fetch_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Market data fetch failed (%d in a row): %s",
                           self.consecutive_fetch_errors, report.fetch_error)
            return None
        self.consecutive_fetch_errors = 0
        return frames

    def _closed_only(self, raw: pd.DataFrame, now: datetime) -> pd.DataFrame:
        frame = raw.sort_index()
        frame = frame[~frame.index.duplicated(keep="last")]
        index = pd.DatetimeIndex(frame.index)
        frame.index = index.tz_localize(timezone.utc) if index.tz is None else index.tz_convert(timezone.utc)
        closes_at = frame.index + self.interval
        return frame[closes_at <= pd.Timestamp(now)]

    @staticmethod
    def _common_timestamps(frames: dict[str, pd.DataFrame]) -> list[datetime]:
        common: Optional[pd.DatetimeIndex] = None
        for frame in frames.values():
            idx = pd.DatetimeIndex(frame.index)
            common = idx if common is None else common.intersection(idx)
        if common is None:
            return []
        return [ts.to_pydatetime() for ts in common.sort_values()]

    # ------------------------------------------------------------------
    # Continuous run
    # ------------------------------------------------------------------

    def run(self, max_ticks: Optional[int] = None) -> int:
        """Poll until the stop file appears or `max_ticks` polls were made.
        Sleeps until just after the next bar is due to close. Returns the
        number of polls made."""
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            if self.stop_file is not None and self.stop_file.exists():
                logger.info("Stop file %s present — stopping", self.stop_file)
                break
            self.tick()
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            self.sleep(self.seconds_until_next_close())
        return ticks

    def seconds_until_next_close(self) -> float:
        now = self.clock()
        step = self.interval.total_seconds()
        epoch = now.timestamp()
        next_close = (int(epoch // step) + 1) * step
        return max(1.0, next_close - epoch + self.close_grace.total_seconds())

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        data = json.loads(self.state_path.read_text())
        if data.get("timeframe") not in (None, self.timeframe) or data.get("symbols") not in (None, self.symbols):
            raise ValueError(
                f"{self.state_path} was written for {data.get('symbols')} {data.get('timeframe')}; "
                f"refusing to resume as {self.symbols} {self.timeframe}"
            )
        last = data.get("last_processed")
        self.last_processed = datetime.fromisoformat(last) if last else None

    def _save_state(self, now: datetime, report: TickReport) -> None:
        paper, risk = self.runner.paper, self.runner.risk_engine
        status = {
            "last_tick": now.isoformat(),
            "equity": str(paper.last_known_equity()),
            "cash": str(paper.cash),
            "open_positions": sorted(paper.positions),
            "kill_switch": risk.state.kill_switch,
            "kill_switch_reason": risk.state.kill_switch_reason,
            "consecutive_fetch_errors": self.consecutive_fetch_errors,
            "last_fetch_error": report.fetch_error,
            "books_disagree": self.runner.reconcile(),
        }
        data = {
            "symbols": self.symbols,
            "timeframe": self.timeframe,
            "last_processed": self.last_processed.isoformat() if self.last_processed else None,
            "status": status,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.state_path)
