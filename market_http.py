"""Datos públicos únicamente. Sin credenciales, órdenes ni redirecciones."""
import json
import logging
import math
from pathlib import Path
import threading
import time
import uuid
import os
from contextlib import contextmanager

import requests
import config

BASE = 'https://data-api.binance.vision'
PARAMETROS = {
    '/api/v3/exchangeInfo': {'symbol'},
    '/api/v3/ticker/24hr': {'symbol'},
    '/api/v3/ticker/price': {'symbol'},
    '/api/v3/klines': {'symbol', 'interval', 'limit', 'startTime', 'endTime'},
    '/api/v3/time': set(),
    '/api/v3/depth': {'symbol', 'limit'},
}


class DatosInvalidos(ValueError):
    pass


class ErrorMercado(RuntimeError):
    pass


class MercadoBloqueado(ErrorMercado):
    pass


@contextmanager
def bloqueo_escritura(ruta):
    """Serializa actualizaciones del cooldown entre procesos sin bloquear la red."""
    archivo = ruta.with_name(ruta.name+'.lock').open('a+b')
    try:
        archivo.seek(0)
        if os.name == 'nt':
            import msvcrt
            # Windows permite bloquear más allá de EOF. No leer primero:
            # otro proceso puede tener ese byte bloqueado.
            msvcrt.locking(archivo.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(archivo, fcntl.LOCK_EX)
        yield
    finally:
        archivo.close()


def numero_finito(valor, *, positivo=False, no_negativo=False):
    if isinstance(valor, bool):
        raise DatosInvalidos('Booleano en campo numérico.')
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DatosInvalidos('Campo numérico inválido.') from exc
    if not math.isfinite(numero) or (positivo and numero <= 0) or (no_negativo and numero < 0):
        raise DatosInvalidos('Número no finito o fuera de rango.')
    return numero


class ClientePublico:
    def __init__(self, ruta_bloqueo=None, transporte=None, reloj=None, dormir=None):
        self.ruta_bloqueo = Path(ruta_bloqueo) if ruta_bloqueo else config.DIRECTORIO/'market_cooldown.json'
        self.transporte = transporte or requests.get
        self.reloj = reloj or time.time
        self.dormir = dormir or time.sleep
        self.lock = threading.Lock()
        self.bloqueo_memoria = 0.

    def comprobar_bloqueo(self):
        if self.reloj() < self.bloqueo_memoria:
            raise MercadoBloqueado('Bloqueo HTTP activo en este proceso.')
        try:
            dato = json.loads(self.ruta_bloqueo.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return
        except (ValueError, OSError) as exc:
            raise MercadoBloqueado('No se puede verificar el bloqueo de datos públicos.') from exc
        if not isinstance(dato, dict) or 'hasta' not in dato:
            raise MercadoBloqueado('Archivo de bloqueo inválido; requiere revisión local.')
        hasta = dato['hasta']
        if hasta is None:
            raise MercadoBloqueado('Bloqueo HTTP sin plazo válido; requiere revisión local.')
        try:
            hasta = numero_finito(hasta, positivo=True)
        except DatosInvalidos as exc:
            raise MercadoBloqueado('Plazo de bloqueo inválido.') from exc
        if self.reloj() < hasta:
            raise MercadoBloqueado(f'Datos públicos bloqueados hasta UTC epoch {hasta}.')

    def bloquear(self, respuesta):
        try:
            # Una restricción legal/de acceso no se libera por un temporizador.
            if respuesta.status_code == 451:
                raise DatosInvalidos('HTTP 451 requiere revisión local.')
            espera = numero_finito(respuesta.headers.get('Retry-After'), positivo=True)
            hasta = self.reloj()+espera
        except DatosInvalidos:
            hasta = None  # Nunca inventar el vencimiento de una restricción del servidor.
        if hasta is not None and not math.isfinite(hasta):
            hasta = None
        # Si falla persistir, este cliente tampoco vuelve a consultar en esta sesión.
        self.bloqueo_memoria = max(self.bloqueo_memoria, hasta if hasta is not None else math.inf)
        with self.lock, bloqueo_escritura(self.ruta_bloqueo):
            try:
                anterior = json.loads(self.ruta_bloqueo.read_text(encoding='utf-8'))
            except FileNotFoundError:
                anterior = {'hasta': 0}
            except (ValueError, OSError):
                anterior = {'hasta': None}
            previo = anterior.get('hasta') if isinstance(anterior, dict) else None
            if previo is None or hasta is None:
                hasta = None
            else:
                try:
                    hasta = max(numero_finito(previo, no_negativo=True), hasta)
                except DatosInvalidos:
                    hasta = None
            dato = {'hasta': hasta, 'status': respuesta.status_code, 'creado_epoch': self.reloj()}
            temporal = self.ruta_bloqueo.with_name(self.ruta_bloqueo.name+'.'+uuid.uuid4().hex+'.tmp')
            temporal.write_text(json.dumps(dato, allow_nan=False), encoding='utf-8')
            temporal.replace(self.ruta_bloqueo)
        logging.error('Restricción de datos públicos HTTP %s; hasta=%s', respuesta.status_code, hasta)

    def get(self, ruta, params=None, *, decodificador=None):
        params = dict(params or {})
        if ruta not in PARAMETROS or not set(params) <= PARAMETROS[ruta]:
            raise ValueError('Ruta o parámetros no permitidos para datos públicos.')
        for intento in range(2):
            self.comprobar_bloqueo()
            try:
                respuesta = self.transporte(BASE+ruta, params=params, timeout=(5, 15), allow_redirects=False)
            except (requests.Timeout, requests.ConnectionError) as exc:
                if intento == 0:
                    self.dormir(.5)
                    continue
                raise ErrorMercado('Consulta pública fallida tras 2 intentos de red.') from exc
            except requests.RequestException as exc:
                raise ErrorMercado('Consulta pública fallida.') from exc
            try:
                status = respuesta.status_code
                if status in (403, 418, 429, 451):
                    self.bloquear(respuesta)
                    raise MercadoBloqueado(f'Restricción HTTP {status}; no se reintenta esta llamada.')
                if 500 <= status < 600 and intento == 0:
                    self.dormir(.5)
                    continue
                if status != 200:
                    raise ErrorMercado(f'Consulta pública HTTP {status}.')
                try:
                    datos = respuesta.json() if decodificador is None else decodificador(respuesta.text)
                except ValueError as exc:
                    raise DatosInvalidos('Respuesta pública no es JSON válido.') from exc
                if not isinstance(datos, (dict, list)) or (isinstance(datos, dict) and 'code' in datos):
                    raise DatosInvalidos('Formato o error remoto en respuesta pública.')
                return datos
            finally:
                respuesta.close()


CLIENTE = ClientePublico()


def get_publico(ruta, params=None, *, decodificador=None):
    return CLIENTE.get(ruta, params, decodificador=decodificador)


def precio_actual(simbolo):
    datos = get_publico('/api/v3/ticker/price', {'symbol': simbolo})
    if not isinstance(datos, dict) or datos.get('symbol') != simbolo:
        raise DatosInvalidos('Símbolo de cotización no coincide.')
    return numero_finito(datos.get('price'), positivo=True)
