"""Tests for research_deflactado (synthetic numbers, no network)."""
import numpy as np
import pandas as pd
import pytest
from scipy import stats as st

from trading_intelligence.backtesting import research_deflactado as rd


def test_expected_max_sharpe_matches_the_paper():
    assert rd.expected_max_sr(1, 1.0) == 0.0
    assert rd.expected_max_sr(1000, 1.0) == pytest.approx(3.26, abs=0.01)  # Bailey and López de Prado (2014)
    assert rd.expected_max_sr(100, 4.0) == pytest.approx(2 * rd.expected_max_sr(100, 1.0))


def test_deflated_sharpe_is_the_probabilistic_sharpe_with_one_test_and_falls_with_more():
    sr, t = 0.1, 250
    psr = st.norm.cdf(sr * np.sqrt(t - 1) / np.sqrt(1 + (3 - 1) / 4 * sr ** 2))
    assert rd.deflated_sharpe(sr, t, 0.0, 3.0, 1, 1 / t) == pytest.approx(psr)
    assert rd.deflated_sharpe(sr, t, 0.0, 3.0, 40, 1 / t) < rd.deflated_sharpe(sr, t, 0.0, 3.0, 10, 1 / t) < psr
    assert rd.deflated_sharpe(sr, t, -1.0, 8.0, 1, 1 / t) < psr  # fat left tail lowers confidence


def test_daily_returns_take_the_last_mark_of_each_day():
    idx = pd.date_range("2026-01-05", periods=48, freq="h", tz="UTC")
    eq = [1000.0] * 24 + [1010.0] * 24
    r = rd.daily_returns(eq, idx)
    assert list(r.round(6)) == [0.0, 0.01]


def test_evaluate_uses_the_gold_london_row_and_lists_all_cases():
    rng = np.random.default_rng(0)
    table = {f"x{k}": rd.moments(pd.Series(rng.normal(0.001 * k, 0.01, 250))) for k in range(5)}
    table["oro · londres"] = rd.moments(pd.Series(rng.normal(0.002, 0.01, 250)))
    res = rd.evaluate(table, 40, 20)
    assert [c["N"] for c in res["cases"]] == [1, 20, 20, 40, 40]
    assert res["cases"][0]["dsr"] > res["cases"][3]["dsr"]
    assert "Sharpe deflactado" in rd.render(res, table)
