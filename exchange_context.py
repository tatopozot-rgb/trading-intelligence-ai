"""Normalización diagnóstica de exchangeInfo público. No es contexto Testnet."""
from copy import deepcopy

from execution_context import hash_contenido, ContextoInvalido, _tiempo
from execution_filters import decimal_texto, validar_limite_offline
from execution_ledger import texto

ORIGEN = 'BINANCE_PUBLIC_MARKET_DATA'
ESTATICOS = {'PRICE_FILTER', 'LOT_SIZE', 'MIN_NOTIONAL', 'NOTIONAL'}
NO_APLICAN_LIMIT_SIMPLE = {'MARKET_LOT_SIZE', 'ICEBERG_PARTS', 'TRAILING_DELTA'}
DINAMICOS = {'PERCENT_PRICE', 'PERCENT_PRICE_BY_SIDE'}
CUENTA = {'MAX_NUM_ORDERS', 'MAX_NUM_ALGO_ORDERS', 'MAX_NUM_ICEBERG_ORDERS',
          'MAX_POSITION', 'MAX_NUM_ORDER_AMENDS', 'MAX_NUM_ORDER_LISTS'}
# Campos de filtros publicados; un campo nuevo no se elimina ni se aprueba.
CAMPOS_FILTRO = {
    'PRICE_FILTER': ('minPrice', 'maxPrice', 'tickSize'),
    'LOT_SIZE': ('minQty', 'maxQty', 'stepSize'),
    'MARKET_LOT_SIZE': ('minQty', 'maxQty', 'stepSize'),
    'MIN_NOTIONAL': ('minNotional', 'applyToMarket', 'avgPriceMins'),
    'NOTIONAL': ('minNotional', 'maxNotional', 'applyMinToMarket', 'applyMaxToMarket', 'avgPriceMins'),
    'ICEBERG_PARTS': ('limit',),
    'TRAILING_DELTA': ('minTrailingAboveDelta', 'maxTrailingAboveDelta', 'minTrailingBelowDelta', 'maxTrailingBelowDelta'),
    'PERCENT_PRICE': ('multiplierUp', 'multiplierDown', 'avgPriceMins'),
    'PERCENT_PRICE_BY_SIDE': ('bidMultiplierUp', 'bidMultiplierDown', 'askMultiplierUp', 'askMultiplierDown', 'avgPriceMins'),
    'MAX_NUM_ORDERS': ('maxNumOrders',), 'MAX_NUM_ALGO_ORDERS': ('maxNumAlgoOrders',),
    'MAX_NUM_ICEBERG_ORDERS': ('maxNumIcebergOrders',), 'MAX_POSITION': ('maxPosition',),
    'MAX_NUM_ORDER_AMENDS': ('maxNumOrderAmends',), 'MAX_NUM_ORDER_LISTS': ('maxNumOrderLists',),
}
ENTEROS = {'avgPriceMins', 'limit', 'maxNumOrders', 'maxNumAlgoOrders', 'maxNumIcebergOrders',
           'maxNumOrderAmends', 'maxNumOrderLists', 'minTrailingAboveDelta', 'maxTrailingAboveDelta',
           'minTrailingBelowDelta', 'maxTrailingBelowDelta'}
BOOLEANOS = {'applyToMarket', 'applyMinToMarket', 'applyMaxToMarket'}


def _lista_textos(valores):
    if type(valores) is not list or not valores:
        raise ContextoInvalido('Lista textual no vacía requerida.')
    for valor in valores:
        texto(valor, 'elemento')
    if len(set(valores)) != len(valores):
        raise ContextoInvalido('Elementos duplicados.')


def permisos_compatibles(conjuntos, permisos_cuenta):
    """AND entre conjuntos, OR dentro; solo evaluación de evidencia suministrada."""
    if type(conjuntos) is not list or not conjuntos:
        raise ContextoInvalido('Faltan permissionSets explícitos.')
    for conjunto in conjuntos:
        _lista_textos(conjunto)
    if type(permisos_cuenta) is not list:
        raise ContextoInvalido('Permisos de cuenta requieren lista explícita.')
    if permisos_cuenta:
        _lista_textos(permisos_cuenta)
    return all(any(p in permisos_cuenta for p in grupo) for grupo in conjuntos)


def _filtros(filtros):
    if type(filtros) is not list:
        raise ContextoInvalido('Filtros requieren lista.')
    vistos = set()
    desconocidos = []
    for filtro in filtros:
        if type(filtro) is not dict:
            raise ContextoInvalido('Filtro inválido.')
        tipo = texto(filtro.get('filterType'), 'filterType')
        if tipo in vistos:
            raise ContextoInvalido('Filtro duplicado.')
        vistos.add(tipo)
        campos = CAMPOS_FILTRO.get(tipo)
        if campos is None:
            desconocidos.append(tipo)
            continue
        if not set(campos) <= set(filtro):
            raise ContextoInvalido('Filtro incompleto: '+tipo)
        for campo in campos:
            valor = filtro[campo]
            if campo in BOOLEANOS:
                if type(valor) is not bool:
                    raise ContextoInvalido('Flag inválido.')
            elif campo in ENTEROS:
                _tiempo(valor)  # Mismo contrato entero no negativo, no bool.
            else:
                decimal_texto(valor)
        if set(filtro) != {'filterType', *campos}:
            desconocidos.append(tipo+':CAMPOS_NUEVOS')
    return sorted(vistos), desconocidos


def normalizar_exchange_info(respuesta, *, simbolo_esperado, obtenido_ms, origen):
    """Preserva respuesta completa y su hash; exige consulta de un solo símbolo.

    obtenido_ms es recepción local aportada, no serverTime ni prueba de frescura.
    La etiqueta de origen no autentica al proveedor; el transporte debe fijarla.
    """
    if origen != ORIGEN:
        raise ContextoInvalido('Origen público explícito requerido; no renombrar a Testnet.')
    texto(simbolo_esperado, 'simbolo')
    _tiempo(obtenido_ms)
    hash_respuesta = hash_contenido(respuesta)
    dato = deepcopy(respuesta)
    if type(dato) is not dict or not {'timezone','serverTime','rateLimits','exchangeFilters','symbols'} <= set(dato):
        raise ContextoInvalido('exchangeInfo incompleto.')
    if dato['timezone'] != 'UTC':
        raise ContextoInvalido('Timezone no soportado.')
    _tiempo(dato['serverTime'])
    if type(dato['symbols']) is not list or len(dato['symbols']) != 1:
        raise ContextoInvalido('Se exige respuesta de un solo símbolo.')
    s = dato['symbols'][0]
    if type(s) is not dict or not {'symbol','status','baseAsset','quoteAsset','orderTypes','isSpotTradingAllowed','filters','permissionSets'} <= set(s):
        raise ContextoInvalido('Símbolo incompleto.')
    if s['symbol'] != simbolo_esperado:
        raise ContextoInvalido('Símbolo discordante.')
    for k in ('symbol','status','baseAsset','quoteAsset'):
        texto(s[k], k)
    if type(s['isSpotTradingAllowed']) is not bool:
        raise ContextoInvalido('Permiso Spot no booleano.')
    _lista_textos(s['orderTypes'])
    permisos_compatibles(s['permissionSets'], [])  # Valida estructura sin inventar permisos.
    tipos, desconocidos = _filtros(s['filters'])
    globales, desconocidos_globales = _filtros(dato['exchangeFilters'])
    if type(dato['rateLimits']) is not list or not dato['rateLimits']:
        raise ContextoInvalido('Límites de tasa ausentes.')
    for limite in dato['rateLimits']:
        if type(limite) is not dict or not {'rateLimitType','interval','intervalNum','limit'} <= set(limite):
            raise ContextoInvalido('Límite de tasa incompleto.')
        texto(limite['rateLimitType'], 'rateLimitType')
        texto(limite['interval'], 'interval')
        if _tiempo(limite['intervalNum']) == 0 or _tiempo(limite['limit']) == 0:
            raise ContextoInvalido('Límite de tasa no positivo.')
    return {'schema':'PUBLIC_EXCHANGE_INFO_V1', 'origen':ORIGEN, 'obtenido_ms':obtenido_ms,
            'hash_respuesta':hash_respuesta, 'respuesta':dato, 'tipos_filtro':tipos,
            # Solo excluye serverTime. Permisos, precisiones, límites y campos nuevos permanecen.
            'hash_reglas':hash_contenido({'schema':'REGLAS_PUBLICAS_V1','origen':ORIGEN,
                                          'contenido':{k:v for k,v in dato.items() if k != 'serverTime'}}),
            'filtros_exchange':globales, 'no_clasificados':desconocidos+desconocidos_globales,
            'campos_raiz_adicionales':sorted(set(dato)-{'timezone','serverTime','rateLimits','exchangeFilters','symbols'}),
            'campos_simbolo_no_evaluados':sorted(set(s)-{'symbol','status','baseAsset','quoteAsset','orderTypes',
                                                       'isSpotTradingAllowed','filters','permissionSets'}),
            'enviable':False, 'autorizado':False}


def diagnosticar_limite_publico(orden, respuesta, *, obtenido_ms, origen):
    """No elimina controles para aprobar: evalúa estáticos y enumera TODO lo pendiente."""
    if type(orden) is not dict:
        raise ContextoInvalido('Orden de fixture requerida.')
    normal = normalizar_exchange_info(respuesta, simbolo_esperado=orden.get('symbol'),
                                     obtenido_ms=obtenido_ms, origen=origen)
    s = normal['respuesta']['symbols'][0]
    estaticos = {**s, 'filters':[f for f in s['filters'] if f['filterType'] in ESTATICOS]}
    # E1 impone EXACTAMENTE seis campos de LIMIT simple: ni iceberg, trailing ni órdenes compuestas.
    evaluacion = validar_limite_offline(orden, estaticos)
    pendientes = ['PERMISOS_CUENTA_NO_VERIFICADOS', 'FILTROS_PRIVADOS_NO_VERIFICADOS', 'VIGENCIA_NO_VERIFICADA']
    clasificacion = {}
    for tipo in normal['tipos_filtro']:
        if tipo in ESTATICOS:
            clasificacion[tipo] = 'ESTATICO_EVALUADO'
        elif tipo in NO_APLICAN_LIMIT_SIMPLE:
            clasificacion[tipo] = 'NO_APLICA_LIMIT_SIMPLE'
        else:
            clasificacion[tipo] = ('REQUIERE_PRECIO_REFERENCIA' if tipo in DINAMICOS else
                                   'REQUIERE_CONTEXTO_CUENTA' if tipo in CUENTA else 'DESCONOCIDO')
            pendientes.append(tipo)
    pendientes += normal['no_clasificados'] + normal['filtros_exchange']
    if normal['campos_raiz_adicionales']:
        pendientes.append('CAMPOS_RAIZ_NUEVOS')
    if normal['campos_simbolo_no_evaluados']:
        pendientes.append('METADATOS_SIMBOLO_NO_EVALUADOS')
    return {'modo':'DIAGNOSTICO_PUBLICO', 'estado':'NO_VALIDABLE_PARA_ENVIO', 'enviable':False,
            'autorizado':False, 'hash_respuesta':normal['hash_respuesta'], 'hash_reglas':normal['hash_reglas'], 'clasificacion':clasificacion,
            'pendientes':sorted(set(pendientes)), 'estaticos':evaluacion, 'normalizado':normal}


def consultar_contexto_publico(simbolo):
    """Entrada de red explícita: ruta/origen/lector estrictos, sin opciones para omitirlos.

    normalizar_exchange_info acepta dicts para fixtures; no acredita cómo fueron decodificados.
    Esta es la entrada pública soportada cuando se consulta red. Nunca se llama al importar.
    """
    import time
    from market_http import get_publico
    from execution_context import cargar_json_contexto
    texto(simbolo, 'simbolo')
    dato = get_publico('/api/v3/exchangeInfo', {'symbol':simbolo}, decodificador=cargar_json_contexto)
    return normalizar_exchange_info(dato, simbolo_esperado=simbolo, obtenido_ms=time.time_ns()//1000000,
                                   origen=ORIGEN)
