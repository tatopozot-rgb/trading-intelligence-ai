"""Tests for the rotation / reversion / pairs research (no network: synthetic hourly bars)."""
import math

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_rotacion as rr


def _market(n=24 * 40, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"), drifts=None, seed=0,
            vol=0.004):
    times = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    rng = np.random.default_rng(seed)
    bars = {}
    for k, s in enumerate(symbols):
        d = (drifts or {}).get(s, 0.0)
        close = 100 * np.cumprod(1 + d + rng.normal(0, vol, n))
        open_ = np.r_[close[0], close[:-1]]
        bars[s] = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.001,
                                "low": np.minimum(open_, close) * 0.999, "close": close}, index=times)
    funding = {s: pd.Series(dtype=float) for s in symbols}
    return rr.build_market(bars, funding, times)


def _set(m, sym, i, **vals):
    for k, v in vals.items():
        getattr(m, k).iloc[i, m.symbols.index(sym)] = v


def test_long_target_pays_fees_slippage_and_funding():
    m = _market(symbols=("SOLUSDT", "BTCUSDT"))
    i = 100
    o = float(m.open["SOLUSDT"].iloc[i])
    _set(m, "SOLUSDT", i + 1, high=o * 1.2, low=o * 0.99)
    sig = rr.Signal(i, "SOLUSDT", (("SOLUSDT", "BUY", 1 / 3),), i + 50, stop=o * 0.9, target=o * 1.1)
    run = rr.simulate(m, [sig], 0, len(m.times))
    (t,) = run.trades
    assert t["why"] == "meta"
    entry = o * (1 + rr.SLIP)
    qty = rr.CAPITAL / 3 / entry
    exit_ = o * 1.1 * (1 - rr.SLIP)
    gross = (exit_ - entry) * qty
    fees = entry * qty * rr.FEE + exit_ * qty * rr.FEE
    funding = 2 * qty * o * rr.tw.FUNDING_PER_8H / 8  # two hourly bars at the default rate
    assert t["fees"] == pytest.approx(fees)
    assert t["pnl"] == pytest.approx(gross - fees - funding, rel=0.02)
    assert run.curve.iloc[-1] == pytest.approx(rr.CAPITAL + t["pnl"])


def test_stop_beats_target_in_the_same_bar_and_gap_fills_at_open():
    m = _market(symbols=("SOLUSDT", "BTCUSDT"))
    i = 100
    o = float(m.open["SOLUSDT"].iloc[i])
    _set(m, "SOLUSDT", i + 2, high=o * 1.3, low=o * 0.7)
    sig = rr.Signal(i, "SOLUSDT", (("SOLUSDT", "BUY", 1 / 3),), i + 50, stop=o * 0.9, target=o * 1.1)
    assert rr.simulate(m, [sig], 0, len(m.times)).trades[0]["why"] == "stop"
    # a short whose stop is jumped by the open fills at the (worse) open
    _set(m, "SOLUSDT", i + 2, open=o * 1.2, high=o * 1.25, low=o * 1.15)
    sig = rr.Signal(i, "SOLUSDT", (("SOLUSDT", "SELL", 1 / 3),), i + 50, stop=o * 1.05)
    t = rr.simulate(m, [sig], 0, len(m.times)).trades[0]
    entry = o * (1 - rr.SLIP)
    qty = rr.CAPITAL / 3 / entry
    assert t["why"] == "stop"
    assert t["pnl"] < (entry - o * 1.2 * (1 + rr.SLIP)) * qty + 1e-9  # filled at 1.2, not at the 1.05 stop


def test_three_positions_at_most_and_one_x_leverage():
    syms = ("A", "B", "C", "D", "BTCUSDT")
    m = _market(symbols=syms)
    sigs = [rr.Signal(50, s, ((s, "BUY", 1 / 3),), 80) for s in syms[:4]]
    run = rr.simulate(m, sigs, 0, len(m.times))
    assert len(run.trades) == 3
    # two half-size positions fill the 1x margin: a third does not fit
    sigs = [rr.Signal(50, s, ((s, "BUY", 0.5),), 80) for s in syms[:3]]
    run = rr.simulate(m, sigs, 0, len(m.times))
    assert len(run.trades) == 2 and run.skipped == 1
    # a window ignores entries outside it and closes everything at its end
    run = rr.simulate(m, sigs, 60, 70)
    assert run.trades == []
    run = rr.simulate(m, [rr.Signal(60, "A", (("A", "BUY", 0.5),), 500)], 60, 70)
    assert run.trades[0]["why"] == "fin de ventana" and run.trades[0]["exit_at"] == m.times[69].isoformat()


def test_rotation_holds_the_strongest_and_trades_only_changes():
    drifts = {"SOLUSDT": 0.002, "XRPUSDT": 0.0015, "ADAUSDT": 0.001, "ETHUSDT": -0.002}
    m = _market(drifts=drifts, vol=0.001)
    sigs = rr.rotation_signals(m, 24 * 10, len(m.times), lookback=7, rebalance=1, mode="largo3")
    keys = {s.key for s in sigs}
    assert keys == {"SOLUSDT", "XRPUSDT", "ADAUSDT"}
    assert len(sigs) == 3  # held all along: one trade each, closed at the window's end
    assert all(s.legs[0][1] == "BUY" and s.exit_i == len(m.times) for s in sigs)
    assert all(m.times[s.i].hour == 0 for s in sigs)
    ls = rr.rotation_signals(m, 24 * 10, len(m.times), lookback=7, rebalance=7, mode="ls")
    assert {(s.key, s.legs[0][1], s.legs[0][2]) for s in ls} == {("SOLUSDT", "BUY", 0.5), ("ETHUSDT", "SELL", 0.5)}


def test_rotation_btc_filter_keeps_longs_out_when_btc_is_below_its_mean():
    m = _market(n=24 * 80, drifts={"BTCUSDT": -0.001, "SOLUSDT": 0.002}, vol=0.001)
    assert rr.rotation_signals(m, 24 * 60, len(m.times), 7, 1, "largo3_btc50") == []
    assert rr.rotation_signals(m, 24 * 60, len(m.times), 7, 1, "largo3") != []


def test_pairs_short_the_rich_leg_and_exit_at_zero():
    n = 24 * 30
    m = _market(n=n, symbols=("ETHUSDT", "BTCUSDT", "SOLUSDT"), vol=0.0005)
    k = 24 * 20
    eth = m.close["ETHUSDT"].copy()
    eth.iloc[k:k + 10] *= 1.05  # ETH rich against BTC for 10 hours, then back
    for f in ("open", "high", "low", "close"):
        m.__dict__[f]["ETHUSDT"] = eth
    sigs = [s for s in rr.pairs_signals(m, lookback=7, z_in=2.0, z_stop=None) if s.key == "ETH/BTC"]
    hit = [s for s in sigs if k <= s.i <= k + 2]
    assert hit, "the jump must open a pair trade"
    s = hit[0]
    assert dict((sym, side) for sym, side, _ in s.legs) == {"ETHUSDT": "SELL", "BTCUSDT": "BUY"}
    assert s.exit_why == "z=0" and k + 9 <= s.exit_i <= k + 13
    run = rr.simulate(m, [s], 0, n)
    assert run.trades[0]["side"] == "PAR" and run.trades[0]["pnl"] > 0


def test_reversion_waits_for_a_weak_trend():
    trend = _market(n=24 * 20, symbols=("SOLUSDT", "BTCUSDT"), drifts={"SOLUSDT": 0.004, "BTCUSDT": 0.004}, vol=0.001)
    assert all(s.legs[0][1] == "SELL" for s in rr.reversion_signals(trend, "rsi2", 6, 1.5)) is True
    assert len(rr.reversion_signals(trend, "rsi2", 6, 1.5)) < 5  # ADX high: almost nothing
    flat = _market(n=24 * 20, symbols=("SOLUSDT", "BTCUSDT"), vol=0.004, seed=3)
    sigs = rr.reversion_signals(flat, "bb2", 6, 1.5)
    assert sigs
    s = sigs[0]
    side = s.legs[0][1]
    c = flat.close[s.key].iloc[s.i - 1]
    assert (s.stop < c) == (side == "BUY") and s.exit_i == s.i + 6
    if s.target is not None:
        assert (s.target > c) == (side == "BUY")


def test_indicators_are_sane():
    m = _market(n=500, symbols=("SOLUSDT", "BTCUSDT"))
    c, h, low = m.close["SOLUSDT"], m.high["SOLUSDT"], m.low["SOLUSDT"]
    r = rr.rsi(c, 2).dropna()
    assert ((r >= 0) & (r <= 100)).all()
    up = pd.Series(np.arange(1.0, 101.0))
    assert rr.rsi(up, 4).iloc[-1] == 100.0
    a = rr.adx(h, low, c).dropna()
    assert ((a >= 0) & (a <= 100)).all()
    assert (rr.atr(h, low, c).dropna() > 0).all()


def test_windows_fit_90_test_30_roll_30():
    m = _market(n=24 * 300, symbols=("BTCUSDT", "ETHUSDT"))
    wins = rr.windows(m, 120)
    assert len(wins) == 4
    assert wins[-1][2] == len(m.times)
    for flo, lo, hi in wins:
        assert lo - flo == 90 * 24 and hi - lo == 30 * 24 and flo >= rr.WARM_DAYS * 24
    assert all(wins[k][2] == wins[k + 1][1] for k in range(3))


def test_chain_metrics_and_quarters():
    idx1 = pd.date_range("2026-03-01", periods=24 * 30, freq="1h", tz="UTC")
    idx2 = pd.date_range(idx1[-1] + pd.Timedelta(hours=1), periods=24 * 30, freq="1h", tz="UTC")
    c1 = pd.Series(np.linspace(1000, 1100, len(idx1)), index=idx1)
    c2 = pd.Series(np.linspace(1000, 950, len(idx2)), index=idx2)
    full = rr.chain([c1, c2])
    assert full.iloc[-1] == pytest.approx(1050)
    s = rr.metrics([{"pnl": 100.0, "fees": 1.0, "funding": 0.5}, {"pnl": -50.0, "fees": 1.0, "funding": 0.0}], full)
    assert s["neto_pct"] == pytest.approx(5.0)
    assert s["max_caida_pct"] == pytest.approx(50 / 1000 * 100, rel=1e-3)  # in % of the capital
    assert s["acierto_pct"] == 50.0 and s["factor_beneficio"] == 2.0
    assert sum(s["trimestres"].values()) == pytest.approx(5.0, abs=0.05)
    assert set(s["trimestres"]) == {"2026-T1", "2026-T2"}


def test_verdict_rules():
    oos = {"operaciones": 150, "neto_pct": 20.0, "neto_caida": 3.0, "trimestres_positivos": "3/4"}
    desk = {"neto_caida": 2.0}
    assert rr.verdict(oos, desk, 0.5, None, None)[1] is True
    assert rr.verdict({**oos, "operaciones": 50}, desk, 0.5, None, None)[0].startswith("muestra corta")
    assert rr.verdict({**oos, "trimestres_positivos": "2/4"}, desk, 0.5, None, None)[1] is False
    weaker = {**oos, "neto_caida": 1.0}
    assert rr.verdict(weaker, desk, 0.1, {"neto_caida": 2.5}, 2.0)[0].startswith("SUMA")
    assert rr.verdict(weaker, desk, 0.6, {"neto_caida": 2.5}, 2.0)[1] is False
    assert rr.verdict({**oos, "neto_pct": -1.0}, desk, 0.1, None, None)[0] == "pierde fuera de muestra"
    # adding to the desk also needs 3 positive quarters out of 4; a survivor-biased universe never counts
    assert rr.verdict({**weaker, "trimestres_positivos": "3/5"}, desk, 0.1, {"neto_caida": 2.5}, 2.0)[1] is False
    assert rr.verdict(oos, desk, 0.1, None, None, biased=True)[1] is False


def test_drawdown_of_summed_windows_is_in_percent_of_capital():
    idx = pd.date_range("2026-01-01", periods=4, freq="1h", tz="UTC")
    assert rr.max_dd_pct(pd.Series([900.0, 400.0, -100.0, 0.0], index=idx)) == pytest.approx(110.0)
    assert rr.max_dd_pct(pd.Series([1200.0, 1500.0, 1400.0, 1600.0], index=idx)) == pytest.approx(10.0)


def test_study_end_to_end_without_the_desk(tmp_path):
    syms = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "BNBUSDT")
    m = _market(n=24 * 220, symbols=syms, drifts={"SOLUSDT": 0.0003}, seed=7)
    wins = rr.windows(m, 60)
    assert len(wins) == 2
    small = {"rotacion": rr.GRIDS["rotacion"][:3], "reversion": rr.GRIDS["reversion"][:2],
             "pares": rr.GRIDS["pares"][:2]}
    old = dict(rr.GRIDS)
    rr.GRIDS.update(small)
    try:
        result = rr.study(m, wins, {"rotacion": m, "reversion": m, "pares": m}, None)
    finally:
        rr.GRIDS.update(old)
    assert set(result["familias"]) == {"rotacion", "reversion", "pares"}
    for r in result["familias"].values():
        assert len(r["folds"]) == 2
        assert not math.isnan(r["oos"]["neto_pct"])
        assert r["veredicto"]
    text = rr.render(result, {"desde": "2026-06-01", "hasta": "2026-08-01", "ventanas": 2})
    assert "Veredicto" in text and "BTC comprar y mantener" in text


def test_walk_forward_stays_flat_when_the_fit_loses():
    m = _market(n=24 * 200, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"))
    wins = rr.windows(m, 30)
    always_lose = [{"lookback": 7, "rebalance": 1, "mode": "ls"}]
    orig = rr.simulate

    def losing(mk, sigs, lo, hi, capital=rr.CAPITAL):
        run = orig(mk, sigs, lo, hi, capital)
        if lo == wins[0][0]:  # the fit window
            run.curve = run.curve * 0 + capital - 10
            run.trades = [{"pnl": -1.0, "fees": 0.0, "funding": 0.0}] * 10
        return run

    rr.simulate = losing
    try:
        r = rr.walk_forward(m, "rotacion", always_lose, wins)
    finally:
        rr.simulate = orig
    assert r["folds"][0]["elegida"] is None and r["oos"]["operaciones"] == 0 and r["oos"]["neto_pct"] == 0.0
