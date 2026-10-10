"""The real-data check of the futures engine, on synthetic bars (the real run is in GitHub Actions)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import two_way_backtest as B

END = datetime(2026, 10, 10, tzinfo=timezone.utc)


def _fetcher(drift):
    def fetch(symbol, interval, start, end):
        step = {"5m": "5min", "1h": "1h"}[interval]
        idx = pd.date_range(start, end, freq=step, inclusive="left")
        rng = np.random.default_rng(sum(map(ord, symbol)))
        wave = np.sin(np.arange(len(idx)) / 40) * 0.004
        c = 100 * np.exp(np.cumsum(rng.normal(drift.get(symbol, 0.0), 0.002, len(idx)) + wave / 10))
        return pd.DataFrame({"open": c, "high": c * 1.003, "low": c * 0.997, "close": c, "volume": 1.0}, index=idx)
    return fetch


def test_every_variant_is_measured_with_costs_and_written_down(tmp_path):
    out = B.run(2, ["SOLUSDT", "XRPUSDT"], 37.0, tmp_path, _fetcher({"SOLUSDT": 0.0004, "XRPUSDT": -0.0004}),
                end=END, warmup=200)
    assert [s["variante"] for s in out] == list(B.VARIANTS)
    for s in out:
        assert s["operaciones"] == s["por"]["BUY"]["operaciones"] + s["por"]["SELL"]["operaciones"]
        if s["operaciones"]:
            assert s["comisiones_usdt"] > 0
    report = (tmp_path / "2026-10-10.md").read_text()
    assert "Veredicto" in report and "aproximación" in report
    assert (tmp_path / "2026-10-10.json").exists()


def test_a_falling_market_is_traded_short():
    fetch = _fetcher({"SOLUSDT": -0.0008})
    m5 = fetch("SOLUSDT", "5m", datetime(2026, 10, 7, tzinfo=timezone.utc), END)
    h1 = fetch("SOLUSDT", "1h", datetime(2026, 10, 4, tzinfo=timezone.utc), END)
    res = B.simulate({"SOLUSDT": B.prepare(m5, h1, 200)}, "regimen", 37.0)
    sides = {t["side"] for t in res.trades}
    assert "SELL" in sides


def test_btc_does_not_fit_a_small_account():
    fetch = _fetcher({"BTCUSDT": 0.0008})
    m5 = fetch("BTCUSDT", "5m", datetime(2026, 10, 8, tzinfo=timezone.utc), END)
    h1 = fetch("BTCUSDT", "1h", datetime(2026, 10, 5, tzinfo=timezone.utc), END)
    res = B.simulate({"BTCUSDT": B.prepare(m5, h1, 200)}, "regimen", 37.0)
    assert not res.trades and res.skipped_minimum > 0  # 40% of 37 USDT < Binance's 100 USDT minimum
