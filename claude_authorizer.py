"""Importación de revisión Claude y autorización local de una propuesta inmutable."""
import argparse
import json
from pathlib import Path

import config
import paper_store as store
from paper_monitor import obtener_precio_actual


def cargar_respuestas(ruta):
    ruta = Path(ruta)
    with ruta.open('rb') as archivo:
        contenido = archivo.read(100_001)
    if len(contenido) > 100_000:
        raise ValueError('Archivo de respuesta demasiado grande.')
    def pares_unicos(pares):
        objeto = {}
        for clave, valor in pares:
            if clave in objeto:
                raise ValueError('JSON con claves duplicadas.')
            objeto[clave] = valor
        return objeto
    def constante_invalida(_):
        raise ValueError('JSON contiene número no finito.')
    datos = json.loads(contenido.decode('utf-8-sig'), object_pairs_hook=pares_unicos,
                       parse_constant=constante_invalida)
    respuestas = datos.get('respuestas') if isinstance(datos, dict) else None
    if not isinstance(respuestas, list) or not 1 <= len(respuestas) <= 5:
        raise ValueError('Se espera un objeto con lista respuestas, máximo cinco.')
    if any(not isinstance(r, dict) for r in respuestas):
        raise ValueError('Respuesta inválida.')
    ids = [r.get('request_id') for r in respuestas]
    if any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('IDs inválidos o repetidos.')
    return respuestas


def procesar(respuesta, automatico=False, confirmar=input, sesion_activa=None):
    try:
        store.caducar_solicitudes()
        return _procesar(respuesta, automatico, confirmar, sesion_activa)
    except Exception as error:
        store.registrar_rechazo('importacion_respuesta',respuesta,error)
        raise


def _procesar(respuesta, automatico=False, confirmar=input, sesion_activa=None):
    store.validar_paper()
    fila = store.leer_solicitud(respuesta.get('request_id'))
    plan = store.validar_respuesta(fila, respuesta)
    if respuesta['decision'] == 'RECHAZAR':
        return store.ejecutar_respuesta(respuesta, '')
    autorizacion = ''
    if not automatico:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        autorizacion = confirmar('Para registrar SOLO PAPER escribe OK ' + fila['id'] + ': ').strip()
        if autorizacion != 'OK ' + fila['id']:
            store.registrar_rechazo('autorizacion_manual',respuesta,'No autorizado por el usuario.')
            return {'registrada': False, 'motivo': 'No autorizado por el usuario.'}
    # No recalcular el plan aprobado. Cotizar ahora y rechazar si cambió demasiado.
    if automatico and (sesion_activa is None or not sesion_activa()):
        raise ValueError('Sesión automática ausente, detenida o caducada.')
    precio = obtener_precio_actual(plan['simbolo'])
    return store.ejecutar_respuesta(respuesta, autorizacion, precio, automatico, sesion_activa)


def procesar_archivo(ruta, automatico=False, confirmar=input, sesion_activa=None):
    resultados = []
    try:
        respuestas = cargar_respuestas(ruta)
    except Exception as error:
        store.registrar_rechazo('archivo_respuesta',None,type(error).__name__)
        raise
    for respuesta in respuestas:
        try:
            resultados.append(procesar(respuesta, automatico, confirmar, sesion_activa))
        except (ValueError, KeyError, TypeError) as error:
            resultados.append({'registrada': False, 'motivo': str(error)})
    return resultados


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archivo', type=Path, default=config.DIRECTORIO/'claude_response.json')
    args = parser.parse_args()
    print(json.dumps(procesar_archivo(args.archivo), ensure_ascii=False, indent=2))
