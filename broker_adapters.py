"""Lectores PAPER de snapshots explícitos. Sin transporte, terminal ni órdenes.

Los hashes vinculan contenido; no autentican un broker ni sus cálculos. Nunca
importar MetaTrader5, conectar cuentas o traducir lotes MT5 a cantidad Spot aquí.
"""
from dataclasses import dataclass, field
from decimal import (Context, Decimal, DivisionByZero, InvalidOperation, Overflow,
                     ROUND_HALF_EVEN, localcontext)
import hashlib
import json
import re


class SnapshotInvalido(ValueError):
    pass


@dataclass(frozen=True)
class CapacidadesPaper:
    plataforma: str
    mercado: str
    unidad_volumen: str
    lee_snapshots: bool = field(default=True, init=False)
    conecta_cuentas: bool = field(default=False, init=False)
    envia_ordenes: bool = field(default=False, init=False)
    calcula_pnl: bool = field(default=False, init=False)
    calcula_margen: bool = field(default=False, init=False)


@dataclass(frozen=True)
class SpotPaper:
    simbolo: str
    activo_base: str
    activo_cotizacion: str
    snapshot_hash: str
    evidencia_json: str
    capacidades: CapacidadesPaper = field(default=CapacidadesPaper(
        'BINANCE', 'SPOT', 'ACTIVO_BASE'), init=False)


@dataclass(frozen=True)
class ContratoMt5Paper:
    simbolo: str
    divisa_cuenta: str
    contract_size: Decimal
    tick_size: Decimal
    tick_value_profit: Decimal
    tick_value_loss: Decimal
    calc_mode: str
    snapshot_hash: str
    evidencia_json: str
    capacidades: CapacidadesPaper = field(default=CapacidadesPaper(
        'XM_MT5', 'CONTRATO_MT5', 'LOTES'), init=False)


@dataclass(frozen=True)
class EconomiaMt5Paper:
    divisa: str
    beneficio_bruto: Decimal
    comisiones_debito: Decimal
    swap_firmado: Decimal
    margen_aislado: Decimal
    evidencia_hash: str
    evidencia_json: str
    autorizacion: bool = field(default=False, init=False)


def _campos(dato, campos):
    if type(dato) is not dict or set(dato) != set(campos.split()):
        raise SnapshotInvalido('Campos ausentes o no admitidos.')


def _texto(valor):
    if (type(valor) is not str or not 1 <= len(valor) <= 100 or
            valor.strip() != valor or any(ord(c) < 32 for c in valor) or
            valor.upper() in {'UNKNOWN', 'DESCONOCIDO', 'N/A', 'PENDIENTE'}):
        raise SnapshotInvalido('Dato textual explícito requerido.')
    return valor


def _decimal(valor, *, signo=False, positivo=False):
    patron = r'-?[0-9]+(?:\.[0-9]+)?' if signo else r'[0-9]+(?:\.[0-9]+)?'
    if type(valor) is not str or len(valor) > 50 or re.fullmatch(patron, valor) is None:
        raise SnapshotInvalido('Se requiere decimal textual, sin float/NaN/exponente.')
    numero = Decimal(valor)
    if positivo and numero <= 0:
        raise SnapshotInvalido('Valor positivo requerido.')
    return numero


def _ms(valor):
    if type(valor) is not int or not 0 <= valor < 2**63:
        raise SnapshotInvalido('Tiempo entero no negativo requerido.')
    return valor


def _serializar(dato):
    # Limita el árbol antes de serializar; excluye floats, None y objetos activos.
    nodos = 0

    def recorrer(v, profundidad=0):
        nonlocal nodos
        nodos += 1
        if nodos > 3000 or profundidad > 12:
            raise SnapshotInvalido('Snapshot demasiado complejo.')
        if type(v) is dict:
            for k, x in v.items():
                _texto(k)
                recorrer(x, profundidad + 1)
        elif type(v) is list:
            for x in v:
                recorrer(x, profundidad + 1)
        elif type(v) is str:
            if len(v) > 1000:
                raise SnapshotInvalido('Texto demasiado largo.')
        elif type(v) is int:
            _ms(v)
        elif type(v) is not bool:
            raise SnapshotInvalido('Tipo no admitido en snapshot.')

    recorrer(dato)
    contenido = json.dumps(dato, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    if len(contenido) > 100000:
        raise SnapshotInvalido('Snapshot demasiado grande.')
    return contenido


def _hash(contenido):
    return hashlib.sha256(contenido.encode('ascii')).hexdigest()


def cargar_snapshot_json(contenido):
    """Decodificación estricta disponible para un futuro importador local."""
    if type(contenido) is not str or len(contenido) > 100000:
        raise SnapshotInvalido('JSON textual acotado requerido.')

    def pares(items):
        dato = {}
        for clave, valor in items:
            if clave in dato:
                raise SnapshotInvalido('Clave JSON repetida.')
            dato[clave] = valor
        return dato

    def rechazar(_):
        raise SnapshotInvalido('Los decimales deben ser texto.')

    try:
        dato = json.loads(contenido, object_pairs_hook=pares,
                          parse_float=rechazar, parse_constant=rechazar)
        _serializar(dato)
        return dato
    except (ValueError, RecursionError) as error:
        raise SnapshotInvalido('JSON de snapshot inválido.') from error


def _cabecera(s, *, broker, origenes, ahora_ms, max_edad_ms):
    _campos(s, 'schema modo broker origen obtenido_ms cuenta instrumento cotizacion')
    for k in ('schema', 'modo', 'broker', 'origen'):
        _texto(s[k])
    if (s['schema'] != 'BROKER_PAPER_V1' or s['modo'] != 'PAPER' or
            s['broker'] != broker or s['origen'] not in origenes):
        raise SnapshotInvalido('Modo/origen/broker no admitido.')
    obtenido, ahora, edad = map(_ms, (s['obtenido_ms'], ahora_ms, max_edad_ms))
    if not obtenido <= ahora or ahora - obtenido > edad:
        raise SnapshotInvalido('Snapshot futuro o caducado.')
    q = s['cotizacion']
    _campos(q, 'bid ask tiempo_ms')
    bid, ask = (_decimal(q[k], positivo=True) for k in ('bid', 'ask'))
    if bid > ask or not _ms(q['tiempo_ms']) <= obtenido or ahora - q['tiempo_ms'] > edad:
        raise SnapshotInvalido('Cotización cruzada, futura o caducada.')


class BinanceSpotPaperAdapter:
    """Metadatos normalizados para lectura; no valida todos los filtros del exchange."""

    @staticmethod
    def leer_snapshot(s, *, ahora_ms, max_edad_ms):
        contenido = _serializar(s)
        _cabecera(s, broker='BINANCE', origenes={'SINTETICO', 'EXPORTACION_PUBLICA_BINANCE'},
                  ahora_ms=ahora_ms, max_edad_ms=max_edad_ms)
        if s['cuenta'] != 'SIN_CUENTA':
            raise SnapshotInvalido('Solo datos Spot públicos sin cuenta.')
        i = s['instrumento']
        _campos(i, 'symbol market base_asset quote_asset tick_size quantity_min quantity_max quantity_step')
        if i['market'] != 'SPOT':
            raise SnapshotInvalido('Este lector solo reconoce activos Spot.')
        for k in ('symbol', 'base_asset', 'quote_asset'):
            _texto(i[k])
        if i['base_asset'] == i['quote_asset']:
            raise SnapshotInvalido('Los activos base y cotizado deben diferir.')
        for k in ('tick_size', 'quantity_min', 'quantity_max', 'quantity_step'):
            _decimal(i[k], positivo=True)
        if Decimal(i['quantity_min']) > Decimal(i['quantity_max']):
            raise SnapshotInvalido('Rango de cantidades inválido.')
        return SpotPaper(i['symbol'], i['base_asset'], i['quote_asset'], _hash(contenido), contenido)


class XmMt5PaperAdapter:
    """Lee contratos demo exportados o sintéticos; nunca inicializa MT5."""
    CALC_MODES = frozenset({'FOREX', 'FOREX_NO_LEVERAGE', 'CFD', 'CFDINDEX', 'CFDLEVERAGE'})
    SWAP_MODES = frozenset({'DISABLED', 'POINTS', 'CURRENCY_SYMBOL', 'CURRENCY_MARGIN',
        'CURRENCY_DEPOSIT', 'CURRENCY_PROFIT', 'INTEREST_CURRENT', 'INTEREST_OPEN',
        'REOPEN_CURRENT', 'REOPEN_BID'})

    @staticmethod
    def leer_snapshot(s, *, ahora_ms, max_edad_ms):
        contenido = _serializar(s)
        _cabecera(s, broker='XM_MT5', origenes={'SINTETICO', 'EXPORTACION_DEMO_MT5'},
                  ahora_ms=ahora_ms, max_edad_ms=max_edad_ms)
        c, i = s['cuenta'], s['instrumento']
        _campos(c, 'alias server account_type trade_mode currency margin_mode')
        for k in ('alias', 'server', 'account_type', 'currency', 'trade_mode', 'margin_mode'):
            _texto(c[k])
        if c['trade_mode'] != 'DEMO' or c['margin_mode'] not in {'RETAIL_NETTING', 'RETAIL_HEDGING', 'EXCHANGE'}:
            raise SnapshotInvalido('Cuenta demo y modo de margen explícitos requeridos.')
        _campos(i, 'symbol market contract_size tick_size tick_value_profit tick_value_loss tick_value_currency currency_profit currency_margin calc_mode volume_min volume_max volume_step swap_mode swap_long swap_short swap_rollover3days')
        for k in ('symbol', 'tick_value_currency', 'currency_profit', 'currency_margin', 'calc_mode', 'swap_mode'):
            _texto(i[k])
        if (i['market'] != 'CONTRATO_MT5' or i['calc_mode'] not in XmMt5PaperAdapter.CALC_MODES or
                i['swap_mode'] not in XmMt5PaperAdapter.SWAP_MODES or i['tick_value_currency'] != c['currency']):
            raise SnapshotInvalido('Contrato, cálculo, swaps o divisa de tick desconocidos.')
        for k in ('contract_size', 'tick_size', 'tick_value_profit', 'tick_value_loss',
                  'volume_min', 'volume_max', 'volume_step'):
            _decimal(i[k], positivo=True)
        if Decimal(i['volume_min']) > Decimal(i['volume_max']):
            raise SnapshotInvalido('Rango de lotes inválido.')
        largo, corto = (_decimal(i[k], signo=True) for k in ('swap_long', 'swap_short'))
        if i['swap_mode'] == 'DISABLED' and (largo or corto):
            raise SnapshotInvalido('Swaps desactivados incompatibles con valores no cero.')
        if not 0 <= _ms(i['swap_rollover3days']) <= 6:
            raise SnapshotInvalido('Día de triple swap fuera de 0..6.')
        return ContratoMt5Paper(i['symbol'], c['currency'], Decimal(i['contract_size']),
            Decimal(i['tick_size']), Decimal(i['tick_value_profit']), Decimal(i['tick_value_loss']),
            i['calc_mode'], _hash(contenido), contenido)

    @staticmethod
    def leer_economia(snapshot, escenario, evidencia, *, ahora_ms, max_edad_ms):
        """Lee resultados aportados para UN escenario; no los calcula ni autentica.

        Margen aislado no equivale a margen disponible o de cartera. Las tarifas,
        conversión y swaps deben venir respaldados por el exportador futuro.
        """
        if type(snapshot) is not ContratoMt5Paper:
            raise SnapshotInvalido('Se requiere contrato MT5, nunca Spot.')
        s = cargar_snapshot_json(snapshot.evidencia_json)
        verificado = XmMt5PaperAdapter.leer_snapshot(s, ahora_ms=ahora_ms, max_edad_ms=max_edad_ms)
        if snapshot != verificado:
            raise SnapshotInvalido('Objeto de snapshot alterado.')
        _campos(escenario, 'side volume_lots price_open price_close horizonte_horas')
        if escenario['side'] not in ('BUY', 'SELL'):
            raise SnapshotInvalido('Lado desconocido.')
        for k in ('volume_lots', 'price_open', 'price_close', 'horizonte_horas'):
            _decimal(escenario[k], positivo=True)
        i = s['instrumento']
        with localcontext(Context(prec=120, rounding=ROUND_HALF_EVEN, Emin=-999999,
                                  Emax=999999, capitals=1, clamp=0, flags=[],
                                  traps=[InvalidOperation, DivisionByZero, Overflow])):
            volumen = Decimal(escenario['volume_lots'])
            if (not Decimal(i['volume_min']) <= volumen <= Decimal(i['volume_max']) or
                    volumen % Decimal(i['volume_step']) or any(
                        Decimal(escenario[k]) % snapshot.tick_size for k in ('price_open', 'price_close'))):
                raise SnapshotInvalido('Escenario fuera de lote o incremento de precio.')
        # No cuantifica P&L, costes ni margen mediante fórmulas del mercado Spot.
        _campos(evidencia, 'schema snapshot_hash escenario obtenido_ms currency profit_method margin_method profit_gross fees_debit swap_signed margin_isolated cost_source')
        _serializar(escenario)
        contenido = _serializar(evidencia)
        if (evidencia['schema'] != 'ECONOMIA_MT5_PAPER_V1' or
                evidencia['snapshot_hash'] != snapshot.snapshot_hash or
                evidencia['escenario'] != escenario or evidencia['currency'] != snapshot.divisa_cuenta):
            raise SnapshotInvalido('Economía no vinculada al snapshot, escenario o divisa.')
        metodos = ('SINTETICO', 'SINTETICO') if s['origen'] == 'SINTETICO' else ('ORDER_CALC_PROFIT', 'ORDER_CALC_MARGIN')
        if (evidencia['profit_method'], evidencia['margin_method']) != metodos:
            raise SnapshotInvalido('Método de beneficio/margen desconocido o incompatible.')
        obtenido = _ms(evidencia['obtenido_ms'])
        if not s['obtenido_ms'] <= obtenido <= ahora_ms or ahora_ms - obtenido > max_edad_ms:
            raise SnapshotInvalido('Economía futura, antigua o anterior al snapshot.')
        _texto(evidencia['cost_source'])
        return EconomiaMt5Paper(snapshot.divisa_cuenta,
            _decimal(evidencia['profit_gross'], signo=True), _decimal(evidencia['fees_debit']),
            _decimal(evidencia['swap_signed'], signo=True), _decimal(evidencia['margin_isolated']),
            _hash(contenido), contenido)
