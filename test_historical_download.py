import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from analysis_engine import INTERVALOS_MS
from historical_download import crear_dataset, descargar_serie, fecha_ms
from market_http import DatosInvalidos


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.inicio = fecha_ms('2026-06-25')
        self.fin = self.inicio+86_400_000
        self.calls = []
        p = patch('requests.sessions.Session.request', side_effect=AssertionError('Red prohibida'))
        p.start(); self.addCleanup(p.stop)

    def consulta(self, ruta, p):
        self.assertEqual(ruta, '/api/v3/klines')
        self.calls.append(dict(p))
        paso = INTERVALOS_MS[p['interval']]
        return [[t,'100','102','99','101','10',t+paso-1,'1',1,'1','1','0']
                for t in list(range(p['startTime'],p['endTime']+1,paso))[:p['limit']]]

    def test_paginacion_y_limites(self):
        filas, paginas = descargar_serie('BTCUSDT','15m',self.inicio,self.inicio+1200*900000,self.consulta)
        self.assertEqual(len(filas),1200)
        self.assertEqual(len(paginas),2)
        self.assertEqual(self.calls[1]['startTime'],self.inicio+1000*900000)
        self.assertEqual(filas[-1]['tiempo_cierre'],self.inicio+1200*900000-1)

    def test_paginas_ambiguas_rechazadas(self):
        original = self.consulta('/api/v3/klines',dict(interval='15m',startTime=self.inicio,endTime=self.fin-1,limit=1000))
        for datos in ([],{},original[::-1],[original[0]]*2):
            with self.subTest(tipo=str(type(datos))), self.assertRaises(DatosInvalidos):
                descargar_serie('BTCUSDT','15m',self.inicio,self.fin,lambda *a:datos)

    def test_microsegundos_no_se_adivinan(self):
        def malo(r,p):
            datos=self.consulta(r,p); datos[0][0]*=1000; return datos
        with self.assertRaises(DatosInvalidos): descargar_serie('BTCUSDT','15m',self.inicio,self.fin,malo)

    def test_dataset_completo_y_no_sobrescritura(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino=Path(tmp)/'btc'
            manifest=crear_dataset('BTCUSDT',self.inicio,self.fin,destino,self.consulta,
                                   ahora_ms=self.fin,dormir=lambda _:None)
            m=json.loads(manifest.read_text())
            self.assertEqual(m['series']['4h']['filas'],206)
            self.assertEqual(m['series']['15m']['filas'],296)
            with self.assertRaises(FileExistsError):
                crear_dataset('BTCUSDT',self.inicio,self.fin,destino,self.consulta,ahora_ms=self.fin)

    def test_fallo_no_publica_manifiesto(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino=Path(tmp)/'fallo'
            with self.assertRaises(DatosInvalidos):
                crear_dataset('BTCUSDT',self.inicio,self.fin,destino,lambda *a:[],ahora_ms=self.fin)
            self.assertFalse((destino/'manifest.json').exists())
            self.assertTrue((destino/'solicitud.json').exists())

    def test_futuro_rechazado_antes_de_red(self):
        consulta=Mock()
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(DatosInvalidos):
            crear_dataset('BTCUSDT',self.inicio,self.fin,Path(tmp)/'futuro',consulta,ahora_ms=self.inicio)
        consulta.assert_not_called()

    def test_rango_invalido(self):
        for inicio,fin in ((True,self.fin),(self.inicio+1,self.fin),(self.fin,self.inicio)):
            with self.assertRaises(DatosInvalidos):
                descargar_serie('BTCUSDT','15m',inicio,fin,self.consulta)


if __name__ == '__main__': unittest.main()
