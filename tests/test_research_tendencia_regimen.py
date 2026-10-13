"""Tests for the BTC regime research (no network: synthetic hourly bars)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_tendencia as rt
from trading_intelligence.backtesting import research_tendencia_regimen as rr


def _bars(path):
    idx = pd.date_range("2025-01-01", periods=len(path), freq="1h", tz="UTC")
    close = np.asarray(path, dtype=float)
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close), "low": np.minimum(open_, close),
                         "close": close}, index=idx)


def test_signal_uses_only_closed_days():
    b = _bars(np.r_[np.full(24 * 10, 100.0), np.full(24 * 5, 120.0)])
    want = rr.regime_signal(b.index, b["close"], 3)
    i = 24 * 10  # the first hour at 120: its day has not closed yet
    assert want[i] == 0.0 and want[i + 24] == 1.0


def test_all_in_long_costs_and_exit_on_regime():
    b = _bars(np.full(100, 100.0))
    want = np.r_[np.zeros(10), np.ones(40), np.zeros(50)]
    run = rr.simulate(b, np.zeros(100), want, 0, 100)
    (t,) = run.trades
    assert t["why"] == "régimen" and t["exit_at"] == b.index[50].isoformat()
    buy, sell = 100 * (1 + rt.SLIP), 100 * (1 - rt.SLIP)
    qty = rt.CAPITAL / (buy * (1 + rt.FEE))
    assert t["pnl"] == pytest.approx((sell - buy) * qty - (buy + sell) * qty * rt.FEE)
    assert run.equity.iloc[-1] == pytest.approx(rt.CAPITAL + t["pnl"])


def test_trailing_stop_and_waits_for_a_fresh_cross():
    path = np.r_[np.full(10, 100.0), np.linspace(100, 150, 20), np.full(20, 140.0), np.full(50, 160.0)]
    b = _bars(path)
    b.iloc[35, b.columns.get_loc("low")] = 120.0  # 20% below the peak: stop
    want = np.r_[np.ones(60), np.zeros(10), np.ones(30)]
    run = rr.simulate(b, np.zeros(100), want, 0, 100, stop=0.10)
    assert [t["why"] for t in run.trades] == ["stop", "fin del periodo"]
    assert run.trades[0]["exit_at"] == b.index[35].isoformat()
    assert run.trades[1]["entry_at"] == str(b.index[70])  # not before the regime turned off and on again


def test_year_report_and_render():
    n = 24 * 400
    rng = np.random.default_rng(0)
    b = _bars(100 * np.cumprod(1 + rng.normal(0.0002, 0.004, n)))
    start = b.index[0] + pd.Timedelta(days=240)
    end = start + pd.Timedelta(days=120)
    desk = {"operaciones": 500, "neto_pct": -10.0, "max_caida_pct": 30.0, "neto_caida": -0.33,
            "trimestres": {"2025-T3": {"neto_pct": -10.0}}, "trimestres_positivos": 0}
    y = rr.year_report(b, np.zeros(n), start, end, desk)
    assert set(y["reglas"]) == set(rr.VARIANTS)
    report = rr.render([y])
    assert "btc_sma200_stop10" in report and "Veredicto" in report


def test_yearly_periods():
    assert rr.yearly("2020-10-12", "2022-10-12") == [("2020-10-12", "2021-10-12", ""), ("2021-10-12", "2022-10-12", "")]
    assert rr.yearly("2020-10-12", "2021-04-12") == [("2020-10-12", "2021-04-12", "")]
