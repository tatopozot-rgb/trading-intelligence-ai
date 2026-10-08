"""Copy trading: sources, evaluator, risk policy, PAPER follower and the end-to-end run.
All data here is synthetic; the RiskEngine is the real one."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading_intelligence.copy_trading import demo
from trading_intelligence.copy_trading import evaluator as E
from trading_intelligence.copy_trading.follower import CopyFollower, ExecutionModel, LiveTradingNotAuthorized
from trading_intelligence.copy_trading.models import LeaderAction, LeaderEvent, Market, Side, TraderRecord
from trading_intelligence.copy_trading.pipeline import record_as_of, render, state_of
from trading_intelligence.copy_trading.risk import CopyRiskConfig, CopyRiskPolicy, PositionView
from trading_intelligence.copy_trading.sources import (
    OFFICIAL_COPY_TRADING_ENDPOINTS,
    UnverifiedSource,
    parse_snapshot,
)
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.risk.engine import RiskEngine

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _engine(tmp_path, **cfg):
    return RiskEngine(replace(demo.DEMO_RISK, **cfg), tmp_path / "risk.json", AuditLog(tmp_path / "audit"))


def _record(**kw) -> TraderRecord:
    base = dict(
        trader_id="t", name="t", market=Market.SPOT, source="binance_app_manual", captured_at=NOW, active=True,
        daily_returns=tuple(Decimal("0.002") if i % 3 else Decimal("-0.001") for i in range(300)),
        symbol_share={"BTCUSDT": Decimal("0.5"), "ETHUSDT": Decimal("0.5")},
        closed_trade_pnls=tuple(Decimal(10 + i % 7) for i in range(30)),
    )
    base.update(kw)
    return TraderRecord(**base)


def _event(action="OPEN", fraction="0.5", price="100", side="LONG", h=0.0, trader="t", symbol="BTCUSDT", lev="1"):
    return LeaderEvent(trader, NOW + timedelta(hours=h), symbol, LeaderAction(action), Side(side),
                       Decimal(price), Decimal(fraction), Decimal(lev))


# ---------------------------------------------------------------- sources


class TestSources:
    def test_only_official_channels_are_accepted(self):
        data = demo.snapshot_data()
        with pytest.raises(UnverifiedSource):
            parse_snapshot(data)  # synthetic, not allowed by default
        for bad in ("binance_leaderboard_scraper", "apify", ""):
            with pytest.raises(UnverifiedSource):
                parse_snapshot({**data, "source": bad}, allow_synthetic=True)
        assert parse_snapshot({**data, "source": "binance_app_manual"}).traders

    def test_events_after_the_capture_time_are_look_ahead(self):
        data = demo.snapshot_data()
        data["events"][0]["ts"] = (demo.CAPTURED_AT + timedelta(hours=1)).isoformat()
        with pytest.raises(ValueError, match="look-ahead"):
            parse_snapshot(data, allow_synthetic=True)

    def test_impossible_events_are_refused(self):
        with pytest.raises(ValueError):
            _event(price="0")
        with pytest.raises(ValueError):
            _event(action="CLOSE", fraction="0.3")
        with pytest.raises(ValueError):
            _event(fraction="-0.1")

    def test_the_official_api_is_lead_trader_only(self):
        assert set(OFFICIAL_COPY_TRADING_ENDPOINTS) == {
            "/sapi/v1/copyTrading/futures/userStatus", "/sapi/v1/copyTrading/futures/leadSymbol"}


# ---------------------------------------------------------------- evaluator


class TestEvaluator:
    C = E.SelectionCriteria()

    def test_a_sound_record_is_eligible(self):
        assert E.evaluate(_record(), self.C).failed == []

    @pytest.mark.parametrize("kw,reason", [
        ({"active": False}, E.INACTIVE),
        ({"market": Market.USDM_FUTURES}, E.MARKET_NOT_ALLOWED),
        ({"daily_returns": (Decimal("0.01"),) * 60}, E.HISTORY_TOO_SHORT),
        ({"closed_trade_pnls": (Decimal("5"),) * 5}, E.TOO_FEW_TRADES),
        ({"closed_trade_pnls": (Decimal("1000"),) + (Decimal("1"),) * 29}, E.PROFIT_CONCENTRATED_IN_FEW_TRADES),
        ({"closed_trade_pnls": ()}, E.PROFIT_CONCENTRATED_IN_FEW_TRADES),  # unknown fails closed
        ({"symbol_share": {"BTCUSDT": Decimal("0.9"), "ETHUSDT": Decimal("0.1")}}, E.SYMBOL_CONCENTRATED),
        ({"symbol_share": {"PEPEUSDT": Decimal("0.5"), "FLOKIUSDT": Decimal("0.5")}}, E.ILLIQUID_SYMBOLS),
        ({"symbol_share": {}}, E.ILLIQUID_SYMBOLS),
        ({"max_leverage": Decimal("5")}, E.LEVERAGE_TOO_HIGH),
    ])
    def test_each_criterion_names_itself(self, kw, reason):
        assert reason in E.evaluate(_record(**kw), self.C).failed

    def test_deep_drawdown_and_losses_are_rejected(self):
        crash = tuple(Decimal("0.003") for _ in range(150)) + tuple(Decimal("-0.02") for _ in range(30)) + \
            tuple(Decimal("0.003") for _ in range(150))
        failed = E.evaluate(_record(daily_returns=crash), self.C).failed
        assert E.DRAWDOWN_TOO_DEEP in failed

    def test_shrinkage_discounts_short_records(self):
        long_m = E.compute_metrics(_record(), self.C)
        short_m = E.compute_metrics(_record(daily_returns=_record().daily_returns[:90]), self.C)
        assert short_m.annual_net_return == pytest.approx(long_m.annual_net_return, rel=0.2)
        assert short_m.shrunk_annual_return < long_m.shrunk_annual_return / 2

    def test_profit_share_is_paid_on_gains(self):
        free = E.compute_metrics(_record(profit_share_pct=Decimal("0")), self.C)
        paid = E.compute_metrics(_record(profit_share_pct=Decimal("30")), self.C)
        assert paid.total_net_return < free.total_net_return

    def test_a_universe_without_quitters_is_flagged_as_survivorship(self):
        stats = E.universe_stats([E.evaluate(_record(), self.C)])
        assert stats.survivorship_warning and stats.inactive == 0
        both = E.universe_stats([E.evaluate(_record(), self.C), E.evaluate(_record(trader_id="q", active=False), self.C)])
        assert both.survivorship_warning is None and both.inactive == 1

    def _evals(self, scores: dict[str, float]):
        out = []
        for tid, score in scores.items():
            ev = E.evaluate(_record(trader_id=tid, name=tid), self.C)
            ev.metrics.score = Decimal(str(score))
            out.append(ev)
        return out

    def test_selection_has_hysteresis(self):
        c = replace(self.C, max_selected=2)
        evals = self._evals({"a": 1.0, "b": 0.8, "c": 0.9})
        first = E.selected_ids(E.select(evals, c))
        assert first == {"a", "c"}
        # c slips below b, but not by the displacement margin: it stays.
        evals = self._evals({"a": 1.0, "b": 0.95, "c": 0.9})
        assert E.selected_ids(E.select(evals, c, incumbents=first)) == {"a", "c"}
        # b becomes materially better than c: c is displaced (wind-down, not invalidated).
        evals = self._evals({"a": 1.0, "b": 1.5, "c": 0.9})
        decisions = {d.trader_id: d for d in E.select(evals, c, incumbents=first)}
        assert decisions["b"].decision == "ADD" and decisions["c"].decision == "REMOVE_WIND_DOWN"

    def test_an_incumbent_that_breaks_a_hard_criterion_is_invalidated(self):
        evals = [E.evaluate(_record(trader_id="a", active=False), self.C)]
        decisions = E.select(evals, self.C, incumbents=frozenset({"a", "gone"}))
        by = {d.trader_id: d for d in decisions}
        assert by["a"].decision == "REMOVE_INVALIDATED" and E.INACTIVE in by["a"].reasons
        assert by["gone"].decision == "REMOVE_INVALIDATED"

    def test_selection_uses_only_data_available_before_the_first_event(self):
        r = _record()
        earlier = record_as_of(r, NOW - timedelta(days=10))
        assert earlier.history_days == r.history_days - 10


class TestReportedAppFigures:
    """What the Binance app actually shows: ROI windows, MDD, lead days, trades."""

    C = E.SelectionCriteria()

    def _rep(self, **kw):
        from trading_intelligence.copy_trading.models import ReportedStats

        base = dict(roi_pct_by_days={7: Decimal("1"), 30: Decimal("4"), 90: Decimal("9"), 180: Decimal("20")},
                    max_drawdown_pct=Decimal("12"), lead_days=400, trades=120)
        base.update(kw)
        return _record(daily_returns=(), reported=ReportedStats(**base))

    def test_a_sound_reported_record_is_eligible_and_flagged_as_coarser(self):
        ev = E.evaluate(self._rep(), self.C)
        assert ev.failed == [] and ev.metrics.basis == "reported_windows"
        assert ev.metrics.max_drawdown == Decimal("0.12") and ev.metrics.trades == 120

    def test_only_windows_inside_the_lead_period_count(self):
        m = E.compute_metrics(self._rep(lead_days=100, roi_pct_by_days={30: Decimal("4"), 180: Decimal("90")}), self.C)
        assert m.history_days == 100 and m.annual_net_return < Decimal("1")  # the 180-day 90% is ignored
        assert E.HISTORY_TOO_SHORT in E.evaluate(self._rep(lead_days=100), self.C).failed

    def test_reported_drawdown_and_losing_windows_are_judged(self):
        failed = E.evaluate(self._rep(max_drawdown_pct=Decimal("45"),
                                      roi_pct_by_days={30: Decimal("-6"), 90: Decimal("-3"), 180: Decimal("5")}),
                            self.C).failed
        assert E.DRAWDOWN_TOO_DEEP in failed and E.INCONSISTENT in failed

    def test_snapshot_parsing_and_no_rewinding(self):
        data = {"source": "binance_app_manual", "captured_at": NOW.isoformat(), "traders": [{
            "trader_id": "x", "market": "SPOT", "active": True, "symbol_share": {"BTCUSDT": "0.5", "ETHUSDT": "0.5"},
            "closed_trade_pnls": ["5"] * 30,
            "reported": {"roi_pct_by_days": {"30": "4", "180": "20"}, "max_drawdown_pct": "10",
                         "lead_days": 300, "trades": 90}}]}
        rec = parse_snapshot(data).traders[0]
        assert rec.reported.roi_pct_by_days[180] == Decimal("20") and rec.history_days == 300
        with pytest.raises(ValueError, match="look-ahead"):
            record_as_of(rec, NOW - timedelta(days=3))
        bare = {**data, "traders": [{**data["traders"][0], "reported": None}]}
        with pytest.raises(ValueError, match="neither"):
            parse_snapshot(bare)

    def test_the_template_file_parses(self):
        from pathlib import Path

        template = Path(__file__).resolve().parents[1] / "docs/templates/copy_trading_snapshot.template.json"
        snap = parse_snapshot(json.loads(template.read_text(encoding="utf-8")))
        assert snap.source == "binance_app_manual" and snap.traders


# ---------------------------------------------------------------- risk policy


class TestRiskPolicy:
    def _policy(self, tmp_path, **cfg):
        return CopyRiskPolicy(CopyRiskConfig(**cfg), _engine(tmp_path))

    def _decide(self, policy, event, current=None, **kw):
        args = dict(trader_followed=True, trader_blocked=False, leader_losing_adds=0, leader_underwater=False,
                    exposure_excluding_this=Decimal("0"), exited_until_leader_closes=False)
        args.update(kw)
        return policy.on_leader_event(event, Decimal("1000"), current, **args)

    def test_target_is_allocation_times_leader_fraction_capped(self, tmp_path):
        p = self._policy(tmp_path)
        d = self._decide(p, _event(fraction="0.4"))
        assert (d.action, d.target_notional) == ("COPY_OPEN", Decimal("120.0"))
        d = self._decide(p, _event(fraction="0.9"))
        assert d.target_notional == Decimal("150") and "POSITION_CAP" in d.reason

    def test_leverage_is_clipped_and_shorts_are_skipped_on_spot(self, tmp_path):
        p = self._policy(tmp_path)
        assert "LEVERAGE_CLIPPED" in self._decide(p, _event(fraction="0.2", lev="10")).reason
        assert self._decide(p, _event(side="SHORT")).reason == "SHORT_NOT_SUPPORTED_ON_SPOT"

    def test_exits_are_never_blocked(self, tmp_path):
        p = self._policy(tmp_path)
        p.engine.activate_kill_switch("test")
        held = PositionView(Decimal("100"), Decimal("100"), Side.LONG)
        assert self._decide(p, _event(), trader_blocked=True).action == "NO_TRADE"
        assert self._decide(p, _event(action="CLOSE", fraction="0"), held, trader_blocked=True).action == "COPY_EXIT"
        reduce = self._decide(p, _event(action="REDUCE", fraction="0.1"), held)
        assert reduce.action == "COPY_RESIZE" and reduce.target_notional == Decimal("30.0")

    def test_the_risk_engine_veto_is_final_for_new_risk(self, tmp_path):
        p = self._policy(tmp_path)
        p.engine.activate_kill_switch("owner")
        assert self._decide(p, _event()).reason == "RISK_ENGINE:KILL_SWITCH_ACTIVE"

    def test_total_exposure_cap(self, tmp_path):
        p = self._policy(tmp_path)  # demo cap 60% of 1000
        d = self._decide(p, _event(fraction="0.5"), exposure_excluding_this=Decimal("550"))
        assert d.target_notional == Decimal("50") and "TOTAL_EXPOSURE_CAP" in d.reason

    def test_no_martingale(self, tmp_path):
        p = self._policy(tmp_path)
        losing = PositionView(Decimal("90"), Decimal("100"), Side.LONG)
        d = self._decide(p, _event(action="INCREASE", fraction="0.6", price="90"), losing,
                         leader_underwater=True, leader_losing_adds=0)
        assert (d.action, d.reason) == ("HOLD", "NO_ADDING_TO_A_LOSING_POSITION")
        d = self._decide(p, _event(action="INCREASE", fraction="0.8", price="85"), losing,
                         leader_underwater=True, leader_losing_adds=2)
        assert (d.action, d.reason) == ("BLOCK_TRADER", "LEADER_MARTINGALE")

    def test_a_loss_is_not_closed_mechanically(self, tmp_path):
        p = self._policy(tmp_path)
        pos = PositionView(Decimal("100"), Decimal("100"), Side.LONG)
        assert p.on_mark(pos, Decimal("96"), "TREND_DOWN").reason == "TEMPORARY_DRAWDOWN"  # inside envelope: hold
        assert p.on_mark(pos, Decimal("92"), "RANGE").reason == "WATCH_BEYOND_ENVELOPE"  # beyond, regime fine: hold
        assert p.on_mark(pos, Decimal("92"), "TREND_DOWN").action == "COPY_EXIT"  # beyond + regime turned: thesis gone
        assert p.on_mark(pos, Decimal("87"), "TREND_UP").reason == "HARD_STOP"  # hard limit, whatever the regime

    def test_invalid_config_is_refused(self):
        with pytest.raises(ValueError):
            CopyRiskConfig(temporary_drawdown_envelope_pct=Decimal("15"), hard_stop_loss_pct=Decimal("10"))
        with pytest.raises(ValueError):
            CopyRiskConfig(per_trader_allocation_pct=Decimal("0"))


# ---------------------------------------------------------------- follower


def _follower(tmp_path, prices: dict[str, list[tuple[float, float]]], equity="1000", **kw):
    def price_at(symbol, ts):
        h = (ts - NOW).total_seconds() / 3600
        pts = prices[symbol]
        value = pts[0][1]
        for x, y in pts:
            if x <= h:
                value = y
        return Decimal(str(value))

    f = CopyFollower(CopyRiskPolicy(CopyRiskConfig(), _engine(tmp_path)),
                     kw.pop("execution", ExecutionModel(latency_seconds=0, slippage_bps=Decimal("0"))),
                     price_at, Decimal(equity), **kw)
    f.followed.add("t")
    return f


class TestFollower:
    def test_live_mode_cannot_be_constructed(self, tmp_path):
        with pytest.raises(LiveTradingNotAuthorized):
            _follower(tmp_path, {"BTCUSDT": [(0, 100)]}, mode="LIVE")

    def test_fees_slippage_and_latency_are_paid(self, tmp_path):
        ex = ExecutionModel(latency_seconds=3600, slippage_bps=Decimal("10"))
        f = _follower(tmp_path, {"BTCUSDT": [(0, 100), (1, 101)]}, execution=ex)
        f.on_event(_event(fraction="0.5", price="100"))
        pos = f.positions[("t", "BTCUSDT")]
        assert pos.avg_entry == Decimal("101") * Decimal("1.001")  # an hour late, 10 bps worse
        assert pos.fees > 0 and f.cash < Decimal("1000") - pos.qty * pos.avg_entry

    def test_below_min_notional_is_skipped_and_journaled(self, tmp_path):
        f = _follower(tmp_path, {"BTCUSDT": [(0, 100)]}, equity="30")
        f.on_event(_event(fraction="0.5"))
        assert not f.positions
        assert f.journal[-1]["reason"].startswith("BELOW_MIN_NOTIONAL")

    def test_a_failed_order_is_healed_by_the_next_event(self, tmp_path):
        fails = {"n": 1}

        def failure_at(symbol, ts):
            if fails["n"]:
                fails["n"] -= 1
                return "TIMEOUT"
            return None

        f = _follower(tmp_path, {"BTCUSDT": [(0, 100)]}, failure_at=failure_at)
        f.on_event(_event(fraction="0.4"))
        assert f.journal[-1]["action"] == "ORDER_FAILED" and not f.positions
        f.on_event(_event(action="INCREASE", fraction="0.45", h=1))
        assert f.positions[("t", "BTCUSDT")].qty > 0

    def test_round_trip_accounting_and_risk_registration(self, tmp_path):
        f = _follower(tmp_path, {"BTCUSDT": [(0, 100), (5, 110)]})
        f.on_event(_event(fraction="0.5"))
        assert f.policy.engine.open_position_count == 1
        f.on_event(_event(action="CLOSE", fraction="0", price="110", h=6))
        assert not f.positions and f.policy.engine.open_position_count == 0
        trade = f.closed[-1]
        expected = trade.qty * 110 * Decimal("0.999") - trade.qty * 100 * Decimal("1.001")
        assert trade.pnl == pytest.approx(expected) and f.equity(NOW) == f.cash
        assert f.cash == pytest.approx(Decimal("1000") + trade.pnl)

    def test_after_our_own_exit_we_wait_for_the_leader_to_close(self, tmp_path):
        f = _follower(tmp_path, {"BTCUSDT": [(0, 100), (2, 85)]})
        f.on_event(_event(fraction="0.4"))
        f.on_mark(NOW + timedelta(hours=3))  # -15%: hard stop
        assert f.closed[-1].reason == "HARD_STOP"
        f.on_event(_event(action="INCREASE", fraction="0.5", price="86", h=4))
        assert f.journal[-1]["reason"] == "EXITED_UNTIL_LEADER_CLOSES"
        f.on_event(_event(action="CLOSE", fraction="0", price="80", h=5))
        assert f.closed[-1].leader_exit == Decimal("80")  # compared with where the leader got out
        f.on_event(_event(action="OPEN", fraction="0.3", price="85", h=6))
        assert ("t", "BTCUSDT") in f.positions

    def test_a_trader_who_loses_his_budget_is_blocked(self, tmp_path):
        f = _follower(tmp_path, {"BTCUSDT": [(0, 100), (2, 60)]})
        f.on_event(_event(fraction="0.5"))
        f.on_mark(NOW + timedelta(hours=3))  # -40% on 150 = -60 > 5% of 1000
        assert f.blocked.get("t") == "TRADER_LOSS_BUDGET" and "t" not in f.followed

    def test_a_blocked_trader_is_never_followed_again(self, tmp_path):
        f = _follower(tmp_path, {"BTCUSDT": [(0, 100)]})
        f.blocked["t"] = "LEADER_MARTINGALE"
        f.followed.discard("t")
        f.apply_selection(NOW, [E.SelectionDecision("t", "ADD", ["ELIGIBLE"], Decimal("9"))])
        assert "t" not in f.followed and f.journal[-1]["reason"] == "STILL_BLOCKED:LEADER_MARTINGALE"
        f.followed.add("t")  # even if something re-adds it, the policy still refuses new risk
        f.on_event(_event(fraction="0.4"))
        assert not f.positions and f.journal[-1]["reason"] == "TRADER_BLOCKED"

    def test_emergency_stop_blocks_entries_and_flattens_only_with_owner_confirmation(self, tmp_path):
        f = _follower(tmp_path, {"BTCUSDT": [(0, 100)]})
        f.on_event(_event(fraction="0.4"))
        with pytest.raises(ValueError):
            f.emergency_stop(NOW, "test", flatten=True)
        assert f.policy.engine.state.kill_switch and f.positions  # entries blocked, positions untouched
        f.on_event(_event(trader="t", symbol="BTCUSDT", action="INCREASE", fraction="0.5", h=1))
        assert "KILL_SWITCH" in f.journal[-1]["reason"]
        f.emergency_stop(NOW, "owner", flatten=True, owner_confirmed=True)
        assert not f.positions


# ---------------------------------------------------------------- end to end


class TestEndToEnd:
    def test_the_demo_universe_exercises_every_rule(self, tmp_path):
        result = demo.run(tmp_path)
        state = json.loads((tmp_path / "copy_state.json").read_text())
        decisions = {s["trader_id"]: s for s in state["selection"]}
        assert {t for t, s in decisions.items() if s["decision"] == "ADD"} == {"steady_a", "steady_b", "martingale"}
        assert "HISTORY_TOO_SHORT" in decisions["lucky_short"]["reasons"]
        assert "PROFIT_CONCENTRATED_IN_FEW_TRADES" in decisions["one_hit"]["reasons"]
        assert "ILLIQUID_SYMBOLS" in decisions["illiquid"]["reasons"]
        assert "LEVERAGE_TOO_HIGH" in decisions["futures_20x"]["reasons"]
        assert "INACTIVE" in decisions["blown_up"]["reasons"]
        assert state["blocked"] == {"martingale": "LEADER_MARTINGALE"}
        reasons = {c["symbol"] + ":" + c["trader"]: c for c in state["closed"]}
        sol = reasons["SOLUSDT:steady_b"]
        assert sol["reason"].startswith("THESIS_INVALIDATED_REGIME")
        assert Decimal(sol["our_return_pct"]) > Decimal(sol["leader_return_pct"])  # left before the leader's loss
        assert reasons["ETHUSDT:steady_a"]["reason"] == "LEADER_CLOSED"  # held through the ~4% dip
        assert any(j["reason"] == "TEMPORARY_DRAWDOWN" and j["trader"] == "steady_a" for j in state["journal"])
        assert any(j["action"] == "ORDER_FAILED" for j in state["journal"])
        assert not state["positions"] and result.follower.policy.engine.open_position_count == 0
        assert state["synthetic"] is True and "SINTÉTICOS" in render(state)

    def test_thirty_dollars_cannot_copy_at_these_allocations(self, tmp_path):
        result = demo.run(tmp_path, starting_equity=Decimal("30"))
        state = state_of(result)
        skips = [j for j in state["journal"] if j["reason"].startswith("BELOW_MIN_NOTIONAL")]
        assert skips and not state["closed"] and state["equity"] == "30.0000"

    def test_thirty_dollars_with_one_trader_fully_allocated_can(self, tmp_path):
        cfg = CopyRiskConfig(per_trader_allocation_pct=Decimal("100"), max_position_pct=Decimal("60"))
        result = demo.run(tmp_path, starting_equity=Decimal("30"), copy_config=cfg)
        assert any(c.trader_id == "steady_a" for c in result.follower.closed)
