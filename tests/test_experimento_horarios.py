"""Tests for the experimento horarios (docs/PREREG_HORARIOS.md + Amendment 1). No network."""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import experimento_horarios as eh


def _one_min(start="2026-09-28", days=4, seed=0, drift=0.0) -> pd.DataFrame:
    idx = pd.date_range(start, periods=days * 1440, freq="1min", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + drift + rng.normal(0, 0.0008, len(idx)))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.0002,
                         "low": np.minimum(open_, close) * 0.9998, "close": close, "volume": 1.0}, index=idx)


def _data(**kw):
    m1 = _one_min(**kw)
    return m1, eh.to_20m(m1)[0]


START = pd.Timestamp("2026-10-01 12:00", tz="UTC")


def test_20m_bars_from_1m_align_and_drop_incomplete():
    m1 = _one_min(days=1)
    bars, gaps = eh.to_20m(m1)
    assert len(bars) == 72 and gaps == 0 and all(t.minute in (0, 20, 40) for t in bars.index)
    assert bars.iloc[0]["close"] == m1["close"].iloc[19] and bars.iloc[0]["low"] == m1["low"].iloc[:20].min()
    bars2, gaps2 = eh.to_20m(m1.drop(m1.index[30]))
    assert len(bars2) == 71 and gaps2 == 1


def test_owner_window_is_07_to_10_ecuador():
    owner = [w for w in eh.WINDOWS if w[0] == "dueno"][0]
    assert owner[1:] == (12, 3, "dueno")
    assert eh.window_label("dueno") == "07–10 Ecuador (12–15 UTC) — ventana del dueño"
    assert eh.hour_label(0) == "19–21 Ecuador (00–02 UTC)"
    assert len([w for w in eh.WINDOWS if w[3] == "exploratoria"]) == 12


def test_baseline_buys_the_first_minute_and_sells_the_last():
    m1, bars = _data()
    (t,) = eh.run_window(m1, bars, START, 3, "baseline", "BTCUSDT")
    assert t.entry == pytest.approx(m1.at[START, "open"] * (1 + eh.SLIP))
    assert t.exit == pytest.approx(m1.at[START + pd.Timedelta(minutes=179), "close"] * (1 - eh.SLIP))
    assert t.exit_time == START + pd.Timedelta(hours=3)


class _Stub:
    """Buys on every flat decision with a stop `stop_pct` below the last close; exits on the n-th check."""

    def __init__(self, stop_pct=0.01, exit_on_check=None):
        self.stop_pct, self.exit_on_check, self.checks, self.seen = stop_pct, exit_on_check, 0, []

    def on_bar(self, hist):
        return SimpleNamespace(stop_price=Decimal(str(hist["close"].iloc[-1] * (1 - self.stop_pct))))

    def on_exit_signal(self, hist, entry):
        self.checks += 1
        self.seen.append(hist.index[-1])
        return self.exit_on_check is not None and self.checks >= self.exit_on_check


def _route_to(monkeypatch, stub):
    router = SimpleNamespace(route=lambda snap: SimpleNamespace(strategy=stub))
    monkeypatch.setattr(eh, "router_for", lambda strategy, symbol: router)


def test_held_position_is_force_closed_at_the_window_end_and_exits_checked_every_3_minutes(monkeypatch):
    m1, bars = _data(seed=2)
    stub = _Stub(stop_pct=0.5)  # stop never reached
    _route_to(monkeypatch, stub)
    (t,) = eh.run_window(m1, bars, START, 2, "tendencia", "BTCUSDT")
    assert t.entry == pytest.approx(m1.at[START, "open"] * (1 + eh.SLIP))
    assert t.reason == "fin de ventana" and t.exit_time == START + pd.Timedelta(hours=2)
    assert t.exit == pytest.approx(m1.at[START + pd.Timedelta(minutes=119), "close"] * (1 - eh.SLIP))
    assert stub.checks == 39  # minutes 3, 6, ..., 117


def test_exit_signal_fills_at_that_minute_open_and_re_entry_waits_for_the_next_20m(monkeypatch):
    m1, bars = _data(seed=2)
    _route_to(monkeypatch, _Stub(stop_pct=0.5, exit_on_check=2))
    trades = eh.run_window(m1, bars, START, 2, "tendencia", "BTCUSDT")
    first = trades[0]
    assert first.reason == "señal" and first.exit_time == START + pd.Timedelta(minutes=6)
    assert first.exit == pytest.approx(m1.at[first.exit_time, "open"] * (1 - eh.SLIP))
    assert trades[1].entry_time == START + pd.Timedelta(minutes=20)


def test_stop_on_a_1m_low_and_on_a_gap(monkeypatch):
    m1, bars = _data(seed=4)
    ref = bars.loc[START - eh.BAR, "close"]
    stop = ref * 0.99
    hit = START + pd.Timedelta(minutes=7)
    m1.loc[hit, "low"] = stop * 0.98
    _route_to(monkeypatch, _Stub(stop_pct=0.01))
    t = eh.run_window(m1, bars, START, 2, "tendencia", "BTCUSDT")[0]
    assert t.reason == "stop" and t.exit_time == hit and t.exit == pytest.approx(stop * (1 - 2 * eh.SLIP))
    m1.loc[hit, "open"] = stop * 0.97  # gapped through
    t = eh.run_window(m1, bars, START, 2, "tendencia", "BTCUSDT")[0]
    assert t.exit == pytest.approx(stop * 0.97 * (1 - eh.SLIP))


def test_in_progress_bar_is_built_from_minutes_only_up_to_the_check():
    m1, bars = _data()
    t = START + pd.Timedelta(minutes=26)
    h = eh._with_partial(bars, m1, t)
    assert h.index[-1] == START + pd.Timedelta(minutes=20)
    part = m1.loc[START + pd.Timedelta(minutes=20): t - pd.Timedelta(minutes=1)]
    assert h["close"].iloc[-1] == part["close"].iloc[-1] and h["high"].iloc[-1] == part["high"].max()
    assert len(h) <= eh.HISTORY_BARS


@pytest.mark.parametrize("strategy", ["tendencia", "rango"])
def test_real_strategies_stay_inside_the_window_and_never_see_the_future(strategy):
    m1, bars = _data(seed=3, drift=0.00004)
    end = START + pd.Timedelta(hours=2)
    trades = eh.run_window(m1, bars, START, 2, strategy, "BTCUSDT")
    assert all(START <= t.entry_time < end and t.exit_time <= end for t in trades)
    m2 = m1.copy()
    m2.loc[m2.index >= end, ["open", "high", "low", "close"]] *= 3.0
    again = eh.run_window(m2, eh.to_20m(m2)[0], START, 2, strategy, "BTCUSDT")
    assert [(t.entry, t.exit) for t in trades] == [(t.entry, t.exit) for t in again]


def test_window_with_a_gap_is_skipped():
    m1, _ = _data()
    m1 = m1.drop(START + pd.Timedelta(minutes=45))
    assert eh.run_window(m1, eh.to_20m(m1)[0], START, 2, "baseline", "BTCUSDT") == []


def test_benjamini_hochberg():
    assert eh.bh([0.001, 0.02, 0.04, 0.5], q=0.10) == [True, True, True, False]
    assert eh.bh([0.2, 0.3], q=0.10) == [False, False]


def _row(d, window, sym, strat, nets, family="exploratoria"):
    return {"date": d.isoformat(), "weekday": d.weekday(), "window": window, "window_utc": 0, "hours": 2,
            "family": family, "symbol": sym, "strategy": strat, "net_pct": nets, "trades": len(nets)}


def test_selection_uses_weekday_scope_and_calendar_halves():
    rows = []
    for i in range(14):
        d = eh.FORWARD_START + timedelta(days=i)
        good = 0.5 + 0.01 * i
        rows.append(_row(d, "04h", "BTCUSDT", "baseline", [good]))
        rows.append(_row(d, "06h", "ETHUSDT", "baseline", [0.5 if d < eh.HALF2_START else -0.5]))
        rows.append(_row(d, "08h", "SOLUSDT", "baseline", [0.5 if d.weekday() < 5 else -9.0]))  # only weekends bad
    res = {tuple(c["cell"]): c for c in eh.select(rows, lambda r: (r["window"], r["symbol"], r["strategy"]), "lun-vie")}
    assert res[("04h", "BTCUSDT", "baseline")]["qualifies"] and res[("04h", "BTCUSDT", "baseline")]["half1_n"] == 5
    assert not res[("06h", "ETHUSDT", "baseline")]["qualifies"]
    assert res[("08h", "SOLUSDT", "baseline")]["half2_n"] == 5  # Saturday excluded from lun-vie
    sat = {tuple(c["cell"]): c for c in eh.select(rows, lambda r: (r["window"], r["symbol"], r["strategy"]), "lun-sab")}
    assert ("08h", "SOLUSDT", "baseline") not in sat  # the bad Saturday kills it in Mon-Sat


def test_owner_pooled_test_is_planned_at_bonferroni_alpha():
    syms = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")  # 4 x 5 weekdays = 20 >= 15 per half
    rows = [_row(eh.FORWARD_START + timedelta(days=i), "dueno", s, strat, [0.2 + 0.01 * i], family="dueno")
            for i in range(14) for s in syms for strat in ("baseline", "ruptura")]
    rows += [_row(eh.FORWARD_START + timedelta(days=i), "dueno", "BTCUSDT", "tendencia", [0.5], family="dueno")
             for i in range(14)]  # only 5 per half: insufficient for a pooled test
    out = eh.evaluate(rows)["lun-vie"]
    pooled = {tuple(c["cell"]): c for c in out["dueno_pooled"]}
    assert eh.OWNER_ALPHA == pytest.approx(0.0125)
    assert pooled[("dueno", "TODOS", "baseline")]["qualifies"] and pooled[("dueno", "TODOS", "ruptura")]["qualifies"]
    assert not pooled[("dueno", "TODOS", "tendencia")]["qualifies"]
    assert pooled[("dueno", "TODOS", "tendencia")]["insufficient"]
    assert len(out["dueno_baseline_por_simbolo"]) == 4  # baseline only


def test_run_days_writes_reports_with_ecuador_time_first(tmp_path):
    def fetch(symbol, start, end):
        m1 = _one_min(start="2026-09-20", days=12, seed=hash(symbol) % 50)
        return m1.loc[start: end - timedelta(minutes=1)]
    eh.run_days([date(2026, 9, 30)], tmp_path, fetch)
    day = json.loads((tmp_path / "2026-09-30.json").read_text())
    assert day["label"].startswith("miércoles; referencia: datos pasados")
    assert len(day["rows"]) == len(eh.WINDOWS) * 13 * 4
    md = (tmp_path / "2026-09-30.md").read_text()
    assert "Ecuador (UTC−5)" in md and "07–10 Ecuador (12–15 UTC) — ventana del dueño" in md
    summary = (tmp_path / "resumen.md").read_text()
    assert "días hábiles lun–vie: 0/10" in summary and "por día de la semana" in summary


def test_main_refuses_incomplete_days(tmp_path):
    today = datetime.now(timezone.utc).date().isoformat()
    with pytest.raises(SystemExit):
        eh.main(["--start", today, "--out", str(tmp_path)])


def _breakout_data(break_up: bool, hit_stop: bool = False):
    m1, bars = _data(seed=6)
    first = bars.loc[START]
    t = START + eh.BAR  # second bar: closes above (or below) the range
    sl = slice(t, t + pd.Timedelta(minutes=19))
    level = first["high"] * 1.01 if break_up else first["low"] * 1.001
    m1.loc[sl, ["open", "high", "low", "close"]] = level
    m1.loc[sl, "high"] = level * 1.0001
    later = slice(t + eh.BAR, START + pd.Timedelta(hours=2) - pd.Timedelta(minutes=1))
    m1.loc[later, ["open", "close"]] = level
    m1.loc[later, "high"] = level * 1.0001
    m1.loc[later, "low"] = level * 0.9999
    if hit_stop:
        m1.loc[t + eh.BAR + pd.Timedelta(minutes=5), "low"] = first["low"] * 0.99
    return m1, eh.to_20m(m1)[0], first


def test_ruptura_enters_once_on_a_close_above_the_opening_range_and_holds_to_the_end():
    m1, bars, first = _breakout_data(True)
    (t,) = eh.run_window(m1, bars, START, 2, "ruptura", "BTCUSDT")
    assert t.entry_time == START + 2 * eh.BAR  # decided on bar 2's close, filled at the next open
    assert t.entry == pytest.approx(m1.at[t.entry_time, "open"] * (1 + eh.SLIP))
    assert t.reason == "fin de ventana" and t.exit_time == START + pd.Timedelta(hours=2)


def test_ruptura_stop_is_the_range_low():
    m1, bars, first = _breakout_data(True, hit_stop=True)
    (t,) = eh.run_window(m1, bars, START, 2, "ruptura", "BTCUSDT")
    assert t.reason == "stop" and t.exit == pytest.approx(first["low"] * (1 - 2 * eh.SLIP))


def test_ruptura_does_nothing_without_a_breakout():
    m1, bars, _ = _breakout_data(False)
    assert eh.run_window(m1, bars, START, 2, "ruptura", "BTCUSDT") == []
