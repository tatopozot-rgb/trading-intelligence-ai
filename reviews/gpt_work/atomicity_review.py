"""Transaction-boundary review against the unmodified Finding-3 snapshot.

Usage: python -B atomicity_review.py <snapshot-directory>
Expected source paper_store.py Git blob: 7ea113b777f46a589078e3992ef07a66823bb5de.
No runtime edits: proposed_open is an in-memory orchestration experiment,
not a production patch or a claim that the reviewed branch is fixed.
Temporary SQLite only; public-price lookup and socket access are blocked.
"""
from __future__ import annotations

import importlib
import socket
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(SOURCE))
config = importlib.import_module("config")
store = importlib.import_module("paper_store")
T0 = datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)


class AtomicityReview(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="watchdog-atomicity-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = T0
        self.price = 100.0
        for item in (
            patch.multiple(config, BASE_DATOS=self.root / "isolated.sqlite",
                           DIRECTORIO=self.root, MODO="PAPER", USAR_DINERO_REAL=False,
                           CAPITAL_USD=100.0, DRAWDOWN_HALT_PCT=15.0,
                           DRAWDOWN_PAUSE_PCT=8.0),
            patch.object(store, "ahora", side_effect=lambda: self.now),
            patch.object(store, "_precio_para_equity", side_effect=lambda _: self.price),
            patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")),
            patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")),
            patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Network forbidden")),
        ):
            item.start()
            self.addCleanup(item.stop)
        store.inicializar()
        with store.conectar() as con:
            con.execute("""INSERT INTO paper_trades
                (simbolo,fecha_apertura,estado,entrada,stop_precio,objetivo_precio,
                 tamano_posicion,riesgo_usd,comision_pct_apertura)
                VALUES ('BTCUSDT',?,'ABIERTA',100,98,104,40,0.88,0.1)""", (T0.isoformat(),))
        store.evaluar_riesgo()
        self.plan = dict(modo="PAPER", decision="PAPER CANDIDATE", simbolo="ETHUSDT",
                         entrada=100, stop_precio=98, objetivo_precio=104,
                         tamano_posicion=40, comision_paper_pct=0.1)
        self.request_id, _ = store.registrar_solicitud(self.plan, True)
        self.request = store.leer_solicitud(self.request_id)
        self.before = self.snapshot()
        self.now += timedelta(seconds=59)

    def snapshot(self) -> dict:
        with store.conectar() as con:
            return {
                "halt": dict(con.execute("SELECT * FROM paper_halt WHERE id=1").fetchone()),
                "hist": [tuple(row) for row in con.execute("SELECT * FROM paper_equity_hist ORDER BY id")],
                "trades": [tuple(row) for row in con.execute("SELECT * FROM paper_trades ORDER BY id")],
                "requests": [tuple(row) for row in con.execute("SELECT * FROM paper_requests ORDER BY id")],
                "days": [tuple(row) for row in con.execute("SELECT * FROM paper_days ORDER BY dia")],
                "events": [tuple(row) for row in con.execute("SELECT * FROM paper_events ORDER BY id")],
                "account": tuple(con.execute("SELECT * FROM paper_account WHERE id=1").fetchone()),
            }

    def assert_no_order_effects(self, current: dict) -> None:
        for key in ("trades", "requests", "days", "events", "account"):
            self.assertEqual(current[key], self.before[key], key)

    def proposed_open(self, *, escape_inside: bool = False) -> dict:
        """Model explicit health/order boundary using actual unmodified helpers.

        The second _evaluar_halt call inside _abrir_validado is replaced only
        in memory with its already-computed result. Production should split
        the post-health order block, not monkeypatch or evaluate twice.
        """
        deferred: BaseException | None = None
        result: dict = {}
        with store.conectar() as con:
            con.execute("BEGIN IMMEDIATE")
            gate = store._evaluar_halt(con)
            blocked, new, reason = gate
            if blocked:
                result = {"registrada": False, "motivo": reason}
                if not new:
                    deferred = ValueError(reason)
            else:
                # Starts BEFORE daily-base writes, all trade/request/event
                # mutations, and the final session/mode/fill checks.
                con.execute("SAVEPOINT rejected_order")
                try:
                    with patch.object(store, "_evaluar_halt", return_value=gate):
                        result = store._abrir_validado(
                            con, self.request, self.plan, {}, 100.0,
                            False, None, "fixture", "CLAUDE")
                except (ValueError, store.SesionFinalizada) as error:
                    con.execute("ROLLBACK TO rejected_order")
                    con.execute("RELEASE rejected_order")
                    if escape_inside:
                        raise
                    deferred = error
                else:
                    con.execute("RELEASE rejected_order")
        # The outer with con has now committed. A commit exception must win
        # over a deferred domain rejection; never claim successful persistence.
        if deferred is not None:
            raise deferred
        return result

    def test_savepoint_reraise_inside_outer_context_loses_health(self) -> None:
        with patch.object(store, "validar_paper", side_effect=ValueError("late domain rejection")):
            with self.assertRaisesRegex(ValueError, "late domain"):
                self.proposed_open(escape_inside=True)
        after = self.snapshot()
        self.assert_no_order_effects(after)
        self.assertEqual(after["halt"], self.before["halt"])
        self.assertEqual(after["hist"], self.before["hist"])

    def test_deferred_late_rejection_keeps_health_without_partial_order(self) -> None:
        original_event = store.evento
        reached = []

        def observe_event(con, kind, data):
            original_event(con, kind, data)
            if kind == "APERTURA":
                reached.append(True)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0], 2)
                self.assertEqual(con.execute("SELECT estado FROM paper_requests WHERE id=?",
                                             (self.request_id,)).fetchone()[0], "EJECUTADA")

        with patch.object(store, "evento", side_effect=observe_event), \
                patch.object(store, "validar_paper", side_effect=ValueError("late domain rejection")):
            with self.assertRaisesRegex(ValueError, "late domain"):
                self.proposed_open()
        self.assertEqual(reached, [True], "Must exercise rejection after actual order writes")
        after = self.snapshot()
        self.assert_no_order_effects(after)
        self.assertEqual(after["halt"]["ultimo_ok"], self.now.isoformat())
        self.assertEqual(len(after["hist"]), len(self.before["hist"]) + 1)

    def test_success_commits_health_and_complete_order(self) -> None:
        result = self.proposed_open()
        after = self.snapshot()
        self.assertTrue(result["registrada"])
        self.assertEqual(len(after["trades"]), 2)
        request = store.leer_solicitud(self.request_id)
        self.assertEqual(request["estado"], "EJECUTADA")
        self.assertEqual(request["trade_id"], result["id"])
        self.assertEqual(after["halt"]["ultimo_ok"], self.now.isoformat())
        self.assertEqual(sum(row[2] == "APERTURA" for row in after["events"]), 1)

    def test_deferred_pause_preserves_valuation_without_opening(self) -> None:
        self.price = 77.0  # Synthetic mark generates pause, strictly below halt.
        with self.assertRaisesRegex(ValueError, "PAUSA_DRAWDOWN"):
            self.proposed_open()
        after = self.snapshot()
        self.assert_no_order_effects(after)
        self.assertEqual(after["halt"]["activo"], 0)
        self.assertEqual(after["halt"]["ultimo_ok"], self.now.isoformat())
        self.assertEqual(len(after["hist"]), len(self.before["hist"]) + 1)

    def test_unmodified_pause_path_also_rolls_back_valuation(self) -> None:
        self.price = 77.0
        with self.assertRaisesRegex(ValueError, "PAUSA_DRAWDOWN"):
            with store.conectar() as con:
                con.execute("BEGIN IMMEDIATE")
                store._abrir_validado(con, self.request, self.plan, {}, 100.0,
                                      False, None, "fixture", "CLAUDE")
        after = self.snapshot()
        self.assert_no_order_effects(after)
        self.assertEqual(after["halt"], self.before["halt"])
        self.assertEqual(after["hist"], self.before["hist"])

    def test_unexpected_storage_failure_does_not_partially_commit(self) -> None:
        original_event = store.evento

        def failing_event(con, kind, data):
            original_event(con, kind, data)
            if kind == "APERTURA":
                raise sqlite3.OperationalError("injected storage failure")

        with patch.object(store, "evento", side_effect=failing_event):
            with self.assertRaisesRegex(sqlite3.OperationalError, "storage failure"):
                self.proposed_open()
        self.assertEqual(self.snapshot(), self.before)

    def test_commit_failure_is_not_reported_as_ordinary_rejection(self) -> None:
        original_connect = sqlite3.connect

        class FailingCommit(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                if exc_type is None:
                    error = sqlite3.OperationalError("injected commit failure")
                    super().__exit__(type(error), error, None)
                    raise error
                return super().__exit__(exc_type, exc_value, traceback)

        def connect(*args, **kwargs):
            return original_connect(*args, **kwargs, factory=FailingCommit)

        with patch.object(store.sqlite3, "connect", side_effect=connect), \
                patch.object(store, "validar_paper", side_effect=ValueError("late domain rejection")):
            with self.assertRaisesRegex(sqlite3.OperationalError, "commit failure"):
                self.proposed_open()
        self.assertEqual(self.snapshot(), self.before)


if __name__ == "__main__":
    print("ATOMICITY REVIEW SOURCE:", SOURCE, flush=True)
    unittest.main(verbosity=2)
