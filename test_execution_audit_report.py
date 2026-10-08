import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import execution_audit_report as report


@unittest.skipUnless(os.name == 'nt', 'Lector Windows: otras plataformas rechazan')
class AuditReportTests(unittest.TestCase):
    def setUp(self):
        from test_execution_audit_reader import AuditReaderCoreTests
        AuditReaderCoreTests.setUp(self)

    def archivos(self):
        return {p.name: p.read_bytes() for p in self.ruta.parent.iterdir() if p.is_file()}

    def leer(self, ruta=None, id_local='i1'):
        antes = self.archivos()
        resultado = report.leer_auditoria(self.ruta if ruta is None else ruta, id_local)
        self.assertEqual(antes, self.archivos())
        for campo in ('autorizado', 'enviable'):
            self.assertFalse(resultado[campo])
        self.assertTrue(resultado['historico']); self.assertTrue(resultado['solo_lectura'])
        return resultado

    def test_integro_sin_constructor(self):
        with patch('execution_audit.AuditoriaOffline.__init__', side_effect=AssertionError('constructor')):
            self.assertEqual(self.leer()['estado'], 'REGISTRO_INTEGRO')

    def test_ruta_ausente_directorio_sufijo_y_uri_no_crean(self):
        for ruta in (self.ruta.parent/'ausente.offline.sqlite3', self.ruta.parent,
                     self.ruta.parent/'trading.db', ':memory:', 'file:otra?mode=rwc'):
            with self.subTest(ruta=str(ruta)):
                self.assertEqual(self.leer(ruta)['estado'], 'NO_VERIFICADO')

    def test_ajena_corrupta_y_vacia(self):
        for tipo in ('ajena', 'corrupta', 'vacia'):
            ruta = self.ruta.parent/(tipo+'.offline.sqlite3')
            if tipo == 'ajena':
                con = sqlite3.connect(ruta)
                con.execute('CREATE TABLE otro (valor TEXT)'); con.commit(); con.close()
            else:
                ruta.write_bytes(b'no sqlite' if tipo == 'corrupta' else b'')
            with self.subTest(tipo=tipo):
                self.assertEqual(self.leer(ruta)['estado'], 'NO_VERIFICADO')

    def test_esquema_incompleto_no_migra(self):
        with self.db.conectar() as con:
            con.execute('DROP TABLE evaluaciones')
        self.assertEqual(self.leer()['motivo'], 'TABLAS_INCOMPATIBLES')

    def test_columna_extra_no_se_ignora(self):
        with self.db.conectar() as con:
            con.execute('ALTER TABLE evaluaciones ADD COLUMN extra TEXT')
        self.assertEqual(self.leer()['motivo'], 'COLUMNAS_INCOMPATIBLES')

    def test_vista_no_es_tabla(self):
        with self.db.conectar() as con:
            con.execute('DROP TABLE evaluaciones')
            con.execute('CREATE VIEW evaluaciones AS SELECT * FROM conflictos_evaluacion')
        self.assertEqual(self.leer()['motivo'], 'OBJETOS_NO_SOPORTADOS')

    def test_version_desconocida(self):
        with self.db.conectar() as con:
            con.execute('PRAGMA user_version=99')
        self.assertEqual(self.leer()['motivo'], 'VERSION_NO_SOPORTADA')

    def test_discrepancia_y_json_corrupto(self):
        with self.db.conectar() as con:
            con.execute("UPDATE evaluaciones SET hash='alterado'")
        self.assertEqual(self.leer()['estado'], 'DISCREPANCIA')
        with self.db.conectar() as con:
            con.execute("UPDATE evaluaciones SET datos='['")
        self.assertEqual(self.leer()['estado'], 'NO_VERIFICADO')

    def test_intencion_ausente(self):
        self.assertEqual(self.leer(id_local='no existe')['estado'], 'NO_VERIFICADO')

    def test_otro_lector_solo_lectura_es_compatible(self):
        con = sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True)
        try:
            con.execute('BEGIN')
            con.execute('SELECT * FROM intenciones').fetchall()
            self.assertEqual(self.leer()['estado'], 'REGISTRO_INTEGRO')
        finally:
            con.close()

    def test_sidecar_surgido_al_conectar_aborta_antes_de_begin(self):
        original = sqlite3.connect
        sidecar = Path(str(self.ruta)+'-wal')
        sentencias = []
        def abrir(*args, **kwargs):
            con = original(*args, **kwargs)
            con.set_trace_callback(sentencias.append)
            sidecar.write_bytes(b'fixture concurrente')
            return con
        with patch.object(report.sqlite3, 'connect', side_effect=abrir):
            resultado = report.leer_auditoria(self.ruta, 'i1')
        self.assertEqual(resultado['motivo'], 'ARCHIVOS_AUXILIARES_PRESENTES')
        self.assertEqual(sidecar.read_bytes(), b'fixture concurrente')
        self.assertFalse(any(s.upper().startswith('BEGIN') for s in sentencias))

    def test_escritor_en_otro_proceso_es_rechazado(self):
        codigo = "import sys; f=open(sys.argv[1], 'r+b'); print('ABIERTO', flush=True); sys.stdin.readline(); f.close()"
        proceso = subprocess.Popen([sys.executable, '-B', '-c', codigo, str(self.ruta)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(proceso.stdout.readline().strip(), 'ABIERTO')
            self.assertEqual(self.leer()['motivo'], 'ARCHIVO_NO_DISPONIBLE_PARA_LECTURA_ESTABLE')
        finally:
            proceso.communicate('\n', timeout=10)
        self.assertEqual(proceso.returncode, 0)

    def test_wal_cerrado_no_crea_sidecars(self):
        con = sqlite3.connect(self.ruta)
        self.assertEqual(con.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        con.close()
        self.assertEqual(self.leer()['motivo'], 'WAL_O_FORMATO_NO_SOPORTADO')

    def test_wal_abierto_no_modifica_sidecars(self):
        con = sqlite3.connect(self.ruta)
        try:
            con.execute('PRAGMA journal_mode=WAL')
            con.execute("UPDATE intenciones SET conflicto=1"); con.commit()
            self.assertEqual(self.leer()['estado'], 'NO_VERIFICADO')
        finally:
            con.close()

    def test_sidecar_no_se_elimina(self):
        for sufijo in ('-journal', '-wal', '-shm'):
            ruta = Path(str(self.ruta)+sufijo)
            ruta.write_bytes(b'evidencia sintetica')
            self.assertEqual(self.leer()['motivo'], 'ARCHIVOS_AUXILIARES_PRESENTES')
            ruta.unlink()  # Sólo fixture desechable del TemporaryDirectory.

    def test_escritor_previo_rechazado_sin_reintento(self):
        con = sqlite3.connect(self.ruta)
        try:
            con.execute('BEGIN IMMEDIATE')
            self.assertEqual(self.leer()['motivo'], 'ARCHIVO_NO_DISPONIBLE_PARA_LECTURA_ESTABLE')
        finally:
            con.close()

    def test_handle_impide_escritura_y_reemplazo_y_se_libera(self):
        original = report.informe_auditoria_en
        def comprobar(con, id_local):
            with self.assertRaises(OSError):
                with self.ruta.open('r+b'):
                    pass
            with self.assertRaises(OSError):
                self.ruta.rename(self.ruta.with_suffix('.renombrado'))
            self.assertEqual(con.execute('SELECT 1').fetchone()[0], 1)
            with self.assertRaises(sqlite3.DatabaseError):
                con.execute('DELETE FROM intenciones')
            return original(con, id_local)
        with patch.object(report, 'informe_auditoria_en', side_effect=comprobar):
            self.assertEqual(self.leer()['estado'], 'REGISTRO_INTEGRO')
        with self.ruta.open('r+b'):
            pass

    def test_cli_json_y_codigos(self):
        for esperado in (0, 1, 2):
            if esperado == 1:
                with self.db.conectar() as con:
                    con.execute("UPDATE evaluaciones SET hash='alterado'")
            with patch('sys.stdout', new_callable=io.StringIO) as salida:
                codigo = report.main(['--base', str(self.ruta), '--id', 'ausente' if esperado == 2 else 'i1'])
                self.assertEqual(codigo, esperado)
                self.assertFalse(json.loads(salida.getvalue())['autorizado'])

    def test_cli_proceso_real_y_argumentos_obligatorios(self):
        script = Path(report.__file__)
        r = subprocess.run([sys.executable, '-B', str(script), '--base', str(self.ruta), '--id', 'i1'],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)['estado'], 'REGISTRO_INTEGRO')
        r = subprocess.run([sys.executable, '-B', str(script)], capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 2)


if __name__ == '__main__':
    unittest.main()
