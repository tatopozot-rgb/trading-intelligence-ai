"""Cartera de escenarios exactos PAPER; pura, sin datos/red/órdenes ni config.

No admite intervalos de incertidumbre como horas de ejecución. El adaptador
histórico futuro deberá declarar escenarios, nunca inventar orden intravela.
"""
from decimal import (Context, Decimal, DivisionByZero, InvalidOperation, Overflow,
                     ROUND_HALF_EVEN, localcontext)
import hashlib
import json
import re

POLITICA = 'SALIDAS_ANTES_ENTRADAS_ID_LEXICO_V1'
CAMPOS = {'id', 'simbolo', 'entrada_ms', 'entrada', 'stop', 'objetivo',
          'salida_ms', 'salida', 'comision_pct'}


def _numero(v, *, cero=False):
    if type(v) not in (str, int, float, Decimal) or len(str(v)) > 80:
        raise ValueError('Número de escenario inválido.')
    try:
        n = Decimal(str(v))
    except InvalidOperation as exc:
        raise ValueError('Número de escenario inválido.') from exc
    if not n.is_finite() or n < 0 or (not cero and n == 0) or (n and not -18 <= n.adjusted() <= 18):
        raise ValueError('Número de escenario fuera de rango.')
    return Decimal(0) if n == 0 else n


def _ms(v):
    if type(v) is not int or not 0 <= v < 2**53:
        raise ValueError('Instante entero no negativo requerido.')
    return v


def _texto(v):
    return format(v, 'f')


def simular(candidatos, *, capital_inicial, riesgo_operacion_pct, perdida_diaria_pct,
            max_posiciones, inicio_ms, fin_ms, politica_empates):
    """Saldo realizado reconoce fee de entrada al abrir; NO es equity MTM.

    Reconocimiento distinto del ledger operativo, que difiere ambas fees al
    cierre. No modifica el runner ni replica su estrategia o redondeo a lotes.
    """
    capital, riesgo_pct, diario_pct = map(_numero,
        (capital_inicial, riesgo_operacion_pct, perdida_diaria_pct))
    if riesgo_pct > 100 or diario_pct > 100 or type(max_posiciones) is not int or not 1 <= max_posiciones <= 1000:
        raise ValueError('Límites explícitos fuera de rango.')
    inicio, fin = _ms(inicio_ms), _ms(fin_ms)
    if inicio >= fin or politica_empates != POLITICA:
        raise ValueError('Cobertura o política de empates no admitida.')
    if type(candidatos) is not list or len(candidatos) > 10000:
        raise ValueError('Lista acotada de candidatos requerida.')
    vistos, preparados = set(), []
    for c in candidatos:
        if type(c) is not dict or set(c) != CAMPOS:
            raise ValueError('Campos de candidato inválidos.')
        identidad, simbolo = c['id'], c['simbolo']
        if (type(identidad) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', identidad)
                or identidad in vistos or type(simbolo) is not str or not re.fullmatch(r'[A-Z0-9]{5,30}', simbolo)):
            raise ValueError('Identidad duplicada o símbolo inválido.')
        vistos.add(identidad)
        entrada, stop, objetivo = map(_numero, (c['entrada'], c['stop'], c['objetivo']))
        comision = _numero(c['comision_pct'], cero=True)
        if not stop < entrada < objetivo or comision >= 100:
            raise ValueError('Niveles o comisión fuera de rango.')
        t = _ms(c['entrada_ms'])
        if not inicio <= t < fin:
            raise ValueError('Entrada fuera de cobertura.')
        salida_t, salida = c['salida_ms'], c['salida']
        if (salida_t is None) != (salida is None):
            raise ValueError('Censura requiere fecha y precio de salida ambos nulos.')
        if salida_t is not None:
            salida_t, salida = _ms(salida_t), _numero(salida)
            if not t <= salida_t <= fin:
                raise ValueError('Salida fuera de cobertura o anterior a entrada.')
        preparados.append(dict(id=identidad, simbolo=simbolo, entrada_ms=t, entrada=entrada,
            stop=stop, objetivo=objetivo, comision_pct=comision, salida_ms=salida_t, salida=salida))
    # Todo se valida ANTES de calcular. Orden de entrada del JSON no concede prioridad.
    # Never inherit rounding, traps or exponent bounds from an embedding caller.
    with localcontext(Context(prec=100, rounding=ROUND_HALF_EVEN, Emin=-999999,
                              Emax=999999, capitals=1, clamp=0, flags=[],
                              traps=[InvalidOperation, DivisionByZero, Overflow])):
        return _calcular(preparados, capital, riesgo_pct, diario_pct, max_posiciones, inicio, fin)


def _calcular(casos, capital, riesgo_pct, diario_pct, max_posiciones, inicio, fin):
    cash, realizado, fees, max_saldo, drawdown = capital, Decimal(0), Decimal(0), capital, Decimal(0)
    abiertas, decisiones, eventos, dias = {}, [], [], {}
    agenda, por_id = [], {c['id']:c for c in casos}
    for c in casos:
        agenda.append((c['entrada_ms'], 1, c['id']))
        if c['salida_ms'] is not None:
            # Una posición recién abierta a esa hora sólo puede cerrar después.
            agenda.append((c['salida_ms'], 2 if c['salida_ms'] == c['entrada_ms'] else 0, c['id']))
    max_abiertas = 0

    def nominal_abierto():
        return sum((p['nominal'] for p in abiertas.values()), Decimal(0))

    def verificar():
        saldo = cash + nominal_abierto()
        # División periódica puede dejar residuo en el último decimal de contexto.
        if cash < 0 or abs(saldo - (capital + realizado)) > Decimal('1e-70'):
            raise ArithmeticError('Conservación de capital violada.')
        return saldo

    for instante, fase, identidad in sorted(agenda):
        c = por_id[identidad]
        dia = instante // 86400000  # UTC, no zona local ni reloj del equipo.
        if dia not in dias:
            dias[dia] = {'saldo_base': verificar(), 'perdidas': Decimal(0)}
        datos_dia = dias[dia]
        limite_dia = datos_dia['saldo_base'] * diario_pct / 100
        if fase != 1:
            p = abiertas.pop(identidad, None)
            if p is None:  # salida de un candidato rechazado no genera dinero/evento.
                continue
            ingreso = p['cantidad'] * c['salida']
            fee = ingreso * c['comision_pct'] / 100
            pnl_cierre = ingreso - fee - p['nominal']
            cash += ingreso - fee
            realizado += pnl_cierre
            fees += fee
            datos_dia['perdidas'] += max(Decimal(0), -pnl_cierre)
            eventos.append(dict(tipo='CIERRE', id=identidad, instante_ms=instante,
                cantidad=_texto(p['cantidad']), ingreso=_texto(ingreso), comision=_texto(fee),
                pnl_neto_operacion=_texto(pnl_cierre-p['fee_entrada'])))
        else:
            saldo = verificar()
            riesgo_abierto = sum((p['riesgo_restante'] for p in abiertas.values()), Decimal(0))
            motivo = None
            if any(p['simbolo'] == c['simbolo'] for p in abiertas.values()):
                motivo = 'SIMBOLO_YA_ABIERTO'
            elif len(abiertas) >= max_posiciones:
                motivo = 'MAX_POSICIONES'
            elif cash <= 0 or saldo <= 0:
                motivo = 'SIN_CAPITAL_LIBRE'
            tarifa = c['comision_pct']/100
            perdida_precio = (c['entrada']-c['stop'])/c['entrada']
            coste_riesgo = perdida_precio + tarifa*(1+c['stop']/c['entrada'])
            nominal = min(max(Decimal(0), cash)/(1+tarifa), max(Decimal(0), saldo)*riesgo_pct/100/coste_riesgo)
            fee = nominal*tarifa
            riesgo_nuevo = nominal*coste_riesgo
            if motivo is None and datos_dia['perdidas']+riesgo_abierto+riesgo_nuevo > limite_dia:
                motivo = 'LIMITE_PERDIDA_DIARIA'
            if motivo is None and nominal <= 0:
                motivo = 'TAMANO_NULO'
            d = dict(id=identidad, simbolo=c['simbolo'], instante_ms=instante,
                estado='RECHAZADO' if motivo else 'ACEPTADO', motivo=motivo,
                saldo_base_dia=_texto(datos_dia['saldo_base']))
            decisiones.append(d)
            if motivo:
                continue
            cantidad = nominal/c['entrada']
            cash -= nominal+fee
            # El cociente cash/(1+fee) puede exceder cash en el último ulp decimal.
            if -Decimal('1e-70') < cash < 0:
                cash = Decimal(0)
            realizado -= fee
            fees += fee
            datos_dia['perdidas'] += fee
            abiertas[identidad] = dict(simbolo=c['simbolo'], nominal=nominal, cantidad=cantidad,
                fee_entrada=fee, riesgo_restante=nominal*perdida_precio + nominal*c['stop']/c['entrada']*tarifa)
            d.update(nominal=_texto(nominal), cantidad=_texto(cantidad), riesgo_presupuestado=_texto(riesgo_nuevo))
            eventos.append(dict(tipo='APERTURA', id=identidad, instante_ms=instante,
                nominal=_texto(nominal), cantidad=_texto(cantidad), comision=_texto(fee)))
            max_abiertas = max(max_abiertas, len(abiertas))
        saldo = verificar()
        max_saldo = max(max_saldo, saldo)
        drawdown = max(drawdown, max_saldo-saldo)
    canon = [{k:_texto(v) if isinstance(v,Decimal) else v for k,v in c.items()}
             for c in sorted(casos, key=lambda c:c['id'])]
    entradas = dict(candidatos=canon, capital_inicial=_texto(capital), riesgo_operacion_pct=_texto(riesgo_pct),
        perdida_diaria_pct=_texto(diario_pct), max_posiciones=max_posiciones, inicio_ms=inicio, fin_ms=fin,
        politica_empates=POLITICA)
    digest = hashlib.sha256(json.dumps(entradas,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(schema='CARTERA_ESCENARIOS_PAPER_V1', modo='PAPER', enviable=False,
        politica_empates=POLITICA, entradas_sha256=digest, decisiones=decisiones, eventos=eventos,
        dias={str(d):{k:_texto(v) for k,v in valor.items()} for d,valor in sorted(dias.items())},
        metricas=dict(capital_inicial=_texto(capital), cash_libre=_texto(cash),
            capital_comprometido=_texto(nominal_abierto()), saldo_realizado_no_mtm=_texto(verificar()),
            pnl_realizado_incluye_fees_entrada=_texto(realizado), comisiones=_texto(fees),
            drawdown_realizado_usd_no_mtm=_texto(drawdown), max_posiciones_observadas=max_abiertas,
            aceptados=sum(d['estado']=='ACEPTADO' for d in decisiones),
            rechazados=sum(d['estado']=='RECHAZADO' for d in decisiones)),
        abiertas=[dict(id=i,**{k:_texto(v) if isinstance(v,Decimal) else v for k,v in p.items()})
                  for i,p in sorted(abiertas.items())],
        limites=['Instantes/precios de escenario aportados; no fills confirmados.',
                 'No MTM, lote/tick, margen, cortos ni broker; no replica el scanner.',
                 'Empates lexicográficos son hipótesis técnica explícita, no orden del mercado.',
                 'Censura conserva posiciones abiertas; no liquida al fin.'])
