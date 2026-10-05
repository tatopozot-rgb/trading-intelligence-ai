"""Fills PAPER por profundidad visible; no envía órdenes ni promete fills reales."""
import copy
from decimal import (Context, Decimal, DivisionByZero, InvalidOperation, Overflow,
                     ROUND_HALF_EVEN, localcontext)
import hashlib
import json
import re
import time

MODELO = 'PROFUNDIDAD_VISIBLE_FOK_PAPER_V1'
MAX_EDAD_MS = 5000


def decimal(valor, *, cero=False):
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float, Decimal)):
        raise ValueError('Número de fill inválido.')
    if len(str(valor)) > 100:
        raise ValueError('Número excesivo.')
    try:
        d = Decimal(str(valor))
    except InvalidOperation as exc:
        raise ValueError('Número de fill inválido.') from exc
    if not d.is_finite() or d < 0 or (not cero and d == 0) or (d and not -24 <= d.adjusted() <= 24):
        raise ValueError('Número de fill fuera de rango.')
    # Un cero con exponente enorme no debe expandirse al serializarlo.
    return Decimal(0) if d == 0 else d


def texto(valor):
    return format(valor, 'f')


def huella(valor):
    return hashlib.sha256(json.dumps(valor, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def entero(valor):
    if type(valor) is not int or valor < 0:
        raise ValueError('Tiempo/identificador de snapshot inválido.')
    return valor


def validar_snapshot(snapshot, *, ahora_ms, max_edad_ms):
    entero(ahora_ms); entero(max_edad_ms)
    if max_edad_ms <= 0 or max_edad_ms > MAX_EDAD_MS:
        raise ValueError('Edad técnica permitida: 1 a 5000 ms.')
    if not isinstance(snapshot, dict) or snapshot.get('fuente') not in ('BINANCE_PUBLIC_DEPTH', 'FIXTURE'):
        raise ValueError('Fuente de profundidad no admitida.')
    if not re.fullmatch('[A-Z0-9]{5,30}', snapshot.get('simbolo', '')):
        raise ValueError('Símbolo de profundidad inválido.')
    inicio, recibido = entero(snapshot.get('solicitado_ms')), entero(snapshot.get('recibido_ms'))
    if not inicio <= recibido <= ahora_ms or ahora_ms-inicio > max_edad_ms:
        raise ValueError('Snapshot futuro/antiguo o consulta demasiado lenta.')
    libro = snapshot.get('libro')
    if not isinstance(libro, dict):
        raise ValueError('Libro ausente.')
    entero(libro.get('lastUpdateId'))
    lados = {}
    for lado in ('bids', 'asks'):
        raw = libro.get(lado)
        if not isinstance(raw, list) or not 1 <= len(raw) <= 1000:
            raise ValueError('Libro vacío o demasiado grande.')
        filas = []
        for par in raw:
            if not isinstance(par, list) or len(par) != 2:
                raise ValueError('Nivel inválido.')
            filas.append((decimal(par[0]), decimal(par[1])))
        for anterior, actual in zip(filas, filas[1:]):
            if (lado == 'asks' and actual[0] <= anterior[0]) or (lado == 'bids' and actual[0] >= anterior[0]):
                raise ValueError('Libro desordenado o precios duplicados.')
        lados[lado] = filas
    if lados['bids'][0][0] >= lados['asks'][0][0]:
        raise ValueError('Libro cruzado/cerrado inválido.')
    return lados


def simular(snapshot, *, lado, monto, comision_pct, ahora_ms, max_edad_ms=MAX_EDAD_MS):
    """BUY: monto quote sin fee; SELL: cantidad base. Parcial NO autoriza ledger."""
    lados = validar_snapshot(snapshot, ahora_ms=ahora_ms, max_edad_ms=max_edad_ms)
    if lado not in ('BUY', 'SELL'):
        raise ValueError('Lado inválido.')
    solicitado, tarifa = decimal(monto), decimal(comision_pct, cero=True)
    if tarifa >= 100:
        raise ValueError('Comisión inválida.')
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999,
                              Emax=999999, capitals=1, clamp=0, flags=[],
                              traps=[InvalidOperation, DivisionByZero, Overflow])):
        restante, base, quote = solicitado, Decimal(0), Decimal(0)
        fills = []
        niveles = lados['asks' if lado == 'BUY' else 'bids']
        for precio, disponible in niveles:
            if restante == 0:
                break
            if lado == 'BUY':
                nominal = min(restante, precio*disponible)
                cantidad = nominal/precio
                restante -= nominal
            else:
                cantidad = min(restante, disponible)
                nominal = cantidad*precio
                restante -= cantidad
            base += cantidad; quote += nominal
            fills.append({'precio': texto(precio), 'cantidad': texto(cantidad), 'nominal': texto(nominal)})
        medio = quote/base
        referencia = niveles[0][0]
        impacto = ((medio/referencia-1) if lado == 'BUY' else (1-medio/referencia))*10000
        # Redondeo Decimal de cocientes puede producir -1e-45, no mejora real.
        if abs(impacto) < Decimal('1e-40'):
            impacto = Decimal(0)
        bid, ask = lados['bids'][0][0], lados['asks'][0][0]
        return dict(modo='PAPER_SIMULACION', enviable=False, modelo=MODELO,
                    simbolo=snapshot['simbolo'], lado=lado,
                    solicitado=texto(solicitado), unidad='QUOTE' if lado == 'BUY' else 'BASE',
                    estado='COMPLETO' if restante == 0 else 'PARCIAL', restante=texto(restante),
                    motivo=None if restante == 0 else 'PROFUNDIDAD_VISIBLE_INSUFICIENTE',
                    base_ejecutada=texto(base), quote_ejecutado=texto(quote), precio_medio=texto(medio),
                    precio_referencia=texto(referencia), impacto_bps=texto(impacto),
                    spread_bps=texto((ask-bid)/((ask+bid)/2)*10000),
                    comision_quote=texto(quote*tarifa/100), comision_pct=texto(tarifa),
                    fills=fills, snapshot_sha256=huella(snapshot))


def evidencia(snapshot, *, lado, monto, comision_pct, ahora_ms):
    parametros = dict(lado=lado, monto=texto(decimal(monto)),
                      comision_pct=texto(decimal(comision_pct, cero=True)), ahora_ms=entero(ahora_ms))
    return dict(snapshot=copy.deepcopy(snapshot), parametros=parametros,
                resultado=simular(snapshot, **parametros))


def validar_evidencia(dato, *, simbolo, lado, monto, comision_pct, precio, ahora_ms):
    """Recalcula antes del commit; el caller no puede inventar el fill guardado."""
    if not isinstance(dato, dict) or set(dato) != {'snapshot', 'parametros', 'resultado'}:
        raise ValueError('Evidencia de fill ausente/inválida.')
    p = dato['parametros']; r = dato['resultado']
    if not isinstance(p, dict) or set(p) != {'lado', 'monto', 'comision_pct', 'ahora_ms'}:
        raise ValueError('Parámetros de evidencia inválidos.')
    if (p['lado'] != lado or decimal(p['monto']) != decimal(monto)
            or decimal(p['comision_pct'], cero=True) != decimal(comision_pct, cero=True)):
        raise ValueError('Evidencia no corresponde a la operación.')
    if entero(p['ahora_ms']) > entero(ahora_ms):
        raise ValueError('Evidencia calculada en el futuro.')
    validar_snapshot(dato['snapshot'], ahora_ms=ahora_ms, max_edad_ms=MAX_EDAD_MS)
    esperado = simular(dato['snapshot'], **p)
    if r != esperado or r['simbolo'] != simbolo or r['estado'] != 'COMPLETO':
        raise ValueError('Fill alterado/incompleto o símbolo distinto.')
    # SQLite legado usa float; contrastar su representación, sin tolerancia libre.
    if float(r['precio_medio']) != precio:
        raise ValueError('Precio de ledger no coincide con fill.')
    return copy.deepcopy(dato)


def resultado_cierre(apertura, cierre):
    """Economía de dos evidencias ya verificadas; no reconstruye base desde VWAP."""
    compra, venta = apertura['resultado'], cierre['resultado']
    if (compra['lado'] != 'BUY' or venta['lado'] != 'SELL'
            or compra['estado'] != 'COMPLETO' or venta['estado'] != 'COMPLETO'
            or Decimal(compra['base_ejecutada']) != Decimal(venta['base_ejecutada'])):
        raise ValueError('Cantidades de apertura/cierre incompatibles.')
    with localcontext(Context(prec=100, rounding=ROUND_HALF_EVEN, Emin=-999999,
                              Emax=999999, capitals=1, clamp=0, flags=[],
                              traps=[InvalidOperation, DivisionByZero, Overflow])):
        entrada, salida = Decimal(compra['quote_ejecutado']), Decimal(venta['quote_ejecutado'])
        comisiones = Decimal(compra['comision_quote']) + Decimal(venta['comision_quote'])
        bruto = salida-entrada
        pnl = bruto-comisiones
        return dict(resultado_bruto_usd=texto(bruto), comisiones_estimadas=texto(comisiones),
                    resultado_usd=texto(pnl), resultado_pct=texto(pnl/entrada*100))


def cotizar(simbolo, *, cliente=None, reloj=None):
    """Sólo GET público, sin API key. Fecha de recepción NO es timestamp exchange."""
    from market_http import CLIENTE
    if not re.fullmatch('[A-Z0-9]{5,30}', simbolo):
        raise ValueError('Símbolo inválido.')
    reloj = reloj or (lambda: time.time_ns()//1_000_000)
    inicio = reloj()
    libro = (cliente or CLIENTE).get('/api/v3/depth', {'symbol': simbolo, 'limit': 100})
    recibido = reloj()
    snapshot = dict(fuente='BINANCE_PUBLIC_DEPTH', simbolo=simbolo,
                    solicitado_ms=inicio, recibido_ms=recibido, libro=libro)
    validar_snapshot(snapshot, ahora_ms=recibido, max_edad_ms=MAX_EDAD_MS)
    return snapshot
