"""SHADOW sobre el runtime PAPER real: mismo veredicto que las reglas PAPER, sin efecto alguno. Sin red."""
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

import config
import paper_monitor as monitor
import paper_report
import paper_rules as rules
import paper_store as store
import system_runner as runner

TABLAS = ('paper_trades', 'paper_account', 'paper_halt', 'paper_equity_hist', 'paper_days',
          'paper_flows', 'paper_requests')


class ShadowTests(unittest.TestCase):
    def setUp(self):
        from test_paper_system import PaperTests
        PaperTests.setUp(self)
        self.addCleanup(lambda: PaperTests.tearDown(self))
        self.plan.update(consenso='ALCISTA', estado='ALCISTA MOMENTUM SANO', origen_revision='REGLAS_PAPER_V1')
        self.mercado = lambda simbolo: 100.0
        for parche in (patch.object(store, '_precio_para_equity', side_effect=lambda s: self.mercado(s)),
                       patch.object(config, 'DRAWDOWN_HALT_PCT', 15.0),
                       patch.object(config, 'DRAWDOWN_PAUSE_PCT', 8.0)):
            parche.start()
            self.addCleanup(parche.stop)

    def solicitud(self, **cambios):
        return store.registrar_solicitud({**self.plan, **cambios}, True)

    def estado(self):
        """Todo lo que SHADOW no puede tocar: tablas completas y eventos que no son SHADOW_*."""
        with store.conectar() as con:
            datos = {t: [tuple(f) for f in con.execute(f'SELECT * FROM {t} ORDER BY 1')] for t in TABLAS}
            datos['eventos'] = [tuple(f) for f in con.execute(
                "SELECT tipo,datos FROM paper_events WHERE tipo NOT LIKE 'SHADOW_%' ORDER BY id")]
        return datos

    def eventos_shadow(self):
        with store.conectar() as con:
            return [(f['tipo'], json.loads(f['datos'])) for f in con.execute(
                "SELECT tipo,datos FROM paper_events WHERE tipo LIKE 'SHADOW_%' ORDER BY id")]

    def sombra(self, solicitud, precio=100, sesion=lambda: True):
        return store.ejecutar_reglas_shadow(*solicitud, precio, sesion)

    @staticmethod
    def _sin_red(simbolo):
        raise OSError('sin red')

    # --- escenarios: (preparación, solicitud, precio) ---

    def escenarios(self):
        def abrir_btc():
            store.ejecutar_reglas(*self.solicitud(), 100, lambda: True)

        def halt_activo():
            with store.conectar() as con:
                con.execute("UPDATE paper_halt SET activo=1,razon='fixture'")

        def pausa():
            abrir_btc()
            self.mercado = lambda simbolo: 80.0

        def drawdown_nuevo():
            abrir_btc()
            self.mercado = lambda simbolo: 50.0

        def sin_precio():
            abrir_btc()
            self.mercado = self._sin_red

        def pausa_entradas():
            (self.root / 'PAUSA_ENTRADAS').touch()

        eth = {'simbolo': 'ETHUSDT'}
        return {
            'libre': (lambda: None, {}, 100, True),
            'duplicado': (abrir_btc, {}, 100, False),
            'otro_simbolo_con_posicion_abierta': (abrir_btc, eth, 100, True),
            'halt_activo': (halt_activo, {}, 100, False),
            'pausa_por_drawdown': (pausa, eth, 100, False),
            'drawdown_que_activaria_halt': (drawdown_nuevo, eth, 100, False),
            'sin_precio_dentro_de_gracia': (sin_precio, eth, 100, False),
            'precio_movido': (lambda: None, {}, 110, False),
            'pausa_entradas': (pausa_entradas, {}, 100, False),
            'riesgo_excesivo': (lambda: None, {'tamano_posicion': 90.}, 100, False),
        }

    def test_mismo_veredicto_que_paper_y_ningun_efecto(self):
        for nombre, (preparar, cambios, precio, esperado) in self.escenarios().items():
            with self.subTest(escenario=nombre):
                for ruta in self.root.glob('test.db*'):
                    ruta.unlink()
                (self.root / 'PAUSA_ENTRADAS').unlink(missing_ok=True)
                store.inicializar()
                self.mercado = lambda simbolo: 100.0
                preparar()
                solicitud = self.solicitud(**cambios)
                antes = self.estado()
                veredicto = self.sombra(solicitud, precio)
                self.assertEqual(self.estado(), antes, 'SHADOW alteró el estado PAPER')
                self.assertEqual(veredicto['abriria'], esperado)
                self.assertIs(veredicto['registrada'], False)
                # La misma solicitud sigue intacta: PAPER la decide ahora con el mismo estado.
                try:
                    real = store.ejecutar_reglas(*solicitud, precio, lambda: True)
                    registrada, motivo = real['registrada'], real.get('motivo', '')
                except ValueError as error:
                    registrada, motivo = False, str(error)
                self.assertEqual(veredicto['abriria'], registrada)
                self.assertEqual(veredicto['motivo'], motivo)

    def test_un_halt_que_shadow_activaria_no_se_activa_ni_mueve_el_pico(self):
        store.ejecutar_reglas(*self.solicitud(), 100, lambda: True)
        with store.conectar() as con:
            halt = dict(con.execute('SELECT * FROM paper_halt').fetchone())
            muestras = con.execute('SELECT COUNT(*) FROM paper_equity_hist').fetchone()[0]
        self.mercado = lambda simbolo: 50.0
        veredicto = self.sombra(self.solicitud(simbolo='ETHUSDT'))
        self.assertIn('DRAWDOWN_HALT', veredicto['motivo'])
        with store.conectar() as con:
            self.assertEqual(dict(con.execute('SELECT * FROM paper_halt').fetchone()), halt)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM paper_equity_hist').fetchone()[0], muestras)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM paper_events WHERE tipo='HALT_ACTIVADO'").fetchone()[0], 0)
        self.assertEqual(self.eventos_shadow()[-1][1]['halt_activo'], 0)
        # El camino real sí lo activa.
        self.assertTrue(store.evaluar_riesgo()['nuevo'])

    def test_registra_un_evento_auditable_por_decision(self):
        solicitud = self.solicitud()
        self.sombra(solicitud)
        self.sombra(solicitud, precio=110)
        (tipo_a, a), (tipo_b, b) = self.eventos_shadow()
        self.assertEqual((tipo_a, tipo_b), ('SHADOW_ABRIRIA', 'SHADOW_RECHAZADA'))
        self.assertEqual(a, {'request_id': solicitud[0], 'simbolo': 'BTCUSDT', 'lado': 'BUY', 'precio': 100,
                             'stop_precio': 98.0, 'objetivo_precio': 104.0, 'tamano_posicion': 40.0,
                             'motivo': '', 'halt_activo': 0})
        self.assertIn('precio cambió', b['motivo'])
        self.assertEqual(store.leer_solicitud(solicitud[0])['estado'], 'PENDIENTE')
        self.assertEqual(paper_report.informe()['estado'], 'OK')

    def test_solicitud_desconocida_o_alterada_se_rechaza_sin_inventar_datos(self):
        identidad, digest = self.solicitud()
        self.assertEqual(self.sombra(('0' * 32, digest))['motivo'], 'Solicitud desconocida o consumida.')
        self.assertIsNone(self.eventos_shadow()[-1][1]['request_id'])
        self.assertFalse(self.sombra((identidad, 'f' * 64))['abriria'])
        store.ejecutar_reglas(identidad, digest, 100, lambda: True)
        self.assertEqual(self.sombra((identidad, digest))['motivo'], 'Solicitud desconocida o consumida.')

    def test_exige_sesion_y_modo_paper(self):
        solicitud = self.solicitud()
        for sesion in (None, lambda: False):
            with self.assertRaisesRegex(ValueError, 'Sesión'):
                self.sombra(solicitud, sesion=sesion)
        with patch.object(config, 'USAR_DINERO_REAL', True), self.assertRaisesRegex(ValueError, 'PAPER'):
            self.sombra(solicitud)
        self.assertEqual(self.eventos_shadow(), [])

    def test_un_error_inesperado_tambien_se_revierte(self):
        solicitud = self.solicitud()
        antes = self.estado()
        with patch.object(store, '_registrar_apertura', side_effect=RuntimeError('fallo interno')):
            with self.assertRaisesRegex(RuntimeError, 'fallo interno'):
                self.sombra(solicitud)
        self.assertEqual(self.estado(), antes)
        self.assertEqual(self.eventos_shadow(), [])

    def test_reglas_paper_si_confirman_la_valoracion_tras_un_rechazo(self):
        # Contraste con SHADOW: el camino real por reglas conserva ultimo_ok y la muestra de equity.
        store.ejecutar_reglas(*self.solicitud(), 100, lambda: True)
        with store.conectar() as con:
            con.execute("UPDATE paper_halt SET ultimo_ok='2000-01-01T00:00:00+00:00'")
            muestras = con.execute('SELECT COUNT(*) FROM paper_equity_hist').fetchone()[0]
        with self.assertRaisesRegex(ValueError, 'Ya existe'):
            store.ejecutar_reglas(*self.solicitud(), 100, lambda: True)
        with store.conectar() as con:
            self.assertNotEqual(con.execute('SELECT ultimo_ok FROM paper_halt').fetchone()[0],
                                '2000-01-01T00:00:00+00:00')
            self.assertEqual(con.execute('SELECT COUNT(*) FROM paper_equity_hist').fetchone()[0], muestras + 1)

    # --- reglas y runner ---

    def test_procesar_candidatos_en_sombra_no_abre(self):
        antes = self.estado()['paper_trades']
        with patch.object(rules, 'obtener_precio_actual', return_value=100):
            decisiones = rules.procesar_candidatos([{'plan': self.plan}, {'error': 'x'}], lambda: True, sombra=True)
        self.assertEqual([(d['sombra'], d['abriria'], d['registrada']) for d in decisiones], [(True, True, False)])
        self.assertEqual(self.estado()['paper_trades'], antes)
        with patch.object(rules, 'obtener_precio_actual', side_effect=ValueError('sin cotización')):
            decisiones = rules.procesar_candidatos([{'plan': self.plan}], lambda: True, sombra=True)
        self.assertEqual((decisiones[0]['sombra'], decisiones[0]['abriria']), (True, False))

    def test_escaneo_en_sombra_no_exporta_claude_ni_abre(self):
        with patch.object(runner, 'ejecutar_scanner', return_value=[{'plan': self.plan}]), \
             patch.object(runner, 'crear_solicitud_claude', side_effect=AssertionError('Claude')), \
             patch.object(rules, 'obtener_precio_actual', return_value=100):
            r = runner.escanear(sesion_activa=lambda: True, reglas=True, sombra=True)
        self.assertTrue(r['sombra_paper'])
        self.assertTrue(r['decisiones_reglas'][0]['abriria'])
        self.assertEqual(self.estado()['paper_trades'], [])
        with patch.object(monitor, 'obtener_precio_actual', return_value=104), redirect_stdout(io.StringIO()):
            self.assertEqual(monitor.revisar_operaciones()['cerradas'], 0)

    def test_continuo_en_sombra_no_abre_y_se_identifica_como_shadow(self):
        (self.root / 'respuestas').mkdir()
        (self.root / 'respuestas' / 'pendiente.json').write_text('{}')
        estados = []
        original = runner.guardar_atomico

        def espia(ruta, texto):
            estados.append(json.loads(texto))
            return original(ruta, texto)

        with patch.object(runner, 'preparar', side_effect=store.inicializar), \
             patch.object(runner, 'ejecutar_scanner', return_value=[{'plan': self.plan}]), \
             patch.object(rules, 'obtener_precio_actual', return_value=100), \
             patch.object(monitor, 'obtener_precio_actual', return_value=100), \
             patch.object(runner, 'guardar_atomico', side_effect=espia), \
             patch.object(runner, 'procesar_entrada_bandeja', side_effect=AssertionError('bandeja')), \
             patch.object(runner, 'crear_solicitud_claude', side_effect=AssertionError('Claude')), \
             redirect_stdout(io.StringIO()):
            runner.ejecutar_continuo(horas=.0005, intervalo_scanner=60, intervalo_monitor=.05, sombra=True)
        self.assertEqual(self.estado()['paper_trades'], [])
        self.assertEqual([t for t, _ in self.eventos_shadow()], ['SHADOW_ABRIRIA'])
        activos = [e for e in estados if e.get('estado') == 'ACTIVO']
        self.assertTrue(activos)
        for e in estados:
            self.assertEqual(e['modo'], 'SHADOW_PAPER')
        self.assertEqual({e['autorizacion'] for e in activos}, {'SHADOW_PAPER'})
        final = json.loads((self.root / 'status.json').read_text())
        self.assertEqual((final['estado'], final['modo']), ('DETENIDO', 'SHADOW_PAPER'))

    def test_el_modo_paper_sigue_identificandose_como_paper(self):
        with patch.object(runner, 'preparar', side_effect=store.inicializar), \
             patch.object(runner, 'ejecutar_scanner', return_value=[]), \
             patch.object(monitor, 'obtener_precio_actual', return_value=100), redirect_stdout(io.StringIO()):
            runner.ejecutar_continuo(horas=.0003, intervalo_scanner=60, intervalo_monitor=.05, reglas=True)
        self.assertEqual(json.loads((self.root / 'status.json').read_text())['modo'], 'PAPER')

    def test_shadow_excluye_los_demas_modos(self):
        for kwargs in ({'reglas': True}, {'automatico': True}, {'sombra': 1}):
            with self.subTest(kwargs=kwargs), patch.object(runner, 'preparar', side_effect=AssertionError('inicio')), \
                    self.assertRaises(ValueError):
                runner.ejecutar_continuo(.01, **{'sombra': True, **kwargs})
        for args in (['--sombra-paper'], ['--sombra-paper', '--continuo', '--auto-paper'],
                     ['--sombra-paper', '--continuo', '--reglas-paper'],
                     ['--sombra-paper', '--continuo', '--prueba-claude'], ['--continuo', '--profundidad-paper']):
            with self.subTest(args=args), patch('sys.argv', ['runner', *args]), \
                    patch.object(runner, 'preparar', side_effect=AssertionError('inicio')), \
                    patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
                runner.main()
            self.assertEqual(error.exception.code, 2)

    def test_cli_pasa_sombra_al_runner(self):
        with patch('sys.argv', ['runner', '--continuo', '--sombra-paper', '--profundidad-paper', '--horas', '1']), \
                patch.object(runner, 'ejecutar_continuo') as ejecutar, patch.object(runner, 'instancia_unica'):
            runner.main()
        self.assertEqual(ejecutar.call_args.kwargs, {'reglas': False, 'sesion_id': None, 'profundidad': True,
                                                     'sombra': True})


if __name__ == '__main__':
    unittest.main()
