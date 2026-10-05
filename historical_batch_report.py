"""Informe diagnóstico de episodios, no backtest de cartera ni pronóstico."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from historical_batch import cargar_replay, evaluar_lote
from historical_case import MODELO_ENTRADA, MODELO_SALIDA
from paper_store import numero, validar_comision

SELECCION = 'PRIMERA_SENAL_DE_CADA_EPISODIO'
ENTRADA = 'APERTURA_15M_DE_SENAL_SIN_LATENCIA_NI_DESLIZAMIENTO'


def preparar_casos(ds, replay, *, capital, comision_pct, seleccion, entrada):
    if seleccion != SELECCION or entrada != ENTRADA:
        raise ValueError('Selección/modelo de entrada diagnósticos deben ser explícitos.')
    capital, comision_pct = numero(capital), validar_comision(comision_pct)
    aperturas = dict(zip(ds['series']['15m'].tiempo_apertura,ds['series']['15m'].apertura))
    casos, anterior = [], False
    for fila in replay['filas']:
        cumple=fila['cumple_condicion_tecnica']
        if cumple and not anterior:
            t=fila['instante_utc_ms']
            if t not in aperturas:
                raise ValueError('Falta apertura para entrada hipotética.')
            casos.append(dict(instante_senal_ms=t,instante_entrada_ms=t,
                              fin_exclusivo_ms=replay['fin_exclusivo_ms'],
                              precio_entrada=float(aperturas[t]),capital=capital,comision_pct=comision_pct))
        anterior=cumple
    return casos


def generar(manifiesto,replay,*,sha256_replay_esperado,capital,comision_pct,seleccion,entrada):
    ds,r,digest=cargar_replay(manifiesto,replay,sha256_replay_esperado=sha256_replay_esperado)
    casos=preparar_casos(ds,r,capital=capital,comision_pct=comision_pct,
                         seleccion=seleccion,entrada=entrada)
    if not casos:
        raise ValueError('Sin episodios: no generar informe económico vacío.')
    informe=evaluar_lote(manifiesto,replay,casos,sha256_replay_esperado=digest,
                         modelo_entrada=MODELO_ENTRADA,modelo_salida=MODELO_SALIDA)
    # Sólo frecuencias: no sumas, media de escenarios, ROI ni tasa de acierto inventada.
    estados=Counter(x['trayectoria']['estado'] for x in informe['resultados'])
    eventos=Counter((x['trayectoria']['evento'] or {}).get('diagnostico',{}).get('estado','SIN_EVENTO')
                   for x in informe['resultados'])
    informe.update(simbolo=r['simbolo'],seleccion_diagnostica=seleccion,
                   entrada_diagnostica=entrada,capital_aislado_por_caso=capital,
                   resumen=dict(casos=len(casos),estados=dict(estados),eventos=dict(eventos)),
                   codigo_informe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    informe['advertencias'] += [
        'Primera señal de episodio es selección diagnóstica, no política operativa de reentrada.',
        'Apertura simultánea a señal supone latencia cero; no es ejecución alcanzable demostrada.',
        'Un capital independiente por caso no representa capital agregado disponible ni reinversión.']
    return informe


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for nombre in ('manifest','replay','sha256-replay-esperado','salida'):
        p.add_argument('--'+nombre,required=True)
    p.add_argument('--capital',type=float,required=True)
    p.add_argument('--comision-pct',type=float,required=True)
    p.add_argument('--seleccion',choices=[SELECCION],required=True)
    p.add_argument('--entrada',choices=[ENTRADA],required=True)
    a=p.parse_args()
    salida=Path(a.salida)
    if salida.exists(): raise FileExistsError('No sobrescribir informe existente.')
    informe=generar(a.manifest,a.replay,sha256_replay_esperado=a.sha256_replay_esperado,
                    capital=a.capital,comision_pct=a.comision_pct,seleccion=a.seleccion,entrada=a.entrada)
    with salida.open('x',encoding='utf-8') as archivo:
        json.dump(informe,archivo,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    print(json.dumps({'simbolo':informe['simbolo'],**informe['resumen'],
                      'salida':str(salida)},ensure_ascii=False),flush=True)


if __name__ == '__main__': main()
