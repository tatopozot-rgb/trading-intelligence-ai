"""XM DEMO "Claude decide": Claude proposes, the code's rules and XmDemoTrader decide; every answer is logged."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from tests.test_xm_demo import TradingMt5
from trading_intelligence.live import xm_claude as C
from trading_intelligence.live.xm_demo import XmDemoTrader
from trading_intelligence.live.xm_mt5 import XmError, XmReader

AT = datetime(2026, 10, 7, 9, 3, tzinfo=timezone.utc)  # a Wednesday


def _frame(n: int = 80, price: float = 2600.0) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp(AT).floor("h"), periods=n, freq="h")
    close = [price + (i % 7) - 3 for i in range(n)]
    return pd.DataFrame({"open": close, "high": [c + 2 for c in close], "low": [c - 2 for c in close],
                         "close": close}, index=idx)


class Scripted:
    """A decider that answers from a list and remembers what it was shown."""

    def __init__(self, *answers: C.Decision, cost: float = 0.05) -> None:
        self.answers, self.cost, self.briefs = list(answers), cost, []

    def decide(self, brief: str):
        self.briefs.append(brief)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer, C.Usage("claude-opus-5-5", self.cost, 1000, 500)


def buy(stop=2574.0, meta=2652.0) -> C.Decision:
    return C.Decision("COMPRAR", stop, meta, 70, "sobre la media de 20 y 50; stop bajo el último mínimo")


WAIT = C.Decision("ESPERAR", 0, 0, 30, "sin ventaja clara")


def _bot(tmp_path, decider, at=AT, symbols=("GOLD",), budget=Decimal("40"), **kw):
    m = TradingMt5(equity=10_000.0, now=at)
    trader = XmDemoTrader(tmp_path / "orders.json", m, reader=XmReader(m, clock=lambda: at))
    trader.connect()
    notes: list[str] = []
    bot = C.ClaudeBot(trader, tmp_path, decider, notes.append, symbols=symbols, nominal=Decimal("10000"),
                      budget=budget, clock=lambda: at, candles=lambda s, tf, n: _frame(), **kw)
    return bot, m, notes


def _log(tmp_path) -> list[dict]:
    return [json.loads(line) for line in (tmp_path / "decisiones.jsonl").read_text(encoding="utf-8").splitlines()]


def test_parse_decision_reads_the_json_and_refuses_junk():
    d = C.parse_decision('texto {"accion": "comprar", "stop": 1, "meta": 3, "confianza": 140, "razon": "x"} fin')
    assert d.accion == "COMPRAR" and d.confianza == 100
    for bad in ("sin json", '{"accion": "COMPRAR"}', '{"accion": "APOSTAR", "stop": 0, "meta": 0, "confianza": 1, "razon": ""}'):
        with pytest.raises(ValueError):
            C.parse_decision(bad)


def test_rules_stop_band_and_reward_at_least_one_and_a_half_the_risk():
    assert C.check_decision(buy(), 2600.35, False) == []
    assert C.check_decision(buy(stop=2610), 2600.35, False)  # stop above the price on a buy
    assert any("fuera de 0.2-5" in r for r in C.check_decision(buy(stop=2599.9, meta=2601.0), 2600.35, False))
    assert any("veces el stop" in r for r in C.check_decision(buy(meta=2610.0), 2600.35, False))  # 0.37R
    assert C.check_decision(buy(), 2600.35, True)  # with a position only MANTENER or CERRAR
    assert C.check_decision(C.Decision("CERRAR", 0, 0, 50, ""), 2600, False)
    sell = C.Decision("VENDER", 2626.0, 2548.0, 60, "")
    assert C.check_decision(sell, 2600.0, False) == []


def test_a_buy_goes_out_with_stop_target_and_one_percent_of_the_nominal(tmp_path):
    bot, m, notes = _bot(tmp_path, Scripted(buy()))
    msg = bot.step()
    (order,) = m.sent
    assert order["type"] == 0 and order["sl"] < order["price"] < order["tp"]
    assert order["sl"] == pytest.approx(2574.0, abs=0.05) and order["tp"] == pytest.approx(2652.0, abs=0.05)
    risk = order["volume"] * 100 * abs(order["price"] - order["sl"])
    assert 60.0 < risk <= 100.0  # 1% of 10,000 nominal, lots rounded down
    assert "COMPRO" in msg and "Razón de Claude" in notes[0]
    (row,) = _log(tmp_path)
    assert row["accion"] == "COMPRAR" and row["rechazos"] == [] and row["version_prompt"] == C.PROMPT_VERSION
    assert bot.state["gasto"]["2026-10"] == pytest.approx(0.05)


def test_asks_once_per_hour_per_symbol(tmp_path):
    decider = Scripted(WAIT, WAIT)
    bot, m, _ = _bot(tmp_path, decider)
    bot.step()
    bot.step()
    assert len(decider.briefs) == 1
    bot.clock = lambda: AT + timedelta(hours=1)
    bot.step()
    assert len(decider.briefs) == 2 and not m.sent


def test_a_refused_answer_is_logged_and_no_order_is_sent(tmp_path):
    bot, m, _ = _bot(tmp_path, Scripted(buy(meta=2610.0)))
    assert "rechazada" in bot.step()
    assert not m.sent and _log(tmp_path)[0]["rechazos"]


def test_with_a_position_claude_can_close_it_and_the_result_is_in_r(tmp_path):
    decider = Scripted(buy(), C.Decision("MANTENER", 0, 0, 60, "sigue la tendencia"),
                       C.Decision("CERRAR", 0, 0, 60, "perdió la media"))
    bot, m, _ = _bot(tmp_path, decider)
    bot.step()
    assert "Posición abierta" not in decider.briefs[0]
    bot.clock = lambda: AT + timedelta(hours=1)
    assert "mantener" in bot.step()
    assert "Posición abierta: BUY" in decider.briefs[1]
    bot.clock = lambda: AT + timedelta(hours=2)
    assert "cerré" in bot.step()
    assert len(m.sent) == 2 and not m.positions and not bot.state["open"]
    (close,) = [t for t in bot.state["trades"] if t["accion"] == "cierre"]
    assert close["motivo"] == "Claude cerró" and Decimal(close["r"]) < 0  # closed at the mid, below the ask paid


def test_a_server_close_is_recorded_at_the_nearer_of_stop_and_target(tmp_path):
    bot, m, _ = _bot(tmp_path, Scripted(buy(), WAIT))
    bot.step()
    m.positions.clear()  # the stop or the target closed it on XM's server; the price is near the entry, below
    bot.clock = lambda: AT + timedelta(hours=1)
    bot.step()
    (close,) = [t for t in bot.state["trades"] if t["accion"] == "cierre"]
    assert close["motivo"] == "stop" and close["r"] == "-1.00"


def test_two_entries_a_day_per_symbol_at_most(tmp_path):
    bot, m, _ = _bot(tmp_path, Scripted(buy(), buy(), buy()))
    for hour in range(3):
        bot.clock = lambda h=hour: AT + timedelta(hours=h)
        bot.step()
        m.positions.clear()  # stopped out each time
    assert len(m.sent) == 2


def test_the_monthly_cap_stops_the_calls_and_warns_once(tmp_path):
    decider = Scripted(WAIT, WAIT, cost=0.30)
    alarms: list[str] = []
    bot, _, _ = _bot(tmp_path, decider, budget=Decimal("0.50"), alarm=alarms.append)
    bot.step()  # 0.30 spent; 0.30 + 0.25 reserve > 0.50
    for hour in (1, 2):
        bot.clock = lambda h=hour: AT + timedelta(hours=h)
        assert "tope de gasto" in bot.step()
    assert len(decider.briefs) == 1 and len(alarms) == 1


def test_a_failed_call_is_logged_and_waits(tmp_path):
    bot, m, _ = _bot(tmp_path, Scripted(RuntimeError("sin red")))
    assert "no respondió" in bot.step()
    assert not m.sent and _log(tmp_path)[0]["error"] == "sin red"


def test_the_experiment_halts_itself_after_ten_r_lost(tmp_path):
    alarms: list[str] = []
    bot, m, _ = _bot(tmp_path, Scripted(buy()), alarm=alarms.append)
    bot.state["trades"] = [{"t": "2026-10-01T10:00:00", "accion": "cierre", "simbolo": "GOLD", "lado": "BUY",
                            "motivo": "stop", "r": "-1.00", "pnl": "-10"} for _ in range(10)]
    assert "detenido" in bot.step()
    assert not m.sent and alarms and bot.state["halted"]


def test_a_closed_market_costs_nothing(tmp_path):
    decider = Scripted(WAIT)
    m = TradingMt5(equity=10_000.0, now=AT, tick_age=10_000)
    trader = XmDemoTrader(tmp_path / "orders.json", m, reader=XmReader(m, clock=lambda: AT))
    trader.connect()
    bot = C.ClaudeBot(trader, tmp_path, decider, print, symbols=("GOLD",), clock=lambda: AT,
                      candles=lambda s, tf, n: _frame())
    assert "cerrado" in bot.step() and not decider.briefs


def test_the_brief_carries_the_three_timeframes_and_its_history():
    frames = {tf: _frame() for tf in ("1d", "4h", "1h")}
    brief = C.market_brief("GOLD", AT, 2600.0, 2600.35, 0.013, frames, None,
                           [{"lado": "BUY", "motivo": "meta", "r": "2.00"}])
    assert "Velas 1d" in brief and "Velas 4h" in brief and "Velas 1h" in brief and "rsi14" in brief
    assert "BUY meta 2.00R" in brief and "COMPRAR, VENDER o ESPERAR" in brief


def test_api_decider_counts_the_cost_and_waits_on_a_refusal():
    def make(stop_reason, text='{"accion": "ESPERAR", "stop": 0, "meta": 0, "confianza": 10, "razon": "nada"}'):
        usage = NS(input_tokens=3000, output_tokens=1000, cache_creation_input_tokens=0, cache_read_input_tokens=0)
        response = NS(model="claude-opus-5-5", usage=usage, stop_reason=stop_reason,
                      content=[NS(type="thinking", thinking=""), NS(type="text", text=text)])
        seen: dict = {}

        def create(**kw):
            seen.update(kw)
            return response
        return NS(beta=NS(messages=NS(create=create))), seen

    client, seen = make("end_turn")
    d, u = C.ApiDecider(client=client).decide("datos")
    assert d.accion == "ESPERAR" and u.cost_usd == pytest.approx(0.032)  # 3000x4 + 1000x20 per million
    assert seen["model"] == "claude-opus-5-5" and seen["output_config"]["format"]["schema"] == C.SCHEMA
    assert seen["fallbacks"] == "default" and C.FALLBACK_BETA in seen["betas"]
    client, _ = make("refusal", text="")
    d, _ = C.ApiDecider(client=client).decide("datos")
    assert d.accion == "ESPERAR"


def test_api_decider_needs_the_key_in_the_environment(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(XmError, match="ANTHROPIC_API_KEY"):
        C.ApiDecider()


def test_its_magic_differs_from_every_other_agent_on_the_demo_account():
    from trading_intelligence.live.xm_auto import agent_magic
    others = {agent_magic(a) for a in ("", "Cripto", "Índices", "Londres", "Londres BTCUSD")}
    assert agent_magic(C.AGENT) not in others
