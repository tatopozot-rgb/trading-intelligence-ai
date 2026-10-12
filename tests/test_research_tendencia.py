"""Tests for the trend-following research (no network: synthetic hourly bars)."""
import math

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_tendencia as rt


def _bars(n, seed=0, drift=0.0, vol=0.004, start="2025-01-01"):
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + drift + rng.normal(0, vol, n))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.001,
                         "low": np.minimum(open_, close) * 0.999, "close": close}, index=idx)


def _market(bars):
    times = next(iter(bars.values())).index
    return rt.build_market(bars, {}, times)


def _flat_plan(m):
    z = {s: np.zeros(len(m.times)) for s in m.bars}
    nan = {s: np.full(len(m.times), np.nan) for s in m.bars}
    return rt.Plan({s: v.copy() for s, v in z.items()}, {s: v.astype(bool) for s, v in z.items()},
                   {s: v.astype(bool) for s, v in z.items()}, {s: v.copy() for s, v in nan.items()},
                   {s: v.copy() for s, v in nan.items()}, {s: v.copy() for s, v in z.items()})


def test_entry_at_next_open_risk_sizing_fees_slippage_and_stop():
    m = _market({"SOLUSDT": _bars(200)})
    plan = _flat_plan(m)
    i = 50
    o = float(m.bars["SOLUSDT"]["open"].iloc[i])
    plan.entry["SOLUSDT"][i] = 1
    plan.stop_long["SOLUSDT"][i] = o * 0.98
    m.bars["SOLUSDT"].iloc[i + 3, m.bars["SOLUSDT"].columns.get_loc("low")] = o * 0.90
    sim = rt.simulate(m, plan, 0)
    (t,) = sim.trades
    price = o * (1 + rt.SLIP)
    qty = min(rt.CAPITAL * rt.RISK / (price - o * 0.98), rt.CAPITAL * rt.MAX_POSITION / price)
    assert t["why"] == "stop" and t["exit_at"] == m.times[i + 3].isoformat()
    exit_price = o * 0.98 * (1 - rt.SLIP)
    expected = (exit_price - price) * qty - (price + exit_price) * qty * rt.FEE - t["funding"]
    assert t["pnl"] == pytest.approx(expected, rel=1e-9)
    assert t["funding"] > 0  # longs pay the default positive funding


def test_gap_through_the_stop_fills_at_the_open_and_short_stop():
    m = _market({"SOLUSDT": _bars(200)})
    b = m.bars["SOLUSDT"]
    plan = _flat_plan(m)
    i = 50
    o = float(b["open"].iloc[i])
    plan.entry["SOLUSDT"][i] = -1
    plan.stop_short["SOLUSDT"][i] = o * 1.02
    b.iloc[i + 2, b.columns.get_loc("open")] = o * 1.05
    b.iloc[i + 2, b.columns.get_loc("high")] = o * 1.06
    (t,) = rt.simulate(m, plan, 0).trades
    assert t["side"] == "SELL" and t["why"] == "stop"
    assert t["pnl"] < 0
    assert t["ret_pct"] < -5  # filled at the gap open (+5%), not at the stop (+2%)


def test_stop_ratchets_only_in_the_trade_direction():
    m = _market({"SOLUSDT": _bars(300, vol=0.0001)})
    plan = _flat_plan(m)
    o = float(m.bars["SOLUSDT"]["open"].iloc[10])
    plan.entry["SOLUSDT"][10] = 1
    plan.stop_long["SOLUSDT"][10] = o * 0.9
    plan.stop_long["SOLUSDT"][20] = o * 0.8  # lower: ignored
    plan.stop_long["SOLUSDT"][30] = o * 1.5  # above the price: the next open gaps through it
    (t,) = rt.simulate(m, plan, 0).trades
    assert t["why"] == "stop" and t["exit_at"] == m.times[30].isoformat()


def test_max_three_positions_strongest_first_and_regime_filter():
    syms = ("A", "B", "C", "D")
    m = _market({s: _bars(100, seed=k) for k, s in enumerate(syms)})
    plan = _flat_plan(m)
    for k, s in enumerate(syms):
        plan.entry[s][10] = 1
        plan.stop_long[s][10] = float(m.bars[s]["open"].iloc[10]) * 0.9
        plan.strength[s][10] = k
    sim = rt.simulate(m, plan, 0)
    assert sorted(t["symbol"] for t in sim.trades) == ["B", "C", "D"]
    m.regime[:] = -1.0  # BTC below its mean: no longs
    assert rt.simulate(m, plan, 0, regime_filter=True).trades == []


def test_one_x_keeps_all_positions_within_the_equity():
    syms = ("A", "B", "C")
    m = _market({s: _bars(100, seed=k) for k, s in enumerate(syms)})
    plan = _flat_plan(m)
    for s in syms:
        plan.entry[s][10] = 1
        plan.stop_long[s][10] = float(m.bars[s]["open"].iloc[10]) * 0.999  # tiny stop: capped by the position size
    sim = rt.simulate(m, plan, 0)
    assert max(sim.exposure[10:]) <= 1.0 + 1e-6


def test_signals_use_only_closed_bars():
    bars = _bars(24 * 120, drift=0.0005)
    m = _market({"BTCUSDT": bars})
    plan = rt.donchian_plan(m, "1d", 20, "atr3")
    hits = np.flatnonzero(plan.entry["BTCUSDT"])
    assert len(hits) > 0
    assert all(m.times[i].hour == 0 for i in hits)  # a daily bar acts at the next day's first hour
    i = hits[0]
    daily = rt.resample(bars.iloc[:i], "1d")  # only bars that closed before hour i
    assert daily["close"].iloc[-1] > daily["high"].iloc[-21:-1].max()


def test_ema_and_tsmom_plans_follow_the_trend_sign():
    up = _bars(24 * 200, seed=1, drift=0.0004)
    down = _bars(24 * 200, seed=2, drift=-0.0004)
    m = _market({"BTCUSDT": up, "ETHUSDT": down})
    ema = rt.ema_plan(m, "4h", 20, 50, 3)
    assert (ema.entry["BTCUSDT"] > 0).sum() >= (ema.entry["BTCUSDT"] < 0).sum()
    ts = rt.tsmom_plan(m, 30, 20, 3)
    late = slice(24 * 100, None)
    assert set(np.unique(ts.entry["BTCUSDT"][late])) <= {0.0, 1.0}
    assert set(np.unique(ts.entry["ETHUSDT"][late])) <= {0.0, -1.0}
    assert ts.weight is not None and 0 < ts.weight["BTCUSDT"][late].max() <= rt.MAX_POSITION


def test_regime_is_known_only_after_the_day_closes():
    times = pd.date_range("2025-01-01", periods=24 * 260, freq="1h", tz="UTC")
    bars = _bars(len(times), drift=0.0003)
    reg = rt.btc_regime(times, bars)
    assert (reg[: 24 * rt.REGIME_DAYS] == 0).all()
    assert reg[-1] == 1.0


def test_walk_forward_picks_by_the_past_and_charges_the_switch():
    days = pd.date_range("2025-01-01", periods=180, freq="1D", tz="UTC")
    good_then_bad = pd.Series(np.where(np.arange(180) < 120, 0.01, -0.01), index=days)
    flat = pd.Series(0.001, index=days)

    def combo(name, r):
        eq = rt.CAPITAL * (1 + r).cumprod()
        return rt.Combo({"n": name}, r, pd.Series(0.5, index=days), eq,
                        [{"side": "BUY", "exit_at": str(days[130]), "pnl": 1.0, "fees": 0.1, "funding": 0.0}])

    wins = rt.windows(days[90], days[-1] + rt.DAY)
    wf = rt.walk_forward([combo("a", good_then_bad), combo("b", flat)], wins)
    assert [c["parametros"]["n"] for c in wf["chosen"]] == ["a", "a", "b"]  # the switch waits until the fit sees the bad days
    assert wf["switch_cost"] > 0
    first = wf["r"].iloc[0]
    assert first == pytest.approx(0.01 - 0.5 * (rt.FEE + rt.SLIP))
    assert len(wf["r"]) == 90 and len(wf["trades"]) == 1


def test_summary_quarters_and_verdict():
    days = pd.date_range("2025-01-01", periods=365, freq="1D", tz="UTC")
    r = pd.Series(0.001, index=days)
    trades = [{"side": "BUY", "exit_at": str(days[k % 365]), "pnl": 2.0 if k % 2 else -1.0, "fees": 0.1,
               "funding": 0.0} for k in range(120)]
    s = rt.summarize(r, trades, desk_r=pd.Series(np.sin(np.arange(365)), index=days))
    assert s["operaciones"] == 120 and s["acierto_pct"] == 50.0
    assert len(s["trimestres"]) == 4 and s["trimestres_positivos"] == 4
    assert s["max_caida_pct"] == 0.0 and s["neto_caida"] is None
    desk = {"neto_caida": 1.0}
    s["neto_caida"] = 5.0
    assert rt.verdict(s, desk).startswith("GANA")
    s["operaciones"] = 50
    assert rt.verdict(s, desk).startswith("muestra corta")


def test_study_end_to_end_without_network(monkeypatch):
    n = 24 * (rt.WARMUP_DAYS + rt.FIT_DAYS + 60)
    bars = {s: _bars(n, seed=k, drift=0.0002 * (1 if k % 2 else -1), vol=0.006) for k, s in
            enumerate(("BTCUSDT", "ETHUSDT", "SOLUSDT"))}
    m = _market(bars)
    monkeypatch.setattr(rt, "GRIDS", {"donchian": rt.GRIDS["donchian"][:2], "ema": rt.GRIDS["ema"][:1],
                                      "tsmom": rt.GRIDS["tsmom"][:2]})
    days = pd.date_range(m.times[-1].normalize() - pd.Timedelta(days=59), periods=60, freq="1D")
    res = rt.study(m, 60, pd.Series(0.001, index=days), [])
    assert set(res["familias"]) == {"donchian", "donchian_filtro", "ema", "ema_filtro", "tsmom", "tsmom_filtro"}
    assert len(res["ventanas"]) == 2
    report = rt.render(res, {"prueba_desde": "a", "hasta": "b", "simbolos": list(bars)})
    assert "mesa_r3" in report and "Veredicto" in report
    for s in res["familias"].values():
        assert not math.isnan(s["neto_pct"])
