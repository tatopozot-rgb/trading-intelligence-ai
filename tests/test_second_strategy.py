"""Tests for the second-strategy research (no network: synthetic bars)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import second_strategy as ss
from trading_intelligence.backtesting import two_way_backtest as tw


def _bars(n, seed=0, drift=0.0, start="2026-07-01"):
    idx = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + drift + rng.normal(0, 0.002, n))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.001,
                         "low": np.minimum(open_, close) * 0.999, "close": close, "volume": 100.0}, index=idx)


def _data(symbols=("BTCUSDT", "ETHUSDT"), n=12 * 24 * 6, **kw):
    bars = {s: _bars(n, seed=i, **kw) for i, s in enumerate(symbols)}
    times = next(iter(bars.values())).index
    return ss.Data(times, bars, {s: pd.Series(dtype=float) for s in symbols}, {s: pd.Series(dtype=float) for s in symbols})


def test_simulate_long_target_with_desk_sizing_and_fees():
    d = _data(("SOLUSDT",))
    i = 400
    entry = float(d.bars["SOLUSDT"]["open"].iloc[i])
    d.bars["SOLUSDT"].iloc[i + 1, d.bars["SOLUSDT"].columns.get_loc("high")] = entry * 1.10
    sig = ss.Signal(i, "SOLUSDT", "BUY", 0.5, entry * 0.95, entry * 1.05, i + 50)
    run = ss.simulate(d, [sig], 0, len(d.times))
    (t,) = run.trades
    assert t["why"] == "meta"
    risk = tw.RISK_MIN + (tw.RISK_MAX - tw.RISK_MIN) * 0.5
    qty = min(ss.CAPITAL * risk / (entry * 0.05), ss.CAPITAL * tw.MAX_POSITION / entry)
    expected = qty * entry * 0.05 - qty * entry * tw.FEE - qty * entry * 1.05 * tw.FEE
    assert t["pnl"] == pytest.approx(expected, rel=0.01)  # plus a small funding charge


def test_stop_beats_target_in_the_same_bar_and_time_exit():
    d = _data(("SOLUSDT",))
    i = 400
    entry = float(d.bars["SOLUSDT"]["open"].iloc[i])
    b = d.bars["SOLUSDT"]
    b.iloc[i + 2, b.columns.get_loc("high")] = entry * 1.2
    b.iloc[i + 2, b.columns.get_loc("low")] = entry * 0.8
    run = ss.simulate(d, [ss.Signal(i, "SOLUSDT", "BUY", 0.5, entry * 0.9, entry * 1.1, i + 50)], 0, len(d.times))
    assert run.trades[0]["why"] == "stop"
    run = ss.simulate(d, [ss.Signal(i, "SOLUSDT", "SELL", 0.5, entry * 1.5, None, i + 10)], 0, len(d.times))
    assert run.trades[0]["why"] == "tiempo" and run.trades[0]["exit_at"] == d.times[i + 10].isoformat()


def test_max_three_positions_and_entries_outside_the_window_ignored():
    syms = ("A", "B", "C", "D")
    d = _data(syms)
    sigs = [ss.Signal(300, s, "BUY", 0.0, float(d.bars[s]["open"].iloc[300]) * 0.5, None, 600) for s in syms]
    run = ss.simulate(d, sigs, 0, len(d.times))
    assert len(run.trades) == 3
    assert ss.simulate(d, sigs, 301, len(d.times)).trades == []


def test_ruptura_takes_one_trade_per_day_after_the_asia_range():
    d = _data()
    b = d.bars["BTCUSDT"]
    day = pd.Timestamp("2026-07-03", tz="UTC")
    asia_high = float(b.loc[day: day + pd.Timedelta(hours=7) - ss.BAR, "high"].max())
    t = day + pd.Timedelta(hours=8)
    b.loc[t:, ["open", "high", "low", "close"]] = asia_high * 1.02
    sigs = [s for s in ss.ruptura_signals(d, "opuesto", 1.5) if s.symbol == "BTCUSDT" and d.times[s.i].normalize() == day]
    assert len(sigs) == 1 and sigs[0].side == "BUY"
    assert d.times[sigs[0].i] == t + ss.BAR  # decided on the close, filled at the next open


def test_scout_signal_on_a_volume_spike_move():
    d = _data(("SOLUSDT",))
    b = d.bars["SOLUSDT"]
    i = 500
    b.iloc[i, b.columns.get_loc("volume")] = 1000.0
    b.iloc[i, b.columns.get_loc("close")] = b["open"].iloc[i - 2] * 1.03
    sigs = ss.scout_signals(d, move=1.5, vol=3.0, hours=1)
    assert any(s.i == i + 1 and s.side == "BUY" for s in sigs)


def test_funding_fades_the_crowd_only_when_top_traders_agree():
    d = _data(("SOLUSDT",))
    t = d.times[600]
    d.funding["SOLUSDT"] = pd.Series([0.05, 0.05], index=[t, d.times[900]])
    d.top["SOLUSDT"] = pd.Series([1.5, 0.8], index=[t - pd.Timedelta(minutes=5), d.times[899]])
    sigs = ss.funding_signals(d, theta=0.025, hours=8)
    assert [(s.i, s.side) for s in sigs] == [(600, "SELL")]  # the second one: top traders disagree


def test_evaluate_reports_insufficient_when_few_test_trades():
    d = _data(n=12 * 24 * 4)
    res = ss.evaluate(d)
    assert set(res["candidates"]) == {"funding", "ruptura", "scout"}
    for c in res["candidates"].values():
        if c["chosen"] is not None and c["test"]["trades"] < ss.MIN_TEST_TRADES:
            assert c["verdict"].startswith("insuficiente")
    assert "Segunda estrategia" in ss.render(res, {"desde": "a", "hasta": "b"})
