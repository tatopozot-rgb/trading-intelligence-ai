"""Ejecución determinista exclusivamente PAPER durante sesión explícita.

Reutiliza candidatos y límites existentes. No llama IA ni fabrica sus respuestas.
"""
import paper_store as store
from paper_monitor import obtener_precio_actual


def procesar_candidatos(resultados, sesion_activa, *, profundidad=False, sombra=False):
    """sombra=True: mismo recorrido y mismo veredicto, pero sin abrir operaciones (SHADOW)."""
    store.validar_paper()
    ejecutar = store.ejecutar_reglas_shadow if sombra else store.ejecutar_reglas
    if sesion_activa is None:
        raise ValueError('El modo por reglas exige una sesión explícita.')
    store.comprobar_sesion(sesion_activa)
    decisiones = []
    for resultado in resultados:
        store.comprobar_sesion(sesion_activa)
        if 'error' in resultado:
            continue
        plan = resultado.get('plan', {})
        if plan.get('decision') != 'PAPER CANDIDATE':
            continue
        if plan.get('consenso') != 'ALCISTA' or plan.get('estado') != 'ALCISTA MOMENTUM SANO':
            raise ValueError('Candidato incompatible con estrategia vigente.')
        plan = {**plan, 'origen_revision': 'REGLAS_PAPER_V1'}
        if profundidad:
            from paper_fills import MODELO
            plan['modelo_fill_paper'] = MODELO
        identidad, digest = store.registrar_solicitud(plan, True, sesion_activa)
        try:
            store.comprobar_sesion(sesion_activa)
            if profundidad:
                from paper_fills import cotizar, evidencia
                snapshot = cotizar(plan['simbolo'])
                fill = evidencia(snapshot, lado='BUY', monto=plan['tamano_posicion'],
                                 comision_pct=plan['comision_paper_pct'],
                                 ahora_ms=int(store.ahora().timestamp()*1000))
                if fill['resultado']['estado'] != 'COMPLETO':
                    raise ValueError('PROFUNDIDAD_VISIBLE_INSUFICIENTE: FOK PAPER no registrado.')
                precio = float(fill['resultado']['precio_medio'])
                decision = ejecutar(identidad, digest, precio, sesion_activa, evidencia_fill=fill)
            else:
                precio = obtener_precio_actual(plan['simbolo'])
                decision = ejecutar(identidad, digest, precio, sesion_activa)
        except store.SesionFinalizada:
            raise
        except ValueError as error:
            store.registrar_rechazo('shadow_paper' if sombra else 'reglas_paper', {'request_id': identidad}, error)
            decision = {'registrada': False, 'motivo': str(error), 'request_id': identidad}
            if sombra:
                decision.update(sombra=True, abriria=False)
        decisiones.append(decision)
    return decisiones
