"""Contrato OFFLINE de filtros estáticos. No autoriza, firma ni envía órdenes."""
from decimal import (Context, Decimal, DivisionByZero, InvalidOperation, Overflow,
                     ROUND_HALF_EVEN, localcontext)
import re


class FiltroInvalido(ValueError):
    pass


def decimal_texto(valor):
    # Cota de representación del contrato local, no límite financiero de Binance.
    if type(valor) is not str or len(valor)>80 or re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',valor) is None:
        raise FiltroInvalido('Se exige decimal textual acotado, sin signo ni exponente.')
    return Decimal(valor)


def validar_parametros_limite(orden):
    """Forma cerrada compartida; no evalúa reglas del símbolo."""
    campos = {'symbol','side','type','timeInForce','price','quantity'}
    if not isinstance(orden,dict) or set(orden)!=campos:
        raise FiltroInvalido('Campos de orden incompletos o no soportados.')
    if orden['type']!='LIMIT' or orden['side'] not in ('BUY','SELL') or orden['timeInForce'] not in ('GTC','IOC','FOK'):
        raise FiltroInvalido('Solo contratos LIMIT explícitos en esta prueba offline.')
    if type(orden['symbol']) is not str or not orden['symbol']:
        raise FiltroInvalido('Símbolo requerido.')
    precio,cantidad = (decimal_texto(orden[k]) for k in ('price','quantity'))
    if precio<=0 or cantidad<=0:
        raise FiltroInvalido('Precio y cantidad deben ser positivos.')
    return precio,cantidad


def validar_limite_offline(orden, simbolo):
    """Solo fixture LIMIT: si falta contexto/filtro soportado, falla cerrado."""
    precio,cantidad = validar_parametros_limite(orden)
    if (not isinstance(simbolo,dict) or not isinstance(orden['symbol'],str) or not orden['symbol']
            or simbolo.get('symbol')!=orden['symbol'] or simbolo.get('status')!='TRADING'
            or simbolo.get('isSpotTradingAllowed') is not True
            or not isinstance(simbolo.get('orderTypes'),list) or 'LIMIT' not in simbolo['orderTypes']):
        raise FiltroInvalido('Símbolo o permiso Spot/LIMIT no verificable.')
    filtros = simbolo.get('filters')
    if not isinstance(filtros,list) or not filtros:
        raise FiltroInvalido('Faltan filtros.')
    vistos = set()
    # Producto/resto exactos; no heredar exponentes/traps del llamante.
    with localcontext(Context(prec=200, rounding=ROUND_HALF_EVEN, Emin=-999999,
                              Emax=999999, capitals=1, clamp=0, flags=[],
                              traps=[InvalidOperation, DivisionByZero, Overflow])):
        notional = precio*cantidad
        for filtro in filtros:
            if not isinstance(filtro,dict) or not isinstance(filtro.get('filterType'),str):
                raise FiltroInvalido('Filtro mal formado.')
            tipo = filtro['filterType']
            if tipo in vistos:
                raise FiltroInvalido('Filtro duplicado.')
            vistos.add(tipo)
            try:
                if tipo=='PRICE_FILTER':
                    minimo,maximo,paso = (decimal_texto(filtro[k]) for k in ('minPrice','maxPrice','tickSize'))
                    if (minimo and maximo and minimo>maximo) or (minimo and precio<minimo) or (maximo and precio>maximo) or (paso and precio%paso):
                        raise FiltroInvalido('PRICE_FILTER incumplido.')
                elif tipo=='LOT_SIZE':
                    minimo,maximo,paso = (decimal_texto(filtro[k]) for k in ('minQty','maxQty','stepSize'))
                    if paso<=0 or maximo<=0 or minimo>maximo or cantidad<minimo or cantidad>maximo or cantidad%paso:
                        raise FiltroInvalido('LOT_SIZE incumplido/no soportado.')
                elif tipo=='MIN_NOTIONAL':
                    if notional<decimal_texto(filtro['minNotional']):
                        raise FiltroInvalido('MIN_NOTIONAL incumplido.')
                elif tipo=='NOTIONAL':
                    minimo,maximo = (decimal_texto(filtro[k]) for k in ('minNotional','maxNotional'))
                    if minimo>maximo or not minimo<=notional<=maximo:
                        raise FiltroInvalido('NOTIONAL incumplido.')
                else:
                    raise FiltroInvalido('Filtro no soportado; falta contexto: '+tipo)
            except KeyError as error:
                raise FiltroInvalido('Campo de filtro ausente.') from error
        if not {'PRICE_FILTER','LOT_SIZE'}<=vistos or not vistos.intersection({'MIN_NOTIONAL','NOTIONAL'}):
            raise FiltroInvalido('Contrato local requiere precio, lote y notional explícitos.')
        return {'modo':'OFFLINE','enviable':False,'notional':format(notional,'f'),
                'filtros_evaluados':sorted(vistos)}
