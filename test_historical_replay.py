import unittest
from unittest.mock import patch

from historical_analysis import analizar_instante
from historical_dataset import cargar_dataset
from historical_replay import reproducir
from market_http import DatosInvalidos
import test_historical_dataset as fixtures
from analysis_engine import INTERVALOS_MS


class ReplayTests(unittest.TestCase):
    def setUp(self):
        # Reutiliza exclusivamente generador de fixtures temporales de H2.
        fixtures.DatasetTests.setUp(self)

    guardar_serie = fixtures.DatasetTests.guardar_serie
    guardar = fixtures.DatasetTests.guardar

    def test_paridad_h1_cada_punto_incluso_cambio_hora(self):
        inicio = self.ahora-3_600_000
        fin = self.ahora+900_000
        r = reproducir(self.ruta, inicio, fin)
        ds = cargar_dataset(self.ruta)
        for fila in r['filas']:
            h1 = analizar_instante('BTCUSDT', ds['series'], fila['instante_utc_ms'])
            self.assertEqual(fila['analisis'], h1['analisis'])
            self.assertEqual(fila['ventanas'], h1['ventanas'])
        self.assertEqual(r['evaluaciones'],5)
        self.assertEqual(sum(r['estados'].values()),5)

    def test_determinismo_y_sin_mutacion(self):
        antes={p.name:p.read_bytes() for p in self.root.iterdir()}
        a=reproducir(self.ruta,self.ahora,self.ahora+900_000)
        b=reproducir(self.ruta,self.ahora,self.ahora+900_000)
        self.assertEqual(a,b)
        self.assertEqual(antes,{p.name:p.read_bytes() for p in self.root.iterdir()})
        self.assertNotIn('pnl',a)

    def test_fuera_cobertura_rechazado(self):
        with self.assertRaises(DatosInvalidos):
            reproducir(self.ruta,self.ahora,self.ahora+2*900_000)

    def test_calentamiento_insuficiente(self):
        inicio=self.m['series']['4h']['inicio_ms']
        with self.assertRaises(DatosInvalidos): reproducir(self.ruta,inicio,inicio+900_000)

    def test_rangos_invalidos(self):
        for inicio,fin in ((True,self.ahora),(self.ahora+1,self.ahora+900_000),
                           (self.ahora,self.ahora),(self.ahora,self.ahora+367*86_400_000)):
            with self.subTest(inicio=inicio), self.assertRaises(DatosInvalidos):
                reproducir(self.ruta,inicio,fin)

    def test_episodios_no_son_conteo_de_ordenes(self):
        # Repetición de condición se cuenta como un episodio, no tres compras.
        for marco, paso in INTERVALOS_MS.items():
            for n in range(1,4):
                fila=dict(self.filas[marco][-1]); fila['tiempo_apertura']+=paso
                fila['tiempo_cierre']+=paso; self.filas[marco].append(fila)
            self.guardar_serie(marco)
        self.guardar()
        resumen={'consenso':'ALCISTA','estado':'ALCISTA MOMENTUM SANO','simbolo':'BTCUSDT'}
        with patch('historical_replay.resumir_temporalidades',return_value=resumen):
            r=reproducir(self.ruta,self.ahora,self.ahora+3*900_000)
        self.assertEqual(r['condiciones_cumplidas'],3)
        self.assertEqual(r['episodios_condicion'],1)


if __name__ == '__main__': unittest.main()
