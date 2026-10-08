"""Tests for the real-data walk-forward harness — no network: a fake getter
stands in for data-api.binance.vision."""
import json
import urllib.parse
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import real_data_validation as rdv

HOUR = 3_600_000


def _fake_get(start_ms: int, n_bars: int, *, bad_at: int = -1, calls: list | None = None):
    """Serves n_bars 1h klines from start_ms, honoring startTime/endTime/limit."""

    def get(url: str, timeout: float) -> bytes:
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        if calls is not None:
            calls.append(q)
        t0, t1, limit = int(q["startTime"]), int(q["endTime"]), int(q["limit"])
        out = []
        for i in range(n_bars):
            t = start_ms + i * HOUR
            if t0 <= t <= t1 and len(out) < limit:
                price = 100.0 + i * 0.01
                high = price * (0.5 if i == bad_at else 1.01)
                out.append([t, str(price), str(high), str(price * 0.99), str(price), "5.0"])
        return json.dumps(out).encode()

    return get


START = datetime(2024, 1, 1, tzinfo=timezone.utc)
START_MS = int(START.timestamp() * 1000)


class TestFetchKlines:
    def test_paginates_across_requests_without_duplicates(self):
        calls: list = []
        end = datetime.fromtimestamp((START_MS + 2500 * HOUR) / 1000, tz=timezone.utc)
        df = rdv.fetch_klines("BTCUSDT", "1h", START, end, get=_fake_get(START_MS, 3000, calls=calls))
        assert len(df) == 2500
        assert len(calls) == 3  # 1000 + 1000 + 500
        assert df.index.is_monotonic_increasing and df.index.is_unique
        assert df.index[0] == pd.Timestamp(START)
        assert rdv.count_gaps(df, "1h") == 0

    def test_end_is_exclusive(self):
        end = datetime.fromtimestamp((START_MS + 10 * HOUR) / 1000, tz=timezone.utc)
        df = rdv.fetch_klines("BTCUSDT", "1h", START, end, get=_fake_get(START_MS, 50))
        assert len(df) == 10

    def test_impossible_kline_is_rejected_not_traded_on(self):
        end = datetime.fromtimestamp((START_MS + 20 * HOUR) / 1000, tz=timezone.utc)
        with pytest.raises(ValueError, match="impossible OHLC"):
            rdv.fetch_klines("BTCUSDT", "1h", START, end, get=_fake_get(START_MS, 20, bad_at=7))

    def test_no_data_raises(self):
        end = datetime.fromtimestamp((START_MS + 5 * HOUR) / 1000, tz=timezone.utc)
        with pytest.raises(ValueError, match="no klines"):
            rdv.fetch_klines("BTCUSDT", "1h", START, end, get=_fake_get(START_MS + 100 * HOUR, 5))


def test_count_gaps_detects_missing_bars():
    idx = pd.date_range("2024-01-01", periods=10, freq="1h", tz="UTC").delete([3, 4, 8])
    assert rdv.count_gaps(pd.DataFrame({"close": 1.0}, index=idx), "1h") == 2


@pytest.mark.parametrize("profile", rdv.PROFILES)
@pytest.mark.parametrize("timeframe", ["1h", "4h"])
def test_profiles_match_the_live_operator_exactly(profile, timeframe):
    """The harness must validate exactly what trading_intelligence/live/operator.py runs."""
    from trading_intelligence.live.operator import router_factory

    def shape(router):
        return sorted(
            (regime.value, type(s).__name__, s.symbol, s.strategy_id, sorted(s.params.items()), conf)
            for regime, (s, conf) in router._registry.items()
        )

    live = router_factory(profile, timeframe)("ETHUSDT")
    ours = rdv.profile_router(profile, "ETHUSDT", timeframe)
    assert shape(ours) == shape(live)


def _synthetic(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": close, "high": close * 1.005, "low": close * 0.995,
                         "close": close, "volume": 1.0}, index=idx)


def test_walk_forward_symbol_covers_second_half_in_five_folds():
    data = _synthetic(1000, 4)
    outcomes = rdv.walk_forward_symbol(data, lambda: rdv.profile_router("tendencia", "X", "1h"), history_bars=120)
    assert len(outcomes) == 5
    assert outcomes[0].fold.is_start == data.index[0]  # anchored
    assert outcomes[0].fold.oos_start == data.index[500]
    for a, b in zip(outcomes, outcomes[1:]):
        assert b.fold.oos_start > a.fold.oos_end  # non-overlapping
    summary = rdv.summarize_symbol("X", data, outcomes, "1h")
    assert summary["folds"] == 5 and summary["gaps"] == 0
    assert len(summary["oos_trade_returns"]) == len(summary["oos_trade_pnls"])


def _sym(name, returns, pnls, go=False):
    return {"symbol": name, "oos_trade_returns": returns, "oos_trade_pnls": pnls, "framework_go": go,
            "oos_fees": 1.0, "oos_max_dd_pct_by_fold": [-5.0], "buy_hold_oos_return": 0.1}


class TestPoolVerdict:
    def test_go_requires_every_criterion(self):
        rets = [0.02, 0.025, 0.018, 0.03, -0.005] * 8
        pnls = [r * 1000 for r in rets]
        pooled = rdv.pool_verdict([_sym("A", rets, pnls, go=True), _sym("B", rets, pnls, go=True)])
        assert pooled["go"] is True and pooled["reasons"] == []
        assert pooled["oos_trades"] == 80

    def test_negative_expectancy_is_no_go(self):
        rets = [-0.01, 0.005, -0.008, 0.002] * 20
        pooled = rdv.pool_verdict([_sym("A", rets, [r * 1000 for r in rets], go=True)])
        assert pooled["go"] is False
        assert any("profit factor" in r for r in pooled["reasons"])
        assert any("not significantly > 0" in r for r in pooled["reasons"])

    def test_too_few_trades_and_too_few_symbols_go(self):
        pooled = rdv.pool_verdict([_sym("A", [0.05] * 5, [50.0] * 5, go=False), _sym("B", [], [], go=False)])
        assert pooled["go"] is False
        assert any("OOS trades" in r for r in pooled["reasons"])
        assert any("symbols GO" in r for r in pooled["reasons"])

    def test_no_trades_at_all_is_a_clean_no_go(self):
        pooled = rdv.pool_verdict([_sym("A", [], [])])
        assert pooled["go"] is False and pooled["oos_trades"] == 0 and pooled["p_value"] == 1.0


def test_render_markdown_reports_label_and_every_symbol():
    syms = [dict(_sym("BTCUSDT", [0.01], [10.0]), bars=100, gaps=0, folds=5, folds_passing_is_gate=0)]
    md = rdv.render_markdown("tendencia", "4h", "2022-10-01", "2026-10-01", syms, rdv.pool_verdict(syms))
    assert "tendencia @ 4h — NO-GO" in md and "| BTCUSDT |" in md
