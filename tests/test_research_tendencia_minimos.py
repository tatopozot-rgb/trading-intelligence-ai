"""Tests for the minimum-notional refusal check (no network: synthetic bars)."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_tendencia_minimos as rm
from trading_intelligence.backtesting import two_way_backtest as tw


def _fetch(symbol, interval, start, end):
    step = {"5m": "5min", "1h": "1h"}[interval]
    idx = pd.date_range(start, end, freq=step, inclusive="left")
    c = 100 * np.exp(np.cumsum(np.full(len(idx), 0.0008)))
    return pd.DataFrame({"open": c, "high": c * 1.003, "low": c * 0.997, "close": c, "volume": 1.0}, index=idx)


def _event(sym, i, side="BUY", room=0.0, used=1000.0, open_=2):
    return {"symbol": sym, "i": i, "side": side, "by_risk": 300.0, "by_position": 500.0, "by_room": room,
            "used": used, "equity": 1000.0, "open": open_, "dist_pct": 3.0, "stop": 1.0, "target": 2.0}


def test_simulate_reports_each_refusal_with_its_sizing():
    m5 = _fetch("BTCUSDT", "5m", datetime(2026, 10, 8, tzinfo=timezone.utc), datetime(2026, 10, 10, tzinfo=timezone.utc))
    h1 = _fetch("BTCUSDT", "1h", datetime(2026, 10, 5, tzinfo=timezone.utc), datetime(2026, 10, 10, tzinfo=timezone.utc))
    seen = []
    res = tw.simulate({"BTCUSDT": tw.prepare(m5, h1, 200)}, "regimen", 37.0, on_skip=seen.append)
    assert res.skipped_minimum == len(seen) > 0
    e = seen[0]
    assert e["minimum"] == 100.0 and min(e["by_risk"], e["by_position"], e["by_room"]) < 100.0


def test_episodes_join_consecutive_bars_and_name_the_cap():
    events = [_event("SOLUSDT", 10), _event("SOLUSDT", 11), _event("SOLUSDT", 12), _event("SOLUSDT", 20),
              _event("SOLUSDT", 21, side="SELL"), _event("ADAUSDT", 11)]
    eps = rm.episodes(events)
    assert [(e["symbol"], e["bars"]) for e in eps] == [("ADAUSDT", 1), ("SOLUSDT", 3), ("SOLUSDT", 1), ("SOLUSDT", 1)]
    assert all(e["limit"] == "by_room" for e in eps)


def test_summary_compares_with_the_desk():
    events = [_event("SOLUSDT", 10), _event("SOLUSDT", 11), _event("ADAUSDT", 30)]
    eps = rm.episodes(events)
    eps[0]["outcome"], eps[1]["outcome"] = "evitó pérdida", "dejó pasar ganancia"
    s = rm.summarize(events, eps, [{"pnl": 1.0}, {"pnl": -1.0}, {"pnl": 2.0}, {"pnl": -0.5}])
    assert s["rechazos"] == 3 and s["episodios"] == 2
    assert s["limite"] == {"capital ya usado (1x)": 3}
    assert s["acierto_episodios_pct"] == 50.0 and s["mesa_acierto_pct"] == 50.0
    assert "Rechazos" in rm.render([{**s, "desde": "a", "hasta": "b"}])
