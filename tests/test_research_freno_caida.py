"""Tests for the drawdown brake (research_mesa.replay dd_brake and research_freno_caida, synthetic, no network)."""
import numpy as np
import pytest

from trading_intelligence.backtesting import research_freno_caida as rf
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.live import desk as D


def _sym(n=600, at=(10,), stop=95.0):
    close = np.full(n, 100.0)
    side = np.zeros(n, dtype=np.int8)
    side[list(at)] = 1
    return rm.Sym(np.arange(n, dtype=np.int64), close, close * 1.001, close * 0.999, close, side, np.full(n, 0.5),
                  np.where(side != 0, stop, np.nan), np.zeros(n), np.full(n, np.nan), np.zeros(n, bool))


FIXED = rm.Sizing("fijo 2%", 0.02)


def _replay(**kw):
    return rm.replay({"XUSDT": _sym()}, 0, 600, sizing=FIXED, rules=D.DeskRules(), slippage=0.0, capital=1000.0, **kw)


def test_without_the_brake_nothing_changes():
    a, b = _replay(), _replay(dd_brake=None, peak=5000.0)
    assert a.trades == b.trades and a.trades[0]["risk_usdt"] == pytest.approx(20.0, rel=1e-6)


def test_ten_percent_down_halves_the_risk():
    rep = _replay(dd_brake=rf.BRAKE, peak=1150.0)
    assert rep.trades[0]["risk_usdt"] == pytest.approx(10.0, rel=1e-6)
    assert rep.halved == 1 and not rep.paused


def test_under_ten_percent_full_risk():
    rep = _replay(dd_brake=rf.BRAKE, peak=1090.0)
    assert rep.trades[0]["risk_usdt"] == pytest.approx(20.0, rel=1e-6) and rep.halved == 0


def test_twenty_percent_down_blocks_entries_and_a_pause_carries_in():
    rep = _replay(dd_brake=rf.BRAKE, peak=1300.0)
    assert rep.trades == [] and rep.paused
    rep = _replay(dd_brake=rf.BRAKE, peak=1000.0, paused=True)
    assert rep.trades == [] and rep.paused


def test_brake_never_raises_risk():
    rep = _replay(dd_brake=rf.BRAKE, peak=900.0)  # a stale peak below the capital is ignored
    assert rep.peak == pytest.approx(1000.0) and rep.trades[0]["risk_usdt"] == pytest.approx(20.0, rel=1e-6)


class _Fake:
    """A replay that loses 25% in the first block and records what each block received."""

    def __init__(self):
        self.calls = []

    def __call__(self, syms, lo, hi, *, capital, peak, paused, dd_brake, **kw):
        self.calls.append({"capital": capital, "peak": peak, "paused": paused})
        loss = -0.25 * capital if lo == 0 else 0.0
        rep = rm.Replay(trades=[{"pnl": loss, "symbol": "X", "fees": 0.0, "funding": 0.0}],
                        curve=[capital, capital + loss], peak=max(capital, peak),
                        paused=paused or (dd_brake is not None and loss < 0))
        return rep


def test_pause_resets_the_peak_at_the_next_block_only_with_review():
    bounds = [(0, 10), (10, 20), (20, 30)]
    fake = _Fake()
    run = rf.run_chained({}, bounds, 1000.0, FIXED, True, True, replay=fake)
    assert fake.calls[1] == {"capital": 750.0, "peak": 750.0, "paused": False}
    assert run["pauses"] == 1
    fixed = _Fake()
    rf.run_chained({}, bounds, 1000.0, FIXED, True, False, replay=fixed)
    assert fixed.calls[1]["paused"] and fixed.calls[2]["paused"] and fixed.calls[2]["peak"] == 1000.0


def test_no_pause_carries_the_peak():
    fake = _Fake()
    rf.run_chained({}, [(0, 10), (10, 20)], 1000.0, FIXED, False, True, replay=fake)
    assert fake.calls[1] == {"capital": 750.0, "peak": 1000.0, "paused": False}


def test_rows_and_pass_rule():
    assert sum(v[4] == "decisoria" for v in rf.ROWS.values()) == 2
    assert rf.ROWS["f3x"][1].leverage == 3.0
    years = [{"desk": 1.67, "rows": {"f1x": {"net_dd": 2.0, "dsr": 0.1}}},
             {"desk": -0.21, "rows": {"f1x": {"net_dd": 0.5, "dsr": 0.96}}}]
    assert rf.passes(years, "f1x")
    years[-1]["rows"]["f1x"]["dsr"] = 0.5
    assert not rf.passes(years, "f1x")
