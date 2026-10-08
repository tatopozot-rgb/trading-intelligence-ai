"""Pruebas de datos sin llamadas de red ni cambios al saldo de trabajo."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
import market_http as mercado
import trading_scanner as scanner
import analysis_engine as analysis
import pandas as pd
from concurrent.futures import ThreadPoolExecutor


def respuesta(status=200, datos=None, retry=None):
    r = Mock(status_code=status, headers={} if retry is None else {'Retry-After': retry})
    r.json.return_value = {'serverTime': 123} if datos is None else datos
    return r


class MercadoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name)/'cooldown.json'
        self.reloj = [1000.]
        self.transporte = Mock()
        self.dormir = Mock()
        self.cliente = mercado.ClientePublico(self.ruta, self.transporte, lambda: self.reloj[0], self.dormir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_publico_sin_redireccion(self):
        r = respuesta()
        self.transporte.return_value = r
        self.assertEqual(self.cliente.get('/api/v3/time'), {'serverTime': 123})
        self.transporte.assert_called_once_with(mercado.BASE+'/api/v3/time', params={}, timeout=(5,15), allow_redirects=False)
        r.close.assert_called_once()

    def test_bloquea_rutas_y_parametros_privados(self):
        for ruta, params in [('/api/v3/order', {}), ('https://otro.example', {}),
                             ('/api/v3/time', {'signature':'secreto'}),
                             ('/api/v3/time', {'apiKey':'secreto'})]:
            with self.subTest(ruta=ruta, params=params), self.assertRaises(ValueError):
                self.cliente.get(ruta, params)
        self.transporte.assert_not_called()

    def test_reintento_red_acotado(self):
        self.transporte.side_effect = [requests.Timeout(), respuesta()]
        self.cliente.get('/api/v3/time')
        self.assertEqual(self.transporte.call_count,2)
        self.dormir.assert_called_once_with(.5)
        self.transporte.reset_mock(side_effect=True)
        self.transporte.side_effect = requests.ConnectionError()
        with self.assertRaises(mercado.ErrorMercado):
            self.cliente.get('/api/v3/time')
        self.assertEqual(self.transporte.call_count,2)

    def test_5xx_reintenta_una_vez_y_cierra(self):
        primero, segundo = respuesta(502), respuesta(503)
        self.transporte.side_effect = [primero, segundo]
        with self.assertRaisesRegex(mercado.ErrorMercado,'503'):
            self.cliente.get('/api/v3/time')
        primero.close.assert_called_once()
        segundo.close.assert_called_once()
        self.assertEqual(self.transporte.call_count,2)

    def test_4xx_y_redirect_no_reintentan(self):
        for status in (400, 401, 404, 301, 302):
            self.transporte.reset_mock()
            self.transporte.return_value = respuesta(status)
            with self.subTest(status=status), self.assertRaises(mercado.ErrorMercado):
                self.cliente.get('/api/v3/time')
            self.transporte.assert_called_once()

    def test_json_invalido_error_remoto_y_tipo(self):
        casos = [respuesta(datos={'code':-1121,'msg':'error'}), respuesta(datos='texto')]
        roto = respuesta()
        roto.json.side_effect = ValueError('JSON')
        casos.append(roto)
        for r in casos:
            self.transporte.reset_mock()
            self.transporte.return_value = r
            with self.assertRaises(mercado.DatosInvalidos):
                self.cliente.get('/api/v3/time')
            self.transporte.assert_called_once()

    def test_429_persiste_y_respetado_por_cliente_nuevo(self):
        self.transporte.return_value = respuesta(429, retry='90')
        with self.assertRaises(mercado.MercadoBloqueado):
            self.cliente.get('/api/v3/time')
        self.assertEqual(json.loads(self.ruta.read_text())['hasta'],1090)
        nuevo = mercado.ClientePublico(self.ruta, self.transporte, lambda:self.reloj[0], self.dormir)
        with self.assertRaises(mercado.MercadoBloqueado):
            nuevo.get('/api/v3/time')
        self.transporte.assert_called_once()
        self.reloj[0] = 1090
        self.transporte.return_value = respuesta()
        self.assertEqual(nuevo.get('/api/v3/time'), {'serverTime':123})

    def test_418_y_403_sin_plazo_no_inventan_reanudacion(self):
        for status in (418,403):
            self.cliente.bloquear(respuesta(status))
            self.reloj[0] += 1_000_000
            with self.assertRaises(mercado.MercadoBloqueado):
                self.cliente.get('/api/v3/time')
        self.transporte.assert_not_called()

    def test_retry_after_invalido_bloquea(self):
        for retry in ('NaN','Infinity','-1','0','texto'):
            with self.subTest(retry=retry):
                self.cliente.bloquear(respuesta(429,retry=retry))
                self.assertIsNone(json.loads(self.ruta.read_text())['hasta'])

    def test_451_persiste_sin_reanudacion_automatica(self):
        # Retry-After no transforma una restricción de acceso en permiso.
        r = respuesta(451, retry='60')
        self.transporte.return_value = r
        with self.assertRaisesRegex(mercado.MercadoBloqueado, '451'):
            self.cliente.get('/api/v3/time')
        guardado = json.loads(self.ruta.read_text())
        self.assertEqual(guardado['status'], 451)
        self.assertIsNone(guardado['hasta'])
        r.close.assert_called_once()
        self.reloj[0] += 1_000_000
        nuevo = mercado.ClientePublico(self.ruta, self.transporte, lambda:self.reloj[0], self.dormir)
        for cliente in (self.cliente, nuevo):
            with self.assertRaises(mercado.MercadoBloqueado):
                cliente.get('/api/v3/time')
        self.transporte.assert_called_once()
        self.dormir.assert_not_called()

    def test_451_sin_cabecera_no_se_reduce_por_otro_bloqueo(self):
        self.transporte.return_value = respuesta(451)
        with self.assertRaises(mercado.MercadoBloqueado):
            self.cliente.get('/api/v3/time')
        self.cliente.bloquear(respuesta(429, retry='1'))
        self.assertIsNone(json.loads(self.ruta.read_text())['hasta'])
        self.reloj[0] += 1_000_000
        nuevo = mercado.ClientePublico(self.ruta, self.transporte, lambda:self.reloj[0], self.dormir)
        with self.assertRaises(mercado.MercadoBloqueado):
            nuevo.get('/api/v3/exchangeInfo')
        self.transporte.assert_called_once()

    def test_bloqueo_corto_no_reduce_anterior(self):
        self.cliente.bloquear(respuesta(429,retry='300'))
        self.cliente.bloquear(respuesta(429,retry='1'))
        self.assertEqual(json.loads(self.ruta.read_text())['hasta'],1300)

    def test_clientes_concurrentes_preservan_bloqueo_mayor(self):
        def bloquear(segundos):
            otro = mercado.ClientePublico(self.ruta, self.transporte, lambda:1000, self.dormir)
            otro.bloquear(respuesta(429,retry=str(segundos)))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(bloquear,[300,2,50,4,500,1,90,3]))
        self.assertEqual(json.loads(self.ruta.read_text())['hasta'],1500)

    def test_fallo_persistencia_no_permite_reconsulta(self):
        with patch.object(Path,'write_text',side_effect=OSError('disco lleno')):
            with self.assertRaises(OSError):
                self.cliente.bloquear(respuesta(429,retry='60'))
        with self.assertRaises(mercado.MercadoBloqueado):
            self.cliente.get('/api/v3/time')
        self.transporte.assert_not_called()

    def test_estado_corrupto_falla_cerrado(self):
        for contenido in ('no json','[]','{}','{"hasta":"NaN"}'):
            self.ruta.write_text(contenido,encoding='utf-8')
            with self.assertRaises(mercado.MercadoBloqueado):
                self.cliente.get('/api/v3/time')
        self.transporte.assert_not_called()

    def test_cotizacion_simbolo_precio_finito(self):
        for dato in ({'symbol':'ETHUSDT','price':'100'}, {'symbol':'BTCUSDT'},
                     *({'symbol':'BTCUSDT','price':p} for p in ('NaN','inf',0,-1,True,None)), []):
            with self.subTest(dato=dato), patch.object(mercado,'get_publico',return_value=dato):
                with self.assertRaises(mercado.DatosInvalidos):
                    mercado.precio_actual('BTCUSDT')
        with patch.object(mercado,'get_publico',return_value={'symbol':'BTCUSDT','price':'123.45'}):
            self.assertEqual(mercado.precio_actual('BTCUSDT'),123.45)

    def test_scanner_descarta_no_finitos(self):
        valido = {'symbol':'BTCUSDT','lastPrice':'100','quoteVolume':'30000000','priceChangePercent':'3'}
        for campo,valor in [('lastPrice','NaN'),('quoteVolume','inf'),('priceChangePercent','NaN')]:
            with patch.object(scanner,'obtener_simbolos_validos',return_value={'BTCUSDT'}), \
                 patch.object(scanner,'get_publico',return_value=[{**valido,campo:valor}]):
                self.assertEqual(scanner.obtener_candidatos(),[])


class VelasTests(unittest.TestCase):
    def setUp(self):
        self.paso = 900_000
        self.ahora = 1_800_000_000_000
        self.df = pd.DataFrame([{'tiempo_apertura':self.ahora-(59-i)*self.paso,
            'tiempo_cierre':self.ahora-(58-i)*self.paso-1,
            'apertura':100+i*.1, 'cierre':100+i*.1+(-1)**i*.2,
            'maximo':101+i*.1,'minimo':99+i*.1,'volumen':100.} for i in range(60)])

    def analizar(self,df=None,ahora=None):
        return analysis.analizar_temporalidad(self.df if df is None else df,'15m',self.ahora if ahora is None else ahora)

    def test_ultima_cerrada_y_no_muta(self):
        original = self.df.copy(deep=True)
        resultado = self.analizar()
        self.assertEqual(resultado['vela_cierre_utc_ms'],self.ahora-1)
        self.assertEqual(resultado['precio'],self.df.iloc[-2]['cierre'])
        pd.testing.assert_frame_equal(original,self.df)

    def test_todas_cerradas_selecciona_ultima(self):
        resultado = self.analizar(ahora=self.ahora+self.paso)
        self.assertEqual(resultado['precio'],self.df.iloc[-1]['cierre'])

    def test_no_finitos_en_historia(self):
        for campo in ('apertura','maximo','minimo','cierre','volumen'):
            for malo in (float('nan'),float('inf')):
                df = self.df.copy()
                df.loc[10,campo] = malo
                with self.subTest(campo=campo,malo=malo), self.assertRaises(mercado.DatosInvalidos):
                    self.analizar(df)

    def test_ohlc_volumen_y_timestamps(self):
        for campo,malo in [('minimo',1000),('maximo',1),('volumen',-1),('cierre',0),
                          ('tiempo_apertura',1.5),('tiempo_cierre',0),('volumen',True)]:
            df = self.df.astype(object)
            df.loc[10,campo] = malo
            with self.subTest(campo=campo), self.assertRaises(mercado.DatosInvalidos):
                self.analizar(df)

    def test_huecos_duplicados_intervalo_desconocido_y_cortas(self):
        for delta in (-self.paso,self.paso,1):
            df = self.df.copy()
            df.loc[20,'tiempo_apertura'] += delta
            with self.assertRaises(mercado.DatosInvalidos):
                self.analizar(df)
        with self.assertRaises(mercado.DatosInvalidos):
            self.analizar(self.df.iloc[1:])
        with self.assertRaises(mercado.DatosInvalidos):
            analysis.analizar_temporalidad(self.df,'5m',self.ahora)

    def test_futuras_y_obsoletas_limite_exacto(self):
        with self.assertRaisesRegex(mercado.DatosInvalidos,'futura'):
            self.analizar(ahora=self.ahora-1)
        cierre = self.df.iloc[-1]['tiempo_cierre']
        self.analizar(ahora=cierre+self.paso+120000)
        with self.assertRaisesRegex(mercado.DatosInvalidos,'obsoletas'):
            self.analizar(ahora=cierre+self.paso+120001)

    def test_respuesta_klines_rechaza_estructura(self):
        for dato in ({'error':'x'},[[1,2,3]],'mal'):
            with patch.object(analysis,'get_publico',return_value=dato), self.assertRaises(mercado.DatosInvalidos):
                analysis.obtener_velas('BTCUSDT','15m')


if __name__ == '__main__':
    unittest.main()
