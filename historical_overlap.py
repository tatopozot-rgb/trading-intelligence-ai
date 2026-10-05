"""Inventario temporal conjunto H5f; no asigna capital, señales ni resultados.

Lee casos y replay ya calculados con hashes externos. Los intervalos de salida
son cotas temporales hipotéticas: nunca fills ni un orden de ejecución.
"""
import argparse
from collections import Counter
import hashlib
from itertools import combinations
import json
from pathlib import Path

import historical_periods as periodos

ENTRADA = 'APERTURA_15M_DE_SENAL_SIN_LATENCIA_NI_DESLIZAMIENTO'
SIMBOLOS = ('BTCUSDT', 'ETHUSDT')
APERTURAS = ('APERTURA_EN_O_BAJO_STOP', 'APERTURA_EN_O_SOBRE_OBJETIVO')
TIPOS_EVENTO = ('entradas_hipoteticas', 'salidas_en_apertura_modelada',
               'limites_inferiores_salida_intravela', 'limites_superiores_salida_intravela',
               'censuras_fin_observacion')


def _exigir(condicion, mensaje):
    if not condicion:
        raise ValueError(mensaje)


def _intervalo(caso, resultado, simbolo, indice):
    trayectoria = resultado['trayectoria']
    _exigir(trayectoria.get('ejecutable') is False
            and trayectoria.get('fill_confirmado') is False
            and 'seleccionado' in trayectoria and trayectoria['seleccionado'] is None,
            'Trayectoria no debe confirmar fills ni seleccionar escenarios.')
    evento = trayectoria['evento']
    salida, categoria, escenarios = None, 'SIN_SALIDA_EN_RANGO', []
    if evento is not None:
        _exigir('instante_fill' in evento and evento['instante_fill'] is None,
                'Evento contiene instante de fill o carece de declaración explícita.')
        diagnostico = evento['diagnostico']
        _exigir(diagnostico.get('fill_confirmado') is False
                and 'precio_fill' in diagnostico and diagnostico['precio_fill'] is None,
                'Diagnóstico no debe confirmar un fill.')
        nombre = diagnostico['estado']
        categoria = periodos.EVENTOS[nombre]
        escenarios = (['OBJETIVO_PRIMERO', 'STOP_PRIMERO'] if categoria == 'AMBIGUO'
                      else [nombre])
        _exigir(isinstance(trayectoria['escenarios'], dict)
                and set(trayectoria['escenarios']) == set(escenarios),
                'Escenarios ausentes o incompatibles con el evento; no resolver ambigüedad.')
        exacta = nombre in APERTURAS
        salida = dict(tipo='APERTURA_MODELADA' if exacta else 'INTERVALO_INTRAVELA',
                      limite_inferior_ms=evento['primera_apertura_ms'],
                      limite_superior_ms=(evento['primera_apertura_ms'] if exacta else evento['cierre_ms']),
                      limites_inclusivos=True, evento=nombre,
                      vela_apertura_ms=evento['primera_apertura_ms'], vela_cierre_ms=evento['cierre_ms'],
                      instante_fill_confirmado=None)
    return dict(id_caso=f'{simbolo}:{indice}', simbolo=simbolo, indice_original=indice,
                instante_senal_ms=caso['instante_senal_ms'], instante_entrada_ms=caso['instante_entrada_ms'],
                fin_observacion_exclusivo_ms=caso['fin_exclusivo_ms'],
                censurado_derecha=evento is None, categoria=categoria,
                ambiguo_resultado=categoria == 'AMBIGUO', escenarios_conservados=escenarios,
                salida_hipotetica=salida)


def _cotas(caso):
    """Extremos de permanencia observada; censura NO se convierte en salida."""
    salida = caso['salida_hipotetica']
    if salida is None:
        return (caso['fin_observacion_exclusivo_ms'],) * 2
    return salida['limite_inferior_ms'], salida['limite_superior_ms']


def _pares(casos):
    solapes, contactos = [], []
    for a, b in combinations(casos, 2):
        amin, amax = _cotas(a)
        bmin, bmax = _cotas(b)
        inicio = max(a['instante_entrada_ms'], b['instante_entrada_ms'])
        minimo, maximo = min(amin, bmin), min(amax, bmax)
        if inicio < maximo:
            solapes.append(dict(caso_a=a['id_caso'], caso_b=b['id_caso'],
                                relacion='MISMO_SIMBOLO' if a['simbolo'] == b['simbolo'] else 'ENTRE_SIMBOLOS',
                                clasificacion='CIERTO' if inicio < minimo else 'POSIBLE_NO_CONFIRMADO',
                                inicio_ms=inicio,
                                duracion_minima_ms=max(0, minimo - inicio),
                                duracion_maxima_ms=maximo - inicio,
                                incluye_caso_censurado=a['censurado_derecha'] or b['censurado_derecha']))
        # Mismo timestamp no demuestra que el saldo se libere antes de la entrada.
        for anterior, nuevo in ((a, b), (b, a)):
            salida = anterior['salida_hipotetica']
            if salida and salida['limite_inferior_ms'] <= nuevo['instante_entrada_ms'] <= salida['limite_superior_ms']:
                contactos.append(dict(caso_con_salida=anterior['id_caso'], caso_con_entrada=nuevo['id_caso'],
                                      instante_entrada_ms=nuevo['instante_entrada_ms'],
                                      tipo=('MISMO_INSTANTE_MODELADO' if salida['tipo'] == 'APERTURA_MODELADA'
                                            else 'ENTRADA_EN_INTERVALO_DE_SALIDA'),
                                      orden_ejecucion=None))
    return solapes, contactos


def _cronologia(casos, inicio, fin):
    grupos = {t: dict(instante_ms=t, instante_utc=periodos._iso(t),
                      **{tipo: [] for tipo in TIPOS_EVENTO}) for t in (inicio, fin)}

    def agregar(t, tipo, identificador):
        if t not in grupos:
            grupos[t] = dict(instante_ms=t, instante_utc=periodos._iso(t),
                             **{nombre: [] for nombre in TIPOS_EVENTO})
        grupos[t][tipo].append(identificador)

    for caso in casos:
        identificador, salida = caso['id_caso'], caso['salida_hipotetica']
        agregar(caso['instante_entrada_ms'], 'entradas_hipoteticas', identificador)
        if salida is None:
            agregar(caso['fin_observacion_exclusivo_ms'], 'censuras_fin_observacion', identificador)
        elif salida['tipo'] == 'APERTURA_MODELADA':
            agregar(salida['limite_inferior_ms'], 'salidas_en_apertura_modelada', identificador)
        else:
            agregar(salida['limite_inferior_ms'], 'limites_inferiores_salida_intravela', identificador)
            agregar(salida['limite_superior_ms'], 'limites_superiores_salida_intravela', identificador)
    tiempos, tramos = sorted(grupos), []
    for izquierda, derecha in zip(tiempos, tiempos[1:]):
        ciertos, posibles = [], []
        for caso in casos:
            minimo, maximo = _cotas(caso)
            if caso['instante_entrada_ms'] <= izquierda < maximo:
                posibles.append(caso['id_caso'])
                if izquierda < minimo:
                    ciertos.append(caso['id_caso'])
        tramos.append(dict(inicio_ms=izquierda, fin_exclusivo_ms=derecha,
                           casos_con_permanencia_cierta=ciertos, casos_con_permanencia_posible=posibles,
                           cantidad_minima=len(ciertos), cantidad_maxima=len(posibles)))
    return [grupos[t] for t in tiempos], tramos


def generar(fuentes):
    """Dos fuentes explícitas BTC/ETH, cada una con casos, replay y sus SHA256.

    Conserva todos los casos H5f. El orden de argumentos no prioriza símbolos.
    La validación compartida comprueba evidencia ya guardada, sin reevaluarla.
    """
    _exigir(isinstance(fuentes, list) and len(fuentes) == 2, 'Se requieren las dos fuentes BTC/ETH.')
    casos, procedencia, rangos = [], {}, []
    for fuente in fuentes:
        periodos._objeto(fuente, ('casos', 'replay', 'sha256_casos_esperado', 'sha256_replay_esperado'))
        informe = periodos._leer(fuente['casos'], fuente['sha256_casos_esperado'])
        replay = periodos._leer(fuente['replay'], fuente['sha256_replay_esperado'])
        periodos._fechas(informe); periodos._fechas(replay)
        periodos._validar_informe(informe, replay, fuente['sha256_replay_esperado'])
        simbolo = informe['simbolo']
        _exigir(simbolo in SIMBOLOS and simbolo not in procedencia, 'Símbolo repetido o no admitido.')
        _exigir(informe['entrada_diagnostica'] == ENTRADA, 'Se requiere base H5f, no un escenario de estrés.')
        for indice, (caso, resultado) in enumerate(zip(informe['casos_aportados'], informe['resultados'])):
            _exigir(caso['instante_entrada_ms'] == caso['instante_senal_ms']
                    and caso['fin_exclusivo_ms'] == replay['fin_exclusivo_ms'],
                    'Base H5f debe conservar entrada simultánea y fin absoluto de observación.')
            casos.append(_intervalo(caso, resultado, simbolo, indice))
        rangos.append((replay['inicio_ms'], replay['fin_exclusivo_ms']))
        procedencia[simbolo] = dict(casos_archivo_sha256=fuente['sha256_casos_esperado'],
                                   replay_archivo_sha256=fuente['sha256_replay_esperado'],
                                   casos_sha256=informe['casos_sha256'], manifiesto_sha256=informe['manifiesto_sha256'],
                                   total_casos=len(informe['casos_aportados']))
    _exigir(rangos[0] == rangos[1], 'Coberturas BTC/ETH distintas; no suponer cobertura conjunta.')
    inicio, fin = rangos[0]
    casos.sort(key=lambda c: (c['instante_entrada_ms'], c['id_caso']))
    for indice, caso in enumerate(casos):
        caso['indice_global'] = indice
    solapes, contactos = _pares(casos)
    cronologia, tramos = _cronologia(casos, inicio, fin)
    clases = Counter(p['clasificacion'] for p in solapes)
    relaciones = Counter(p['relacion'] for p in solapes)
    simultaneos = [g for g in cronologia if len(g['entradas_hipoteticas']) > 1]
    return dict(tipo='INVENTARIO_CONJUNTO_INTERVALOS_SOLAPES_H5F_V1', ejecutable=False,
                inicio_ms=inicio, fin_exclusivo_ms=fin, inicio_utc=periodos._iso(inicio),
                fin_exclusivo_utc=periodos._iso(fin), seleccion_diagnostica=periodos.SELECCION,
                entrada_diagnostica=ENTRADA, modelo_entrada=periodos.MODELO_ENTRADA,
                modelo_salida=periodos.MODELO_SALIDA, fuentes={s: procedencia[s] for s in SIMBOLOS},
                codigo_sha256={nombre: hashlib.sha256(Path(__file__).with_name(nombre).read_bytes()).hexdigest()
                               for nombre in ('historical_overlap.py', 'historical_periods.py')},
                resumen=dict(casos=len(casos), casos_por_simbolo={s: procedencia[s]['total_casos'] for s in SIMBOLOS},
                             categorias={s: dict(Counter(c['categoria'] for c in casos if c['simbolo'] == s)) for s in SIMBOLOS},
                             sin_salida_censurados=sum(c['censurado_derecha'] for c in casos),
                             resultados_ambiguos=sum(c['ambiguo_resultado'] for c in casos),
                             salidas_en_apertura_modelada=sum(c['salida_hipotetica'] is not None and c['salida_hipotetica']['tipo'] == 'APERTURA_MODELADA' for c in casos),
                             salidas_intravela=sum(c['salida_hipotetica'] is not None and c['salida_hipotetica']['tipo'] == 'INTERVALO_INTRAVELA' for c in casos),
                             pares_solape=len(solapes), pares_solape_cierto=clases['CIERTO'],
                             pares_solape_posible_no_confirmado=clases['POSIBLE_NO_CONFIRMADO'],
                             pares_mismo_simbolo=relaciones['MISMO_SIMBOLO'], pares_entre_simbolos=relaciones['ENTRE_SIMBOLOS'],
                             contactos_entrada_salida=len(contactos), grupos_entradas_simultaneas=len(simultaneos),
                             casos_en_entradas_simultaneas=sum(len(g['entradas_hipoteticas']) for g in simultaneos),
                             cota_inferior_pico_concurrencia=max(t['cantidad_minima'] for t in tramos),
                             cota_superior_pico_concurrencia=max(t['cantidad_maxima'] for t in tramos)),
                casos=casos, cronologia=cronologia, tramos=tramos, pares_solape=solapes,
                contactos_entrada_salida=contactos,
                convenciones=[
                    'Índices originales base cero; índice global sólo ordena almacenamiento cronológico, nunca aceptación o prioridad.',
                    'Identificadores en empates se ordenan únicamente para serialización determinista; cada grupo es simultáneo sin orden de ejecución.',
                    'Salida intravela acotada inclusivamente por apertura/cierre OHLC; se incluye conservadoramente la apertura, sin inferir instante exacto.',
                    'Apertura modelada es un instante hipotético del modelo original, no fill confirmado.',
                    'Permanencia [entrada,salida): los solapes requieren duración positiva. Contactos al mismo instante se registran aparte sin ordenar liberación/entrada.',
                    'Sin salida implica censura derecha: salida null y permanencia observada hasta fin exclusivo; nada se infiere después.',
                    'Tramos son [inicio,fin); cantidades mínima/máxima son cotas conservadoras de casos hipotéticos, no posiciones financiables.',
                    'Las cotas de pico no demuestran simultaneidad intravela exacta ni que todos los solapes posibles se materialicen conjuntamente.',
                    'Ambigüedad stop/objetivo y tiempo intravela son incertidumbres distintas; ninguna se resuelve.'],
                advertencias=[
                    'No asigna capital, acepta/rechaza señales, prioriza símbolos ni suma P&L; no es cartera o rendimiento.',
                    'Reutiliza H5f original; H5h no es estrategia ni entrada de este informe.',
                    'No recalcula H4, indicadores o trayectorias; no consulta red, cuentas ni órdenes.',
                    'Hashes externos verifican integridad respecto de valores aportados, no autenticidad ni corrección económica.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for simbolo in ('btc', 'eth'):
        for campo in ('casos', 'replay', 'sha256-casos-esperado', 'sha256-replay-esperado'):
            parser.add_argument('--' + simbolo + '-' + campo, required=True)
    parser.add_argument('--salida', required=True)
    args = vars(parser.parse_args(argv))
    salida = Path(args['salida'])
    if salida.exists():
        raise FileExistsError('No sobrescribir informe existente.')
    fuentes = [{campo: args[simbolo + '_' + campo] for campo in
                ('casos', 'replay', 'sha256_casos_esperado', 'sha256_replay_esperado')}
               for simbolo in ('btc', 'eth')]
    informe = generar(fuentes)
    with salida.open('x', encoding='utf-8') as archivo:
        json.dump(informe, archivo, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    print(json.dumps(dict(**informe['resumen'], salida=str(salida)), ensure_ascii=False))


if __name__ == '__main__':
    main()
