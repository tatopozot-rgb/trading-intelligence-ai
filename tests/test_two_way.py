"""The shared two-way engine: the Spot program's rules (loss limit with a warning, goal, trailing stop)
and the two-way signals, on a fake broker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        self.px = Decimal("100")
        self.hide = False  # the account does not show positions (to test the double check)
        self.volume = 1.0
        self.fail = 0  # this many calls to equity() raise, like an exchange outage
        self.moved: list[tuple[str, Decimal]] = []
        self.closed: list[str] = []

    def equity(self):
        if self.fail > 0:
            self.fail -= 1
            raise RuntimeError("exchange down")
        return self.eq, "USDT"

    def positions(self):
        return {} if self.hide else dict(self.pos)

    def candles(self, symbol, timeframe, count):
        c = float(self.px)
        idx = pd.date_range(end=NOW, periods=count, freq="5min")
        vol = np.full(count, 1.0)
        vol[-2] = self.volume
        return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": vol}, index=idx)

    def plan(self, symbol, side, risk_pct, timeframe):
        self.last_risk = risk_pct
        sl = self.px - 3 if side == "BUY" else self.px + 3
        tp = self.px + self.reward if side == "BUY" else self.px - self.reward
        return T.Plan(symbol, side, Decimal("0.1"), self.px, sl, tp, Decimal("0.3"))

    reward = Decimal("6")

    def open(self, plan):
        self.pos[plan.symbol] = T.Position(plan.symbol, plan.side, plan.qty, f"t-{plan.symbol}", plan.price)
        return f"t-{plan.symbol}"

    def close(self, position):
        self.pos.pop(position.symbol)
        self.closed.append(position.symbol)

    def move_stop(self, position, stop, target):
        self.moved.append((position.symbol, stop))

    def price(self, symbol):
        return self.px


def _engine(tmp_path, sig, broker=None, **kw):
    broker = broker or FakeBroker()
    sent: list[str] = []
    auto = T.TwoWayAuto(broker, list(sig), tmp_path / "state.json", signal=lambda s, d, h=None, top=None: sig.get(s), pause=lambda s: None,
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
    b.px = Decimal("102")
    auto.step()
    assert b.moved == []  # below +1R
    b.px = Decimal("103")
    auto.step()
    assert b.moved == [("SOLUSDT", Decimal("101.5"))]  # R/2 behind
    b.px = Decimal("102.5")
    auto.step()
    assert len(b.moved) == 1  # never back down


def test_a_short_trails_downward(tmp_path):
    sig = {"SOLUSDT": "SELL"}
    auto, b, _ = _engine(tmp_path, sig)
    auto.step()  # entry 100, stop 103
    b.px = Decimal("96")
    auto.step()
    assert b.moved == [("SOLUSDT", Decimal("97.5"))]


def test_state_from_the_first_version_still_loads(tmp_path):
    (tmp_path / "state.json").write_text('{"day": "2026-10-10", "known": {"EURUSD": "1001"}}')
    s = T.State.load(tmp_path / "state.json")
    assert s.known == {"EURUSD": {"ticket": "1001"}} and s.status == T.RUNNING


# --- owner, 2026-10-10: risk 1-15% with the signal, bots per position, Telegram verified twice ---------

def test_risk_goes_from_1_to_15_percent_with_the_signals_quality(tmp_path):
    auto, b, _ = _engine(tmp_path, {})
    assert (auto.risk_for(0.0), auto.risk_for(0.5), auto.risk_for(1.0)) == (Decimal("1.00"), Decimal("8.00"),
                                                                         Decimal("15.00"))
    sig = {"SOLUSDT": ("BUY", 1.0)}
    auto2, b2, _ = _engine(tmp_path / "x", sig)
    auto2.step()
    assert b2.last_risk == Decimal("15.00")  # the strongest signal uses the owner's top risk


def test_risk_never_grows_after_a_loss(tmp_path):
    sig = {"SOLUSDT": ("BUY", 0.5)}
    auto, b, _ = _engine(tmp_path, sig)
    auto.step()
    first = b.last_risk
    b.pos.clear()  # stopped out
    b.eq = Decimal("95")
    auto.step()
    assert b.last_risk == first  # same signal, same risk: losses do not change it


def test_nothing_reaches_telegram_as_opened_unless_the_account_shows_it_twice(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    b = FakeBroker()
    b.hide = True
    auto, b, sent = _engine(tmp_path, sig, broker=b)
    auto.step()
    assert not any("Compré" in m for m in sent)
    assert any("No la doy por abierta" in m for m in sent)
    b.hide = False
    sent.clear()
    auto2, _, sent2 = _engine(tmp_path / "y", sig)
    auto2.step()
    assert any("Compré" in m and "Verificado 2 veces" in m and "Bot SOLUSDT" in m for m in sent2)


def test_each_position_has_its_own_bot_that_watches_reports_and_trails(tmp_path):
    sig = {"SOLUSDT": "BUY", "XRPUSDT": "SELL"}
    t = {"now": NOW}
    b = FakeBroker()
    sent: list[str] = []
    auto = T.TwoWayAuto(b, list(sig), tmp_path / "s.json", signal=lambda s, d, h=None, top=None: sig.get(s),
                        pause=lambda s: None, notify=sent.append, clock=lambda: t["now"])
    auto.step()
    sent.clear()
    t["now"] = NOW + timedelta(seconds=30)
    b.px = Decimal("103")  # +1R for the long, against the short
    auto.watch()
    reports = [m for m in sent if m.startswith("📍")]
    assert any("Bot SOLUSDT" in m for m in reports) and any("Bot XRPUSDT" in m for m in reports)
    assert ("SOLUSDT", Decimal("101.5")) in b.moved  # the long's bot moved its stop between decisions
    sent.clear()
    t["now"] = NOW + timedelta(seconds=60)
    auto.watch()
    assert not [m for m in sent if m.startswith("📍")]  # next report only after 2 minutes
    t["now"] = NOW + timedelta(seconds=160)
    auto.watch()
    assert len([m for m in sent if m.startswith("📍")]) == 2


# --- the desk: Scout, Skeptic, kill switch ---------------------------------------------------------

def test_the_skeptic_vetoes_a_poor_reward_risk_and_scores_the_veto_later(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    b = FakeBroker()
    b.reward = Decimal("3")  # 1:1, under the 1.5:1 rule
    auto, b, sent = _engine(tmp_path, sig, broker=b, desk_rules=T.D.DeskRules(), journal_dir=tmp_path / "mesa")
    auto.step()
    assert not b.pos and any("Escéptico" in m and "beneficio/riesgo" in m for m in sent)
    assert auto.state.vetoes and auto.state.vetoes[0]["side"] == "BUY"
    sent.clear()
    auto.step()
    assert not any("Escéptico" in m for m in sent)  # not re-proposed every 30 s
    b.px = Decimal("96.5")  # the refused long would have hit its stop (97)
    auto._score_vetoes()
    assert auto.state.veto_score["evitó pérdida"] == 1
    assert "Escéptico rechaza BUY SOLUSDT" in (tmp_path / "mesa" / "2026-10-12.md").read_text(encoding="utf-8")


def test_the_scout_alerts_the_chief_who_evaluates_at_once(tmp_path):
    sig = {"SOLUSDT": "SELL"}
    b = FakeBroker()
    b.volume = 3.0  # 3x the usual volume on the last closed bar
    auto, b, sent = _engine(tmp_path, sig, broker=b, desk_rules=T.D.DeskRules())
    auto.watch()  # no scheduled decision: the Scout alone triggers the evaluation
    assert any(m.startswith("📡 Scout") and "3.0x" in m for m in sent)
    assert "SOLUSDT" in b.pos and b.pos["SOLUSDT"].side == "SELL"


def test_kill_switch_stops_new_entries_after_three_failures_and_resumes(tmp_path):
    sig = {"SOLUSDT": None}
    b = FakeBroker()
    b.fail = 3
    t = {"now": NOW}
    sent: list[str] = []
    auto = T.TwoWayAuto(b, list(sig), tmp_path / "s.json", signal=lambda s, d, h=None, top=None: sig.get(s),
                        pause=lambda s: None, notify=sent.append, clock=lambda: t["now"], outside_every_min=5)

    def tick(seconds):
        t["now"] += timedelta(seconds=seconds)

    auto.run(max_iterations=1, sleep=tick)
    for _ in range(2):
        t["now"] += timedelta(minutes=5)
        auto.run(max_iterations=1, sleep=lambda s: None)
    assert auto.state.status == T.PAUSED_API and any("fallos seguidos" in m for m in sent)
    t["now"] += timedelta(minutes=5)
    auto.run(max_iterations=1, sleep=lambda s: None)
    assert auto.state.status == T.RUNNING and any("la conexión volvió" in m for m in sent)


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
    out = signal_for("tendencia_rango_1h")("SOLUSDT", bars, hourly)
    assert out is None or (out[0] == "SELL" and 0 <= out[1] <= 1)
    regime_only = signal_for("regimen")("SOLUSDT", bars, None)
    assert regime_only is None or regime_only[0] != "BUY"
