"""Tests for the experimento horarios (docs/PREREG_HORARIOS.md). No network: fake 5m data."""
import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import experimento_horarios as eh


def _five_min(start="2026-09-20", days=12, seed=0, drift=0.0) -> pd.DataFrame:
    idx = pd.date_range(start, periods=days * 288, freq="5min", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + drift + rng.normal(0, 0.002, len(idx)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * 1.0005
    low = np.minimum(open_, close) * 0.9995
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": 1.0}, index=idx)


def test_20m_bars_align_and_drop_incomplete():
    df = _five_min(days=1)
    bars, gaps = eh.to_20m(df)
    assert len(bars) == 72 and gaps == 0
    assert all(t.minute in (0, 20, 40) for t in bars.index)
    first = df.iloc[:4]
    assert bars.iloc[0]["open"] == first["open"].iloc[0] and bars.iloc[0]["close"] == first["close"].iloc[-1]
    assert bars.iloc[0]["high"] == first["high"].max() and bars.iloc[0]["low"] == first["low"].min()
    bars2, gaps2 = eh.to_20m(df.drop(df.index[5]))
    assert len(bars2) == 71 and gaps2 == 1


def test_baseline_buys_window_open_and_sells_window_close():
    bars, _ = eh.to_20m(_five_min())
    start = pd.Timestamp("2026-09-30 04:00", tz="UTC")
    (t,) = eh.run_window(bars, start, "baseline", "BTCUSDT")
    w = bars.loc[start: start + pd.Timedelta(minutes=100)]
    assert t.entry == pytest.approx(w["open"].iloc[0] * (1 + eh.SLIP))
    assert t.exit == pytest.approx(w["close"].iloc[-1] * (1 - eh.SLIP))
    flat = eh.Trade(start, 100.0, start, 100.0, "x")
    assert flat.net_pct == pytest.approx(((1 - eh.FEE) / (1 + eh.FEE) - 1) * 100)


@pytest.mark.parametrize("strategy", ["tendencia", "rango"])
def test_trades_stay_inside_the_window_and_never_see_the_future(strategy):
    df = _five_min(seed=3, drift=0.0003)
    bars, _ = eh.to_20m(df)
    start = pd.Timestamp("2026-09-30 10:00", tz="UTC")
    end = start + pd.Timedelta(hours=2)
    trades = eh.run_window(bars, start, strategy, "BTCUSDT")
    assert all(start <= t.entry_time < end and t.exit_time <= end for t in trades)
    future = bars.copy()
    future.loc[future.index >= end, ["open", "high", "low", "close"]] *= 3.0  # changes after the window
    again = eh.run_window(future, start, strategy, "BTCUSDT")
    assert [(t.entry, t.exit) for t in trades] == [(t.entry, t.exit) for t in again]


class _Stub:
    """Proposes a buy with a stop 1% below the last close on every flat decision; exits on a flag."""

    def __init__(self, exit_after=None):
        self.exit_after, self.calls = exit_after, 0

    def on_bar(self, hist):
        from decimal import Decimal
        from types import SimpleNamespace
        return SimpleNamespace(stop_price=Decimal(str(hist["close"].iloc[-1] * 0.99)))

    def on_exit_signal(self, hist, entry):
        self.calls += 1
        return self.exit_after is not None and self.calls >= self.exit_after


def _stub_router(monkeypatch, stub):
    from types import SimpleNamespace
    router = SimpleNamespace(route=lambda snap: SimpleNamespace(strategy=stub))
    monkeypatch.setattr(eh, "router_for", lambda strategy, symbol: router)


def test_held_position_is_force_closed_at_the_window_close(monkeypatch):
    df = _five_min(seed=2, drift=0.0005)
    bars, _ = eh.to_20m(df)
    _stub_router(monkeypatch, _Stub())
    start = pd.Timestamp("2026-09-30 06:00", tz="UTC")
    trades = eh.run_window(bars, start, "tendencia", "BTCUSDT")
    w = bars.loc[start: start + pd.Timedelta(minutes=100)]
    assert trades[0].entry == pytest.approx(w["open"].iloc[0] * (1 + eh.SLIP))
    last = trades[-1]
    if last.reason == "fin de ventana":
        assert last.exit == pytest.approx(w["close"].iloc[-1] * (1 - eh.SLIP))


def test_exit_signal_fills_at_the_next_open_and_re_entry_waits_a_bar(monkeypatch):
    df = _five_min(seed=2, drift=0.0005)
    bars, _ = eh.to_20m(df)
    _stub_router(monkeypatch, _Stub(exit_after=1))
    start = pd.Timestamp("2026-09-30 06:00", tz="UTC")
    trades = eh.run_window(bars, start, "tendencia", "BTCUSDT")
    signal_exits = [t for t in trades if t.reason == "señal"]
    assert signal_exits
    t = signal_exits[0]
    assert t.exit == pytest.approx(bars.loc[t.exit_time, "open"] * (1 - eh.SLIP))
    assert t.exit_time == t.entry_time + eh.BAR


def test_stop_fills_at_the_stop_with_double_slippage(monkeypatch):
    df = _five_min(seed=4)
    bars, _ = eh.to_20m(df)
    start = pd.Timestamp("2026-09-30 08:00", tz="UTC")
    i = bars.index.get_loc(start)
    bars.iloc[i, bars.columns.get_loc("low")] = bars.iloc[i - 1]["close"] * 0.95  # pierces the 1% stop
    bars.iloc[i, bars.columns.get_loc("open")] = bars.iloc[i - 1]["close"]
    _stub_router(monkeypatch, _Stub())
    t = eh.run_window(bars, start, "tendencia", "BTCUSDT")[0]
    assert t.reason == "stop" and t.exit == pytest.approx(bars.iloc[i - 1]["close"] * 0.99 * (1 - 2 * eh.SLIP))


def test_window_with_a_gap_is_skipped():
    df = _five_min()
    bars, _ = eh.to_20m(df.drop(df.loc["2026-09-30 04:20":"2026-09-30 04:25"].index))
    assert eh.run_window(bars, pd.Timestamp("2026-09-30 04:00", tz="UTC"), "baseline", "BTCUSDT") == []


def test_benjamini_hochberg():
    assert eh.bh([0.001, 0.02, 0.04, 0.5], q=0.10) == [True, True, True, False]
    assert eh.bh([0.2, 0.3], q=0.10) == [False, False]
    assert eh.bh([]) == []


def _row(d, h, sym, strat, nets):
    return {"date": d.isoformat(), "window_utc": h, "symbol": sym, "strategy": strat, "net_pct": nets,
            "trades": len(nets), "wins": sum(n > 0 for n in nets), "net_sum": sum(nets), "reasons": []}


def test_selection_rule_requires_both_halves_and_bh():
    rows = []
    for i in range(14):
        d = eh.FORWARD_START + timedelta(days=i)
        rows.append(_row(d, 4, "BTCUSDT", "baseline", [0.5 + 0.01 * i]))      # good in both halves
        rows.append(_row(d, 6, "ETHUSDT", "baseline", [0.5 if i < 7 else -0.5]))  # fails half 2
        rows.append(_row(d, 8, "SOLUSDT", "baseline", [-0.3]))               # never a candidate
    rows.append(_row(eh.FORWARD_START - timedelta(days=1), 10, "XRPUSDT", "baseline", [9.0]))  # reference: ignored
    res = eh.select(rows, lambda r: (r["window_utc"], r["symbol"], r["strategy"]))
    by_cell = {tuple(c["cell"]): c for c in res}
    assert by_cell[(4, "BTCUSDT", "baseline")]["qualifies"] is True
    assert by_cell[(6, "ETHUSDT", "baseline")]["qualifies"] is False
    assert (8, "SOLUSDT", "baseline") not in by_cell and (10, "XRPUSDT", "baseline") not in by_cell


def test_hour_label_shows_utc_and_ecuador_time():
    assert eh.hour_label(0) == "00–02 UTC (19–21 UTC−5)"
    assert eh.hour_label(14) == "14–16 UTC (09–11 UTC−5)"


def test_run_days_writes_daily_and_summary_reports(tmp_path):
    def fetch(symbol, start, end):
        df = _five_min(start="2026-09-20", days=14, seed=hash(symbol) % 100)
        return df.loc[start: end - timedelta(minutes=5)]
    eh.run_days([date(2026, 9, 30), date(2026, 10, 1)], tmp_path, fetch)
    day = json.loads((tmp_path / "2026-09-30.json").read_text())
    assert day["label"] == "referencia: datos pasados"
    assert len(day["rows"]) == 12 * 13 * 3 and all(v == 0 for v in day["gaps"].values())
    md = (tmp_path / "2026-09-30.md").read_text()
    assert "UTC−5" in md and "Mejores 5" in md and "sin órdenes reales" in md
    summary = (tmp_path / "resumen.md").read_text()
    assert "Días forward (deciden): 0/14" in summary and "referencia: datos pasados" in summary


def test_main_refuses_incomplete_days(tmp_path):
    today = datetime.now(timezone.utc).date().isoformat()
    with pytest.raises(SystemExit):
        eh.main(["--start", today, "--out", str(tmp_path)])
