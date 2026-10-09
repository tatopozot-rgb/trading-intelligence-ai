"""Tests for the pre-registered 4h short-side study (docs/PREREG_SHORT_4H.md). No network."""
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import short_side_validation as ssv
from trading_intelligence.backtesting.backtest_engine import BacktestEngine
from trading_intelligence.strategy.router import default_router


def _series(n: int, seed: int, drift: float = 0.0, start: str = "2024-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + drift + rng.normal(0, 0.012, n))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    idx = pd.date_range(start, periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": 1.0}, index=idx)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_long_mode_with_spot_costs_reproduces_backtest_engine_exactly(seed):
    """The loop is BacktestEngine's: same trades, prices, quantities and P&L."""
    data = _series(900, seed, drift=0.0004 * (seed - 2))
    engine = BacktestEngine(router=default_router("BTCUSDT", "4h"), history_bars=300).run(data)
    ours = ssv.simulate(data, "BTCUSDT", "long", fee=Decimal("0.001"), funding_rate=Decimal("0"), history_bars=300)
    assert len(engine.trades) > 0
    assert [(t.entry_time, t.entry_price, t.quantity, t.exit_time, t.exit_price, t.pnl) for t in engine.trades] == \
           [(t.entry_time, t.entry_price, t.quantity, t.exit_time, t.exit_price, t.pnl) for t in ours.trades]
    assert ours.equity_curve[-1] == pytest.approx(float(engine.final_equity))


def test_short_trades_appear_in_a_downtrend_with_stops_above_entry():
    data = _series(900, 11, drift=-0.0015)
    sim = ssv.simulate(data, "BTCUSDT", "short")
    assert sim.trades and all(t.side == "short" for t in sim.trades)
    assert all(t.stop_price > t.entry_price for t in sim.trades)
    assert all(t.funding > 0 for t in sim.trades if t.exit_time - t.entry_time >= pd.Timedelta("8h"))


def test_long_plus_short_never_holds_two_positions():
    data = _series(1200, 5)
    sim = ssv.simulate(data, "BTCUSDT", "long+short")
    for a, b in zip(sim.trades, sim.trades[1:]):
        assert b.entry_time >= a.exit_time


def test_short_pnl_and_funding_arithmetic():
    t = ssv.Trade("short", pd.Timestamp("2024-01-01 04:00", tz="UTC"), Decimal("100"), Decimal("2"),
                  Decimal("105"), Decimal("0.1"))
    t.exit_price, t.exit_fee, t.funding = Decimal("90"), Decimal("0.09"), Decimal("0.06")
    assert t.pnl == Decimal("20") - Decimal("0.25")


@pytest.mark.parametrize("entry,exit_,n", [
    ("2024-01-01 04:00", "2024-01-01 08:00", 1),   # boundary at exit counts
    ("2024-01-01 08:00", "2024-01-01 12:00", 0),   # boundary at entry does not
    ("2024-01-01 00:00", "2024-01-02 00:00", 3),
    ("2024-01-01 20:00", "2024-01-01 23:59", 0),
])
def test_funding_events(entry, exit_, n):
    assert ssv.funding_events(pd.Timestamp(entry, tz="UTC"), pd.Timestamp(exit_, tz="UTC")) == n


def test_verdict_rules():
    good = [0.02, 0.025, 0.018, 0.03, -0.005] * 8
    assert ssv.verdict(good, [r * 1000 for r in good])["outcome"] == "GO"
    bad = [-0.01, 0.005, -0.008, 0.002] * 10
    assert ssv.verdict(bad, [r * 1000 for r in bad])["outcome"] == "NO-GO"
    noisy = [0.30, -0.25, 0.28, -0.27, 0.01] * 8
    assert ssv.verdict(noisy, [r * 1000 for r in noisy])["outcome"] == "INCONCLUSIVE"
    assert ssv.verdict([0.05] * 5, [50.0] * 5)["outcome"] == "INCONCLUSIVE"


def test_registration_constants():
    assert (ssv.START, ssv.END, ssv.TIMEFRAME) == ("2022-10-01", "2026-10-01", "4h")
    assert ssv.FUTURES_FEE == Decimal("0.0005") and ssv.FUNDING_RATE == Decimal("0.0001")
    assert ssv.EXTRA_SYMBOLS == ("PAXGUSDT",)


def test_run_symbol_and_render():
    data = _series(1400, 9)
    out = ssv.run_symbol("BTCUSDT", data)
    assert set(out["modes"]) == set(ssv.MODES)
    assert len(out["modes"]["short"]["fold_trades"]) == 5
    md = ssv.render([out], {"PAXGUSDT": "first bar after start"})
    assert "| long+short |" in md and "PAXGUSDT" in md
