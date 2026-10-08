import inspect
import io
import json
import logging
from pathlib import Path
import pickle
import tempfile
import traceback
import unittest
import urllib.parse

import binance_signed
from binance_signed import (BinanceRestringido, ClienteLectura, CredencialRechazada, Credenciales,
    CredencialesAusentes, ErrorBinance, PermisosInseguros, RespuestaHttp, activos_con_saldo,
    evaluar_restricciones, firmar, main)

# Ejemplo PÚBLICO de la documentación oficial de Binance (SIGNED endpoint, HMAC SHA256).
# No son credenciales reales de nadie.
CLAVE_DOC = 'vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A'
SECRETO_DOC = 'NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j'
QUERY_DOC = ('symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1'
             '&recvWindow=5000&timestamp=1499827319559')
FIRMA_DOC = 'c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71'

# Valores falsos para el resto de pruebas.
CLAVE_FALSA = 'CLAVEFALSA' * 6 + 'abcd'
SECRETO_FALSO = 'SECRETOFALSO' * 5 + 'wxyz'
SOLO_LECTURA = dict(ipRestrict=True, createTime=1, enableReading=True, enableWithdrawals=False,
    enableSpotAndMarginTrading=False, enableInternalTransfer=False, enableMargin=False,
    enableFutures=False, permitsUniversalTransfer=False, enableVanillaOptions=False)
CUENTA = dict(canTrade=True, balances=[dict(asset='AAA', free='1.5', locked='0'),
    dict(asset='BBB', free='0', locked='0.2'), dict(asset='CCC', free='0', locked='0.00000000')])


def respuesta(dato, status=200, cabeceras=None):
    return RespuestaHttp(status, cabeceras or {}, json.dumps(dato).encode('utf-8'))


class Falso:
    """Transporte en memoria: nunca toca la red."""

    def __init__(self, rutas=None, hora=1_700_000_000_000):
        self.rutas = dict(rutas or {})
        self.hora = hora
        self.llamadas = []

    def __call__(self, url, cabeceras, timeout):
        partes = urllib.parse.urlsplit(url)
        self.llamadas.append((partes.path, partes.query, dict(cabeceras), url))
        if partes.path == binance_signed.RUTA_HORA:
            return respuesta({'serverTime': self.hora})
        guion = self.rutas[partes.path]
        paso = guion.pop(0) if type(guion) is list else guion
        if isinstance(paso, Exception):
            raise paso
        return paso

    def firmadas(self):
        return [c for c in self.llamadas if c[0] != binance_signed.RUTA_HORA]


class BinanceSignedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bloqueo = Path(self.tmp.name) / 'cooldown.json'
        self.ahora = 1_700_000_000.0
        self.credenciales = Credenciales(CLAVE_FALSA, SECRETO_FALSO)

    def cliente(self, transporte):
        return ClienteLectura(self.credenciales, transporte=transporte, reloj=lambda: self.ahora,
                              dormir=lambda s: None, ruta_bloqueo=self.bloqueo)

    def verificado(self, **rutas):
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: respuesta(SOLO_LECTURA), **rutas})
        cliente = self.cliente(falso)
        cliente.verificar_permisos()
        return cliente, falso

    # --- firma ---

    def test_firma_coincide_con_ejemplo_oficial(self):
        self.assertEqual(firmar(SECRETO_DOC, QUERY_DOC), FIRMA_DOC)
        self.assertEqual(Credenciales(CLAVE_DOC, SECRETO_DOC).firmar(QUERY_DOC), FIRMA_DOC)

    def test_peticion_firmada_lleva_timestamp_recvwindow_cabecera_y_firma_de_la_query_exacta(self):
        cliente, falso = self.verificado(**{'/api/v3/account': respuesta(CUENTA)})
        falso.hora = 1_700_000_000_000 + 0  # desfase calculado en la primera sincronización
        cliente.cuenta()
        _, query, cabeceras, url = falso.firmadas()[-1]
        self.assertTrue(url.startswith('https://api.binance.com/api/v3/account?'))
        self.assertEqual(cabeceras, {'X-MBX-APIKEY': CLAVE_FALSA})
        sin_firma, firma = query.rsplit('&signature=', 1)
        self.assertEqual(firma, firmar(SECRETO_FALSO, sin_firma))
        params = dict(urllib.parse.parse_qsl(sin_firma))
        self.assertEqual(params, {'omitZeroBalances': 'true', 'recvWindow': '5000',
                                  'timestamp': '1700000000000'})

    def test_timestamp_usa_la_hora_del_servidor_y_la_hora_se_pide_sin_clave(self):
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: respuesta(SOLO_LECTURA)},
                      hora=1_700_000_000_000 + 7_000)
        self.cliente(falso).verificar_permisos()
        self.assertEqual(falso.llamadas[0][0], binance_signed.RUTA_HORA)
        self.assertEqual(falso.llamadas[0][2], {})
        self.assertIn('timestamp=1700000007000', falso.firmadas()[0][1])

    def test_hora_fuera_de_ventana_resincroniza_una_sola_vez(self):
        fuera = respuesta({'code': -1021, 'msg': 'x'}, 400)
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: [fuera, respuesta(SOLO_LECTURA)]})
        self.cliente(falso).verificar_permisos()
        self.assertEqual([c[0] for c in falso.llamadas].count(binance_signed.RUTA_HORA), 2)
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: [fuera, fuera, fuera]})
        with self.assertRaises(ErrorBinance):
            self.cliente(falso).verificar_permisos()
        self.assertEqual(len(falso.firmadas()), 2)

    # --- guardia de permisos ---

    def test_guardia_acepta_solo_lectura(self):
        permisos = evaluar_restricciones(dict(SOLO_LECTURA))
        self.assertEqual((permisos.lectura, permisos.trading, permisos.retiros, permisos.restriccion_ip),
                         (True, False, False, True))

    def test_guardia_rechaza_retiros_trading_o_indeterminado(self):
        malos = [dict(SOLO_LECTURA, enableWithdrawals=True), dict(SOLO_LECTURA, enableWithdrawals='false'),
                 dict(SOLO_LECTURA, enableWithdrawals=0), dict(SOLO_LECTURA, enableWithdrawals=None),
                 dict(SOLO_LECTURA, enableSpotAndMarginTrading=True),
                 dict(SOLO_LECTURA, enableSpotAndMarginTrading=None),
                 dict(SOLO_LECTURA, enableReading=False), dict(SOLO_LECTURA, ipRestrict='si'),
                 dict(SOLO_LECTURA, enableInternalTransfer=True),
                 dict(SOLO_LECTURA, permitsUniversalTransfer=True),
                 dict(SOLO_LECTURA, enableMargin=True), dict(SOLO_LECTURA, enableFutures=True),
                 dict(SOLO_LECTURA, enablePermisoNuevo=True), dict(SOLO_LECTURA, enableFutures='x'),
                 dict(SOLO_LECTURA, enableFutures=None), dict(SOLO_LECTURA, permitsOtro=0),
                 [], None, 'texto', {}]
        for quitar in ('enableWithdrawals', 'enableSpotAndMarginTrading', 'enableReading', 'ipRestrict'):
            malos.append({k: v for k, v in SOLO_LECTURA.items() if k != quitar})
        for malo in malos:
            with self.subTest(malo=malo), self.assertRaises(PermisosInseguros):
                evaluar_restricciones(malo)

    def test_sin_guardia_no_se_lee_la_cuenta_ni_se_toca_la_red(self):
        falso = Falso()
        cliente = self.cliente(falso)
        for lectura in (cliente.cuenta, cliente.ordenes_abiertas, lambda: cliente.mis_trades('AAAUSDT')):
            with self.assertRaises(PermisosInseguros):
                lectura()
        self.assertEqual(falso.llamadas, [])

    def test_guardia_fallida_o_no_consultable_bloquea_las_lecturas(self):
        casos = [respuesta(dict(SOLO_LECTURA, enableWithdrawals=True)),
                 respuesta({'code': -2015, 'msg': 'x'}, 400), respuesta('no json', 200),
                 RespuestaHttp(200, {}, b'<html>')]
        for caso in casos:
            with self.subTest(caso=caso.cuerpo):
                falso = Falso({binance_signed.RUTA_RESTRICCIONES: caso, '/api/v3/account': respuesta(CUENTA)})
                cliente = self.cliente(falso)
                with self.assertRaises(ErrorBinance):
                    cliente.verificar_permisos()
                with self.assertRaises(PermisosInseguros):
                    cliente.cuenta()
                self.assertNotIn('/api/v3/account', [c[0] for c in falso.llamadas])

    def test_una_guardia_superada_se_invalida_si_la_siguiente_falla(self):
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: [
            respuesta(SOLO_LECTURA), respuesta(dict(SOLO_LECTURA, enableWithdrawals=True))]})
        cliente = self.cliente(falso)
        cliente.verificar_permisos()
        with self.assertRaises(PermisosInseguros):
            cliente.verificar_permisos()
        with self.assertRaises(PermisosInseguros):
            cliente.cuenta()

    # --- solo lectura ---

    def test_lecturas_y_parametros(self):
        cliente, falso = self.verificado(**{'/api/v3/account': respuesta(CUENTA),
            '/api/v3/openOrders': respuesta([]), '/api/v3/myTrades': respuesta([{'id': 1}])})
        self.assertEqual(activos_con_saldo(cliente.cuenta()), 2)
        self.assertEqual(cliente.ordenes_abiertas(), [])
        self.assertEqual(cliente.ordenes_abiertas('AAAUSDT'), [])
        self.assertEqual(cliente.mis_trades('AAAUSDT', limite=10), [{'id': 1}])
        self.assertIn('symbol=AAAUSDT&limit=10&', falso.firmadas()[-1][1])
        for malo in ('aaausdt', 'AAA/USDT', 'AAAUSDT&side=BUY', '', None):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                cliente.mis_trades(malo)
        with self.assertRaises(ValueError):
            cliente.mis_trades('AAAUSDT', limite=0)

    def test_rutas_y_parametros_fuera_de_la_lista_se_rechazan_sin_red(self):
        cliente, falso = self.verificado()
        antes = len(falso.llamadas)
        for ruta, params in (('/api/v3/order', {}), ('/api/v3/order/test', {}),
                             ('/sapi/v1/capital/withdraw/apply', {}), ('/api/v3/account', {'symbol': 'X'}),
                             ('/api/v3/openOrders', {'side': 'BUY'}), ('/api/v3/account/../order', {})):
            with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                cliente._get(ruta, params)
        self.assertEqual(len(falso.llamadas), antes)

    def test_el_modulo_no_contiene_ordenes_retiros_ni_otro_metodo_http(self):
        fuente = inspect.getsource(binance_signed)
        for prohibido in ('/api/v3/order', 'withdraw', '/transfer', '/capital/', "'POST'", "'DELETE'", "'PUT'",
                          'testnet', 'print(error.', 'requests'):
            self.assertNotIn(prohibido, fuente)
        self.assertEqual(fuente.count("method='GET'"), 1)
        self.assertEqual(set(binance_signed.RUTAS_LECTURA), {'/sapi/v1/account/apiRestrictions',
            '/api/v3/account', '/api/v3/openOrders', '/api/v3/myTrades'})

    def test_transporte_real_no_sigue_redirecciones_ni_usa_proxies(self):
        self.assertIsNone(binance_signed._SinRedireccion().redirect_request(None, None, 302, '', {}, 'x'))
        fuente = inspect.getsource(binance_signed.transporte_urllib)
        self.assertIn('ProxyHandler({})', fuente)
        self.assertIn('_SinRedireccion()', fuente)
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: RespuestaHttp(302, {'Location': 'https://x'}, b'')})
        with self.assertRaises(ErrorBinance):
            self.cliente(falso).verificar_permisos()
        self.assertEqual(len(falso.firmadas()), 1)

    # --- restricciones HTTP ---

    def test_429_respeta_retry_after_persiste_y_no_reintenta(self):
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: [
            respuesta({}, 429, {'Retry-After': '30'}), respuesta(SOLO_LECTURA)]})
        cliente = self.cliente(falso)
        with self.assertRaises(BinanceRestringido):
            cliente.verificar_permisos()
        self.assertEqual(len(falso.firmadas()), 1)
        self.assertEqual(json.loads(self.bloqueo.read_text())['hasta'], self.ahora + 30)
        otro = self.cliente(falso)  # otro proceso: mismo archivo
        self.ahora += 29
        with self.assertRaises(BinanceRestringido):
            otro.verificar_permisos()
        self.assertEqual(len(falso.firmadas()), 1)
        self.ahora += 2
        otro.verificar_permisos()

    def test_restriccion_sin_plazo_y_451_requieren_revision(self):
        for status, cabeceras in ((418, {}), (403, {'Retry-After': 'pronto'}), (429, {'Retry-After': '-1'}),
                                  (451, {'Retry-After': '10'})):
            with self.subTest(status=status):
                self.bloqueo.unlink(missing_ok=True)
                falso = Falso({binance_signed.RUTA_RESTRICCIONES: respuesta({}, status, cabeceras)})
                with self.assertRaises(BinanceRestringido):
                    self.cliente(falso).verificar_permisos()
                self.assertIsNone(json.loads(self.bloqueo.read_text())['hasta'])
                self.ahora += 10**9
                otro = Falso({binance_signed.RUTA_RESTRICCIONES: respuesta(SOLO_LECTURA)})
                with self.assertRaises(BinanceRestringido):
                    self.cliente(otro).verificar_permisos()
                self.assertEqual(otro.llamadas, [])

    def test_bloqueo_ilegible_es_fail_closed_y_un_plazo_no_acorta_uno_indefinido(self):
        self.bloqueo.write_text('{corrupto', encoding='utf-8')
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: respuesta(SOLO_LECTURA)})
        with self.assertRaises(BinanceRestringido):
            self.cliente(falso).verificar_permisos()
        self.assertEqual(falso.llamadas, [])
        self.bloqueo.write_text(json.dumps({'hasta': None}), encoding='utf-8')
        cliente = self.cliente(falso)
        cliente._bloquear(respuesta({}, 429, {'Retry-After': '5'}))
        self.assertIsNone(json.loads(self.bloqueo.read_text())['hasta'])

    def test_restriccion_al_leer_la_hora_tambien_bloquea(self):
        class HoraBloqueada(Falso):
            def __call__(self, url, cabeceras, timeout):
                self.llamadas.append(url)
                return respuesta({}, 418, {'Retry-After': '60'})
        falso = HoraBloqueada()
        with self.assertRaises(BinanceRestringido):
            self.cliente(falso).verificar_permisos()
        self.assertEqual(len(falso.llamadas), 1)
        self.assertEqual(json.loads(self.bloqueo.read_text())['status'], 418)

    def test_5xx_y_fallo_de_red_reintentan_una_vez_con_firma_nueva(self):
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: [respuesta({}, 502), respuesta(SOLO_LECTURA)]})
        cliente = self.cliente(falso)
        cliente._dormir = lambda s: setattr(self, 'ahora', self.ahora + 1)
        cliente.verificar_permisos()
        primera, segunda = (c[1] for c in falso.firmadas())
        self.assertNotEqual(primera, segunda)
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: [TimeoutError('t'), OSError('o'), respuesta(SOLO_LECTURA)]})
        with self.assertRaises(ErrorBinance):
            self.cliente(falso).verificar_permisos()
        self.assertEqual(len(falso.firmadas()), 2)

    def test_401_no_se_reintenta(self):
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: [respuesta({'code': -2015, 'msg': 'x'}, 401)] * 3})
        with self.assertRaises(CredencialRechazada):
            self.cliente(falso).verificar_permisos()
        self.assertEqual(len(falso.firmadas()), 1)

    # --- redacción ---

    def secretos_de(self, falso):
        firmas = [c[1].rsplit('signature=', 1)[1] for c in falso.firmadas()]
        return [CLAVE_FALSA, SECRETO_FALSO, *firmas]

    def test_ninguna_excepcion_log_ni_repr_contiene_clave_secreto_o_firma(self):
        class Chivato(Falso):
            def __call__(self, url, cabeceras, timeout):
                partes = urllib.parse.urlsplit(url)
                self.llamadas.append((partes.path, partes.query, dict(cabeceras), url))
                if partes.path == binance_signed.RUTA_HORA:
                    return respuesta({'serverTime': self.hora})
                if self.modo == 'excepcion':
                    raise RuntimeError(f'fallo en {url} con {cabeceras} y {SECRETO_FALSO}')
                eco = {'code': -2015, 'msg': f'{url} {cabeceras}'}
                return respuesta(eco, self.modo)

        for modo in ('excepcion', 400, 401, 429, 500):
            with self.subTest(modo=modo):
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
                try:
                    with self.assertRaises(ErrorBinance) as contexto:
                        cliente.verificar_permisos()
                finally:
                    raiz.removeHandler(manejador)
                    raiz.setLevel(nivel)
                error = contexto.exception
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
                textos = [str(error), repr(error), ''.join(traceback.format_exception(error)),
                          registro.getvalue(), repr(cliente), str(cliente), repr(self.credenciales),
                          str(self.credenciales), repr(vars(cliente)),
                          self.bloqueo.read_text() if self.bloqueo.exists() else '']
                self.assertTrue(falso.firmadas())
                for secreto in self.secretos_de(falso):
                    for texto in textos:
                        self.assertNotIn(secreto, texto)

    def test_credenciales_no_se_serializan_ni_exponen_atributos(self):
        with self.assertRaises(TypeError):
            pickle.dumps(self.credenciales)
        self.assertFalse(hasattr(self.credenciales, '__dict__'))
        self.assertEqual(repr(self.credenciales), 'Credenciales(<redactado>)')
        with self.assertRaises(TypeError):
            ClienteLectura((CLAVE_FALSA, SECRETO_FALSO))

    def test_entorno_ausente_o_malformado_nombra_la_variable_y_nunca_el_valor(self):
        with self.assertRaisesRegex(CredencialesAusentes, 'BINANCE_READONLY_API_KEY'):
            Credenciales.desde_entorno(entorno={})
        with self.assertRaisesRegex(CredencialesAusentes, 'BINANCE_READONLY_SECRET_KEY'):
            Credenciales.desde_entorno(entorno={'BINANCE_READONLY_API_KEY': CLAVE_FALSA})
        for malo in (f' {SECRETO_FALSO}', f'"{SECRETO_FALSO}"', SECRETO_FALSO + '\n', 'corta',
                     '-----BEGIN ' + 'PRIVATE KEY-----'):
            with self.subTest(malo=malo), self.assertRaises(CredencialesAusentes) as contexto:
                Credenciales.desde_entorno(entorno={'BINANCE_READONLY_API_KEY': CLAVE_FALSA,
                                                    'BINANCE_READONLY_SECRET_KEY': malo})
            self.assertNotIn(malo.strip(' "\n'), str(contexto.exception))
        ok = Credenciales.desde_entorno(entorno={'BINANCE_READONLY_API_KEY': CLAVE_FALSA,
                                                 'BINANCE_READONLY_SECRET_KEY': SECRETO_FALSO})
        self.assertEqual(ok.cabecera(), {'X-MBX-APIKEY': CLAVE_FALSA})

    # --- saldos y comando del dueño ---

    def test_activos_con_saldo_rechaza_formatos_inesperados(self):
        for malo in ({}, {'balances': None}, {'balances': [{'asset': 'A', 'free': 'x', 'locked': '0'}]},
                     {'balances': [{'asset': 'A', 'free': '1'}]}, {'balances': ['A']},
                     {'balances': [{'asset': 'A', 'free': 'NaN', 'locked': '0'}]},
                     {'balances': [{'asset': 'A', 'free': '-1', 'locked': '0'}]}):
            with self.subTest(malo=malo), self.assertRaises(ErrorBinance):
                activos_con_saldo(malo)
        self.assertEqual(activos_con_saldo({'balances': []}), 0)

    def ejecutar(self, falso, entorno=None):
        salida = io.StringIO()
        entorno = {'BINANCE_READONLY_API_KEY': CLAVE_FALSA,
                   'BINANCE_READONLY_SECRET_KEY': SECRETO_FALSO} if entorno is None else entorno
        codigo = main([], entorno=entorno, salida=salida, transporte=falso, ruta_bloqueo=self.bloqueo)
        texto = salida.getvalue()
        for secreto in (CLAVE_FALSA, SECRETO_FALSO):
            self.assertNotIn(secreto, texto)
        return codigo, texto

    def test_comando_muestra_solo_conexion_permisos_y_numero_de_activos(self):
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: respuesta(SOLO_LECTURA),
                       '/api/v3/account': respuesta(CUENTA)})
        codigo, texto = self.ejecutar(falso)
        self.assertEqual(codigo, 0)
        self.assertEqual(texto.splitlines()[1:], ['Conectado: SI',
            'Permisos de la clave: lectura=SI trading=NO retiros=NO restriccion_ip=SI',
            'Activos con saldo: 2'])
        for dato in ('AAA', 'BBB', '1.5', '0.2'):
            self.assertNotIn(dato, texto)

    def test_comando_se_niega_con_retiros_y_no_lee_la_cuenta(self):
        falso = Falso({binance_signed.RUTA_RESTRICCIONES: respuesta(dict(SOLO_LECTURA, enableWithdrawals=True)),
                       '/api/v3/account': respuesta(CUENTA)})
        codigo, texto = self.ejecutar(falso)
        self.assertEqual(codigo, 1)
        self.assertIn('Conectado: NO', texto)
        self.assertIn('RETIROS', texto)
        self.assertNotIn('Activos con saldo', texto)
        self.assertNotIn('/api/v3/account', [c[0] for c in falso.llamadas])

    def test_comando_sin_variables_espera_al_dueno_sin_tocar_la_red(self):
        falso = Falso()
        codigo, texto = self.ejecutar(falso, entorno={})
        self.assertEqual(codigo, 2)
        self.assertIn('WAITING_FOR_USER', texto)
        self.assertIn('BINANCE_READONLY_API_KEY', texto)
        self.assertEqual(falso.llamadas, [])
        self.assertEqual(main(['--host', 'x'], entorno={}, salida=io.StringIO(), transporte=falso), 2)
        self.assertEqual(falso.llamadas, [])


if __name__ == '__main__':
    unittest.main()
