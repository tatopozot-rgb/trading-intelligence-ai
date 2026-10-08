"""Reconstrucción offline de análisis, NO backtest de rentabilidad ni ejecutor.

El llamante aporta tablas por temporalidad y un instante UTC en milisegundos.
No elige universo, período, capital ni modelo de fills. No descarga datos.
Se reproduce la ventana de hasta 200 velas iniciadas del motor actual; una
vela abierta ocupa una plaza, pero sus precios nunca entran al análisis.
"""
import math
import re

import pandas as pd

from analysis_engine import (
    INTERVALOS_MS, LIMITE, TEMPORALIDADES, analizar_temporalidad,
    resumir_temporalidades,
)
from market_http import DatosInvalidos


def analizar_instante(simbolo, series, instante_ms):
    """Devuelve indicadores/consenso con reloj explícito y sin efectos externos.

Exige al menos 60 velas cerradas por marco. Rechaza datos desordenados,
duplicados, huecos en la ventana e historial obsoleto; no rellena ni ordena.
El resultado no representa selección histórica del radar ni una orden.
"""
    if not isinstance(simbolo, str) or not re.fullmatch(r'[A-Z0-9]{2,30}', simbolo):
        raise DatosInvalidos('Símbolo explícito inválido.')
    if (type(instante_ms) is not int or not 0 < instante_ms <= 2**53):
        raise DatosInvalidos('Instante UTC debe ser entero positivo en milisegundos.')
    if not isinstance(series, dict) or set(series) != set(TEMPORALIDADES):
        raise DatosInvalidos('Se requieren exactamente 15m, 1h y 4h.')
    resultados, ventanas = {}, {}
    for intervalo in TEMPORALIDADES:
        df = series[intervalo]
        if not isinstance(df, pd.DataFrame) or df.empty or not df.columns.is_unique:
            raise DatosInvalidos('Tabla vacía, inválida o columnas duplicadas.')
        paso = INTERVALOS_MS[intervalo]
        tiempos = {}
        for campo in ('tiempo_apertura', 'tiempo_cierre'):
            if campo not in df:
                raise DatosInvalidos('Faltan timestamps históricos.')
            if any(isinstance(v, bool) for v in df[campo].tolist()):
                raise DatosInvalidos('Timestamp booleano.')
            try:
                s = pd.to_numeric(df[campo], errors='raise')
                validos = all(math.isfinite(float(v)) and 0 < v <= 2**53
                              and v % 1 == 0 for v in s)
            except (ValueError, TypeError, OverflowError) as exc:
                raise DatosInvalidos('Timestamp histórico inválido.') from exc
            if not validos:
                raise DatosInvalidos('Timestamp histórico inválido.')
            tiempos[campo] = s
        aperturas, cierres = tiempos['tiempo_apertura'], tiempos['tiempo_cierre']
        if ((aperturas % paso != 0).any() or (aperturas.diff().iloc[1:] <= 0).any()
                or (cierres != aperturas + paso - 1).any()):
            raise DatosInvalidos('Orden, duplicado o intervalo histórico inválido.')
        # Selección temporal antes de leer precios: nunca usa el OHLC futuro.
        elegibles = df.loc[aperturas <= instante_ms].tail(LIMITE).copy()
        elegibles['tiempo_cierre'] = pd.to_numeric(elegibles['tiempo_cierre'])
        cerradas = elegibles.loc[elegibles['tiempo_cierre'] < instante_ms].copy()
        if len(cerradas) < 60:
            raise DatosInvalidos('Se requieren 60 velas cerradas por temporalidad.')
        resultados[intervalo] = analizar_temporalidad(cerradas, intervalo, instante_ms)
        ventanas[intervalo] = {
            'velas_cerradas': len(cerradas),
            'primera_apertura_ms': int(cerradas.iloc[0]['tiempo_apertura']),
            'ultima_cierre_ms': int(cerradas.iloc[-1]['tiempo_cierre']),
        }
    return {
        'tipo': 'ANALISIS_HISTORICO_OFFLINE_NO_EJECUTABLE',
        'instante_utc_ms': instante_ms,
        'ventanas': ventanas,
        'analisis': resumir_temporalidades(simbolo, resultados),
        'limitaciones': ['No simula fills, comisiones ni P&L.',
                         'No reconstruye selección del radar ni disponibilidad histórica del activo.',
                         'No certifica datos ni validación fuera de muestra.'],
    }
