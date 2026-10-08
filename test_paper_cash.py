"""Reservas de efectivo y base diaria con SQLite temporal; sin mercado real."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import config
import paper_report
import paper_store as store
import risk_engine


class PaperCashTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix='paper-cash-test-')
        self.addCleanup(temporal.cleanup)
        self.root = Path(temporal.name)
        for p in (patch.object(config, 'BASE_DATOS', self.root/'test.db'),
                  patch.object(config, 'DIRECTORIO', self.root),
                  patch.object(config, 'DRAWDOWN_HALT_PCT', 50.0), patch.object(config, 'DRAWDOWN_PAUSE_PCT', None),
                  patch.object(store, '_precio_para_equity', side_effect=lambda simbolo: 100.0),
                  patch('socket.create_connection', side_effect=AssertionError('Red prohibida'))):
            p.start()
            self.addCleanup(p.stop)
        store.inicializar()
        self.plan = dict(modo='PAPER', decision='PAPER CANDIDATE', simbolo='BTCUSDT',
                         entrada=100., stop_precio=98., objetivo_precio=104.,
                         tamano_posicion=40., riesgo_usd=.88, comision_paper_pct=.1,
                         consenso='ALCISTA', estado='ALCISTA MOMENTUM SANO',
                         origen_revision='REGLAS_PAPER_V1')

    def abrir(self, simbolo='BTCUSDT', tamano=40, stop=98):
        plan = {**self.plan, 'simbolo':simbolo, 'tamano_posicion':tamano, 'stop_precio':stop}
        return store.ejecutar_reglas(*store.registrar_solicitud(plan, True), 100, lambda:True)

    def test_apertura_reserva_compra_y_comision_de_entrada(self):
        self.abrir(tamano=50, stop=99)
        with self.assertRaisesRegex(ValueError, 'Capital disponible'):
            self.abrir('ETHUSDT', tamano=50, stop=99)
        with store.conectar() as con:
            estado = store.resumen(con)
        self.assertEqual(estado['n'], 1)
        self.assertAlmostEqual(estado['nominal'], 50)
        self.assertAlmostEqual(estado['capital'], 50.05)
        self.assertAlmostEqual(estado['comisiones_entrada'], .05)

    def test_retiro_no_puede_consumir_comision_reservada(self):
        trade = self.abrir()
        with self.assertRaisesRegex(ValueError, 'capital libre'):
            store.movimiento(-60, 'retiro temporal')
        store.movimiento(-59.96, 'retiro temporal permitido')
        self.assertAlmostEqual(store.cuenta()['saldo_actual'], 40.04)
        cerrado = store.cerrar(trade['id'], 100, 'CERRADA_MANUAL')
        self.assertAlmostEqual(cerrado['resultado_usd'], -.08)
        self.assertAlmostEqual(cerrado['saldo_actual'], 39.96)
        self.assertEqual(paper_report.informe()['estado'], 'OK')

    def test_reporte_reserva_comision_sin_reescribir_pnl(self):
        self.abrir()
        informe = paper_report.informe()
        self.assertEqual(informe['estado'], 'OK')
        self.assertAlmostEqual(informe['cuenta']['capital_abierto'], 40)
        self.assertAlmostEqual(informe['cuenta']['capital_comprometido'], 40.04)
        self.assertAlmostEqual(informe['cuenta']['comisiones_entrada_reservadas'], .04)
        self.assertEqual(informe['cuenta']['pnl_cerrado'], 0)

    def test_reporte_detecta_efectivo_insuficiente_para_tarifa(self):
        self.abrir()
        with store.conectar() as con:
            con.execute('UPDATE paper_account SET capital_inicial=40,saldo_actual=40')
        codigos = {p['codigo'] for p in paper_report.informe()['problemas']}
        self.assertIn('CAPITAL_ABIERTO_SUPERA_SALDO', codigos)
        self.assertNotIn('SALDO_NO_CONCILIA', codigos)

    def test_tarifa_desconocida_bloquea_consumo_de_efectivo(self):
        self.abrir()
        with store.conectar() as con:
            con.execute('UPDATE paper_trades SET comision_pct_apertura=NULL')
        with self.assertRaisesRegex(ValueError, 'Comisión'):
            store.movimiento(-1, 'retiro temporal')
        self.assertEqual(store.cuenta()['saldo_actual'], 100)

    def test_primer_cierre_del_dia_fija_base_antes_del_resultado(self):
        with patch.object(store, 'ahora', return_value=datetime(2026, 9, 25, 20, tzinfo=timezone.utc)):
            trade = self.abrir()
        with patch.object(store, 'ahora', return_value=datetime(2026, 9, 26, 6, tzinfo=timezone.utc)):
            store.cerrar(trade['id'], 104, 'CERRADA_OBJETIVO')
            trade = self.abrir()
            store.cerrar(trade['id'], 98, 'CERRADA_STOP')
            with store.conectar() as con:
                base = con.execute("SELECT capital_base FROM paper_days WHERE dia='2026-09-26'").fetchone()[0]
            self.assertEqual(base, 100)

    def test_primer_stop_no_reduce_la_base_del_nuevo_dia(self):
        with patch.object(store, 'ahora', return_value=datetime(2026, 9, 25, 20, tzinfo=timezone.utc)):
            trade = self.abrir()
        with patch.object(store, 'ahora', return_value=datetime(2026, 9, 26, 6, tzinfo=timezone.utc)):
            store.cerrar(trade['id'], 98, 'CERRADA_STOP')
            self.abrir()
            with store.conectar() as con:
                base = con.execute("SELECT capital_base FROM paper_days WHERE dia='2026-09-26'").fetchone()[0]
            self.assertEqual(base, 100)

    def test_rollback_cierre_no_deja_base_diaria_parcial(self):
        with patch.object(store, 'ahora', return_value=datetime(2026, 9, 25, 20, tzinfo=timezone.utc)):
            trade = self.abrir()
        with patch.object(store, 'ahora', return_value=datetime(2026, 9, 26, 6, tzinfo=timezone.utc)), \
                patch.object(store, 'evento', side_effect=RuntimeError('disco temporal')):
            with self.assertRaisesRegex(RuntimeError, 'disco'):
                store.cerrar(trade['id'], 104, 'CERRADA_OBJETIVO')
        with store.conectar() as con:
            self.assertIsNone(con.execute("SELECT capital_base FROM paper_days WHERE dia='2026-09-26'").fetchone())
            self.assertEqual(con.execute('SELECT estado FROM paper_trades').fetchone()[0], 'ABIERTA')

    def test_tamano_spot_incluye_comision_en_tope_de_efectivo(self):
        posicion = risk_engine.calcular_tamano_posicion(.5, 100, comision_entrada_pct=.1)
        self.assertAlmostEqual(posicion['tamano_posicion'], 100/1.001)
        self.assertAlmostEqual(store.capital_requerido(posicion['tamano_posicion'], .1), 100)

    def test_riesgo_no_acepta_numeros_invalidos(self):
        for valor in (True, float('nan'), float('inf'), -1, 0):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    risk_engine.calcular_tamano_posicion(valor, 100)
                with self.assertRaises(ValueError):
                    risk_engine.calcular_tamano_posicion(1, valor)


if __name__ == '__main__':
    unittest.main()
