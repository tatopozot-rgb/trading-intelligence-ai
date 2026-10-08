"""Integridad y vigencia de fixtures OFFLINE, sin firma, reloj global ni envío.

SHA256 detecta cambios respecto de una referencia fijada; NO autentica al autor.
La serialización es un contrato local versionado, no una implementación de JCS.
"""
import hashlib
import json
import re

from execution_filters import validar_limite_offline
from execution_ledger import ENTORNO, texto
from execution_orders import validar_intencion


class ContextoInvalido(ValueError):
    pass


def cargar_json_contexto(contenido):
    """Entrada textual estricta; nunca resolver claves duplicadas con 'última gana'."""
    if type(contenido) is not str or len(contenido) > 100000:
        raise ContextoInvalido('JSON textual acotado requerido.')

    def pares(items):
        dato = {}
        for clave, valor in items:
            if clave in dato:
                raise ContextoInvalido('Clave JSON repetida.')
            dato[clave] = valor
        return dato

    def numero_no_admitido(_):
        raise ContextoInvalido('Los decimales deben ser texto; no float/NaN/Infinity.')

    try:
        if len(contenido.encode('utf-8')) > 100000:
            raise ContextoInvalido('JSON demasiado grande.')
        dato = json.loads(contenido, object_pairs_hook=pares, parse_float=numero_no_admitido,
                          parse_constant=numero_no_admitido)
        hash_contenido(dato)  # Aplica tipos, profundidad y límites antes de devolverlo.
    except (ValueError, RecursionError, UnicodeError) as error:
        raise ContextoInvalido('JSON de contexto no válido.') from error
    return dato


def hash_contenido(dato):
    """JSON local: objetos ordenados, listas ordenadas, sin float/NaN ni coerción."""
    nodos = 0

    def recorrer(valor, profundidad=0):
        nonlocal nodos
        nodos += 1
        if nodos > 10000 or profundidad > 16:
            raise ContextoInvalido('Contenido demasiado complejo.')
        tipo = type(valor)
        if tipo is dict:
            for k, v in valor.items():
                if type(k) is not str or len(k) > 1000:
                    raise ContextoInvalido('Clave JSON inválida.')
                recorrer(v, profundidad + 1)
        elif tipo is list:
            for v in valor:
                recorrer(v, profundidad + 1)
        elif tipo is str:
            if len(valor) > 10000:
                raise ContextoInvalido('Texto demasiado largo.')
        elif tipo is int:
            if not -(2**63) <= valor < 2**63:
                raise ContextoInvalido('Entero fuera del contrato.')
        elif tipo is not bool:
            raise ContextoInvalido('Tipo JSON no admitido; no se convierten números.')

    recorrer(dato)
    digest = hashlib.sha256()
    longitud = 0
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
    for fragmento in encoder.iterencode(dato):
        contenido = fragmento.encode('ascii')
        longitud += len(contenido)
        if longitud > 100000:
            raise ContextoInvalido('Contenido demasiado grande.')
        digest.update(contenido)
    return digest.hexdigest()


def _campos(dato, campos):
    if type(dato) is not dict or set(dato) != set(campos):
        raise ContextoInvalido('Campos ausentes o no soportados.')


def _tiempo(valor):
    if type(valor) is not int or not 0 <= valor < 2**63:
        raise ContextoInvalido('Tiempo/duración requiere entero no negativo en ms.')
    return valor


def _hash(valor):
    if type(valor) is not str or re.fullmatch('[0-9a-f]{64}', valor) is None:
        raise ContextoInvalido('Hash SHA256 textual inválido.')
    return valor


def _verificar_integridad_contexto(plan, snapshot, *, plan_hash_esperado, cuenta_esperada,
                                   ahora_ms, max_edad_ms):
    """Verifica contenido COMPLETO antes de que un evaluador distribuya sus filtros."""
    if type(plan) is not dict:
        raise ContextoInvalido('Plan requerido.')
    extras = ('evidencias_hash','politica') if plan.get('schema') == 'PLAN_EVALUACION_FIXTURE_V2' else ()
    _campos(plan, ('schema', 'entorno', 'cuenta', 'parametros', 'snapshot_hash', 'creado_ms', 'vence_ms', *extras))
    _campos(snapshot, ('schema', 'entorno', 'obtenido_ms', 'simbolo'))
    if plan['schema'] not in ('PLAN_OFFLINE_V1','PLAN_EVALUACION_FIXTURE_V2') or snapshot['schema'] != 'SNAPSHOT_OFFLINE_V1':
        raise ContextoInvalido('Versión no soportada.')
    if plan['entorno'] != ENTORNO or snapshot['entorno'] != ENTORNO:
        raise ContextoInvalido('Solo TESTNET_FIXTURE.')
    texto(cuenta_esperada, 'cuenta_esperada')
    if plan['cuenta'] != cuenta_esperada:
        raise ContextoInvalido('Cuenta distinta de referencia.')
    plan_hash = hash_contenido(plan)
    snapshot_hash = hash_contenido(snapshot)
    if plan_hash != _hash(plan_hash_esperado) or snapshot_hash != _hash(plan['snapshot_hash']):
        raise ContextoInvalido('Contenido alterado o referencia discordante.')
    ahora, edad_max, creado, vence, obtenido = map(_tiempo,
        (ahora_ms, max_edad_ms, plan['creado_ms'], plan['vence_ms'], snapshot['obtenido_ms']))
    if not obtenido <= creado <= ahora < vence:
        raise ContextoInvalido('Plan futuro/caducado o cronología incompatible.')
    if ahora - obtenido > edad_max:
        raise ContextoInvalido('Snapshot caducado.')
    return {'modo':'OFFLINE','enviable':False,'plan_hash': plan_hash,
            'snapshot_hash': snapshot_hash, 'edad_ms': ahora - obtenido,
            'autorizado': False}


def validar_contexto_offline(plan, snapshot, *, plan_hash_esperado, cuenta_esperada,
                            ahora_ms, max_edad_ms):
    """Contrato V1 estático, sin cambios: no acepta planes V2 por esta entrada."""
    if type(plan) is not dict or plan.get('schema') != 'PLAN_OFFLINE_V1':
        raise ContextoInvalido('Esta entrada requiere PLAN_OFFLINE_V1.')
    integridad = _verificar_integridad_contexto(plan, snapshot, plan_hash_esperado=plan_hash_esperado,
        cuenta_esperada=cuenta_esperada, ahora_ms=ahora_ms, max_edad_ms=max_edad_ms)
    filtros = validar_limite_offline(plan['parametros'], snapshot['simbolo'])
    return {**integridad, **filtros, 'estado':'CONTEXTO_OFFLINE_VERIFICADO'}


def validar_contexto_intencion(intencion, plan, snapshot, *, ahora_ms, max_edad_ms):
    """Une E2 con E1/E3 sin cambiar estado ni autorizar una simulación/envío."""
    validar_intencion(intencion)
    _campos(plan, ('schema', 'entorno', 'cuenta', 'parametros', 'snapshot_hash', 'creado_ms', 'vence_ms'))
    if (hash_contenido(intencion['parametros']) != hash_contenido(plan['parametros']) or
            intencion['snapshot_hash'] != plan['snapshot_hash']):
        raise ContextoInvalido('La intención no corresponde al plan/snapshot.')
    return validar_contexto_offline(plan, snapshot, plan_hash_esperado=intencion['plan_hash'],
        cuenta_esperada=intencion['cuenta'], ahora_ms=ahora_ms, max_edad_ms=max_edad_ms)
