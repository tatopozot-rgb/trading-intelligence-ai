"""The shared two-way engine: the Spot program's rules (loss limit with a warning, goal, trailing stop)
and the two-way signals, on a fake broker."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.live import two_way as T
from trading_intelligence.regime.detector import Regime
from trading_intelligence.strategy.two_way_signals import Reading, decide, signal_for

NOW = datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc)


class FakeBroker:
    name, unit = "Fake", "unidades"

    def __init__(self, equity="100"):
        self.eq = Decimal(equity)
        self.pos: dict[str, T.Position] = {}
        self.price = Decimal("100")
        self.moved: list[tuple[str, Decimal]] = []
        self.closed: list[str] = []

    def equity(self):
        return self.eq, "USDT"

    def positions(self):
        return dict(self.pos)

    def candles(self, symbol, timeframe, count):
        c = float(self.price)
        idx = pd.date_range(end=NOW, periods=count, freq="5min")
        return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1.0}, index=idx)

    def plan(self, symbol, side, risk_pct, timeframe):
        sl = self.price - 3 if side == "BUY" else self.price + 3
        tp = self.price + 6 if side == "BUY" else self.price - 6
        return T.Plan(symbol, side, Decimal("0.1"), self.price, sl, tp, Decimal("0.3"))

    def open(self, plan):
        self.pos[plan.symbol] = T.Position(plan.symbol, plan.side, plan.qty, f"t-{plan.symbol}", plan.price)
        return f"t-{plan.symbol}"

    def close(self, position):
        self.pos.pop(position.symbol)
        self.closed.append(position.symbol)

    def move_stop(self, position, stop, target):
        self.moved.append((position.symbol, stop))


def _engine(tmp_path, sig, broker=None, **kw):
    broker = broker or FakeBroker()
    sent: list[str] = []
    auto = T.TwoWayAuto(broker, list(sig), tmp_path / "state.json", signal=lambda s, d, h=None: sig.get(s),
                        notify=sent.append, clock=lambda: NOW, **kw)
    return auto, broker, sent


# --- the Spot program's session rules --------------------------------------------------------------

def test_two_dollars_before_the_loss_limit_the_owner_is_asked_and_entries_pause(tmp_path):
    sig = {"SOLUSDT": None}
    auto, b, sent = _engine(tmp_path, sig)
    auto.step()  # capital 100: limit 45 USD, warning at 43
    b.eq = Decimal("56.5")
    sig["SOLUSDT"] = "BUY"
    auto.step()
    assert auto.state.status == T.WAITING_OWNER and not b.pos
    assert any("a 1.50 del límite" in m and "continuar" in m for m in sent)
    T.owner_continue(tmp_path)
    auto.step()
    assert auto.state.status == T.RUNNING and b.pos  # the owner said continue: trading resumes
    auto.step()
    assert auto.state.status == T.RUNNING  # and he is not asked again


def test_at_the_loss_limit_everything_closes_and_the_session_ends(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    auto, b, sent = _engine(tmp_path, sig)
    auto.step()
    assert b.pos
    b.eq = Decimal("55")
    auto.step()
    assert auto.state.status == T.STOPPED and not b.pos and any("límite de 45" in m for m in sent)
    auto.run(max_iterations=5, sleep=lambda s: None)
    assert not b.pos  # the loop does not trade after the end


def test_at_the_goal_everything_closes_and_the_session_ends(tmp_path):
    sig = {"SOLUSDT": "SELL"}
    auto, b, sent = _engine(tmp_path, sig)
    auto.step()
    b.eq = Decimal("158")
    auto.step()
    assert auto.state.status == T.GOAL and not b.pos and any("meta cumplida" in m for m in sent)


def test_the_stop_follows_the_gain_from_one_r_and_never_moves_back(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    auto, b, _ = _engine(tmp_path, sig)
    auto.step()  # entry 100, stop 97: R = 3
    b.price = Decimal("102")
    auto.step()
    assert b.moved == []  # below +1R
    b.price = Decimal("103")
    auto.step()
    assert b.moved == [("SOLUSDT", Decimal("101.5"))]  # R/2 behind
    b.price = Decimal("102.5")
    auto.step()
    assert len(b.moved) == 1  # never back down


def test_a_short_trails_downward(tmp_path):
    sig = {"SOLUSDT": "SELL"}
    auto, b, _ = _engine(tmp_path, sig)
    auto.step()  # entry 100, stop 103
    b.price = Decimal("96")
    auto.step()
    assert b.moved == [("SOLUSDT", Decimal("97.5"))]


def test_state_from_the_first_version_still_loads(tmp_path):
    (tmp_path / "state.json").write_text('{"day": "2026-10-10", "known": {"EURUSD": "1001"}}')
    s = T.State.load(tmp_path / "state.json")
    assert s.known == {"EURUSD": {"ticket": "1001"}} and s.status == T.RUNNING


# --- the signals ------------------------------------------------------------------------------------

def _r(regime, close=100.0, fast=101.0, slow=100.0, low=99.0, up=101.0, htf=None):
    return Reading(regime, close, fast, slow, low, up, htf)


def test_trend_needs_the_averages_to_agree_and_mirrors_for_shorts():
    assert decide(_r(Regime.TREND_UP), "tendencia_rango") == "BUY"
    assert decide(_r(Regime.TREND_UP, fast=99.0), "tendencia_rango") is None
    assert decide(_r(Regime.BREAKOUT_DOWN, fast=99.0), "tendencia_rango") == "SELL"
    assert decide(_r(Regime.TREND_UP, fast=99.0), "regimen") == "BUY"  # the regime alone ignores them


def test_a_range_buys_below_the_lower_band_and_sells_above_the_upper():
    assert decide(_r(Regime.RANGE, close=98.0), "tendencia_rango") == "BUY"
    assert decide(_r(Regime.RANGE, close=102.0), "tendencia_rango") == "SELL"
    assert decide(_r(Regime.RANGE, close=100.0), "tendencia_rango") is None
    assert decide(_r(Regime.RANGE, close=98.0), "regimen") is None


def test_never_against_the_one_hour_trend():
    assert decide(_r(Regime.TREND_UP, htf="SELL"), "tendencia_rango_1h") is None
    assert decide(_r(Regime.TREND_UP, htf="BUY"), "tendencia_rango_1h") == "BUY"
    assert decide(_r(Regime.RANGE, close=102.0, htf="BUY"), "tendencia_rango_1h") is None
    assert decide(_r(Regime.RANGE, close=102.0, htf=None), "tendencia_rango_1h") == "SELL"
    assert decide(_r(None), "tendencia_rango_1h") is None
    with pytest.raises(ValueError):
        decide(_r(Regime.RANGE), "otra")


def test_the_live_signal_reads_real_bars():
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(-0.002, 0.002, 400)))  # a steady fall
    idx = pd.date_range(end=NOW, periods=400, freq="5min")
    bars = pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 1.0}, index=idx)
    hourly = bars.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    assert signal_for("tendencia_rango_1h")("SOLUSDT", bars, hourly) in ("SELL", None)
    assert signal_for("regimen")("SOLUSDT", bars, None) != "BUY"
