"""BinancePublicKlines: public market data only. No network: HTTP is a fake that
returns payloads in Binance's documented /api/v3/klines shape (12 fields, strings)."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.test_paper_runner import WARMUP
from trading_intelligence.data.binance_public_feed import BinancePublicKlines, MarketDataOnly
from trading_intelligence.execution.order_models import OrderRequest

START_MS = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
H_MS = 3_600_000


def _kline(i: int, price: float = 100.0) -> list:
    open_ms = START_MS + i * H_MS
    return [open_ms, f"{price:.8f}", f"{price * 1.001:.8f}", f"{price * 0.999:.8f}", f"{price:.8f}", "12.5",
            open_ms + H_MS - 1, "1250.0", 42, "6.0", "600.0", "0"]


class FakeHttp:
    def __init__(self, routes: dict):
        self.routes = routes
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> bytes:
        self.urls.append(url)
        for prefix, payload in self.routes.items():
            if prefix in url:
                if isinstance(payload, Exception):
                    raise payload
                return json.dumps(payload).encode()
        raise AssertionError(f"unexpected url {url}")


def test_klines_are_parsed_into_a_utc_ohlcv_frame():
    http = FakeHttp({"/api/v3/klines": [_kline(0), _kline(1, 101.0)]})
    frame = BinancePublicKlines(fetch=http).get_ohlcv("ETHUSDT", "1h", limit=2)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert str(frame.index.tz) == "UTC"
    assert frame.index[1] == datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
    assert frame["close"].iloc[1] == 101.0
    assert http.urls == ["https://data-api.binance.vision/api/v3/klines?symbol=ETHUSDT&interval=1h&limit=2"]


@pytest.mark.parametrize("symbol", ["BTC&interval=1m", "btcusdt", "", "A" * 30, "BTC/USDT"])
def test_a_malformed_symbol_never_reaches_the_url(symbol):
    http = FakeHttp({})
    with pytest.raises(ValueError, match="symbol"):
        BinancePublicKlines(fetch=http).get_ohlcv(symbol, "1h")
    assert http.urls == []


def test_bad_interval_and_limit_are_refused():
    feed = BinancePublicKlines(fetch=FakeHttp({}))
    with pytest.raises(ValueError, match="interval"):
        feed.get_ohlcv("BTCUSDT", "7m")
    with pytest.raises(ValueError, match="limit"):
        feed.get_ohlcv("BTCUSDT", "1h", limit=5000)


def test_only_https_hosts_are_accepted():
    with pytest.raises(ValueError, match="https"):
        BinancePublicKlines("http://data-api.binance.vision")


def test_an_exchange_error_payload_is_an_error_not_an_empty_frame():
    http = FakeHttp({"/api/v3/klines": {"code": -1121, "msg": "Invalid symbol."}})
    with pytest.raises(ValueError, match="unexpected klines payload"):
        BinancePublicKlines(fetch=http).get_ohlcv("ZZZUSDT", "1h")


def test_impossible_prices_are_rejected():
    broken = _kline(0)
    broken[2], broken[3] = "90.0", "110.0"  # high below low
    with pytest.raises(ValueError, match="impossible OHLC"):
        BinancePublicKlines(fetch=FakeHttp({"/api/v3/klines": [broken]})).get_ohlcv("BTCUSDT", "1h")


def test_price_and_connectivity():
    http = FakeHttp({"/api/v3/ticker/price": {"symbol": "BTCUSDT", "price": "64000.12"}, "/api/v3/ping": {}})
    feed = BinancePublicKlines(fetch=http)
    assert feed.get_current_price("BTCUSDT") == Decimal("64000.12")
    assert feed.is_connected() is True
    assert BinancePublicKlines(fetch=FakeHttp({"/api/v3/ping": ConnectionError("down")})).is_connected() is False


def test_it_can_never_trade_or_see_an_account():
    feed = BinancePublicKlines(fetch=FakeHttp({}))
    with pytest.raises(MarketDataOnly):
        feed.submit_order(OrderRequest("BTCUSDT", "BUY", "MARKET", Decimal("1")))
    with pytest.raises(MarketDataOnly):
        feed.cancel_order("x")
    with pytest.raises(MarketDataOnly):
        feed.get_account_info()
    with pytest.raises(MarketDataOnly):
        feed.get_position("BTCUSDT")


def test_paperloop_runs_end_to_end_on_the_public_feed(tmp_path, monkeypatch):
    """Through the real CLI wiring: real RiskEngine, PaperAdapter, default router."""
    from trading_intelligence.data import binance_public_feed
    from trading_intelligence.execution import paper_loop

    klines = {s: [_kline(i) for i in range(WARMUP + 2)] for s in ("BTCUSDT", "ETHUSDT")}  # last one is forming

    def fake_get(url: str, timeout: float) -> bytes:
        symbol = url.split("symbol=")[1].split("&")[0]
        return json.dumps(klines[symbol]).encode()

    monkeypatch.setattr(binance_public_feed, "_urllib_get", fake_get)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=WARMUP + 1, minutes=30)
    original = paper_loop.PaperLoop.__init__

    def init(self, *args, **kwargs):
        kwargs["clock"] = lambda: now
        original(self, *args, **kwargs)

    monkeypatch.setattr(paper_loop.PaperLoop, "__init__", init)
    assert paper_loop.main(["--symbols", "BTCUSDT", "ETHUSDT", "--timeframe", "1h",
                            "--state-dir", str(tmp_path / "live"), "--max-ticks", "1"]) == 0
    saved = json.loads((tmp_path / "live" / "loop.json").read_text())
    assert saved["last_processed"] == (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=WARMUP)).isoformat()
    assert saved["status"]["last_fetch_error"] is None
    assert saved["status"]["books_disagree"] == []


@pytest.mark.parametrize("label,o,h,lo,c,v", [
    ("NaN open", "NaN", "101", "99", "100", "1"),
    ("Infinity high", "100", "Infinity", "99", "100", "1"),
    ("high below open", "100", "99.5", "98", "99", "1"),
    ("low above close", "100", "101", "99.5", "99", "1"),
    ("negative volume", "100", "101", "99", "100", "-1"),
    ("zero price", "0", "101", "99", "100", "1"),
])
def test_a_bar_that_cannot_have_happened_is_an_error(label, o, h, lo, c, v):
    """GPT Work (PR #8): these used to be accepted as prices to trade on."""
    kline = [START_MS, o, h, lo, c, v, START_MS + H_MS - 1, "0", 0, "0", "0", "0"]
    with pytest.raises(ValueError):
        BinancePublicKlines(fetch=FakeHttp({"/api/v3/klines": [kline]})).get_ohlcv("BTCUSDT", "1h")


def test_zero_volume_bars_are_legitimate():
    kline = [START_MS, "100", "100", "100", "100", "0", START_MS + H_MS - 1, "0", 0, "0", "0", "0"]
    frame = BinancePublicKlines(fetch=FakeHttp({"/api/v3/klines": [kline]})).get_ohlcv("BTCUSDT", "1h")
    assert frame["volume"].iloc[0] == 0.0


@pytest.mark.parametrize("price", ["NaN", "Infinity", "0", "-1"])
def test_an_impossible_ticker_price_is_an_error(price):
    feed = BinancePublicKlines(fetch=FakeHttp({"/api/v3/ticker/price": {"symbol": "BTCUSDT", "price": price}}))
    with pytest.raises(ValueError, match="impossible price"):
        feed.get_current_price("BTCUSDT")


class Paged5m:
    """Binance /api/v3/klines at 5m: newest `limit` klines up to endTime, like the exchange."""

    def __init__(self, n: int):
        self.n, self.calls = n, []

    def __call__(self, url: str, timeout: float) -> bytes:
        from urllib.parse import parse_qs, urlparse

        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert q["interval"] == "5m"
        self.calls.append(q)
        five = 300_000
        rows = [[START_MS + i * five, f"{100 + i}", f"{100 + i + 0.5}", f"{100 + i - 0.5}", f"{100 + i + 0.25}", "1",
                 START_MS + (i + 1) * five - 1, "1", 1, "1", "1", "0"] for i in range(self.n)]
        if "endTime" in q:
            rows = [r for r in rows if r[0] <= int(q["endTime"])]
        return json.dumps(rows[-int(q["limit"]):]).encode()


def test_20m_bars_are_built_from_5m_klines_at_00_20_40():
    http = Paged5m(4 * 600 + 2)  # 600 full 20m bars plus a forming one with 2 klines
    frame = BinancePublicKlines(fetch=http).get_ohlcv("BTCUSDT", "20m", limit=500)
    assert len(frame) == 500 and len(http.calls) == 3 and "endTime" in http.calls[1]  # paged past 1000
    assert all(t.minute in (0, 20, 40) for t in frame.index)
    last_full = frame.iloc[-2]  # 20m bar n = 5m klines 4n..4n+3
    i = 4 * 599
    assert (last_full["open"], last_full["high"], last_full["low"], last_full["close"], last_full["volume"]) == (
        100 + i, 100 + i + 3 + 0.5, 100 + i - 0.5, 100 + i + 3 + 0.25, 4.0)
    assert frame.index[-1] - frame.index[-2] == timedelta(minutes=20)  # the forming bar is kept; PaperLoop drops it


def test_20m_runs_through_the_paper_loop_interval():
    from trading_intelligence.execution.paper_loop import INTERVAL_SECONDS

    assert INTERVAL_SECONDS["20m"] == 1200
    with pytest.raises(ValueError):
        BinancePublicKlines(fetch=Paged5m(1)).get_ohlcv("BTCUSDT", "7m")
