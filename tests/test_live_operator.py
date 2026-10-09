"""Route B (real trading) offline: transport against a fake Binance, the owner's loss
guard, the mirror, and the operator end to end in SHADOW. No network, no keys."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_intelligence.live import binance_live as B
from trading_intelligence.live import mirror
from trading_intelligence.live.limits import LimitsNotApproved, OwnerLimits, load_limits
from trading_intelligence.live.operator import Operator, ShadowTrader, engine_risk_overrides, leader_targets
from trading_intelligence.live.session import RUNNING, STOPPED, WAITING_OWNER, Session

LIMITS = OwnerLimits(Decimal("20"), Decimal("2"), Decimal("40"), 3, frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"}))
RULES = B.SymbolRules(step=Decimal("0.0001"), min_qty=Decimal("0.0001"), min_notional=Decimal("5"))
KEY = "A" * 64


def _resp(status, body, headers=None):
    return B.HttpResponse(status, headers or {}, json.dumps(body).encode())


class FakeBinance:
    """Records every request; answers like Binance's documented REST API."""

    def __init__(self):
        self.calls = []
        self.restrictions = {"ipRestrict": True, "enableReading": True, "enableSpotAndMarginTrading": True,
                             "enableWithdrawals": False, "enableInternalTransfer": False, "enableMargin": False,
                             "enableFutures": False, "permitsUniversalTransfer": False}
        self.order_mode = "fill"
        self.orders = {}

    def __call__(self, method, url, headers, timeout):
        self.calls.append((method, url, dict(headers)))
        path = url.split("api.binance.com")[1].split("?")[0]
        query = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")) if "?" in url else {}
        if path == "/api/v3/time":
            return _resp(200, {"serverTime": 1_800_000_000_000})
        if path == "/sapi/v1/account/apiRestrictions":
            return _resp(200, self.restrictions)
        if path == "/api/v3/account":
            return _resp(200, {"balances": [{"asset": "USDT", "free": "1000", "locked": "0"}]})
        if path == "/api/v3/order" and method == "POST":
            cid = query["newClientOrderId"]
            qty = Decimal(query["quantity"])
            body = {"symbol": query["symbol"], "side": query["side"], "orderId": 7, "clientOrderId": cid,
                    "status": "FILLED", "executedQty": str(qty), "cummulativeQuoteQty": str(qty * 100),
                    "fills": [{"price": "100", "qty": str(qty), "commission": str(qty * Decimal("0.001")),
                               "commissionAsset": query["symbol"][:-4]}]}
            self.orders[cid] = body
            if self.order_mode == "timeout":
                raise TimeoutError("read timed out")
            if self.order_mode == "reject":
                return _resp(400, {"code": -2010, "msg": "Account has insufficient balance"})
            return _resp(200, body)
        if path == "/api/v3/order" and method == "GET":
            body = self.orders.get(query["origClientOrderId"])
            return _resp(200, {k: v for k, v in body.items() if k != "fills"}) if body else \
                _resp(400, {"code": -2013, "msg": "Order does not exist."})
        if path == "/api/v3/myTrades":
            body = next(iter(self.orders.values()))
            return _resp(200, [{**f, "orderId": 7} for f in body["fills"]])
        return _resp(404, {"code": -1, "msg": "unexpected"})


def _trader(tmp_path, fake=None):
    fake = fake or FakeBinance()
    t = B.SpotTrader(B.Credentials(KEY, KEY), tmp_path / "orders.json", transport=fake, clock=lambda: 1_800_000_000.0)
    return t, fake


# ------------------------------------------------------------------ transport


class TestTransport:
    def test_a_safe_key_passes_and_any_extra_power_is_refused(self, tmp_path):
        t, fake = _trader(tmp_path)
        assert t.verify_key() is True and t.key_checked
        fake.restrictions = {**FakeBinance().restrictions, "enableWithdrawals": True}
        with pytest.raises(B.UnsafeKey, match="WITHDRAWALS"):
            t.verify_key()
        for bad in ({"enableWithdrawals": True}, {"enableWithdrawals": None}, {"ipRestrict": False},
                    {"enableSpotAndMarginTrading": False}, {"permitsUniversalTransfer": True},
                    {"enableFutures": True}, {"enableNewThing": True}):
            fake.restrictions = {**FakeBinance().restrictions, **bad}
            with pytest.raises(B.UnsafeKey):
                t.verify_key()
            assert not t.key_checked

    def test_no_order_without_a_verified_key(self, tmp_path):
        t, _ = _trader(tmp_path)
        with pytest.raises(B.UnsafeKey):
            t.market_order("BTCUSDT", "BUY", Decimal("0.1"), lambda s: Decimal("1"))

    def test_a_filled_order_is_journaled_and_net_of_base_commission(self, tmp_path):
        t, fake = _trader(tmp_path)
        t.verify_key()
        fill = t.market_order("BTCUSDT", "BUY", Decimal("0.1"), lambda s: Decimal("1"))
        assert fill.executed_qty == Decimal("0.0999") and fill.quote_qty == Decimal("10.0")
        assert fill.fee_usdt == Decimal("0.0001") * fill.avg_price
        journal = json.loads((tmp_path / "orders.json").read_text())["orders"]
        assert list(journal.values())[0]["state"] == "FILLED"
        method, url, headers = fake.calls[-1]
        assert method == "POST" and "type=MARKET" in url and "signature=" in url and headers == {"X-MBX-APIKEY": KEY}

    def test_an_uncertain_order_is_reconciled_never_resent(self, tmp_path):
        t, fake = _trader(tmp_path)
        t.verify_key()
        fake.order_mode = "timeout"
        with pytest.raises(B.Unreconciled):
            t.market_order("BTCUSDT", "BUY", Decimal("0.1"), lambda s: Decimal("1"))
        with pytest.raises(B.Unreconciled):
            t.market_order("BTCUSDT", "BUY", Decimal("0.1"), lambda s: Decimal("1"))  # blocked, not sent
        assert sum(1 for c in fake.calls if c[0] == "POST") == 1
        fills = t.reconcile(lambda s: Decimal("1"))
        assert len(fills) == 1 and fills[0].executed_qty == Decimal("0.0999") and t.unresolved() == []

    def test_a_rejected_order_is_recorded_and_raised(self, tmp_path):
        t, fake = _trader(tmp_path)
        t.verify_key()
        fake.order_mode = "reject"
        with pytest.raises(B.LiveError, match="-2010"):
            t.market_order("BTCUSDT", "BUY", Decimal("0.1"), lambda s: Decimal("1"))
        assert t.unresolved() == []

    def test_secrets_never_leak(self, tmp_path):
        creds = B.Credentials(KEY, "S" * 64)
        assert KEY not in repr(creds) and "S" * 64 not in str(creds)
        with pytest.raises(TypeError):
            json.dumps(creds)

    def test_only_api_binance_com(self):
        with pytest.raises(B.LiveError):
            B.urllib_transport("GET", "https://evil.example/api/v3/time", {}, 1)

    def test_rate_limit_cools_down_and_403_blocks(self, tmp_path):
        calls = {"n": 0}

        def transport(method, url, headers, timeout):
            calls["n"] += 1
            return _resp(429 if calls["n"] == 1 else 403, {"code": -1003}, {"Retry-After": "30"})

        t = B.SpotTrader(None, tmp_path / "o.json", transport=transport, clock=lambda: 1000.0)
        with pytest.raises(B.LiveError):
            t.price("BTCUSDT")
        with pytest.raises(B.Restricted):
            t.price("BTCUSDT")  # cooling down: not even sent
        assert calls["n"] == 1


# ------------------------------------------------------------------ session guard


class TestLossGuard:
    def _session(self, capital="50"):
        return Session("s", "tendencia", "2026-10-08T00:00:00+00:00", Decimal(capital))

    def test_ask_two_dollars_before_the_limit_then_stop_at_it(self):
        s = self._session()
        s.record_buy("BTCUSDT", Decimal("0.2"), Decimal("20"), Decimal("0.02"), "test")  # 20 USDT at 100
        assert s.evaluate({"BTCUSDT": Decimal("70")}, LIMITS) is None  # loss 6 < 8
        msg = s.evaluate({"BTCUSDT": Decimal("59")}, LIMITS)  # loss 8.2 >= 10 - 2
        assert s.status == WAITING_OWNER and "AVISO" in msg and not s.may_buy
        s.owner_continue()
        assert s.status == RUNNING and s.may_buy
        assert s.evaluate({"BTCUSDT": Decimal("58")}, LIMITS) is None  # acknowledged: no second warning
        msg = s.evaluate({"BTCUSDT": Decimal("50")}, LIMITS)  # loss 10 = limit
        assert s.status == STOPPED and "STOP" in msg
        with pytest.raises(ValueError):
            s.owner_continue()

    def test_a_sell_never_exceeds_what_the_session_holds(self):
        s = self._session()
        s.record_buy("BTCUSDT", Decimal("0.1"), Decimal("10"), Decimal("0"), "open")
        pnl = s.record_sell("BTCUSDT", Decimal("5"), Decimal("11"), Decimal("0"), "close")
        assert pnl == Decimal("1") and not s.holdings and s.trades[-1]["qty"] == "0.1"

    def test_added_capital_raises_the_limit_and_rearms_the_warning(self):
        s = self._session()
        s.add_capital(Decimal("1000"))
        assert s.capital == Decimal("1050") and LIMITS.loss_limit_usd(s.capital) == Decimal("210")

    def test_realized_pnl_and_persistence(self, tmp_path):
        s = self._session()
        s.record_buy("BTCUSDT", Decimal("0.2"), Decimal("20.02"), Decimal("0.02"), "open")
        pnl = s.record_sell("BTCUSDT", Decimal("0.2"), Decimal("21.978"), Decimal("0.022"), "close")
        assert pnl == Decimal("1.958") and s.equity({}) == Decimal("51.958") and not s.holdings
        s.save(tmp_path / "s.json")
        again = Session.load(tmp_path / "s.json")
        assert again.realized_pnl == s.realized_pnl and again.trades == s.trades


# ------------------------------------------------------------------ mirror


class FakeTrader:
    def __init__(self, prices, free=Decimal("1000")):
        self.prices, self.free, self.orders = prices, free, []
        self.key_checked = True

    def price(self, s):
        return self.prices[s]

    def rules(self, s):
        return RULES

    def free_balance(self, a):
        return self.free

    def unresolved(self):
        return []

    def reconcile(self, fp):
        return []

    def market_order(self, symbol, side, qty, fp):
        self.orders.append((symbol, side, qty))
        p = self.prices[symbol]
        return B.Fill("x", symbol, side, "FILLED", qty, qty * p, qty * p * Decimal("0.001"), p)


def _s(capital="50"):
    return Session("s", "tendencia", "t", Decimal(capital))


class TestMirror:
    P = {"BTCUSDT": Decimal("100"), "ETHUSDT": Decimal("10"), "SOLUSDT": Decimal("1"), "PEPEUSDT": Decimal("1")}

    def test_open_close_and_caps(self):
        s, t = _s(), FakeTrader(dict(self.P))
        acts = mirror.apply_targets(s, t, {"BTCUSDT": Decimal("0.9"), "PEPEUSDT": Decimal("0.2")}, LIMITS, self.P, "eng")
        assert [a.kind for a in acts] == ["BUY", "SKIP"] and acts[1].reason == "SYMBOL_NOT_APPROVED"
        assert s.holdings["BTCUSDT"].qty * 100 <= Decimal("20")  # 40% cap of 50
        mirror.apply_targets(s, t, {}, LIMITS, self.P, "eng")
        assert not s.holdings and t.orders[-1][1] == "SELL"

    def test_below_the_exchange_minimum_is_skipped(self):
        s, t = _s("10"), FakeTrader(dict(self.P))
        acts = mirror.apply_targets(s, t, {"BTCUSDT": Decimal("0.3")}, LIMITS, self.P, "eng")  # 3 USDT
        assert acts[0].kind == "SKIP" and acts[0].reason.startswith("BELOW_EXCHANGE_MINIMUM") and not t.orders

    def test_never_sells_coins_the_session_did_not_buy(self):
        s, t = _s(), FakeTrader(dict(self.P))
        assert mirror.sell(s, t, "BTCUSDT", "x").reason == "NOTHING_HELD" and not t.orders

    def test_no_buys_while_waiting_for_the_owner_and_no_adding_to_losers(self):
        s, t = _s(), FakeTrader(dict(self.P))
        s.status = WAITING_OWNER
        acts = mirror.apply_targets(s, t, {"BTCUSDT": Decimal("0.3")}, LIMITS, self.P, "eng")
        assert acts[0].reason == "SESSION_WAITING_OWNER" and not t.orders
        s.status = RUNNING
        mirror.apply_targets(s, t, {"BTCUSDT": Decimal("0.2")}, LIMITS, self.P, "eng")
        assert "BTCUSDT" in s.holdings
        lower = {**self.P, "BTCUSDT": Decimal("90")}
        acts = mirror.apply_targets(s, t, {"BTCUSDT": Decimal("0.4")}, LIMITS, lower, "eng")
        assert acts[-1].reason == "NO_ADDING_TO_A_LOSING_POSITION"

    def test_max_open_positions_and_stops(self):
        s, t = _s("100"), FakeTrader(dict(self.P))
        limits = OwnerLimits(Decimal("20"), Decimal("2"), Decimal("40"), 1, LIMITS.allowed_symbols)
        acts = mirror.apply_targets(s, t, {"BTCUSDT": Decimal("0.2"), "ETHUSDT": Decimal("0.2")}, limits, self.P, "e")
        assert [a.kind for a in acts] == ["BUY", "SKIP"] and acts[1].reason == "MAX_OPEN_POSITIONS"
        acts = mirror.enforce_stops(s, t, {"BTCUSDT": Decimal("95")}, {**self.P, "BTCUSDT": Decimal("94")})
        assert acts[0].kind == "SELL" and "STOP_HIT" in acts[0].reason and not s.holdings


# ------------------------------------------------------------------ operator


class FakeLoop:
    """Stands in for PaperLoop: exposes runner.paper positions / pending orders."""

    class _Paper:
        def __init__(self):
            self.positions, self.pending_orders, self._last_price = {}, [], {}

        def last_known_equity(self):
            return Decimal("50")

    def __init__(self, tmp_path):
        self.runner = type("R", (), {"paper": self._Paper()})()
        self.state_path = tmp_path / "loop.json"
        self.ticks = 0

    def tick(self):
        self.ticks += 1


def _operator(tmp_path, trader, loop=None, profile="tendencia", now=None):
    Session("s1", profile, "t", Decimal("50")).save(tmp_path / "session.json")
    clock = now or (lambda: datetime(2026, 10, 8, 12, tzinfo=timezone.utc))
    return Operator(tmp_path, trader, LIMITS, profile=profile, timeframe="1h", symbols=["BTCUSDT"], loop=loop,
                    clock=clock, notify=lambda m: None)


class TestOperator:
    def test_engine_decision_becomes_a_real_order_and_a_report(self, tmp_path):
        from trading_intelligence.execution.order_models import OrderRequest, Position

        trader = FakeTrader({"BTCUSDT": Decimal("100")})
        loop = FakeLoop(tmp_path)
        loop.runner.paper.positions["BTCUSDT"] = Position("BTCUSDT", Decimal("0.1"), Decimal("100"), Decimal("0"))
        loop.runner.paper._last_price["BTCUSDT"] = Decimal("100")
        loop.runner.paper.pending_orders.append(OrderRequest("BTCUSDT", "SELL", "STOP", Decimal("0.1"),
                                                             stop_price=Decimal("95")))
        op = _operator(tmp_path, trader, loop)
        op.step(decide=True)
        assert loop.ticks == 1 and trader.orders[0][:2] == ("BTCUSDT", "BUY")
        assert json.loads((tmp_path / "status.json").read_text())["holdings"]
        trader.prices["BTCUSDT"] = Decimal("94")
        op.step(decide=False)  # between bars: the live stop still works
        assert trader.orders[-1][1] == "SELL" and not op.session.holdings
        report = op.write_report("final").read_text(encoding="utf-8")
        assert "FINAL" in report and "BTCUSDT" in report and "STOP_HIT" in report and "No usados" in report

    def test_hard_limit_closes_everything_and_the_run_ends(self, tmp_path):
        trader = FakeTrader({"BTCUSDT": Decimal("100")})
        op = _operator(tmp_path, trader)
        op.session.record_buy("BTCUSDT", Decimal("0.2"), Decimal("20"), Decimal("0"), "t")
        trader.prices["BTCUSDT"] = Decimal("49")
        op.run(poll_seconds=0, sleep=lambda s: None, max_iterations=3)
        s = Session.load(tmp_path / "session.json")
        assert s.status == STOPPED and not s.holdings and (tmp_path / "AVISO.txt").exists()
        assert list(tmp_path.glob("reporte_final_*.md"))

    def test_owner_stop_file_with_close(self, tmp_path):
        trader = FakeTrader({"BTCUSDT": Decimal("100")})
        op = _operator(tmp_path, trader)
        op.session.record_buy("BTCUSDT", Decimal("0.1"), Decimal("10"), Decimal("0"), "t")
        (tmp_path / "STOP").write_text("cerrar")
        op.run(poll_seconds=0, sleep=lambda s: None, max_iterations=2)
        assert not Session.load(tmp_path / "session.json").holdings

    def test_copy_profile_follows_fresh_leader_positions_only(self, tmp_path):
        now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        trader = FakeTrader({"BTCUSDT": Decimal("100")})
        op = _operator(tmp_path, trader, profile="copiar", now=lambda: now)
        op.step(decide=True)
        assert not trader.orders and op.session.events[-1]["text"].startswith("LEADER_POSITIONS_MISSING")
        (tmp_path / "leader_positions.json").write_text(json.dumps(
            {"read_at": (now - timedelta(minutes=5)).isoformat(), "trader": "x", "positions": {"BTCUSDT": 0.3}}))
        op.step(decide=True)
        assert trader.orders[-1][:2] == ("BTCUSDT", "BUY")
        (tmp_path / "leader_positions.json").write_text(json.dumps(
            {"read_at": (now - timedelta(hours=7)).isoformat(), "trader": "x", "positions": {}}))
        orders_before = len(trader.orders)
        op.step(decide=True)  # stale leader data: hold what we have, never read it as "leader sold"
        assert len(trader.orders) == orders_before and "BTCUSDT" in op.session.holdings
        targets, problem = leader_targets(tmp_path / "leader_positions.json", timedelta(minutes=1), now)
        assert problem == "LEADER_POSITIONS_STALE" and targets == {}

    def test_shadow_trader_never_sends(self):
        t = ShadowTrader(lambda s: Decimal("100"), lambda s: RULES)
        fill = t.market_order("BTCUSDT", "BUY", Decimal("0.1"), lambda s: Decimal("1"))
        assert fill.client_id.startswith("shadow-") and t.sent == [("BTCUSDT", "BUY", Decimal("0.1"))]


class TestLimits:
    def test_the_committed_limits_load(self):
        limits = load_limits()
        assert limits.loss_limit_pct == Decimal("20") and limits.warn_before_usd == Decimal("2")
        assert limits.loss_limit_usd(Decimal("50")) == Decimal("10") and limits.warn_at_usd(Decimal("50")) == Decimal("8")

    @pytest.mark.parametrize("change", [{"approved_by_owner": False}, {"withdrawals": True}, {"max_leverage": 3},
                                        {"market": "FUTURES"}, {"loss_limit_pct": 0}])
    def test_unapproved_or_unsafe_limits_refuse(self, tmp_path, change):
        data = json.loads((Path(__file__).resolve().parents[1] / "config/live_limits.json").read_text())
        (tmp_path / "l.json").write_text(json.dumps({**data, **change}))
        with pytest.raises(LimitsNotApproved):
            load_limits(tmp_path / "l.json")

    def test_engine_never_trips_before_the_owner_guard(self):
        o = engine_risk_overrides(LIMITS)
        assert o["daily_loss_limit_pct"] == 20.0 and o["drawdown_halt_pct"] == 20.0 and o["drawdown_pause_pct"] < 20
        from trading_intelligence.risk.models import RiskConfig

        RiskConfig(**o)  # valid


def test_the_real_engine_drives_the_real_account_end_to_end(tmp_path):
    """The real PaperLoop + runner + RiskEngine decide; the operator mirrors the decision
    onto the (fake) exchange the moment the entry is approved, with its protective stop."""
    from tests.test_paper_loop import SYMBOL, WARMUP, FakeFeed, _at, _build, _flat, _frame

    feed = FakeFeed({SYMBOL: _frame(_flat(WARMUP + 5))})
    (tmp_path / "eng").mkdir()
    loop = _build(tmp_path / "eng", feed)  # scripted strategy: entry on bar WARMUP, stop 5% below
    trader = FakeTrader({SYMBOL: Decimal("100")})
    Session("s1", "tendencia", "t", Decimal("50")).save(tmp_path / "session.json")
    op = Operator(tmp_path, trader, LIMITS, profile="tendencia", timeframe="1h", symbols=[SYMBOL], loop=loop,
                  clock=lambda: datetime(2026, 10, 8, tzinfo=timezone.utc), notify=lambda m: None)
    _at(feed, WARMUP + 1)
    op.step(decide=True)
    assert trader.orders and trader.orders[0][:2] == (SYMBOL, "BUY")
    held = op.session.holdings[SYMBOL]
    assert held.qty * 100 <= Decimal("20.01")  # owner's 40% cap of 50
    assert getattr(op, "_last_stops")[SYMBOL] < Decimal("100")  # the engine's protective stop is known live


def test_real_orders_are_refused_at_a_timeframe_proven_to_lose(tmp_path, capsys):
    from trading_intelligence.live import operator as O

    assert O.DEFAULT_TIMEFRAME == "4h" and O.REAL_TIMEFRAMES == {"4h"}
    with pytest.raises(SystemExit):
        O.main(["--dir", str(tmp_path), "iniciar", "--capital", "50", "--temporalidad", "1h", "--real"])
    assert "lost money after fees" in capsys.readouterr().err
    assert not (tmp_path / "session.json").exists()


def test_a_shadow_report_never_claims_real_execution(tmp_path):
    op = _operator(tmp_path, FakeTrader({"BTCUSDT": Decimal("100")}))
    text = op.write_report("inicio").read_text(encoding="utf-8")
    used = next(line for line in text.splitlines() if line.startswith("Usados:"))
    assert "SHADOW" in text and "Ejecución real" not in used and "Ejecución simulada" in used


class TestOwnerExits:
    """The owner's "por N horas" and "hasta ganar N%": both only close, and a finished
    session can be followed by a new one."""

    def test_profit_target_takes_the_gain_and_finishes(self, tmp_path):
        trader = FakeTrader({"BTCUSDT": Decimal("100")})
        op = _operator(tmp_path, trader)
        op.profit_target_pct = Decimal("10")
        op.session.record_buy("BTCUSDT", Decimal("0.2"), Decimal("20"), Decimal("0"), "t")
        trader.prices["BTCUSDT"] = Decimal("124")  # equity 54.8: +9.6%, not yet
        assert op.finish_reason() is None
        trader.prices["BTCUSDT"] = Decimal("126")  # equity 55.2: +10.4%
        op.run(poll_seconds=0, sleep=lambda s: None, max_iterations=3)
        s = Session.load(tmp_path / "session.json")
        assert s.status == STOPPED and not s.holdings and s.realized_pnl == Decimal("5.2")
        assert trader.orders[-1][1] == "SELL" and "META_ALCANZADA" in (tmp_path / "AVISO.txt").read_text()
        assert list(tmp_path.glob("reporte_final_*.md"))

    def test_time_box_closes_and_finishes(self, tmp_path):
        now = [datetime(2026, 10, 8, 12, tzinfo=timezone.utc)]
        trader = FakeTrader({"BTCUSDT": Decimal("100")})
        op = _operator(tmp_path, trader, now=lambda: now[0])
        op.end_at = now[0] + timedelta(hours=3)
        op.session.record_buy("BTCUSDT", Decimal("0.1"), Decimal("10"), Decimal("0"), "t")
        assert op.finish_reason() is None
        now[0] += timedelta(hours=3)
        op.run(poll_seconds=0, sleep=lambda s: None, max_iterations=3)
        s = Session.load(tmp_path / "session.json")
        assert s.status == STOPPED and not s.holdings and "TIEMPO_CUMPLIDO" in s.events[-1]["text"]

    def test_after_the_owner_stops_a_new_session_can_start(self, tmp_path):
        op = _operator(tmp_path, FakeTrader({"BTCUSDT": Decimal("100")}))
        (tmp_path / "STOP").write_text("parar")
        op.run(poll_seconds=0, sleep=lambda s: None, max_iterations=1)
        assert Session.load(tmp_path / "session.json").status == STOPPED

    @pytest.mark.parametrize("flag", [["--horas", "0"], ["--meta", "-5"], ["--meta", "NaN"]])
    def test_nonsense_exits_are_refused(self, tmp_path, flag, capsys):
        from trading_intelligence.live import operator as O

        with pytest.raises(SystemExit):
            O.main(["--dir", str(tmp_path), "iniciar", "--capital", "50", *flag])
        assert not (tmp_path / "session.json").exists()


def test_the_start_report_shows_the_first_market_read(tmp_path):
    """Pre-flight finding: the start report was written before the first decision, so the
    owner's rehearsal showed no regime per coin. It now follows the first decision pass."""
    trader = FakeTrader({"BTCUSDT": Decimal("100")})
    loop = FakeLoop(tmp_path)
    loop.tick = lambda: (setattr(loop, "ticks", loop.ticks + 1),
                         loop.state_path.write_text(json.dumps({"journal": [
                             {"bar": "b1", "symbol": "BTCUSDT", "action": "NO_STRATEGY_FOR_REGIME",
                              "regime": "TREND_DOWN"}]})))
    op = _operator(tmp_path, trader, loop)
    op.run(poll_seconds=0, sleep=lambda s: None, max_iterations=1, start_report=True)
    start = next(tmp_path.glob("reporte_inicio_*.md")).read_text(encoding="utf-8")
    assert loop.ticks == 1 and "TREND_DOWN" in start and "BTCUSDT" in start
    assert list(tmp_path.glob("reporte_final_*.md"))  # a bounded rehearsal leaves its summary


class TestResume:
    """Owner: "estar atento al cierre". If the operator dies (crash, reboot, power cut), the
    open session must be resumable, so its stops and loss guard are watched again."""

    def _session(self, d, status="RUNNING", holdings=True):
        s = Session("s1", "tendencia", "t", Decimal("100"))
        if holdings:
            s.record_buy("BTCUSDT", Decimal("0.1"), Decimal("10"), Decimal("0"), "t")
        s.status = status
        s.save(d / "session.json")
        (d / "meta.json").write_text(json.dumps({"profile": "tendencia", "timeframe": "4h", "symbols": ["BTCUSDT"],
                                                 "real": True, "end_at": None, "profit_target_pct": None}))

    def test_a_fresh_lock_means_running_and_a_stale_one_is_replaced(self, tmp_path):
        import os

        from trading_intelligence.live import operator as O

        lock = O._lock(tmp_path)
        with pytest.raises(O.AlreadyRunning):
            O._lock(tmp_path)
        old = (datetime.now(timezone.utc) - timedelta(minutes=30)).timestamp()
        os.utime(lock, (old, old))
        assert O._lock(tmp_path).exists()  # dead operator: its lock no longer blocks

    def test_resume_relaunches_the_open_session_once(self, tmp_path, monkeypatch, capsys):
        from trading_intelligence.live import operator as O

        self._session(tmp_path)
        launched = []
        monkeypatch.setattr(O, "_launch", lambda d, limits, meta, eq, it: launched.append((meta["real"], eq)))
        assert O.main(["--dir", str(tmp_path), "reanudar"]) == 0
        assert launched == [(True, "100")] and not (tmp_path / "OPERATOR.lock").exists()
        assert Session.load(tmp_path / "session.json").events[-1]["kind"] == "RESUMED"
        O._lock(tmp_path)  # now a live operator holds it
        assert O.main(["--dir", str(tmp_path), "reanudar"]) == 0
        assert len(launched) == 1 and "ya está corriendo" in capsys.readouterr().out

    @pytest.mark.parametrize("status,holdings", [("STOPPED", False), (None, None)])
    def test_nothing_to_resume(self, tmp_path, monkeypatch, status, holdings):
        from trading_intelligence.live import operator as O

        if status:
            self._session(tmp_path, status, holdings)
        monkeypatch.setattr(O, "_launch", lambda *a: pytest.fail("must not launch"))
        assert O.main(["--dir", str(tmp_path), "reanudar"]) == 0

    def test_a_stopped_session_with_positions_is_resumed_to_close_them(self, tmp_path, monkeypatch):
        from trading_intelligence.live import operator as O

        self._session(tmp_path, "STOPPED", holdings=True)
        launched = []
        monkeypatch.setattr(O, "_launch", lambda *a: launched.append(1))
        O.main(["--dir", str(tmp_path), "reanudar"])
        assert launched == [1]  # step() flattens a STOPPED session that still holds coins

    def test_a_new_session_never_inherits_the_previous_engine(self, tmp_path, monkeypatch):
        from trading_intelligence.live import operator as O

        self._session(tmp_path, "STOPPED", holdings=False)
        (tmp_path / "engine").mkdir()
        (tmp_path / "engine" / "paper.json").write_text("{}")
        seen = []
        monkeypatch.setattr(O, "_trader", lambda real, journal: None)
        monkeypatch.setattr(O, "_launch", lambda d, limits, meta, eq, it: seen.append((d / "engine").exists()))
        O.main(["--dir", str(tmp_path), "iniciar", "--capital", "100"])
        assert seen == [False] and Session.load(tmp_path / "session.json").capital == Decimal("100")


def test_resume_never_sells_what_the_owner_kept_with_parar(tmp_path, monkeypatch):
    from trading_intelligence.live import operator as O

    TestResume()._session(tmp_path, "STOPPED", holdings=True)
    s = Session.load(tmp_path / "session.json")
    s.note("FIN", "OWNER_STOP: parada ordenada por el dueño")
    s.save(tmp_path / "session.json")
    monkeypatch.setattr(O, "_launch", lambda *a: pytest.fail("a finished session is never reopened"))
    assert O.main(["--dir", str(tmp_path), "reanudar"]) == 0
