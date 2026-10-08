"""Frecuencias por fecha de señal UTC desde dos archivos fijados externamente.

No importa evaluadores, indicadores, conectores ni almacenamiento operativo.
No comprueba OHLC ni vuelve a evaluar resultados: resume evidencia guardada.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re

PASO_MS = 900_000
DIA_MS = 86_400_000
MODELO_ENTRADA = 'PRECIO_APORTADO_AL_INICIO_15M_HIPOTETICO_V1'
MODELO_SALIDA = 'BARRERA_TOQUE_APERTURA_SALTO_SIN_DESLIZAMIENTO_V1'
SELECCION = 'PRIMERA_SENAL_DE_CADA_EPISODIO'
CATEGORIAS = ('OBJETIVO_PRIMERO', 'STOP_PRIMERO', 'AMBIGUO', 'SIN_SALIDA_EN_RANGO')
EVENTOS = {
    'SOLO_OBJETIVO_OBSERVADO': 'OBJETIVO_PRIMERO',
    'APERTURA_EN_O_SOBRE_OBJETIVO': 'OBJETIVO_PRIMERO',
    'SOLO_STOP_OBSERVADO': 'STOP_PRIMERO',
    'APERTURA_EN_O_BAJO_STOP': 'STOP_PRIMERO',
    'AMBIGUO_AMBOS_NIVELES': 'AMBIGUO',
}


def _exigir(condicion, mensaje):
    if not condicion:
        raise ValueError(mensaje)


def _objeto(dato, campos):
    _exigir(isinstance(dato, dict) and set(campos) <= dato.keys(),
            'Estructura incompleta o desconocida.')


def _hash(dato):
    return hashlib.sha256(json.dumps(dato, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _sin_duplicados(pares):
    dato = {}
    for clave, valor in pares:
        _exigir(clave not in dato, 'Clave JSON duplicada.')
        dato[clave] = valor
    return dato


def _real(texto):
    numero = float(texto)
    _exigir(math.isfinite(numero), 'JSON contiene un número no finito.')
    return numero


def _leer(ruta, esperado):
    _exigir(isinstance(esperado, str) and re.fullmatch('[0-9a-f]{64}', esperado),
            'Se requiere SHA256 externo explícito en hexadecimal minúsculo.')
    with Path(ruta).open('rb') as archivo:
        contenido = archivo.read(64 * 1024 * 1024 + 1)
    _exigir(len(contenido) <= 64 * 1024 * 1024, 'Archivo superior a64MiB.')
    _exigir(hashlib.sha256(contenido).hexdigest() == esperado,
            'Archivo no coincide con SHA256 externo esperado.')
    return json.loads(contenido, object_pairs_hook=_sin_duplicados,
                      parse_constant=_real, parse_float=_real)


def _fecha(valor):
    _exigir(type(valor) is int and 0 < valor < 253402300800000,
            'Fecha UTC debe ser un entero de milisegundos válido; no booleano.')
    return valor


def _fechas(dato):
    """Valida tipos incluso en fechas anidadas que sólo se copian como evidencia."""
    if isinstance(dato, dict):
        for clave, valor in dato.items():
            if clave.endswith('_ms'):
                _fecha(valor)
            _fechas(valor)
    elif isinstance(dato, list):
        for valor in dato:
            _fechas(valor)


def _conteos(dato, esperado):
    _exigir(isinstance(dato, dict) and all(type(v) is int and v >= 0 for v in dato.values())
            and dato == dict(esperado), 'Conteos guardados inconsistentes.')


def _numero(valor, *, cero=False):
    _exigir(type(valor) in (int, float) and math.isfinite(valor)
            and (valor >= 0 if cero else valor > 0), 'Número de caso inválido.')
    return valor


def _validar_replay(replay):
    _objeto(replay, ('tipo', 'simbolo', 'manifiesto_sha256', 'inicio_ms', 'fin_exclusivo_ms',
                     'paso_ms', 'filas', 'filas_sha256', 'evaluaciones',
                     'condiciones_cumplidas', 'episodios_condicion', 'estados'))
    _exigir(replay['tipo'] == 'REPLAY_SENALES_NO_EJECUTABLE_V1'
            and replay['simbolo'] in ('BTCUSDT', 'ETHUSDT'), 'Formato/símbolo de replay no admitido.')
    inicio, fin = _fecha(replay['inicio_ms']), _fecha(replay['fin_exclusivo_ms'])
    _exigir(inicio % PASO_MS == fin % PASO_MS == 0 and 0 < fin - inicio <= 366 * DIA_MS
            and type(replay['paso_ms']) is int and replay['paso_ms'] == PASO_MS,
            'Rango o malla15m inválidos.')
    filas = replay['filas']
    _exigir(isinstance(filas, list) and len(filas) == (fin - inicio) // PASO_MS
            and type(replay['evaluaciones']) is int and replay['evaluaciones'] == len(filas),
            'Cantidad de filas inválida.')
    _exigir(_hash(filas) == replay['filas_sha256'], 'SHA256 de filas inválido.')
    estados, episodios, condiciones, anterior = Counter(), [], 0, False
    for i, fila in enumerate(filas):
        _objeto(fila, ('instante_utc_ms', 'cumple_condicion_tecnica', 'analisis', 'ventanas'))
        _objeto(fila['analisis'], ('simbolo', 'estado'))
        _exigir(type(fila['instante_utc_ms']) is int
                and fila['instante_utc_ms'] == inicio + i * PASO_MS,
                'Replay con fechas repetidas, fuera de orden o huecos.')
        _exigir(fila['analisis']['simbolo'] == replay['simbolo']
                and isinstance(fila['analisis']['estado'], str), 'Identidad de fila inválida.')
        cumple = fila['cumple_condicion_tecnica']
        _exigir(type(cumple) is bool, 'Condición de señal no booleana.')
        if cumple and not anterior:
            episodios.append(fila['instante_utc_ms'])
        condiciones += int(cumple)
        anterior = cumple
        estados[fila['analisis']['estado']] += 1
    _conteos(replay['estados'], estados)
    for clave, cantidad in (('condiciones_cumplidas', condiciones), ('episodios_condicion', len(episodios))):
        _exigir(type(replay[clave]) is int and replay[clave] == cantidad, 'Conteo de replay inválido.')
    return {fila['instante_utc_ms']: fila for fila in filas}, episodios


def _resultado(caso, resultado, fila, simbolo):
    _objeto(resultado, ('tipo', 'ejecutable', 'fill_confirmado', 'modelo_entrada', 'modelo_salida',
                        'entrada_hipotetica', 'senal', 'plan_hipotetico', 'trayectoria', 'estado'))
    _exigir(resultado['tipo'] == 'CASO_HISTORICO_AISLADO_NO_EJECUTABLE'
            and resultado['estado'] == 'CASO_HIPOTETICO_EVALUADO'
            and resultado['ejecutable'] is False and resultado['fill_confirmado'] is False
            and resultado['modelo_entrada'] == MODELO_ENTRADA
            and resultado['modelo_salida'] == MODELO_SALIDA, 'Formato de resultado no admitido.')
    entrada = resultado['entrada_hipotetica']
    _objeto(entrada, ('instante_ms', 'precio_aportado'))
    _exigir(entrada['instante_ms'] == caso['instante_entrada_ms']
            and _numero(entrada['precio_aportado']) == caso['precio_entrada'], 'Entrada desalineada.')
    senal = resultado['senal']
    _objeto(senal, ('analisis_historico', 'comision_pct_aportada'))
    evidencia = senal['analisis_historico']
    _objeto(evidencia, ('instante_utc_ms', 'analisis', 'ventanas'))
    _exigir(evidencia['instante_utc_ms'] == caso['instante_senal_ms']
            and _hash(evidencia['analisis']) == _hash(fila['analisis'])
            and _hash(evidencia['ventanas']) == _hash(fila['ventanas']),
            'Caso/resultado no corresponden a la misma señal del replay.')
    plan = resultado['plan_hipotetico']
    _objeto(plan, ('simbolo', 'capital', 'comision_paper_pct', 'entrada'))
    _exigir(plan['simbolo'] == simbolo and _numero(plan['capital']) == caso['capital']
            and _numero(plan['entrada']) == caso['precio_entrada']
            and _numero(plan['comision_paper_pct'], cero=True) == caso['comision_pct']
            and _numero(senal['comision_pct_aportada'], cero=True) == caso['comision_pct'],
            'Parámetros del resultado distintos del caso.')
    trayectoria = resultado['trayectoria']
    _objeto(trayectoria, ('tipo', 'modelo', 'inicio_ms', 'fin_exclusivo_ms', 'estado', 'evento',
                          'entrada_aportada', 'comision_pct_aportada', 'escenarios'))
    _exigir(trayectoria['tipo'] == 'TRAYECTORIA_HIPOTETICA_NO_EJECUTABLE'
            and trayectoria['modelo'] == MODELO_SALIDA
            and trayectoria['inicio_ms'] == caso['instante_entrada_ms']
            and trayectoria['fin_exclusivo_ms'] == caso['fin_exclusivo_ms']
            and _numero(trayectoria['entrada_aportada']) == caso['precio_entrada']
            and _numero(trayectoria['comision_pct_aportada'], cero=True) == caso['comision_pct'],
            'Trayectoria desalineada del caso.')
    evento = trayectoria['evento']
    if trayectoria['estado'] == 'SIN_SALIDA_EN_RANGO':
        _exigir(evento is None and trayectoria['escenarios'] == {}, 'Sin salida con evento/escenario.')
        return 'SIN_SALIDA_EN_RANGO', 'SIN_EVENTO', trayectoria['estado']
    _objeto(evento, ('primera_apertura_ms', 'cierre_ms', 'diagnostico'))
    _objeto(evento['diagnostico'], ('estado',))
    apertura = _fecha(evento['primera_apertura_ms'])
    _exigir(apertura % PASO_MS == 0 and caso['instante_entrada_ms'] <= apertura
            and evento['cierre_ms'] == apertura + PASO_MS - 1
            and evento['cierre_ms'] < caso['fin_exclusivo_ms'], 'Evento fuera del rango del caso.')
    nombre = evento['diagnostico']['estado']
    _exigir(isinstance(nombre, str) and nombre in EVENTOS, 'Evento desconocido.')
    categoria = EVENTOS[nombre]
    estado = 'DOS_SALIDAS_HIPOTETICAS' if categoria == 'AMBIGUO' else 'SALIDA_HIPOTETICA'
    _exigir(trayectoria['estado'] == estado, 'Estado y evento incompatibles.')
    return categoria, nombre, estado


def _validar_informe(informe, replay, digest_replay):
    indice, episodios = _validar_replay(replay)
    _objeto(informe, ('tipo', 'ejecutable', 'simbolo', 'replay_sha256', 'manifiesto_sha256',
                      'casos_sha256', 'casos_aportados', 'resultados', 'modelo_entrada',
                      'modelo_salida', 'seleccion_diagnostica', 'entrada_diagnostica', 'resumen'))
    _exigir(informe['tipo'] == 'LOTE_CASOS_AISLADOS_NO_EJECUTABLE'
            and informe['ejecutable'] is False and informe['simbolo'] == replay['simbolo']
            and informe['modelo_entrada'] == MODELO_ENTRADA and informe['modelo_salida'] == MODELO_SALIDA
            and informe['seleccion_diagnostica'] == SELECCION
            and isinstance(informe['entrada_diagnostica'], str) and informe['entrada_diagnostica'],
            'Formato/modelo de informe no admitido.')
    _exigir(informe['replay_sha256'] == digest_replay
            and informe['manifiesto_sha256'] == replay['manifiesto_sha256'], 'Referencia a replay distinta.')
    casos, resultados = informe['casos_aportados'], informe['resultados']
    _exigir(isinstance(casos, list) and isinstance(resultados, list)
            and 0 < len(casos) <= 1000 and len(casos) == len(resultados), 'Cantidad de casos/resultados inválida.')
    _exigir(_hash(casos) == informe['casos_sha256'], 'SHA256 de casos incompatible.')
    registros, estados, eventos = [], Counter(), Counter()
    for caso, resultado in zip(casos, resultados):
        _objeto(caso, ('instante_senal_ms', 'instante_entrada_ms', 'fin_exclusivo_ms',
                       'precio_entrada', 'capital', 'comision_pct'))
        senal, entrada, fin = (_fecha(caso[k]) for k in ('instante_senal_ms', 'instante_entrada_ms', 'fin_exclusivo_ms'))
        _exigir(senal in indice and entrada % PASO_MS == fin % PASO_MS == 0
                and senal <= entrada < fin <= replay['fin_exclusivo_ms'], 'Cronología del caso inválida.')
        _numero(caso['precio_entrada']); _numero(caso['capital'])
        _exigir(_numero(caso['comision_pct'], cero=True) < 100, 'Comisión inválida.')
        categoria, evento, estado = _resultado(caso, resultado, indice[senal], informe['simbolo'])
        registros.append((senal, categoria))
        estados[estado] += 1
        eventos[evento] += 1
    _exigir([r[0] for r in registros] == episodios,
            'Casos repetidos, fuera de orden o distintos de primeras señales de episodio.')
    resumen = informe['resumen']
    _objeto(resumen, ('casos', 'estados', 'eventos'))
    _exigir(type(resumen['casos']) is int and resumen['casos'] == len(casos), 'Total de casos incompatible.')
    _conteos(resumen['estados'], estados); _conteos(resumen['eventos'], eventos)
    return registros


def _dt(ms):
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ms)


def _ms(fecha):
    return (fecha - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1)


def _iso(ms):
    return _dt(ms).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _limites(ms, frecuencia):
    fecha = _dt(ms).replace(hour=0, minute=0, second=0, microsecond=0)
    if frecuencia == 'mes':
        inicio = fecha.replace(day=1)
        fin = inicio.replace(year=inicio.year + 1, month=1) if inicio.month == 12 else inicio.replace(month=inicio.month + 1)
        etiqueta = inicio.strftime('%Y-%m')
    elif frecuencia == 'semana_iso':
        inicio = fecha - timedelta(days=fecha.weekday())
        fin = inicio + timedelta(days=7)
        ano, semana, _ = inicio.isocalendar()
        etiqueta = f'{ano:04d}-W{semana:02d}'
    elif frecuencia == 'dia':
        inicio, fin, etiqueta = fecha, fecha + timedelta(days=1), fecha.strftime('%Y-%m-%d')
    else:
        raise ValueError('Frecuencia desconocida.')
    return etiqueta, _ms(inicio), _ms(fin)


def agrupar(registros, inicio_ms, fin_exclusivo_ms, frecuencia):
    """Particiona [inicio,fin), incluyendo períodos sin señales y ambos bordes."""
    _fecha(inicio_ms); _fecha(fin_exclusivo_ms)
    _exigir(inicio_ms % PASO_MS == fin_exclusivo_ms % PASO_MS == 0
            and 0 < fin_exclusivo_ms - inicio_ms <= 366 * DIA_MS, 'Cobertura de agrupación inválida.')
    periodos, indice, cursor = [], {}, inicio_ms
    while cursor < fin_exclusivo_ms:
        etiqueta, inicio, fin = _limites(cursor, frecuencia)
        cubierto_inicio, cubierto_fin = max(inicio, inicio_ms), min(fin, fin_exclusivo_ms)
        fila = dict(periodo=etiqueta, inicio_utc=_iso(inicio), fin_exclusivo_utc=_iso(fin),
                    cobertura_inicio_utc=_iso(cubierto_inicio), cobertura_fin_exclusivo_utc=_iso(cubierto_fin),
                    parcial_inicio=inicio < inicio_ms, parcial_fin=fin > fin_exclusivo_ms,
                    evaluaciones=(cubierto_fin - cubierto_inicio) // PASO_MS,
                    casos=0, frecuencias=dict.fromkeys(CATEGORIAS, 0))
        periodos.append(fila); indice[etiqueta] = fila
        cursor = fin
    for instante, categoria in registros:
        _exigir(type(instante) is int and inicio_ms <= instante < fin_exclusivo_ms
                and instante % PASO_MS == 0 and categoria in CATEGORIAS,
                'Registro fuera de cobertura o categoría desconocida.')
        fila = indice[_limites(instante, frecuencia)[0]]
        fila['casos'] += 1
        fila['frecuencias'][categoria] += 1
    return periodos


def generar(casos, replay, *, sha256_casos_esperado, sha256_replay_esperado):
    informe = _leer(casos, sha256_casos_esperado)
    fuente = _leer(replay, sha256_replay_esperado)
    _fechas(informe); _fechas(fuente)
    registros = _validar_informe(informe, fuente, sha256_replay_esperado)
    total = Counter(categoria for _, categoria in registros)
    return dict(tipo='FRECUENCIAS_POR_PERIODO_DE_SENAL_UTC_V1', ejecutable=False,
                simbolo=informe['simbolo'], agrupacion='FECHA_DE_SENAL_UTC',
                casos_archivo_sha256=sha256_casos_esperado, replay_archivo_sha256=sha256_replay_esperado,
                casos_sha256=informe['casos_sha256'], manifiesto_sha256=informe['manifiesto_sha256'],
                codigo_informe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                seleccion_diagnostica=informe['seleccion_diagnostica'],
                entrada_diagnostica=informe['entrada_diagnostica'],
                modelo_entrada=informe['modelo_entrada'], modelo_salida=informe['modelo_salida'],
                inicio_utc=_iso(fuente['inicio_ms']), fin_exclusivo_utc=_iso(fuente['fin_exclusivo_ms']),
                resumen=dict(casos=len(registros), frecuencias={k: total[k] for k in CATEGORIAS}),
                periodos={frecuencia: agrupar(registros, fuente['inicio_ms'], fuente['fin_exclusivo_ms'], frecuencia)
                          for frecuencia in ('mes', 'semana_iso', 'dia')},
                advertencias=[
                    'Frecuencias de desenlaces por fecha de señal UTC; el desenlace puede ocurrir después del período.',
                    'No son ganancias mensuales ni resultados de cartera; no se suma P&L de casos solapados.',
                    'Cero casos sólo indica ausencia de episodios seleccionados en la cobertura; no es ausencia de datos.',
                    'Los períodos parciales sólo tienen la cobertura declarada. Semana ISO comienza lunes UTC.',
                    'No recalcula indicadores ni evalúa trayectorias; no verifica OHLC, autenticidad o vigencia del código original.',
                    'Los hashes prueban integridad respecto de valores externos; no autenticidad ni validez económica.',
                    'Casos sin salida y ambiguos conservan su categoría; no se asignan beneficios ni probabilidades.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for nombre in ('casos', 'replay', 'sha256-casos-esperado', 'sha256-replay-esperado', 'salida'):
        parser.add_argument('--' + nombre, required=True)
    args = parser.parse_args(argv)
    salida = Path(args.salida)
    if salida.exists():
        raise FileExistsError('No sobrescribir informe existente.')
    informe = generar(args.casos, args.replay, sha256_casos_esperado=args.sha256_casos_esperado,
                      sha256_replay_esperado=args.sha256_replay_esperado)
    with salida.open('x', encoding='utf-8') as archivo:
        json.dump(informe, archivo, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    print(json.dumps(dict(simbolo=informe['simbolo'], **informe['resumen'], salida=str(salida)), ensure_ascii=False))


if __name__ == '__main__':
    main()
