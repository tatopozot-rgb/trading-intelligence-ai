"""Independent acceptance checks; use only an isolated, pinned source checkout.

Usage: python test_watchdog_review.py <directory-containing-paper_store-and-config>
No account/session/network is opened. All data lives in a temporary SQLite DB.
Failures are evidence for Claude Code Local, not permission to relax any gate.
"""
import importlib
import socket
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


class WatchdogAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="watchdog-review-")
        self.addCleanup(self.tmp.cleanup)
        self.now = T0
        self.root = Path(self.tmp.name)
        settings = dict(BASE_DATOS=self.root / "isolated.sqlite", DIRECTORIO=self.root,
                        MODO="PAPER", USAR_DINERO_REAL=False, CAPITAL_USD=100.0,
                        DRAWDOWN_HALT_PCT=15.0, DRAWDOWN_PAUSE_PCT=8.0)
        patches = [patch.multiple(config, **settings),
                   patch.object(store, "ahora", side_effect=lambda: self.now),
                   patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")),
                   patch.object(store, "_precio_para_equity", return_value=100.0)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        store.inicializar()
        # Fixture only: not an order or a call to the execution runner.
        with store.conectar() as con:
            con.execute("""INSERT INTO paper_trades
                (simbolo,fecha_apertura,estado,entrada,stop_precio,objetivo_precio,
                 tamano_posicion,riesgo_usd,comision_pct_apertura)
                VALUES ('BTCUSDT',?,'ABIERTA',100,98,104,40,0.88,0.1)""", (T0.isoformat(),))

    def halt(self):
        with store.conectar() as con:
            return dict(con.execute("SELECT * FROM paper_halt WHERE id=1").fetchone())

    def good(self):
        return store.evaluar_riesgo(precio_fn=lambda symbol: 100.0)

    @staticmethod
    def unavailable(symbol):
        raise OSError("injected feed outage")

    def test_fresh_initialization_provides_finite_grace_anchor(self):
        self.assertIsNotNone(self.halt()["ultimo_ok"], "Fresh/migrated NULL currently means infinite outage")

    def test_first_transient_failure_after_migration_does_not_persist_halt(self):
        with store.conectar() as con:
            con.execute("UPDATE paper_halt SET ultimo_ok=NULL")
        store.inicializar()
        with self.assertRaisesRegex(ValueError, "Precio no disponible"):
            store.evaluar_riesgo(precio_fn=self.unavailable)
        self.assertEqual(self.halt()["activo"], 0)

    def test_valid_heartbeat_is_not_extended_by_reinitialization(self):
        self.good()
        self.now += timedelta(seconds=59)
        store.inicializar()
        self.assertEqual(self.halt()["ultimo_ok"], T0.isoformat())

    def test_transient_failure_within_window_blocks_without_persisting_halt(self):
        self.good()
        self.now += timedelta(seconds=59)
        with self.assertRaisesRegex(ValueError, "Precio no disponible"):
            store.evaluar_riesgo(precio_fn=self.unavailable)
        self.assertEqual(self.halt()["activo"], 0)

    def test_long_outage_persists_halt_and_survives_restart(self):
        self.good()
        self.now += timedelta(seconds=61)
        result = store.evaluar_riesgo(precio_fn=self.unavailable)
        self.assertTrue(result["bloqueado"])
        self.assertTrue(result["nuevo"])
        store.inicializar()
        self.assertEqual(self.halt()["activo"], 1)
        self.assertFalse(self.good()["nuevo"])
        self.assertEqual(self.halt()["activo"], 1)

    def test_successful_manual_release_refreshes_valuation_evidence(self):
        self.good()
        self.now += timedelta(seconds=61)
        store.evaluar_riesgo(precio_fn=self.unavailable)
        self.now += timedelta(seconds=1)
        store.liberar_halt(confirmado=True, precio_fn=lambda symbol: 100.0)
        self.assertEqual(self.halt()["ultimo_ok"], self.now.isoformat())

    def test_rejected_duplicate_does_not_discard_successful_feed_observation(self):
        self.good()
        self.now += timedelta(seconds=59)
        plan = dict(modo="PAPER", decision="PAPER CANDIDATE", simbolo="BTCUSDT",
                    entrada=100, stop_precio=98, objetivo_precio=104,
                    tamano_posicion=40, comision_paper_pct=0.1)
        with self.assertRaisesRegex(ValueError, "Ya existe"):
            with store.conectar() as con:
                con.execute("BEGIN IMMEDIATE")
                store._abrir_validado(con, {"id": "fixture"}, plan, {}, 100,
                                      False, None, "fixture", "CLAUDE")
        # It really valued the existing position at T0+59, despite rejecting a duplicate.
        self.now += timedelta(seconds=2)
        with self.assertRaisesRegex(ValueError, "Precio no disponible"):
            store.evaluar_riesgo(precio_fn=self.unavailable)
        self.assertEqual(self.halt()["activo"], 0)

    def test_release_without_valid_price_does_not_clear_halt(self):
        self.good()
        self.now += timedelta(seconds=61)
        store.evaluar_riesgo(precio_fn=self.unavailable)
        with self.assertRaisesRegex(ValueError, "Precio no disponible"):
            store.liberar_halt(confirmado=True, precio_fn=self.unavailable)
        self.assertEqual(self.halt()["activo"], 1)


if __name__ == "__main__":
    print("REVIEW SOURCE:", SOURCE)
    unittest.main(verbosity=2)
