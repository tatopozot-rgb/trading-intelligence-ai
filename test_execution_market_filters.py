import copy
from decimal import Inexact, localcontext
import unittest

from execution_filters import FiltroInvalido
from execution_market_filters import remanente_de_lote, validar_market_offline


class MarketFilterTests(unittest.TestCase):
    def setUp(self):
        self.orden = dict(symbol='FIXTUREUSDT', side='BUY', type='MARKET', quantity='1.000')
        self.simbolo = dict(symbol='FIXTUREUSDT', status='TRADING', isSpotTradingAllowed=True,
                            orderTypes=['LIMIT', 'MARKET'], filters=[
                                dict(filterType='LOT_SIZE', minQty='0.001', maxQty='10', stepSize='0.001'),
                                dict(filterType='MARKET_LOT_SIZE', minQty='0.001', maxQty='5', stepSize='0.001'),
                                dict(filterType='MIN_NOTIONAL', applyToMarket=False, minNotional='10'),
                                dict(filterType='NOTIONAL', applyMinToMarket=False, applyMaxToMarket=False,
                                     minNotional='10', maxNotional='100')])

    def validar(self):
        return validar_market_offline(self.orden, self.simbolo)

    def cambiar_filtro(self, tipo, **cambios):
        for filtro in self.simbolo['filters']:
            if filtro['filterType'] == tipo:
                filtro.update(cambios)

    def test_valida_exacta_sin_mutar_ni_habilitar(self):
        antes = copy.deepcopy((self.orden, self.simbolo))
        resultado = self.validar()
        self.assertFalse(resultado['enviable'])
        self.assertEqual(resultado['cantidad'], '1.000')
        self.assertEqual(resultado['version'], 'MARKET_FILTERS_OFFLINE_V1')
        self.assertEqual((self.orden, self.simbolo), antes)

    def test_limites_inclusivos_de_market_lot_size(self):
        for cantidad in ('0.001', '5'):
            with self.subTest(cantidad=cantidad):
                self.orden['quantity'] = cantidad
                self.validar()

    def test_lote_fuera_de_rango_rechaza(self):
        for cantidad in ('0.0005', '5.001', '5.0005'):
            with self.subTest(cantidad=cantidad):
                self.orden['quantity'] = cantidad
                with self.assertRaisesRegex(FiltroInvalido, 'incumplido'):
                    self.validar()
        self.orden['quantity'] = '0.000'
        with self.assertRaisesRegex(FiltroInvalido, 'positiva'):
            self.validar()

    def test_desalineacion_no_se_redondea(self):
        self.orden['quantity'] = '1.0005'
        with self.assertRaises(FiltroInvalido):
            self.validar()

    def test_lot_size_tambien_se_exige(self):
        self.cambiar_filtro('LOT_SIZE', maxQty='0.5')
        with self.assertRaisesRegex(FiltroInvalido, 'LOT_SIZE'):
            self.validar()

    def test_falta_cualquiera_de_los_dos_lotes_rechaza(self):
        for tipo in ('LOT_SIZE', 'MARKET_LOT_SIZE'):
            with self.subTest(falta=tipo):
                info = copy.deepcopy(self.simbolo)
                info['filters'] = [f for f in info['filters'] if f['filterType'] != tipo]
                with self.assertRaises(FiltroInvalido):
                    validar_market_offline(self.orden, info)

    def test_quote_order_qty_rechazado(self):
        for orden in (dict(self.orden, quoteOrderQty='10'),
                      {k: v for k, v in self.orden.items() if k != 'quantity'} | {'quoteOrderQty': '10'}):
            with self.subTest(orden=orden), self.assertRaisesRegex(FiltroInvalido, 'quoteOrderQty'):
                validar_market_offline(orden, self.simbolo)

    def test_tipo_lado_y_campos_no_soportados(self):
        for cambio in ({'type': 'LIMIT'}, {'side': 'otro'}, {'price': '10'}):
            with self.subTest(cambio=cambio), self.assertRaises(FiltroInvalido):
                validar_market_offline({**self.orden, **cambio}, self.simbolo)
        orden = dict(self.orden)
        del orden['quantity']
        with self.assertRaises(FiltroInvalido):
            validar_market_offline(orden, self.simbolo)

    def test_cantidad_representacion_invalida(self):
        for valor in (1.0, 1, True, '0', '-1', '1e1', 'NaN', ' 1', '1'*81):
            with self.subTest(valor=valor), self.assertRaises(FiltroInvalido):
                validar_market_offline({**self.orden, 'quantity': valor}, self.simbolo)

    def test_permiso_y_orderTypes_sin_market_rechaza(self):
        for cambio in ({'status': 'BREAK'}, {'isSpotTradingAllowed': 'true'}, {'orderTypes': ['LIMIT']},
                       {'symbol': 'OTRO'}):
            with self.subTest(cambio=cambio), self.assertRaises(FiltroInvalido):
                validar_market_offline(self.orden, {**self.simbolo, **cambio})

    def test_filtro_que_requiere_precio_no_se_ignora(self):
        self.cambiar_filtro('MIN_NOTIONAL', applyToMarket=True)
        with self.assertRaisesRegex(FiltroInvalido, 'MIN_NOTIONAL'):
            self.validar()
        self.cambiar_filtro('MIN_NOTIONAL', applyToMarket=False)
        self.cambiar_filtro('NOTIONAL', applyMinToMarket=True)
        with self.assertRaisesRegex(FiltroInvalido, 'NOTIONAL'):
            self.validar()
        self.cambiar_filtro('NOTIONAL', applyMinToMarket=False, applyMaxToMarket=True)
        with self.assertRaisesRegex(FiltroInvalido, 'NOTIONAL'):
            self.validar()

    def test_flags_de_aplicacion_ausentes_rechazan(self):
        self.cambiar_filtro('MIN_NOTIONAL')
        del next(f for f in self.simbolo['filters'] if f['filterType'] == 'MIN_NOTIONAL')['applyToMarket']
        with self.assertRaises(FiltroInvalido):
            self.validar()

    def test_filtro_no_soportado_o_duplicado(self):
        for tipo in ('PERCENT_PRICE', 'PERCENT_PRICE_BY_SIDE', 'PRICE_FILTER', 'MAX_NUM_ORDERS'):
            info = copy.deepcopy(self.simbolo)
            info['filters'].append(dict(filterType=tipo))
            with self.subTest(tipo=tipo), self.assertRaisesRegex(FiltroInvalido, 'no soportado'):
                validar_market_offline(self.orden, info)
        info = copy.deepcopy(self.simbolo)
        info['filters'].append(dict(self.simbolo['filters'][0]))
        with self.assertRaisesRegex(FiltroInvalido, 'duplicado'):
            validar_market_offline(self.orden, info)

    def test_contexto_decimal_externo_no_cambia_resultado(self):
        esperado = self.validar()
        with localcontext() as contexto:
            contexto.prec = 2
            contexto.traps[Inexact] = True
            self.assertEqual(self.validar(), esperado)

    def test_remanente_informa_sin_redondear_la_orden(self):
        self.assertEqual(remanente_de_lote('1.0005', '0.001'),
                         {'alineada_hacia_abajo': '1.000', 'polvo': '0.0005'})
        self.assertEqual(remanente_de_lote('2.000', '0.001'),
                         {'alineada_hacia_abajo': '2.000', 'polvo': '0.000'})
        self.assertEqual(remanente_de_lote('0.0004', '0.001'),
                         {'alineada_hacia_abajo': '0.000', 'polvo': '0.0004'})

    def test_remanente_rechaza_paso_no_positivo(self):
        for paso in ('0', '0.000', '-0.001', '1e-3'):
            with self.subTest(paso=paso), self.assertRaises(FiltroInvalido):
                remanente_de_lote('1', paso)


if __name__ == '__main__':
    unittest.main()
