"""R2: todo el circuito real con HTTP sintético y SQLite temporal, sin operar."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import analysis_engine as analysis
import config
import market_http as market
import paper_monitor as monitor
import paper_report
import paper_store as store
import system_runner as runner


class PipelineTests(unittest.TestCase):
    def setUp(self):
        from test_paper_system import PaperTests
        PaperTests.setUp(self)
        self.addCleanup(lambda: PaperTests.tearDown(self))
        self.clock = 1_790_121_600.0
        self.escenario = 'sano'
        self.precio = 110.45
        self.precios_consultados = 0
        self.viva = True
        self.llamadas = []
        self.respuestas = []
        cliente = market.ClientePublico(self.root/'cooldown.json', self.http,
                                        lambda:self.clock, lambda _:None)
        self.conectar_real = sqlite3.connect
        self.red = Mock(side_effect=AssertionError('RED REAL PROHIBIDA EN R2'))
        self.claude = Mock(side_effect=AssertionError('CLAUDE PROHIBIDO EN R2'))
        for p in (patch.object(market, 'CLIENTE', cliente),
                  patch.object(analysis, 'time', SimpleNamespace(time=lambda:self.clock)),
                  patch('requests.sessions.Session.request', self.red),
                  patch('socket.create_connection', self.red),
                  patch.object(runner, 'crear_solicitud_claude', self.claude),
                  patch.object(sqlite3, 'connect', side_effect=self.conectar_temporal)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.verificar_aislamiento)

    def verificar_aislamiento(self):
        self.red.assert_not_called()
        self.claude.assert_not_called()
        for respuesta in self.respuestas:
            respuesta.close.assert_called_once()

    def conectar_temporal(self, ruta, *args, **kwargs):
        texto = str(ruta)
        if texto.startswith('file:'):
            self.assertTrue(texto.startswith(self.root.as_uri()+'/'), texto)
        else:
            self.assertTrue(Path(ruta).resolve().is_relative_to(self.root), texto)
        return self.conectar_real(ruta, *args, **kwargs)

    def velas(self, intervalo):
        paso = analysis.INTERVALOS_MS[intervalo]
        inicio = (int(self.clock*1000)//paso - 200)*paso
        if self.escenario == 'obsoleto':
            inicio -= 10*paso
        filas = []
        anterior = 100.
        for i in range(200):
            cierre = 100 + .05*i + (.5 if i % 2 else -.5)
            if self.escenario == 'bajista':
                cierre = 200-cierre
            elif self.escenario == 'sobreextendido':
                cierre = 100+.1*i
            apertura = anterior
            t = inicio+i*paso
            filas.append([t, str(apertura), str(max(apertura,cierre)+.2),
                          str(min(apertura,cierre)-.2), str(cierre), '1000',
                          t+paso-1, '100000', 50, '500', '50000', '0'])
            anterior = cierre
        if self.escenario == 'ohlc_invalido':
            filas[-1][2] = '1'
        return filas

    def http(self, url, *, params, timeout, allow_redirects):
        self.assertTrue(url.startswith(market.BASE+'/api/v3/'))
        self.assertFalse(allow_redirects)
        self.assertEqual(timeout, (5,15))
        ruta = url[len(market.BASE):]
        self.assertIn(ruta, market.PARAMETROS)
        self.llamadas.append((ruta, dict(params)))
        if ruta == '/api/v3/exchangeInfo':
            datos = {'symbols':[{'symbol':'BTCUSDT','quoteAsset':'USDT',
                                  'status':'TRADING','isSpotTradingAllowed':True}]}
        elif ruta == '/api/v3/ticker/24hr':
            datos = [{'symbol':'BTCUSDT','lastPrice':str(self.precio),
                      'priceChangePercent':'3.5','quoteVolume':'50000000'}]
        elif ruta == '/api/v3/klines':
            self.assertEqual(params['symbol'], 'BTCUSDT')
            self.assertEqual(params['limit'], 200)
            datos = self.velas(params['interval'])
            if self.escenario == 'sesion_terminada':
                self.viva = False
        elif ruta == '/api/v3/ticker/price':
            self.assertEqual(params, {'symbol':'BTCUSDT'})
            self.precios_consultados += 1
            precio = self.precio
            if self.escenario == 'precio_cambia' and self.precios_consultados > 1:
                precio *= 1.02
            datos = {'symbol':'BTCUSDT','price':str(precio)}
        else:
            self.fail('Endpoint imprevisto: '+ruta)
        respuesta = Mock(status_code=200, headers={})
        respuesta.json.return_value = datos
        self.respuestas.append(respuesta)
        return respuesta

    def escanear(self):
        with redirect_stdout(io.StringIO()):
            return runner.escanear(reglas=True, sesion_activa=lambda:self.viva)

    def operaciones(self):
        with store.conectar() as con:
            return [dict(r) for r in con.execute('SELECT * FROM paper_trades')]

    def test_datos_indicadores_plan_reglas_monitor_conciliacion(self):
        resultado = self.escanear()
        self.assertEqual(resultado['analizados'], 1)
        self.assertEqual(resultado['errores'], 0)
        self.assertTrue(resultado['decisiones_reglas'][0]['registrada'])
        self.assertEqual({p['interval'] for r,p in self.llamadas if r.endswith('/klines')}, {'15m','1h','4h'})
        self.assertEqual(self.precios_consultados, 2)  # planner + recotización antes de abrir.
        trade = self.operaciones()[0]
        self.assertLessEqual(trade['riesgo_usd'], 1+1e-8)
        with store.conectar() as con:
            solicitud = con.execute('SELECT * FROM paper_requests').fetchone()
        plan = json.loads(solicitud['plan'])
        self.assertEqual(plan['consenso'], 'ALCISTA')
        self.assertEqual(plan['estado'], 'ALCISTA MOMENTUM SANO')
        self.assertEqual(plan['origen_revision'], 'REGLAS_PAPER_V1')
        self.assertEqual(store.huella(plan), solicitud['plan_hash'])
        self.precio = trade['objetivo_precio']
        with redirect_stdout(io.StringIO()):
            self.assertEqual(monitor.revisar_operaciones()['cerradas'], 1)
        informe = paper_report.informe()
        self.assertEqual(informe['estado'], 'OK', informe['problemas'])
        self.assertGreater(informe['cuenta']['pnl_cerrado'], 0)  # Escenario construido, no rentabilidad real.
        self.assertFalse((self.root/'request.json').exists())

    def test_stop_y_limite_diario_en_ciclos_completos(self):
        for _ in range(3):
            self.precio = 110.45
            self.assertTrue(self.escanear()['decisiones_reglas'][0]['registrada'])
            self.precio = self.operaciones()[-1]['stop_precio']
            with redirect_stdout(io.StringIO()):
                self.assertEqual(monitor.revisar_operaciones()['cerradas'], 1)
        self.precio = 110.45
        decision = self.escanear()['decisiones_reglas'][0]
        self.assertFalse(decision['registrada'])
        self.assertIn('Límite diario', decision['motivo'])
        self.assertEqual(len(self.operaciones()), 3)
        self.assertEqual(paper_report.informe()['estado'], 'OK')

    def test_bajista_y_sobreextension_no_abren(self):
        for escenario in ('bajista','sobreextendido'):
            with self.subTest(escenario=escenario):
                self.escenario = escenario
                resultado = self.escanear()
                self.assertEqual(resultado['errores'], 0)
                self.assertEqual(resultado['decisiones_reglas'], [])
        self.assertEqual(self.operaciones(), [])
        self.assertEqual(self.precios_consultados, 0)

    def test_velas_invalidas_y_obsoletas_no_abren(self):
        for escenario in ('ohlc_invalido','obsoleto'):
            with self.subTest(escenario=escenario):
                self.escenario = escenario
                resultado = self.escanear()
                self.assertEqual(resultado['errores'], 1)
                self.assertEqual(resultado['decisiones_reglas'], [])
        self.assertEqual(self.operaciones(), [])

    def test_recotizacion_fuera_de_tolerancia_rechaza(self):
        self.escenario = 'precio_cambia'
        decision = self.escanear()['decisiones_reglas'][0]
        self.assertFalse(decision['registrada'])
        self.assertIn('precio cambió', decision['motivo'])
        self.assertEqual(self.operaciones(), [])

    def test_pausa_y_limite_posiciones(self):
        (self.root/'PAUSA_ENTRADAS').touch()
        decision = self.escanear()['decisiones_reglas'][0]
        self.assertFalse(decision['registrada'])
        self.assertIn('pausadas', decision['motivo'])
        (self.root/'PAUSA_ENTRADAS').unlink()  # Fixture temporal únicamente.
        with patch.object(config, 'MAX_OPERACIONES_ABIERTAS', 0):
            decision = self.escanear()['decisiones_reglas'][0]
        self.assertIn('Máximo', decision['motivo'])
        self.assertEqual(self.operaciones(), [])

    def test_fin_de_sesion_durante_datos_no_abre(self):
        self.escenario = 'sesion_terminada'
        resultado = self.escanear()
        self.assertTrue(resultado['cancelado'])
        self.assertEqual(self.operaciones(), [])
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_requests').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
