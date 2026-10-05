"""Diagnóstico OHLC y escenarios explícitos, sin fills confirmados ni cartera."""
from paper_store import numero, calcular_resultado_cierre


def diagnosticar_vela(*, apertura, maximo, minimo, cierre, stop, objetivo):
    """Observa niveles LONG; tocar un nivel NO acredita fill ni su precio.

Si apertura está fuera de niveles, se indica separadamente. Si ambos niveles
aparecen en OHLC, el orden intravela es desconocido. Nunca elige el ganador.
"""
    apertura, maximo, minimo, cierre, stop, objetivo = (
        numero(v) for v in (apertura, maximo, minimo, cierre, stop, objetivo))
    if not minimo <= min(apertura, cierre) <= max(apertura, cierre) <= maximo:
        raise ValueError('OHLC incoherente.')
    if not stop < objetivo:
        raise ValueError('Stop/objetivo fuera de orden.')
    toca_stop, toca_objetivo = minimo <= stop, maximo >= objetivo
    if apertura <= stop:
        estado = 'APERTURA_EN_O_BAJO_STOP'
    elif apertura >= objetivo:
        estado = 'APERTURA_EN_O_SOBRE_OBJETIVO'
    elif toca_stop and toca_objetivo:
        estado = 'AMBIGUO_AMBOS_NIVELES'
    elif toca_stop:
        estado = 'SOLO_STOP_OBSERVADO'
    elif toca_objetivo:
        estado = 'SOLO_OBJETIVO_OBSERVADO'
    else:
        estado = 'NINGUN_NIVEL'
    return {'estado':estado, 'toca_stop':toca_stop, 'toca_objetivo':toca_objetivo,
            'fill_confirmado':False, 'precio_fill':None,
            'limite':'OHLC no demuestra ejecución, orden intravela ni deslizamiento.'}


def resultado_hipotetico(*, entrada, tamano_posicion, salida_aportada, comision_pct):
    """Todos los parámetros son explícitos; no infiere ni valida modelo de fill."""
    return {'tipo':'ARITMETICA_HIPOTETICA_NO_EJECUTABLE',
            'entrada_aportada':numero(entrada), 'salida_aportada':numero(salida_aportada),
            'fill_confirmado':False,
            **calcular_resultado_cierre(entrada, tamano_posicion, salida_aportada, comision_pct)}


def escenarios_ambiguedad(*, entrada, tamano_posicion, comision_pct,
                         apertura, maximo, minimo, cierre, stop, objetivo):
    """Conserva ambas hipótesis para una posición LONG ya abierta.

    No elige ganadora, asigna probabilidades ni promedia resultados. Los precios
    exactos de las barreras son supuestos explícitos, no fills ni cotas de una
    cartera. Aperturas fuera de niveles requieren otro modelo, no este atajo.
    """
    diagnostico = diagnosticar_vela(apertura=apertura, maximo=maximo,
                                  minimo=minimo, cierre=cierre,
                                  stop=stop, objetivo=objetivo)
    entrada = numero(entrada)
    if not stop < entrada < objetivo:
        raise ValueError('La entrada LONG debe estar entre stop y objetivo.')
    # Validar también tamaño/comisión/overflow cuando no haya ambigüedad.
    resultados = {
        nombre: resultado_hipotetico(entrada=entrada,
                                    tamano_posicion=tamano_posicion,
                                    salida_aportada=precio, comision_pct=comision_pct)
        for nombre, precio in (('STOP_PRIMERO', stop), ('OBJETIVO_PRIMERO', objetivo))
    }
    ambiguo = diagnostico['estado'] == 'AMBIGUO_AMBOS_NIVELES'
    return {
        'tipo': 'ESCENARIOS_HIPOTETICOS_NO_EJECUTABLES',
        'diagnostico': diagnostico,
        'escenarios': resultados if ambiguo else {},
        'seleccionado': None,
        'fill_confirmado': False,
        'supuestos': ['Posición LONG abierta antes de esta vela.',
                      'Salida hipotética exactamente en cada barrera; sin deslizamiento.',
                      'Comisión suministrada explícitamente, no tarifa verificada.'],
        'limite': ('No asigna probabilidades ni resultado medio; no son cotas de cartera. '
                   'Sin ambigüedad intravela, conserva diagnóstico sin inventar salida.'),
    }
