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

    def place_stop(self, symbol, qty, stop):
        self.orders.append((symbol, "STOP_LOSS", qty))
        return f"stop-{len(self.orders)}"

    def stop_status(self, symbol, cid, fp):
        return B.StopState("NEW")

    def cancel_stop(self, symbol, cid, fp):
        self.orders.append((symbol, "CANCEL", cid))
        return B.StopState("CANCELED")


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
        # Owner, 2026-10-09: "un standard de 35% ... si algún día quiero arriesgarme más ... al 50 o un 20".
        assert limits.loss_limit_pct == Decimal("35") and limits.warn_before_usd == Decimal("2")
        assert limits.loss_band_pct == (Decimal("20"), Decimal("50"))
        assert limits.loss_limit_usd(Decimal("38")) == Decimal("13.3") and limits.warn_at_usd(Decimal("38")) == Decimal("11.3")
        assert limits.for_session(Decimal("50")).loss_limit_usd(Decimal("100")) == Decimal("50")
        assert limits.for_session(None) is limits
        for outside in (Decimal("19"), Decimal("51")):
            with pytest.raises(LimitsNotApproved):
                limits.for_session(outside)

    @pytest.mark.parametrize("change", [{"approved_by_owner": False}, {"withdrawals": True}, {"max_leverage": 3},
                                        {"market": "FUTURES"}, {"loss_limit_pct": 0}, {"loss_limit_pct": 60},
                                        {"loss_limit_pct": 19}, {"loss_limit_owner_range_pct": ["x"]}])
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

    assert O.DEFAULT_TIMEFRAME == "4h" and O.REAL_TIMEFRAMES == {"4h", "20m", "5m", "1m"}  # 20m/5m: owner's written choice
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


class TestClockSync:
    """Claude Code local saw a -1021 (timestamp outside recvWindow) on the owner's PC. With one
    sync per process, a drifting clock would make Binance refuse every later signed call,
    protective sells included."""

    def _count_time_calls(self, fake):
        return sum(1 for c in fake.calls if "/api/v3/time" in c[1])

    def test_resyncs_periodically_and_right_after_a_1021(self, tmp_path):
        now = [1_800_000_000.0]
        fake = FakeBinance()
        t = B.SpotTrader(B.Credentials(KEY, KEY), tmp_path / "o.json", transport=fake, clock=lambda: now[0])
        t.verify_key()
        t.free_balance("USDT")
        assert self._count_time_calls(fake) == 1  # fresh offset reused
        now[0] += B.TIME_RESYNC_SECONDS
        t.free_balance("USDT")
        assert self._count_time_calls(fake) == 2  # stale offset re-read
        original = fake.restrictions
        fake.restrictions = {"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."}
        with pytest.raises(B.LiveError, match="-1021"):
            t.verify_key()
        fake.restrictions = original
        assert t.verify_key() is True and self._count_time_calls(fake) == 3  # resynced at once

    def test_offset_uses_the_middle_of_the_round_trip(self, tmp_path):
        ticks = iter([1000.0, 1002.0] + [1002.0] * 20)  # the time request took 2 s
        server_ms = 1_001_000

        def transport(method, url, headers, timeout):
            return _resp(200, {"serverTime": server_ms}) if "/api/v3/time" in url else _resp(200, FakeBinance().restrictions)

        t = B.SpotTrader(B.Credentials(KEY, KEY), tmp_path / "o.json", transport=transport, clock=lambda: next(ticks))
        t._sync_time()
        assert t._offset_ms == 0  # the server's 1001.000 s is the midpoint of 1000-1002, not 1 s behind


# ------------------------------------------------------------------ guard stops on Binance


class StopBinance(FakeBinance):
    """FakeBinance plus exchangeInfo, STOP_LOSS orders resting on the book, and DELETE."""

    def __init__(self):
        super().__init__()
        self.stops = {}  # cid -> body
        self.stop_mode = "ok"

    def __call__(self, method, url, headers, timeout):
        path = url.split("api.binance.com")[1].split("?")[0]
        query = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")) if "?" in url else {}
        if path == "/api/v3/exchangeInfo":
            self.calls.append((method, url, dict(headers)))
            return _resp(200, {"symbols": [{"status": "TRADING", "quoteAsset": "USDT",
                                            "orderTypes": ["LIMIT", "MARKET", "STOP_LOSS"],
                                            "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.0001", "minQty": "0.0001"},
                                                        {"filterType": "NOTIONAL", "minNotional": "5"},
                                                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"}]}]})
        if path == "/api/v3/order" and method == "POST" and query.get("type") == "STOP_LOSS":
            self.calls.append((method, url, dict(headers)))
            cid = query["newClientOrderId"]
            if self.stop_mode == "reject":
                return _resp(400, {"code": -2010, "msg": "Stop price would trigger immediately."})
            self.stops[cid] = {"symbol": query["symbol"], "side": "SELL", "orderId": 9, "clientOrderId": cid,
                               "status": "NEW", "executedQty": "0", "cummulativeQuoteQty": "0",
                               "qty": query["quantity"], "stopPrice": query["stopPrice"]}
            if self.stop_mode == "timeout":
                raise TimeoutError("read timed out")
            return _resp(200, self.stops[cid])
        cid = query.get("origClientOrderId")
        if path == "/api/v3/order" and cid in self.stops:
            self.calls.append((method, url, dict(headers)))
            body = self.stops[cid]
            if method == "DELETE":
                if body["status"] != "NEW":
                    return _resp(400, {"code": -2011, "msg": "Unknown order sent."})
                body["status"] = "CANCELED"
            return _resp(200, body)
        if path == "/api/v3/myTrades" and any(b["status"] == "FILLED" for b in self.stops.values()):
            self.calls.append((method, url, dict(headers)))
            b = next(b for b in self.stops.values() if b["status"] == "FILLED")
            return _resp(200, [{"price": "90", "qty": b["executedQty"], "commission": "0.009",
                                "commissionAsset": "USDT", "orderId": 9}])
        return super().__call__(method, url, headers, timeout)

    def trigger(self, cid, price="90"):
        b = self.stops[cid]
        b.update(status="FILLED", executedQty=b["qty"], cummulativeQuoteQty=str(Decimal(b["qty"]) * Decimal(price)))


class TestGuardStopTransport:
    def _t(self, tmp_path):
        fake = StopBinance()
        t = B.SpotTrader(B.Credentials(KEY, KEY), tmp_path / "orders.json", transport=fake, clock=lambda: 1_800_000_000.0)
        t.verify_key()
        return t, fake

    def test_rules_know_tick_size_and_stop_support(self, tmp_path):
        t, _ = self._t(tmp_path)
        r = t.rules("BTCUSDT")
        assert r.stop_loss and r.tick == Decimal("0.01") and r.floor_price(Decimal("94.567")) == Decimal("94.56")

    def test_a_resting_stop_never_blocks_market_orders(self, tmp_path):
        t, fake = self._t(tmp_path)
        cid = t.place_stop("BTCUSDT", Decimal("0.1"), Decimal("95"))
        method, url, _ = fake.calls[-1]
        assert method == "POST" and "type=STOP_LOSS" in url and "side=SELL" in url and "stopPrice=95" in url
        assert t.unresolved() == [] and json.loads((tmp_path / "orders.json").read_text())["orders"][cid]["state"] == "RESTING"
        t.market_order("ETHUSDT", "BUY", Decimal("0.1"), lambda s: Decimal("1"))  # not blocked
        fake.stop_mode = "timeout"
        cid2 = t.place_stop("BTCUSDT", Decimal("0.1"), Decimal("95"))  # unclear: looked up later, no raise
        assert t.unresolved() == [] and t.stop_status("BTCUSDT", cid2, lambda s: Decimal("1")).status == "NEW"

    def test_a_rejected_stop_raises(self, tmp_path):
        t, fake = self._t(tmp_path)
        fake.stop_mode = "reject"
        with pytest.raises(B.LiveError, match="-2010"):
            t.place_stop("BTCUSDT", Decimal("0.1"), Decimal("95"))

    def test_cancel_reports_an_execution_instead_of_hiding_it(self, tmp_path):
        t, fake = self._t(tmp_path)
        cid = t.place_stop("BTCUSDT", Decimal("0.1"), Decimal("95"))
        assert t.cancel_stop("BTCUSDT", cid, lambda s: Decimal("1")).status == "CANCELED"
        cid = t.place_stop("BTCUSDT", Decimal("0.1"), Decimal("95"))
        fake.trigger(cid)
        state = t.cancel_stop("BTCUSDT", cid, lambda s: Decimal("1"))
        assert state.status == "FILLED" and state.fill.side == "SELL" and state.fill.executed_qty == Decimal("0.1")
        assert state.fill.quote_qty == Decimal("8.991")  # 9 USDT minus the USDT commission

    def test_a_vanished_stop_reads_not_found(self, tmp_path):
        t, _ = self._t(tmp_path)
        assert t.stop_status("BTCUSDT", "ts-unknown", lambda s: Decimal("1")).status == "NOT_FOUND"


GUARD_RULES = B.SymbolRules(step=Decimal("0.0001"), min_qty=Decimal("0.0001"), min_notional=Decimal("5"),
                            tick=Decimal("0.01"), stop_loss=True)


class GuardTrader(FakeTrader):
    """FakeTrader whose exchange can execute a resting stop on its own (the PC may be off)."""

    def __init__(self, prices):
        super().__init__(prices)
        self.resting, self.executed, self.unclear = {}, set(), False

    def rules(self, s):
        return GUARD_RULES

    def place_stop(self, symbol, qty, stop):
        cid = f"stop-{len(self.orders)}"
        self.orders.append((symbol, "STOP_LOSS", qty, stop))
        self.resting[cid] = (symbol, qty, stop)
        return cid

    def _state(self, cid):
        symbol, qty, stop = self.resting[cid]
        if cid in self.executed:
            return B.StopState("FILLED", B.Fill(cid, symbol, "SELL", "FILLED", qty, qty * stop, Decimal("0"), stop))
        return B.StopState("NEW")

    def stop_status(self, symbol, cid, fp):
        assert cid is not None, "a refused guard has no order on Binance to ask about"
        return self._state(cid)

    def cancel_stop(self, symbol, cid, fp):
        assert cid is not None, "a refused guard has no order on Binance to cancel"
        self.orders.append((symbol, "CANCEL", cid))
        if self.unclear:
            return B.StopState("UNKNOWN")
        return self._state(cid) if cid in self.executed else B.StopState("CANCELED")


class TestGuardStops:
    def _op(self, tmp_path, trader):
        from trading_intelligence.execution.order_models import OrderRequest, Position

        loop = FakeLoop(tmp_path)
        loop.runner.paper.positions["BTCUSDT"] = Position("BTCUSDT", Decimal("0.1"), Decimal("100"), Decimal("0"))
        loop.runner.paper._last_price["BTCUSDT"] = Decimal("100")
        loop.runner.paper.pending_orders.append(OrderRequest("BTCUSDT", "SELL", "STOP", Decimal("0.1"),
                                                             stop_price=Decimal("95.009")))
        return _operator(tmp_path, trader, loop), loop

    def test_every_position_gets_a_stop_resting_on_binance(self, tmp_path):
        trader = GuardTrader({"BTCUSDT": Decimal("100")})
        op, loop = self._op(tmp_path, trader)
        op.step(decide=True)
        held = op.session.holdings["BTCUSDT"].qty
        assert trader.orders[0][:2] == ("BTCUSDT", "BUY")
        assert trader.orders[1] == ("BTCUSDT", "STOP_LOSS", held, Decimal("95.00"))  # whole qty, tick-floored
        op.step(decide=False)
        assert sum(1 for o in trader.orders if o[1] == "STOP_LOSS") == 1  # unchanged: not re-sent
        assert Session.load(tmp_path / "session.json").guard_stops["BTCUSDT"]["stop"] == "95.00"
        loop.runner.paper.pending_orders[0].stop_price = Decimal("97")  # the engine raised its stop
        op.step(decide=True)
        assert ("BTCUSDT", "CANCEL", "stop-1") in trader.orders and trader.orders[-1][3] == Decimal("97.00")

    def test_a_stop_executed_while_the_pc_was_off_is_recorded_not_repeated(self, tmp_path):
        trader = GuardTrader({"BTCUSDT": Decimal("100")})
        op, _ = self._op(tmp_path, trader)
        op.step(decide=True)
        trader.executed.add("stop-1")
        trader.prices["BTCUSDT"] = Decimal("94")
        sent_before = sum(1 for o in trader.orders if o[1] == "SELL")
        op.step(decide=False)
        assert "BTCUSDT" not in op.session.holdings and op.session.trades[-1]["reason"].startswith("EXCHANGE_STOP")
        assert sum(1 for o in trader.orders if o[1] == "SELL") == sent_before  # no second sale
        assert op.session.guard_stops == {}

    def test_the_operator_cancels_the_guard_before_selling(self, tmp_path):
        trader = GuardTrader({"BTCUSDT": Decimal("100")})
        op, _ = self._op(tmp_path, trader)
        op.step(decide=True)
        trader.prices["BTCUSDT"] = Decimal("94.5")  # below the 95 stop: the operator sells itself
        op.step(decide=False)
        kinds = [o[1] for o in trader.orders]
        assert kinds.index("CANCEL") < len(kinds) - 1 and kinds[-1] == "SELL" and "BTCUSDT" not in op.session.holdings

    def test_an_unclear_cancel_never_risks_a_double_sale(self, tmp_path):
        trader = GuardTrader({"BTCUSDT": Decimal("100")})
        op, _ = self._op(tmp_path, trader)
        op.step(decide=True)
        trader.unclear = True
        a = mirror.sell(op.session, trader, "BTCUSDT", "TEST")
        assert a.kind == "SKIP" and "UNCLEAR" in a.reason and trader.orders[-1][1] == "CANCEL"
        assert "BTCUSDT" in op.session.holdings

    def test_the_cancel_reveals_an_execution_so_nothing_more_is_sold(self, tmp_path):
        trader = GuardTrader({"BTCUSDT": Decimal("100")})
        op, _ = self._op(tmp_path, trader)
        op.step(decide=True)
        trader.executed.add("stop-1")
        a = mirror.sell(op.session, trader, "BTCUSDT", "TEST")
        assert a.reason == "EXCHANGE_STOP_ALREADY_EXECUTED" and trader.orders[-1][1] == "CANCEL"

    @pytest.mark.parametrize("price,rules", [(Decimal("94"), GUARD_RULES),  # stop at/above price: would fire now
                                             (Decimal("100"), RULES)])  # symbol without STOP_LOSS
    def test_no_guard_where_binance_cannot_hold_one(self, tmp_path, price, rules):
        trader = GuardTrader({"BTCUSDT": Decimal("100")})
        trader.rules = lambda s: rules
        s = Session("s", "tendencia", "t", Decimal("50"))
        s.record_buy("BTCUSDT", Decimal("0.1"), Decimal("10"), Decimal("0"), "t")
        assert mirror.place_guards(s, trader, {"BTCUSDT": Decimal("95")}, {"BTCUSDT": price}) == []
        assert s.guard_stops == {}

    def test_coins_kept_with_parar_lose_the_sessions_guard(self, tmp_path):
        trader = GuardTrader({"BTCUSDT": Decimal("100")})
        op, _ = self._op(tmp_path, trader)
        op.step(decide=True)
        (tmp_path / "STOP").write_text("parar")
        op.run(poll_seconds=0, sleep=lambda s: None, max_iterations=1)
        s = Session.load(tmp_path / "session.json")
        assert "BTCUSDT" in s.holdings and s.guard_stops == {} and trader.orders[-1][1] == "CANCEL"

    def test_sessions_saved_before_guards_still_load(self, tmp_path):
        s = Session("s", "tendencia", "t", Decimal("50"))
        s.save(tmp_path / "s.json")
        data = json.loads((tmp_path / "s.json").read_text())
        del data["guard_stops"]
        (tmp_path / "s.json").write_text(json.dumps(data))
        assert Session.load(tmp_path / "s.json").guard_stops == {}


def test_a_partly_executed_guard_leaves_only_the_rest_to_sell(tmp_path):
    trader = GuardTrader({"BTCUSDT": Decimal("100")})
    s = Session("s", "tendencia", "t", Decimal("50"))
    s.record_buy("BTCUSDT", Decimal("0.2"), Decimal("20"), Decimal("0"), "t")
    s.guard_stops["BTCUSDT"] = {"id": "g1", "qty": "0.2", "stop": "95"}
    part = B.Fill("g1", "BTCUSDT", "SELL", "EXPIRED", Decimal("0.05"), Decimal("4.75"), Decimal("0"), Decimal("95"))
    trader.cancel_stop = lambda sym, cid, fp: B.StopState("EXPIRED", part)
    a = mirror.sell(s, trader, "BTCUSDT", "CLOSE")
    assert a.kind == "SELL" and trader.orders[-1] == ("BTCUSDT", "SELL", Decimal("0.1500"))
    assert "BTCUSDT" not in s.holdings and s.guard_stops == {}


def test_a_refused_guard_is_not_resent_every_minute(tmp_path):
    trader = GuardTrader({"BTCUSDT": Decimal("100")})
    calls = []

    def refuse(sym, qty, stop):
        calls.append(stop)
        raise B.LiveError("Binance rejected the protective stop (code -2010)")

    trader.place_stop = refuse
    s = Session("s", "tendencia", "t", Decimal("50"))
    s.record_buy("BTCUSDT", Decimal("0.1"), Decimal("10"), Decimal("0"), "t")
    prices = {"BTCUSDT": Decimal("100")}
    assert mirror.place_guards(s, trader, {"BTCUSDT": Decimal("95")}, prices)[0].kind == "SKIP"
    assert mirror.place_guards(s, trader, {"BTCUSDT": Decimal("95")}, prices) == [] and len(calls) == 1
    assert mirror.sync_guards(s, trader) == []  # nothing rests on Binance: nothing to ask
    mirror.place_guards(s, trader, {"BTCUSDT": Decimal("96")}, prices)  # a new stop tries again
    assert len(calls) == 2
    a = mirror.sell(s, trader, "BTCUSDT", "CLOSE")  # a refused guard never blocks the sale
    assert a.kind == "SELL" and "BTCUSDT" not in s.holdings


# ------------------------------------------------------------------ USD -> USDT (owner-started)


class ConvertBinance(FakeBinance):
    def __init__(self):
        super().__init__()
        self.mode, self.converts = "ok", {}

    def __call__(self, method, url, headers, timeout):
        path = url.split("api.binance.com")[1].split("?")[0]
        query = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")) if "?" in url else {}
        if path == "/api/v3/order" and query.get("symbol") == "USDTUSD":
            self.calls.append((method, url, dict(headers)))
            if method == "GET":
                body = self.converts.get(query["origClientOrderId"])
                return _resp(200, body) if body else _resp(400, {"code": -2013, "msg": "Order does not exist."})
            cid = query["newClientOrderId"]
            if self.mode == "reject":
                return _resp(400, {"code": -2010, "msg": "Account has insufficient balance"})
            got = (Decimal(query["quoteOrderQty"]) / Decimal("0.999")).quantize(Decimal("1"), rounding="ROUND_DOWN")
            self.converts[cid] = {"symbol": "USDTUSD", "side": "BUY", "clientOrderId": cid, "orderId": 3,
                                  "status": "FILLED", "executedQty": str(got), "cummulativeQuoteQty": query["quoteOrderQty"]}
            if self.mode == "timeout":
                raise TimeoutError("read timed out")
            return _resp(200, self.converts[cid])
        return super().__call__(method, url, headers, timeout)


class TestUsdConversion:
    def _t(self, tmp_path):
        fake = ConvertBinance()
        t = B.SpotTrader(B.Credentials(KEY, KEY), tmp_path / "orders.json", transport=fake, clock=lambda: 1_800_000_000.0)
        t.verify_key()
        return t, fake

    def test_spends_exactly_the_usd_amount_on_usdtusd(self, tmp_path):
        t, fake = self._t(tmp_path)
        assert t.convert_usd_to_usdt(Decimal("38.567")) == Decimal("38")
        method, url, _ = fake.calls[-1]
        assert method == "POST" and "symbol=USDTUSD" in url and "side=BUY" in url and "type=MARKET" in url
        assert "quoteOrderQty=38.56" in url and "quantity=" not in url
        assert t.unresolved() == []
        t.market_order("BTCUSDT", "BUY", Decimal("0.1"), lambda s: Decimal("1"))  # never blocks trading

    def test_rejected_conversion_raises(self, tmp_path):
        t, fake = self._t(tmp_path)
        fake.mode = "reject"
        with pytest.raises(B.LiveError, match="-2010"):
            t.convert_usd_to_usdt(Decimal("10"))

    def test_an_unclear_conversion_is_looked_up_never_resent(self, tmp_path):
        t, fake = self._t(tmp_path)
        fake.mode = "timeout"
        with pytest.raises(B.Unreconciled):
            t.convert_usd_to_usdt(Decimal("38.56"))
        assert t.unresolved() == []  # an unclear conversion never blocks trading or its stops
        fake.mode = "ok"
        assert t.convert_usd_to_usdt(Decimal("38.56")) == Decimal("38")  # it had gone through
        assert sum(1 for c in fake.calls if c[0] == "POST" and "USDTUSD" in c[1]) == 1

    @pytest.mark.parametrize("usdt,usd,expect_usd", [
        (Decimal("0"), Decimal("38.56"), Decimal("38.11")),   # capital 38: 38 x 1.003, capped by USD held
        (Decimal("0"), Decimal("20"), Decimal("20.00")),      # less USD than needed: all of it
        (Decimal("36"), Decimal("38.56"), None),              # 2 missing -> below Binance's 5 USD minimum
        (Decimal("40"), Decimal("38.56"), None),              # enough USDT already
    ])
    def test_converts_only_what_the_capital_lacks(self, usdt, usd, expect_usd):
        from trading_intelligence.live.operator import convert_for_capital

        spent = []

        class T:
            def free_balance(self, asset):
                return {"USDT": usdt, "USD": usd}[asset]

            def convert_usd_to_usdt(self, amount):
                spent.append(amount)
                return amount

        convert_for_capital(T(), Decimal("38"))
        assert spent == ([] if expect_usd is None else [expect_usd])

    def test_conversion_only_with_real(self, tmp_path, capsys):
        from trading_intelligence.live import operator as O

        with pytest.raises(SystemExit):
            O.main(["--dir", str(tmp_path), "iniciar", "--capital", "38", "--convertir-usd"])
        assert "--real" in capsys.readouterr().err and not (tmp_path / "session.json").exists()


class TestTrailingStop:
    """Owner: watch an open trade continuously until its goal; let the stop follow the gain."""

    def _op(self, tmp_path, trader, **kw):
        op = _operator(tmp_path, trader)
        for k, v in kw.items():
            setattr(op, k, v)
        op.session.record_buy("BTCUSDT", Decimal("0.1"), Decimal("10"), Decimal("0"), "t")  # cost 100
        return op

    def test_the_stop_follows_the_peak_once_in_profit(self, tmp_path):
        trader = FakeTrader({"BTCUSDT": Decimal("101")})
        op = self._op(tmp_path, trader)
        assert op._with_trailing({"BTCUSDT": Decimal("95")}, {"BTCUSDT": Decimal("101")}) == {"BTCUSDT": Decimal("95")}
        stops = op._with_trailing({"BTCUSDT": Decimal("95")}, {"BTCUSDT": Decimal("110")})  # +10%: trailing on
        assert stops["BTCUSDT"] == Decimal("106.70")  # 3% under the 110 peak
        stops = op._with_trailing({"BTCUSDT": Decimal("95")}, {"BTCUSDT": Decimal("107")})  # peak is remembered
        assert stops["BTCUSDT"] == Decimal("106.70")

    def test_a_pullback_from_the_peak_sells_within_a_minute(self, tmp_path):
        trader = FakeTrader({"BTCUSDT": Decimal("110")})
        op = self._op(tmp_path, trader)
        op._last_stops = {"BTCUSDT": Decimal("95")}
        op.step(decide=False)
        assert "BTCUSDT" in op.session.holdings and op.session.trail_peaks["BTCUSDT"] == Decimal("110")
        trader.prices["BTCUSDT"] = Decimal("106.5")  # 3.2% off the peak, still +6.5% on cost
        op.step(decide=False)
        assert "BTCUSDT" not in op.session.holdings and op.session.trades[-1]["reason"].startswith("STOP_HIT:106.70")
        assert op.session.realized_pnl > 0 and op.session.trail_peaks == {}
        op.session.record_buy("BTCUSDT", Decimal("0.1"), Decimal("10"), Decimal("0"), "again")
        assert "BTCUSDT" not in op.session.trail_peaks  # a re-entry never inherits the old peak

    def test_never_lowers_the_engine_stop_and_can_be_turned_off(self, tmp_path):
        trader = FakeTrader({"BTCUSDT": Decimal("110")})
        op = self._op(tmp_path, trader)
        assert op._with_trailing({"BTCUSDT": Decimal("108")}, {"BTCUSDT": Decimal("110")})["BTCUSDT"] == Decimal("108")
        op.trailing_pct = Decimal("0")
        assert op._with_trailing({"BTCUSDT": Decimal("95")}, {"BTCUSDT": Decimal("150")}) == {"BTCUSDT": Decimal("95")}

    def test_peaks_survive_a_restart(self, tmp_path):
        trader = FakeTrader({"BTCUSDT": Decimal("110")})
        op = self._op(tmp_path, trader)
        op.step(decide=False)
        assert Session.load(tmp_path / "session.json").trail_peaks == {"BTCUSDT": Decimal("110")}


def test_the_session_loss_limit_is_chosen_at_start_inside_the_owners_range(tmp_path, monkeypatch, capsys):
    from trading_intelligence.live import operator as O

    seen = []
    monkeypatch.setattr(O, "_trader", lambda real, journal: None)
    monkeypatch.setattr(O, "_launch", lambda d, limits, meta, eq, it: seen.append(meta))
    O.main(["--dir", str(tmp_path), "iniciar", "--capital", "100", "--limite-perdida", "50", "--trailing", "4"])
    assert seen[0]["loss_limit_pct"] == "50" and seen[0]["trailing_pct"] == "4"
    with pytest.raises(SystemExit):
        O.main(["--dir", str(tmp_path / "b"), "iniciar", "--capital", "100", "--limite-perdida", "60"])
    assert "outside the owner's approved range" in capsys.readouterr().err


def test_a_leftover_peak_never_reaches_a_new_position():
    s = Session("s", "tendencia", "t", Decimal("50"))
    s.trail_peaks["BTCUSDT"] = Decimal("200")  # left by an older position (e.g. closed while the PC was off)
    s.record_buy("BTCUSDT", Decimal("0.1"), Decimal("10"), Decimal("0"), "new")
    assert "BTCUSDT" not in s.trail_peaks


def test_a_launched_session_runs_with_its_own_loss_limit(tmp_path, monkeypatch):
    from trading_intelligence.live import operator as O

    used = []

    class Spy:
        def __init__(self, d, trader, limits, **kw):
            used.append((limits.loss_limit_pct, kw["trailing_pct"]))

        def run(self, **kw):
            pass

    monkeypatch.setattr(O, "_trader", lambda real, journal: None)
    monkeypatch.setattr(O, "Operator", Spy)
    meta = {"profile": "copiar", "timeframe": "4h", "symbols": ["BTCUSDT"], "real": True,
            "loss_limit_pct": "20", "trailing_pct": "2.5"}
    O._launch(tmp_path, load_limits(), meta, "100", 1)
    O._launch(tmp_path, load_limits(), {**meta, "loss_limit_pct": None}, "100", 1)  # older sessions: default
    assert used == [(Decimal("20"), Decimal("2.5")), (Decimal("35"), Decimal("2.5"))]


# ------------------------------------------------------------------ connection check (no money)


class OrderTestBinance(FakeBinance):
    def __init__(self, answer=(200, {})):
        super().__init__()
        self.answer = answer

    def __call__(self, method, url, headers, timeout):
        if "/api/v3/order/test" in url:
            self.calls.append((method, url, dict(headers)))
            return _resp(*self.answer)
        return super().__call__(method, url, headers, timeout)


class TestConnectionCheck:
    def test_the_test_endpoint_is_signed_and_executes_nothing(self, tmp_path):
        fake = OrderTestBinance()
        t, _ = _trader(tmp_path, fake)
        t.verify_key()
        t.test_order("BTCUSDT", "BUY", Decimal("0.0001"))
        method, url, headers = fake.calls[-1]
        assert method == "POST" and "/api/v3/order/test?" in url and "signature=" in url
        assert "quantity=0.0001" in url and "type=MARKET" in url
        assert not any("/api/v3/order?" in c[1] for c in fake.calls)  # nothing real was sent
        assert t.journal.read() == {}  # and nothing was journaled as an order

    def test_a_refused_test_order_raises_and_an_unchecked_key_sends_nothing(self, tmp_path):
        fake = OrderTestBinance((400, {"code": -2010, "msg": "no"}))
        t, _ = _trader(tmp_path, fake)
        with pytest.raises(B.UnsafeKey):
            t.test_order("BTCUSDT", "BUY", Decimal("0.0001"))
        assert not fake.calls
        t.verify_key()
        with pytest.raises(B.LiveError, match="-2010"):
            t.test_order("BTCUSDT", "BUY", Decimal("0.0001"))

    def test_check_connection_reports_and_never_trades(self):
        from trading_intelligence.live.operator import check_connection

        class Probe(FakeTrader):
            def __init__(self):
                super().__init__({"BTCUSDT": Decimal("100")})
                self.tested = []

            def test_order(self, symbol, side, qty):
                self.tested.append((symbol, side, qty))

        p = Probe()
        lines = check_connection(p, LIMITS, "BTCUSDT", Decimal("6"))
        assert p.tested == [("BTCUSDT", "BUY", Decimal("0.06"))] and p.orders == []
        assert "SIN ejecutarse" in lines[1] and "no se movió dinero" in lines[-1]
        assert check_connection(p, LIMITS, "DOGEUSDT", Decimal("6"))[0].startswith("DOGEUSDT no está")
        assert "mínimo" in check_connection(p, LIMITS, "BTCUSDT", Decimal("4"))[0]
        assert len(p.tested) == 1  # refused requests sent nothing


class TestRealTestTrade:
    """Owner: "haz la prueba real". Smallest real buy+sell, selling only what the buy delivered."""

    class Probe(FakeTrader):
        def __init__(self, free=Decimal("1000"), sell_fails=False):
            super().__init__({"BTCUSDT": Decimal("100")}, free)
            self.tested, self.sell_fails = [], sell_fails

        def test_order(self, symbol, side, qty):
            self.tested.append((symbol, side, qty))

        def market_order(self, symbol, side, qty, fp):
            if side == "SELL" and self.sell_fails:
                raise B.LiveError("Binance rejected the order (code -2010)")
            self.orders.append((symbol, side, qty))
            p = self.prices[symbol]
            net = qty * Decimal("0.999") if side == "BUY" else qty  # BUY fee taken in the coin
            return B.Fill("x", symbol, side, "FILLED", net, qty * p, qty * p * Decimal("0.001"), p)

    def test_buys_then_sells_exactly_what_the_buy_delivered(self):
        from trading_intelligence.live.operator import real_test_trade

        p = self.Probe()
        lines = real_test_trade(p, LIMITS, "BTCUSDT", Decimal("6"))
        assert p.tested == [("BTCUSDT", "BUY", Decimal("0.06"))]  # validated first
        assert p.orders == [("BTCUSDT", "BUY", Decimal("0.06")), ("BTCUSDT", "SELL", Decimal("0.0599"))]
        assert lines[-1] == "prueba real completa: el sistema compra y vende en tu cuenta"
        assert any(line.startswith("costo de la prueba:") for line in lines)

    def test_nothing_is_bought_without_money_or_on_a_refused_check(self):
        from trading_intelligence.live.operator import real_test_trade

        p = self.Probe(free=Decimal("5"))
        assert "insuficiente" in real_test_trade(p, LIMITS, "BTCUSDT", Decimal("6"))[-1] and p.orders == []
        p = self.Probe()
        assert real_test_trade(p, LIMITS, "DOGEUSDT", Decimal("6"))[0].startswith("DOGEUSDT no está")
        assert "mínimo" in real_test_trade(p, LIMITS, "BTCUSDT", Decimal("4"))[0] and p.orders == []

    def test_a_failed_sell_tells_the_owner_what_is_left(self):
        from trading_intelligence.live.operator import real_test_trade

        p = self.Probe(sell_fails=True)
        last = real_test_trade(p, LIMITS, "BTCUSDT", Decimal("6"))[-1]
        assert last.startswith("ATENCIÓN: la venta no se completó") and "0.05994 BTCUSDT" in last
        assert [o[1] for o in p.orders] == ["BUY"]

    def test_the_cli_caps_the_real_test_before_touching_keys(self, tmp_path, monkeypatch):
        from trading_intelligence.live import operator as O

        monkeypatch.setattr(O, "SpotTrader", lambda *a, **k: pytest.fail("no trader for a refused amount"))
        with pytest.raises(SystemExit):
            O.main(["--dir", str(tmp_path / "current"), "prueba", "--real", "--usdt", "11"])

    def test_without_real_the_cli_never_buys(self, tmp_path, monkeypatch, capsys):
        from trading_intelligence.live import operator as O

        probe = self.Probe()
        probe.verify_key = lambda: True
        monkeypatch.setattr(O, "SpotTrader", lambda *a, **k: probe)
        monkeypatch.setattr(O.Credentials, "from_env", classmethod(lambda cls, env=None: None))
        O.main(["--dir", str(tmp_path / "current"), "prueba", "--simbolo", "BTCUSDT"])
        assert probe.orders == [] and probe.tested  # validated, nothing executed
        assert "no se movió dinero" in capsys.readouterr().out
        O.main(["--dir", str(tmp_path / "current"), "prueba", "--simbolo", "BTCUSDT", "--real"])
        assert [o[1] for o in probe.orders] == ["BUY", "SELL"]
        assert (tmp_path / "prueba").is_dir()  # its own journal folder, beside the session's


def test_the_owner_hears_plain_words_at_the_warning_and_at_the_stop(tmp_path):
    sent = []
    trader = FakeTrader({"BTCUSDT": Decimal("100")})
    op = _operator(tmp_path, trader)
    op.notify = sent.append
    op.session.record_buy("BTCUSDT", Decimal("0.2"), Decimal("20"), Decimal("0"), "t")
    trader.prices["BTCUSDT"] = Decimal("60")  # loss 8 of the 10 limit: warning (2 USDT before)
    op.step(decide=False)
    assert sent[0].startswith("⚠️ Vas perdiendo 8,00 USDT y tu límite es 10,00 USDT") and "continúa" in sent[0]
    trader.prices["BTCUSDT"] = Decimal("49")
    op.step(decide=False)
    assert any(m.startswith("🛑 Se alcanzó tu límite de pérdida") for m in sent)


# ------------------------------------------------------------------ owner orders, adopting coins, back to USDT, fees

BTC_RULES = B.SymbolRules(step=Decimal("0.00001"), min_qty=Decimal("0.00001"), min_notional=Decimal("5"))


class Wallet(FakeTrader):
    """FakeTrader with real per-asset balances that market orders move (fee taken in the coin on buys)."""

    def __init__(self, prices, balances, rules=RULES):
        super().__init__(prices)
        self.balances, self._rules = dict(balances), rules

    def rules(self, s):
        return self._rules

    def free_balance(self, a):
        return self.balances.get(a, Decimal("0"))

    def test_order(self, symbol, side, qty):
        pass

    def market_order(self, symbol, side, qty, fp):
        p, coin = self.prices[symbol], symbol[:-4]
        if qty * p < self._rules.min_notional:
            raise B.LiveError("Binance rejected the order (code -1013)")
        self.orders.append((symbol, side, qty))
        if side == "BUY":
            got = qty * Decimal("0.999")
            self.balances["USDT"] -= qty * p
            self.balances[coin] = self.balances.get(coin, Decimal("0")) + got
            return B.Fill("x", symbol, side, "FILLED", got, qty * p, qty * p * Decimal("0.001"), p)
        self.balances[coin] -= qty
        self.balances["USDT"] += qty * p * Decimal("0.999")
        return B.Fill("x", symbol, side, "FILLED", qty, qty * p * Decimal("0.999"), qty * p * Decimal("0.001"), p)


class TestRealTestTradeMinimum:
    def test_the_sale_always_clears_the_exchange_minimum(self):
        """2026-10-09 on the owner's PC: 6 USDT of BTC left 0.00006993 BTC, i.e. 0.00006 after
        rounding = 4.97 USDT, and Binance refused the sale (-1013). The buy now covers that."""
        from trading_intelligence.live.operator import real_test_trade, sellable_buy_qty

        price = Decimal("82857")
        qty = sellable_buy_qty(BTC_RULES, price, Decimal("6"))
        assert BTC_RULES.floor_qty(qty * Decimal("0.999")) * price >= Decimal("5.25")
        w = Wallet({"BTCUSDT": price}, {"USDT": Decimal("32")}, BTC_RULES)
        lines = real_test_trade(w, LIMITS, "BTCUSDT", Decimal("6"))
        assert [o[1] for o in w.orders] == ["BUY", "SELL"] and lines[-1].startswith("prueba real completa")

    def test_a_cap_too_low_for_a_sellable_round_trip_buys_nothing(self):
        from trading_intelligence.live import operator as O

        w = Wallet({"BTCUSDT": Decimal("82857")}, {"USDT": Decimal("32")},
                   B.SymbolRules(step=Decimal("0.0001"), min_qty=Decimal("0.0001"), min_notional=Decimal("5")))
        # 9 USDT buys 0.0001 BTC, but after the coin fee 0.00009 rounds down to 0: selling needs 0.0002 = 16.57 > 10
        assert "tope de la prueba" in O.real_test_trade(w, LIMITS, "BTCUSDT", Decimal("9"))[-1] and w.orders == []


class TestToUsdt:
    def test_a_leftover_below_the_minimum_is_topped_up_then_sold_whole(self):
        from trading_intelligence.live.operator import to_usdt

        w = Wallet({"BTCUSDT": Decimal("82857")}, {"USDT": Decimal("32"), "BTC": Decimal("0.00006993")}, BTC_RULES)
        lines = to_usdt(w, LIMITS, "BTCUSDT", set())
        sides = [o[1] for o in w.orders]
        assert sides == ["BUY", "SELL"] and w.orders[0][2] * Decimal("82857") >= 5
        assert w.balances["BTC"] < BTC_RULES.step  # only rounding dust stays
        assert lines[-1].startswith("listo: tu BTC pasó a USDT")

    def test_a_sellable_amount_is_sold_without_buying(self):
        from trading_intelligence.live.operator import to_usdt

        w = Wallet({"BTCUSDT": Decimal("82857")}, {"USDT": Decimal("1"), "BTC": Decimal("0.0002")}, BTC_RULES)
        to_usdt(w, LIMITS, "BTCUSDT", set())
        assert [o[1] for o in w.orders] == ["SELL"] and w.orders[0][2] == Decimal("0.0002")

    def test_never_touches_what_the_session_trades_or_unapproved_coins(self):
        from trading_intelligence.live.operator import to_usdt

        w = Wallet({"BTCUSDT": Decimal("82857")}, {"USDT": Decimal("32"), "BTC": Decimal("0.001")}, BTC_RULES)
        assert "la sesión está operando" in to_usdt(w, LIMITS, "BTCUSDT", {"BTCUSDT"})[0]
        assert "no está entre las monedas aprobadas" in to_usdt(w, LIMITS, "DOGEUSDT", set())[0]
        assert w.orders == []


class TestOwnerOrders:
    """continuar / agregar / adoptar must reach the RUNNING operator: it owns session.json."""

    def test_continue_written_while_running_is_not_lost(self, tmp_path):
        from trading_intelligence.live import operator as O

        sent = []
        trader = FakeTrader({"BTCUSDT": Decimal("100")})
        op = _operator(tmp_path, trader)
        op.notify = sent.append
        op.session.record_buy("BTCUSDT", Decimal("0.2"), Decimal("20"), Decimal("0"), "t")
        trader.prices["BTCUSDT"] = Decimal("60")
        op.step(decide=False)
        assert op.session.status == WAITING_OWNER
        (tmp_path / "OPERATOR.lock").write_text("1")  # this operator is alive
        assert O.main(["--dir", str(tmp_path), "continuar"]) == 0
        assert Session.load(tmp_path / "session.json").status == WAITING_OWNER  # the CLI did not write it
        op.step(decide=False)
        assert op.session.status == RUNNING and not (tmp_path / O.INBOX).exists()
        assert Session.load(tmp_path / "session.json").status == RUNNING  # and the running operator kept it
        assert any("sigo operando" in m for m in sent)

    def test_add_and_adopt_go_through_the_inbox(self, tmp_path):
        from trading_intelligence.live import operator as O

        sent = []
        w = Wallet({"BTCUSDT": Decimal("100")}, {"USDT": Decimal("50"), "BTC": Decimal("0.3")})
        op = _operator(tmp_path, w)
        op.notify = sent.append
        O.queue_owner_order(tmp_path, {"cmd": "agregar", "capital": "10"})
        O.queue_owner_order(tmp_path, {"cmd": "adoptar", "simbolo": "BTCUSDT"})
        O.queue_owner_order(tmp_path, {"cmd": "adoptar", "simbolo": "DOGEUSDT"})
        O.queue_owner_order(tmp_path, {"cmd": "agregar", "capital": "-5"})  # refused, never crashes
        equity_before = op.session.equity({"BTCUSDT": Decimal("100")})
        op.step(decide=False)
        s = op.session
        assert s.capital == Decimal("90") and s.holdings["BTCUSDT"].qty == Decimal("0.3")
        assert s.equity({"BTCUSDT": Decimal("100")}) - equity_before == Decimal("40")  # added, not a gain
        assert s.available == Decimal("60")  # adopting spends no USDT
        assert any("Sumé a la sesión tu BTC" in m for m in sent) and any("DOGE no está" in m for m in sent)
        assert any("No pude aplicar tu orden" in m for m in sent)

    def test_without_a_running_operator_continue_is_applied_directly_and_adopt_refuses(self, tmp_path):
        from trading_intelligence.live import operator as O

        s = Session("s1", "tendencia", "t", Decimal("50"))
        s.status = WAITING_OWNER
        s.save(tmp_path / "session.json")
        assert O.main(["--dir", str(tmp_path), "continuar"]) == 0
        assert Session.load(tmp_path / "session.json").status == RUNNING
        assert O.main(["--dir", str(tmp_path), "adoptar", "--simbolo", "BTCUSDT"]) == 1
        assert not (tmp_path / O.INBOX).exists()


class TestCommissions:
    def test_reads_this_accounts_fees_and_flags_promotions(self, tmp_path):
        from trading_intelligence.live.operator import fee_lines

        class FeeFake(FakeBinance):
            def __call__(self, method, url, headers, timeout):
                if "/api/v3/account/commission" in url:
                    self.calls.append((method, url, dict(headers)))
                    zero = "symbol=BTCUSDT" in url
                    return _resp(200, {"symbol": "X", "standardCommission": {
                        "maker": "0" if zero else "0.001", "taker": "0" if zero else "0.001"},
                        "discount": {"enabledForAccount": True, "enabledForSymbol": True,
                                     "discountAsset": "BNB", "discount": "0.75"}})  # pays 75%
                return super().__call__(method, url, headers, timeout)

        fake = FeeFake()
        t, _ = _trader(tmp_path, fake)
        t.verify_key()
        lines = fee_lines(t, ["BTCUSDT", "ETHUSDT"])
        assert "PROMOCIÓN: sin comisión" in lines[0] and "PROMOCIÓN" not in lines[1]
        assert lines[1] == ("ETH: comisión 0.100% (órdenes a mercado), 0.100% (órdenes límite); "
                            "pagando con BNB baja un 25%.")
        assert all("signature=" in c[1] for c in fake.calls if "commission" in c[1])


# --- 20-minute decisions inside the owner's windows (owner, 2026-10-09: "Todo a 20 min") ----


class TestTradingWindows:
    def test_ecuador_windows_map_to_utc(self):
        from trading_intelligence.live import operator as O

        w = O.parse_windows(list(O.OWNER_WINDOWS))
        assert w == [(12 * 60, 180), (22 * 60, 120)]  # 07-10 and 17-19 Ecuador = 12-15 and 22-24 UTC
        at = lambda h, m=0: datetime(2026, 10, 9, h, m, tzinfo=timezone.utc)  # noqa: E731
        assert O.in_windows(w, at(12)) and O.in_windows(w, at(14, 59)) and not O.in_windows(w, at(15))
        assert O.in_windows(w, at(23, 59)) and not O.in_windows(w, at(0)) and not O.in_windows(w, at(11, 59))
        for bad in (["7"], ["10-07"], ["07-25"], ["a-b"]):
            with pytest.raises(ValueError):
                O.parse_windows(bad)

    def _op(self, tmp_path, now, sent, timeframe="5m", **kw):
        from trading_intelligence.execution.order_models import OrderRequest, Position

        trader = FakeTrader({"BTCUSDT": Decimal("100")})
        loop = FakeLoop(tmp_path)
        loop.runner.paper.positions["BTCUSDT"] = Position("BTCUSDT", Decimal("0.1"), Decimal("100"), Decimal("0"))
        loop.runner.paper._last_price["BTCUSDT"] = Decimal("100")
        loop.runner.paper.pending_orders.append(OrderRequest("BTCUSDT", "SELL", "STOP", Decimal("0.1"),
                                                             stop_price=Decimal("95")))
        Session("s1", "tendencia", "t", Decimal("50")).save(tmp_path / "session.json")
        op = Operator(tmp_path, trader, LIMITS, profile="tendencia", timeframe=timeframe, symbols=["BTCUSDT"],
                      loop=loop, clock=lambda: now[0], notify=sent.append, windows=["07-10", "17-19"], **kw)
        return op, trader, loop

    def test_outside_the_windows_it_also_trades(self, tmp_path):
        now, sent = [datetime(2026, 10, 9, 11, 40, 30, tzinfo=timezone.utc)], []
        op, trader, loop = self._op(tmp_path, now, sent)
        op.step(decide=True)  # 06:40 Ecuador: outside the windows it still buys on a signal
        assert loop.ticks == 1 and trader.orders[0][:2] == ("BTCUSDT", "BUY") and sent[0].startswith("🟢 Compré")
        now[0] = datetime(2026, 10, 9, 12, 0, 30, tzinfo=timezone.utc)
        op.step(decide=False)  # 07:00 Ecuador
        assert sent[-1].startswith("🕖 Empezó tu horario de trading (07:00 a 10:00 y 17:00 a 19:00")
        assert "opero sin parar: decido cada 5 minutos" in sent[-1]
        now[0] = datetime(2026, 10, 9, 15, 0, 30, tzinfo=timezone.utc)
        op.step(decide=False)
        assert sent[-1].startswith("🕙 Terminó tu horario intenso") and "cada 20 minutos" in sent[-1]

    def _decisions(self, tmp_path, start, minutes, **kw):
        now, sent = [start], []
        op, trader, loop = self._op(tmp_path, now, sent, **kw)

        def sleep(_):
            now[0] += timedelta(minutes=1)

        op.run(poll_seconds=60, sleep=sleep, max_iterations=minutes)
        return loop.ticks

    def test_inside_the_windows_it_decides_at_every_5m_bar(self, tmp_path):
        assert self._decisions(tmp_path, datetime(2026, 10, 9, 12, 0, 30, tzinfo=timezone.utc), 60) == 12

    def test_outside_the_windows_it_decides_every_20_minutes(self, tmp_path):
        assert self._decisions(tmp_path, datetime(2026, 10, 9, 16, 0, 30, tzinfo=timezone.utc), 60) == 3

    def test_owner_cadence_2_minutes_inside_and_5_outside(self, tmp_path):
        # Owner, 2026-10-10: "cada 5 minutos fuera del horario y dentro del horario cada 2 minutos"
        kw = dict(timeframe="1m", inside_every_min=2, outside_every_min=5)
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        inside = self._decisions(tmp_path / "a", datetime(2026, 10, 9, 12, 0, 30, tzinfo=timezone.utc), 60, **kw)
        outside = self._decisions(tmp_path / "b", datetime(2026, 10, 9, 16, 0, 30, tzinfo=timezone.utc), 60, **kw)
        assert (inside, outside) == (30, 12)

    def test_a_1m_session_gets_the_owners_cadence_by_default(self, tmp_path, monkeypatch):
        from trading_intelligence.live import operator as O

        launched = []
        monkeypatch.setattr(O, "_trader", lambda real, journal: FakeTrader({"BTCUSDT": Decimal("100")}))
        monkeypatch.setattr(O, "_launch", lambda d, limits, meta, eq, it: launched.append(meta))
        O.main(["--dir", str(tmp_path), "iniciar", "--capital", "32", "--temporalidad", "1m", "--real",
                "--perfil", "tendencia_rango"])
        m = launched[0]
        assert (m["timeframe"], m["windows"], m["inside_every_min"], m["outside_every_min"]) == (
            "1m", ["07-10", "17-19"], 2, 5)

    def test_stops_work_every_minute_outside_the_windows(self, tmp_path):
        now, sent = [datetime(2026, 10, 9, 16, 0, 30, tzinfo=timezone.utc)], []
        op, trader, loop = self._op(tmp_path, now, sent)
        op.step(decide=True)
        trader.prices["BTCUSDT"] = Decimal("94")
        now[0] += timedelta(minutes=1)
        op.step(decide=False)  # no decision due, but the stop is enforced
        assert trader.orders[-1][1] == "SELL" and not op.session.holdings

    @pytest.mark.parametrize("timeframe", ["5m", "20m"])
    def test_a_windowed_real_session_starts_with_the_owners_windows(self, tmp_path, monkeypatch, timeframe):
        from trading_intelligence.live import operator as O

        launched = []
        monkeypatch.setattr(O, "_trader", lambda real, journal: FakeTrader({"BTCUSDT": Decimal("100")}))
        monkeypatch.setattr(O, "_launch", lambda d, limits, meta, eq, it: launched.append(meta))
        O.main(["--dir", str(tmp_path), "iniciar", "--capital", "37.77", "--temporalidad", timeframe, "--real",
                "--perfil", "tendencia_rango"])
        assert launched[0]["timeframe"] == timeframe and launched[0]["windows"] == ["07-10", "17-19"]
        assert json.loads((tmp_path / "meta.json").read_text())["windows"] == ["07-10", "17-19"]


def test_a_repeated_dust_skip_is_noted_once(tmp_path):
    trader = FakeTrader({"BTCUSDT": Decimal("100")})
    op = _operator(tmp_path, trader)
    op.session.record_buy("BTCUSDT", Decimal("0.00001"), Decimal("0.001"), Decimal("0"), "ADOPTED")  # dust
    loop = FakeLoop(tmp_path)  # the engine holds nothing: the mirror tries to close the dust every pass
    op.loop = loop
    for _ in range(5):
        op.step(decide=True)
    skips = [e for e in op.session.events if e.get("kind") == "SKIP"]
    assert len(skips) == 1 and "DUST" in skips[0]["text"]
