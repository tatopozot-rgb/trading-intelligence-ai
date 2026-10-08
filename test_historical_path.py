import copy
import unittest
from unittest.mock import patch

from historical_path import evaluar_trayectoria, MODELO, PASO_MS


class TrayectoriaTests(unittest.TestCase):
    def setUp(self):
        self.t = 1_790_121_600_000
        self.velas = [dict(tiempo_apertura=self.t+i*PASO_MS,
                           tiempo_cierre=self.t+(i+1)*PASO_MS-1,
                           apertura=100, maximo=103, minimo=99, cierre=101) for i in range(3)]
        self.parametros = dict(inicio_ms=self.t, fin_exclusivo_ms=self.t+3*PASO_MS,
                               entrada=100, tamano_posicion=40, stop=98, objetivo=104,
                               comision_pct=.1, modelo=MODELO)
        for destino in ('sqlite3.connect','requests.sessions.Session.request'):
            p=patch(destino,side_effect=AssertionError('Efectos externos prohibidos'))
            p.start(); self.addCleanup(p.stop)

    def ejecutar(self, **cambios):
        return evaluar_trayectoria(self.velas, **(self.parametros | cambios))

    def test_sin_salida_no_liquida(self):
        r=self.ejecutar()
        self.assertEqual(r['estado'],'SIN_SALIDA_EN_RANGO')
        self.assertEqual(r['escenarios'],{})
        self.assertIsNone(r['evento'])
        self.assertNotIn('resultado_usd',r)

    def test_stop_y_comisiones(self):
        self.velas[1]['minimo']=98
        r=self.ejecutar()
        self.assertAlmostEqual(r['escenarios']['SOLO_STOP_OBSERVADO']['resultado_usd'],-.8792)
        self.assertEqual(r['evento']['primera_apertura_ms'],self.t+PASO_MS)

    def test_objetivo_y_comisiones(self):
        self.velas[1]['maximo']=104
        r=self.ejecutar()
        self.assertAlmostEqual(r['escenarios']['SOLO_OBJETIVO_OBSERVADO']['resultado_usd'],1.5184)

    def test_ambos_no_elige_ni_usa_vela_posterior_para_resolver(self):
        self.velas[0].update(minimo=97,maximo=105)
        r=self.ejecutar()
        self.assertEqual(set(r['escenarios']),{'STOP_PRIMERO','OBJETIVO_PRIMERO'})
        self.assertIsNone(r['seleccionado'])
        self.velas[1].update(apertura=80,maximo=200,minimo=50,cierre=190)
        self.assertEqual(r,self.ejecutar())

    def test_salto_apertura_no_promete_stop(self):
        self.velas[1].update(apertura=95,minimo=94,maximo=105,cierre=100)
        r=self.ejecutar()
        s=r['escenarios']['APERTURA_EN_O_BAJO_STOP']
        self.assertEqual(s['salida_aportada'],95)
        self.assertFalse(s['fill_confirmado'])
        self.assertIsNone(r['evento']['instante_fill'])

    def test_salto_sobre_objetivo(self):
        self.velas[1].update(apertura=106,minimo=97,maximo=107,cierre=100)
        r=self.ejecutar()
        self.assertEqual(r['escenarios']['APERTURA_EN_O_SOBRE_OBJETIVO']['salida_aportada'],106)

    def test_primer_toque_impide_cierre_doble(self):
        self.velas[0]['minimo']=97
        self.velas[1]['maximo']=105
        self.assertEqual(list(self.ejecutar()['escenarios']),['SOLO_STOP_OBSERVADO'])

    def test_modelo_explicito_sin_default(self):
        with self.assertRaises(ValueError): self.ejecutar(modelo='otro')
        argumentos=self.parametros.copy(); argumentos.pop('modelo')
        with self.assertRaises(TypeError): evaluar_trayectoria(self.velas,**argumentos)

    def test_no_mutacion_determinista(self):
        antes=copy.deepcopy(self.velas)
        self.assertEqual(self.ejecutar(),self.ejecutar())
        self.assertEqual(self.velas,antes)
        self.assertFalse(self.ejecutar()['ejecutable'])

    def test_huecos_desorden_y_timestamps_booleanos(self):
        original=copy.deepcopy(self.velas)
        for velas in (original[:-1],original[::-1],original[:1]+original[:1]+original[2:]):
            with self.assertRaises(ValueError): evaluar_trayectoria(velas,**self.parametros)
        self.velas[0]['tiempo_apertura']=True
        with self.assertRaises(ValueError): self.ejecutar()

    def test_ohlc_invalido_aun_despues_del_evento(self):
        self.velas[0]['minimo']=97
        self.velas[2]['maximo']=1
        with self.assertRaises(ValueError): self.ejecutar()

    def test_sin_salida_valida_parametros_financieros(self):
        for cambios in (dict(comision_pct=True),dict(entrada=98),dict(tamano_posicion=0),
                        dict(stop=float('nan')),dict(objetivo=float('inf'))):
            with self.subTest(cambios=cambios),self.assertRaises(ValueError): self.ejecutar(**cambios)

    def test_rango_no_alineado_o_invertido(self):
        for cambios in (dict(inicio_ms=True),dict(inicio_ms=self.t+1),
                        dict(fin_exclusivo_ms=self.t),dict(fin_exclusivo_ms=self.t+367*86400000)):
            with self.subTest(cambios=cambios),self.assertRaises(ValueError): self.ejecutar(**cambios)


if __name__ == '__main__': unittest.main()
