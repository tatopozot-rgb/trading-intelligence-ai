"""Propuesta de referencia offline, no señal autorizante, fill ni cartera."""
from historical_analysis import analizar_instante
from trade_planner import crear_plan_con_datos


def proponer_instante(simbolo, series, instante_ms, *, capital, comision_pct):
    evidencia = analizar_instante(simbolo, series, instante_ms)
    return _proponer_evidencia(simbolo, evidencia, capital=capital, comision_pct=comision_pct)


def _proponer_evidencia(simbolo, evidencia, *, capital, comision_pct):
    """Uso interno: evidencia H1 o replay comprobado; no autentica entradas."""
    analisis = evidencia['analisis']
    referencia = analisis['temporalidades']['1h']['precio']
    plan = crear_plan_con_datos(
        simbolo, analisis, capital=capital, precio=referencia,
        comision_pct=comision_pct, modo='PAPER', real_bloqueado=False)
    decision_reglas = plan['decision']
    # No exponer como candidato ejecutable por los consumidores del scanner.
    plan['decision'] = ('PROPUESTA HISTORICA' if decision_reglas == 'PAPER CANDIDATE'
                        else 'ESPERAR')
    return {
        'tipo': 'PROPUESTA_HISTORICA_NO_EJECUTABLE',
        'ejecutable': False, 'fill_confirmado': False, 'precio_fill': None,
        'decision_reglas': decision_reglas, 'propuesta': plan,
        'analisis_historico': evidencia,
        'referencia': {'tipo': 'CIERRE_1H_CONOCIDO_NO_COTIZACION',
                       'precio': referencia,
                       'tiempo_cierre_ms': evidencia['ventanas']['1h']['ultima_cierre_ms']},
        'politica_capital': 'APORTADO_POR_LLAMANTE_SIN_EVOLUCION_DE_CARTERA',
        'comision_pct_aportada': comision_pct,
        'limites': ['No acredita fill al cierre1h ni cotización al instante de señal.',
                    'No verifica saldo libre, riesgo diario ni posiciones simultáneas.',
                    'El capital explícito no representa por sí solo reinversión histórica.',
                    'No reproduce radar dinámico ni demuestra rentabilidad.'],
    }
