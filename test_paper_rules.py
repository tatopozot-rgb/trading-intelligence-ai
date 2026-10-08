from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import timedelta
import io
import json
import unittest
from unittest.mock import patch

import config
import paper_store as store
import paper_rules as rules
import system_runner as runner
import paper_monitor as monitor
import paper_report


class RulesTests(unittest.TestCase):
    def setUp(self):
        from test_paper_system import PaperTests
        PaperTests.setUp(self)
        self.addCleanup(lambda: PaperTests.tearDown(self))
        self.plan.update(consenso='ALCISTA', estado='ALCISTA MOMENTUM SANO', origen_revision='REGLAS_PAPER_V1')

    def solicitud(self, plan=None, ejecutable=True):
        return store.registrar_solicitud(self.plan if plan is None else plan, ejecutable)

    def abrir(self, solicitud=None, precio=100, sesion=lambda: True):
        return store.ejecutar_reglas(*(solicitud or self.solicitud()), precio, sesion)

    def test_apertura_cierre_sin_fingir_claude(self):
        solicitud = self.solicitud()
        r = self.abrir(solicitud)
        fila = store.leer_solicitud(solicitud[0])
        decision = json.loads(fila['respuesta'])
        self.assertEqual(decision['origen_revision'], 'REGLAS_PAPER_V1')
        self.assertNotIn('confianza', decision)
        self.assertTrue(store.cerrar(r['id'], 104, 'CERRADA_OBJETIVO')['cerrada'])
        self.assertAlmostEqual(store.cuenta()['saldo_actual'], 101.5184)
        with self.assertRaisesRegex(ValueError, 'consumida'):
            self.abrir(solicitud)

    def test_reporte_concilia_reglas_y_detecta_origen_alterado(self):
        self.abrir()
        self.assertEqual(paper_report.informe()['estado'], 'OK')
        with store.conectar() as con:
            fila = con.execute("SELECT id,datos FROM paper_events WHERE tipo='APERTURA'").fetchone()
            datos = json.loads(fila['datos']); datos['origen_revision'] = 'CLAUDE'
            con.execute('UPDATE paper_events SET datos=? WHERE id=?', (store.serializar(datos), fila['id']))
        self.assertIn('APERTURA_ORIGEN_NO_COINCIDE', [p['codigo'] for p in paper_report.informe()['problemas']])

    def test_claude_y_reglas_no_consumen_solicitudes_del_otro(self):
        plan = dict(self.plan); plan.pop('origen_revision')
        with self.assertRaisesRegex(ValueError, 'modo de reglas'):
            self.abrir(self.solicitud(plan))
        identidad, digest = self.solicitud()
        respuesta = dict(request_id=identidad, plan_hash=digest, simbolo='BTCUSDT',
                         decision='APROBAR_PAPER', confianza=100, razon='fixture')
        with self.assertRaisesRegex(ValueError, 'circuito Claude'):
            store.ejecutar_respuesta(respuesta, 'OK '+identidad, 100)

    def test_sesion_obligatoria_y_paper_exclusivo(self):
        for sesion in (None, lambda: False):
            with self.assertRaisesRegex(ValueError, 'Sesión'):
                self.abrir(sesion=sesion)
        with patch.object(config, 'USAR_DINERO_REAL', True):
            with self.assertRaisesRegex(ValueError, 'PAPER'):
                self.abrir()

    def test_origen_dentro_del_hash_no_puede_cambiar_de_circuito(self):
        identidad, digest = self.solicitud()
        alterado = {**self.plan, 'origen_revision':'CLAUDE'}
        with store.conectar() as con:
            con.execute('UPDATE paper_requests SET plan=? WHERE id=?', (store.serializar(alterado), identidad))
        respuesta = dict(request_id=identidad, plan_hash=digest, simbolo='BTCUSDT',
                         decision='APROBAR_PAPER', confianza=100, razon='fixture')
        with self.assertRaisesRegex(ValueError, 'alterada'):
            store.ejecutar_respuesta(respuesta, 'OK '+identidad, 100)
        original = dict(self.plan); original.pop('origen_revision')
        identidad, digest = self.solicitud(original)
        with store.conectar() as con:
            con.execute('UPDATE paper_requests SET plan=? WHERE id=?', (store.serializar(self.plan), identidad))
        with self.assertRaisesRegex(ValueError, 'alterada'):
            self.abrir((identidad, digest))

    def test_hash_caducidad_y_fixture_no_ejecutable(self):
        identidad, digest = self.solicitud()
        with self.assertRaisesRegex(ValueError, 'alterada'):
            self.abrir((identidad, 'incorrecto'))
        with store.conectar() as con:
            con.execute('UPDATE paper_requests SET expira=? WHERE id=?',
                        ((store.ahora()-timedelta(seconds=1)).isoformat(), identidad))
        with self.assertRaises(ValueError):
            self.abrir((identidad, digest))
        with self.assertRaisesRegex(ValueError, 'modo de reglas'):
            self.abrir(self.solicitud(ejecutable=False))

    def test_precio_pausa_riesgo_y_numero_posiciones(self):
        with self.assertRaisesRegex(ValueError, 'precio cambió'):
            self.abrir(precio=102)
        (self.root/'PAUSA_ENTRADAS').touch()
        with self.assertRaisesRegex(ValueError, 'pausadas'):
            self.abrir()
        (self.root/'PAUSA_ENTRADAS').unlink()
        with patch.object(config, 'RIESGO_POR_OPERACION_PCT', .1):
            with self.assertRaisesRegex(ValueError, 'riesgo por operación'):
                self.abrir()
        with patch.object(config, 'MAX_OPERACIONES_ABIERTAS', 0):
            with self.assertRaisesRegex(ValueError, 'Máximo'):
                self.abrir()

    def test_capital_y_perdidas_diarias(self):
        r = self.abrir()
        s = self.abrir(self.solicitud({**self.plan, 'simbolo':'ETHUSDT'}))
        with self.assertRaisesRegex(ValueError, 'Capital disponible'):
            self.abrir(self.solicitud({**self.plan, 'simbolo':'SOLUSDT'}))
        for trade in (r, s):
            store.cerrar(trade['id'], 98, 'CERRADA_STOP')
        t = self.abrir(); store.cerrar(t['id'], 98, 'CERRADA_STOP')
        with self.assertRaisesRegex(ValueError, 'Límite diario'):
            self.abrir()

    def test_rollback_si_sesion_termina_antes_commit(self):
        solicitud = self.solicitud()
        viva = [True]
        evento = store.evento
        def guardar(con, tipo, datos):
            evento(con, tipo, datos)
            if tipo == 'APERTURA':
                viva[0] = False
        with patch.object(store, 'evento', side_effect=guardar):
            with self.assertRaisesRegex(ValueError, 'antes de confirmar'):
                self.abrir(solicitud, sesion=lambda: viva[0])
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_trades').fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT count(*) FROM paper_events WHERE tipo='APERTURA'").fetchone()[0], 0)
        self.assertEqual(store.leer_solicitud(solicitud[0])['estado'], 'PENDIENTE')

    def test_concurrencia_un_solo_consumo(self):
        solicitud = self.solicitud()
        def intento(_):
            try:
                return self.abrir(solicitud)['registrada']
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(intento, range(4))), 1)

    def test_esperar_y_error_no_fuerzan_aperturas(self):
        with patch.object(rules, 'obtener_precio_actual', side_effect=AssertionError('red')):
            r = rules.procesar_candidatos([{'plan':{'decision':'ESPERAR'}}, {'error':'fixture', 'plan':self.plan}], lambda:True)
        self.assertEqual(r, [])

    def test_cotizacion_lenta_no_abre_fuera_de_sesion(self):
        viva = [True]
        def cotizar(_):
            viva[0] = False
            return 100
        with patch.object(rules, 'obtener_precio_actual', side_effect=cotizar):
            r = rules.procesar_candidatos([{'plan':self.plan}], lambda:viva[0])
        self.assertFalse(r[0]['registrada'])

    def test_scan_por_reglas_no_exporta_claude_y_monitor_cierra(self):
        with patch.object(runner, 'ejecutar_scanner', return_value=[{'plan':self.plan}]), \
             patch.object(runner, 'crear_solicitud_claude', side_effect=AssertionError('Claude')), \
             patch.object(rules, 'obtener_precio_actual', return_value=100):
            r = runner.escanear(sesion_activa=lambda:True, reglas=True)
        self.assertTrue(r['decisiones_reglas'][0]['registrada'])
        self.assertIsNone(r['solicitud'])
        with patch.object(monitor, 'obtener_precio_actual', return_value=104), redirect_stdout(io.StringIO()):
            self.assertEqual(monitor.revisar_operaciones()['cerradas'], 1)

    def test_cli_rechaza_combinaciones_antes_de_arrancar(self):
        for args in (['--reglas-paper'], ['--reglas-paper','--continuo','--auto-paper'],
                     ['--reglas-paper','--continuo','--prueba-claude']):
            with patch('sys.argv', ['runner', *args]), patch.object(runner, 'preparar', side_effect=AssertionError('inicio')), \
                 patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
                runner.main()
            self.assertEqual(error.exception.code, 2)

    def test_continuo_aislado_no_consume_bandeja(self):
        (self.root/'respuestas').mkdir()
        (self.root/'respuestas'/'pendiente.json').write_text('{}')
        with patch.object(runner, 'preparar', side_effect=store.inicializar), \
             patch.object(runner, 'ejecutar_scanner', return_value=[{'plan':self.plan}]), \
             patch.object(rules, 'obtener_precio_actual', return_value=100), \
             patch.object(monitor, 'obtener_precio_actual', return_value=100), \
             patch.object(runner, 'procesar_entrada_bandeja', side_effect=AssertionError('bandeja')), \
             patch.object(runner, 'crear_solicitud_claude', side_effect=AssertionError('Claude')), redirect_stdout(io.StringIO()):
            runner.ejecutar_continuo(horas=.0005, intervalo_scanner=60, intervalo_monitor=.05, reglas=True)
        self.assertEqual((self.root/'respuestas'/'pendiente.json').read_text(), '{}')
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_trades').fetchone()[0], 1)
        self.assertEqual(json.loads((self.root/'status.json').read_text())['estado'], 'DETENIDO')


if __name__ == '__main__':
    unittest.main()
