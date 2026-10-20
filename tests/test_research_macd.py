"""Tests for research_macd (synthetic daily candles, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_macd as rmc


def _frame(closes, start="2025-01-01", spread=0.5):
    c = np.array(closes, float)
    o = np.concatenate([[c[0]], c[:-1]])
    idx = pd.date_range(start, periods=len(c), freq="D", tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c}, index=idx)


def _vee(n_down=60, n_up=60, n_down2=40):
    return list(np.linspace(200, 100, n_down)) + list(np.linspace(100, 200, n_up)) + list(np.linspace(200, 120, n_down2))


@pytest.fixture
def free(monkeypatch):
    monkeypatch.setattr(rmc, "FEE", 0.0)
    monkeypatch.setattr(rmc, "SLIP", 0.0)


def test_crosses_follow_the_definition():
    f = _frame(_vee())
    x = rmc.macd(f["close"])
    line = f["close"].ewm(span=12, adjust=False).mean() - f["close"].ewm(span=26, adjust=False).mean()
    sig = line.ewm(span=9, adjust=False).mean()
    up = int(np.flatnonzero(x.up)[0])
    assert line.iloc[up] > sig.iloc[up] and line.iloc[up - 1] <= sig.iloc[up - 1]
    down = int(np.flatnonzero(x.down & (np.arange(len(f)) > up))[0])
    assert line.iloc[down] < sig.iloc[down] and line.iloc[down - 1] >= sig.iloc[down - 1]
    assert not (x.up & x.down).any()


def test_a_buys_and_sells_at_next_opens(free):
    f = _frame(_vee())
    x = rmc.macd(f["close"])
    book, eq = rmc.simulate(f, x, 30, len(f), 1000.0, brakes=False)
    up = int(np.flatnonzero(x.up & (np.arange(len(f)) >= 29))[0])
    down = int(np.flatnonzero(x.down & (np.arange(len(f)) > up))[0])
    t = book.trades[0]
    assert t["in"] == str(f.index[up + 1].date()) and t["out"] == str(f.index[down + 1].date())
    assert t["why"] == "señal"
    assert t["ret_pct"] == pytest.approx((f["open"].iloc[down + 1] / f["open"].iloc[up + 1] - 1) * 100, abs=1e-3)


def test_b_sizes_two_percent_to_the_desk_stop_and_stops_out(free):
    f = _frame(_vee())
    x = rmc.macd(f["close"])
    up = int(np.flatnonzero(x.up & (np.arange(len(f)) >= 29))[0])
    j = up + 1
    entry = f["open"].iloc[j]
    crash = f.copy()
    crash.iloc[j + 1:, :] = entry * 0.5  # gaps far below the stop the day after entry
    book, _ = rmc.simulate(crash, x, 30, len(f), 1000.0, brakes=True, stop_fn=lambda fr, jj, px: px * 0.9)
    t = book.trades[0]
    assert t["why"] == "stop"
    qty = min(1000.0 / entry, 0.02 * 1000.0 / (entry * 0.1))
    assert t["ret_pct"] == pytest.approx(qty * (entry * 0.5 - entry) / 10, abs=1e-3)


def test_b_brakes_block_entries_and_regime_closes(free):
    f = _frame(_vee())
    x = rmc.macd(f["close"])
    up = int(np.flatnonzero(x.up & (np.arange(len(f)) >= 29))[0])
    j = up + 1
    stop = lambda fr, jj, px: px * 0.9  # noqa: E731
    events = np.zeros(len(f), bool)
    events[j] = True
    book, _ = rmc.simulate(f, x, 30, len(f), 1000.0, brakes=True, events=events, stop_fn=stop)
    assert all(t["in"] != str(f.index[j].date()) for t in book.trades)
    gate = np.ones(len(f), bool)
    gate[j + 3:] = False
    book, _ = rmc.simulate(f, x, 30, len(f), 1000.0, brakes=True, gate=gate, stop_fn=stop)
    assert book.trades[0]["why"] == "régimen" and book.trades[0]["out"] == str(f.index[j + 3].date())


def test_desk_stop_is_below_the_entry():
    f = _frame(list(np.linspace(100, 200, 320)), start="2024-01-01")
    s = rmc.desk_stop(f, 310, float(f["open"].iloc[310]))
    assert 0 < s < f["open"].iloc[310]


def test_rows_run_end_to_end():
    frames = {"btc": _frame(_vee() * 3, start="2024-01-01"), "eth": _frame(_vee() * 3, start="2024-01-01")}
    mk = rmc.prepare(frames, {})
    books, eq = rmc.run_row(mk, ("btc", "eth"), True, 1.0, "2024-04-01", "2025-01-01")
    assert len(eq) > 200 and eq.iloc[0] == pytest.approx(1000.0, rel=0.05)
