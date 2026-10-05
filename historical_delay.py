"""Estrés pareado de entrada+15m; no latencia calibrada ni cartera operativa."""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

from historical_batch import cargar_replay, evaluar_lote
from historical_batch_report import ENTRADA
from historical_case import MODELO_ENTRADA, MODELO_SALIDA
from historical_path import PASO_MS
import historical_periods as periodos

ESCENARIO = 'ENTRADA_MAS_UNA_VELA_15M_APERTURA_HIPOTETICA'
CODIGO_BASE = ('historical_batch.py', 'historical_case.py', 'historical_path.py',
               'historical_proposal.py', 'historical_economics.py', 'trade_planner.py',
               'risk_engine.py', 'paper_store.py', 'config.py')


def _huellas(nombres):
    return {n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in nombres}


def preparar_retraso(casos, serie, *, escenario):
    """Casos validados previamente; mantiene índice incluso si no hay horizonte."""
    if escenario != ESCENARIO:
        raise ValueError('Escenario de estrés explícito no admitido.')
    aperturas = {int(t): float(p) for t, p in zip(serie.tiempo_apertura, serie.apertura)}
    seleccion, excluidos = [], []
    for indice, original in enumerate(casos):
        t, fin = original['instante_entrada_ms'], original['fin_exclusivo_ms']
        if (type(t) is not int or type(fin) is not int or t % PASO_MS or fin % PASO_MS
                or t != original['instante_senal_ms'] or not 0 < t < fin):
            raise ValueError('Base debe tener entrada simultánea a señal y horizonte válido.')
        if t not in aperturas or original['precio_entrada'] != aperturas[t]:
            raise ValueError('Precio base no coincide con apertura de su vela.')
        nuevo_t = t + PASO_MS
        motivo = ('SIN_HORIZONTE_TRAS_RETRASO' if nuevo_t >= fin else
                  'SIN_APERTURA_PARA_ENTRADA' if nuevo_t not in aperturas else None)
        if motivo:
            excluidos.append(dict(indice_base=indice, instante_senal_ms=t,
                                  instante_entrada_propuesto_ms=nuevo_t, motivo=motivo))
            continue
        caso = copy.deepcopy(original)
        caso.update(instante_entrada_ms=nuevo_t, precio_entrada=aperturas[nuevo_t])
        seleccion.append(dict(indice_base=indice, caso=caso))
    return seleccion, excluidos


def _transiciones(pares):
    conteos = Counter((p['categoria_base'], p['categoria_retardo']) for p in pares
                      if p['categoria_retardo'] is not None)
    return [dict(base=b, retardo=r, casos=n) for (b, r), n in sorted(conteos.items())]


def comparar(pares, inicio, fin):
    """Mismo denominador comparable; exclusión nunca se trata como una salida."""
    base = [(p['instante_senal_ms'], p['categoria_base']) for p in pares]
    comparables = [p for p in pares if p['categoria_retardo'] is not None]
    comparable_base = [(p['instante_senal_ms'], p['categoria_base']) for p in comparables]
    retardo = [(p['instante_senal_ms'], p['categoria_retardo']) for p in comparables]

    def contar(registros):
        c = Counter(cat for _, cat in registros)
        return {cat: c[cat] for cat in periodos.CATEGORIAS}

    resumen = dict(casos_base=len(base), comparables=len(comparables), excluidos=len(base)-len(comparables),
                   base_total=contar(base), base_comparable=contar(comparable_base), retardo=contar(retardo),
                   cambios_categoria=sum(p['categoria_base'] != p['categoria_retardo'] for p in comparables),
                   transiciones=_transiciones(comparables))
    grupos = {}
    for frecuencia in ('mes', 'semana_iso', 'dia'):
        todas = periodos.agrupar(base, inicio, fin, frecuencia)
        originales = periodos.agrupar(comparable_base, inicio, fin, frecuencia)
        retrasadas = periodos.agrupar(retardo, inicio, fin, frecuencia)
        por_etiqueta = {}
        for p in comparables:
            etiqueta = periodos._limites(p['instante_senal_ms'], frecuencia)[0]
            por_etiqueta.setdefault(etiqueta, []).append(p)
        grupos[frecuencia] = []
        for total, anterior, posterior in zip(todas, originales, retrasadas):
            fila = {k: v for k, v in total.items() if k not in ('casos', 'frecuencias')}
            fila.update(casos_base=total['casos'], comparables=anterior['casos'],
                        excluidos=total['casos']-anterior['casos'], base_total=total['frecuencias'],
                        base_comparable=anterior['frecuencias'], retardo=posterior['frecuencias'],
                        transiciones=_transiciones(por_etiqueta.get(total['periodo'], [])))
            grupos[frecuencia].append(fila)
    return resumen, grupos


def generar(manifiesto, replay, casos, *, sha256_replay_esperado, sha256_casos_esperado, escenario):
    if escenario != ESCENARIO:
        raise ValueError('Escenario de estrés explícito no admitido.')
    base = periodos._leer(casos, sha256_casos_esperado)
    ds, r, digest = cargar_replay(manifiesto, replay, sha256_replay_esperado=sha256_replay_esperado)
    periodos._fechas(base)
    registros = periodos._validar_informe(base, r, digest)
    codigo = _huellas(CODIGO_BASE)
    if base.get('codigo_evaluacion_sha256') != codigo:
        raise ValueError('Evaluador/reglas distintos de la base: no comparar cambios mezclados.')
    if base['entrada_diagnostica'] != ENTRADA:
        raise ValueError('Se requiere base de apertura simultánea sin latencia.')
    seleccion, excluidos = preparar_retraso(base['casos_aportados'], ds['series']['15m'], escenario=escenario)
    lote = (evaluar_lote(manifiesto, replay, [s['caso'] for s in seleccion],
                         sha256_replay_esperado=digest, modelo_entrada=MODELO_ENTRADA,
                         modelo_salida=MODELO_SALIDA) if seleccion else None)
    if lote is not None and lote['codigo_evaluacion_sha256'] != codigo:
        raise ValueError('Código cambiado durante la comparación.')
    pares = [dict(indice_base=i, instante_senal_ms=t, categoria_base=c, categoria_retardo=None)
             for i, (t, c) in enumerate(registros)]
    for exclusion in excluidos:
        pares[exclusion['indice_base']]['exclusion'] = exclusion
    indice_filas = {f['instante_utc_ms']: f for f in r['filas']}
    if lote is not None:
        if len(lote['resultados']) != len(seleccion):
            raise ValueError('Cantidad de resultados retrasados incompatible.')
        for indice_retardo, (s, resultado) in enumerate(zip(seleccion, lote['resultados'])):
            i, caso = s['indice_base'], s['caso']
            # La evidencia de la señal debe ser idéntica, no sólo su categoría.
            if resultado['senal'] != base['resultados'][i]['senal']:
                raise ValueError('La señal original cambió durante el estrés.')
            cat, _, _ = periodos._resultado(caso, resultado, indice_filas[caso['instante_senal_ms']], r['simbolo'])
            pares[i].update(categoria_retardo=cat, indice_retardo=indice_retardo)
    resumen, grupos = comparar(pares, r['inicio_ms'], r['fin_exclusivo_ms'])
    return dict(tipo='SENSIBILIDAD_ENTRADA_15M_NO_EJECUTABLE_V1', ejecutable=False,
                escenario=escenario, retardo_ms=PASO_MS, simbolo=r['simbolo'],
                inicio_ms=r['inicio_ms'], fin_exclusivo_ms=r['fin_exclusivo_ms'],
                base_archivo_sha256=sha256_casos_esperado, replay_archivo_sha256=digest,
                manifiesto_sha256=ds['manifiesto_sha256'], codigo_evaluacion_sha256=codigo,
                codigo_comparacion_sha256=_huellas(('historical_delay.py', 'historical_periods.py')),
                resumen=resumen, periodos=grupos, pares=pares, excluidos=excluidos,
                lote_retrasado=lote, advertencias=[
                    'Una vela15m es estrés hipotético, no latencia medida ni permiso de entrada caducada.',
                    'Señal/ATR porcentual original; niveles y tamaño con mismas fórmulas al nuevo precio.',
                    'Entrada a apertura OHLC aportada, no fill alcanzable probado; sin spread/deslizamiento.',
                    'Mismo final absoluto: retrasar entrada reduce horizonte de observación.',
                    'Períodos por señal UTC, no fecha de salida ni ganancias mensuales.',
                    'Base total y base comparable separadas; excluidos no cuentan como stops ni como abiertos.',
                    'Misma categoría no significa igual precio, duración o resultado económico.',
                    'No cartera, sumaP&L, calibración de estrategia ni predicción de rentabilidad.',
                    'Hashes no autentican datos; indicadores guardados se validan, no se recalculan.'])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('manifest', 'replay', 'casos', 'sha256-replay-esperado', 'sha256-casos-esperado', 'salida'):
        p.add_argument('--'+n, required=True)
    p.add_argument('--escenario', choices=[ESCENARIO], required=True)
    a = p.parse_args(argv)
    salida = Path(a.salida)
    if salida.exists():
        raise FileExistsError('No sobrescribir informe existente.')
    informe = generar(a.manifest, a.replay, a.casos, sha256_replay_esperado=a.sha256_replay_esperado,
                      sha256_casos_esperado=a.sha256_casos_esperado, escenario=a.escenario)
    with salida.open('x', encoding='utf-8') as archivo:
        json.dump(informe, archivo, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    print(json.dumps({'simbolo': informe['simbolo'], **informe['resumen']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
