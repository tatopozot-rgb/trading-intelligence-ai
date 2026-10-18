"""Tests for research_supertrend (synthetic candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_supertrend as rs


def _frame(close, start="2025-01-01", spread=0.004):
    idx = pd.date_range(start, periods=len(close), freq="h", tz="UTC")
    c = np.asarray(close, float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * (1 + spread), "low": np.minimum(o, c) * (1 - spread),
                         "close": c, "volume": 1.0}, index=idx)


def _reference(df, multiplier, period):
    """The strategy's supertrend() transcribed with pandas, as in freqtrade-strategies b8a90be."""
    df = df.copy()
    prev = df["close"].shift(1)
    df["TR"] = np.nan
    df.loc[df.index[1:], "TR"] = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(),
                                           (df["low"] - prev).abs()], axis=1).max(axis=1).iloc[1:]
    df["ATR"] = df["TR"].rolling(period).mean()
    bub = ((df["high"] + df["low"]) / 2 + multiplier * df["ATR"]).to_numpy()
    blb = ((df["high"] + df["low"]) / 2 - multiplier * df["ATR"]).to_numpy()
    close = df["close"].to_numpy()
    fub, flb, st = np.zeros(len(df)), np.zeros(len(df)), np.zeros(len(df))
    for i in range(period, len(df)):
        fub[i] = bub[i] if bub[i] < fub[i - 1] or close[i - 1] > fub[i - 1] else fub[i - 1]
        flb[i] = blb[i] if blb[i] > flb[i - 1] or close[i - 1] < flb[i - 1] else flb[i - 1]
    for i in range(period, len(df)):
        st[i] = (fub[i] if st[i - 1] == fub[i - 1] and close[i] <= fub[i]
                 else flb[i] if st[i - 1] == fub[i - 1] and close[i] > fub[i]
                 else flb[i] if st[i - 1] == flb[i - 1] and close[i] >= flb[i]
                 else fub[i] if st[i - 1] == flb[i - 1] and close[i] < flb[i]
                 else 0.00)
    stx = np.where(st > 0.00, np.where(close < st, "down", "up"), None)
    return stx


def test_supertrend_matches_the_strategy_code():
    rng = np.random.default_rng(3)
    f = _frame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 600))))
    h, lo, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    for m, p in rs.BUY + rs.SELL:
        ours = rs.supertrend(h, lo, c, m, p)
        ref = _reference(f, m, p)
        want = np.where(ref == "up", 1, np.where(ref == "down", -1, 0))
        assert (ours == want).all()


def test_roi_table_by_age():
    assert rs.roi_at(0) == 0.10 and rs.roi_at(1) == 0.05 and rs.roi_at(2) == 0.025 and rs.roi_at(50) == 0.025


def _sig(n, long_at=None, short_at=None, exit_long_from=None):
    z = np.zeros(n, bool)
    el, es, xl, xs = z.copy(), z.copy(), z.copy(), z.copy()
    if long_at is not None:
        el[long_at] = True
    if short_at is not None:
        es[short_at] = True
    if exit_long_from is not None:
        xl[exit_long_from:] = True
    return rs.Signals(el, es, xl, xs)


def test_long_takes_the_roi_target_with_costs():
    c = [100.0] * 5 + [100.0, 103.0, 106.0, 106.0, 106.0]
    f = _frame(c, spread=0.0)
    book, eq = rs.simulate(f, _sig(len(c), long_at=4), 1, len(c), 1000.0, False)
    t = book.trades[0]
    assert t["why"] == "roi" and t["side"] == 1
    fill = 100.0 * (1 + rs.SLIP)
    # age 1 at the 103 candle: 5% target not reached; age 2 opens at 103, past the 2.5% target: fills at the open
    qty = 1000.0 / (fill * (1 + rs.FEE))
    exit_fill = 103.0 * (1 - rs.SLIP)
    expect = 1000.0 - rs.FEE * qty * fill + qty * (exit_fill - fill) - rs.FEE * qty * exit_fill
    assert eq[-1] == pytest.approx(expect)


def test_stop_fills_at_the_open_when_it_gaps_past():
    c = [100.0] * 6 + [60.0, 60.0]
    f = _frame(c, spread=0.0)
    f.loc[f.index[6], "open"] = 60.0  # gaps past the -26.5% stop
    book, _ = rs.simulate(f, _sig(len(c), long_at=4), 1, len(c), 1000.0, False)
    assert book.trades[0]["why"] == "stop"
    assert book.trades[0]["ret_pct"] < -39


def test_exit_signal_closes_at_the_next_open_and_short_mirrors():
    c = [100.0] * 10
    f = _frame(c, spread=0.0)
    book, _ = rs.simulate(f, _sig(10, long_at=3, exit_long_from=6), 1, 10, 1000.0, False)
    assert [t["why"] for t in book.trades] == ["señal"] and book.trades[0]["out"] == str(f.index[7])
    book, _ = rs.simulate(_frame([100.0, 100, 100, 100, 95, 90, 90, 90], spread=0.0),
                          _sig(8, short_at=2), 1, 8, 1000.0, False)
    assert book.trades[0]["side"] == -1 and book.trades[0]["why"] == "roi"


def test_brakes_block_shorts_events_and_close_longs_when_the_gate_shuts():
    n = 10
    f = _frame([100.0] * n, spread=0.0)
    off = np.ones(n)
    book, _ = rs.simulate(f, _sig(n, short_at=3), 1, n, 1000.0, True, gate=off, events=np.zeros(n, bool))
    assert book.trades == []
    ev = np.zeros(n, bool)
    ev[4] = True
    book, _ = rs.simulate(f, _sig(n, long_at=3), 1, n, 1000.0, True, gate=off, events=ev)
    assert book.trades == []


def test_brakes_size_by_desk_risk(monkeypatch):
    n = 12
    f = _frame([100.0] * n, spread=0.0)
    monkeypatch.setattr(rs, "desk_stop", lambda f, j, px, side: px * 0.95)
    gate = np.ones(n)
    gate[8:] = -1
    book, eq = rs.simulate(f, _sig(n, long_at=3), 1, n, 1000.0, True, gate=gate, events=np.zeros(n, bool))
    assert book.trades[0]["why"] == "régimen" and book.trades[0]["out"] == str(f.index[8])
    # 2% risk over a ~5% stop: about 40% of capital, so the costs are about 40% of a full-size trade
    assert 1000.0 - eq[-1] == pytest.approx(0.4 * 1000 * (2 * rs.FEE + 2 * rs.SLIP), rel=0.05)


def test_rows_and_summary():
    rng = np.random.default_rng(1)
    idx_n = 24 * 60
    frames = {k: _frame(p0 * np.exp(np.cumsum(rng.normal(0, 0.01, idx_n))), start="2025-01-01")
              for k, p0 in (("btc", 60000.0), ("eth", 3000.0))}
    d1 = frames["btc"]["close"].resample("1D").last()
    mk = rs.prepare(frames, d1, {})
    books, eq = rs.run_row(mk, ("btc", "eth"), False, 1.0, "2025-01-05", "2025-02-25")
    s = rs.summarize(books, eq, 272)
    assert s["trades"] > 0 and s["longs"] + s["shorts"] == s["trades"]
    books, eq = rs.run_row(mk, ("btc",), True, 1.0, "2025-01-05", "2025-02-25")
    assert all(t["side"] > 0 for b in books for t in b.trades)
