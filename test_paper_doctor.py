from contextlib import closing, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import paper_doctor as doctor


def dependencia_ok(nombre):
    return {'estado':'OK', 'importable':True, 'version_instalada_metadata':'SINTETICA',
            'metodo':'SONDEO_SIMULADO_EN_TEST'}


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.root = Path(self.temporal.name)
        self.base = self.root/'fixture.db'
        (self.root/'config.py').write_text('MODO = "PAPER"\nUSAR_DINERO_REAL = False\n', encoding='utf-8')
        with closing(sqlite3.connect(self.base)) as con, con:
            con.executescript('''
                CREATE TABLE paper_account (id INTEGER, capital_inicial REAL, saldo_actual REAL, pnl_acumulado REAL);
                INSERT INTO paper_account VALUES (1,100,100,0);
                CREATE TABLE paper_trades (id INTEGER);
                CREATE TABLE paper_flows (id INTEGER, monto REAL);
                CREATE TABLE paper_requests (id INTEGER);
                CREATE TABLE paper_events (id INTEGER, tipo TEXT, datos TEXT);
            ''')
        self.runner = dict(modo='PAPER', estado='ACTIVO', fecha=self.fecha(1000),
            salud={n:dict(estado='OK', ciclos=1, errores_total=0) for n in ('scanner', 'monitor', 'bandeja')},
            pid=999999, sesion_id='NO_REPUBLICAR_IDENTIFICADOR')
        self.guardar_runner()
        self.sondeo = patch.object(doctor, 'sondear_dependencia', side_effect=dependencia_ok)
        self.sondeo.start()
        self.addCleanup(self.sondeo.stop)

    @staticmethod
    def fecha(epoch):
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat()

    def guardar_runner(self):
        (self.root/'runner_status.json').write_text(json.dumps(self.runner), encoding='utf-8')

    def ejecutar(self, **cambios):
        return doctor.diagnosticar(**{'directorio':self.root, 'base':self.base,
            'ahora_epoch':1100, 'max_edad_estado_seg':200, **cambios})

    def huellas(self):
        return {p.name:(hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in self.root.iterdir() if p.is_file()}

    def test_sano_solo_lectura_no_es_rentabilidad_ni_prueba_proceso(self):
        antes = self.huellas()
        dato = self.ejecutar()
        self.assertEqual(dato['estado'], 'OK_LOCAL')
        self.assertTrue(dato['solo_lectura'])
        self.assertTrue(dato['no_evalua_rentabilidad'])
        self.assertFalse(dato['autoriza_operar'])
        self.assertEqual(dato['conciliacion']['estado'], 'OK')
        self.assertEqual(dato['runner']['estado_registrado'], 'ACTIVO')
        self.assertEqual(dato['runner']['proceso_vivo'], 'NO_VERIFICADO')
        self.assertNotIn('NO_REPUBLICAR_IDENTIFICADOR', json.dumps(dato))
        self.assertEqual(self.huellas(), antes)
        self.assertEqual(dato['cooldown_http']['estado'], 'SIN_REGISTRO')
        self.assertFalse(dato['capacidades']['xm']['conexion_probada'])

    def test_bd_inexistente_no_se_crea_y_estado_ausente_no_se_infiere(self):
        faltante = self.root/'no_crear.db'
        (self.root/'runner_status.json').unlink()
        antes = self.huellas()
        dato = self.ejecutar(base=faltante)
        self.assertEqual(dato['estado'], 'NO_VERIFICADO')
        self.assertEqual(dato['conciliacion']['codigo'], 'BD_AUSENTE')
        self.assertEqual(dato['runner']['codigo'], 'ESTADO_AUSENTE')
        self.assertFalse(faltante.exists())
        self.assertEqual(self.huellas(), antes)

    def test_bd_discrepante_no_se_repara(self):
        with closing(sqlite3.connect(self.base)) as con, con:
            con.execute('UPDATE paper_account SET saldo_actual=999')
        antes = self.huellas()
        dato = self.ejecutar()
        self.assertEqual(dato['estado'], 'BLOQUEADO')
        self.assertIn('SALDO_NO_CONCILIA', {p['codigo'] for p in dato['conciliacion']['problemas']})
        self.assertEqual(self.huellas(), antes)

    def test_bd_invalida_reporta_error_sin_inicializar(self):
        self.base.write_bytes(b'no es SQLite')
        antes = self.huellas()
        dato = self.ejecutar()
        self.assertEqual(dato['conciliacion']['codigo'], 'CONCILIACION_NO_COMPLETADA')
        self.assertEqual(self.huellas(), antes)

    def test_bd_con_journal_no_se_abre_ni_borra_sidecar(self):
        for sufijo in ('-wal', '-shm', '-journal'):
            sidecar = self.base.with_name(self.base.name+sufijo)
            sidecar.write_bytes(b'fixture')
            antes = self.huellas()
            with self.subTest(sufijo=sufijo), patch('paper_report.informe') as informe:
                dato = self.ejecutar()
                informe.assert_not_called()
                self.assertEqual(dato['conciliacion']['codigo'], 'BD_CON_JOURNAL_NO_ABIERTA')
                self.assertEqual(self.huellas(), antes)
            sidecar.unlink()

    def test_config_no_paper_bloqueada_y_nunca_se_ejecuta(self):
        for texto in ('MODO="REAL"\nUSAR_DINERO_REAL=False\n', 'MODO="PAPER"\nUSAR_DINERO_REAL=True\n'):
            (self.root/'config.py').write_text(texto, encoding='utf-8')
            with self.subTest(texto=texto):
                self.assertIn('CONFIGURACION_NO_PAPER', self.ejecutar()['bloqueos'])
        (self.root/'config.py').write_text('MODO="PAPER"\nUSAR_DINERO_REAL=False\nraise RuntimeError("NO EJECUTAR")\n', encoding='utf-8')
        self.assertEqual(self.ejecutar()['configuracion']['estado'], 'OK')

    def test_config_dinamica_duplicada_y_ausente_no_verificadas(self):
        for texto in ('MODO=obtener_modo()\nUSAR_DINERO_REAL=False', 'MODO="PAPER"\nMODO="REAL"\nUSAR_DINERO_REAL=False',
                      'if True:\n MODO="PAPER"\nUSAR_DINERO_REAL=False', 'USAR_DINERO_REAL=False'):
            (self.root/'config.py').write_text(texto, encoding='utf-8')
            with self.subTest(texto=texto): self.assertEqual(self.ejecutar()['configuracion']['estado'], 'NO_VERIFICADO')
        (self.root/'config.py').unlink()
        self.assertEqual(self.ejecutar()['configuracion']['codigo'], 'CONFIG_AUSENTE')

    def test_dependencia_no_importable_bloquea_sin_reparar(self):
        with patch.object(doctor, 'sondear_dependencia', return_value={'estado':'ERROR', 'importable':False,
                'codigo':'POSIBLE_BLOQUEO_APPLICATION_CONTROL', 'version_instalada_metadata':'SINTETICA'}):
            antes = self.huellas()
            dato = self.ejecutar()
        self.assertIn('DEPENDENCIAS_NO_IMPORTABLES', dato['bloqueos'])
        self.assertEqual(self.huellas(), antes)

    def test_cooldown_activo_expirado_y_sin_plazo(self):
        for hasta, esperado in ((1200, 'BLOQUEADO'), (1100, 'EXPIRADO'), (1099, 'EXPIRADO'), (None, 'BLOQUEADO')):
            (self.root/'market_cooldown.json').write_text(json.dumps(dict(hasta=hasta, status=429)), encoding='utf-8')
            antes = self.huellas()
            with self.subTest(hasta=hasta):
                self.assertEqual(self.ejecutar()['cooldown_http']['estado'], esperado)
                self.assertEqual(self.huellas(), antes)
        (self.root/'market_cooldown.json').write_text('{"hasta":1,"status":451}', encoding='utf-8')
        self.assertEqual(self.ejecutar()['cooldown_http']['codigo'], 'REQUIERE_REVISION_LOCAL')

    def test_cooldown_json_malformado_desconocido_duplicado_y_no_finito(self):
        for contenido in ('[]', '{}', '{"hasta":true}', '{"hasta":NaN}', '{"hasta":1e9999}',
                          '{"hasta":1200,"hasta":1}', '{"hasta":-1}', '{"hasta":1000,"status":200}', 'x' * 262145):
            (self.root/'market_cooldown.json').write_text(contenido, encoding='utf-8')
            with self.subTest(contenido=contenido[:50]):
                self.assertEqual(self.ejecutar()['cooldown_http']['codigo'], 'COOLDOWN_NO_INTERPRETABLE')

    def test_estado_antiguo_activo_no_acredita_vida_actual(self):
        dato = self.ejecutar(ahora_epoch=1201)
        self.assertEqual(dato['estado'], 'NO_VERIFICADO')
        self.assertEqual(dato['runner']['estado'], 'REGISTRO_ANTIGUO')
        self.assertEqual(dato['runner']['proceso_vivo'], 'NO_VERIFICADO')

    def test_latido_activo_usa_heartbeat_y_terminal_fecha(self):
        self.runner['heartbeat_utc'] = self.fecha(1050)
        self.runner.pop('fecha')
        self.guardar_runner()
        r = self.ejecutar()['runner']
        self.assertEqual(r['estado'], 'REGISTRO_RECIENTE')
        self.assertEqual(r['edad_registro_seg'], 50)
        self.assertEqual(r['proceso_vivo'], 'NO_VERIFICADO')
        self.runner.update(estado='DETENIDO', fecha=self.fecha(1070))
        self.guardar_runner()
        self.assertEqual(self.ejecutar()['runner']['edad_registro_seg'], 30)

    def test_latido_futuro_no_usa_fecha_antigua_para_ocultarlo(self):
        self.runner['heartbeat_utc'] = self.fecha(1200)
        self.guardar_runner()
        self.assertEqual(self.ejecutar()['runner']['estado'], 'NO_VERIFICADO')

    def test_estado_runner_futuro_no_paper_o_incompleto_no_verificado(self):
        for campo, valor in (('modo', 'REAL'), ('fecha', self.fecha(1200)), ('fecha', '2026-09-29T12:00:00'),
                             ('salud', {}), ('estado', 'INVENTADO')):
            previo = self.runner[campo]
            self.runner[campo] = valor
            self.guardar_runner()
            with self.subTest(campo=campo): self.assertEqual(self.ejecutar()['runner']['estado'], 'NO_VERIFICADO')
            self.runner[campo] = previo
        (self.root/'runner_status.json').write_text('{"modo":"PAPER","modo":"REAL"}', encoding='utf-8')
        self.assertEqual(self.ejecutar()['runner']['estado'], 'NO_VERIFICADO')

    def test_salud_y_error_runner_recientes_bloquean_pero_no_afirman_vida(self):
        self.runner['salud']['scanner']['estado'] = 'DEGRADADO'
        self.guardar_runner()
        self.assertIn('SALUD_REGISTRADA_CON_ERRORES', self.ejecutar()['bloqueos'])
        self.runner['salud']['scanner']['estado'] = 'OK'
        self.runner['estado'] = 'ERROR'
        self.guardar_runner()
        self.assertIn('SALUD_REGISTRADA_CON_ERRORES', self.ejecutar()['bloqueos'])
        self.assertEqual(self.ejecutar()['runner']['proceso_vivo'], 'NO_VERIFICADO')

    def test_cli_rutas_explicitas_salida_json_y_codigo(self):
        salida = io.StringIO()
        with patch.object(doctor.time, 'time', return_value=1100), redirect_stdout(salida):
            codigo = doctor.main(['--directorio', str(self.root), '--base', str(self.base)])
        self.assertEqual(codigo, 0)
        self.assertEqual(json.loads(salida.getvalue())['base'], str(self.base.resolve()))
        salida = io.StringIO()
        with redirect_stdout(salida):
            codigo = doctor.main(['--directorio', str(self.root), '--max-edad-estado-seg', 'nan'])
        self.assertEqual(codigo, 2)
        self.assertEqual(json.loads(salida.getvalue())['estado'], 'NO_VERIFICADO')


class SondeoTests(unittest.TestCase):
    def test_clasifica_dll_appcontrol_y_otras_importaciones(self):
        casos = [('ImportError', 'DLL load failed', None, 'ERROR_CARGA_DLL'),
                 ('ImportError', 'DLL load failed: Application Control blocked this file', None, 'POSIBLE_BLOQUEO_APPLICATION_CONTROL'),
                 ('OSError', '', 4551, 'POSIBLE_BLOQUEO_APPLICATION_CONTROL'),
                 ('ModuleNotFoundError', 'No module', None, 'MODULO_NO_ENCONTRADO'),
                 ('ImportError', 'No symbol', None, 'IMPORT_ERROR')]
        for tipo, mensaje, winerror, esperado in casos:
            with self.subTest(tipo=tipo, mensaje=mensaje):
                self.assertEqual(doctor.clasificar_error_importacion(tipo, mensaje, winerror), esperado)

    def test_sondeo_exitoso_usa_mismo_python_sin_ejecutar_runner(self):
        proceso = subprocess.CompletedProcess([], 0, '{"ok":true}', '')
        with patch.object(doctor.metadata, 'version', return_value='1.2.3'), patch.object(doctor.subprocess, 'run', return_value=proceso) as ejecutar:
            dato = doctor.sondear_dependencia('pandas')
        self.assertTrue(dato['importable'])
        self.assertEqual(dato['version_instalada_metadata'], '1.2.3')
        self.assertEqual(ejecutar.call_args.args[0][:4], [doctor.sys.executable, '-I', '-B', '-c'])
        self.assertEqual(ejecutar.call_args.args[0][-1], 'pandas')
        self.assertFalse(ejecutar.call_args.kwargs.get('shell', False))

    def test_sondeo_error_no_republica_mensaje_y_timeout_acotado(self):
        proceso = subprocess.CompletedProcess([], 0, json.dumps(dict(ok=False, tipo='ImportError',
            mensaje='DLL load failed: Application Control, dato privado', winerror=None)), '')
        with patch.object(doctor.metadata, 'version', return_value='1.2.3'), patch.object(doctor.subprocess, 'run', return_value=proceso):
            dato = doctor.sondear_dependencia('pandas')
        self.assertEqual(dato['codigo'], 'POSIBLE_BLOQUEO_APPLICATION_CONTROL')
        self.assertNotIn('dato privado', json.dumps(dato))
        with patch.object(doctor.metadata, 'version', return_value='1.2.3'), patch.object(doctor.subprocess, 'run', side_effect=subprocess.TimeoutExpired('probe', 15)):
            self.assertEqual(doctor.sondear_dependencia('requests')['codigo'], 'TIEMPO_AGOTADO')

    def test_sondeo_salida_invalida_y_dependencia_no_permitida(self):
        for salida in ('[]', '{"ok":"si"}', '{"ok":false}', 'no-json'):
            proceso = subprocess.CompletedProcess([], 0, salida, '')
            with self.subTest(salida=salida), patch.object(doctor.metadata, 'version', return_value='1'), patch.object(doctor.subprocess, 'run', return_value=proceso):
                self.assertEqual(doctor.sondear_dependencia('pandas')['codigo'], 'RESPUESTA_SONDEO_INVALIDA')
        with self.assertRaises(ValueError): doctor.sondear_dependencia('MetaTrader5')


if __name__ == '__main__':
    unittest.main()
