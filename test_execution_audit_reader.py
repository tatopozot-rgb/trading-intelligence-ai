"""Pruebas del núcleo compartido de lectura; aún no del futuro CLI E4b."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from execution_audit import AuditoriaOffline, informe_auditoria_en


class AuditReaderCoreTests(unittest.TestCase):
    def setUp(self):
        from test_execution_bundle import BundleTests
        fixture = BundleTests()
        fixture.setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = Path(self.tmp.name) / 'con espacios # prueba.offline.sqlite3'
        self.db = AuditoriaOffline(self.ruta)
        self.db.crear_intencion(fixture.intencion)
        self.db.evaluar_y_registrar('i1', 'e1', dict(
            plan=fixture.plan, snapshot=fixture.snapshot, evidencias=fixture.evidencias),
            ahora_ms=1200, limites_politica=fixture.limites)

    def conectar_ro(self):
        con = sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True)
        self.addCleanup(con.close)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        return con

    def test_nucleo_reutilizado_sin_constructor_ni_escrituras(self):
        esperado = self.db.informe_auditoria('i1')
        originales = {p.name: p.read_bytes() for p in self.ruta.parent.iterdir()}
        con = self.conectar_ro()
        con.execute('BEGIN')
        sentencias = []
        con.set_trace_callback(sentencias.append)
        permitidos = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        con.set_authorizer(lambda accion, *_: sqlite3.SQLITE_OK
                           if accion in permitidos else sqlite3.SQLITE_DENY)
        with patch.object(AuditoriaOffline, '__init__', side_effect=AssertionError('constructor')):
            obtenido = informe_auditoria_en(con, 'i1')
        self.assertEqual(obtenido, esperado)
        self.assertFalse(obtenido['autorizado'])
        self.assertFalse(obtenido['enviable'])
        self.assertTrue(obtenido['historico'])
        self.assertTrue(con.in_transaction)
        self.assertEqual(con.total_changes, 0)
        self.assertTrue(sentencias)
        self.assertTrue(all(s.lstrip().upper().startswith('SELECT ') for s in sentencias))
        con.set_authorizer(None)
        con.close()
        self.assertEqual(originales, {p.name: p.read_bytes() for p in self.ruta.parent.iterdir()})

    def test_exige_transaccion_del_llamador(self):
        con = self.conectar_ro()
        with self.assertRaisesRegex(ValueError, 'transacción'):
            informe_auditoria_en(con, 'i1')
        self.assertFalse(con.in_transaction)

    def test_ausente_no_crea_intencion_y_conserva_transaccion(self):
        con = self.conectar_ro()
        con.execute('BEGIN')
        with self.assertRaisesRegex(ValueError, 'inexistente'):
            informe_auditoria_en(con, 'ausente')
        self.assertTrue(con.in_transaction)
        self.assertEqual(con.execute('SELECT count(*) FROM intenciones').fetchone()[0], 1)

    def test_dos_lecturas_comparten_snapshot_del_llamador(self):
        con = self.conectar_ro()
        con.execute('BEGIN')
        primero = informe_auditoria_en(con, 'i1')
        segundo = informe_auditoria_en(con, 'i1')
        self.assertEqual(primero, segundo)
        self.assertTrue(con.in_transaction)


if __name__ == '__main__':
    unittest.main()
