import copy
import unittest
from unittest.mock import patch

import pandas as pd
from historical_case import evaluar_caso, MODELO_ENTRADA, MODELO_SALIDA
from historical_path import PASO_MS
from historical_proposal import proponer_instante
from trade_planner import crear_plan_con_datos
import test_historical_analysis as fixtures


class CasoTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.HistoricalAnalysisTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.t=self.fixture.ahora
        self.args=dict(instante_entrada_ms=self.t,fin_exclusivo_ms=self.t+3*PASO_MS,
                       precio_entrada=120,capital=100,comision_pct=.1,
                       modelo_entrada=MODELO_ENTRADA,modelo_salida=MODELO_SALIDA)
        self.futuras=self.fixture.series['15m']['tiempo_apertura'] >= self.t
        self.fixture.series['15m'].loc[self.futuras,
            ['apertura','maximo','minimo','cierre']]=[120,121,119,120]

    def ejecutar(self,**cambios):
        return evaluar_caso('BTCUSDT',self.fixture.series,self.t,**(self.args | cambios))

    def test_integracion_paridad_y_referencia_separada(self):
        r=self.ejecutar()
        self.assertEqual(r['estado'],'CASO_HIPOTETICO_EVALUADO')
        self.assertEqual(r['trayectoria']['estado'],'SIN_SALIDA_EN_RANGO')
        esperado=crear_plan_con_datos('BTCUSDT',r['senal']['analisis_historico']['analisis'],
                    capital=100,precio=120,comision_pct=.1,modo='PAPER',real_bloqueado=False)
        esperado['decision']='PLAN HISTORICO HIPOTETICO'
        self.assertEqual(r['plan_hipotetico'],esperado)
        self.assertNotEqual(r['senal']['referencia']['precio'],120)
        self.assertFalse(r['ejecutable']); self.assertFalse(r['fill_confirmado'])

    def test_futuro_cambia_resultado_no_senal_ni_plan(self):
        antes=self.ejecutar()
        self.fixture.series['15m'].loc[self.futuras,'maximo']=140
        despues=self.ejecutar()
        self.assertEqual(antes['senal'],despues['senal'])
        self.assertEqual(antes['plan_hipotetico'],despues['plan_hipotetico'])
        self.assertEqual(despues['trayectoria']['estado'],'SALIDA_HIPOTETICA')

    def test_ambiguedad_conserva_dos_resultados(self):
        self.fixture.series['15m'].loc[self.futuras,['minimo','maximo']]=[90,150]
        r=self.ejecutar()['trayectoria']
        self.assertEqual(set(r['escenarios']),{'STOP_PRIMERO','OBJETIVO_PRIMERO'})
        self.assertIsNone(r['seleccionado'])

    def test_senal_esperar_no_evalua_entrada(self):
        señal=proponer_instante('BTCUSDT',self.fixture.series,self.t,capital=100,comision_pct=.1)
        señal['decision_reglas']='ESPERAR'
        with patch('historical_case.proponer_instante',return_value=señal), \
             patch('historical_case.evaluar_trayectoria',side_effect=AssertionError):
            r=self.ejecutar()
        self.assertEqual(r['estado'],'SIN_ENTRADA_POR_REGLAS')
        self.assertIsNone(r['plan_hipotetico']); self.assertIsNone(r['trayectoria'])

    def test_cronologia_rechaza_entrada_anterior_o_intravela(self):
        for cambios in (dict(instante_entrada_ms=self.t-PASO_MS),
                        dict(instante_entrada_ms=self.t+1),dict(instante_entrada_ms=True),
                        dict(fin_exclusivo_ms=self.t),dict(fin_exclusivo_ms=2**54)):
            with self.subTest(cambios=cambios),self.assertRaises(ValueError): self.ejecutar(**cambios)

    def test_senal_intravela_admite_entrada_al_siguiente_inicio(self):
        self.t += 1000
        r=self.ejecutar(instante_entrada_ms=self.args['instante_entrada_ms']+PASO_MS)
        self.assertEqual(r['estado'],'CASO_HIPOTETICO_EVALUADO')

    def test_cobertura_incompleta_y_hueco_no_se_rellenan(self):
        with self.assertRaises(ValueError): self.ejecutar(fin_exclusivo_ms=self.t+11*PASO_MS)
        df=self.fixture.series['15m']
        self.fixture.series['15m']=df[df.tiempo_apertura != self.t+PASO_MS]
        with self.assertRaises(ValueError): self.ejecutar()

    def test_fin_no_usa_velas_posteriores(self):
        antes=self.ejecutar()
        df=self.fixture.series['15m']
        df.loc[df.tiempo_apertura >= self.args['fin_exclusivo_ms'],
               ['apertura','maximo','minimo','cierre']]=float('nan')
        self.assertEqual(antes,self.ejecutar())

    def test_modelos_y_precio_explicitos(self):
        for cambios in (dict(modelo_entrada=''),dict(modelo_salida=''),
                        dict(precio_entrada=True),dict(precio_entrada=float('nan'))):
            with self.subTest(cambios=cambios),self.assertRaises(ValueError): self.ejecutar(**cambios)
        args=self.args.copy(); args.pop('precio_entrada')
        with self.assertRaises(TypeError): evaluar_caso('BTCUSDT',self.fixture.series,self.t,**args)

    def test_no_mutacion_y_repetibilidad(self):
        antes=copy.deepcopy(self.fixture.series)
        self.assertEqual(self.ejecutar(),self.ejecutar())
        for k in antes: pd.testing.assert_frame_equal(antes[k],self.fixture.series[k])

    def test_consumidor_operativo_ignora_plan(self):
        import paper_rules
        r=self.ejecutar()
        with patch('paper_rules.store.validar_paper'), \
             patch('paper_rules.store.registrar_solicitud',side_effect=AssertionError):
            self.assertEqual(paper_rules.procesar_candidatos(
                [{'plan':r['plan_hipotetico']}],lambda:True),[])


if __name__ == '__main__': unittest.main()
