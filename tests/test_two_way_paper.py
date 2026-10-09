"""Tests for the two-way momentum forward PAPER runner. No network: fake fetchers."""
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import two_way_momentum as tw
from trading_intelligence.backtesting import two_way_paper as tp

SYMBOLS = ["AAAUSDT", "BBBUSDT"]


def _market(drift: dict[str, float], crash_from: str | None = None, monday_close: float | None = None):
    days = pd.date_range("2026-01-01", "2027-03-01", freq="1D", tz="UTC")
    paths = {}
    for i, s in enumerate([*SYMBOLS, "PAXGUSDT"]):
        rng = np.random.default_rng(i)
        r = drift.get(s, 0.0) + rng.normal(0, 0.02, len(days))
        if crash_from is not None:
            r[days >= pd.Timestamp(crash_from, tz="UTC")] = -0.06
        paths[s] = 100 * np.cumprod(1 + r)

    def fetch(symbol, start, end):
        close = pd.Series(paths[symbol], index=days)
        frame = pd.DataFrame({"open": close.shift(1).fillna(close.iloc[0]), "close": close})
        frame = frame.loc[pd.Timestamp(start, tz="UTC"): pd.Timestamp(end, tz="UTC") - pd.Timedelta(days=1)]
        if monday_close is not None:
            frame.iloc[-1, frame.columns.get_loc("close")] = monday_close
        return frame
    return fetch


def _no_funding(symbol, start, end):
    return pd.Series(dtype=float), "fallback"


@pytest.fixture
def limits(tmp_path):
    p = tmp_path / "live_limits.json"
    p.write_text(json.dumps({"allowed_symbols": SYMBOLS}))
    return p


def _now(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_first_run_before_start_is_pending_with_frozen_symbols(tmp_path, limits):
    report = tp.run(tmp_path / "p", _now("2026-10-09T13:00"), _market({}), _no_funding, limits)
    state = json.loads((tmp_path / "p" / "state.json").read_text())
    assert report["status"] == "PENDING" and state["start"] == "2026-10-12"
    assert state["symbols"] == [*SYMBOLS, "PAXGUSDT"]
    assert "PENDIENTE" in (tmp_path / "p" / "report.md").read_text()


def test_running_replays_the_registered_code_and_reports_both_legs(tmp_path, limits):
    d = tmp_path / "p"
    tp.run(d, _now("2026-10-09T13:00"), _market({"AAAUSDT": 0.012, "BBBUSDT": -0.012}), _no_funding, limits)
    report = tp.run(d, _now("2026-11-02T00:20"), _market({"AAAUSDT": 0.012, "BBBUSDT": -0.012}), _no_funding, limits)
    assert report["status"] == "RUNNING" and len(report["weeks"]) == 3
    assert report["weeks"][0]["week"] == "2026-10-12"
    # Same numbers as calling the registered simulator directly.
    closes, opens, funding, _ = tp.load_market([*SYMBOLS, "PAXGUSDT"], pd.Timestamp("2026-10-12", tz="UTC"),
                                               pd.Timestamp("2026-11-02", tz="UTC"),
                                               _market({"AAAUSDT": 0.012, "BBBUSDT": -0.012}), _no_funding)
    weeks = [pd.Timestamp("2026-10-12", tz="UTC") + pd.Timedelta(days=7 * k) for k in range(3)]
    direct = tw.simulate_fold(closes, opens, funding, weeks, 1)
    assert report["equity"] == pytest.approx(tw.INITIAL_EQUITY * (1 + direct.total_return))
    assert report["positions"]["AAAUSDT"] > 0 and report["positions"]["BBBUSDT"] < 0
    md = (d / "report.md").read_text()
    assert "EN CURSO" in md and "Pierna **larga**" in md and "Corta:" in md and "| BBBUSDT | CORTO |" in md
    assert (d / "history" / "2026-11-02.json").exists()


def test_the_open_monday_close_is_never_used(tmp_path, limits):
    a = tp.run(tmp_path / "a", _now("2026-11-02T00:20"), _market({}), _no_funding, limits)
    b = tp.run(tmp_path / "b", _now("2026-11-02T00:20"), _market({}, monday_close=1e9), _no_funding, limits)
    assert a["equity"] == b["equity"] and a["positions"] == b["positions"]


def test_drawdown_stops_the_experiment_for_good(tmp_path, limits):
    d = tmp_path / "p"
    tp.run(d, _now("2026-10-09T13:00"), _market({}), _no_funding, limits)
    crash = _market({"AAAUSDT": 0.01, "BBBUSDT": 0.01, "PAXGUSDT": 0.01}, crash_from="2026-10-27")
    report = tp.run(d, _now("2026-11-09T00:20"), crash, _no_funding, limits)
    state = json.loads((d / "state.json").read_text())
    assert report["status"] == "STOPPED" and "caída máxima" in state["stopped_reason"]
    again = tp.run(d, _now("2026-11-16T00:20"), _market({}), _no_funding, limits)
    assert again["status"] == "STOPPED"
    assert "DETENIDO" in (d / "report.md").read_text()


def test_real_funding_far_above_the_model_stops_the_experiment(tmp_path, limits):
    def expensive(symbol, start, end):
        t = pd.date_range("2026-01-01", "2027-02-01", freq="8h", tz="UTC")
        return pd.Series(0.003, index=t), "data.binance.vision"  # 30x the model's 0.01%/8h
    d = tmp_path / "p"
    up = _market({"AAAUSDT": 0.012, "BBBUSDT": 0.012, "PAXGUSDT": 0.012})  # all long: longs pay
    tp.run(d, _now("2026-10-09T13:00"), up, _no_funding, limits)
    report = tp.run(d, _now("2026-10-26T00:20"), up, expensive, limits)
    state = json.loads((d / "state.json").read_text())
    assert report["status"] == "STOPPED" and "modelo" in state["stopped_reason"]


def test_days_after_the_last_published_rate_fall_back():
    t = pd.to_datetime(["2026-09-30 08:00", "2026-09-30 16:00", "2026-10-01 00:00"], utc=True)
    days = pd.date_range("2026-09-29", "2026-10-03", freq="1D", tz="UTC")
    out = tw.daily_funding(pd.Series(0.0001, index=t), days)
    assert math.isnan(out.iloc[0]) and out.iloc[1] == pytest.approx(0.0003)
    assert out.iloc[2:].isna().all()


def test_monday_helpers():
    assert tp.next_monday(_now("2026-10-09T13:00")) == pd.Timestamp("2026-10-12", tz="UTC")
    assert tp.next_monday(_now("2026-10-12T00:20")) == pd.Timestamp("2026-10-12", tz="UTC")
    assert tp.monday_of(_now("2026-10-18T23:00")) == pd.Timestamp("2026-10-12", tz="UTC")
