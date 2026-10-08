"""Cliente firmado de Binance Spot, SOLO LECTURA (hito H1). Solo biblioteca estándar.

Este módulo únicamente emite GET a una lista cerrada de rutas de lectura. No
contiene envío de órdenes, retiros ni transferencias, y no hay opción para
añadirlos. Las credenciales se leen por NOMBRE de variable de entorno; su valor
nunca se imprime, registra ni incluye en una excepción o repr.

La guardia de permisos es fail-closed: si la clave tiene retiros o trading
habilitados, o no se puede determinar, el cliente se niega a leer la cuenta.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Callable, Mapping, Optional, Sequence, TextIO
import urllib.error
import urllib.parse
import urllib.request
import uuid

logger = logging.getLogger(__name__)

PRODUCCION = 'https://api.binance.com'
VARIABLE_CLAVE = 'BINANCE_READONLY_API_KEY'
VARIABLE_SECRETO = 'BINANCE_READONLY_SECRET_KEY'
RUTA_HORA = '/api/v3/time'
RUTA_RESTRICCIONES = '/sapi/v1/account/apiRestrictions'
# Lista cerrada: rutas firmadas de LECTURA y los parámetros que admiten.
RUTAS_LECTURA: Mapping[str, frozenset[str]] = {
    RUTA_RESTRICCIONES: frozenset(),
    '/api/v3/account': frozenset({'omitZeroBalances'}),
    '/api/v3/openOrders': frozenset({'symbol'}),
    '/api/v3/myTrades': frozenset({'symbol', 'limit', 'startTime', 'endTime', 'fromId'}),
}
RECV_WINDOW_MS = 5000
TIMEOUT_SEG = 15.0
MAX_CUERPO = 5_000_000
ESTADOS_RESTRICCION = frozenset({403, 418, 429, 451})
# Únicos permisos que pueden estar activos en una clave de solo lectura.
PERMISOS_ADMITIDOS = frozenset({'enableReading', 'enableFixReadOnly'})
CODIGO_HORA_FUERA_DE_VENTANA = -1021


class ErrorBinance(RuntimeError):
    """Mensaje fijo y seguro: nunca contiene clave, firma, query ni cuerpo remoto."""


class CredencialesAusentes(ErrorBinance):
    pass


class CredencialRechazada(ErrorBinance):
    pass


class BinanceRestringido(ErrorBinance):
    pass


class PermisosInseguros(ErrorBinance):
    pass


@dataclass(frozen=True)
class RespuestaHttp:
    status: int
    cabeceras: Mapping[str, str]
    cuerpo: bytes


@dataclass(frozen=True)
class Permisos:
    lectura: bool
    trading: bool
    retiros: bool
    restriccion_ip: bool


Transporte = Callable[[str, Mapping[str, str], float], RespuestaHttp]


class Credenciales:
    """Par clave/secreto HMAC. Sin repr, sin pickle y sin atributos públicos."""
    __slots__ = ('_clave', '_secreto')
    _FORMATO = re.compile(r'[A-Za-z0-9]{16,256}')

    def __init__(self, clave: str, secreto: str) -> None:
        for valor in (clave, secreto):
            if type(valor) is not str or self._FORMATO.fullmatch(valor) is None:
                raise CredencialesAusentes('Credencial con formato inesperado.')
        self._clave = clave
        self._secreto = secreto

    @classmethod
    def desde_entorno(cls, nombre_clave: str = VARIABLE_CLAVE, nombre_secreto: str = VARIABLE_SECRETO,
                      entorno: Optional[Mapping[str, str]] = None) -> 'Credenciales':
        entorno = os.environ if entorno is None else entorno
        valores = []
        for nombre in (nombre_clave, nombre_secreto):
            valor = entorno.get(nombre)
            if not valor:
                raise CredencialesAusentes(f'La variable de entorno {nombre} no está definida.')
            if cls._FORMATO.fullmatch(valor) is None:
                # Solo el nombre: el valor jamás aparece en el mensaje.
                raise CredencialesAusentes(
                    f'La variable de entorno {nombre} tiene un formato inesperado '
                    '(espacios, comillas o una clave que no es de tipo HMAC).')
            valores.append(valor)
        return cls(valores[0], valores[1])

    def cabecera(self) -> dict[str, str]:
        return {'X-MBX-APIKEY': self._clave}

    def firmar(self, query: str) -> str:
        return firmar(self._secreto, query)

    def __repr__(self) -> str:
        return 'Credenciales(<redactado>)'

    __str__ = __repr__

    def __reduce__(self) -> str:
        raise TypeError('Las credenciales no se serializan.')


def firmar(secreto: str, query: str) -> str:
    """HMAC-SHA256 en hexadecimal de la query string exacta que se envía."""
    return hmac.new(secreto.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    # Una redirección reenviaría la cabecera con la clave a otro host.
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def transporte_urllib(url: str, cabeceras: Mapping[str, str], timeout: float) -> RespuestaHttp:
    """GET único, sin proxies del entorno y sin seguir redirecciones."""
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SinRedireccion())
    peticion = urllib.request.Request(url, headers=dict(cabeceras), method='GET')
    try:
        with abridor.open(peticion, timeout=timeout) as respuesta:
            return RespuestaHttp(respuesta.status, dict(respuesta.headers.items()),
                                 respuesta.read(MAX_CUERPO + 1))
    except urllib.error.HTTPError as error:
        with error:
            return RespuestaHttp(error.code, dict(error.headers.items()), error.read(MAX_CUERPO + 1))


def evaluar_restricciones(dato: object) -> Permisos:
    """Guardia fail-closed sobre la respuesta de apiRestrictions de una clave de solo lectura."""
    if type(dato) is not dict:
        raise PermisosInseguros('No se pudieron determinar los permisos de la clave.')
    if dato.get('enableWithdrawals') is not False:
        if dato.get('enableWithdrawals') is True:
            raise PermisosInseguros('La clave tiene RETIROS habilitados. Desactívalos en Binance.')
        raise PermisosInseguros('No se pudo determinar si la clave tiene retiros habilitados.')
    if dato.get('enableSpotAndMarginTrading') is not False:
        if dato.get('enableSpotAndMarginTrading') is True:
            raise PermisosInseguros('La clave de solo lectura tiene TRADING habilitado. Desactívalo en Binance.')
        raise PermisosInseguros('No se pudo determinar si la clave tiene trading habilitado.')
    if dato.get('enableReading') is not True:
        raise PermisosInseguros('La clave no tiene lectura habilitada o no se pudo determinar.')
    if type(dato.get('ipRestrict')) is not bool:
        raise PermisosInseguros('No se pudo determinar la restricción de IP de la clave.')
    for nombre, valor in dato.items():
        if type(nombre) is not str or not nombre.startswith(('enable', 'permits')):
            continue
        if type(valor) is not bool:
            raise PermisosInseguros('La clave tiene un permiso que no se pudo determinar.')
        if valor and nombre not in PERMISOS_ADMITIDOS:
            etiqueta = nombre if re.fullmatch(r'[A-Za-z]{1,60}', nombre) else 'desconocido'
            raise PermisosInseguros(f'La clave tiene un permiso no admitido para solo lectura: {etiqueta}.')
    return Permisos(lectura=True, trading=False, retiros=False, restriccion_ip=dato['ipRestrict'])


def activos_con_saldo(cuenta: Mapping[str, object]) -> int:
    balances = cuenta.get('balances')
    if type(balances) is not list:
        raise ErrorBinance('Respuesta de cuenta sin lista de saldos.')
    total = 0
    for saldo in balances:
        try:
            cantidad = Decimal(saldo['free']) + Decimal(saldo['locked'])
        except (TypeError, KeyError, InvalidOperation):
            raise ErrorBinance('Saldo con formato inesperado.') from None
        if not cantidad.is_finite() or cantidad < 0:
            raise ErrorBinance('Saldo con formato inesperado.')
        total += cantidad > 0
    return total


class Enfriamiento:
    """Restricciones HTTP 429/418/403/451: mismo criterio que el cliente público
    (CONEXION_BINANCE.md). Persistido para que otro proceso tampoco insista."""

    def __init__(self, ruta: Path, reloj: Callable[[], float]) -> None:
        self._ruta = Path(ruta)
        self._reloj = reloj
        self._memoria = 0.0

    def comprobar(self) -> None:
        if self._reloj() < self._memoria:
            raise BinanceRestringido('Restricción HTTP activa en este proceso.')
        try:
            dato = json.loads(self._ruta.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return
        except (ValueError, OSError):
            raise BinanceRestringido('No se puede verificar el bloqueo de la API firmada.') from None
        hasta = dato.get('hasta') if type(dato) is dict else None
        if type(hasta) not in (int, float) or not math.isfinite(hasta):
            raise BinanceRestringido('Restricción HTTP sin plazo válido; requiere revisión del dueño.')
        if self._reloj() < hasta:
            raise BinanceRestringido(f'API firmada bloqueada hasta UTC epoch {hasta}.')

    def bloquear(self, respuesta: RespuestaHttp) -> None:
        hasta: Optional[float] = None  # Nunca inventar el vencimiento de una restricción.
        if respuesta.status != 451:  # Una restricción legal no se libera por temporizador.
            cabeceras = {k.lower(): v for k, v in respuesta.cabeceras.items()}
            try:
                espera = float(cabeceras.get('retry-after', ''))
                if math.isfinite(espera) and espera > 0:
                    hasta = self._reloj() + espera
            except (TypeError, ValueError):
                pass
        # Si falla persistir, este cliente tampoco vuelve a consultar en este proceso.
        self._memoria = max(self._memoria, math.inf if hasta is None else hasta)
        try:
            previo = json.loads(self._ruta.read_text(encoding='utf-8')).get('hasta')
            if type(previo) not in (int, float) or not math.isfinite(previo):
                hasta = None
            elif hasta is not None:
                hasta = max(hasta, previo)
        except FileNotFoundError:
            pass
        except (ValueError, OSError, AttributeError):
            hasta = None
        dato = {'hasta': hasta, 'status': respuesta.status, 'creado_epoch': self._reloj()}
        temporal = self._ruta.with_name(f'{self._ruta.name}.{uuid.uuid4().hex}.tmp')
        temporal.write_text(json.dumps(dato, allow_nan=False), encoding='utf-8')
        temporal.replace(self._ruta)
        logger.error('Restricción HTTP %s en la API firmada; hasta=%s', respuesta.status, hasta)


class ClienteLectura:
    """Lecturas firmadas de la cuenta. Sin guardia de permisos superada no lee nada."""

    def __init__(self, credenciales: Credenciales, *, transporte: Optional[Transporte] = None,
                 reloj: Optional[Callable[[], float]] = None, dormir: Optional[Callable[[float], None]] = None,
                 ruta_bloqueo: Optional[Path] = None) -> None:
        if type(credenciales) is not Credenciales:
            raise TypeError('Se requieren Credenciales.')
        self._credenciales = credenciales
        self._transporte: Transporte = transporte or transporte_urllib
        self._reloj = reloj or time.time
        self._dormir = dormir or time.sleep
        self._enfriamiento = Enfriamiento(ruta_bloqueo or (
            Path(__file__).resolve().parent / 'binance_signed_cooldown.json'), self._reloj)
        self._desfase_ms: Optional[int] = None
        self._permisos: Optional[Permisos] = None

    def __repr__(self) -> str:
        return f'ClienteLectura(host={PRODUCCION!r}, guardia={"OK" if self._permisos else "PENDIENTE"})'

    def _comprobar_bloqueo(self) -> None:
        self._enfriamiento.comprobar()

    def _bloquear(self, respuesta: RespuestaHttp) -> None:
        self._enfriamiento.bloquear(respuesta)

    # --- transporte ---

    def _enviar(self, ruta: str, query: str, cabeceras: Mapping[str, str]) -> Optional[RespuestaHttp]:
        """Devuelve None ante un fallo de red. La excepción original se descarta
        entera: su texto puede contener la URL con la firma."""
        url = f'{PRODUCCION}{ruta}?{query}' if query else f'{PRODUCCION}{ruta}'
        tipo = None
        try:
            respuesta = self._transporte(url, cabeceras, TIMEOUT_SEG)
        except Exception as error:  # noqa: BLE001 - se redacta todo fallo de transporte
            tipo = type(error).__name__
        if tipo is not None:
            logger.warning('Fallo de red (%s) en %s', tipo, ruta)
            return None
        if type(respuesta) is not RespuestaHttp or len(respuesta.cuerpo) > MAX_CUERPO:
            raise ErrorBinance(f'Respuesta inválida o demasiado grande en {ruta}.')
        return respuesta

    @staticmethod
    def _json(respuesta: RespuestaHttp) -> object:
        try:
            return json.loads(respuesta.cuerpo.decode('utf-8'))
        except (ValueError, RecursionError):
            return None

    def _sincronizar_hora(self) -> None:
        """Hora del servidor por ruta pública: se envía sin la cabecera de la clave."""
        self._comprobar_bloqueo()
        respuesta = self._enviar(RUTA_HORA, '', {})
        if respuesta is None:
            raise ErrorBinance('Sin conexión con Binance al leer la hora del servidor.')
        if respuesta.status in ESTADOS_RESTRICCION:
            self._bloquear(respuesta)
            raise BinanceRestringido(f'Restricción HTTP {respuesta.status}; no se reintenta.')
        dato = self._json(respuesta)
        hora = dato.get('serverTime') if type(dato) is dict else None
        if respuesta.status != 200 or type(hora) is not int or hora <= 0:
            raise ErrorBinance('No se pudo leer la hora del servidor de Binance.')
        self._desfase_ms = hora - int(self._reloj() * 1000)

    def _get(self, ruta: str, params: Optional[Mapping[str, str]] = None) -> object:
        params = dict(params or {})
        if ruta not in RUTAS_LECTURA or not set(params) <= RUTAS_LECTURA[ruta]:
            raise ValueError('Ruta o parámetros no permitidos: este cliente es de solo lectura.')
        if self._desfase_ms is None:
            self._sincronizar_hora()
        resincronizado = False
        intento = 0
        while True:
            self._comprobar_bloqueo()
            assert self._desfase_ms is not None
            firmables = {**params, 'recvWindow': str(RECV_WINDOW_MS),
                         'timestamp': str(int(self._reloj() * 1000) + self._desfase_ms)}
            query = urllib.parse.urlencode(firmables)
            query = f'{query}&signature={self._credenciales.firmar(query)}'
            respuesta = self._enviar(ruta, query, self._credenciales.cabecera())
            status = None if respuesta is None else respuesta.status
            if status in ESTADOS_RESTRICCION:
                assert respuesta is not None
                self._bloquear(respuesta)
                raise BinanceRestringido(f'Restricción HTTP {status}; no se reintenta esta llamada.')
            if respuesta is None or 500 <= respuesta.status < 600:
                # Un GET de lectura admite un único reintento, con firma nueva.
                if intento == 0:
                    intento += 1
                    self._dormir(0.5)
                    continue
                raise ErrorBinance(f'Lectura fallida tras 2 intentos en {ruta}.')
            dato = self._json(respuesta)
            codigo = dato.get('code') if type(dato) is dict else None
            codigo = codigo if type(codigo) is int else None
            if codigo == CODIGO_HORA_FUERA_DE_VENTANA and not resincronizado:
                resincronizado = True
                self._sincronizar_hora()
                continue
            if status == 401:
                raise CredencialRechazada(
                    f'Binance rechazó la clave (HTTP 401, código {codigo}). Revisa la clave, '
                    'su restricción de IP y sus permisos; no se reintenta.')
            if status != 200 or codigo is not None or type(dato) not in (dict, list):
                # Solo el código numérico: el cuerpo remoto no se propaga.
                raise ErrorBinance(f'Lectura rechazada en {ruta} (HTTP {status}, código {codigo}).')
            return dato

    # --- guardia de permisos y lecturas ---

    def verificar_permisos(self) -> Permisos:
        """Debe superarse antes de cualquier lectura de cuenta. No hay forma de saltarla."""
        self._permisos = None
        self._permisos = evaluar_restricciones(self._get(RUTA_RESTRICCIONES))
        logger.info('Guardia de permisos superada: lectura sin trading ni retiros.')
        return self._permisos

    def _exigir_guardia(self) -> None:
        if self._permisos is None:
            raise PermisosInseguros('Guardia de permisos no superada: no se lee la cuenta.')

    def cuenta(self) -> dict:
        self._exigir_guardia()
        dato = self._get('/api/v3/account', {'omitZeroBalances': 'true'})
        if type(dato) is not dict:
            raise ErrorBinance('Respuesta de cuenta con formato inesperado.')
        return dato

    def ordenes_abiertas(self, simbolo: Optional[str] = None) -> list:
        self._exigir_guardia()
        dato = self._get('/api/v3/openOrders', {} if simbolo is None else {'symbol': _simbolo(simbolo)})
        if type(dato) is not list:
            raise ErrorBinance('Respuesta de órdenes abiertas con formato inesperado.')
        return dato

    def mis_trades(self, simbolo: str, *, limite: int = 500) -> list:
        self._exigir_guardia()
        if type(limite) is not int or not 1 <= limite <= 1000:
            raise ValueError('Límite de trades fuera de 1..1000.')
        dato = self._get('/api/v3/myTrades', {'symbol': _simbolo(simbolo), 'limit': str(limite)})
        if type(dato) is not list:
            raise ErrorBinance('Respuesta de trades con formato inesperado.')
        return dato


def _simbolo(valor: str) -> str:
    if type(valor) is not str or re.fullmatch(r'[A-Z0-9]{5,20}', valor) is None:
        raise ValueError('Símbolo inválido.')
    return valor


def _si_no(valor: bool) -> str:
    return 'SI' if valor else 'NO'


def main(argv: Optional[Sequence[str]] = None, *, entorno: Optional[Mapping[str, str]] = None,
         salida: Optional[TextIO] = None, transporte: Optional[Transporte] = None,
         ruta_bloqueo: Optional[Path] = None) -> int:
    """Comprobación que ejecuta el dueño. Muestra solo: conectado, permisos y nº de activos."""
    salida = salida or sys.stdout
    if argv:
        print('Uso: python binance_signed.py   (sin argumentos)', file=salida)
        return 2
    print('Binance Spot - comprobación de SOLO LECTURA (sin órdenes, sin retiros)', file=salida)
    try:
        credenciales = Credenciales.desde_entorno(entorno=entorno)
    except CredencialesAusentes as error:
        print(f'Conectado: NO\nWAITING_FOR_USER: {error}', file=salida)
        print(f'Define {VARIABLE_CLAVE} y {VARIABLE_SECRETO} en las variables de entorno de tu '
              'cuenta de Windows y abre una terminal nueva. No las pegues en ningún chat.', file=salida)
        return 2
    cliente = ClienteLectura(credenciales, transporte=transporte, ruta_bloqueo=ruta_bloqueo)
    try:
        permisos = cliente.verificar_permisos()
        activos = activos_con_saldo(cliente.cuenta())
    except PermisosInseguros as error:
        print(f'Conectado: NO\nGuardia de permisos: RECHAZADA. {error}', file=salida)
        return 1
    except ErrorBinance as error:
        print(f'Conectado: NO\nMotivo: {error}', file=salida)
        return 1
    print('Conectado: SI', file=salida)
    print(f'Permisos de la clave: lectura={_si_no(permisos.lectura)} trading={_si_no(permisos.trading)} '
          f'retiros={_si_no(permisos.retiros)} restriccion_ip={_si_no(permisos.restriccion_ip)}', file=salida)
    print(f'Activos con saldo: {activos}', file=salida)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
