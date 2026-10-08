"""Evaluación conjunta de filtros de fixture, ligada a intención. Nunca autoriza."""
from execution_context import (ContextoInvalido, hash_contenido, _campos, _hash,
                               _tiempo, _verificar_integridad_contexto)
from execution_orders import validar_intencion
from execution_filters import validar_limite_offline
from execution_percent import validar_porcentaje_offline

ESTATICOS = {'PRICE_FILTER','LOT_SIZE','MIN_NOTIONAL','NOTIONAL'}
PORCENTUALES = {'PERCENT_PRICE','PERCENT_PRICE_BY_SIDE'}
FORMA_ESTATICA = {
    'PRICE_FILTER':({'minPrice','maxPrice','tickSize'},set()),
    'LOT_SIZE':({'minQty','maxQty','stepSize'},set()),
    'MIN_NOTIONAL':({'minNotional'},{'applyToMarket','avgPriceMins'}),
    'NOTIONAL':({'minNotional','maxNotional'},{'applyMinToMarket','applyMaxToMarket','avgPriceMins'}),
}


def evaluar_paquete_fixture(intencion, plan, snapshot, evidencias, *, ahora_ms, limites_politica):
    """Políticas, hashes y parámetros son inmutables en el plan, no flags de envío.

    El llamador debe aportar la intención desde almacenamiento confiable. Esta función
    no verifica identidad del autor ni consulta la BD; no modifica estados ni crea planes.
    """
    validar_intencion(intencion)
    _campos(plan, ('schema','entorno','cuenta','parametros','snapshot_hash','creado_ms','vence_ms',
                  'evidencias_hash','politica'))
    if plan['schema'] != 'PLAN_EVALUACION_FIXTURE_V2':
        raise ContextoInvalido('Paquete requiere plan V2 explícito.')
    _campos(plan['politica'], ('max_edad_snapshot_ms','max_edad_referencia_ms'))
    _campos(limites_politica, ('max_edad_snapshot_ms','max_edad_referencia_ms','max_vigencia_plan_ms'))
    for valor in limites_politica.values():
        _tiempo(valor)
    for valor in plan['politica'].values():
        _tiempo(valor)
    if any(plan['politica'][k] > limites_politica[k] for k in plan['politica']):
        raise ContextoInvalido('Política de plan más laxa que el límite externo.')
    if (hash_contenido(intencion['parametros']) != hash_contenido(plan['parametros']) or
            intencion['snapshot_hash'] != plan['snapshot_hash']):
        raise ContextoInvalido('Parámetros o snapshot distintos de intención.')
    integridad = _verificar_integridad_contexto(plan,snapshot,plan_hash_esperado=intencion['plan_hash'],
        cuenta_esperada=intencion['cuenta'],ahora_ms=ahora_ms,max_edad_ms=plan['politica']['max_edad_snapshot_ms'])
    if plan['vence_ms']-plan['creado_ms'] > limites_politica['max_vigencia_plan_ms']:
        raise ContextoInvalido('Vigencia del plan supera el límite externo.')
    simbolo = snapshot['simbolo']
    _campos(simbolo, ('symbol','status','isSpotTradingAllowed','orderTypes','filters'))
    filtros = simbolo['filters']
    if type(filtros) is not list or not filtros:
        raise ContextoInvalido('Lista de filtros requerida.')
    por_tipo = {}
    for filtro in filtros:
        if type(filtro) is not dict or type(filtro.get('filterType')) is not str:
            raise ContextoInvalido('Filtro mal formado.')
        tipo = filtro['filterType']
        if tipo in por_tipo or tipo not in ESTATICOS | PORCENTUALES:
            raise ContextoInvalido('Filtro duplicado o no soportado: '+tipo)
        if tipo in ESTATICOS:
            requeridos, opcionales = FORMA_ESTATICA[tipo]
            campos = set(filtro)-{'filterType'}
            if not requeridos <= campos <= requeridos | opcionales:
                raise ContextoInvalido('Campos estáticos ausentes o no soportados.')
            for campo in campos & opcionales:
                if campo == 'avgPriceMins':
                    _tiempo(filtro[campo])
                elif type(filtro[campo]) is not bool:
                    raise ContextoInvalido('Flag de filtro no booleano.')
        por_tipo[tipo] = filtro
    dinamicos = set(por_tipo) & PORCENTUALES
    if (type(evidencias) is not dict or type(plan['evidencias_hash']) is not dict or
            set(evidencias) != dinamicos or set(plan['evidencias_hash']) != dinamicos):
        raise ContextoInvalido('Evidencia/hash faltante o sobrante para filtros declarados.')
    hash_contenido(evidencias)  # Limita también el conjunto antes de evaluar partes.
    # Nada desconocido fue eliminado: ya se rechazó arriba. Proyección interna, no snapshot nuevo.
    estatica = validar_limite_offline(plan['parametros'], {**simbolo,
        'filters':[f for t,f in por_tipo.items() if t in ESTATICOS]})
    resultados = []
    referencia_comun = None
    for tipo in sorted(dinamicos):
        evidencia = evidencias[tipo]
        esperado = _hash(plan['evidencias_hash'][tipo])
        if hash_contenido(evidencia) != esperado:
            raise ContextoInvalido('Evidencia no ligada al plan.')
        resultado = validar_porcentaje_offline(plan['parametros'],por_tipo[tipo],evidencia,
            simbolo_filtro=simbolo['symbol'],filtro_hash_esperado=hash_contenido(por_tipo[tipo]),
            evidencia_hash_esperado=esperado,ahora_ms=ahora_ms,
            max_edad_ms=plan['politica']['max_edad_referencia_ms'])
        # Toda evidencia ligada ya existía al crear el plan; no firmar datos del futuro.
        piezas = [evidencia['referencia']]
        if 'sustituto' in evidencia:
            piezas.append(evidencia['sustituto'])
            if any(evidencia['sustituto'][k] != evidencia['referencia'][k] for k in ('observado_ms','recibido_ms')):
                raise ContextoInvalido('Fixture sustituto no pertenece a la misma observación/recepción.')
        if any(p['recibido_ms'] > plan['creado_ms'] for p in piezas):
            raise ContextoInvalido('Evidencia recibida después de crear el plan.')
        ref_hash = hash_contenido(evidencia['referencia'])
        if referencia_comun is not None and referencia_comun != ref_hash:
            raise ContextoInvalido('Filtros usan estados de referencia incompatibles.')
        referencia_comun = ref_hash
        resultados.append(resultado)
    return {**integridad,'estado':'FILTROS_DECLARADOS_VERIFICADOS_OFFLINE','enviable':False,'autorizado':False,
            'intencion_id':intencion['id_local'],'filtros_evaluados':sorted(por_tipo),
            'estaticos':estatica,'porcentuales':resultados,'evidencias_hash':dict(plan['evidencias_hash']),
            'limites_politica_hash':hash_contenido(limites_politica),
            'pendientes':['AUTORIZACION','RIESGO_Y_CUENTA','FILTROS_PRIVADOS','PRICE_RANGE','PROTECCION','TRANSPORTE']}
