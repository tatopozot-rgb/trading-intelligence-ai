"""Órdenes SOLO en Binance Spot Testnet (hito H2). Dinero ficticio. Solo biblioteca estándar.

Transporte, no decisión: este módulo no elige operaciones ni sustituye al Risk
Engine, y hoy no está conectado al runner PAPER. El host es fijo y no existe
opción para cambiarlo: cualquier URL fuera de testnet.binance.vision lanza un error
antes de tocar la red.

Una orden nunca se reenvía. Cada intento se anota en un diario local ANTES de
enviarse; una respuesta incierta (timeout, corte, 5xx) se concilia consultando por
su newClientOrderId. Mientras quede una orden sin conciliar no se envía otra.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from typing import Callable, Iterator, Mapping, Optional, Sequence, TextIO
import urllib.error
import urllib.parse
import urllib.request
import uuid

from binance_signed import (ESTADOS_RESTRICCION, MAX_CUERPO, RECV_WINDOW_MS, TIMEOUT_SEG,
    BinanceRestringido, Credenciales, CredencialesAusentes, Enfriamiento, ErrorBinance,
    RespuestaHttp, activos_con_saldo)

logger = logging.getLogger(__name__)

TESTNET = 'https://testnet.binance.vision'
VARIABLE_CLAVE = 'BINANCE_TESTNET_API_KEY'
VARIABLE_SECRETO = 'BINANCE_TESTNET_SECRET_KEY'
RUTA_HORA = '/api/v3/time'
RUTA_ORDEN = '/api/v3/order'
RUTA_CUENTA = '/api/v3/account'
PETICIONES = frozenset({('GET', RUTA_HORA), ('GET', RUTA_CUENTA), ('GET', RUTA_ORDEN), ('POST', RUTA_ORDEN)})
ESQUEMA = 'TESTNET_ORDENES_V1'
PENDIENTE_ENVIO, CONFIRMADA, RECHAZADA, INCIERTA, NO_ENCONTRADA = (
    'PENDIENTE_ENVIO', 'CONFIRMADA', 'RECHAZADA', 'INCIERTA', 'NO_ENCONTRADA')
SIN_CONCILIAR = frozenset({PENDIENTE_ENVIO, INCIERTA})
CODIGO_ORDEN_INEXISTENTE = -2013
# Una orden recién enviada puede tardar en ser consultable: antes de este plazo
# "no existe" no se toma como definitivo.
ESPERA_MINIMA_CONCILIACION_SEG = 10.0


class HostNoPermitido(ErrorBinance):
    pass


class OrdenInvalida(ValueError):
    pass


class DiarioInconsistente(ErrorBinance):
    pass


class ConciliacionPendiente(ErrorBinance):
    pass


TransporteOrdenes = Callable[[str, str, Mapping[str, str], float], RespuestaHttp]


def exigir_testnet(url: str) -> None:
    """Único host admitido, escrito aquí como literal: no depende de ninguna variable."""
    partes = urllib.parse.urlsplit(url)
    if partes.scheme != 'https' or partes.netloc != 'testnet.binance.vision':
        raise HostNoPermitido('Las órdenes solo pueden ir a Binance Spot Testnet.')


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def transporte_urllib(metodo: str, url: str, cabeceras: Mapping[str, str], timeout: float) -> RespuestaHttp:
    exigir_testnet(url)
    if metodo not in ('GET', 'POST'):
        raise HostNoPermitido('Método HTTP no admitido.')
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SinRedireccion())
    peticion = urllib.request.Request(url, headers=dict(cabeceras), method=metodo,
                                      data=b'' if metodo == 'POST' else None)
    try:
        with abridor.open(peticion, timeout=timeout) as respuesta:
            return RespuestaHttp(respuesta.status, dict(respuesta.headers.items()),
                                 respuesta.read(MAX_CUERPO + 1))
    except urllib.error.HTTPError as error:
        with error:
            return RespuestaHttp(error.code, dict(error.headers.items()), error.read(MAX_CUERPO + 1))


def _decimal_texto(valor: object) -> str:
    if type(valor) is not str or len(valor) > 40 or re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', valor) is None \
            or not any(c in '123456789' for c in valor):
        raise OrdenInvalida('Se requiere un decimal positivo en texto, sin float ni exponente.')
    return valor


@dataclass(frozen=True)
class OrdenTestnet:
    simbolo: str
    lado: str
    tipo: str
    cantidad: str
    client_order_id: str
    precio: Optional[str] = None

    def parametros(self) -> dict[str, str]:
        if type(self.simbolo) is not str or re.fullmatch(r'[A-Z0-9]{5,20}', self.simbolo) is None:
            raise OrdenInvalida('Símbolo inválido.')
        if self.lado not in ('BUY', 'SELL') or self.tipo not in ('MARKET', 'LIMIT'):
            raise OrdenInvalida('Lado o tipo de orden no admitido.')
        if type(self.client_order_id) is not str or \
                re.fullmatch(r'[A-Za-z0-9_-]{1,36}', self.client_order_id) is None:
            raise OrdenInvalida('newClientOrderId inválido.')
        if (self.tipo == 'LIMIT') != (self.precio is not None):
            raise OrdenInvalida('LIMIT exige precio; MARKET no lo admite.')
        params = {'symbol': self.simbolo, 'side': self.lado, 'type': self.tipo,
                  'quantity': _decimal_texto(self.cantidad), 'newClientOrderId': self.client_order_id,
                  'newOrderRespType': 'RESULT'}
        if self.precio is not None:
            params.update(timeInForce='GTC', price=_decimal_texto(self.precio))
        return params


class Diario:
    """Registro local de intentos. Ilegible o alterado = no se envía nada."""

    def __init__(self, ruta: Path) -> None:
        self._ruta = Path(ruta)

    @contextmanager
    def exclusivo(self) -> Iterator[None]:
        """Un único escritor entre procesos e hilos. Toda secuencia leer-decidir-guardar va dentro:
        reemplazar el archivo de forma atómica no basta para que la secuencia lo sea.
        No es reentrante. Si no se obtiene el bloqueo, no se envía ni se escribe nada."""
        with self._ruta.with_name(self._ruta.name + '.lock').open('a+b') as archivo:
            archivo.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(archivo.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(archivo, fcntl.LOCK_EX)
            except OSError:
                raise DiarioInconsistente('Diario de órdenes Testnet ocupado por otro proceso.') from None
            try:
                yield
            finally:
                if os.name == 'nt':
                    archivo.seek(0)
                    msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)

    def leer(self) -> dict[str, dict]:
        try:
            dato = json.loads(self._ruta.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}
        except (ValueError, OSError):
            raise DiarioInconsistente('Diario de órdenes Testnet ilegible; requiere revisión.') from None
        ordenes = dato.get('ordenes') if type(dato) is dict and dato.get('schema') == ESQUEMA else None
        if type(ordenes) is not dict or any(
                type(o) is not dict or o.get('estado') not in
                (PENDIENTE_ENVIO, CONFIRMADA, RECHAZADA, INCIERTA, NO_ENCONTRADA) or
                type(o.get('simbolo')) is not str or type(o.get('creado_epoch')) not in (int, float)
                for o in ordenes.values()):
            raise DiarioInconsistente('Diario de órdenes Testnet con formato inesperado.')
        return ordenes

    def guardar(self, ordenes: Mapping[str, dict]) -> None:
        temporal = self._ruta.with_name(f'{self._ruta.name}.{uuid.uuid4().hex}.tmp')
        temporal.write_text(json.dumps({'schema': ESQUEMA, 'ordenes': ordenes}, allow_nan=False,
                                       sort_keys=True), encoding='utf-8')
        temporal.replace(self._ruta)


class ClienteTestnet:
    def __init__(self, credenciales: Credenciales, *, transporte: Optional[TransporteOrdenes] = None,
                 reloj: Optional[Callable[[], float]] = None, ruta_diario: Optional[Path] = None,
                 ruta_bloqueo: Optional[Path] = None) -> None:
        if type(credenciales) is not Credenciales:
            raise TypeError('Se requieren Credenciales.')
        carpeta = Path(__file__).resolve().parent
        self._credenciales = credenciales
        self._transporte: TransporteOrdenes = transporte or transporte_urllib
        self._reloj = reloj or time.time
        self._diario = Diario(ruta_diario or carpeta / 'binance_testnet_journal.json')
        self._enfriamiento = Enfriamiento(ruta_bloqueo or carpeta / 'binance_testnet_cooldown.json', self._reloj)
        self._desfase_ms: Optional[int] = None

    @classmethod
    def desde_entorno(cls, entorno: Optional[Mapping[str, str]] = None, **kwargs: object) -> 'ClienteTestnet':
        credenciales = Credenciales.desde_entorno(VARIABLE_CLAVE, VARIABLE_SECRETO,
                                                  os.environ if entorno is None else entorno)
        return cls(credenciales, **kwargs)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        return 'ClienteTestnet(host=testnet.binance.vision)'

    # --- transporte: un único intento por llamada, nunca un reintento ---

    def _enviar(self, metodo: str, ruta: str, query: str, cabeceras: Mapping[str, str]) -> Optional[RespuestaHttp]:
        if (metodo, ruta) not in PETICIONES:
            raise ValueError('Petición no admitida en el cliente Testnet.')
        url = f'{TESTNET}{ruta}?{query}' if query else f'{TESTNET}{ruta}'
        exigir_testnet(url)
        tipo = None
        try:
            respuesta = self._transporte(metodo, url, cabeceras, TIMEOUT_SEG)
        except Exception as error:  # noqa: BLE001 - el texto puede contener la URL firmada
            tipo = type(error).__name__
        if tipo is not None:
            logger.warning('Fallo de red (%s) en %s %s', tipo, metodo, ruta)
            return None
        if type(respuesta) is not RespuestaHttp or len(respuesta.cuerpo) > MAX_CUERPO:
            return None
        return respuesta

    @staticmethod
    def _json(respuesta: Optional[RespuestaHttp]) -> object:
        try:
            return None if respuesta is None else json.loads(respuesta.cuerpo.decode('utf-8'))
        except (ValueError, RecursionError):
            return None

    def _sincronizar_hora(self) -> None:
        self._enfriamiento.comprobar()
        respuesta = self._enviar('GET', RUTA_HORA, '', {})
        if respuesta is not None and respuesta.status in ESTADOS_RESTRICCION:
            self._enfriamiento.bloquear(respuesta)
            raise BinanceRestringido(f'Restricción HTTP {respuesta.status} en Testnet; no se reintenta.')
        dato = self._json(respuesta)
        hora = dato.get('serverTime') if type(dato) is dict else None
        if respuesta is None or respuesta.status != 200 or type(hora) is not int or hora <= 0:
            raise ErrorBinance('No se pudo leer la hora del servidor de Testnet.')
        self._desfase_ms = hora - int(self._reloj() * 1000)

    def _firmada(self, metodo: str, ruta: str, params: Mapping[str, str]) -> Optional[RespuestaHttp]:
        assert self._desfase_ms is not None
        query = urllib.parse.urlencode({**params, 'recvWindow': str(RECV_WINDOW_MS),
                                        'timestamp': str(int(self._reloj() * 1000) + self._desfase_ms)})
        query = f'{query}&signature={self._credenciales.firmar(query)}'
        respuesta = self._enviar(metodo, ruta, query, self._credenciales.cabecera())
        if respuesta is not None and respuesta.status in ESTADOS_RESTRICCION:
            self._enfriamiento.bloquear(respuesta)
        return respuesta

    def _preparar(self) -> None:
        self._enfriamiento.comprobar()
        if self._desfase_ms is None:
            self._sincronizar_hora()

    # --- órdenes ---

    @staticmethod
    def _coincide(dato: object, client_order_id: str, registro: Mapping[str, object]) -> bool:
        return (type(dato) is dict and dato.get('clientOrderId') == client_order_id and
                dato.get('symbol') == registro['simbolo'] and type(dato.get('orderId')) is int and
                type(dato.get('status')) is str and re.fullmatch(r'[A-Z_]{1,30}', dato['status']) is not None)

    @staticmethod
    def _confirmar(registro: dict, dato: Mapping[str, object]) -> None:
        registro.update(estado=CONFIRMADA, order_id=dato['orderId'], estado_exchange=dato['status'])
        for origen, destino in (('executedQty', 'ejecutado'), ('cummulativeQuoteQty', 'importe_cotizado')):
            valor = dato.get(origen)
            if type(valor) is str and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', valor):
                registro[destino] = valor

    def sin_conciliar(self) -> list[str]:
        return sorted(k for k, o in self._diario.leer().items() if o['estado'] in SIN_CONCILIAR)

    @staticmethod
    def _exigir_libre(client_order_id: str, ordenes: Mapping[str, dict]) -> None:
        if client_order_id in ordenes:
            raise OrdenInvalida('Ese newClientOrderId ya consta en el diario: una orden nunca se reenvía.')
        if any(o['estado'] in SIN_CONCILIAR for o in ordenes.values()):
            raise ConciliacionPendiente('Hay una orden sin conciliar; no se envía otra hasta resolverla.')

    def _actualizar(self, client_order_id: str, registro: Mapping[str, object]) -> dict:
        """Único punto de escritura de un resultado, sobre el diario releído bajo bloqueo.
        La transición es monótona: un estado definitivo (CONFIRMADA, RECHAZADA, NO_ENCONTRADA)
        que otro proceso ya anotó no se sustituye ni se degrada. Devuelve el registro vigente."""
        with self._diario.exclusivo():
            ordenes = self._diario.leer()
            actual = ordenes.get(client_order_id)
            if actual is not None and actual['estado'] not in SIN_CONCILIAR:
                return dict(actual)
            ordenes[client_order_id] = dict(registro)
            self._diario.guardar(ordenes)
            return dict(registro)

    def enviar(self, orden: OrdenTestnet) -> dict:
        """Un único POST. Devuelve el registro del diario; INCIERTA exige conciliar()."""
        params = orden.parametros()
        self._exigir_libre(orden.client_order_id, self._diario.leer())  # rechazo temprano, sin tocar la red
        self._preparar()
        registro: dict = {'estado': PENDIENTE_ENVIO, 'simbolo': orden.simbolo, 'lado': orden.lado,
                          'tipo': orden.tipo, 'cantidad': orden.cantidad, 'precio': orden.precio,
                          'creado_epoch': self._reloj()}
        # Reserva: comprobar y anotar son una sola operación para cualquier otro proceso o hilo.
        with self._diario.exclusivo():
            ordenes = self._diario.leer()
            self._exigir_libre(orden.client_order_id, ordenes)  # la comprobación que vale
            ordenes[orden.client_order_id] = registro
            self._diario.guardar(ordenes)  # Si esto falla, la orden no sale.
        respuesta = self._firmada('POST', RUTA_ORDEN, params)
        dato = self._json(respuesta)
        codigo = dato.get('code') if type(dato) is dict else None
        if respuesta is not None and respuesta.status == 200 and self._coincide(dato, orden.client_order_id, registro):
            self._confirmar(registro, dato)  # type: ignore[arg-type]
        elif (respuesta is not None and 400 <= respuesta.status < 500 and
              respuesta.status not in ESTADOS_RESTRICCION and type(codigo) is int and codigo < 0):
            registro.update(estado=RECHAZADA, codigo=codigo)
        else:
            # Timeout, corte, 5xx, restricción o respuesta que no se entiende: estado desconocido.
            registro.update(estado=INCIERTA, http=None if respuesta is None else respuesta.status)
        registro = self._actualizar(orden.client_order_id, registro)
        logger.info('Orden Testnet %s: %s', orden.client_order_id, registro['estado'])
        return registro

    def conciliar(self) -> dict[str, str]:
        """Consulta por newClientOrderId cada orden sin conciliar. Nunca reenvía."""
        resultado: dict[str, str] = {}
        for client_order_id in self.sin_conciliar():
            registro = self._diario.leer().get(client_order_id)
            if registro is None or registro['estado'] not in SIN_CONCILIAR:
                continue  # otro proceso la resolvió entretanto
            self._preparar()
            respuesta = self._firmada('GET', RUTA_ORDEN, {'symbol': registro['simbolo'],
                                                         'origClientOrderId': client_order_id})
            dato = self._json(respuesta)
            codigo = dato.get('code') if type(dato) is dict else None
            if respuesta is not None and respuesta.status == 200 and self._coincide(dato, client_order_id, registro):
                self._confirmar(registro, dato)  # type: ignore[arg-type]
            elif (respuesta is not None and respuesta.status == 400 and codigo == CODIGO_ORDEN_INEXISTENTE and
                  self._reloj() - registro['creado_epoch'] >= ESPERA_MINIMA_CONCILIACION_SEG):
                registro['estado'] = NO_ENCONTRADA
            else:
                registro['estado'] = INCIERTA
            registro = self._actualizar(client_order_id, registro)
            resultado[client_order_id] = registro['estado']
            if respuesta is not None and respuesta.status in ESTADOS_RESTRICCION:
                break
        return resultado

    def cuenta(self) -> dict:
        self._preparar()
        respuesta = self._firmada('GET', RUTA_CUENTA, {'omitZeroBalances': 'true'})
        dato = self._json(respuesta)
        if respuesta is None or respuesta.status != 200 or type(dato) is not dict or 'code' in dato:
            raise ErrorBinance(f'Lectura de cuenta Testnet fallida (HTTP '
                               f'{None if respuesta is None else respuesta.status}).')
        return dato


def main(argv: Optional[Sequence[str]] = None, *, entorno: Optional[Mapping[str, str]] = None,
         salida: Optional[TextIO] = None, **kwargs: object) -> int:
    """Estado de Testnet para el dueño. No envía ninguna orden."""
    salida = salida or sys.stdout
    if argv:
        print('Uso: python binance_testnet_orders.py   (sin argumentos; no envía órdenes)', file=salida)
        return 2
    print('Binance Spot TESTNET (dinero ficticio) - comprobación sin órdenes', file=salida)
    try:
        cliente = ClienteTestnet.desde_entorno(entorno, **kwargs)
    except CredencialesAusentes as error:
        print(f'Conectado: NO\nWAITING_FOR_USER: {error}', file=salida)
        print(f'Crea una clave HMAC en testnet.binance.vision y define {VARIABLE_CLAVE} y '
              f'{VARIABLE_SECRETO} en las variables de entorno de tu cuenta de Windows.', file=salida)
        return 2
    try:
        activos = activos_con_saldo(cliente.cuenta())
        pendientes = cliente.sin_conciliar()
    except ErrorBinance as error:
        print(f'Conectado: NO\nMotivo: {error}', file=salida)
        return 1
    print(f'Conectado: SI\nActivos ficticios con saldo: {activos}\n'
          f'Ordenes sin conciliar en el diario: {len(pendientes)}', file=salida)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
