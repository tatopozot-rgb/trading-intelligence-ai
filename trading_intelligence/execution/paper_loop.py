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
from trading_intelligence.execution.paper_runner import PaperTradingRunner, RunnerStep

logger = logging.getLogger(__name__)

# Bounded history kept in the state file so the owner can see what the loop decided
# and why (the GitHub Actions summary renders it). Older entries are dropped.
JOURNAL_MAX = 300
TRADES_MAX = 200
EQUITY_HISTORY_MAX = 500

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
    stale_symbols: list[str] = field(default_factory=list)  # newest closed bar older than expected


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
        max_lag_bars: int = 1,
        fetch_attempts: int = 3,
        retry_backoff_seconds: float = 2.0,
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
        if max_lag_bars < 0 or fetch_attempts < 1:
            raise ValueError("max_lag_bars must be >= 0 and fetch_attempts >= 1")
        self.max_lag_bars = max_lag_bars
        self.fetch_attempts = fetch_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.last_processed: Optional[datetime] = None
        self.consecutive_fetch_errors = 0
        self.feed_origin = _feed_origin(market_data)
        self.journal: list[dict] = []
        self.trades: list[dict] = []
        self.equity_history: list[dict] = []
        self._trades_seen = len(runner.closed_trades)
        self._load_state()

    # ------------------------------------------------------------------
    # One poll
    # ------------------------------------------------------------------

    def tick(self) -> TickReport:
        now = self.clock()
        report = TickReport(at=now.isoformat())
        frames = self._fetch_closed(now, report)
        risk = self.runner.risk_engine
        if frames is not None:
            report.stale_symbols = self._stale_symbols(frames, now)
            if report.stale_symbols:
                logger.warning("Stale market data (newest closed bar more than %d bar(s) old): %s",
                               self.max_lag_bars, ", ".join(report.stale_symbols))
        try:
            # A feed that answers but serves old bars is not a working market view:
            # protective STOPs cannot see prices it does not deliver. Report it to the
            # connectivity watchdog exactly like a failed fetch.
            risk.check_connectivity(frames is not None and not report.stale_symbols, now=now)
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
            missing = self._missing_bars(self.last_processed, pending)
            if missing:
                # Any bar that should exist between what was processed and what is
                # about to be processed (before the first, or BETWEEN two of them) is a
                # bar whose stop crossing nobody saw. Found by GPT Work: only the first
                # gap used to be checked.
                report.gap_halt = (
                    f"{len(missing)} bar(s) missing and cannot be replayed, first {missing[0].isoformat()}"
                )
                logger.error("Unreplayable data gap: %s — activating kill switch", report.gap_halt)
                if not risk.state.kill_switch:
                    risk.activate_kill_switch(f"PaperLoop data gap: {report.gap_halt}")

        for ts in pending:
            window = {sym: frame[frame.index <= pd.Timestamp(ts)] for sym, frame in frames.items()}
            for step in self.runner.process_bars(window):
                report.actions.append(f"{step.symbol}@{step.bar_time}:{step.action}")
                self._journal_step(step, window.get(step.symbol))
            self._record_closed_trades()
            self.equity_history.append({"bar": ts.isoformat(), "equity": str(self.runner.paper.last_known_equity())})
            del self.equity_history[:-EQUITY_HISTORY_MAX]
            self.last_processed = ts
            report.processed.append(ts.isoformat())
            self._save_state(now, report)  # progress survives a crash mid catch-up
        if not pending:
            self._save_state(now, report)
        return report

    def _journal_step(self, step: RunnerStep, frame: Optional[pd.DataFrame]) -> None:
        close = None
        if frame is not None and not frame.empty:
            close = str(frame["close"].iloc[-1])
        self.journal.append({
            "bar": step.bar_time,
            "symbol": step.symbol,
            "action": step.action,
            "regime": step.regime,
            "close": close,
            "equity": str(step.equity) if step.equity is not None else None,
            "fills": [
                {"side": f.side, "status": f.status,
                 "qty": str(f.filled_quantity), "price": str(f.fill_price) if f.fill_price is not None else None,
                 "fee": str(f.fee)}
                for f in step.fills
            ],
            "notes": list(step.notes),
        })
        del self.journal[:-JOURNAL_MAX]

    def _record_closed_trades(self) -> None:
        for trade in self.runner.closed_trades[self._trades_seen:]:
            self.trades.append({
                "symbol": trade.symbol, "quantity": str(trade.quantity),
                "entry_price": str(trade.entry_price), "exit_price": str(trade.exit_price),
                "pnl": str(trade.pnl), "exit_reason": trade.exit_reason, "closed_at": trade.closed_at,
            })
        self._trades_seen = len(self.runner.closed_trades)
        del self.trades[:-TRADES_MAX]

    def _fetch_closed(self, now: datetime, report: TickReport) -> Optional[dict[str, pd.DataFrame]]:
        # Retried within the tick: with polls hours apart, one transient failure
        # would otherwise reach the connectivity watchdog as an hours-long outage.
        last_error: Optional[Exception] = None
        for attempt in range(self.fetch_attempts):
            if attempt:
                self.sleep(self.retry_backoff_seconds * 2 ** (attempt - 1))
            try:
                frames = {
                    symbol: self._closed_only(
                        self.market_data.get_ohlcv(symbol, self.timeframe, limit=self.fetch_limit), now,
                    )
                    for symbol in self.symbols
                }
            except Exception as exc:  # network, rate limit, malformed payload
                last_error = exc
                continue
            self.consecutive_fetch_errors = 0
            return frames
        self.consecutive_fetch_errors += 1
        report.fetch_error = f"{type(last_error).__name__}: {last_error}"
        logger.warning("Market data fetch failed after %d attempt(s) (%d tick(s) in a row): %s",
                       self.fetch_attempts, self.consecutive_fetch_errors, report.fetch_error)
        return None

    def _expected_last_closed(self, now: datetime) -> datetime:
        step = self.interval.total_seconds()
        return datetime.fromtimestamp((int(now.timestamp() // step) - 1) * step, tz=timezone.utc)

    def _stale_symbols(self, frames: dict[str, pd.DataFrame], now: datetime) -> list[str]:
        expected = self._expected_last_closed(now)
        oldest_ok = expected - self.max_lag_bars * self.interval
        stale = []
        for symbol, frame in frames.items():
            if frame.empty or frame.index.max().to_pydatetime() < oldest_ok:
                stale.append(symbol)
        return stale

    def _missing_bars(self, last: datetime, pending: list[datetime]) -> list[datetime]:
        missing: list[datetime] = []
        expected = last + self.interval
        for ts in pending:
            while expected < ts:
                missing.append(expected)
                expected += self.interval
            expected = ts + self.interval
        return missing

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
        saved_origin = data.get("feed_origin")
        if saved_origin is not None and saved_origin != self.feed_origin:
            # Found by GPT Work (PR #8): a state built on one feed (e.g. production
            # data) resumed on another (e.g. testnet) would mix two price histories.
            raise ValueError(
                f"{self.state_path} was built on feed origin {saved_origin!r}; "
                f"refusing to resume on {self.feed_origin!r}"
            )
        last = data.get("last_processed")
        self.last_processed = datetime.fromisoformat(last) if last else None
        self.journal = list(data.get("journal", []))
        self.trades = list(data.get("trades", []))
        self.equity_history = list(data.get("equity_history", []))

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
            "stale_symbols": report.stale_symbols,
            "last_gap_halt": report.gap_halt,
            "books_disagree": self.runner.reconcile(),
        }
        data = {
            "symbols": self.symbols,
            "timeframe": self.timeframe,
            "feed_origin": self.feed_origin,
            "last_processed": self.last_processed.isoformat() if self.last_processed else None,
            "status": status,
            "journal": self.journal,
            "trades": self.trades,
            "equity_history": self.equity_history,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.state_path)


def _feed_origin(market_data: object) -> str:
    """Where the bars come from: the host for URL-based feeds, else the adapter's
    own exchange name, else its class."""
    base_url = getattr(market_data, "base_url", None)
    if base_url:
        return str(base_url).rstrip("/")
    name = getattr(market_data, "get_exchange_name", None)
    if callable(name):
        try:
            return str(name())
        except Exception:
            pass
    return type(market_data).__name__


# ----------------------------------------------------------------------
# Command line: `python -m trading_intelligence.execution.paper_loop ...`
# ----------------------------------------------------------------------

def build_loop(
    symbols: list[str],
    timeframe: str,
    state_dir: Path,
    *,
    market_data: AbstractExchangeAdapter,
    paper_equity: str = "10000",
    risk_overrides: Optional[dict] = None,
    trailing_stop_pct: Optional[float] = None,
    stop_file: Optional[Path] = None,
) -> PaperLoop:
    """Wires the real RiskEngine, PaperAdapter and the default router (per symbol,
    at this timeframe) into a PaperLoop whose state lives in `state_dir`.
    `risk_overrides` must come from a file the owner controls; without it the
    RiskEngine uses the spec defaults."""
    from decimal import Decimal

    from trading_intelligence.persistence.audit_log import AuditLog
    from trading_intelligence.risk.engine import RiskEngine
    from trading_intelligence.risk.models import RiskConfig
    from trading_intelligence.strategy.router import default_router

    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    risk = RiskEngine(RiskConfig(**(risk_overrides or {})), state_dir / "risk.json", AuditLog(state_dir / "audit"))
    paper = PaperAdapter(market_data, Decimal(paper_equity), state_dir / "paper.json")
    runner = PaperTradingRunner(
        lambda sym: default_router(sym, timeframe), risk, paper, trailing_stop_pct=trailing_stop_pct,
        state_path=state_dir / "runner.json",
    )
    return PaperLoop(runner, market_data, symbols, timeframe, state_dir / "loop.json", stop_file=stop_file)


def _binance_market_data(allow_testnet_data: bool) -> AbstractExchangeAdapter:
    """Public Binance klines only. Credentials are cleared so no signed endpoint
    can be reached from here, and testnet data (which an environment variable
    can silently force) is refused unless explicitly allowed."""
    from trading_intelligence.execution.binance import BinanceSpotAdapter

    adapter = BinanceSpotAdapter(testnet=False)
    adapter.api_key = None
    adapter.secret_key = None
    if adapter.testnet and not allow_testnet_data:
        raise SystemExit(
            "Refusing to run on Binance TESTNET market data (BINANCE_TESTNET forces it). "
            "Unset it, or pass --allow-testnet-data if that is really intended."
        )
    return adapter


def main(argv: Optional[list[str]] = None, market_data: Optional[AbstractExchangeAdapter] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the research pipeline continuously in PAPER mode.")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--timeframe", required=True, choices=sorted(INTERVAL_SECONDS))
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--paper-equity", default="10000", help="simulated starting equity (PAPER only)")
    parser.add_argument("--risk-config", type=Path, help="JSON file of RiskConfig overrides chosen by the owner")
    parser.add_argument("--trailing-stop-pct", type=float, help="opt-in trailing stop, e.g. 0.10")
    parser.add_argument("--max-ticks", type=int, help="stop after this many polls (default: run until stopped)")
    parser.add_argument("--stop-file", type=Path, help="the loop stops before its next poll if this file exists")
    parser.add_argument("--feed", choices=["binance-public", "binance"], default="binance-public",
                        help="binance-public: public market-data host, no account, no keys, no extra "
                             "dependency (default); binance: python-binance client")
    parser.add_argument("--feed-url", default=None, help="override the binance-public host (https only)")
    parser.add_argument("--allow-testnet-data", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    overrides = json.loads(args.risk_config.read_text()) if args.risk_config else None
    if market_data is not None:
        feed = market_data
    elif args.feed == "binance-public":
        from trading_intelligence.data.binance_public_feed import DEFAULT_BASE_URL, BinancePublicKlines

        feed = BinancePublicKlines(args.feed_url or DEFAULT_BASE_URL)
    else:
        feed = _binance_market_data(args.allow_testnet_data)
    loop = build_loop(
        args.symbols, args.timeframe, args.state_dir, market_data=feed, paper_equity=args.paper_equity,
        risk_overrides=overrides, trailing_stop_pct=args.trailing_stop_pct,
        stop_file=args.stop_file or args.state_dir / "STOP",
    )
    ticks = loop.run(max_ticks=args.max_ticks)
    logger.info("PaperLoop stopped after %d polls; state in %s", ticks, args.state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
