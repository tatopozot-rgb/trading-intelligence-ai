"""
Historical OHLCV downloader. Per docs/BINANCE_INTEGRATION_NOTES.md and
docs/SYSTEM_ARCHITECTURE.md: public Binance klines endpoint, no API key
needed. Caches to Parquet, never re-downloads a month already on disk.

Storage layout: data/historical/{symbol}/{interval}/{YYYY-MM}.parquet
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from trading_intelligence.execution.binance import BinanceSpotAdapter

logger = logging.getLogger(__name__)

MAX_KLINES_PER_REQUEST = 1000


class HistoricalDataDownloader:
    """
    Downloads and caches OHLCV data from Binance's public klines endpoint.
    Uses BinanceSpotAdapter for market data only — no credentials required.
    """

    def __init__(self, data_dir: Path, adapter: Optional[BinanceSpotAdapter] = None):
        self.data_dir = Path(data_dir)
        self.adapter = adapter or BinanceSpotAdapter()

    def _month_path(self, symbol: str, interval: str, year: int, month: int) -> Path:
        return self.data_dir / symbol / interval / f"{year:04d}-{month:02d}.parquet"

    def _month_range(self, year: int, month: int) -> tuple[datetime, datetime]:
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        end = (datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12
               else datetime(year, month + 1, 1, tzinfo=timezone.utc))
        return start, end

    def is_month_cached(self, symbol: str, interval: str, year: int, month: int) -> bool:
        return self._month_path(symbol, interval, year, month).exists()

    def load_month(self, symbol: str, interval: str, year: int, month: int) -> pd.DataFrame:
        path = self._month_path(symbol, interval, year, month)
        if not path.exists():
            raise FileNotFoundError(f"No cached data for {symbol}/{interval}/{year:04d}-{month:02d}")
        return pd.read_parquet(path)

    def download_month(
        self, symbol: str, interval: str, year: int, month: int, force: bool = False
    ) -> pd.DataFrame:
        """
        Downloads one calendar month of OHLCV data, caching to Parquet.
        Returns the cached DataFrame without re-downloading unless force=True.
        """
        if not force and self.is_month_cached(symbol, interval, year, month):
            logger.debug("Using cached %s/%s/%04d-%02d", symbol, interval, year, month)
            return self.load_month(symbol, interval, year, month)

        start, end = self._month_range(year, month)
        df = self._fetch_range(symbol, interval, start, end)

        path = self._month_path(symbol, interval, year, month)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        logger.info("Cached %d bars to %s", len(df), path)
        return df

    def download_range(
        self, symbol: str, interval: str, start: datetime, end: datetime, force: bool = False
    ) -> pd.DataFrame:
        """Downloads and concatenates all months overlapping [start, end)."""
        months = []
        cursor = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
        while cursor < end:
            months.append(self.download_month(symbol, interval, cursor.year, cursor.month, force=force))
            cursor = (datetime(cursor.year + 1, 1, 1, tzinfo=timezone.utc) if cursor.month == 12
                      else datetime(cursor.year, cursor.month + 1, 1, tzinfo=timezone.utc))
        if not months:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        combined = pd.concat(months).sort_index()
        combined = combined[~combined.index.duplicated(keep="first")]
        return combined[(combined.index >= start) & (combined.index <= end)]

    def _fetch_range(self, symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Paginates the public klines endpoint by close-time, per BINANCE_INTEGRATION_NOTES.md."""
        client = self.adapter._get_client()
        all_klines: list = []
        current_start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        while current_start_ms < end_ms:
            batch = client.get_klines(
                symbol=symbol, interval=interval,
                startTime=current_start_ms, limit=MAX_KLINES_PER_REQUEST,
            )
            if not batch:
                break
            all_klines.extend(batch)
            last_close_time = batch[-1][6]
            next_start = last_close_time + 1
            if next_start <= current_start_ms:
                break  # safety: avoid infinite loop if exchange returns no progress
            current_start_ms = next_start
            if len(batch) < MAX_KLINES_PER_REQUEST:
                break  # exhausted available data before reaching `end`

        return self._klines_to_dataframe(all_klines, end_ms)

    @staticmethod
    def _klines_to_dataframe(klines: list, end_ms: int) -> pd.DataFrame:
        if not klines:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(
            klines,
            columns=[
                "open_time", "open", "high", "low", "close", "volume", "close_time",
                "quote_asset_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
            ],
        )
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df = df.set_index("open_time")
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        df = df[df["close_time"] < end_ms][["open", "high", "low", "close", "volume"]]
        return df[~df.index.duplicated(keep="first")].sort_index()
