"""Tests for the pre-registered two-way TSMOM study (docs/PREREG_TWO_WAY.md). No network."""
import io
import json
import math
import urllib.parse
import zipfile

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import two_way_momentum as tw

DAYS = pd.date_range("2019-01-01", periods=400, freq="1D", tz="UTC")


def _frames(paths: dict[str, np.ndarray]) -> tuple[pd.DataFrame, pd.DataFrame]:
    closes = pd.DataFrame(paths, index=DAYS[: len(next(iter(paths.values())))])
    opens = closes.shift(1).fillna(closes.iloc[0])  # 24/7 market: open = previous close
    return closes, opens


def _weeks(closes: pd.DataFrame) -> list[pd.Timestamp]:
    return [m for m in tw.mondays(str(closes.index[0].date()), str(closes.index[-1].date()))
            if tw.targets(closes, closes.shift(1), m, 1.0, 1.0)]


def _no_funding(cols) -> dict:
    return {c: pd.Series(0.0, index=DAYS) for c in cols}


def test_uptrend_goes_long_and_downtrend_goes_short_and_both_pay():
    rng = np.random.default_rng(0)
    up = 100 * np.cumprod(1 + 0.004 + rng.normal(0, 0.01, 400))
    down = 100 * np.cumprod(1 - 0.004 + rng.normal(0, 0.01, 400))
    closes, opens = _frames({"UP": up, "DOWN": down})
    res = tw.simulate_fold(closes, opens, _no_funding(closes), _weeks(closes), 1)
    assert res.total_return > 0 and not res.ruined
    assert sum(w.long_pnl for w in res.weeks) > 0 and sum(w.short_pnl for w in res.weeks) > 0
    assert sum(w.symbol_returns.get("DOWN", 0) for w in res.weeks) > 0


def test_weekly_pnl_adds_up_to_the_fold_result():
    rng = np.random.default_rng(3)
    a = 100 * np.cumprod(1 + rng.normal(0, 0.03, 400))
    closes, opens = _frames({"A": a})
    res = tw.simulate_fold(closes, opens, _no_funding(closes), _weeks(closes), 1)
    assert sum(w.pnl for w in res.weeks) == pytest.approx(res.total_return * tw.INITIAL_EQUITY)
    assert all(w.long_pnl + w.short_pnl == pytest.approx(w.pnl) for w in res.weeks)


def test_volatility_target_caps_size_at_one_times_allocation():
    calm = 100 * np.cumprod(np.full(400, 1.001))  # ~0 vol -> capped at 1x
    closes, opens = _frames({"CALM": calm})
    m = _weeks(closes)[0]
    assert tw.targets(closes, opens, m, 10_000, 1)["CALM"] == pytest.approx(10_000)
    assert tw.targets(closes, opens, m, 10_000, 3)["CALM"] == pytest.approx(30_000)
    rng = np.random.default_rng(1)
    wild = 100 * np.cumprod(1 + 0.002 + rng.normal(0, 0.06, 400))  # ~115% vol -> ~0.35x
    closes, opens = _frames({"WILD": wild})
    size = abs(tw.targets(closes, opens, _weeks(closes)[0], 10_000, 1)["WILD"])
    assert 2_000 < size < 6_000


def test_costs_and_funding_on_a_flat_market():
    flat = np.full(400, 100.0)
    flat[:200] = np.linspace(90, 100, 200)  # rising first so the signal is long, then flat
    closes, opens = _frames({"A": flat})
    weeks = [m for m in _weeks(closes) if m > DAYS[200]][:4]
    rate = pd.Series(0.0001 * 3, index=DAYS)  # 0.03%/day, positive: longs pay
    free = tw.simulate_fold(closes, opens, {"A": pd.Series(0.0, index=DAYS)}, weeks, 1)
    paid = tw.simulate_fold(closes, opens, {"A": rate}, weeks, 1)
    assert free.total_return < 0  # only the entry cost (0.10% of notional)
    assert paid.total_return < free.total_return
    assert paid.funding > 0


def test_fallback_funding_charges_both_sides():
    rng = np.random.default_rng(5)
    down = 100 * np.cumprod(1 - 0.004 + rng.normal(0, 0.01, 400))
    closes, opens = _frames({"D": down})
    weeks = _weeks(closes)
    nan_rates = {"D": pd.Series(np.nan, index=DAYS)}
    zero = tw.simulate_fold(closes, opens, _no_funding(["D"]), weeks, 1)
    fallback = tw.simulate_fold(closes, opens, nan_rates, weeks, 1)
    assert fallback.funding > 0 and fallback.total_return < zero.total_return


def test_daily_funding_buckets_events_into_the_day_they_charge():
    t = pd.to_datetime(["2020-01-01 08:00", "2020-01-01 16:00", "2020-01-02 00:00", "2020-01-02 08:00"], utc=True)
    rates = pd.Series([0.001, 0.002, 0.003, 0.004], index=t)
    days = pd.date_range("2019-12-31", "2020-01-02", freq="1D", tz="UTC")
    out = tw.daily_funding(rates, days)
    assert math.isnan(out.iloc[0])  # before the first real rate -> fallback
    assert out.iloc[1] == pytest.approx(0.006) and out.iloc[2] == pytest.approx(0.004)


def test_mondays():
    m = tw.mondays("2019-01-01", "2019-02-01")
    assert all(d.weekday() == 0 for d in m) and m[0] == pd.Timestamp("2019-01-07", tz="UTC")
    assert m[-1] + pd.Timedelta(days=7) <= pd.Timestamp("2019-02-01", tz="UTC")


def test_fetch_funding_paginates_fapi():
    def get(url, timeout):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        start = int(q["startTime"])
        base = 1_577_836_800_000  # 2020-01-01
        rows = [{"fundingTime": base + i * 28_800_000, "fundingRate": "0.0001"} for i in range(1500)]
        return json.dumps([r for r in rows if r["fundingTime"] >= start][:1000]).encode()
    rates, source = tw.fetch_funding("BTCUSDT", "2020-01-01", "2022-01-01", get=get)
    assert source == "fapi" and len(rates) == 1500


def test_fetch_funding_falls_back_to_vision_then_to_none():
    def zipped(lines):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("x.csv", "calc_time,funding_interval_hours,last_funding_rate\n" + "\n".join(lines))
        return buf.getvalue()

    def get(url, timeout):
        if "fapi" in url:
            raise OSError("451 restricted location")
        if url.endswith("2020-02.zip"):
            return zipped(["1580544000000,8,0.0002"])
        raise OSError("404")
    rates, source = tw.fetch_funding("BTCUSDT", "2020-01-01", "2020-04-01", get=get)
    assert source == "data.binance.vision" and list(rates) == [0.0002]

    def nothing(url, timeout):
        raise OSError("down")
    rates, source = tw.fetch_funding("PAXGUSDT", "2020-01-01", "2020-03-01", get=nothing)
    assert source == "fallback" and rates.empty


def _fold(rets):
    weeks = [tw.Week(pd.Timestamp("2020-01-06", tz="UTC"), r, r * 10_000, r * 10_000, 0.0, 10_000) for r in rets]
    return tw.FoldResult(weeks, -5.0, False, float(np.prod([1 + r for r in rets]) - 1), 0.0)


def test_verdict_rules():
    good = [0.02, 0.025, 0.018, 0.03, -0.005] * 2
    assert tw.verdict([_fold(good) for _ in range(5)])["outcome"] == "GO"
    bad = [-0.01, 0.005, -0.008, 0.002] * 2
    assert tw.verdict([_fold(bad) for _ in range(5)])["outcome"] == "NO-GO"
    noisy = [0.30, -0.25, 0.28, -0.27, 0.01] * 2
    assert tw.verdict([_fold(noisy) for _ in range(5)])["outcome"] == "INCONCLUSIVE"
    # significant but only 2/5 folds positive -> not GO
    mixed = [_fold(good)] * 2 + [_fold([0.001, -0.002] * 5)] * 3
    assert tw.verdict(mixed)["outcome"] != "GO"


def test_registration_constants():
    assert (tw.LOOKBACK_DAYS, tw.VOL_DAYS, tw.TARGET_VOL) == (28, 60, 0.40)
    assert (tw.FEE, tw.SLIPPAGE, tw.FALLBACK_RATE) == (0.0005, 0.0005, 0.0001)
    assert tw.PRIMARY == ("2019-01-01", "2022-10-01") and tw.LEVERAGES == (1, 2, 3)


def test_run_period_and_render():
    rng = np.random.default_rng(2)
    paths = {s: 100 * np.cumprod(1 + rng.normal(0, 0.03, 400)) for s in ("A", "B")}
    closes, opens = _frames(paths)
    res = tw.run_period(closes, opens, _no_funding(closes), "2019-01-01", "2020-02-01")
    assert len(res["fold_starts"]) == 5 and set(res["1x"]["per_symbol"]) <= {"A", "B"}
    md = tw.render("TEST", res, {"A": "fapi", "B": "fallback"})
    assert "| 3x |" in md and "| short |" in md and "fallback" in md
