"""Tests for the point-in-time top-30 rotation (no network: fake archive, synthetic bars)."""
import io
import zipfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_rotacion as rr
from trading_intelligence.backtesting import research_rotacion_pit as pit


def _zip(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", text)
    return buf.getvalue()


def test_parse_klines_with_and_without_header_and_microseconds():
    row_ms = "1704067200000,1,2,0.5,1.5,10,1704153599999,15,3,5,7,0"
    row_us = "1704153600000000,1.5,3,1,2,20,1704239999999999,40,3,5,7,0"
    header = "open_time,open,high,low,close,volume,close_time,quote_volume,count,tbv,tbqv,ignore"
    df = pit.parse_klines(_zip(header + "\n" + row_ms + "\n" + row_us + "\n"))
    assert list(df.index) == [pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2024-01-02", tz="UTC")]
    assert df["quote_volume"].tolist() == [15.0, 40.0] and df["close"].tolist() == [1.5, 2.0]
    assert len(pit.parse_klines(_zip(row_ms + "\n"))) == 1


def test_list_symbols_follows_pages_and_candidates_filter():
    pages = {
        "": "<ListBucketResult><Prefix>data/futures/um/monthly/klines/</Prefix><IsTruncated>true</IsTruncated>"
            "<NextMarker>data/futures/um/monthly/klines/ETHUSDT/</NextMarker>"
            "<CommonPrefixes><Prefix>data/futures/um/monthly/klines/BTCUSDT/</Prefix></CommonPrefixes>"
            "<CommonPrefixes><Prefix>data/futures/um/monthly/klines/ETHUSDT/</Prefix></CommonPrefixes>"
            "</ListBucketResult>",
        "data/futures/um/monthly/klines/ETHUSDT/":
            "<ListBucketResult><IsTruncated>false</IsTruncated>"
            "<CommonPrefixes><Prefix>data/futures/um/monthly/klines/USDCUSDT/</Prefix></CommonPrefixes>"
            "<CommonPrefixes><Prefix>data/futures/um/monthly/klines/BTCUSDT_250328/</Prefix></CommonPrefixes>"
            "<CommonPrefixes><Prefix>data/futures/um/monthly/klines/BTCDOMUSDT/</Prefix></CommonPrefixes>"
            "<CommonPrefixes><Prefix>data/futures/um/monthly/klines/ETHBTC/</Prefix></CommonPrefixes>"
            "<CommonPrefixes><Prefix>data/futures/um/monthly/klines/1000PEPEUSDT/</Prefix></CommonPrefixes>"
            "</ListBucketResult>"}

    def get(url):
        marker = url.split("marker=")[1].replace("%2F", "/")
        return pages[marker].encode()

    syms = pit.list_symbols(get)
    assert syms == ["1000PEPEUSDT", "BTCDOMUSDT", "BTCUSDT", "BTCUSDT_250328", "ETHBTC", "ETHUSDT", "USDCUSDT"]
    assert [s for s in syms if pit.is_candidate(s)] == ["1000PEPEUSDT", "BTCUSDT", "ETHUSDT"]


def test_fetch_um_uses_monthly_files_then_daily_files_for_the_current_month():
    asked = []

    def get(url):
        asked.append(url)
        return None

    pit.fetch_um("SOLUSDT", "1h", datetime(2026, 8, 15, tzinfo=timezone.utc), datetime(2026, 10, 3, tzinfo=timezone.utc),
                 get)
    assert asked[0].endswith("/monthly/klines/SOLUSDT/1h/SOLUSDT-1h-2026-08.zip")
    assert asked[1].endswith("/monthly/klines/SOLUSDT/1h/SOLUSDT-1h-2026-09.zip")
    assert [u.rsplit("-1h-", 1)[1] for u in asked[2:]] == ["2026-10-01.zip", "2026-10-02.zip"]


def test_daily_universe_is_point_in_time_and_needs_30_days():
    days = pd.date_range("2025-01-01", periods=80, freq="1D", tz="UTC")
    qv = pd.DataFrame({"A": 100.0, "B": 50.0, "C": 10.0}, index=days)
    qv.loc[days[:40], "C"] = np.nan  # listed on day 40
    qv.loc[days[45]:, "C"] = 1000.0  # then trades heavily
    u = pit.daily_universe(qv, top_n=2, days=30)
    assert not u.iloc[:30].any().any()  # 30 full days needed
    assert u.iloc[30].tolist() == [True, True, False]
    assert not u["C"].iloc[:70].any()  # listed on day 40: needs 30 full days before it counts
    assert u.iloc[70].tolist() == [True, False, True]  # then its volume puts it in, the same day it qualifies
    assert pit.daily_universe(qv, exclude=("A",), top_n=2, days=30).iloc[35].tolist() == [False, True, False]


def _market(n_days=200, symbols=("BTCUSDT", "AUSDT", "BUSDT", "CUSDT", "DUSDT", "EUSDT"), drifts=None):
    times = pd.date_range("2025-01-01", periods=n_days * 24, freq="1h", tz="UTC")
    rng = np.random.default_rng(1)
    bars = {}
    for s in symbols:
        close = 100 * np.cumprod(1 + (drifts or {}).get(s, 0.0) + rng.normal(0, 0.001, len(times)))
        open_ = np.r_[close[0], close[:-1]]
        bars[s] = pd.DataFrame({"open": open_, "high": np.maximum(open_, close), "low": np.minimum(open_, close),
                                "close": close}, index=times)
    return rr.build_market(bars, {}, times)


def test_rule_only_buys_coins_in_that_days_universe_and_sensitivity_drops_them():
    drifts = {"BTCUSDT": 0.0003, "AUSDT": 0.003, "BUSDT": 0.002, "CUSDT": 0.001, "DUSDT": 0.0005}
    m = _market(drifts=drifts)
    days = pd.date_range("2025-01-01", periods=200, freq="1D", tz="UTC")
    qv = pd.DataFrame({s: 100.0 for s in m.symbols}, index=days)
    qv["AUSDT"] = 1.0  # A is the strongest coin but never in the top 5 by volume
    u = pit.daily_universe(qv, top_n=5, days=30)
    wins = rr.windows(m, 30)
    assert len(wins) == 1
    curve, trades = pit.run_rule(m, pit.hourly_mask(u, m), wins)
    assert trades and "AUSDT" not in {t["key"] for t in trades}
    top = pit.top_contributors(trades)
    assert top and top[0] == "BUSDT"
    _, trades2 = pit.run_rule(m, pit.hourly_mask(pit.daily_universe(qv, exclude=tuple(top), top_n=5, days=30), m), wins)
    assert not set(top) & {t["key"] for t in trades2}


def test_full_quarters_and_pass_rules():
    days = pd.date_range("2025-01-01", "2025-12-31", freq="1D", tz="UTC")
    daily = pd.Series(1.0, index=days)
    daily[days >= pd.Timestamp("2025-04-01", tz="UTC")] = -1.0
    q = pit.full_quarters(daily.loc["2025-02-15":])
    assert set(q) == {"2025-T2", "2025-T3", "2025-T4"}  # T1 is only partly covered
    good = {"operaciones": 150, "neto_pct": 10.0, "neto_caida": 1.0}
    c = pit.passes(good, {"neto_caida": 0.5}, {"neto_pct": 2.0}, {"a": 1.0, "b": 1.0, "c": 1.0, "d": -1.0})
    assert c["pasa"] is True
    assert pit.passes(good, {"neto_caida": 0.5}, {"neto_pct": -2.0}, {"a": 1.0})["pasa"] is False
    assert pit.passes(good, {"neto_caida": 1.5}, {"neto_pct": 2.0}, {"a": 1.0})["pasa"] is False
    assert pit.passes(good, None, {"neto_pct": 2.0}, {"a": 1.0, "b": -1.0})["pasa"] is False


def test_evaluate_and_render_without_the_desk():
    m = _market(n_days=200, drifts={"BTCUSDT": 0.0002, "BUSDT": 0.001})
    days = pd.date_range("2025-01-01", periods=200, freq="1D", tz="UTC")
    qv = pd.DataFrame({s: 100.0 + k for k, s in enumerate(m.symbols)}, index=days)
    wins = rr.windows(m, 60)
    r = pit.evaluate(m, qv, wins, None, rr.buy_and_hold(m, wins), walk=False)
    assert set(r["criterios"]) >= {"pasa", "100_operaciones"}
    text = pit.render({"ciego": r})
    assert "Año ciego" in text and "Veredicto" in text
    assert r["regla"]["neto_pct"] == pytest.approx(r["regla"]["neto_usdt"] / 10, abs=0.01)
