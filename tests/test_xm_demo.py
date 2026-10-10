"""XM phase 2: DEMO-only orders, always with SL and TP, sized from risk, checked by MT5 first."""
from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from tests.test_xm_mt5 import NOW, FakeMt5
from trading_intelligence.live import xm_demo as D
from trading_intelligence.live.xm_mt5 import XmError, XmReader


class TradingMt5(FakeMt5):
    def __init__(self, check_ok=True, send_result="ok", **kw):
        super().__init__(**kw)
        self.check_ok, self.send_result = check_ok, send_result
        self.sent, self.positions = [], []

    def order_check(self, request):
        return NS(retcode=0 if self.check_ok else 10019, comment="ok" if self.check_ok else "No money")

    def order_send(self, request):
        self.sent.append(request)
        if self.send_result is None:
            return None
        ticket = 1000 + len(self.sent)
        if "position" in request:
            self.positions = [p for p in self.positions if p.ticket != request["position"]]
        else:
            self.positions.append(NS(ticket=ticket, symbol=request["symbol"], type=request["type"],
                                     volume=request["volume"], comment=request["comment"]))
        return NS(retcode=10009, order=ticket, deal=ticket, volume=request["volume"], price=request["price"],
                  comment="done")

    def positions_get(self, symbol=None):
        return tuple(p for p in self.positions if symbol is None or p.symbol == symbol)


def _trader(tmp_path, **kw):
    m = TradingMt5(**kw)
    t = D.XmDemoTrader(tmp_path / "orders.json", m, reader=XmReader(m, clock=lambda: NOW))
    t.connect()
    return t, m


def test_a_real_account_refuses_every_order(tmp_path):
    m = TradingMt5(mode=2)
    t = D.XmDemoTrader(tmp_path / "o.json", m, reader=XmReader(m, clock=lambda: NOW))
    with pytest.raises(D.NotDemo):
        t.connect()
    assert not m.sent


def test_size_comes_from_risk_and_never_rounds_up(tmp_path):
    t, m = _trader(tmp_path, equity=1000.0)
    with pytest.raises(XmError, match="ni el lote mínimo"):  # 0.5% risk = 5 USD < 0.01 lot at a 0.5% stop
        t.plan("EURUSD", "BUY", Decimal("0.5"), Decimal("1.0"), Decimal("0.5"))
    p = t.plan("EURUSD", "BUY", Decimal("0.5"), Decimal("1.0"), Decimal("1"))
    assert p.lots == Decimal("0.01") and p.sl < p.price < p.tp and p.risk_money == Decimal("5.43")
    s = t.plan("EURUSD", "SELL", Decimal("0.5"), Decimal("1.0"), Decimal("1"))
    assert s.tp < s.price < s.sl


def test_the_pre_entry_check_runs_first(tmp_path):
    t, m = _trader(tmp_path, equity=100.0)
    with pytest.raises(XmError, match="entrada no autorizada"):
        t.plan("GOLD", "BUY", Decimal("0.5"), Decimal("1"), Decimal("1"))


def test_an_order_carries_sl_tp_and_is_journaled_before_sending(tmp_path):
    t, m = _trader(tmp_path, equity=1000.0)
    plan = t.plan("EURUSD", "BUY", Decimal("0.5"), Decimal("1.0"), Decimal("1"))
    out = t.open(plan)
    req = m.sent[0]
    assert req["sl"] < req["price"] < req["tp"] and req["magic"] == D.MAGIC and req["comment"].startswith("TI-")
    rows = json.loads((tmp_path / "orders.json").read_text())
    assert [r["state"] for r in rows] == ["SENDING", "DONE"] and out["order"] == 1001
    t.close("EURUSD", 1001)
    assert m.sent[-1]["position"] == 1001 and m.sent[-1]["type"] == 1 and not m.positions


def test_mt5_validation_failure_sends_nothing(tmp_path):
    t, m = _trader(tmp_path, equity=1000.0, check_ok=False)
    with pytest.raises(XmError, match="No money"):
        t.open(t.plan("EURUSD", "BUY", Decimal("0.5"), Decimal("1.0"), Decimal("1")))
    assert not m.sent


def test_an_unclear_answer_is_reconciled_never_resent(tmp_path):
    t, m = _trader(tmp_path, equity=1000.0, send_result=None)
    with pytest.raises(XmError, match="no reenvío"):
        t.open(t.plan("EURUSD", "BUY", Decimal("0.5"), Decimal("1.0"), Decimal("1")))
    assert len(m.sent) == 1
    assert json.loads((tmp_path / "orders.json").read_text())[-1]["state"] == "UNCLEAR"


def test_the_demo_round_trip_command(tmp_path, capsys, monkeypatch):
    from datetime import datetime, timezone

    m = TradingMt5(equity=1000.0, now=datetime.now(timezone.utc))
    assert D.main(["--simbolo", "EURUSD", "--sl", "0.5", "--tp", "1.0", "--riesgo", "1",
                   "--diario", str(tmp_path / "o.json")], mt5=m) == 0
    out = capsys.readouterr().out
    assert "Cuenta DEMO" in out and "Abierta" in out and "Cerrada" in out and not m.positions



def test_without_sl_tp_the_plan_is_read_from_the_market(tmp_path):
    """Owner: stop and take profit "siempre con lógica del mercado", on XM as on Binance."""
    t, m = _trader(tmp_path, equity=1_000_000.0)
    p = t.plan("EURUSD", "BUY")
    stop_pct = (1 - p.sl / p.price) * 100
    assert Decimal("3") <= stop_pct <= Decimal("15.01") and p.tp > p.price
