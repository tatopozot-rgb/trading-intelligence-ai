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
                        notify=sent.append, chatter=sent.append, clock=lambda: NOW, **kw)
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


def test_at_the_monthly_goal_everything_closes_and_trading_resumes_next_month(tmp_path):
    sig = {"SOLUSDT": "SELL"}
    now = [NOW]
    broker = FakeBroker()
    sent: list[str] = []
    auto = T.TwoWayAuto(broker, list(sig), tmp_path / "state.json", signal=lambda s, d, h=None, top=None: sig.get(s),
                        pause=lambda s: None, notify=sent.append, clock=lambda: now[0])
    auto.step()
    broker.eq = Decimal("158")
    auto.step()
    assert auto.state.status == T.GOAL and not broker.pos and any("meta del mes cumplida" in m for m in sent)
    auto.step()
    assert not broker.pos  # no new entries for the rest of the month
    now[0] = datetime(2026, 11, 2, 13, 0, tzinfo=timezone.utc)
    auto.step()
    assert auto.state.status == T.RUNNING and auto.state.month_start_equity == "158" and "SOLUSDT" in broker.pos
    assert any("empieza 2026-11" in m for m in sent)


def test_an_owner_set_monthly_goal_in_dollars(tmp_path):
    auto, b, sent = _engine(tmp_path, {"SOLUSDT": None}, goal_usd=Decimal("20"))
    auto.step()
    b.eq = Decimal("121")
    auto.step()
    assert auto.state.status == T.GOAL and any("meta 20.00" in m for m in sent)


def test_a_warning_needs_two_reads_of_the_account(tmp_path):
    auto, b, sent = _engine(tmp_path, {"SOLUSDT": None})
    auto.step()  # capital 100: warning at 43 USD of loss
    reads = iter([(Decimal("56"), "USDT"), (Decimal("80"), "USDT")])  # the second read disagrees
    b.equity = lambda: next(reads)
    auto.step()
    assert auto.state.status == T.RUNNING and not any("del límite" in m for m in sent)


def test_desk_chatter_never_reaches_telegram(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    b = FakeBroker()
    b.reward = Decimal("3")  # vetoed by the Skeptic
    telegram: list[str] = []
    console: list[str] = []
    auto = T.TwoWayAuto(b, list(sig), tmp_path / "state.json", signal=lambda s, d, h=None, top=None: sig.get(s),
                        pause=lambda s: None, notify=telegram.append, chatter=console.append, clock=lambda: NOW,
                        desk_rules=T.D.DeskRules())
    auto.step()
    assert any("Escéptico" in m for m in console) and not any("Escéptico" in m for m in telegram)


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
    assert any("Compré" in m and "Verificado 2 veces" in m and "Bot SOLUSDT" in m and "El plan: stop en" in m
               and "si llega gano" in m for m in sent2)


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


# --- bull-run mode and the 3-5% take profit (owner, 2026-10-11) ----------------------------------------

class RallyBroker(FakeBroker):
    """Daily bars of a coin that rose 40% in two weeks and is still rising."""

    def candles(self, symbol, timeframe, count):
        if timeframe != "1d":
            return super().candles(symbol, timeframe, count)
        idx = pd.date_range(end=NOW, periods=count, freq="1D")
        c = np.concatenate([np.full(count - 15, 70.0), np.linspace(70.0, 100.0, 15)])
        return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1.0}, index=idx)


def test_the_target_is_kept_between_3_and_5_percent(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    b = FakeBroker()
    b.reward = Decimal("12")  # the market's target is 12% away: taken at 5%
    auto, b, sent = _engine(tmp_path, sig, broker=b, desk_rules=T.D.DeskRules(target_max_pct=Decimal("5")))
    auto.step()
    assert Decimal(auto.state.known["SOLUSDT"]["target"]) == Decimal("105")
    assert auto.state.known["SOLUSDT"]["rally"] is False


def test_a_coin_in_a_bull_run_keeps_its_long_open_with_the_trailing_stop(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    auto, b, sent = _engine(tmp_path, sig, broker=RallyBroker(), desk_rules=T.D.DeskRules())
    auto.step()
    info = auto.state.known["SOLUSDT"]
    assert info["rally"] is True and Decimal(info["target"]) == Decimal("150")  # no 3-5% exit: only the trail
    assert any("Modo alcista" in m and "+43%" in m for m in sent)
    assert b.last_risk <= Decimal("15")  # "arriesgar algo no todo": the usual risk, never more
    sig["SOLUSDT"] = "SELL"  # a 5-minute dip does not close the bull-run long
    auto.step()
    assert "SOLUSDT" in b.pos and not b.closed
    b.px = Decimal("110")  # up 10%: the stop follows the gain
    auto.watch()
    assert b.moved and b.moved[-1][1] > Decimal("97")


def test_shorts_are_never_in_bull_run_mode(tmp_path):
    sig = {"SOLUSDT": "SELL"}
    auto, b, sent = _engine(tmp_path, sig, broker=RallyBroker(), desk_rules=T.D.DeskRules(target_max_pct=Decimal("5")))
    auto.step()
    assert auto.state.known["SOLUSDT"]["rally"] is False
    assert Decimal(auto.state.known["SOLUSDT"]["target"]) == Decimal("95")


def test_the_goal_is_confirmed_on_the_lower_of_two_reads(tmp_path):
    auto, b, sent = _engine(tmp_path, {"SOLUSDT": None}, goal_usd=Decimal("10"))
    auto.step()  # capital 100
    reads = iter([(Decimal("111"), "USDT"), (Decimal("105"), "USDT")])  # the second read is under the goal
    b.equity = lambda: next(reads)
    auto.step()
    assert auto.state.status == T.RUNNING and not any("meta del mes" in m for m in sent)


def test_a_close_that_failed_at_the_goal_is_retried(tmp_path):
    sig = {"SOLUSDT": "BUY"}
    auto, b, sent = _engine(tmp_path, sig)
    auto.step()
    assert "SOLUSDT" in b.pos
    real_close, calls = b.close, []

    def flaky(position):
        calls.append(position.symbol)
        if len(calls) == 1:
            raise RuntimeError("exchange down")
        real_close(position)
    b.close = flaky
    b.eq = Decimal("160")
    with pytest.raises(RuntimeError):
        auto.step()  # the goal is reached but the close fails
    b.eq = Decimal("160")
    auto.step()
    assert not b.pos and len(calls) == 2


def test_a_heartbeat_tells_the_owner_the_bot_is_alive_every_few_hours(tmp_path):
    now = [NOW]
    b = FakeBroker()
    sent: list[str] = []
    auto = T.TwoWayAuto(b, ["SOLUSDT"], tmp_path / "state.json", signal=lambda s, d, h=None, top=None: None,
                        pause=lambda s: None, notify=sent.append, chatter=lambda m: None, clock=lambda: now[0],
                        heartbeat_every_s=4 * 3600)
    auto.watch()
    assert not any("🫀" in m for m in sent)  # not at start-up
    now[0] = NOW + timedelta(hours=4, minutes=1)
    auto.watch()
    beat = [m for m in sent if "🫀" in m]
    assert len(beat) == 1 and "Saldo 100 USDT (revisado 2 veces)" in beat[0] and "Posiciones abiertas: 0" in beat[0]
    assert "Por qué: ninguna moneda dio una señal que pasara todas las reglas" in beat[0]  # the real reason, said
    now[0] += timedelta(minutes=30)
    auto.watch()
    assert len([m for m in sent if "🫀" in m]) == 1  # once per interval


class RegimeBroker(FakeBroker):
    """BTC daily bars that end above (up=True) or below (up=False) their 50-day mean."""

    up = True

    def candles(self, symbol, timeframe, count):
        if timeframe != "1d":
            return super().candles(symbol, timeframe, count)
        closes = np.linspace(100, 150, count) if self.up else np.linspace(150, 100, count)
        idx = pd.date_range(end=NOW - pd.Timedelta(hours=13), periods=count, freq="1D")
        return pd.DataFrame({"close": closes}, index=idx)


def test_the_regime_brake_allows_only_longs_above_btcs_mean_and_closes_the_rest(tmp_path):
    rules = T.D.DeskRules(target_min_pct=None, regime_btc_sma=50, min_reward_risk=Decimal("1"))
    sig = {"SOLUSDT": "SELL", "ETHUSDT": "BUY"}
    b = RegimeBroker()
    auto, b, sent = _engine(tmp_path, sig, broker=b, desk_rules=rules)
    auto.step()
    assert "SOLUSDT" not in b.pos and "ETHUSDT" in b.pos  # shorts are blocked even above the mean
    b.up = False
    auto._regime = (None, True)  # force a fresh read
    auto.step()
    assert "ETHUSDT" not in b.pos and "ETHUSDT" in b.closed  # below the mean: the long is closed
    assert any("freno de riesgo" in m for m in sent)
    auto.step()
    assert not b.pos  # and nothing new opens


def test_without_btc_data_the_brake_fails_closed(tmp_path):
    rules = T.D.DeskRules(target_min_pct=None, regime_btc_sma=50, min_reward_risk=Decimal("1"))
    sig = {"SOLUSDT": "BUY"}
    auto, b, sent = _engine(tmp_path, sig, desk_rules=rules)  # FakeBroker serves 5m bars for "1d": too short
    auto.step()
    assert "SOLUSDT" not in b.pos  # no new entry while the brake cannot read BTC


class ContractBroker(FakeBroker):
    """XM-like: 0.01 lot of a pair with a 100,000 contract; the broker's plan carries the money at risk."""

    def __init__(self):
        super().__init__(equity="1000")
        self.px = Decimal("0.69855")

    def plan(self, symbol, side, risk_pct, timeframe):
        return T.Plan(symbol, side, Decimal("0.01"), self.px, Decimal("0.69575"), Decimal("0.7069100000000000000000000003"),
                      Decimal("2.80"))


def test_messages_use_the_brokers_money_not_quantity_times_price(tmp_path):
    b = ContractBroker()
    auto, b, sent = _engine(tmp_path, {"AUDUSD": "BUY"}, broker=b)
    auto.step()
    opened = next(m for m in sent if "Compré" in m)
    assert "gano unos 8.36 USDT" in opened and "pierdo unos 2.80 USDT" in opened
    assert "meta en 0.70691 " in opened and "arriesgo 0.28% de la cuenta" in opened
    b.px = Decimal("0.69883")
    auto.watch()
    status = next(m for m in sent if m.startswith("📍"))
    assert "resultado +0.28 (+0.10R)" in status and "meta 0.70691." in status
