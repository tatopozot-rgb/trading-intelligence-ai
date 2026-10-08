"""H6c: sensibilidades de cartera desde H5f/H6a fijados por SHA256 externo.

Sólo offline. No indicadores, red, config, cuentas, órdenes ni almacenamiento
operativo. Cuatro hipótesis globales NO son extremos garantizados de P&L.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import historical_overlap as solapes
import historical_periods as periodos
import historical_portfolio as cartera

TIEMPOS = ('TEMPRANA', 'TARDIA')
BARRERAS = ('STOP_PRIMERO', 'OBJETIVO_PRIMERO')


def _exigir(condicion, mensaje):
    if not condicion:
        raise ValueError(mensaje)


def _precio_escenario(nombre, escenario, plan):
    periodos._objeto(escenario, ('salida_aportada',))
    precio = cartera._numero(escenario['salida_aportada'])
    stop, objetivo = (cartera._numero(plan[k]) for k in ('stop_precio', 'objetivo_precio'))
    if nombre in ('SOLO_STOP_OBSERVADO', 'STOP_PRIMERO'):
        coherente = precio == stop
    elif nombre in ('SOLO_OBJETIVO_OBSERVADO', 'OBJETIVO_PRIMERO'):
        coherente = precio == objetivo
    elif nombre == 'APERTURA_EN_O_BAJO_STOP':
        coherente = precio <= stop
    elif nombre == 'APERTURA_EN_O_SOBRE_OBJETIVO':
        coherente = precio >= objetivo
    else:
        coherente = False
    _exigir(coherente, 'Precio de escenario incompatible con su barrera/gap.')
    return str(precio)


def _preparar(fuentes, mapa):
    _exigir(type(fuentes) is list and len(fuentes) == 2, 'Se requieren fuentes BTC/ETH.')
    periodos._objeto(mapa, ('tipo', 'ejecutable', 'inicio_ms', 'fin_exclusivo_ms', 'casos',
                            'fuentes', 'entrada_diagnostica', 'seleccion_diagnostica',
                            'modelo_entrada', 'modelo_salida'))
    _exigir(mapa['tipo'] == 'INVENTARIO_CONJUNTO_INTERVALOS_SOLAPES_H5F_V1'
            and mapa['ejecutable'] is False and mapa['entrada_diagnostica'] == solapes.ENTRADA
            and mapa['seleccion_diagnostica'] == periodos.SELECCION
            and mapa['modelo_entrada'] == periodos.MODELO_ENTRADA
            and mapa['modelo_salida'] == periodos.MODELO_SALIDA, 'Formato H6a no admitido.')
    esperados, originales, procedencia = [], {}, {}
    for f in fuentes:
        periodos._objeto(f, ('casos', 'replay', 'sha256_casos_esperado', 'sha256_replay_esperado'))
        informe = periodos._leer(f['casos'], f['sha256_casos_esperado'])
        replay = periodos._leer(f['replay'], f['sha256_replay_esperado'])
        periodos._fechas(informe)
        periodos._fechas(replay)
        periodos._validar_informe(informe, replay, f['sha256_replay_esperado'])
        simbolo = informe['simbolo']
        _exigir(simbolo in solapes.SIMBOLOS and simbolo not in procedencia, 'Símbolo repetido/no admitido.')
        _exigir(informe['entrada_diagnostica'] == solapes.ENTRADA, 'Sólo base H5f, no estrés H5h.')
        _exigir(type(mapa['inicio_ms']) is int and type(mapa['fin_exclusivo_ms']) is int
                and (replay['inicio_ms'], replay['fin_exclusivo_ms']) ==
                    (mapa['inicio_ms'], mapa['fin_exclusivo_ms']), 'Coberturas incompatibles.')
        procedencia[simbolo] = dict(casos_archivo_sha256=f['sha256_casos_esperado'],
            replay_archivo_sha256=f['sha256_replay_esperado'], casos_sha256=informe['casos_sha256'],
            manifiesto_sha256=informe['manifiesto_sha256'], total_casos=len(informe['casos_aportados']))
        for i, (caso, r) in enumerate(zip(informe['casos_aportados'], informe['resultados'])):
            _exigir(caso['instante_entrada_ms'] == caso['instante_senal_ms']
                    and caso['fin_exclusivo_ms'] == mapa['fin_exclusivo_ms'], 'Base H5f desalineada.')
            intervalo = solapes._intervalo(caso, r, simbolo, i)
            esperados.append(intervalo)
            plan = r['plan_hipotetico']
            periodos._objeto(plan, ('stop_precio', 'objetivo_precio', 'entrada', 'comision_paper_pct'))
            entrada, stop, objetivo = (cartera._numero(plan[k]) for k in
                                       ('entrada', 'stop_precio', 'objetivo_precio'))
            _exigir(stop < entrada < objetivo, 'Niveles LONG incompatibles.')
            precios = {nombre: _precio_escenario(nombre, valor, plan)
                       for nombre, valor in r['trayectoria']['escenarios'].items()}
            originales[intervalo['id_caso']] = dict(id=f'{simbolo}_{i:06d}', simbolo=simbolo,
                entrada_ms=caso['instante_entrada_ms'], entrada=str(entrada), stop=str(stop),
                objetivo=str(objetivo), comision_pct=str(plan['comision_paper_pct']), precios=precios)
    esperados.sort(key=lambda c: (c['instante_entrada_ms'], c['id_caso']))
    for i, caso in enumerate(esperados):
        caso['indice_global'] = i
    # Canonical JSON equality distinguishes false/0 and preserves every identity;
    # H6a pair inventory is neither recomputed nor used for capital allocation.
    _exigir(periodos._hash(mapa['casos']) == periodos._hash(esperados),
            'Casos/intervalos H6a no corresponden exactamente a H5f.')
    _exigir(periodos._hash(mapa['fuentes']) == periodos._hash(procedencia),
            'Procedencia H6a incompatible con hashes externos H5f/replay.')
    return esperados, originales, {s: procedencia[s] for s in solapes.SIMBOLOS}


def generar(fuentes, *, mapa, sha256_mapa_esperado, capital_inicial,
            riesgo_operacion_pct, perdida_diaria_pct, max_posiciones):
    evidencia = periodos._leer(mapa, sha256_mapa_esperado)
    intervalos, originales, procedencia = _preparar(fuentes, evidencia)
    parametros = dict(capital_inicial=capital_inicial, riesgo_operacion_pct=riesgo_operacion_pct,
        perdida_diaria_pct=perdida_diaria_pct, max_posiciones=max_posiciones,
        inicio_ms=evidencia['inicio_ms'], fin_ms=evidencia['fin_exclusivo_ms'], politica_empates=cartera.POLITICA)
    variantes = {}
    for tiempo in TIEMPOS:
        for barrera in BARRERAS:
            candidatos, seleccion = [], []
            for intervalo in intervalos:
                original = originales[intervalo['id_caso']]
                c = {k: v for k, v in original.items() if k != 'precios'}
                salida, nombre = intervalo['salida_hipotetica'], None
                c.update(salida_ms=None, salida=None)
                if salida is not None:
                    nombre = barrera if intervalo['ambiguo_resultado'] else intervalo['escenarios_conservados'][0]
                    c['salida_ms'] = salida['limite_inferior_ms' if tiempo == 'TEMPRANA' else 'limite_superior_ms']
                    c['salida'] = original['precios'][nombre]
                candidatos.append(c)
                seleccion.append(dict(id=c['id'], id_caso_original=intervalo['id_caso'],
                    escenario_barrera=nombre, salida_ms=c['salida_ms'], precio_salida=c['salida'],
                    censurado_derecha=intervalo['censurado_derecha']))
            resultado = cartera.simular(candidatos, **parametros)
            _exigir(len(resultado['decisiones']) == len(intervalos)
                    and {d['id'] for d in resultado['decisiones']} == {c['id'] for c in candidatos},
                    'El motor perdió o duplicó identidades.')
            variantes[f'{tiempo}_{barrera}'] = dict(tiempo_salida=tiempo,
                barrera_si_ambigua=barrera, candidatos=candidatos, seleccion=seleccion, cartera=resultado,
                rechazos_por_motivo=dict(Counter(d['motivo'] for d in resultado['decisiones'] if d['estado'] == 'RECHAZADO')))
    return dict(tipo='SENSIBILIDADES_CARTERA_H5F_H6A_PAPER_V1', ejecutable=False,
        fill_confirmado=False, ganador_seleccionado=None, limites_pnl_garantizados=False,
        inicio_ms=evidencia['inicio_ms'], fin_exclusivo_ms=evidencia['fin_exclusivo_ms'],
        mapa_archivo_sha256=sha256_mapa_esperado, fuentes=procedencia,
        parametros={k: str(v) if k.endswith('_pct') or k == 'capital_inicial' else v for k, v in parametros.items()},
        codigo_sha256={n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
                       for n in ('historical_portfolio_report.py', 'historical_portfolio.py',
                                 'historical_periods.py', 'historical_overlap.py')},
        resumen=dict(casos=len(intervalos), censurados=sum(c['censurado_derecha'] for c in intervalos),
                     ambiguos=sum(c['ambiguo_resultado'] for c in intervalos)),
        identidades=[dict(id=originales[c['id_caso']]['id'], id_caso_original=c['id_caso'],
                         simbolo=c['simbolo'], indice_original=c['indice_original']) for c in intervalos],
        variantes=variantes, advertencias=[
            'Cuatro hipótesis globales de sensibilidad, no extremos garantizados ni estrategia seleccionada.',
            'Tiempo temprano/tardío afecta TODAS las salidas intravela, incluso sin ambigüedad de barrera.',
            'Apertura modelada conserva mismo instante/precio en ambas variantes; no es un fill confirmado.',
            'Censurados conservan salida nula; sólo los aceptados quedan como posiciones abiertas.',
            'ID lexicográfico prioriza BTC en empates, explícitamente como hipótesis técnica no validada.',
            'Resultados son dependientes de trayectoria, sin suma de P&L aislados ni optimización de parámetros.',
            'Fee al abrir y riesgo exacto al stop difieren del ledger operativo; no réplica exacta del runner.',
            'Saldo/drawdown realizados no son equity/drawdown MTM; no rentabilidad validada ni precios finales inventados.',
            'Precios guardados sin slippage, lotes, ticks ni profundidad; no autenticidad de mercado demostrada.',
            'Selección primera señal por episodio, entrada simultánea sin latencia: diagnóstico, no scanner ejecutado.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for simbolo in ('btc', 'eth'):
        for campo in ('casos', 'replay', 'sha256-casos-esperado', 'sha256-replay-esperado'):
            parser.add_argument('--' + simbolo + '-' + campo, required=True)
    for campo in ('mapa', 'sha256-mapa-esperado', 'capital-inicial', 'riesgo-operacion-pct', 'perdida-diaria-pct', 'salida'):
        parser.add_argument('--' + campo, required=True)
    parser.add_argument('--max-posiciones', required=True, type=int)
    args = vars(parser.parse_args(argv))
    salida = Path(args['salida'])
    if salida.exists():
        raise FileExistsError('No sobrescribir informe existente.')
    fuentes = [{campo: args[simbolo + '_' + campo] for campo in
                ('casos', 'replay', 'sha256_casos_esperado', 'sha256_replay_esperado')}
               for simbolo in ('btc', 'eth')]
    informe = generar(fuentes, **{k: args[k] for k in ('mapa', 'sha256_mapa_esperado',
        'capital_inicial', 'riesgo_operacion_pct', 'perdida_diaria_pct', 'max_posiciones')})
    contenido = json.dumps(informe, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
    with salida.open('x', encoding='utf-8', newline='\n') as archivo:
        archivo.write(contenido)
    print(json.dumps(dict(archivo=str(salida), sha256=hashlib.sha256(contenido.encode()).hexdigest(),
                         resumen=informe['resumen']), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
