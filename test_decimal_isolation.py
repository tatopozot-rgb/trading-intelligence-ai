"""Una aplicación anfitriona no debe cambiar evidencia/validaciones ya fijadas."""
import copy
from decimal import ROUND_DOWN, ROUND_UP, localcontext
import unittest

import paper_fills
import test_broker_adapters as brokers
import test_execution_filters as filtros
import test_execution_percent as porcentajes
import test_paper_fills as fills


class DecimalIsolationTests(unittest.TestCase):
    def comprobar(self, llamada):
        esperado = llamada()
        for redondeo in (ROUND_DOWN, ROUND_UP):
            with localcontext() as contexto:
                contexto.prec = 2
                contexto.rounding = redondeo
                contexto.Emax = 0
                contexto.Emin = 0
                contexto.clamp = 1
                for clave in contexto.traps:
                    contexto.traps[clave] = True
                contexto.clear_flags()
                antes = repr(contexto)
                self.assertEqual(llamada(), esperado)
                self.assertEqual(repr(contexto), antes)

    def test_simulacion_evidencia_identica_con_contexto_hostil(self):
        self.comprobar(lambda: paper_fills.evidencia(fills.snapshot(), lado='BUY',
            monto='100', comision_pct='.1', ahora_ms=1200))

    def test_evidencia_preexistente_no_se_declara_alterada(self):
        e = paper_fills.evidencia(fills.snapshot(), lado='BUY', monto='100', comision_pct='.1', ahora_ms=1200)
        self.comprobar(lambda: paper_fills.validar_evidencia(e, simbolo='BTCUSDT',
            lado='BUY', monto='100', comision_pct='.1', precio=float(e['resultado']['precio_medio']), ahora_ms=1300))

    def test_cierre_decimal_no_hereda_inexact(self):
        compra = paper_fills.evidencia(fills.snapshot(), lado='BUY', monto='3', comision_pct='.1', ahora_ms=1200)
        venta = paper_fills.evidencia(fills.snapshot(), lado='SELL',
            monto=compra['resultado']['base_ejecutada'], comision_pct='.1', ahora_ms=1200)
        self.comprobar(lambda: paper_fills.resultado_cierre(compra, venta))

    def test_limites_estaticos_no_heredan_overflow(self):
        fixture = filtros.FilterTests()
        fixture.setUp()
        self.comprobar(fixture.validar)

    def test_porcentajes_no_heredan_overflow(self):
        fixture = porcentajes.PercentTests()
        fixture.setUp()
        self.comprobar(fixture.validar)

    def test_lotes_mt5_no_heredan_clamped(self):
        fixture = brokers.BrokerAdaptersTests()
        datos = fixture.economia()
        self.comprobar(lambda: fixture.leer_economia(*datos))

    def test_contexto_fijo_no_permite_evidencia_falsa(self):
        e = paper_fills.evidencia(fills.snapshot(), lado='BUY', monto='100', comision_pct='.1', ahora_ms=1200)
        adulterado = copy.deepcopy(e)
        adulterado['resultado']['comision_quote'] = '0'
        def rechazar():
            with self.assertRaisesRegex(ValueError, 'alterado'):
                paper_fills.validar_evidencia(adulterado, simbolo='BTCUSDT', lado='BUY',
                    monto='100', comision_pct='.1', precio=float(e['resultado']['precio_medio']), ahora_ms=1300)
            return 'RECHAZADO'
        self.comprobar(rechazar)


if __name__ == '__main__':
    unittest.main()
