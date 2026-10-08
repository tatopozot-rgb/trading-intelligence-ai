"""Offline acceptance checks for BinancePublicKlines' market-data validation.

Run: python -B test_binance_public_review.py <research-source-directory>
All payloads are synthetic; HTTP is injected and socket connections are blocked.
"""
from __future__ import annotations

import json
import socket
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(sys.argv.pop(1)).resolve()))
sys.dont_write_bytecode = True
from trading_intelligence.data.binance_public_feed import BinancePublicKlines  # noqa: E402


OPEN_MS = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


class PublicFeedAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        guard = patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK FORBIDDEN"))
        guard.start()
        self.addCleanup(guard.stop)

    def feed_for_kline(self, open_: str, high: str, low: str, close: str, volume: str = "1"):
        payload = json.dumps([[OPEN_MS, open_, high, low, close, volume]]).encode()
        return BinancePublicKlines(fetch=lambda url, timeout: payload)

    def test_valid_public_ohlcv_control(self) -> None:
        frame = self.feed_for_kline("100", "101", "99", "100", "2").get_ohlcv("BTCUSDT", "1h")
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["close"], 100.0)

    def test_nonfinite_or_physically_impossible_ohlcv_is_rejected(self) -> None:
        cases = [
            ("NaN open", "NaN", "101", "99", "100", "1"),
            ("Infinity high", "100", "Infinity", "99", "100", "1"),
            ("high below open and close", "100", "99", "98", "100", "1"),
            ("negative volume", "100", "101", "99", "100", "-1"),
        ]
        for label, open_, high, low, close, volume in cases:
            with self.subTest(label=label):
                with self.assertRaises(ValueError, msg=f"invalid public kline accepted: {label}"):
                    self.feed_for_kline(open_, high, low, close, volume).get_ohlcv("BTCUSDT", "1h")

    def test_nonfinite_or_nonpositive_ticker_price_is_rejected(self) -> None:
        for value in ("NaN", "Infinity", "0", "-1"):
            with self.subTest(price=value):
                payload = json.dumps({"symbol": "BTCUSDT", "price": value}).encode()
                feed = BinancePublicKlines(fetch=lambda url, timeout: payload)
                with self.assertRaises(ValueError, msg=f"invalid ticker price accepted: {value}"):
                    feed.get_current_price("BTCUSDT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
