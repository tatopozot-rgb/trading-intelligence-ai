import inspect
import io
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import traceback
import unittest
import urllib.parse
from unittest.mock import patch

import binance_testnet_orders as modulo
from binance_signed import BinanceRestringido, Credenciales, ErrorBinance, RespuestaHttp, firmar
from binance_testnet_orders import (CONFIRMADA, INCIERTA, NO_ENCONTRADA, PENDIENTE_ENVIO, RECHAZADA,
    ClienteTestnet, ConciliacionPendiente, DiarioInconsistente, HostNoPermitido, OrdenInvalida,
    OrdenTestnet, exigir_testnet, main)

CLAVE_FALSA = 'CLAVETESTNETFALSA' * 3 + 'abcd'
SECRETO_FALSO = 'SECRETOTESTNETFALSO' * 3 + 'wxyz'


def respuesta(dato, status=200, cabeceras=None):
    return RespuestaHttp(status, cabeceras or {}, json.dumps(dato).encode('utf-8'))


def aceptada(orden, status='FILLED', order_id=77):
    return respuesta({'symbol': orden.simbolo, 'orderId': order_id, 'clientOrderId': orden.client_order_id,
                      'status': status, 'executedQty': orden.cantidad, 'cummulativeQuoteQty': '10.5'})


def orden(ident='ti-0001', **cambios):
    return OrdenTestnet(**{'simbolo': 'BTCUSDT', 'lado': 'BUY', 'tipo': 'MARKET', 'cantidad': '0.001',
                           'client_order_id': ident, **cambios})


class Falso:
    """Transporte en memoria con guion por (método, ruta). Nunca toca la red."""

    def __init__(self, **guion):
        self.guion = {k: list(v) for k, v in guion.items()}
        self.llamadas = []

    def __call__(self, metodo, url, cabeceras, timeout):
        partes = urllib.parse.urlsplit(url)
        self.llamadas.append((metodo, partes.path, partes.query, dict(cabeceras), url))
        if partes.path == modulo.RUTA_HORA:
            return respuesta({'serverTime': 1_700_000_000_000})
        paso = self.guion[f'{metodo}_{partes.path.rsplit("/", 1)[1]}'].pop(0)
        if isinstance(paso, Exception):
            raise paso
        return paso

    def de(self, metodo, ruta=modulo.RUTA_ORDEN):
        return [c for c in self.llamadas if c[0] == metodo and c[1] == ruta]


class TestnetOrdenesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.diario = Path(self.tmp.name) / 'diario.json'
        self.bloqueo = Path(self.tmp.name) / 'cooldown.json'
        self.ahora = 1_700_000_000.0

    def cliente(self, falso):
        return ClienteTestnet(Credenciales(CLAVE_FALSA, SECRETO_FALSO), transporte=falso,
                              reloj=lambda: self.ahora, ruta_diario=self.diario, ruta_bloqueo=self.bloqueo)

    def registro(self, ident='ti-0001'):
        return json.loads(self.diario.read_text())['ordenes'][ident]

    # --- solo Testnet ---

    def test_exigir_testnet_rechaza_cualquier_otro_host(self):
        exigir_testnet('https://testnet.binance.vision/api/v3/order?x=1')
        for url in ('https://api.binance.com/api/v3/order', 'https://api1.binance.com/api/v3/order',
                    'https://data-api.binance.vision/api/v3/order', 'http://testnet.binance.vision/api/v3/order',
                    'https://testnet.binance.vision.evil.example/api/v3/order',
                    'https://testnet.binance.vision@api.binance.com/api/v3/order',
                    'https://api.binance.com/?testnet.binance.vision', 'https://testnet.binance.vision:8443/x',
                    'https://TESTNET.binance.vision/x', '//testnet.binance.vision/x', ''):
            with self.subTest(url=url), self.assertRaises(HostNoPermitido):
                exigir_testnet(url)

    def test_orden_hacia_produccion_lanza_error_sin_tocar_la_red_ni_el_exchange(self):
        o = orden()
        for host in ('https://api.binance.com', 'https://testnet.binance.vision.evil.example'):
            with self.subTest(host=host):
                self.diario.unlink(missing_ok=True)
                falso = Falso(POST_order=[aceptada(o)])
                with patch.object(modulo, 'TESTNET', host), self.assertRaises(HostNoPermitido):
                    self.cliente(falso).enviar(o)
                self.assertEqual(falso.llamadas, [])
        with self.assertRaises(HostNoPermitido):
            modulo.transporte_urllib('POST', 'https://api.binance.com/api/v3/order', {}, 1)
        with self.assertRaises(HostNoPermitido):
            modulo.transporte_urllib('DELETE', 'https://testnet.binance.vision/api/v3/order', {}, 1)

    def test_no_existe_opcion_para_cambiar_de_host(self):
        for objeto in (ClienteTestnet.__init__, ClienteTestnet.desde_entorno, main):
            for nombre in inspect.signature(objeto).parameters:
                self.assertNotRegex(nombre.lower(), 'host|url|base|produccion|live|real')
        fuente = inspect.getsource(modulo)
        self.assertNotIn('api.binance.com', fuente)
        self.assertNotIn('environ.get', fuente)
        self.assertEqual(modulo.PETICIONES, {('GET', '/api/v3/time'), ('GET', '/api/v3/account'),
                                             ('GET', '/api/v3/order'), ('POST', '/api/v3/order')})
        with self.assertRaises(ValueError):
            self.cliente(Falso())._enviar('POST', '/sapi/v1/capital/withdraw/apply', '', {})

    # --- envío ---

    def test_envio_confirmado_firma_la_query_exacta_y_va_a_testnet(self):
        o = orden()
        falso = Falso(POST_order=[aceptada(o)])
        registro = self.cliente(falso).enviar(o)
        self.assertEqual((registro['estado'], registro['order_id'], registro['estado_exchange']),
                         (CONFIRMADA, 77, 'FILLED'))
        (metodo, ruta, query, cabeceras, url), = falso.de('POST')
        self.assertTrue(url.startswith('https://testnet.binance.vision/api/v3/order?'))
        self.assertEqual(cabeceras, {'X-MBX-APIKEY': CLAVE_FALSA})
        sin_firma, firma = query.rsplit('&signature=', 1)
        self.assertEqual(firma, firmar(SECRETO_FALSO, sin_firma))
        self.assertEqual(dict(urllib.parse.parse_qsl(sin_firma)), {'symbol': 'BTCUSDT', 'side': 'BUY',
            'type': 'MARKET', 'quantity': '0.001', 'newClientOrderId': 'ti-0001',
            'newOrderRespType': 'RESULT', 'recvWindow': '5000', 'timestamp': '1700000000000'})
        self.assertEqual(self.registro()['estado'], CONFIRMADA)

    def test_limit_lleva_precio_y_gtc(self):
        o = orden(tipo='LIMIT', precio='25000.10')
        falso = Falso(POST_order=[aceptada(o, status='NEW')])
        self.cliente(falso).enviar(o)
        params = dict(urllib.parse.parse_qsl(falso.de('POST')[0][2]))
        self.assertEqual((params['price'], params['timeInForce']), ('25000.10', 'GTC'))

    def test_ordenes_invalidas_no_llegan_al_diario_ni_a_la_red(self):
        falso = Falso()
        cliente = self.cliente(falso)
        malas = [orden(simbolo='btcusdt'), orden(simbolo='BTC/USDT'), orden(lado='LONG'), orden(tipo='STOP'),
                 orden(cantidad='0'), orden(cantidad='0.000'), orden(cantidad='-1'), orden(cantidad='1e3'),
                 orden(cantidad=0.001), orden(cantidad='NaN'), orden(cantidad='1&side=SELL'),
                 orden(precio='100'), orden(tipo='LIMIT'), orden(tipo='LIMIT', precio='0'),
                 orden(ident=''), orden(ident='a' * 37), orden(ident='x&symbol=ETHUSDT'), orden(ident=None)]
        for mala in malas:
            with self.subTest(mala=mala), self.assertRaises(OrdenInvalida):
                cliente.enviar(mala)
        self.assertEqual(falso.llamadas, [])
        self.assertFalse(self.diario.exists())

    def test_el_intento_se_anota_antes_de_enviar(self):
        o = orden()
        vistos = []

        class Espia(Falso):
            def __call__(espia, metodo, url, cabeceras, timeout):
                if metodo == 'POST':
                    vistos.append(self.registro()['estado'])
                return super().__call__(metodo, url, cabeceras, timeout)

        self.cliente(Espia(POST_order=[aceptada(o)])).enviar(o)
        self.assertEqual(vistos, [PENDIENTE_ENVIO])

    def test_si_el_diario_no_se_puede_escribir_la_orden_no_sale(self):
        falso = Falso(POST_order=[aceptada(orden())])
        cliente = self.cliente(falso)
        with patch.object(modulo.Diario, 'guardar', side_effect=OSError('disco')), self.assertRaises(OSError):
            cliente.enviar(orden())
        self.assertEqual(falso.de('POST'), [])

    def test_rechazo_definitivo_no_queda_pendiente(self):
        falso = Falso(POST_order=[respuesta({'code': -2010, 'msg': 'insufficient balance'}, 400)])
        registro = self.cliente(falso).enviar(orden())
        self.assertEqual((registro['estado'], registro['codigo']), (RECHAZADA, -2010))
        self.assertEqual(self.cliente(falso).sin_conciliar(), [])

    def test_un_client_order_id_nunca_se_reenvia_en_ningun_estado(self):
        o = orden()
        for primera in (aceptada(o), respuesta({'code': -2010, 'msg': 'x'}, 400), TimeoutError('t')):
            with self.subTest(primera=primera):
                self.diario.unlink(missing_ok=True)
                falso = Falso(POST_order=[primera, aceptada(o)])
                cliente = self.cliente(falso)
                cliente.enviar(o)
                with self.assertRaises(OrdenInvalida):
                    cliente.enviar(o)
                with self.assertRaises(OrdenInvalida):
                    self.cliente(falso).enviar(o)  # tras reinicio
                self.assertEqual(len(falso.de('POST')), 1)

    # --- respuestas inciertas ---

    def inciertas(self, o):
        return [TimeoutError('t'), ConnectionResetError('c'), respuesta({}, 500), respuesta({}, 503),
                respuesta({'code': -1000}, 504), RespuestaHttp(200, {}, b'<html>'), respuesta([], 200),
                respuesta({'orderId': 1}, 200), aceptada(orden('otra')), aceptada(orden(simbolo='ETHUSDT')),
                respuesta({'msg': 'sin codigo'}, 400), respuesta({'code': 'x'}, 400), respuesta({}, 302),
                respuesta({}, 429, {'Retry-After': '1'}), respuesta({}, 418), respuesta({}, 403),
                respuesta({'code': -1003, 'msg': 'x'}, 429), respuesta({'code': -2015, 'msg': 'x'}, 403),
                respuesta({'symbol': o.simbolo, 'clientOrderId': o.client_order_id, 'status': 'FILLED'}),
                respuesta({'symbol': o.simbolo, 'clientOrderId': o.client_order_id, 'status': 'FILLED',
                           'orderId': '77'}),
                respuesta({'symbol': o.simbolo, 'clientOrderId': o.client_order_id, 'orderId': 77})]

    def test_respuesta_incierta_no_se_reintenta_y_bloquea_nuevas_ordenes(self):
        o = orden()
        for incierta in self.inciertas(o):
            with self.subTest(incierta=incierta):
                self.diario.unlink(missing_ok=True)
                self.bloqueo.unlink(missing_ok=True)
                falso = Falso(POST_order=[incierta, aceptada(o), aceptada(o)])
                cliente = self.cliente(falso)
                self.assertEqual(cliente.enviar(o)['estado'], INCIERTA)
                self.assertEqual(len(falso.de('POST')), 1)
                self.assertEqual(cliente.sin_conciliar(), ['ti-0001'])
                for otro in (cliente, self.cliente(falso)):
                    with self.assertRaises(ConciliacionPendiente):
                        otro.enviar(orden('ti-0002'))
                self.assertEqual(len(falso.de('POST')), 1)

    def test_incierta_se_concilia_por_client_order_id_y_resulta_ejecutada(self):
        o = orden()
        falso = Falso(POST_order=[TimeoutError('t'), aceptada(orden('ti-0002'))], GET_order=[aceptada(o)])
        cliente = self.cliente(falso)
        cliente.enviar(o)
        self.assertEqual(cliente.conciliar(), {'ti-0001': CONFIRMADA})
        (_, _, query, _, _), = falso.de('GET')
        params = dict(urllib.parse.parse_qsl(query))
        self.assertEqual((params['symbol'], params['origClientOrderId']), ('BTCUSDT', 'ti-0001'))
        self.assertEqual(self.registro()['order_id'], 77)
        self.assertEqual(len(falso.de('POST')), 1)  # conciliar nunca reenvía
        self.assertEqual(cliente.enviar(orden('ti-0002'))['estado'], CONFIRMADA)

    def test_no_existe_solo_es_definitivo_pasado_el_plazo_y_tampoco_reenvia(self):
        o = orden()
        inexistente = respuesta({'code': -2013, 'msg': 'Order does not exist.'}, 400)
        falso = Falso(POST_order=[TimeoutError('t')], GET_order=[inexistente, inexistente])
        cliente = self.cliente(falso)
        cliente.enviar(o)
        self.ahora += modulo.ESPERA_MINIMA_CONCILIACION_SEG - 1
        self.assertEqual(cliente.conciliar(), {'ti-0001': INCIERTA})
        self.ahora += 1
        self.assertEqual(cliente.conciliar(), {'ti-0001': NO_ENCONTRADA})
        self.assertEqual(len(falso.de('POST')), 1)
        with self.assertRaises(OrdenInvalida):
            cliente.enviar(o)

    def test_conciliacion_que_no_se_entiende_sigue_incierta(self):
        o = orden()
        for dudosa in (TimeoutError('t'), respuesta({}, 500), respuesta({'code': -1021}, 400),
                       aceptada(orden('otra')), aceptada(orden(simbolo='ETHUSDT')), respuesta({}, 200),
                       respuesta({'code': -2013}, 404), respuesta({}, 429, {'Retry-After': '1'})):
            with self.subTest(dudosa=dudosa):
                self.diario.unlink(missing_ok=True)
                self.bloqueo.unlink(missing_ok=True)
                falso = Falso(POST_order=[TimeoutError('t')], GET_order=[dudosa])
                cliente = self.cliente(falso)
                cliente.enviar(o)
                self.ahora += 60
                self.assertEqual(cliente.conciliar(), {'ti-0001': INCIERTA})
                with self.assertRaises(ConciliacionPendiente):
                    cliente.enviar(orden('ti-0002'))

    # --- reinicio ---

    def test_caida_entre_anotar_y_enviar_se_trata_como_incierta_tras_reiniciar(self):
        o = orden()

        class Caida(BaseException):
            pass

        class Muere(Falso):
            def __call__(self, metodo, url, cabeceras, timeout):
                if metodo == 'POST':
                    raise Caida()
                return super().__call__(metodo, url, cabeceras, timeout)

        with self.assertRaises(Caida):
            self.cliente(Muere()).enviar(o)
        self.assertEqual(self.registro()['estado'], PENDIENTE_ENVIO)
        falso = Falso(POST_order=[aceptada(orden('ti-0002'))], GET_order=[aceptada(o, order_id=91)])
        reiniciado = self.cliente(falso)
        self.assertEqual(reiniciado.sin_conciliar(), ['ti-0001'])
        with self.assertRaises(ConciliacionPendiente):
            reiniciado.enviar(orden('ti-0002'))
        with self.assertRaises(OrdenInvalida):
            reiniciado.enviar(o)
        self.assertEqual(falso.de('POST'), [])
        self.assertEqual(reiniciado.conciliar(), {'ti-0001': CONFIRMADA})
        self.assertEqual(self.registro()['order_id'], 91)
        self.assertEqual(reiniciado.enviar(orden('ti-0002'))['estado'], CONFIRMADA)

    def test_reinicio_conserva_incierta_y_confirmadas(self):
        falso = Falso(POST_order=[aceptada(orden()), respuesta({}, 502)], GET_order=[aceptada(orden('ti-0002'))])
        primero = self.cliente(falso)
        primero.enviar(orden())
        primero.enviar(orden('ti-0002'))
        reiniciado = self.cliente(falso)
        self.assertEqual(reiniciado.sin_conciliar(), ['ti-0002'])
        self.assertEqual(reiniciado.conciliar(), {'ti-0002': CONFIRMADA})
        self.assertEqual(reiniciado.conciliar(), {})
        self.assertEqual(len(falso.de('GET')), 1)

    def test_diario_ilegible_o_alterado_impide_enviar_y_conciliar(self):
        for contenido in ('{corrupto', '[]', json.dumps({'schema': 'OTRO', 'ordenes': {}}),
                          json.dumps({'schema': modulo.ESQUEMA, 'ordenes': []}),
                          json.dumps({'schema': modulo.ESQUEMA, 'ordenes': {'a': {'estado': 'INVENTADO',
                              'simbolo': 'BTCUSDT', 'creado_epoch': 1}}}),
                          json.dumps({'schema': modulo.ESQUEMA, 'ordenes': {'a': {'estado': INCIERTA}}})):
            with self.subTest(contenido=contenido):
                self.diario.write_text(contenido, encoding='utf-8')
                falso = Falso(POST_order=[aceptada(orden())])
                cliente = self.cliente(falso)
                for accion in (lambda: cliente.enviar(orden()), cliente.conciliar, cliente.sin_conciliar):
                    with self.assertRaises(DiarioInconsistente):
                        accion()
                self.assertEqual(falso.llamadas, [])

    # --- un único escritor del diario (revisión de GPT Work sobre 3ec14f5) ---

    def test_dos_instancias_en_carrera_solo_envian_una_orden(self):
        a_en_reserva, b_termino, resultado_b = threading.Event(), threading.Event(), {}
        hilo_a = threading.current_thread()
        lecturas_de_a = []
        leer_original = modulo.Diario.leer

        def leer_con_pausa(diario):
            ordenes = leer_original(diario)
            if threading.current_thread() is hilo_a:
                lecturas_de_a.append(1)
                if len(lecturas_de_a) == 2:  # la lectura de la reserva: A ya leyó "vacío" y aún no anotó
                    a_en_reserva.set()
                    b_termino.wait(1.0)
            return ordenes

        class PostLento(Falso):
            def __call__(self, metodo, url, cabeceras, timeout):
                if metodo == 'POST' and 'ti-A' in url:
                    b_termino.wait(10)  # A sigue PENDIENTE_ENVIO mientras B decide
                return super().__call__(metodo, url, cabeceras, timeout)

        falso = PostLento(POST_order=[aceptada(orden('ti-A')), aceptada(orden('ti-B'))])
        cliente_a, cliente_b = self.cliente(falso), self.cliente(falso)
        for cliente in (cliente_a, cliente_b):
            cliente._preparar()  # hora ya sincronizada: la carrera queda sólo en el diario

        def enviar_b():
            a_en_reserva.wait(10)
            try:
                resultado_b['registro'] = cliente_b.enviar(orden('ti-B'))
            except Exception as error:  # noqa: BLE001
                resultado_b['error'] = error
            b_termino.set()

        hilo_b = threading.Thread(target=enviar_b)
        with patch.object(modulo.Diario, 'leer', leer_con_pausa):
            hilo_b.start()
            registro_a = cliente_a.enviar(orden('ti-A'))
            hilo_b.join(20)
        self.assertFalse(hilo_b.is_alive())
        self.assertEqual(registro_a['estado'], CONFIRMADA)
        self.assertIsInstance(resultado_b.get('error'), ConciliacionPendiente)
        self.assertEqual([dict(urllib.parse.parse_qsl(c[2]))['newClientOrderId'] for c in falso.de('POST')], ['ti-A'])
        diario = json.loads(self.diario.read_text())['ordenes']
        self.assertEqual({k: v['estado'] for k, v in diario.items()}, {'ti-A': CONFIRMADA})

    def test_guardar_un_resultado_no_pisa_lo_que_otro_proceso_escribio(self):
        o = orden()
        otro = modulo.Diario(self.diario)

        class EscribeDurantePost(Falso):
            def __call__(self, metodo, url, cabeceras, timeout):
                if metodo == 'POST':
                    with otro.exclusivo():
                        ordenes = otro.leer()
                        ordenes['ajena'] = {'estado': RECHAZADA, 'simbolo': 'ETHUSDT', 'creado_epoch': 1.0}
                        otro.guardar(ordenes)
                return super().__call__(metodo, url, cabeceras, timeout)

        self.cliente(EscribeDurantePost(POST_order=[aceptada(o)])).enviar(o)
        diario = json.loads(self.diario.read_text())['ordenes']
        self.assertEqual({k: v['estado'] for k, v in diario.items()}, {'ti-0001': CONFIRMADA, 'ajena': RECHAZADA})

    def test_conciliar_no_degrada_un_resultado_que_otro_proceso_ya_anoto(self):
        o = orden()
        otro = modulo.Diario(self.diario)

        class ResuelveDuranteConsulta(Falso):
            def __call__(self, metodo, url, cabeceras, timeout):
                if metodo == 'GET' and url.split('?')[0].endswith('/order'):
                    with otro.exclusivo():
                        ordenes = otro.leer()
                        ordenes['ti-0001'].update(estado=CONFIRMADA, order_id=55, estado_exchange='FILLED')
                        otro.guardar(ordenes)
                return super().__call__(metodo, url, cabeceras, timeout)

        falso = ResuelveDuranteConsulta(POST_order=[TimeoutError('t')], GET_order=[respuesta({}, 500)])
        cliente = self.cliente(falso)
        cliente.enviar(o)
        self.assertEqual(cliente.conciliar(), {'ti-0001': CONFIRMADA})
        self.assertEqual(self.registro()['order_id'], 55)

    def test_envio_incierto_no_degrada_lo_que_un_conciliador_ya_anoto(self):
        # Carrera emisor-conciliador: A suelta el bloqueo durante un POST lento; B concilia y anota
        # el resultado definitivo; después A recibe un timeout. El diario conserva lo definitivo.
        o = orden()
        for definitiva, esperado in ((aceptada(o, order_id=91), CONFIRMADA),
                                     (respuesta({'code': -2013, 'msg': 'x'}, 400), NO_ENCONTRADA)):
            with self.subTest(esperado=esperado):
                self.diario.unlink(missing_ok=True)
                conciliado = {}

                class PostLento(Falso):
                    def __call__(falso, metodo, url, cabeceras, timeout):
                        if metodo == 'POST':
                            falso.llamadas.append(('POST', modulo.RUTA_ORDEN, urllib.parse.urlsplit(url).query,
                                                   dict(cabeceras), url))
                            self.ahora += 60
                            conciliado.update(self.cliente(falso).conciliar())
                            raise TimeoutError('respuesta perdida')
                        return super().__call__(metodo, url, cabeceras, timeout)

                falso = PostLento(GET_order=[definitiva])
                registro = self.cliente(falso).enviar(o)
                self.assertEqual(conciliado, {'ti-0001': esperado})
                self.assertEqual(registro['estado'], esperado)
                self.assertEqual(self.registro()['estado'], esperado)
                self.assertEqual(len(falso.de('POST')), 1)
                self.assertEqual(self.cliente(falso).sin_conciliar(), [])

    def test_las_transiciones_del_diario_son_monotonas(self):
        cliente = self.cliente(Falso())
        base = {'simbolo': 'BTCUSDT', 'creado_epoch': 1.0}
        for definitivo in (CONFIRMADA, RECHAZADA, NO_ENCONTRADA):
            for intento in (INCIERTA, PENDIENTE_ENVIO, CONFIRMADA, RECHAZADA, NO_ENCONTRADA):
                with self.subTest(definitivo=definitivo, intento=intento):
                    modulo.Diario(self.diario).guardar({'x': {**base, 'estado': definitivo, 'marca': 'original'}})
                    vigente = cliente._actualizar('x', {**base, 'estado': intento})
                    self.assertEqual((vigente['estado'], vigente.get('marca')), (definitivo, 'original'))
                    self.assertEqual(self.registro('x')['marca'], 'original')
        for previo in (PENDIENTE_ENVIO, INCIERTA):
            for nuevo in (INCIERTA, CONFIRMADA, RECHAZADA, NO_ENCONTRADA):
                modulo.Diario(self.diario).guardar({'x': {**base, 'estado': previo}})
                self.assertEqual(cliente._actualizar('x', {**base, 'estado': nuevo})['estado'], nuevo)
                self.assertEqual(self.registro('x')['estado'], nuevo)

    def test_si_no_se_obtiene_el_bloqueo_del_diario_no_se_envia(self):
        falso = Falso(POST_order=[aceptada(orden())])
        cliente = self.cliente(falso)
        objetivo = 'msvcrt.locking' if os.name == 'nt' else 'fcntl.flock'
        with patch(objetivo, side_effect=OSError('ocupado')), self.assertRaises(DiarioInconsistente):
            cliente.enviar(orden())
        self.assertEqual(falso.de('POST'), [])
        self.assertFalse(self.diario.exists())

    # --- restricciones y redacción ---

    def test_restriccion_bloquea_envios_posteriores_sin_tocar_la_red(self):
        falso = Falso(POST_order=[respuesta({'code': -2010}, 400), respuesta({}, 429, {'Retry-After': '30'})])
        cliente = self.cliente(falso)
        cliente.enviar(orden())
        self.assertEqual(cliente.enviar(orden('ti-0002'))['estado'], INCIERTA)
        antes = len(falso.llamadas)
        with self.assertRaises(BinanceRestringido):
            cliente.conciliar()
        with self.assertRaises(BinanceRestringido):
            self.cliente(falso).cuenta()
        self.assertEqual(len(falso.llamadas), antes)

    def test_bloqueo_previo_impide_enviar_y_no_quema_el_identificador(self):
        self.bloqueo.write_text(json.dumps({'hasta': None}), encoding='utf-8')
        falso = Falso(POST_order=[aceptada(orden())])
        with self.assertRaises(BinanceRestringido):
            self.cliente(falso).enviar(orden())
        self.assertEqual(falso.llamadas, [])
        self.assertFalse(self.diario.exists())

    def test_ningun_error_log_ni_diario_contiene_clave_secreto_o_firma(self):
        class Chivato(Falso):
            def __call__(self, metodo, url, cabeceras, timeout):
                partes = urllib.parse.urlsplit(url)
                self.llamadas.append((metodo, partes.path, partes.query, dict(cabeceras), url))
                if partes.path == modulo.RUTA_HORA:
                    return respuesta({'serverTime': 1_700_000_000_000})
                if self.modo == 'excepcion':
                    raise RuntimeError(f'fallo en {url} con {cabeceras} y {SECRETO_FALSO}')
                return respuesta({'code': -2015, 'msg': f'{url} {cabeceras}'}, self.modo)

        for modo in ('excepcion', 400, 401, 429, 500):
            with self.subTest(modo=modo):
                self.diario.unlink(missing_ok=True)
                self.bloqueo.unlink(missing_ok=True)
                falso = Chivato()
                falso.modo = modo
                cliente = self.cliente(falso)
                registro = io.StringIO()
                manejador = logging.StreamHandler(registro)
                raiz = logging.getLogger()
                nivel = raiz.level
                raiz.addHandler(manejador)
                raiz.setLevel(logging.DEBUG)
                textos = []
                try:
                    textos.append(repr(cliente.enviar(orden())))
                    for accion in (cliente.conciliar, cliente.cuenta):
                        try:
                            textos.append(repr(accion()))
                        except ErrorBinance as error:
                            self.assertIsNone(error.__context__)
                            textos.append(''.join(traceback.format_exception(error)))
                finally:
                    raiz.removeHandler(manejador)
                    raiz.setLevel(nivel)
                textos += [registro.getvalue(), self.diario.read_text(), repr(cliente), repr(vars(cliente)),
                           self.bloqueo.read_text() if self.bloqueo.exists() else '']
                firmas = [c[2].rsplit('signature=', 1)[1] for c in falso.llamadas if 'signature=' in c[2]]
                self.assertTrue(firmas)
                for secreto in (CLAVE_FALSA, SECRETO_FALSO, *firmas):
                    for texto in textos:
                        self.assertNotIn(secreto, texto)

    # --- comando del dueño ---

    def test_comando_no_envia_ordenes_y_espera_al_dueno_sin_variables(self):
        salida = io.StringIO()
        falso = Falso(GET_account=[respuesta({'balances': [{'asset': 'A', 'free': '1', 'locked': '0'}]})])
        self.assertEqual(main([], entorno={}, salida=salida, transporte=falso), 2)
        self.assertIn('WAITING_FOR_USER', salida.getvalue())
        self.assertIn('BINANCE_TESTNET_API_KEY', salida.getvalue())
        self.assertEqual(falso.llamadas, [])
        salida = io.StringIO()
        entorno = {'BINANCE_TESTNET_API_KEY': CLAVE_FALSA, 'BINANCE_TESTNET_SECRET_KEY': SECRETO_FALSO,
                   'BINANCE_READONLY_API_KEY': 'NOUSARNUNCAESTACLAVE1234', 'BINANCE_READONLY_SECRET_KEY': 'X' * 30}
        self.assertEqual(main([], entorno=entorno, salida=salida, transporte=falso,
                              ruta_diario=self.diario, ruta_bloqueo=self.bloqueo), 0)
        texto = salida.getvalue()
        self.assertIn('Conectado: SI', texto)
        self.assertIn('Activos ficticios con saldo: 1', texto)
        self.assertEqual(falso.de('POST'), [])
        self.assertEqual(falso.de('GET', '/api/v3/account')[0][3], {'X-MBX-APIKEY': CLAVE_FALSA})
        for secreto in (CLAVE_FALSA, SECRETO_FALSO):
            self.assertNotIn(secreto, texto)
        self.assertEqual(main(['--orden'], entorno=entorno, salida=io.StringIO(), transporte=falso), 2)


if __name__ == '__main__':
    unittest.main()
