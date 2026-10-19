"""Tests for research_ichimoku (synthetic daily candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_ichimoku as ri


def _frame(closes, start="2025-01-01", spread=0.5):
    """Daily candles that open at the previous close."""
    c = np.array(closes, float)
    o = np.concatenate([[c[0]], c[:-1]])
    idx = pd.date_range(start, periods=len(c), freq="D", tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c}, index=idx)


def _first(mask):
    return int(np.flatnonzero(mask)[0])


def test_lines_follow_the_definitions():
    f = _frame(np.linspace(100, 200, 120))
    ln = ri.ichimoku(f)
    j = 100
    h, lo = f["high"].to_numpy(), f["low"].to_numpy()
    assert ln.tenkan[j] == pytest.approx((h[j - 8:j + 1].max() + lo[j - 8:j + 1].min()) / 2)
    assert ln.kijun[j] == pytest.approx((h[j - 25:j + 1].max() + lo[j - 25:j + 1].min()) / 2)
    k = j - ri.SHIFT
    a_then = (ln.tenkan[k] + ln.kijun[k]) / 2
    b_then = (h[k - 51:k + 1].max() + lo[k - 51:k + 1].min()) / 2
    assert ln.cloud_hi[j] == pytest.approx(max(a_then, b_then))
    assert ln.cloud_lo[j] == pytest.approx(min(a_then, b_then))
    assert not ln.enter[:ri.SENKOU_B + ri.SHIFT - 1].any()  # no cloud yet


def test_uptrend_enters_at_next_open_and_holds_without_costs(monkeypatch):
    monkeypatch.setattr(ri, "FEE", 0.0)
    monkeypatch.setattr(ri, "SLIP", 0.0)
    f = _frame(np.linspace(100, 200, 140))
    ln = ri.ichimoku(f)
    book, eq = ri.simulate(f, ln, 1, len(f), 1000.0, brakes=False)
    first = _first(ln.enter)
    assert len(book.trades) == 1 and book.trades[0]["in"] == str(f.index[first + 1].date())
    assert book.trades[0]["why"] == "fin"
    expect = 1000.0 * f["close"].iloc[-1] / f["open"].iloc[first + 1]
    assert eq[-1] == pytest.approx(expect)


def test_close_under_kijun_exits_at_next_open(monkeypatch):
    monkeypatch.setattr(ri, "FEE", 0.0)
    monkeypatch.setattr(ri, "SLIP", 0.0)
    closes = list(np.linspace(100, 200, 120)) + [150.0, 150.0, 150.0]
    f = _frame(closes)
    ln = ri.ichimoku(f)
    assert ln.exit[120]
    book, _ = ri.simulate(f, ln, 1, len(f), 1000.0, brakes=False)
    t = book.trades[0]
    assert t["why"] == "señal" and t["out"] == str(f.index[121].date())


def test_b_stop_fills_at_stop_or_gapped_open(monkeypatch):
    monkeypatch.setattr(ri, "FEE", 0.0)
    monkeypatch.setattr(ri, "SLIP", 0.0)
    f = _frame(list(np.linspace(100, 200, 120)) + [200.0, 200.0])
    ln = ri.ichimoku(f)
    j = 121
    stop = max(ln.kijun[j - 1], ln.kijun[j - 2])
    touch = f.copy()
    touch.iloc[j, touch.columns.get_loc("low")] = stop - 1
    book, _ = ri.simulate(touch, ln, 1, len(f), 1000.0, brakes=True)
    t = book.trades[0]
    assert t["why"] == "stop" and t["out"] == str(f.index[j].date())
    assert t["ret_pct"] < 0 or stop > f["open"].iloc[_first(ln.enter) + 1]
    gap = touch.copy()
    gap.iloc[j, gap.columns.get_loc("open")] = stop - 5
    b2, _ = ri.simulate(gap, ln, 1, len(f), 1000.0, brakes=True)
    assert b2.trades[0]["why"] == "stop" and b2.trades[0]["ret_pct"] < t["ret_pct"]


def test_b_risk_is_two_percent_and_capped_at_one_x(monkeypatch):
    monkeypatch.setattr(ri, "FEE", 0.0)
    monkeypatch.setattr(ri, "SLIP", 0.0)
    f = _frame(np.linspace(100, 200, 140))
    ln = ri.ichimoku(f)
    j = _first(ln.enter) + 1
    stop = ln.kijun[j - 1]
    crash = f.copy()
    crash.iloc[j + 1:, :] = stop - 50  # gaps far under the stop the day after entry
    book, _ = ri.simulate(crash, ln, 1, len(f), 1000.0, brakes=True)
    qty = min(1000.0 / f["open"].iloc[j], 0.02 * 1000.0 / (f["open"].iloc[j] - stop))
    t = book.trades[0]
    assert t["ret_pct"] == pytest.approx(qty * ((stop - 50) - f["open"].iloc[j]) / 10, abs=1e-3)


def test_b_skips_event_days_and_closes_when_regime_fails(monkeypatch):
    monkeypatch.setattr(ri, "FEE", 0.0)
    monkeypatch.setattr(ri, "SLIP", 0.0)
    f = _frame(np.linspace(100, 200, 140))
    ln = ri.ichimoku(f)
    j = _first(ln.enter) + 1
    events = np.zeros(len(f), bool)
    events[j] = True
    book, _ = ri.simulate(f, ln, 1, len(f), 1000.0, brakes=True, events=events)
    assert book.trades[0]["in"] == str(f.index[j + 1].date())
    gate = np.ones(len(f), bool)
    gate[j + 5:] = False
    book, _ = ri.simulate(f, ln, 1, len(f), 1000.0, brakes=True, gate=gate)
    assert book.trades[0]["why"] == "régimen" and book.trades[0]["out"] == str(f.index[j + 5].date())
    assert len(book.trades) == 1
    a, _ = ri.simulate(f, ln, 1, len(f), 1000.0, brakes=False, gate=gate, events=events)
    assert a.trades[0]["in"] == str(f.index[j].date()) and a.trades[0]["why"] == "fin"


def test_regime_gate_uses_yesterdays_close():
    days = pd.date_range("2025-01-01", periods=80, freq="D", tz="UTC")
    c = pd.Series(np.r_[np.linspace(90.0, 100.0, 60), np.full(20, 50.0)], index=days)
    g = ri.regime_gate(c, days)
    assert g[60] and not g[61]
    assert g[:50].all()  # unknown average: open


def test_daily_funding_sums_the_three_payments():
    days = pd.date_range("2025-01-01", periods=2, freq="D", tz="UTC")
    rates = pd.Series([0.01, 0.02, 0.03], index=pd.to_datetime(
        ["2025-01-01 00:00", "2025-01-01 08:00", "2025-01-01 16:00"], utc=True))
    out = ri.daily_funding(rates, days)
    assert out[0] == pytest.approx(0.06) and out[1] == pytest.approx(0.03)


def test_funding_is_charged_while_long():
    f = _frame(np.linspace(100, 200, 140))
    ln = ri.ichimoku(f)
    fund = np.full(len(f), 0.03)
    book, _ = ri.simulate(f, ln, 1, len(f), 1000.0, brakes=False, funding=fund)
    assert book.funding > 0


def test_summary_and_rows():
    frames = {"btc": _frame(np.linspace(100, 200, 500), start="2024-01-01"),
              "eth": _frame(np.linspace(50, 80, 500), start="2024-01-01")}
    mk = ri.prepare(frames, {})
    books, eq = ri.run_row(mk, ("btc", "eth"), True, 1.0, "2024-06-01", "2025-01-01")
    s = ri.summarize(books, eq, 280)
    assert {"net_pct", "max_dd_pct", "net_dd", "dsr", "daily_equity", "quarters"} <= set(s)
    assert eq.iloc[0] == pytest.approx(1000.0, rel=0.05)
    assert sum(v[4] for v in ri.ROWS.values()) == 6
