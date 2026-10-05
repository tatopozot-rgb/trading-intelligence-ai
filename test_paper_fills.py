import copy
from decimal import Decimal
import unittest
from unittest.mock import Mock

import paper_fills as f


def snapshot():
    return dict(fuente='FIXTURE', simbolo='BTCUSDT', solicitado_ms=1000, recibido_ms=1100,
                libro=dict(lastUpdateId=10, bids=[['99','1'], ['98','2']], asks=[['101','1'], ['102','2']]))


class FillTests(unittest.TestCase):
    def simular(self, **kw):
        a = dict(lado='BUY', monto='203', comision_pct='.1', ahora_ms=1200)
        return f.simular(snapshot(), **(a | kw))

    def test_buy_vwap_fee_spread_y_no_mutacion(self):
        s = snapshot(); antes = copy.deepcopy(s)
        r = f.simular(s, lado='BUY', monto=203, comision_pct=.1, ahora_ms=1200)
        self.assertEqual(r['base_ejecutada'], '2')
        self.assertEqual(r['precio_medio'], '101.5')
        self.assertEqual(r['comision_quote'], '0.203')
        self.assertEqual(r['spread_bps'], '200.00')
        self.assertEqual(r['estado'], 'COMPLETO'); self.assertEqual(s, antes)
        self.assertFalse(r['enviable'])

    def test_sell_en_bids_y_no_suma_spread_dos_veces(self):
        r = self.simular(lado='SELL', monto=2)
        self.assertEqual(r['quote_ejecutado'], '197')
        self.assertEqual(r['precio_medio'], '98.5')
        self.assertEqual(r['comision_quote'], '0.197')

    def test_parciales_no_inventan_niveles(self):
        a = self.simular(monto=400); b = self.simular(lado='SELL', monto=4)
        self.assertEqual((a['estado'], a['quote_ejecutado'], a['restante']), ('PARCIAL','305','95'))
        self.assertEqual((b['estado'], b['base_ejecutada'], b['restante']), ('PARCIAL','3','1'))

    def test_limite_exacto_y_division_periodica(self):
        for m in ('101','305','100'):
            r = self.simular(monto=m)
            self.assertEqual(r['estado'], 'COMPLETO'); self.assertEqual(Decimal(r['quote_ejecutado']), Decimal(m))

    def test_numeros_no_validos(self):
        for v in (True, 'NaN', 'Infinity', 0, -1, '1e9999999', '1e-100'):
            with self.subTest(v=v), self.assertRaises(ValueError): self.simular(monto=v)
        for v in (100, -1, True, 'NaN'):
            with self.assertRaises(ValueError): self.simular(comision_pct=v)

    def test_tiempo_futuro_caducado_lento(self):
        for v in (True, 999, 1001, 6001):
            with self.subTest(v=v), self.assertRaises(ValueError): self.simular(ahora_ms=v)
        self.assertEqual(self.simular(ahora_ms=6000)['estado'], 'COMPLETO')
        with self.assertRaises(ValueError): self.simular(max_edad_ms=6000)

    def test_libro_cruzado_duplicado_desordenado_vacio(self):
        for bids in ([], [['102','1']], [['99','1'],['99','2']], [['98','1'],['99','1']], [['99','0']]):
            s = snapshot(); s['libro']['bids'] = bids
            with self.subTest(bids=bids), self.assertRaises(ValueError):
                f.simular(s, lado='BUY', monto=10, comision_pct=0, ahora_ms=1200)

    def test_evidencia_recalcula_y_rechaza_adulteracion(self):
        e = f.evidencia(snapshot(), lado='BUY', monto=203, comision_pct=.1, ahora_ms=1200)
        kw = dict(simbolo='BTCUSDT', lado='BUY', monto=203, comision_pct=.1, precio=101.5, ahora_ms=1300)
        self.assertEqual(f.validar_evidencia(e, **kw), e)
        for cambios in ({'simbolo':'ETHUSDT'}, {'precio':101}, {'monto':204}, {'lado':'SELL'}, {'ahora_ms':6001}):
            with self.assertRaises(ValueError): f.validar_evidencia(e, **(kw | cambios))
        e['resultado']['comision_quote'] = '0'
        with self.assertRaises(ValueError): f.validar_evidencia(e, **kw)

    def test_parcial_no_se_convierte_en_operacion_completa(self):
        e = f.evidencia(snapshot(), lado='BUY', monto=400, comision_pct=.1, ahora_ms=1200)
        with self.assertRaisesRegex(ValueError, 'incompleto'):
            f.validar_evidencia(e, simbolo='BTCUSDT', lado='BUY', monto=400, comision_pct=.1,
                                precio=float(e['resultado']['precio_medio']), ahora_ms=1300)

    def test_cotizacion_solo_get_limit_acotado_sin_crear_fecha_exchange(self):
        cliente = Mock(); cliente.get.return_value = snapshot()['libro']
        r = f.cotizar('BTCUSDT', cliente=cliente, reloj=Mock(side_effect=[1000,1100]))
        cliente.get.assert_called_once_with('/api/v3/depth', {'symbol':'BTCUSDT','limit':100})
        self.assertEqual(r['recibido_ms'], 1100); self.assertNotIn('timestamp_exchange', r)
        with self.assertRaises(ValueError):
            f.cotizar('BTCUSDT', cliente=cliente, reloj=Mock(side_effect=[1000,7000]))


if __name__ == '__main__': unittest.main()
