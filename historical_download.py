"""Descarga explícita y acotada de velas públicas; nunca accede a cuentas."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

import pandas as pd

from analysis_engine import INTERVALOS_MS, LIMITE, validar_velas
from historical_dataset import cargar_dataset
from market_http import BASE, DatosInvalidos, get_publico


def descargar_serie(simbolo, intervalo, inicio_ms, fin_exclusivo_ms, consulta=get_publico):
    """Rango cerrado por apertura, fin exclusivo UTC; sin saltar huecos."""
    if not isinstance(simbolo, str) or not re.fullmatch(r'[A-Z0-9]{2,30}', simbolo):
        raise DatosInvalidos('Símbolo inválido.')
    if intervalo not in INTERVALOS_MS:
        raise DatosInvalidos('Intervalo no admitido.')
    paso = INTERVALOS_MS[intervalo]
    if any(type(v) is not int or not 0 < v <= 2**53 or v % paso
           for v in (inicio_ms, fin_exclusivo_ms)):
        raise DatosInvalidos('Rango UTC entero alineado requerido.')
    n = (fin_exclusivo_ms-inicio_ms)//paso
    if not 60 <= n <= 100_000:
        raise DatosInvalidos('Rango fuera del límite técnico de60–100000 velas.')
    cursor, filas, paginas = inicio_ms, [], []
    while cursor < fin_exclusivo_ms:
        parametros = dict(symbol=simbolo, interval=intervalo, limit=1000,
                          startTime=cursor, endTime=fin_exclusivo_ms-1)
        datos = consulta('/api/v3/klines', parametros)
        if not isinstance(datos, list) or not 1 <= len(datos) <= 1000:
            raise DatosInvalidos('Página vacía/inválida: no se rellena historial.')
        for fila in datos:
            if (not isinstance(fila, list) or len(fila) != 12
                    or type(fila[0]) is not int or type(fila[6]) is not int
                    or fila[0] != cursor or fila[6] != cursor+paso-1
                    or cursor >= fin_exclusivo_ms):
                raise DatosInvalidos('Página discontinua, repetida, fuera de rango o unidad temporal incorrecta.')
            filas.append(dict(tiempo_apertura=fila[0], apertura=fila[1], maximo=fila[2],
                              minimo=fila[3], cierre=fila[4], volumen=fila[5], tiempo_cierre=fila[6]))
            cursor += paso
        paginas.append({'parametros': parametros, 'filas': len(datos),
                        'respuesta_sha256': hashlib.sha256(json.dumps(datos, separators=(',', ':'),
                                                    allow_nan=False).encode()).hexdigest()})
    validar_velas(pd.DataFrame(filas), intervalo, fin_exclusivo_ms)
    return filas, paginas


def _guardar_nuevo(ruta, dato):
    contenido = json.dumps(dato, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    with ruta.open('xb') as f:
        f.write(contenido)
    return hashlib.sha256(contenido).hexdigest()


def crear_dataset(simbolo, inicio_evaluacion_ms, fin_exclusivo_ms, destino,
                  consulta=get_publico, ahora_ms=None, dormir=time.sleep):
    ahora_ms = int(time.time()*1000) if ahora_ms is None else ahora_ms
    dia = 86_400_000
    if (type(inicio_evaluacion_ms) is not int or type(fin_exclusivo_ms) is not int
            or inicio_evaluacion_ms % dia or fin_exclusivo_ms % dia
            or not 0 < inicio_evaluacion_ms < fin_exclusivo_ms <= ahora_ms
            or fin_exclusivo_ms-inicio_evaluacion_ms > 366*dia):
        raise DatosInvalidos('Evaluación exige días UTC completos del pasado, máximo366.')
    if not isinstance(simbolo, str) or not re.fullmatch(r'[A-Z0-9]{2,30}', simbolo):
        raise DatosInvalidos('Símbolo inválido.')
    raiz = Path(destino)
    raiz.mkdir(parents=True, exist_ok=False)  # Nunca reutiliza/sobrescribe una descarga.
    _guardar_nuevo(raiz/'solicitud.json', {'simbolo':simbolo, 'inicio_evaluacion_ms':inicio_evaluacion_ms,
                   'fin_exclusivo_ms':fin_exclusivo_ms, 'calentamiento_velas':LIMITE,
                   'estado':'SOLICITUD_NO_ACREDITA_COMPLETITUD'})
    manifiesto = dict(version=1, simbolo=simbolo, origen_declarado=BASE+'/api/v3/klines', series={})
    evidencia = {'fuente':BASE+'/api/v3/klines', 'obtenido_utc':datetime.now(timezone.utc).isoformat(),
                 'inicio_evaluacion_ms':inicio_evaluacion_ms, 'fin_exclusivo_ms':fin_exclusivo_ms,
                 'calentamiento_velas':LIMITE, 'paginas':{}, 'autenticidad_independiente':False}
    for intervalo, paso in INTERVALOS_MS.items():
        filas, paginas = descargar_serie(simbolo, intervalo, inicio_evaluacion_ms-LIMITE*paso,
                                         fin_exclusivo_ms, consulta)
        nombre = intervalo+'.json'
        digest = _guardar_nuevo(raiz/nombre, filas)
        manifiesto['series'][intervalo] = dict(archivo=nombre, sha256=digest, filas=len(filas),
                       inicio_ms=filas[0]['tiempo_apertura'], fin_ms=filas[-1]['tiempo_cierre'])
        evidencia['paginas'][intervalo] = paginas
        dormir(.25)
    _guardar_nuevo(raiz/'procedencia.json', evidencia)
    _guardar_nuevo(raiz/'manifest.json', manifiesto)  # Sólo aparece tras las tres series completas.
    cargar_dataset(raiz/'manifest.json')
    return raiz/'manifest.json'


def fecha_ms(texto):
    return int(datetime.strptime(texto, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()*1000)


def main():
    parser = argparse.ArgumentParser(description='Sólo historial público, sin trading ni claves.')
    parser.add_argument('--simbolo', required=True)
    parser.add_argument('--inicio', required=True, type=fecha_ms)
    parser.add_argument('--fin-exclusivo', required=True, type=fecha_ms)
    parser.add_argument('--destino', required=True)
    a = parser.parse_args()
    print(crear_dataset(a.simbolo, a.inicio, a.fin_exclusivo, a.destino), flush=True)


if __name__ == '__main__': main()
