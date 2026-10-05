import ast
import copy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import inspect
import json
import unittest

import broker_adapters
from broker_adapters import (BinanceSpotPaperAdapter, ContratoMt5Paper,
    SnapshotInvalido, SpotPaper, XmMt5PaperAdapter, cargar_snapshot_json)


def snapshot_spot():
    return dict(schema='BROKER_PAPER_V1', modo='PAPER', broker='BINANCE', origen='SINTETICO',
        obtenido_ms=1000, cuenta='SIN_CUENTA', cotizacion=dict(bid='100', ask='101', tiempo_ms=990),
        instrumento=dict(symbol='FIXTUREUSDT', market='SPOT', base_asset='FIXTURE', quote_asset='USDT',
            tick_size='0.01', quantity_min='0.001', quantity_max='100', quantity_step='0.001'))


def snapshot_mt5():
    return dict(schema='BROKER_PAPER_V1', modo='PAPER', broker='XM_MT5', origen='SINTETICO',
        obtenido_ms=1000, cuenta=dict(alias='DEMO_FICTICIA', server='Servidor-Ficticio-Demo',
            account_type='Tipo-Ficticio', trade_mode='DEMO', currency='USD', margin_mode='RETAIL_HEDGING'),
        cotizacion=dict(bid='100', ask='101', tiempo_ms=990),
        instrumento=dict(symbol='CFD_FICTICIO', market='CONTRATO_MT5', contract_size='10', tick_size='0.01',
            tick_value_profit='0.1', tick_value_loss='0.1', tick_value_currency='USD',
            currency_profit='EUR', currency_margin='EUR', calc_mode='CFD',
            volume_min='0.01', volume_max='100', volume_step='0.01', swap_mode='POINTS',
            swap_long='-1.2', swap_short='0.1', swap_rollover3days=3))


class BrokerAdaptersTests(unittest.TestCase):
    def leer_spot(self, s=None, **kwargs):
        return BinanceSpotPaperAdapter.leer_snapshot(snapshot_spot() if s is None else s,
            **{'ahora_ms':1100, 'max_edad_ms':200, **kwargs})

    def leer_mt5(self, s=None, **kwargs):
        return XmMt5PaperAdapter.leer_snapshot(snapshot_mt5() if s is None else s,
            **{'ahora_ms':1100, 'max_edad_ms':200, **kwargs})

    def economia(self):
        snapshot = self.leer_mt5()
        escenario = dict(side='BUY', volume_lots='0.1', price_open='101', price_close='103', horizonte_horas='24')
        evidencia = dict(schema='ECONOMIA_MT5_PAPER_V1', snapshot_hash=snapshot.snapshot_hash,
            escenario=copy.deepcopy(escenario), obtenido_ms=1050, currency='USD', profit_method='SINTETICO',
            margin_method='SINTETICO', profit_gross='2.17', fees_debit='0.11', swap_signed='-0.03',
            margin_isolated='9.91', cost_source='Fixture sintético; no tarifa de XM')
        return snapshot, escenario, evidencia

    def leer_economia(self, snapshot, escenario, evidencia):
        return XmMt5PaperAdapter.leer_economia(snapshot, escenario, evidencia, ahora_ms=1100, max_edad_ms=200)

    def test_modelos_separados_y_capacidades_sin_transporte(self):
        spot, mt5 = self.leer_spot(), self.leer_mt5()
        self.assertIs(type(spot), SpotPaper)
        self.assertIs(type(mt5), ContratoMt5Paper)
        self.assertEqual(spot.capacidades.unidad_volumen, 'ACTIVO_BASE')
        self.assertEqual(mt5.capacidades.unidad_volumen, 'LOTES')
        for resultado in (spot, mt5):
            for campo in ('conecta_cuentas', 'envia_ordenes', 'calcula_pnl', 'calcula_margen'):
                self.assertFalse(getattr(resultado.capacidades, campo))
            with self.assertRaises(FrozenInstanceError):
                resultado.capacidades.envia_ordenes = True

    def test_rechaza_mezclar_instrumentos_brokers_o_modos(self):
        with self.assertRaises(SnapshotInvalido): self.leer_spot(snapshot_mt5())
        with self.assertRaises(SnapshotInvalido): self.leer_mt5(snapshot_spot())
        for lector, factory in ((self.leer_spot, snapshot_spot), (self.leer_mt5, snapshot_mt5)):
            for campo, valor in (('modo', 'REAL'), ('origen', 'LIVE'), ('schema', 'TESTNET_FIXTURE')):
                s = factory()
                s[campo] = valor
                with self.subTest(campo=campo), self.assertRaises(SnapshotInvalido): lector(s)

    def test_no_mutacion_y_serializacion_inmutable(self):
        s = snapshot_mt5()
        antes = copy.deepcopy(s)
        resultado = self.leer_mt5(s)
        self.assertEqual(s, antes)
        self.assertEqual(resultado, self.leer_mt5(s))
        s['instrumento']['contract_size'] = '500'
        self.assertEqual(resultado.contract_size, Decimal('10'))
        self.assertNotEqual(resultado.snapshot_hash, self.leer_mt5(s).snapshot_hash)

    def test_tiempos_incluyen_cotizacion_y_limites(self):
        for campo, valor in (('obtenido_ms', 1101), ('obtenido_ms', 899), ('obtenido_ms', True)):
            s = snapshot_mt5()
            s[campo] = valor
            with self.subTest(valor=valor), self.assertRaises(SnapshotInvalido): self.leer_mt5(s)
        for tiempo in (899, 1001, True, '1000'):
            s = snapshot_mt5()
            s['cotizacion']['tiempo_ms'] = tiempo
            with self.subTest(tiempo=tiempo), self.assertRaises(SnapshotInvalido): self.leer_mt5(s)
        s['cotizacion']['tiempo_ms'] = 900
        self.leer_mt5(s)

    def test_cotizacion_cruzada_numeros_no_finitos_y_floats(self):
        for valor in ('102', 'NaN', 'Infinity', '-1', '0', '1e2', 100.0, True, None):
            s = snapshot_mt5()
            s['cotizacion']['bid'] = valor
            with self.subTest(valor=valor), self.assertRaises(SnapshotInvalido): self.leer_mt5(s)

    def test_metadatos_mt5_obligatorios_y_desconocidos(self):
        for grupo in ('cuenta', 'instrumento'):
            for campo in snapshot_mt5()[grupo]:
                s = snapshot_mt5()
                del s[grupo][campo]
                with self.subTest(grupo=grupo, campo=campo), self.assertRaises(SnapshotInvalido): self.leer_mt5(s)
        for campo in ('calc_mode', 'swap_mode', 'currency_profit', 'currency_margin', 'tick_value_currency'):
            s = snapshot_mt5()
            s['instrumento'][campo] = 'DESCONOCIDO'
            with self.subTest(campo=campo), self.assertRaises(SnapshotInvalido): self.leer_mt5(s)

    def test_no_admite_cuenta_real_secretos_o_campos_nuevos(self):
        for campo, valor in (('trade_mode', 'REAL'), ('margin_mode', 'UNKNOWN'), ('password', 'NO_SECRET')):
            s = snapshot_mt5()
            s['cuenta'][campo] = valor
            with self.subTest(campo=campo), self.assertRaises(SnapshotInvalido): self.leer_mt5(s)
        s = snapshot_spot()
        s['cuenta'] = 'UNA_CUENTA'
        with self.assertRaises(SnapshotInvalido): self.leer_spot(s)

    def test_tick_size_tick_value_y_contract_size_no_tienen_defaults(self):
        for campo in ('contract_size', 'tick_size', 'tick_value_profit', 'tick_value_loss'):
            for valor in ('0', '-1', 1.0, 'UNKNOWN'):
                s = snapshot_mt5()
                s['instrumento'][campo] = valor
                with self.subTest(campo=campo, valor=valor), self.assertRaises(SnapshotInvalido): self.leer_mt5(s)
        s = snapshot_mt5()
        s['instrumento']['tick_value_currency'] = 'EUR'
        with self.assertRaises(SnapshotInvalido): self.leer_mt5(s)

    def test_swaps_y_lotes_inconsistentes_rechazados(self):
        for campo, valor in (('swap_mode', 'DISABLED'), ('swap_rollover3days', 7),
                             ('swap_rollover3days', True), ('volume_min', '101'), ('volume_step', '0')):
            s = snapshot_mt5()
            s['instrumento'][campo] = valor
            with self.subTest(campo=campo), self.assertRaises(SnapshotInvalido): self.leer_mt5(s)

    def test_economia_solo_lee_valores_aportados_sin_formula_cfd_spot(self):
        args = self.economia()
        resultado = self.leer_economia(*args)
        self.assertEqual(resultado.beneficio_bruto, Decimal('2.17'))
        self.assertEqual(resultado.comisiones_debito, Decimal('0.11'))
        self.assertEqual(resultado.swap_firmado, Decimal('-0.03'))
        self.assertEqual(resultado.margen_aislado, Decimal('9.91'))
        self.assertFalse(resultado.autorizacion)
        self.assertNotEqual(resultado.beneficio_bruto, Decimal('0.1') * (Decimal('103') - Decimal('101')))

    def test_costes_beneficio_y_margen_desconocidos_rechazados(self):
        for campo in self.economia()[2]:
            s, escenario, evidencia = self.economia()
            del evidencia[campo]
            with self.subTest(campo=campo), self.assertRaises(SnapshotInvalido): self.leer_economia(s, escenario, evidencia)
        for campo in ('profit_gross', 'fees_debit', 'swap_signed', 'margin_isolated', 'cost_source'):
            s, escenario, evidencia = self.economia()
            evidencia[campo] = 'UNKNOWN'
            with self.subTest(campo=campo), self.assertRaises(SnapshotInvalido): self.leer_economia(s, escenario, evidencia)

    def test_economia_ligada_a_snapshot_divisa_escenario_y_tiempo(self):
        for campo, valor in (('snapshot_hash', '0' * 64), ('currency', 'EUR'), ('obtenido_ms', 999),
                             ('obtenido_ms', 1101), ('profit_method', 'FORMULA_SPOT'), ('margin_isolated', '-1')):
            s, escenario, evidencia = self.economia()
            evidencia[campo] = valor
            with self.subTest(campo=campo), self.assertRaises(SnapshotInvalido): self.leer_economia(s, escenario, evidencia)
        s, escenario, evidencia = self.economia()
        escenario['price_close'] = '104'
        with self.assertRaises(SnapshotInvalido): self.leer_economia(s, escenario, evidencia)
        with self.assertRaises(SnapshotInvalido): self.leer_economia(self.leer_spot(), escenario, evidencia)
        with self.assertRaises(SnapshotInvalido): self.leer_economia(replace(s, contract_size=Decimal('5')), escenario, evidencia)

    def test_escenarios_rechazan_volumen_y_precio_fuera_incrementos(self):
        for campo, valor in (('volume_lots', '0.001'), ('volume_lots', '101'), ('price_open', '100.001'),
                             ('price_close', '100.001'), ('horizonte_horas', '0')):
            s, escenario, evidencia = self.economia()
            escenario[campo] = valor
            evidencia['escenario'] = copy.deepcopy(escenario)
            with self.subTest(campo=campo), self.assertRaises(SnapshotInvalido): self.leer_economia(s, escenario, evidencia)

    def test_exportacion_demo_exige_metodos_de_terminal_pero_no_los_invoca(self):
        s, escenario, evidencia = self.economia()
        bruto = snapshot_mt5()
        bruto['origen'] = 'EXPORTACION_DEMO_MT5'
        s = self.leer_mt5(bruto)
        evidencia['snapshot_hash'] = s.snapshot_hash
        with self.assertRaises(SnapshotInvalido): self.leer_economia(s, escenario, evidencia)
        evidencia.update(profit_method='ORDER_CALC_PROFIT', margin_method='ORDER_CALC_MARGIN')
        self.assertEqual(self.leer_economia(s, escenario, evidencia).beneficio_bruto, Decimal('2.17'))

    def test_json_rechaza_duplicados_float_y_exceso_de_profundidad(self):
        for contenido in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":1.1}', '[null]', '[' * 20 + '1' + ']' * 20):
            with self.subTest(contenido=contenido), self.assertRaises(SnapshotInvalido): cargar_snapshot_json(contenido)
        s = snapshot_mt5()
        self.assertEqual(cargar_snapshot_json(json.dumps(s)), s)

    def test_modulo_no_importa_transporte_terminal_config_ni_persistencia(self):
        arbol = ast.parse(inspect.getsource(broker_adapters))
        importados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import): importados.update(a.name for a in nodo.names)
            if isinstance(nodo, ast.ImportFrom): importados.add(nodo.module)
        self.assertEqual(importados, {'dataclasses', 'decimal', 'hashlib', 'json', 're'})


if __name__ == '__main__':
    unittest.main()
