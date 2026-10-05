"""H2: lector JSON local de sólo lectura; huella no implica autenticidad."""
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from analysis_engine import TEMPORALIDADES, validar_velas
from historical_analysis import analizar_instante
from market_http import DatosInvalidos


def _pares(pares):
    resultado = {}
    for clave, valor in pares:
        if clave in resultado:
            raise DatosInvalidos('Clave JSON duplicada.')
        resultado[clave] = valor
    return resultado


def _constante(_):
    raise DatosInvalidos('Constante JSON no finita.')


def _leer(ruta, limite):
    try:
        with ruta.open('rb') as archivo:
            contenido = archivo.read(limite + 1)
        if len(contenido) > limite:
            raise DatosInvalidos('Archivo supera límite de lectura.')
        datos = json.loads(contenido.decode('utf-8'), object_pairs_hook=_pares,
                           parse_constant=_constante)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise DatosInvalidos('No se puede leer JSON histórico válido.') from exc
    return datos, hashlib.sha256(contenido).hexdigest()


def _campos(datos, nombres):
    if not isinstance(datos, dict) or set(datos) != set(nombres):
        raise DatosInvalidos('Campos de manifiesto incorrectos.')


def cargar_dataset(manifiesto):
    """Carga tres tablas sin ordenar/rellenar datos ni escribir archivos.

Manifiesto v1: version, simbolo, origen_declarado, series. Cada marco lleva
archivo (nombre JSON hermano), sha256, filas, inicio_ms y fin_ms inclusive.
Tablas: lista de objetos con los siete campos canónicos de OHLCV/tiempo.
Origen es declaración del aportante, no validación de proveedor/exchange.
"""
    ruta = Path(manifiesto).resolve(strict=True)
    if ruta.suffix != '.json':
        raise DatosInvalidos('Manifiesto debe ser JSON explícito.')
    m, digest = _leer(ruta, 65_536)
    _campos(m, ('version', 'simbolo', 'origen_declarado', 'series'))
    if type(m['version']) is not int or m['version'] != 1:
        raise DatosInvalidos('Versión de manifiesto no soportada.')
    if not isinstance(m['simbolo'], str) or not re.fullmatch(r'[A-Z0-9]{2,30}', m['simbolo']):
        raise DatosInvalidos('Símbolo inválido.')
    if not isinstance(m['origen_declarado'], str) or not m['origen_declarado'].strip():
        raise DatosInvalidos('Origen declarado requerido.')
    _campos(m['series'], TEMPORALIDADES)
    tablas = {}
    campos_vela = {'tiempo_apertura', 'tiempo_cierre', 'apertura', 'maximo',
                   'minimo', 'cierre', 'volumen'}
    for intervalo in TEMPORALIDADES:
        item = m['series'][intervalo]
        _campos(item, ('archivo', 'sha256', 'filas', 'inicio_ms', 'fin_ms'))
        nombre = item['archivo']
        if (not isinstance(nombre, str)
                or not re.fullmatch(r'[A-Za-z0-9_-]+\.json', nombre)):
            raise DatosInvalidos('Sólo nombres JSON hermanos, sin rutas.')
        try:
            archivo = (ruta.parent / nombre).resolve(strict=True)
        except OSError as exc:
            raise DatosInvalidos('Falta archivo de serie.') from exc
        if archivo.parent != ruta.parent or archivo == ruta:
            raise DatosInvalidos('Archivo fuera de carpeta o apunta al manifiesto.')
        if not isinstance(item['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
            raise DatosInvalidos('Huella SHA256 inválida.')
        for campo in ('filas', 'inicio_ms', 'fin_ms'):
            if type(item[campo]) is not int or not 0 < item[campo] <= 2**53:
                raise DatosInvalidos('Conteo/rango entero positivo requerido.')
        datos, huella = _leer(archivo, 8_388_608)
        if huella != item['sha256']:
            raise DatosInvalidos('Huella de serie no coincide.')
        if (not isinstance(datos, list) or len(datos) != item['filas']
                or len(datos) < 60
                or any(not isinstance(f, dict) or set(f) != campos_vela for f in datos)):
            raise DatosInvalidos('Filas o campos de serie inválidos.')
        # Valida TODA la serie, no sólo la ventana elegida de H1.
        df = validar_velas(pd.DataFrame(datos), intervalo, item['fin_ms'] + 1)
        if (len(df) != len(datos) or int(df.iloc[0]['tiempo_apertura']) != item['inicio_ms']
                or int(df.iloc[-1]['tiempo_cierre']) != item['fin_ms']):
            raise DatosInvalidos('Rango declarado no coincide con serie cerrada.')
        tablas[intervalo] = df
    return {'manifiesto': m, 'manifiesto_sha256': digest, 'series': tablas,
            'procedencia_verificada': False}


def analizar_dataset(manifiesto, instante_ms):
    dataset = cargar_dataset(manifiesto)
    resultado = analizar_instante(dataset['manifiesto']['simbolo'], dataset['series'], instante_ms)
    resultado['dataset'] = {
        'manifiesto_sha256': dataset['manifiesto_sha256'],
        'origen_declarado': dataset['manifiesto']['origen_declarado'],
        'procedencia_verificada': False,
    }
    return resultado
