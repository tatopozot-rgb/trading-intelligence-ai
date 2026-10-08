"""
Tests for HistoricalDataDownloader. No real network calls — the Binance
client is mocked. Verifies caching, pagination, and no-credentials-needed
behavior (public klines endpoint per docs/BINANCE_INTEGRATION_NOTES.md).
"""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from trading_intelligence.data.downloader import HistoricalDataDownloader
from trading_intelligence.execution.binance import BinanceSpotAdapter


def _kline(open_time_ms: int, close_time_ms: int, close_price: float = 100.0) -> list:
    return [
        open_time_ms, "100.0", "101.0", "99.0", str(close_price), "10.0",
        close_time_ms, "1000.0", 5, "5.0", "500.0", "0",
    ]


class FakeClient:
    """Returns one page of klines per call, tracking pagination requests made."""

    def __init__(self, pages: list[list]):
        self.pages = list(pages)
        self.calls: list[dict] = []

    def get_klines(self, symbol, interval, startTime, limit):
        self.calls.append({"symbol": symbol, "interval": interval, "startTime": startTime, "limit": limit})
        if not self.pages:
            return []
        return self.pages.pop(0)


def _downloader(tmp_path: Path, pages: list[list]) -> tuple[HistoricalDataDownloader, FakeClient]:
    adapter = BinanceSpotAdapter()  # no credentials — public data only
    fake_client = FakeClient(pages)
    adapter._get_client = lambda: fake_client
    downloader = HistoricalDataDownloader(data_dir=tmp_path, adapter=adapter)
    return downloader, fake_client


class TestDownloadMonth:
    def test_downloads_and_caches(self, tmp_path):
        jan_start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        page = [_kline(jan_start + i * 3600_000, jan_start + (i + 1) * 3600_000 - 1) for i in range(5)]
        downloader, fake_client = _downloader(tmp_path, [page])

        df = downloader.download_month("BTCUSDT", "1h", 2024, 1)
        assert len(df) == 5
        assert downloader.is_month_cached("BTCUSDT", "1h", 2024, 1)

    def test_second_call_uses_cache_not_network(self, tmp_path):
        jan_start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        page = [_kline(jan_start, jan_start + 3600_000 - 1)]
        downloader, fake_client = _downloader(tmp_path, [page])

        downloader.download_month("BTCUSDT", "1h", 2024, 1)
        calls_after_first = len(fake_client.calls)
        downloader.download_month("BTCUSDT", "1h", 2024, 1)  # should hit cache
        assert len(fake_client.calls) == calls_after_first

    def test_force_redownloads(self, tmp_path):
        jan_start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        page1 = [_kline(jan_start, jan_start + 3600_000 - 1)]
        page2 = [_kline(jan_start, jan_start + 3600_000 - 1)]
        downloader, fake_client = _downloader(tmp_path, [page1, page2])

        downloader.download_month("BTCUSDT", "1h", 2024, 1)
        downloader.download_month("BTCUSDT", "1h", 2024, 1, force=True)
        assert len(fake_client.calls) == 2

    def test_no_credentials_needed(self, tmp_path):
        jan_start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        page = [_kline(jan_start, jan_start + 3600_000 - 1)]
        downloader, _ = _downloader(tmp_path, [page])
        assert downloader.adapter.has_credentials is False
        downloader.download_month("BTCUSDT", "1h", 2024, 1)  # should not raise

    def test_default_adapter_is_not_testnet(self, tmp_path):
        """Real bug found via a real BTCUSDT research run: with no adapter
        injected, the downloader used to build BinanceSpotAdapter() with
        its own default (testnet=True), silently returning sparse testnet
        history for a mainnet research request. The downloader must
        default to mainnet for its own adapter — testnet=True only makes
        sense for a trading adapter, not read-only historical downloads."""
        downloader = HistoricalDataDownloader(data_dir=tmp_path)
        assert downloader.adapter.testnet is False


class TestPagination:
    def test_paginates_by_close_time(self, tmp_path):
        """Exchange returns full pages (1000 bars) until exhausted — downloader
        must follow close_time+1 as the next startTime. Uses 1-minute bar
        spacing so 1000+ bars stay well within the month (unlike hourly
        spacing, where 1000 bars would span ~41 days past the boundary)."""
        jan_start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        bar_ms = 60_000  # 1 minute
        full_page = [_kline(jan_start + i * bar_ms, jan_start + (i + 1) * bar_ms - 1) for i in range(1000)]
        next_start = jan_start + 1000 * bar_ms
        partial_page = [_kline(next_start, next_start + bar_ms - 1)]
        downloader, fake_client = _downloader(tmp_path, [full_page, partial_page])

        df = downloader.download_month("BTCUSDT", "1m", 2024, 1)
        assert len(df) == 1001
        assert len(fake_client.calls) == 2
        assert fake_client.calls[1]["startTime"] == full_page[-1][6] + 1

    def test_empty_response_stops_pagination(self, tmp_path):
        downloader, fake_client = _downloader(tmp_path, [[]])
        df = downloader.download_month("BTCUSDT", "1h", 2024, 1)
        assert len(df) == 0
        assert len(fake_client.calls) == 1


class TestDataFrameShape:
    def test_columns_and_dtypes(self, tmp_path):
        jan_start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        page = [_kline(jan_start, jan_start + 3600_000 - 1, close_price=123.45)]
        downloader, _ = _downloader(tmp_path, [page])

        df = downloader.download_month("BTCUSDT", "1h", 2024, 1)
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.iloc[0]["close"] == 123.45
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_no_duplicate_bars(self, tmp_path):
        jan_start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        # Same bar returned twice (simulates an overlapping/retried page)
        page = [_kline(jan_start, jan_start + 3600_000 - 1), _kline(jan_start, jan_start + 3600_000 - 1)]
        downloader, _ = _downloader(tmp_path, [page])

        df = downloader.download_month("BTCUSDT", "1h", 2024, 1)
        assert len(df) == 1


class TestDownloadRange:
    def test_spans_multiple_months(self, tmp_path):
        """A narrow window straddling the Jan/Feb boundary — kept small so
        the real-vs-expected bar count stays under the sanity check's
        floor (this test isn't about bar density, just month-crossing and
        per-month caching)."""
        jan_bar = int(datetime(2024, 1, 31, 23, 0, tzinfo=timezone.utc).timestamp() * 1000)
        feb_bar = int(datetime(2024, 2, 1, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        jan_page = [_kline(jan_bar, jan_bar + 3600_000 - 1)]
        feb_page = [_kline(feb_bar, feb_bar + 3600_000 - 1)]
        downloader, _ = _downloader(tmp_path, [jan_page, feb_page])

        df = downloader.download_range(
            "BTCUSDT", "1h",
            start=datetime(2024, 1, 31, 23, 0, tzinfo=timezone.utc),
            end=datetime(2024, 2, 1, 1, 0, tzinfo=timezone.utc),
        )
        assert len(df) == 2
        assert downloader.is_month_cached("BTCUSDT", "1h", 2024, 1)
        assert downloader.is_month_cached("BTCUSDT", "1h", 2024, 2)

    def test_empty_range_returns_empty_frame(self, tmp_path):
        downloader, _ = _downloader(tmp_path, [])
        df = downloader.download_range(
            "BTCUSDT", "1h",
            start=datetime(2024, 1, 2, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, tzinfo=timezone.utc),  # end before start
        )
        assert len(df) == 0

    def test_sparse_result_over_large_range_raises(self, tmp_path):
        """Reproduces the real defect: a multi-year daily request that
        comes back with almost no bars (the testnet signature) must raise,
        not silently return garbage to a backtest."""
        jan_start = int(datetime(2019, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        day_ms = 86_400_000
        sparse_page = [_kline(jan_start + i * day_ms, jan_start + (i + 1) * day_ms - 1) for i in range(5)]
        downloader, _ = _downloader(tmp_path, [sparse_page])

        with pytest.raises(ValueError, match="testnet"):
            downloader.download_range(
                "BTCUSDT", "1d",
                start=datetime(2019, 1, 1, tzinfo=timezone.utc),
                end=datetime(2026, 9, 30, tzinfo=timezone.utc),
            )

    def test_short_recent_range_does_not_false_positive(self, tmp_path):
        """A genuinely short, recent range (below the 180-bar sanity
        threshold) returning all its bars must not be flagged."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        start_ms = int(start.timestamp() * 1000)
        day_ms = 86_400_000
        page = [_kline(start_ms + i * day_ms, start_ms + (i + 1) * day_ms - 1) for i in range(10)]
        downloader, _ = _downloader(tmp_path, [page])

        df = downloader.download_range("BTCUSDT", "1d", start=start, end=datetime(2024, 1, 11, tzinfo=timezone.utc))
        assert len(df) == 10

class TestBarCountSanityCheck:
    """Unit-level tests of the sanity check itself, isolated from pagination
    and caching — mirrors how WalkForwardFold's pure logic is tested apart
    from the full backtest pipeline in test_walk_forward.py."""

    def test_raises_on_extreme_shortfall_over_large_range(self, tmp_path):
        downloader, _ = _downloader(tmp_path, [])
        with pytest.raises(ValueError, match="testnet"):
            downloader._check_bar_count_sanity(
                "BTCUSDT", "1d",
                datetime(2019, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 9, 30, tzinfo=timezone.utc),
                actual_bars=28,  # the real defect's exact figure
            )

    def test_does_not_raise_on_legitimate_partial_coverage(self, tmp_path):
        """A symbol with a genuinely shorter real listing history than the
        requested window (here, ~26% of the naive expected count) is not
        the testnet signature and must not be flagged."""
        downloader, _ = _downloader(tmp_path, [])
        downloader._check_bar_count_sanity(
            "BTCUSDT", "1d",
            datetime(2019, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 9, 30, tzinfo=timezone.utc),
            actual_bars=730,  # ~26% of ~2830 expected — should not raise
        )

    def test_does_not_raise_below_the_large_range_floor(self, tmp_path):
        """A small requested range (below the 180-expected-bar floor)
        skips the check entirely, however few bars come back — a short
        range legitimately returning few bars is normal, not suspicious."""
        downloader, _ = _downloader(tmp_path, [])
        downloader._check_bar_count_sanity(
            "BTCUSDT", "1d",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 11, tzinfo=timezone.utc),
            actual_bars=1,
        )

    def test_unknown_interval_string_skips_check(self, tmp_path):
        downloader, _ = _downloader(tmp_path, [])
        downloader._check_bar_count_sanity(
            "BTCUSDT", "not-a-real-interval",
            datetime(2019, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 9, 30, tzinfo=timezone.utc),
            actual_bars=0,
        )


class TestLoadMonth:
    def test_raises_when_not_cached(self, tmp_path):
        downloader, _ = _downloader(tmp_path, [])
        with pytest.raises(FileNotFoundError):
            downloader.load_month("BTCUSDT", "1h", 2024, 1)
