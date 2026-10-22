"""The nightly risk review only warns: Haiku first, Sonnet only on an alarm, Telegram only for what Sonnet confirms;
without a key, or with the API failing, nothing changes. No network here: the client is a test double."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tests.test_resumen_diario import NOW, _runs, _write
from trading_intelligence.live import revision_riesgo as V

OK = {"alarma": False, "hallazgos": [], "resumen": "Todo normal."}
ALARM = {"alarma": True, "hallazgos": ["Futuros práctica 1x: la posición en AVAX no tiene stop."],
         "resumen": "Una posición sin stop."}


class FakeMessages:
    def __init__(self, owner, beta):
        self.owner, self.beta = owner, beta

    def create(self, **kw):
        self.owner.calls.append({**kw, "beta": self.beta})
        answer = self.owner.answers[kw["model"]]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, SimpleNamespace):
            return answer
        return SimpleNamespace(stop_reason="end_turn", content=[
            SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=json.dumps(answer))])


class FakeClient:
    def __init__(self, **answers):
        self.answers = {V.FIRST: answers.get("haiku", OK), V.SECOND: answers.get("sonnet", OK)}
        self.calls: list[dict] = []
        self.messages = FakeMessages(self, False)
        self.beta = SimpleNamespace(messages=FakeMessages(self, True))

    def models(self):
        return [c["model"] for c in self.calls]


def _clean(tmp_path, now=NOW):
    """A PC where every bot is fine: one practice engine with a stopped position, written a minute ago."""
    runs = tmp_path / "live_runs"
    _write(runs / "futures_auto" / "shadow" / "state.json", {
        "name": "🧪 Binance Futuros · PRÁCTICA", "capital": "37", "equity": "38", "currency": "USDT",
        "status": "RUNNING", "known": {"SOLUSDT": {"side": "BUY", "entry": "100", "stop": "97", "target": "106"}},
        "events": []}, now=now)
    return runs


def test_without_a_key_there_is_no_call_and_nothing_is_written(tmp_path, caplog):
    runs = _clean(tmp_path)
    assert V.make_client({}) is None and V.make_client({V.KEY_VAR: "  "}) is None
    sent: list[str] = []
    with caplog.at_level(logging.INFO):
        assert V.run(runs, None, sent.append, NOW) is None
    assert not sent and not (runs / "revision_riesgo").exists()


def test_a_quiet_night_is_one_haiku_call_and_no_message(tmp_path):
    runs, client, sent = _clean(tmp_path), FakeClient(), []
    verdict = V.run(runs, client, lambda m: sent.append(m) or True, NOW)
    assert verdict["alarma"] is False and client.models() == [V.FIRST] and not sent
    call = client.calls[0]
    assert call["output_config"]["format"]["schema"] == V.VERDICT and "temperature" not in call
    assert "SOL BUY entrada 100 stop 97 meta 106" in call["messages"][0]["content"]
    assert json.loads((runs / "revision_riesgo" / "ultima.json").read_text())["enviado"] is False


def test_a_haiku_alarm_goes_to_sonnet_and_only_sonnet_confirmed_reaches_telegram(tmp_path):
    runs, sent = _clean(tmp_path), []
    client = FakeClient(haiku=ALARM, sonnet=OK)  # Sonnet says it was nothing
    assert V.run(runs, client, lambda m: sent.append(m) or True, NOW)["alarma"] is False
    assert client.models() == [V.FIRST, V.SECOND] and not sent
    second = client.calls[1]
    assert second["beta"] and second["fallbacks"] == "default" and "primera revisión" in second["messages"][0]["content"]

    client = FakeClient(haiku=ALARM, sonnet=ALARM)
    verdict = V.run(runs, client, lambda m: sent.append(m) or True, NOW)
    assert verdict["modelo"] == V.SECOND and verdict["enviado"] is True
    (text,) = sent
    assert text.startswith("🔎") and "AVAX no tiene stop" in text and "Es solo un aviso" in text


def test_the_fixed_checks_find_a_position_without_stop_and_a_silent_bot(tmp_path):
    runs = _runs(tmp_path)  # the summary's fixture: positions there carry no stop, and the real bot is 2 h quiet
    text, found = V.digest(runs, NOW)
    assert any("AVAX no tiene stop" in f for f in found) and any("DINERO REAL" in f and "no escribe" in f for f in found)
    assert "stop NINGUNO" in text and "dinero real: SÍ" in text
    assert "31.69" not in text and "38.5" not in text  # percentages only, never the balances
    assert not any("Núcleo" in f and "stop" in f for f in found)  # the spot core bot has an exit rule, not a stop
    client = FakeClient(haiku=OK, sonnet=ALARM)
    V.run(runs, client, None, NOW)
    assert client.models() == [V.FIRST, V.SECOND]  # a fixed finding always gets the second look, whatever Haiku says


def test_too_many_positions_and_a_paused_engine_are_findings(tmp_path):
    runs = tmp_path / "live_runs"
    known = {s: {"side": "BUY", "stop": "1"} for s in ("SOLUSDT", "ADAUSDT", "AVAXUSDT", "XRPUSDT")}
    _write(runs / "xm_auto" / "state.json", {"name": "XM", "status": "WAITING_OWNER", "known": known, "events": []})
    _, found = V.digest(runs, NOW)
    assert any("4 posiciones" in f for f in found) and any("en pausa" in f for f in found)


def test_api_failures_never_raise_and_never_log_the_key(tmp_path, caplog):
    runs, sent = _clean(tmp_path), []
    secret = "clave-de-prueba-123"
    client = FakeClient(haiku=RuntimeError(f"401 bad key {secret}"))
    with caplog.at_level(logging.WARNING):
        assert V.run(runs, client, sent.append, NOW) is None
    assert client.models() == [V.FIRST]  # a failed first look on a clean night is not an alarm: no Sonnet
    assert not sent and secret not in caplog.text and "RuntimeError" in caplog.text
    client = FakeClient(haiku=SimpleNamespace(stop_reason="refusal", content=[]))
    assert V.run(runs, client, sent.append, NOW) is None and not sent
    client = FakeClient(haiku=SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="hola")]))
    assert V.run(runs, client, sent.append, NOW) is None and not sent


def test_when_sonnet_fails_the_haiku_alarm_still_goes_marked_unconfirmed(tmp_path):
    runs, sent = _clean(tmp_path), []
    client = FakeClient(haiku=ALARM, sonnet=ConnectionError("down"))
    verdict = V.run(runs, client, lambda m: sent.append(m) or True, NOW)
    assert verdict["sin_confirmar"] and "No se pudo confirmar" in sent[0]


def test_with_both_looks_down_the_fixed_findings_still_go(tmp_path):
    runs, sent = _runs(tmp_path), []
    client = FakeClient(haiku=ConnectionError("down"), sonnet=ConnectionError("down"))
    verdict = V.run(runs, client, lambda m: sent.append(m) or True, NOW)
    assert verdict["alarma"] and verdict["sin_confirmar"] and "AVAX no tiene stop" in sent[0]


def test_it_reads_only_and_never_touches_the_bots_state(tmp_path):
    runs = _runs(tmp_path)
    before = {p: p.read_bytes() for p in runs.rglob("*.json")}
    V.run(runs, FakeClient(haiku=ALARM, sonnet=ALARM), lambda m: True, NOW + timedelta(minutes=1))
    after = {p: p.read_bytes() for p in runs.rglob("*.json") if "revision_riesgo" not in p.parts}
    assert after == before


def test_ver_prints_the_digest_without_calling_claude(tmp_path, capsys, monkeypatch):
    runs = _clean(tmp_path, datetime.now(timezone.utc))
    monkeypatch.setattr(V, "make_client", lambda env=None: (_ for _ in ()).throw(AssertionError("no call")))
    assert V.main(["ver", "--runs", str(runs)]) == 0
    assert "Futuros" in capsys.readouterr().out
