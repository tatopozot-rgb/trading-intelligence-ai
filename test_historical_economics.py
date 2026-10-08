import unittest
from unittest.mock import patch

from historical_economics import diagnosticar_vela, resultado_hipotetico, escenarios_ambiguedad
from paper_store import calcular_resultado_cierre
import paper_store as store
import test_paper_system as fixtures


class MathTests(unittest.TestCase):
    def setUp(self):
        for destino in ('sqlite3.connect', 'requests.sessions.Session.request'):
            p=patch(destino, side_effect=AssertionError('Efectos externos prohibidos'))
            p.start(); self.addCleanup(p.stop)

    def test_ganancia_y_comisiones(self):
        r=calcular_resultado_cierre(100,40,104,.1)
        self.assertAlmostEqual(r['resultado_usd'],1.5184)
        self.assertAlmostEqual(r['resultado_bruto_usd'],1.6)
        self.assertAlmostEqual(r['comisiones_estimadas'],.0816)

    def test_perdida_con_comisiones(self):
        r=calcular_resultado_cierre(100,40,98,.1)
        self.assertAlmostEqual(r['resultado_usd'],-.8792)

    def test_precio_igual_no_es_costo_cero(self):
        self.assertAlmostEqual(calcular_resultado_cierre(100,40,100,.1)['resultado_usd'],-.08)

    def test_sin_comision_explicitamente(self):
        self.assertAlmostEqual(calcular_resultado_cierre(100,40,104,0)['resultado_usd'],1.6)

    def test_invalido_no_finito_y_overflow(self):
        for v in (True,0,-1,float('nan'),float('inf'),'100'):
            with self.subTest(v=v),self.assertRaises(ValueError): calcular_resultado_cierre(v,40,104,.1)
        for v in (True,-1,100,None,float('nan')):
            with self.subTest(comision=v),self.assertRaises(ValueError): calcular_resultado_cierre(100,40,104,v)
        with self.assertRaises(ValueError): calcular_resultado_cierre(1e-300,1e300,1e300,.1)

    def test_hipotetico_no_afirma_fill(self):
        r=resultado_hipotetico(entrada=100,tamano_posicion=40,salida_aportada=104,comision_pct=.1)
        self.assertFalse(r['fill_confirmado'])
        self.assertAlmostEqual(r['resultado_usd'],1.5184)

    def test_ambiguedad_no_resuelta(self):
        r=diagnosticar_vela(apertura=100,maximo=106,minimo=96,cierre=101,stop=98,objetivo=104)
        self.assertEqual(r['estado'],'AMBIGUO_AMBOS_NIVELES')
        self.assertIsNone(r['precio_fill'])
        self.assertFalse(r['fill_confirmado'])

    def test_toque_frontera_stop_y_objetivo(self):
        for minimo,maximo,esperado in ((98,103,'SOLO_STOP_OBSERVADO'),
                                       (99,104,'SOLO_OBJETIVO_OBSERVADO'),
                                       (99,103,'NINGUN_NIVEL')):
            r=diagnosticar_vela(apertura=100,maximo=maximo,minimo=minimo,cierre=101,stop=98,objetivo=104)
            self.assertEqual(r['estado'],esperado)

    def test_salto_apertura_no_promete_precio_del_stop(self):
        r=diagnosticar_vela(apertura=96,maximo=105,minimo=95,cierre=100,stop=98,objetivo=104)
        self.assertEqual(r['estado'],'APERTURA_EN_O_BAJO_STOP')
        self.assertIsNone(r['precio_fill'])

    def test_apertura_sobre_objetivo(self):
        r=diagnosticar_vela(apertura=106,maximo=107,minimo=97,cierre=100,stop=98,objetivo=104)
        self.assertEqual(r['estado'],'APERTURA_EN_O_SOBRE_OBJETIVO')

    def test_ohlc_invalido(self):
        with self.assertRaises(ValueError):
            diagnosticar_vela(apertura=100,maximo=99,minimo=98,cierre=100,stop=98,objetivo=104)
        with self.assertRaises(ValueError):
            diagnosticar_vela(apertura=100,maximo=102,minimo=98,cierre=101,stop=104,objetivo=98)


class EscenariosTests(unittest.TestCase):
    def setUp(self):
        self.parametros = dict(entrada=100, tamano_posicion=40, comision_pct=.1,
                              apertura=100, maximo=106, minimo=96, cierre=101,
                              stop=98, objetivo=104)
        for destino in ('sqlite3.connect', 'requests.sessions.Session.request'):
            p = patch(destino, side_effect=AssertionError('Efectos externos prohibidos'))
            p.start(); self.addCleanup(p.stop)

    def test_conserva_ambos_sin_elegir_promediar_o_probabilidades(self):
        r = escenarios_ambiguedad(**self.parametros)
        self.assertIsNone(r['seleccionado'])
        self.assertFalse(r['fill_confirmado'])
        self.assertEqual(set(r['escenarios']), {'STOP_PRIMERO', 'OBJETIVO_PRIMERO'})
        self.assertAlmostEqual(r['escenarios']['STOP_PRIMERO']['resultado_usd'], -.8792)
        self.assertAlmostEqual(r['escenarios']['OBJETIVO_PRIMERO']['resultado_usd'], 1.5184)
        for escenario in r['escenarios'].values():
            self.assertFalse(escenario['fill_confirmado'])
            self.assertNotIn('probabilidad', escenario)
        self.assertNotIn('resultado_usd', r)

    def test_determinismo_sin_mutacion(self):
        original = self.parametros.copy()
        self.assertEqual(escenarios_ambiguedad(**original),
                         escenarios_ambiguedad(**original))
        self.assertEqual(original, self.parametros)

    def test_saltos_y_toques_no_se_convierten_en_fills(self):
        for cambios in (dict(apertura=96, minimo=95), dict(apertura=106, maximo=107),
                        dict(minimo=99), dict(maximo=103), dict(minimo=99, maximo=103)):
            with self.subTest(cambios=cambios):
                r = escenarios_ambiguedad(**(self.parametros | cambios))
                self.assertEqual(r['escenarios'], {})
                self.assertIsNone(r['diagnostico']['precio_fill'])

    def test_toques_exactos_conservan_ambos(self):
        r = escenarios_ambiguedad(**(self.parametros | dict(minimo=98, maximo=104)))
        self.assertEqual(len(r['escenarios']), 2)

    def test_valida_entrada_y_parametros_incluso_sin_ambiguedad(self):
        for campo, valor in (('entrada', 98), ('entrada', 104), ('entrada', True),
                             ('entrada', float('nan')), ('tamano_posicion', -1),
                             ('comision_pct', float('inf')), ('comision_pct', True)):
            for cambios in ({}, dict(minimo=99, maximo=103)):
                with self.subTest(campo=campo, valor=valor, cambios=cambios):
                    with self.assertRaises(ValueError):
                        escenarios_ambiguedad(**(self.parametros | cambios | {campo: valor}))

    def test_costos_proporcionales_a_cada_salida(self):
        r = escenarios_ambiguedad(**self.parametros)['escenarios']
        self.assertAlmostEqual(r['STOP_PRIMERO']['comisiones_estimadas'], .0792)
        self.assertAlmostEqual(r['OBJETIVO_PRIMERO']['comisiones_estimadas'], .0816)


class ParidadStoreTests(unittest.TestCase):
    def test_cierre_sqlite_temporal_usa_calculo_comun(self):
        fixture=fixtures.PaperTests()
        fixture.setUp(); self.addCleanup(fixture.tearDown)
        identidad=fixture.abrir()['id']
        esperado=calcular_resultado_cierre(100,40,98,.1)
        resultado=store.cerrar(identidad,98,'CERRADA_STOP')
        self.assertEqual(resultado['resultado_usd'],esperado['resultado_usd'])
        self.assertAlmostEqual(resultado['saldo_actual'],100+esperado['resultado_usd'])
        self.assertFalse(store.cerrar(identidad,98,'CERRADA_STOP')['cerrada'])


if __name__ == '__main__': unittest.main()
