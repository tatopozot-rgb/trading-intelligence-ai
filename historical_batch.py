"""Casos aislados desde replay H4 comprobado; sin recalcular indicadores."""
from collections import Counter
import copy
import hashlib
import math
from pathlib import Path

from analysis_engine import LIMITE, TEMPORALIDADES, resumir_temporalidades
from historical_dataset import cargar_dataset, _leer, _campos
from historical_replay import _hash
from historical_case import _evaluar_caso, MODELO_ENTRADA, MODELO_SALIDA
from historical_path import PASO_MS
from historical_proposal import _proponer_evidencia
from market_http import DatosInvalidos


def _entero(v):
    return type(v) is int and 0 < v <= 2**53


def cargar_replay(manifiesto, replay, *, sha256_replay_esperado):
    """El hash esperado lo fija el llamante fuera del JSON; no autentica fuente.

    Comprueba estructura y coherencia con datos/código, NO recalcula EMA/RSI/ATR.
    Un generador adulterado o un hash externo no confiable quedan fuera de alcance.
    """
    r, digest = _leer(Path(replay), 64*1024*1024)
    if not isinstance(sha256_replay_esperado, str) or digest != sha256_replay_esperado:
        raise DatosInvalidos('Replay no coincide con huella externa esperada.')
    _campos(r, ('tipo','simbolo','manifiesto_sha256','codigo_sha256','inicio_ms',
                'fin_exclusivo_ms','paso_ms','evaluaciones','condiciones_cumplidas',
                'episodios_condicion','estados','filas_sha256','filas','limitaciones'))
    if r['tipo'] != 'REPLAY_SENALES_NO_EJECUTABLE_V1':
        raise DatosInvalidos('Tipo de replay no admitido.')
    ds = cargar_dataset(manifiesto)
    simbolo = ds['manifiesto']['simbolo']
    if r['simbolo'] != simbolo or r['manifiesto_sha256'] != ds['manifiesto_sha256']:
        raise DatosInvalidos('Identidad de replay/manifiesto incompatible.')
    codigo = {n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
              for n in ('analysis_engine.py','historical_replay.py','historical_dataset.py')}
    if r['codigo_sha256'] != codigo:
        raise DatosInvalidos('Código generador distinto; revisar antes de reutilizar.')
    inicio, fin = r['inicio_ms'], r['fin_exclusivo_ms']
    if (not all(_entero(t) and t % PASO_MS == 0 for t in (inicio, fin))
            or not 0 < fin-inicio <= 366*86400000
            or type(r['paso_ms']) is not int or r['paso_ms'] != PASO_MS
            or not isinstance(r['filas'], list) or len(r['filas']) != (fin-inicio)//PASO_MS
            or type(r['evaluaciones']) is not int or r['evaluaciones'] != len(r['filas'])):
        raise DatosInvalidos('Rango, cantidad o malla de replay inválidos.')
    try:
        if _hash(r['filas']) != r['filas_sha256']:
            raise DatosInvalidos('Huella de filas incompatible.')
    except (ValueError, TypeError) as exc:
        raise DatosInvalidos('Filas no serializables o no finitas.') from exc
    arrays = {}
    for marco, df in ds['series'].items():
        if fin > int(df.iloc[-1]['tiempo_cierre'])+1:
            raise DatosInvalidos('Replay excede cobertura.')
        arrays[marco] = (df.tiempo_apertura.to_numpy(), df.tiempo_cierre.to_numpy(),
                         df.cierre.to_numpy())
    estados, condiciones, episodios, anterior = Counter(), 0, 0, False
    for i, fila in enumerate(r['filas']):
        _campos(fila, ('instante_utc_ms','cumple_condicion_tecnica','analisis','ventanas'))
        t = inicio+i*PASO_MS
        if type(fila['instante_utc_ms']) is not int or fila['instante_utc_ms'] != t:
            raise DatosInvalidos('Filas fuera de orden, repetidas o huecos.')
        a = fila['analisis']
        _campos(a, ('simbolo','consenso','estado','temporalidades'))
        _campos(a['temporalidades'], TEMPORALIDADES)
        _campos(fila['ventanas'], TEMPORALIDADES)
        if a['simbolo'] != simbolo:
            raise DatosInvalidos('Símbolo de fila incompatible.')
        for marco in TEMPORALIDADES:
            aperturas, cierres, precios = arrays[marco]
            izquierda = max(0,int(aperturas.searchsorted(t,side='right'))-LIMITE)
            cerradas = int(cierres.searchsorted(t,side='left'))
            if cerradas-izquierda < 60:
                raise DatosInvalidos('Calentamiento insuficiente.')
            ventana = dict(primera_apertura_ms=int(aperturas[izquierda]),
                           ultima_cierre_ms=int(cierres[cerradas-1]), velas_cerradas=cerradas-izquierda)
            v = fila['ventanas'][marco]
            _campos(v, ventana)
            if any(type(x) is not int for x in v.values()) or v != ventana:
                raise DatosInvalidos('Ventana adulterada o con anticipación.')
            d = a['temporalidades'][marco]
            _campos(d, ('precio','ema20','ema50','rsi','atr','atr_pct','tendencia','vela_cierre_utc_ms'))
            for campo in ('precio','ema20','ema50','rsi','atr','atr_pct'):
                x = d[campo]
                if type(x) not in (int,float) or not math.isfinite(x) or x < 0:
                    raise DatosInvalidos('Indicador numérico inválido.')
            if (d['precio'] <= 0 or d['ema20'] <= 0 or d['ema50'] <= 0 or d['rsi'] > 100
                    or type(d['vela_cierre_utc_ms']) is not int
                    or d['vela_cierre_utc_ms'] != ventana['ultima_cierre_ms']
                    or d['precio'] != float(precios[cerradas-1])
                    or not math.isclose(d['atr_pct'], d['atr']/d['precio']*100,rel_tol=1e-12,abs_tol=1e-12)):
                raise DatosInvalidos('Precio/cierre/ATR de fila incoherentes.')
            tendencia = ('ALCISTA' if d['precio'] > d['ema20'] > d['ema50'] else
                         'BAJISTA' if d['precio'] < d['ema20'] < d['ema50'] else 'MIXTA')
            if d['tendencia'] != tendencia:
                raise DatosInvalidos('Tendencia inconsistente.')
        if resumir_temporalidades(simbolo,a['temporalidades']) != a:
            raise DatosInvalidos('Resumen técnico inconsistente.')
        cumple = a['consenso']=='ALCISTA' and a['estado']=='ALCISTA MOMENTUM SANO'
        if type(fila['cumple_condicion_tecnica']) is not bool or fila['cumple_condicion_tecnica'] != cumple:
            raise DatosInvalidos('Condición técnica inconsistente.')
        condiciones += int(cumple); episodios += int(cumple and not anterior); anterior= cumple
        estados[a['estado']] += 1
    if (any(type(r[k]) is not int for k in ('condiciones_cumplidas','episodios_condicion'))
            or r['condiciones_cumplidas'] != condiciones or r['episodios_condicion'] != episodios
            or not isinstance(r['estados'],dict) or any(type(v) is not int for v in r['estados'].values())
            or r['estados'] != dict(estados)):
        raise DatosInvalidos('Conteos inconsistentes.')
    return ds, r, digest


def evaluar_lote(manifiesto, replay, casos, *, sha256_replay_esperado,
                  modelo_entrada, modelo_salida):
    if modelo_entrada != MODELO_ENTRADA or modelo_salida != MODELO_SALIDA:
        raise DatosInvalidos('Modelos explícitos no admitidos.')
    if not isinstance(casos,list) or not 0 < len(casos) <= 1000:
        raise DatosInvalidos('Lista explícita de1 a1000 casos requerida.')
    ds, r, digest = cargar_replay(manifiesto,replay,sha256_replay_esperado=sha256_replay_esperado)
    indice = {f['instante_utc_ms']:f for f in r['filas']}
    campos = ('instante_senal_ms','instante_entrada_ms','fin_exclusivo_ms',
              'precio_entrada','capital','comision_pct')
    casos = copy.deepcopy(casos)
    for c in casos:
        _campos(c,campos)
        if not _entero(c['instante_senal_ms']) or c['instante_senal_ms'] not in indice:
            raise DatosInvalidos('Señal solicitada fuera del replay.')
        if not _entero(c['fin_exclusivo_ms']) or c['fin_exclusivo_ms'] > r['fin_exclusivo_ms']:
            raise DatosInvalidos('Fin de caso fuera de cobertura declarada del replay.')
    resultados = []
    for c in casos:
        fila = indice[c['instante_senal_ms']]
        evidencia = dict(tipo='ANALISIS_HISTORICO_OFFLINE_NO_EJECUTABLE',
                         instante_utc_ms=c['instante_senal_ms'], ventanas=copy.deepcopy(fila['ventanas']),
                         analisis=copy.deepcopy(fila['analisis']),
                         limitaciones=['No simula fills, comisiones ni P&L.',
                          'No reconstruye selección del radar ni disponibilidad histórica del activo.',
                          'No certifica datos ni validación fuera de muestra.'])
        señal = _proponer_evidencia(r['simbolo'],evidencia,capital=c['capital'],comision_pct=c['comision_pct'])
        resultados.append(_evaluar_caso(r['simbolo'],ds['series'],**c,
                          modelo_entrada=modelo_entrada,modelo_salida=modelo_salida,_senal=señal))
    return dict(tipo='LOTE_CASOS_AISLADOS_NO_EJECUTABLE',ejecutable=False,
                replay_sha256=digest,manifiesto_sha256=ds['manifiesto_sha256'],
                casos_sha256=_hash(casos),casos_aportados=casos,resultados=resultados,
                modelo_entrada=modelo_entrada,modelo_salida=modelo_salida,
                codigo_evaluacion_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
                  for n in ('historical_batch.py','historical_case.py','historical_path.py',
                            'historical_proposal.py','historical_economics.py','trade_planner.py',
                            'risk_engine.py','paper_store.py','config.py')},
                autenticidad_verificada=False,indicadores_recalculados=False,
                advertencias=['Casos independientes y posiblemente solapados: no sumar P&L de cartera.',
                              'No certifica ausencia de selección retrospectiva de casos ni autenticidad.'])
