"""Contrato OFFLINE de filtros MARKET, versión MARKET_FILTERS_OFFLINE_V1.

No autoriza, firma ni envía órdenes. Falla cerrado: lo no verificado se rechaza.

Verificado en la documentación oficial de Binance Spot (sección filters): MARKET_LOT_SIZE y
LOT_SIZE exigen minQty <= cantidad <= maxQty y cantidad % stepSize == 0. No se redondea.

NO verificado en esa fuente, por eso se resuelve de forma conservadora:
- si LOT_SIZE aplica además de MARKET_LOT_SIZE: se exigen ambos, si falta uno se rechaza;
- la semántica de quoteOrderQty: se rechaza cualquier orden que lo contenga.
"""
from decimal import (Context, DivisionByZero, InvalidOperation, Overflow,
                     ROUND_HALF_EVEN, localcontext)

from execution_filters import FiltroInvalido, decimal_texto

VERSION = 'MARKET_FILTERS_OFFLINE_V1'
CAMPOS_ORDEN = frozenset({'symbol', 'side', 'type', 'quantity'})
FILTROS_PERMITIDOS = frozenset({'MARKET_LOT_SIZE', 'LOT_SIZE', 'MIN_NOTIONAL', 'NOTIONAL'})
FILTROS_REQUERIDOS = frozenset({'MARKET_LOT_SIZE', 'LOT_SIZE'})


def _contexto():
    # Contexto propio: no hereda precisión, redondeo ni traps del llamante.
    return Context(prec=200, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                   capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])


def validar_orden_market(orden):
    if not isinstance(orden, dict) or 'quoteOrderQty' in orden:
        raise FiltroInvalido('quoteOrderQty no verificado en esta versión; rechazado.')
    if set(orden) != CAMPOS_ORDEN:
        raise FiltroInvalido('Campos de orden incompletos o no soportados.')
    if orden['type'] != 'MARKET' or orden['side'] not in ('BUY', 'SELL'):
        raise FiltroInvalido('Solo contratos MARKET BUY o SELL.')
    if type(orden['symbol']) is not str or not orden['symbol']:
        raise FiltroInvalido('Símbolo requerido.')
    cantidad = decimal_texto(orden['quantity'])
    if cantidad <= 0:
        raise FiltroInvalido('Cantidad debe ser positiva.')
    return cantidad


def _filtros_del_simbolo(simbolo, nombre):
    if (not isinstance(simbolo, dict) or simbolo.get('symbol') != nombre
            or simbolo.get('status') != 'TRADING' or simbolo.get('isSpotTradingAllowed') is not True
            or not isinstance(simbolo.get('orderTypes'), list) or 'MARKET' not in simbolo['orderTypes']):
        raise FiltroInvalido('Símbolo, estado o permiso MARKET no verificable.')
    filtros = simbolo.get('filters')
    if not isinstance(filtros, list) or not filtros:
        raise FiltroInvalido('Faltan filtros.')
    return filtros


def _lote(cantidad, filtro):
    minimo, maximo, paso = (decimal_texto(filtro[k]) for k in ('minQty', 'maxQty', 'stepSize'))
    if (paso <= 0 or maximo <= 0 or minimo > maximo or not minimo <= cantidad <= maximo
            or cantidad % paso):
        raise FiltroInvalido(filtro['filterType'] + ' incumplido.')


def validar_market_offline(orden, simbolo):
    """Evalúa una orden MARKET por cantidad base. No usa precio ni redondea."""
    cantidad = validar_orden_market(orden)
    filtros = _filtros_del_simbolo(simbolo, orden['symbol'])
    vistos = set()
    with localcontext(_contexto()):
        for filtro in filtros:
            if not isinstance(filtro, dict) or not isinstance(filtro.get('filterType'), str):
                raise FiltroInvalido('Filtro mal formado.')
            tipo = filtro['filterType']
            if tipo in vistos:
                raise FiltroInvalido('Filtro duplicado.')
            if tipo not in FILTROS_PERMITIDOS:
                raise FiltroInvalido('Filtro no soportado para MARKET; falta contexto: ' + tipo)
            vistos.add(tipo)
            try:
                if tipo in FILTROS_REQUERIDOS:
                    _lote(cantidad, filtro)
                elif tipo == 'MIN_NOTIONAL':
                    # Aplicarlo a MARKET exige precio de referencia: no soportado aquí.
                    if filtro.get('applyToMarket') is not False:
                        raise FiltroInvalido('MIN_NOTIONAL aplicable a MARKET no soportado.')
                elif tipo == 'NOTIONAL':
                    if filtro.get('applyMinToMarket') is not False or filtro.get('applyMaxToMarket') is not False:
                        raise FiltroInvalido('NOTIONAL aplicable a MARKET no soportado.')
            except KeyError as error:
                raise FiltroInvalido('Campo de filtro ausente.') from error
    if not FILTROS_REQUERIDOS <= vistos:
        raise FiltroInvalido('Contrato MARKET requiere MARKET_LOT_SIZE y LOT_SIZE explícitos.')
    return {'version': VERSION, 'modo': 'OFFLINE', 'enviable': False,
            'cantidad': format(cantidad, 'f'), 'filtros_evaluados': sorted(vistos)}


def remanente_de_lote(cantidad_texto, paso_texto):
    """Informa el polvo al redondear hacia abajo al stepSize. NO altera ninguna orden."""
    cantidad, paso = decimal_texto(cantidad_texto), decimal_texto(paso_texto)
    if paso <= 0:
        raise FiltroInvalido('stepSize debe ser positivo.')
    with localcontext(_contexto()):
        alineada = (cantidad // paso) * paso
        return {'alineada_hacia_abajo': format(alineada, 'f'),
                'polvo': format(cantidad - alineada, 'f')}
