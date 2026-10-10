"""Binance USDⓈ-M Futures in both directions: key safety, sizing, SL/TP on the Algo service, SHADOW."""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pytest

from trading_intelligence.live import binance_futures as F
from trading_intelligence.live.binance_live import HttpResponse, Unreconciled
from trading_intelligence.live.two_way import TwoWayAuto

GOOD_KEY = {"ipRestrict": True, "enableReading": True, "enableFutures": True, "enableWithdrawals": False,
            "enableInternalTransfer": False, "permitsUniversalTransfer": False, "enableMargin": False,
            "enableSpotAndMarginTrading": False, "enableVanillaOptions": False}
ENV = {F.KEY_VAR: "k" * 64, F.SECRET_VAR: "s" * 64}


def _resp(body, status=200):
    return HttpResponse(status, {}, json.dumps(body).encode())


class FakeFapi:
    """Just enough of fapi.binance.com: one-way positions, market orders and algo orders."""

    def __init__(self, price=150.0, balance="37", key=None, dual=False):
        self.price, self.balance, self.key, self.dual = price, balance, dict(key or GOOD_KEY), dual
        self.positions: dict[str, Decimal] = {}
        self.algos: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict]] = []
        self.fail_algo_type: str | None = None
        self.order_mode = "ok"  # ok | lost (network failure after Binance executed) | gone (never arrived)
        self.last_bar = None  # (low, high) of the newest 1m bar
        self.next_algo = 1

    def _bars(self, interval, limit):
        step = {"1m": 60, "5m": 300, "1h": 3600}[interval]
        now = int(datetime.now(timezone.utc).timestamp()) // step * step
        rng = np.random.default_rng(7)
        closes = self.price * np.exp(np.cumsum(rng.normal(0, 0.003, limit)))
        closes = closes / closes[-1] * self.price
        rows = []
        for i, c in enumerate(closes):
            t = (now - (limit - 1 - i) * step) * 1000
            lo, hi = c * 0.998, c * 1.002
            if i == limit - 1 and self.last_bar is not None and interval == "1m":
                lo, hi = self.last_bar
            rows.append([t, str(c), str(hi), str(lo), str(c), "10"])
        return rows

    def __call__(self, method, url, headers, timeout):
        parts = urllib.parse.urlsplit(url)
        q = dict(urllib.parse.parse_qsl(parts.query))
        path = parts.path
        self.calls.append((method, path, q))
        if path == "/fapi/v1/time":
            return _resp({"serverTime": int(datetime.now(timezone.utc).timestamp() * 1000)})
        if path == "/fapi/v1/klines":
            return _resp(self._bars(q["interval"], int(q["limit"])))
        if path == "/fapi/v1/ticker/bookTicker":
            return _resp({"symbol": q["symbol"], "bidPrice": str(self.price - 0.01), "askPrice": str(self.price + 0.01)})
        if path == "/fapi/v1/exchangeInfo":
            return _resp({"symbols": [{"symbol": "SOLUSDT", "status": "TRADING", "contractType": "PERPETUAL",
                                       "quoteAsset": "USDT", "filters": [
                                           {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                           {"filterType": "LOT_SIZE", "stepSize": "0.01", "minQty": "0.01"},
                                           {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.01", "minQty": "0.01"},
                                           {"filterType": "MIN_NOTIONAL", "notional": "5"}]},
                                      {"symbol": "BTCUSDT", "status": "TRADING", "contractType": "PERPETUAL",
                                       "quoteAsset": "USDT", "filters": [
                                           {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                                           {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                                           {"filterType": "MIN_NOTIONAL", "notional": "100"}]}]})
        if path == "/sapi/v1/account/apiRestrictions":
            assert parts.netloc == F.SPOT_HOST
            return _resp(self.key)
        assert parts.netloc == F.FAPI_HOST
        if path == "/fapi/v1/positionSide/dual":
            return _resp({"dualSidePosition": self.dual})
        if path == "/fapi/v3/account":
            return _resp({"totalMarginBalance": self.balance, "availableBalance": self.balance})
        if path == "/fapi/v3/positionRisk":
            return _resp([{"symbol": s, "positionAmt": str(a), "entryPrice": str(self.price)}
                          for s, a in self.positions.items() if a != 0])
        if path == "/fapi/v1/openAlgoOrders":
            return _resp(list(self.algos.values()))
        if path in ("/fapi/v1/marginType", "/fapi/v1/leverage"):
            return _resp({"code": 200, "msg": "success"})
        if path == "/fapi/v1/order" and method == "POST":
            assert "stopPrice" not in q and q["type"] == "MARKET", "conditional orders go to the Algo service"
            if self.order_mode == "gone":
                raise TimeoutError("no answer")
            qty = Decimal(q["quantity"]) * (1 if q["side"] == "BUY" else -1)
            self.positions[q["symbol"]] = self.positions.get(q["symbol"], Decimal("0")) + qty
            self.orders[q["newClientOrderId"]] = {"status": "FILLED", "executedQty": q["quantity"],
                                                  "avgPrice": str(self.price)}
            if self.order_mode == "lost":
                raise TimeoutError("executed, answer lost")
            return _resp({**self.orders[q["newClientOrderId"]], "clientOrderId": q["newClientOrderId"]})
        if path == "/fapi/v1/order" and method == "GET":
            o = self.orders.get(q["origClientOrderId"])
            return _resp(o) if o else _resp({"code": -2013, "msg": "Order does not exist."}, 400)
        if path == "/fapi/v1/algoOrder" and method == "POST":
            if q["type"] == self.fail_algo_type:
                return _resp({"code": -2021, "msg": "Order would immediately trigger."}, 400)
            algo_id = str(self.next_algo)
            self.next_algo += 1
            self.algos[algo_id] = {**q, "algoId": algo_id, "algoStatus": "NEW"}
            return _resp({"algoId": algo_id, "clientAlgoId": q["clientAlgoId"], "algoStatus": "NEW"})
        if path == "/fapi/v1/algoOrder" and method == "DELETE":
            self.algos.pop(q["algoId"], None)
            return _resp({"algoId": q["algoId"], "code": "200"})
        raise AssertionError(f"unexpected call {method} {path}")


def _limits(**kw):
    base = dict(approved=True, max_leverage=1, risk_pct=Decimal("1"), max_position_pct=Decimal("40"), max_open=3,
                loss_limit_pct=Decimal("45"), loss_range=(Decimal("20"), Decimal("50")), warn_before_usd=Decimal("2"),
                profit_target_pct=Decimal("58"), symbols=("SOLUSDT", "BTCUSDT"))
    base.update(kw)
    return F.FuturesLimits(**base)


def _real(tmp_path, fake=None, **kw):
    fake = fake or FakeFapi()
    market = F.FuturesMarket(F.FuturesCredentials.from_env(ENV), tmp_path / "orders.json", transport=fake)
    return F.FuturesBroker(market, _limits(**kw)), fake


# --- the key and the account ---------------------------------------------------------------------

def test_a_key_with_withdrawals_or_transfers_is_refused_and_spot_trading_is_tolerated(tmp_path):
    F.check_futures_key(GOOD_KEY)
    F.check_futures_key({**GOOD_KEY, "enableSpotAndMarginTrading": True})
    for bad in ({"enableWithdrawals": True}, {"enableInternalTransfer": True}, {"permitsUniversalTransfer": True},
                {"enableMargin": True}, {"ipRestrict": False}, {"enableFutures": False}, {"enableNewThing": True}):
        with pytest.raises(F.UnsafeFuturesKey):
            F.check_futures_key({**GOOD_KEY, **bad})


def test_hedge_mode_is_refused(tmp_path):
    broker, _ = _real(tmp_path, FakeFapi(dual=True))
    with pytest.raises(F.FuturesError, match="unidireccional"):
        broker.market.verify()


def test_only_binance_hosts_and_never_a_key_in_the_repr():
    with pytest.raises(F.FuturesError):
        F.urllib_transport("GET", "https://evil.example.com/fapi/v1/time", {}, 1)
    creds = F.FuturesCredentials.from_env(ENV)
    assert "k" * 16 not in repr(creds) and "s" * 16 not in repr(F.FuturesMarket(creds))


def test_real_orders_need_limits_the_owner_approved(tmp_path):
    with pytest.raises(F.FuturesError, match="no están aprobados"):
        _real(tmp_path, approved=False)
    limits = F.load_futures_limits()  # the committed file: the Spot program's numbers, approved 2026-10-10
    assert limits.approved and limits.max_leverage == 1 and limits.risk_pct == 1
    assert limits.max_position_pct == 40 and limits.max_open == 3 and limits.loss_limit_pct == 45
    assert limits.warn_before_usd == 2 and limits.profit_target_pct == 58
    with pytest.raises(F.FuturesError, match="fuera de la banda"):
        limits.for_session(Decimal("60"))


# --- size, stop and target ---------------------------------------------------------------------------

def test_size_comes_from_risk_is_capped_and_never_rounds_up(tmp_path):
    market = F.FuturesMarket(None, transport=FakeFapi())
    p = F.size_plan(market, "SOLUSDT", "BUY", Decimal("37"), Decimal("1"), "5m", 1, Decimal("40"))
    stop_pct = (p.price - p.sl) / p.price * 100
    assert Decimal("3") <= stop_pct <= Decimal("15.1") and p.sl < p.price < p.tp
    assert p.qty * p.price <= Decimal("37") * Decimal("0.4") and p.qty == (p.qty / Decimal("0.01")).to_integral_value() * Decimal("0.01")
    s = F.size_plan(market, "SOLUSDT", "SELL", Decimal("37"), Decimal("1"), "5m", 1, Decimal("40"))
    assert s.tp < s.price < s.sl


def test_below_binances_minimum_there_is_no_trade(tmp_path):
    market = F.FuturesMarket(None, transport=FakeFapi(price=60000.0))
    with pytest.raises(F.FuturesError, match="no llega al mínimo"):
        F.size_plan(market, "BTCUSDT", "BUY", Decimal("37"), Decimal("1"), "5m", 1, Decimal("40"))


# --- real orders -------------------------------------------------------------------------------------

def test_an_entry_gets_isolated_margin_its_leverage_a_stop_and_a_target_on_the_algo_service(tmp_path):
    broker, fake = _real(tmp_path)
    plan = broker.plan("SOLUSDT", "SELL", Decimal("1"), "5m")
    broker.open(plan)
    paths = [(m, p) for m, p, _ in fake.calls]
    assert ("POST", "/fapi/v1/marginType") in paths and ("POST", "/fapi/v1/leverage") in paths
    lev = next(q for m, p, q in fake.calls if p == "/fapi/v1/leverage")
    assert lev["leverage"] == "1" and fake.positions["SOLUSDT"] == -plan.qty
    kinds = {a["type"]: a for a in fake.algos.values()}
    assert set(kinds) == {"STOP_MARKET", "TAKE_PROFIT_MARKET"}
    assert all(a["closePosition"] == "true" and a["side"] == "BUY" and a["algoType"] == "CONDITIONAL"
               and a["workingType"] == "MARK_PRICE" for a in kinds.values())
    assert Decimal(kinds["STOP_MARKET"]["triggerPrice"]) == plan.sl
    journal = json.loads((tmp_path / "orders.json").read_text())["orders"]
    assert [r["state"] for r in journal.values()] == ["FILLED"]


def test_if_the_stop_is_refused_the_position_is_closed_at_once(tmp_path):
    broker, fake = _real(tmp_path)
    fake.fail_algo_type = "STOP_MARKET"
    plan = broker.plan("SOLUSDT", "BUY", Decimal("1"), "5m")
    with pytest.raises(F.FuturesError, match="cerré la posición"):
        broker.open(plan)
    assert fake.positions["SOLUSDT"] == 0
    closing = [q for m, p, q in fake.calls if p == "/fapi/v1/order" and m == "POST"][-1]
    assert closing["reduceOnly"] == "true" and closing["side"] == "SELL"


def test_a_lost_answer_is_looked_up_never_resent(tmp_path):
    broker, fake = _real(tmp_path)
    fake.order_mode = "lost"
    plan = broker.plan("SOLUSDT", "BUY", Decimal("1"), "5m")
    broker.open(plan)  # Binance executed it: found by client id, then protected
    sent = [q for m, p, q in fake.calls if p == "/fapi/v1/order" and m == "POST"]
    assert len(sent) == 1 and fake.positions["SOLUSDT"] == plan.qty and len(fake.algos) == 2


def test_an_order_that_never_arrived_is_not_assumed_and_nothing_is_resent(tmp_path):
    broker, fake = _real(tmp_path)
    fake.order_mode = "gone"
    plan = broker.plan("SOLUSDT", "BUY", Decimal("1"), "5m")
    with pytest.raises(F.FuturesError, match="no llegó"):
        broker.open(plan)
    assert fake.positions.get("SOLUSDT", 0) == 0 and not fake.algos


def test_an_unclear_order_blocks_new_entries(tmp_path):
    broker, fake = _real(tmp_path)
    broker.market._set("TIF-x", state="UNCERTAIN", symbol="SOLUSDT")

    def unclear(method, url, headers, timeout, _orig=fake):
        if "/fapi/v1/order" in url and method == "GET":
            return HttpResponse(500, {}, b"")
        return _orig(method, url, headers, timeout)

    broker.market._transport = unclear
    with pytest.raises(Unreconciled):
        broker.open(broker.plan("SOLUSDT", "BUY", Decimal("1"), "5m"))
    assert not fake.positions


def test_close_cancels_the_stop_and_target_first_then_reduces_only(tmp_path):
    broker, fake = _real(tmp_path)
    broker.open(broker.plan("SOLUSDT", "BUY", Decimal("1"), "5m"))
    pos = broker.positions()["SOLUSDT"]
    broker.close(pos)
    assert not fake.algos and fake.positions["SOLUSDT"] == 0


def test_orders_left_by_a_position_closed_on_the_exchange_are_cleared(tmp_path):
    broker, fake = _real(tmp_path)
    broker.open(broker.plan("SOLUSDT", "BUY", Decimal("1"), "5m"))
    fake.positions["SOLUSDT"] = Decimal("0")  # the stop executed on Binance
    assert broker.positions() == {} and not fake.algos


# --- SHADOW ------------------------------------------------------------------------------------------

def test_shadow_simulates_a_short_stopped_out_with_fees(tmp_path):
    fake = FakeFapi()
    broker = F.PaperFuturesBroker(F.FuturesMarket(None, transport=fake), Decimal("37"), tmp_path / "paper.json")
    plan = broker.plan("SOLUSDT", "SELL", Decimal("1"), "5m")
    broker.open(plan)
    assert set(broker.positions()) == {"SOLUSDT"}
    fake.last_bar = (float(plan.price), float(plan.sl) + 1)  # the price ran up through the stop
    assert broker.positions() == {}
    closed = broker.book["closed"][0]
    assert closed["why"] == "stop" and Decimal(closed["pnl"]) < 0
    loss = Decimal("37") - Decimal(broker.book["cash"])
    fees = (plan.price + plan.sl) * plan.qty * F.TAKER_FEE
    assert loss == (plan.sl - plan.price) * plan.qty + fees  # the stop's distance plus both taker fees


def test_shadow_runs_on_the_shared_engine_from_the_command_line(tmp_path, capsys):
    assert F.main(["--dir", str(tmp_path), "--una-vez", "--simbolos", "SOLUSDT"], transport=FakeFapi()) == 0
    assert "SHADOW" in capsys.readouterr().out and (tmp_path / "shadow" / "state.json").exists()


def test_real_from_the_command_line_refuses_unapproved_limits(tmp_path, capsys):
    data = json.loads(F.DEFAULT_LIMITS.read_text(encoding="utf-8"))
    (tmp_path / "limits.json").write_text(json.dumps({**data, "approved_by_owner": False}), encoding="utf-8")
    assert F.main(["--modo", "real", "--dir", str(tmp_path), "--una-vez", "--limites", str(tmp_path / "limits.json")],
                  transport=FakeFapi(), env=ENV) == 1
    assert "no están aprobados" in capsys.readouterr().out


def test_the_engine_turns_around_on_binance_as_on_xm(tmp_path):
    broker, fake = _real(tmp_path)
    sig = {"SOLUSDT": "BUY"}
    auto = TwoWayAuto(broker, ["SOLUSDT"], tmp_path / "state.json", signal=lambda s, d, h=None: sig.get(s),
                      risk_pct=Decimal("1"), notify=lambda m: None)
    auto.step()
    assert fake.positions["SOLUSDT"] > 0
    sig["SOLUSDT"] = "SELL"
    auto.step()
    assert fake.positions["SOLUSDT"] == 0 and not fake.algos
    auto.step()
    assert fake.positions["SOLUSDT"] < 0



def test_the_stop_that_follows_the_gain_goes_in_before_the_old_one_is_cancelled(tmp_path):
    broker, fake = _real(tmp_path)
    plan = broker.plan("SOLUSDT", "BUY", Decimal("1"), "5m")
    broker.open(plan)
    old = [k for k, a in fake.algos.items() if a["type"] == "STOP_MARKET"]
    broker.move_stop(broker.positions()["SOLUSDT"], plan.price - Decimal("1"), plan.tp)
    stops = [a for a in fake.algos.values() if a["type"] == "STOP_MARKET"]
    assert len(stops) == 1 and old[0] not in fake.algos and Decimal(stops[0]["triggerPrice"]) == plan.price - 1
    placed = [i for i, (m, p, q) in enumerate(fake.calls) if p == "/fapi/v1/algoOrder" and m == "POST"][-1]
    cancelled = [i for i, (m, p, q) in enumerate(fake.calls) if p == "/fapi/v1/algoOrder" and m == "DELETE"][-1]
    assert placed < cancelled  # never a moment without a stop


def test_shadow_moves_its_simulated_stop(tmp_path):
    fake = FakeFapi()
    broker = F.PaperFuturesBroker(F.FuturesMarket(None, transport=fake), Decimal("37"), tmp_path / "paper.json")
    plan = broker.plan("SOLUSDT", "BUY", Decimal("1"), "5m")
    broker.open(plan)
    broker.move_stop(broker.positions()["SOLUSDT"], plan.price, plan.tp)
    assert Decimal(broker.book["positions"]["SOLUSDT"]["sl"]) == plan.price


def test_continue_from_the_command_line_reaches_the_running_engine(tmp_path, capsys):
    assert F.main(["continuar", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "shadow" / "CONTINUAR").exists()


def test_without_a_futures_only_key_the_owners_spot_key_is_used():
    """Owner, 2026-10-10: "usa la misma clave de ser necesario es la misma cuenta"."""
    creds = F.FuturesCredentials.from_env({F.SPOT_KEY_VAR: "a" * 64, F.SPOT_SECRET_VAR: "b" * 64})
    assert creds.header() == {"X-MBX-APIKEY": "a" * 64}
    with pytest.raises(F.FuturesError, match="no hay clave"):
        F.FuturesCredentials.from_env({})


def test_real_runs_one_decision_with_the_approved_limits_and_the_same_key(tmp_path, capsys):
    env = {F.SPOT_KEY_VAR: "a" * 64, F.SPOT_SECRET_VAR: "b" * 64}
    fake = FakeFapi()
    assert F.main(["--modo", "real", "--dir", str(tmp_path), "--una-vez", "--simbolos", "SOLUSDT"],
                  transport=fake, env=env) == 0
    out = capsys.readouterr().out
    assert "Binance Futuros" in out and "40" in out and "45" in out
    assert any(p == "/sapi/v1/account/apiRestrictions" for _, p, _ in fake.calls)  # the key was checked first
