"""Une señal y trayectoria de un caso aislado; no cartera ni órdenes."""
from historical_proposal import proponer_instante
from historical_path import evaluar_trayectoria, MODELO as MODELO_SALIDA, PASO_MS
from paper_store import numero, validar_comision
from trade_planner import crear_plan_con_datos

MODELO_ENTRADA = 'PRECIO_APORTADO_AL_INICIO_15M_HIPOTETICO_V1'


def evaluar_caso(simbolo, series, instante_senal_ms, *, instante_entrada_ms,
                 fin_exclusivo_ms, precio_entrada, capital, comision_pct,
                 modelo_entrada, modelo_salida):
    return _evaluar_caso(simbolo, series, instante_senal_ms,
                        instante_entrada_ms=instante_entrada_ms, fin_exclusivo_ms=fin_exclusivo_ms,
                        precio_entrada=precio_entrada, capital=capital, comision_pct=comision_pct,
                        modelo_entrada=modelo_entrada, modelo_salida=modelo_salida)


def _evaluar_caso(simbolo, series, instante_senal_ms, *, instante_entrada_ms,
                 fin_exclusivo_ms, precio_entrada, capital, comision_pct,
                 modelo_entrada, modelo_salida, _senal=None):
    """Entrada hipotética aportada por el llamante, nunca inferida del cierre1h.

    Señal calculada con datos cerrados al instante_senal_ms. Entrada sólo en
    apertura15m no anterior a señal; precio aportado explícito, no verificado.
    Tamaño/niveles usan reglas vigentes y ATR de la señal. La trayectoria no
    influye en decidir si hubo señal. No verifica caducidad operativa, spread,
    desvío respecto de una cotización ni saldo de cartera. No ejecutable.
    """
    if modelo_entrada != MODELO_ENTRADA or modelo_salida != MODELO_SALIDA:
        raise ValueError('Modelos de prueba explícitos no admitidos.')
    if (type(instante_senal_ms) is not int or not 0 < instante_senal_ms <= 2**53
            or any(type(t) is not int or not 0 < t <= 2**53 or t % PASO_MS
                   for t in (instante_entrada_ms, fin_exclusivo_ms))
            or instante_entrada_ms < instante_senal_ms
            or not 0 < fin_exclusivo_ms-instante_entrada_ms <= 366*86_400_000):
        raise ValueError('Cronología señal/entrada/rango inválida.')
    precio_entrada, capital = numero(precio_entrada), numero(capital)
    comision_pct = validar_comision(comision_pct)
    señal = (_senal if _senal is not None else
             proponer_instante(simbolo, series, instante_senal_ms,
                              capital=capital, comision_pct=comision_pct))
    resultado = dict(
        tipo='CASO_HISTORICO_AISLADO_NO_EJECUTABLE', ejecutable=False,
        fill_confirmado=False, modelo_entrada=modelo_entrada, modelo_salida=modelo_salida,
        entrada_hipotetica=dict(instante_ms=instante_entrada_ms, precio_aportado=precio_entrada),
        senal=señal, plan_hipotetico=None, trayectoria=None, estado='SIN_ENTRADA_POR_REGLAS',
        limites=['Precio de entrada aportado, no fill demostrado ni inferido del cierre1h.',
                 'No replica caducidad, latencia, spread ni tolerancia de precio del runner.',
                 'Capital aislado explícito: no cartera, reinversión ni riesgo diario compartido.',
                 'Casos simultáneos no se pueden sumar como resultados de una cartera.'])
    if señal['decision_reglas'] != 'PAPER CANDIDATE':
        return resultado
    plan = crear_plan_con_datos(
        simbolo, señal['analisis_historico']['analisis'], capital=capital,
        precio=precio_entrada, comision_pct=comision_pct, modo='PAPER', real_bloqueado=False)
    plan['decision'] = 'PLAN HISTORICO HIPOTETICO'
    df = series['15m']
    seleccion = df.loc[(df['tiempo_apertura'] >= instante_entrada_ms)
                      & (df['tiempo_apertura'] < fin_exclusivo_ms)]
    velas = seleccion.to_dict('records')
    # H1 ya validó que todos los timestamps sean enteros exactos/alineados.
    for vela in velas:
        for campo in ('tiempo_apertura', 'tiempo_cierre'):
            vela[campo] = int(vela[campo])
    trayectoria = evaluar_trayectoria(
        velas, inicio_ms=instante_entrada_ms, fin_exclusivo_ms=fin_exclusivo_ms,
        entrada=precio_entrada, tamano_posicion=plan['tamano_posicion'],
        stop=plan['stop_precio'], objetivo=plan['objetivo_precio'],
        comision_pct=comision_pct, modelo=modelo_salida)
    resultado.update(estado='CASO_HIPOTETICO_EVALUADO', plan_hipotetico=plan,
                     trayectoria=trayectoria)
    return resultado
