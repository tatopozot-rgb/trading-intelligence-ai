"""Demos sin efectos al importar y sin una segunda implementación del análisis."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import pandas as pd
import analysis_engine as analysis
import market_data
import technical_analysis as demo
import trading_scanner as scanner


class DemoTests(unittest.TestCase):
    def test_importacion_fria_sin_red_sin_db_sin_salida(self):
        codigo = '''from unittest.mock import patch
with (patch('requests.get',side_effect=AssertionError('red no permitida')),
      patch('sqlite3.connect',side_effect=AssertionError('DB no permitida'))):
    import market_data
    import technical_analysis
'''
        resultado = subprocess.run([sys.executable,'-c',codigo],cwd=Path(__file__).parent,
                                   capture_output=True,text=True,timeout=30)
        self.assertEqual(resultado.returncode,0,resultado.stderr)
        self.assertEqual(resultado.stdout,'')

    def test_radar_conserva_limite_quince_sin_analizar_ni_operar(self):
        candidato = {'simbolo':'BTCUSDT','precio':100,'cambio':3,'volumen':30_000_000,'score':22}
        salida = io.StringIO()
        with (patch.object(market_data,'obtener_candidatos',return_value=[candidato]) as obtener,
              patch.object(scanner,'analizar_simbolo') as analizar, redirect_stdout(salida)):
            market_data.main()
        obtener.assert_called_once_with(limite=15)
        analizar.assert_not_called()
        self.assertIn('BTCUSDT',salida.getvalue())

    def test_limite_demo_no_cambia_cinco_del_scanner(self):
        datos = [{'symbol':f'X{i}USDT','lastPrice':'100','priceChangePercent':'3',
                  'quoteVolume':'30000000'} for i in range(20)]
        with (patch.object(scanner,'obtener_simbolos_validos',return_value={d['symbol'] for d in datos}),
              patch.object(scanner,'get_publico',return_value=datos)):
            self.assertEqual(len(scanner.obtener_candidatos(limite=15)),15)
            self.assertEqual(len(scanner.obtener_candidatos()),5)
        with patch.object(scanner,'get_publico') as consultar:
            for limite in (True,0,-1,2.5):
                with self.assertRaises(ValueError):
                    scanner.obtener_candidatos(limite)
            consultar.assert_not_called()

    def test_analisis_demo_igual_motor_no_muta_y_excluye_abierta(self):
        ahora = 1_800_000_000_000
        paso = 900_000
        df = pd.DataFrame([{'tiempo_apertura':ahora-(59-i)*paso,
            'tiempo_cierre':ahora-(58-i)*paso-1,'apertura':100+i*.1,
            'cierre':100+i*.1+(-1)**i*.2,'maximo':101+i*.1,
            'minimo':99+i*.1,'volumen':100.} for i in range(60)])
        original = df.copy(deep=True)
        resultado = demo.analizar(df,'15m',ahora)
        self.assertEqual(resultado,analysis.analizar_temporalidad(df,'15m',ahora))
        self.assertEqual(resultado['vela_cierre_utc_ms'],ahora-1)
        pd.testing.assert_frame_equal(df,original)
        df.loc[10,'cierre'] = float('nan')
        with self.assertRaises(ValueError):
            demo.analizar(df,'15m',ahora)

    def test_demo_multitemporal_delega_una_vez(self):
        datos = {'precio':100,'ema20':99,'ema50':98,'rsi':50,'tendencia':'ALCISTA'}
        resultado = {'temporalidades':{'15m':datos},'consenso':'ALCISTA','estado':'fixture'}
        with (patch.object(demo,'analizar_simbolo',return_value=resultado) as analizar,
              redirect_stdout(io.StringIO())):
            demo.main()
        analizar.assert_called_once_with('BTCUSDT')


if __name__=='__main__':
    unittest.main()
