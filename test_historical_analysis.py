"""Datos sintéticos exclusivamente; red y SQLite prohibidos."""
import unittest
from unittest.mock import patch

import pandas as pd

import analysis_engine as engine
from historical_analysis import analizar_instante
from market_http import DatosInvalidos


class HistoricalAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.ahora = 1_790_121_600_000
        self.series = {}
        for intervalo, paso in engine.INTERVALOS_MS.items():
            inicio = (self.ahora // paso - 250) * paso
            filas = []
            for i in range(260):
                t = inicio + i * paso
                precio = 100 + .05*i + (.5 if i % 2 else -.5)
                filas.append(dict(tiempo_apertura=t, tiempo_cierre=t+paso-1,
                                  apertura=precio, cierre=precio, maximo=precio+1,
                                  minimo=precio-1, volumen=1000))
            self.series[intervalo] = pd.DataFrame(filas)
        for destino in ('requests.sessions.Session.request', 'sqlite3.connect',
                        'analysis_engine.obtener_velas'):
            p = patch(destino, side_effect=AssertionError('Efecto externo prohibido'))
            p.start(); self.addCleanup(p.stop)

    def ejecutar(self):
        return analizar_instante('BTCUSDT', self.series, self.ahora)

    def test_resultado_reutiliza_motor_y_ventana_sin_mutar(self):
        originales = {k:v.copy(deep=True) for k,v in self.series.items()}
        r = self.ejecutar()
        esperados = {}
        for marco, df in self.series.items():
            ventana = df[df.tiempo_apertura <= self.ahora].tail(engine.LIMITE)
            esperados[marco] = engine.analizar_temporalidad(ventana, marco, self.ahora)
            self.assertEqual(r['ventanas'][marco]['velas_cerradas'], 199)
            pd.testing.assert_frame_equal(df, originales[marco])
        self.assertEqual(r['analisis'], engine.resumir_temporalidades('BTCUSDT', esperados))
        self.assertNotIn('pnl', r)

    def test_futuro_y_vela_abierta_no_influyen(self):
        antes = self.ejecutar()
        for df in self.series.values():
            df.loc[df.tiempo_cierre >= self.ahora,
                   ['apertura','cierre','maximo','minimo','volumen']] = float('nan')
        self.assertEqual(antes, self.ejecutar())

    def test_cierre_exacto_no_se_adelanta(self):
        self.ahora -= 1
        r = self.ejecutar()
        for intervalo, paso in engine.INTERVALOS_MS.items():
            self.assertEqual(r['ventanas'][intervalo]['ultima_cierre_ms'], self.ahora-paso)
            self.assertEqual(r['ventanas'][intervalo]['velas_cerradas'], 199)

    def test_historial_obsoleto_rechazado(self):
        self.series['1h'] = self.series['1h'].iloc[:240]
        with self.assertRaises(DatosInvalidos): self.ejecutar()

    def test_hueco_rechazado(self):
        self.series['15m'] = self.series['15m'].drop(index=245)
        with self.assertRaises(DatosInvalidos): self.ejecutar()

    def test_desorden_y_duplicados_rechazados(self):
        original = self.series['1h']
        for df in (original.iloc[::-1], pd.concat([original, original.iloc[-1:]])):
            self.series['1h'] = df
            with self.assertRaises(DatosInvalidos): self.ejecutar()

    def test_minimo_cerradas(self):
        self.series['4h'] = self.series['4h'].iloc[191:]
        with self.assertRaisesRegex(DatosInvalidos, '60 velas'): self.ejecutar()

    def test_ohlc_pasado_invalido_rechazado(self):
        self.series['1h'].loc[249, 'maximo'] = 1
        with self.assertRaises(DatosInvalidos): self.ejecutar()

    def test_argumentos_explicitos(self):
        for reloj in (True, 0, -1, float('nan'), 1.2, '123', 2**54):
            with self.subTest(reloj=reloj), self.assertRaises(DatosInvalidos):
                analizar_instante('BTCUSDT', self.series, reloj)
        for datos in ({}, {'1h':self.series['1h']}, {**self.series,'5m':None}):
            with self.assertRaises(DatosInvalidos):
                analizar_instante('BTCUSDT', datos, self.ahora)

    def test_timestamps_invalidos_rechazados(self):
        for valor in (True, float('nan'), 'texto', 123.5):
            datos = {k:v.copy().astype(object) for k,v in self.series.items()}
            datos['1h'].loc[249, 'tiempo_apertura'] = valor
            with self.subTest(valor=valor), self.assertRaises(DatosInvalidos):
                analizar_instante('BTCUSDT', datos, self.ahora)


if __name__ == '__main__':
    unittest.main()
