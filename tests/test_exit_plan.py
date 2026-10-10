"""Stop and take profit read from the market at entry (owner, 2026-10-10)."""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.strategy.exit_plan import plan_exits


def _bars(closes, spread=0.002):
    idx = pd.date_range("2026-10-10", periods=len(closes), freq="1min", tz="UTC")
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c * (1 + spread), "low": c * (1 - spread), "close": c, "volume": 1.0},
                        index=idx)


def _walk(sigma, n=600, drift=0.0, seed=3):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(drift, sigma, n)))


def test_trend_lets_profit_run_and_range_takes_a_nearer_target():
    data = _bars(_walk(0.002))
    entry = Decimal(str(data["close"].iloc[-1]))
    trend = plan_exits(data, entry, kind="tendencia")
    rng = plan_exits(data, entry, kind="rango")
    assert trend.stop_pct == rng.stop_pct  # the same market gives the same stop...
    assert trend.target_pct > rng.target_pct  # ...but a trend aims farther than a range
    assert Decimal("1.2") <= trend.reward_risk <= Decimal("3")
    assert Decimal("0.6") <= rng.reward_risk <= Decimal("1.5")


def test_stop_goes_below_a_nearby_support_inside_the_owner_band():
    # quiet trading near 100, a slow dip to 95 (one hour) and a slow recovery to 100 (two hours)
    closes = [100.0] * 380 + list(np.linspace(100, 95, 60)) + list(np.linspace(95, 100, 120))
    data = _bars(closes, spread=0.0005)
    plan = plan_exits(data, Decimal("100"))
    assert plan.stop < Decimal("95") and Decimal("3") <= plan.stop_pct <= Decimal("15")
    assert "soporte" in plan.why


def test_not_always_the_same_numbers():
    """'a veces 15 de stop y 10 de profit, a veces 10 de stop y 15 de profit'."""
    calm, wild = _bars(_walk(0.0005)), _bars(_walk(0.012))
    a = plan_exits(calm, Decimal(str(calm["close"].iloc[-1])), kind="tendencia")
    b = plan_exits(wild, Decimal(str(wild["close"].iloc[-1])), kind="rango")
    assert (a.stop_pct, a.target_pct) != (b.stop_pct, b.target_pct)
    assert a.target_pct > a.stop_pct and b.target_pct <= b.stop_pct * Decimal("1.5")
    assert b.stop_pct <= Decimal("15")


def test_engine_stop_is_kept_and_sell_side_is_mirrored():
    data = _bars(_walk(0.002))
    entry = Decimal(str(data["close"].iloc[-1]))
    kept = plan_exits(data, entry, stop_price=entry * Decimal("0.95"), kind="tendencia")
    assert kept.stop == entry * Decimal("0.95") and kept.stop_pct == Decimal("5.00")
    short = plan_exits(data, entry, side="SELL", kind="rango")
    assert short.stop > entry > short.target
    with pytest.raises(ValueError):
        plan_exits(data, entry, side="HOLD")
