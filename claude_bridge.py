"""Exportación compacta para el chat existente de Claude; sin llamadas de pago."""
import json
import os
import config
import paper_store as store

DIRECTORIO = config.DIRECTORIO
RUTA_JSON = DIRECTORIO / "claude_request.json"
RUTA_TEXTO = DIRECTORIO / "claude_request.txt"


def guardar_atomico(ruta, texto):
    temporal = ruta.with_suffix(ruta.suffix + '.tmp')
    temporal.write_text(texto, encoding='utf-8')
    os.replace(temporal, ruta)


def crear_solicitud_claude(resultados, modo_prueba=False, sesion_activa=None):
    store.comprobar_sesion(sesion_activa)
    store.caducar_solicitudes()
    seleccion = [r for r in resultados if r.get('plan', {}).get('decision') == 'PAPER CANDIDATE']
    if modo_prueba:
        # Toda prueba es no ejecutable, incluso si aparece una oportunidad válida.
        seleccion = [r for r in resultados if 'analisis' in r and 'plan' in r][:1]
    solicitudes = []
    for r in seleccion:
        store.comprobar_sesion(sesion_activa)
        plan = r['plan']
        # No regenerar la misma solicitud mientras espera respuesta y sigue vigente.
        with store.conectar() as con:
            anterior = con.execute("SELECT id FROM paper_requests WHERE estado='PENDIENTE' AND expira>? AND plan_hash=?",
                (store.ahora().isoformat(), store.huella(plan))).fetchone()
        if anterior and not modo_prueba:
            continue
        identidad, digest = store.registrar_solicitud(plan, not modo_prueba, sesion_activa)
        datos = {
            'request_id': identidad, 'plan_hash': digest, 'simbolo': plan['simbolo'],
            'ejecutable': not modo_prueba, 'plan': plan,
            'indicadores': {t: {k: round(float(d[k]), 4) if k != 'tendencia' else d[k]
                for k in ('tendencia', 'rsi', 'atr_pct')} for t, d in r['analisis']['temporalidades'].items()},
        }
        solicitudes.append(datos)
    paquete = {
        'version': 2, 'modo': 'PAPER',
        'tipo': 'PRUEBA_NO_EJECUTABLE' if modo_prueba else 'REVISION_PAPER',
        'creado_utc': store.ahora().isoformat(),
        'saldo_paper': store.cuenta()['saldo_actual'],
        'caducidad_minutos': config.MINUTOS_MAXIMOS_RESPUESTA_CLAUDE,
        'solicitudes': solicitudes,
    }
    esquema = {'respuestas': [{'request_id': 'copiar ID', 'plan_hash': 'copiar hash',
        'simbolo': 'copiar símbolo', 'decision': 'APROBAR_PAPER o RECHAZAR',
        'confianza': 0, 'razon': 'máximo 200 caracteres'}]}
    texto = (
        'Continuamos TRADING INTELLIGENCE, exclusivamente simulación PAPER. '
        'Revisa cada propuesta con los indicadores suministrados; no cambies sus parámetros. '
        'No consultes herramientas ni inventes noticias. Confianza es juicio subjetivo, no probabilidad calibrada. '
        'El campo confianza debe ser un ENTERO entre 0 y 100 (ejemplo: 92), nunca decimal como 0.92. '
        'Rechaza pruebas no ejecutables, datos insuficientes o sobreextensión. '
        'Tu revisión no sustituye la autorización local ni los controles de riesgo. '
        'Devuelve solo JSON, sin bloques Markdown ni texto adicional, una respuesta por solicitud.\nESQUEMA: '
        + store.serializar(esquema) + '\nDATOS: ' + store.serializar(paquete)
    )
    # Una publicación ya iniciada termina sus archivos; no borramos registros confirmados.
    store.comprobar_sesion(sesion_activa)
    guardar_atomico(RUTA_JSON, json.dumps(paquete, ensure_ascii=False, indent=2, allow_nan=False))
    guardar_atomico(RUTA_TEXTO, texto if solicitudes else 'Sin candidatos nuevos; no enviar a Claude.')
    if not solicitudes:
        return None
    archivo = DIRECTORIO / 'solicitudes'
    archivo.mkdir(exist_ok=True)
    guardar_atomico(archivo / (solicitudes[0]['request_id']+'.json'), store.serializar(paquete))
    guardar_atomico(archivo / (solicitudes[0]['request_id']+'.txt'), texto)
    return {'tipo': paquete['tipo'], 'cantidad': len(solicitudes), 'ruta_texto': str(RUTA_TEXTO)}


if __name__ == '__main__':
    raise SystemExit('Generar con system_runner.py --prueba-claude o con un ciclo normal.')
