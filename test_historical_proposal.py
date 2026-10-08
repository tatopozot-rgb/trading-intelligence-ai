import copy
import unittest
from unittest.mock import patch

import trade_planner as planner
from historical_proposal import proponer_instante
import test_historical_analysis as fixtures


class ConstructorTests(unittest.TestCase):
    def setUp(self):
        self.analisis = dict(consenso='ALCISTA', estado='ALCISTA MOMENTUM SANO',
                             temporalidades={'1h': dict(precio=99, atr_pct=2)})
        for destino in ('sqlite3.connect', 'requests.sessions.Session.request'):
            p = patch(destino, side_effect=AssertionError('Efecto externo prohibido'))
            p.start(); self.addCleanup(p.stop)

    def calcular(self, **cambios):
        datos = dict(capital=100, precio=100, comision_pct=.1,
                     modo='PAPER', real_bloqueado=False)
        return planner.crear_plan_con_datos('BTCUSDT', self.analisis, **(datos | cambios))

    def test_reglas_y_costos_existentes(self):
        r = self.calcular()
        self.assertEqual(r['stop_precio'], 97)
        self.assertEqual(r['objetivo_precio'], 106)
        self.assertAlmostEqual(r['tamano_posicion'], 31.25)
        self.assertAlmostEqual(r['riesgo_usd'], 1)

    def test_paridad_wrapper_cotizacion_actual_y_capital_variable(self):
        for capital in (50, 100, 1000):
            with patch.object(planner, 'obtener_capital_operativo', return_value=capital), \
                 patch('paper_monitor.obtener_precio_actual', return_value=100) as cotizar:
                self.assertEqual(planner.crear_plan('BTCUSDT', self.analisis),
                                 self.calcular(capital=capital))
                cotizar.assert_called_once_with('BTCUSDT')

    def test_esperar_no_consulta_precio(self):
        for consenso, estado in (('BAJISTA','BAJISTA'), ('ALCISTA','SOBREEXTENDIDA'),
                                  ('ALCISTA','OTRO')):
            self.analisis.update(consenso=consenso, estado=estado)
            with patch.object(planner, 'obtener_capital_operativo', return_value=100), \
                 patch('paper_monitor.obtener_precio_actual', side_effect=AssertionError):
                self.assertEqual(planner.crear_plan('BTCUSDT',self.analisis)['decision'], 'ESPERAR')

    def test_bandera_real_sigue_bloqueada(self):
        self.assertEqual(self.calcular(real_bloqueado=True)['decision'], 'ESPERAR')

    def test_invalidos_y_stop_no_positivo_rechazados(self):
        for campo in ('capital', 'precio', 'comision_pct'):
            for v in (True, -1, float('nan'), float('inf')):
                with self.subTest(campo=campo,v=v), self.assertRaises(ValueError):
                    self.calcular(**{campo:v})
        self.analisis['temporalidades']['1h']['atr_pct'] = 100
        with self.assertRaises(ValueError): self.calcular()

    def test_no_muta_analisis_y_stop_minimo(self):
        self.analisis['temporalidades']['1h']['atr_pct'] = .2
        original = copy.deepcopy(self.analisis)
        self.assertEqual(self.calcular()['stop_pct'], 1)
        self.assertEqual(original, self.analisis)

    def test_atr_cero_conserva_stop_minimo(self):
        self.analisis['temporalidades']['1h']['atr_pct'] = 0
        self.assertEqual(self.calcular()['stop_pct'], 1)


class HistoricalProposalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HistoricalAnalysisTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def ejecutar(self, **cambios):
        return proponer_instante('BTCUSDT', self.fixture.series, self.fixture.ahora,
                                 **(dict(capital=100, comision_pct=.1) | cambios))

    def test_paridad_y_referencia_no_fill(self):
        r = self.ejecutar()
        self.assertEqual(r['decision_reglas'], 'PAPER CANDIDATE')
        a = r['analisis_historico']['analisis']
        esperado = planner.crear_plan_con_datos(
            'BTCUSDT', a, capital=100, precio=a['temporalidades']['1h']['precio'],
            comision_pct=.1, modo='PAPER', real_bloqueado=False)
        self.assertEqual(r['decision_reglas'], esperado['decision'])
        esperado['decision'] = ('PROPUESTA HISTORICA' if esperado['decision']=='PAPER CANDIDATE'
                                else 'ESPERAR')
        self.assertEqual(r['propuesta'], esperado)
        self.assertFalse(r['ejecutable'])
        self.assertFalse(r['fill_confirmado'])
        self.assertIsNone(r['precio_fill'])
        self.assertLess(r['referencia']['tiempo_cierre_ms'], self.fixture.ahora)
        self.assertIn('SIN_EVOLUCION', r['politica_capital'])

    def test_abierta_y_futuro_no_influyen(self):
        self.fixture.ahora += 120000
        antes = self.ejecutar()
        for df in self.fixture.series.values():
            df.loc[df.tiempo_cierre >= self.fixture.ahora,
                   ['apertura','maximo','minimo','cierre','volumen']] = float('nan')
        self.assertEqual(antes,self.ejecutar())

    def test_capital_y_comision_explicitos(self):
        r = self.ejecutar(capital=250, comision_pct=.2)
        self.assertEqual(r['propuesta']['capital'],250)
        self.assertEqual(r['comision_pct_aportada'],.2)
        with self.assertRaises(TypeError):
            proponer_instante('BTCUSDT',self.fixture.series,self.fixture.ahora)

    def test_consumidor_reglas_no_acepta_propuesta_historica(self):
        import paper_rules
        r = self.ejecutar()
        with patch('paper_rules.store.validar_paper'), \
             patch('paper_rules.store.registrar_solicitud', side_effect=AssertionError), \
             patch('paper_rules.obtener_precio_actual', side_effect=AssertionError):
            self.assertEqual(paper_rules.procesar_candidatos(
                [{'plan': r['propuesta']}], lambda: True), [])


if __name__ == '__main__': unittest.main()
