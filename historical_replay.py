"""Reproducción offline de señales, sin fills, cartera, red ni órdenes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from analysis_engine import LIMITE, TEMPORALIDADES, analizar_temporalidad, resumir_temporalidades
from historical_dataset import cargar_dataset
from historical_download import fecha_ms
from market_http import DatosInvalidos


def _hash(dato):
    return hashlib.sha256(json.dumps(dato, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def reproducir(manifiesto, inicio_ms, fin_exclusivo_ms):
    """Malla diagnóstica cada15m, [inicio,fin); NO horario real del scanner.

El scanner operativo espera15m después de acabar su consulta, por lo que no
coincide exactamente con esta malla. El resultado no simula radar ni ejecución.
"""
    paso = 900_000
    if (any(type(t) is not int or not 0 < t <= 2**53 or t % paso
            for t in (inicio_ms, fin_exclusivo_ms))
            or not 0 < fin_exclusivo_ms-inicio_ms <= 366*86_400_000):
        raise DatosInvalidos('Rango UTC alineado15m y máximo366d requerido.')
    ds = cargar_dataset(manifiesto)
    simbolo = ds['manifiesto']['simbolo']
    arrays = {}
    for marco, df in ds['series'].items():
        if fin_exclusivo_ms > int(df.iloc[-1]['tiempo_cierre'])+1:
            raise DatosInvalidos('El período excede cobertura común de las series.')
        arrays[marco] = (df['tiempo_apertura'].to_numpy(), df['tiempo_cierre'].to_numpy())
    cache, filas, estados = {}, [], Counter()
    episodios, anterior = 0, False
    for instante in range(inicio_ms, fin_exclusivo_ms, paso):
        resultados, ventanas = {}, {}
        for marco in TEMPORALIDADES:
            df = ds['series'][marco]
            aperturas, cierres = arrays[marco]
            # Misma ventana que H1/live:200 iniciadas; precios abiertos excluidos.
            derecha = int(aperturas.searchsorted(instante, side='right'))
            izquierda = max(0, derecha-LIMITE)
            cerradas = int(cierres.searchsorted(instante, side='left'))
            if cerradas-izquierda < 60:
                raise DatosInvalidos('Calentamiento insuficiente en la ventana.')
            clave = (izquierda, cerradas)
            if marco not in cache or cache[marco][0] != clave:
                ventana = df.iloc[izquierda:cerradas]
                cache[marco] = (clave, analizar_temporalidad(ventana, marco, instante))
            resultados[marco] = cache[marco][1]
            ventanas[marco] = {'primera_apertura_ms':int(aperturas[izquierda]),
                              'ultima_cierre_ms':int(cierres[cerradas-1]),
                              'velas_cerradas':cerradas-izquierda}
        analisis = resumir_temporalidades(simbolo, resultados)
        cumple = analisis['consenso'] == 'ALCISTA' and analisis['estado'] == 'ALCISTA MOMENTUM SANO'
        episodios += int(cumple and not anterior)
        anterior = cumple
        estados[analisis['estado']] += 1
        filas.append({'instante_utc_ms':instante, 'cumple_condicion_tecnica':cumple,
                      'analisis':analisis, 'ventanas':ventanas})
    codigo = {nombre:hashlib.sha256(Path(__file__).with_name(nombre).read_bytes()).hexdigest()
              for nombre in ('analysis_engine.py','historical_replay.py','historical_dataset.py')}
    return {'tipo':'REPLAY_SENALES_NO_EJECUTABLE_V1', 'simbolo':simbolo,
            'manifiesto_sha256':ds['manifiesto_sha256'], 'codigo_sha256':codigo,
            'inicio_ms':inicio_ms, 'fin_exclusivo_ms':fin_exclusivo_ms, 'paso_ms':paso,
            'evaluaciones':len(filas), 'condiciones_cumplidas':sum(f['cumple_condicion_tecnica'] for f in filas),
            'episodios_condicion':episodios, 'estados':dict(sorted(estados.items())),
            'filas_sha256':_hash(filas), 'filas':filas,
            'limitaciones':['Condición técnica no equivale a operación ni beneficio.',
                            'Sin radar histórico, fills, cartera, comisiones o P&L.',
                            'Malla15m no reproduce demoras del scanner operativo.',
                            'Historia retrospectiva no demuestra validación fuera de muestra.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True)
    p.add_argument('--inicio', required=True, type=fecha_ms)
    p.add_argument('--fin-exclusivo', required=True, type=fecha_ms)
    p.add_argument('--salida', required=True)
    a = p.parse_args()
    salida = Path(a.salida)
    if salida.exists():
        raise FileExistsError('No se sobrescribe informe existente.')
    informe = reproducir(a.manifest, a.inicio, a.fin_exclusivo)
    with salida.open('x', encoding='utf-8') as f:
        json.dump(informe, f, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    print(json.dumps({k:v for k,v in informe.items() if k != 'filas'}, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
