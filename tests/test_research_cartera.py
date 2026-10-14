"""Tests for research_cartera (synthetic curves, no network)."""
import numpy as np
import pytest

from trading_intelligence.backtesting import research_cartera as rc
from trading_intelligence.backtesting import research_ewmac as ew


def test_session_daily_samples_day_closes_and_stays_flat_after_an_early_end():
    curve = list(np.linspace(1000, 1300, 3 * rc.BARS_PER_DAY))
    d = rc.session_daily(curve, 3)
    assert d[0] == pytest.approx(curve[287] / 1000) and d[2] == pytest.approx(1.3)
    short = rc.session_daily(curve[:400], 3)  # the session stopped on day 2
    assert short[1] == short[2] == pytest.approx(curve[399] / 1000)


def test_portfolio_limits_and_rebalancing():
    desk = [np.linspace(1.01, 1.10, 30), np.linspace(0.99, 0.90, 30)]
    ewmac = ew.CAPITAL * np.r_[np.linspace(1.0, 0.95, 30), np.linspace(0.96, 1.10, 30)]
    all_desk, c1 = rc.portfolio(desk, ewmac, 1.0)
    assert np.allclose(all_desk, rc.chained(desk)) and c1 == 0
    all_ew, _ = rc.portfolio(desk, ewmac, 0.0)
    assert np.allclose(all_ew, ewmac / ew.CAPITAL)
    half, cost = rc.portfolio(desk, ewmac, 0.5)
    assert cost > 0  # the desk leg grew, the EWMAC leg shrank: money moves at the second session
    v1 = 0.5 * 1.10 + 0.5 * 0.95
    v1 -= abs(0.5 * 1.10 - 0.5 * v1) * rc.MOVE_COST
    assert half[29] == pytest.approx(0.5 * 1.10 + 0.5 * 0.95)
    assert half[-1] == pytest.approx(v1 * 0.5 * 0.90 + v1 * 0.5 * 1.10 / 0.95)


def test_stats_quarters_and_verdict():
    up = np.linspace(1.0, 1.2, 360)
    s = rc.curve_stats(up)
    assert s["net_pct"] == pytest.approx(20.0) and s["max_dd_pct"] == 0 and s["net_dd"] is None
    assert len(rc.quarters(up)) == 4
    rows = {"mesa de práctica": {"net_pct": 5, "max_dd_pct": 20, "net_dd": 0.25, "quarters": [1, 1, 1, 1]},
            "EWMAC": {"net_pct": 10, "max_dd_pct": 40, "net_dd": 0.25, "quarters": [1, 1, 1, 1]},
            "cartera 50/50": {"net_pct": 8, "max_dd_pct": 20, "net_dd": 0.4, "quarters": [1, 1, 1, 1]},
            "cartera 70/30": {"net_pct": 6, "max_dd_pct": 36, "net_dd": 0.17, "quarters": [1, 1, 1, 1]}}
    y = {"label": "y", "rows": rows, "btc_pct": 1.0, "corr": -0.1, "rebalance_cost_pct": {"50/50": 0.1, "70/30": 0.1}}
    y["judge"] = rc.judge(y)
    assert y["judge"]["50/50"] == {"beats_desk": True, "dd_ok": True}
    assert y["judge"]["70/30"] == {"beats_desk": False, "dd_ok": False}
    md = rc.render([y, y])
    assert "**Cartera 50/50 (mesa/EWMAC): pasa**" in md and "**Cartera 70/30 (mesa/EWMAC): no pasa**" in md
