"""Finding 3 (halt persistente por drawdown) y Finding 2 (contrato diario UTC-5). Sin red: precios inyectados."""
from datetime import datetime, timezone
import logging
import unittest
from unittest.mock import patch

import config
import paper_monitor as monitor
import paper_store as store
import test_paper_system as legado


def _instante(*args):
    return datetime(*args, tzinfo=timezone.utc)


class _Base(unittest.TestCase):
    umbral = 5.0
    reloj = None
    respuesta = legado.PaperTests.respuesta
    abrir = legado.PaperTests.abrir

    def setUp(self):
        legado.PaperTests.setUp(self)
        self.addCleanup(lambda: legado.PaperTests.tearDown(self))
        self.mercado = lambda simbolo: 100.0
        parches = [
            patch.object(store, '_precio_para_equity', side_effect=lambda s: self.mercado(s)),
            patch.object(config, 'DRAWDOWN_HALT_PCT', self.umbral),
        ]
        if self.reloj is not None:
            parches.append(patch.object(store, 'ahora', side_effect=lambda: self.reloj))
        for p in parches:
            p.start()
            self.addCleanup(p.stop)

    def estado_halt(self):
        with store.conectar() as con:
            return dict(con.execute('SELECT * FROM paper_halt WHERE id=1').fetchone())

    def eventos(self, tipo):
        with store.conectar() as con:
            return con.execute('SELECT COUNT(*) FROM paper_events WHERE tipo=?', (tipo,)).fetchone()[0]

    def trades_abiertos(self):
        with store.conectar() as con:
            return con.execute("SELECT COUNT(*) FROM paper_trades WHERE estado='ABIERTA'").fetchone()[0]


class HaltTests(_Base):
    def test_fila_inicial_inactiva_y_sin_umbral_bloquea_entradas(self):
        self.assertEqual(self.estado_halt()['activo'], 0)
        with patch.object(config, 'DRAWDOWN_HALT_PCT', None):
            with self.assertRaisesRegex(ValueError, 'no aprobado'):
                self.abrir()
        self.assertEqual(self.trades_abiertos(), 0)
        self.assertEqual(self.eventos('HALT_ACTIVADO'), 0)

    def test_drawdown_en_entrada_activa_halt_y_rechaza_sin_abrir(self):
        self.abrir()
        self.mercado = lambda simbolo: 80.0  # MTM -8.07 sobre 100 -> drawdown ~8.07 %
        r = self.abrir(self.respuesta({**self.plan, 'simbolo': 'ETHUSDT'}))
        self.assertFalse(r['registrada'])
        self.assertIn('DRAWDOWN_HALT', r['motivo'])
        estado = self.estado_halt()
        self.assertEqual(estado['activo'], 1)
        self.assertAlmostEqual(estado['pico_equity'], 100.0)
        self.assertEqual(self.eventos('HALT_ACTIVADO'), 1)
        self.assertEqual(self.trades_abiertos(), 1)

    def test_halt_no_se_limpia_al_recuperarse_el_precio(self):
        self.abrir()
        self.mercado = lambda simbolo: 80.0
        self.abrir(self.respuesta({**self.plan, 'simbolo': 'ETHUSDT'}))
        self.mercado = lambda simbolo: 100.0
        with self.assertRaisesRegex(ValueError, 'Halt de riesgo activo'):
            self.abrir(self.respuesta({**self.plan, 'simbolo': 'ETHUSDT'}))
        self.assertFalse(store.evaluar_riesgo()['nuevo'])
        self.assertEqual(self.estado_halt()['activo'], 1)

    def test_halt_bloquea_ruta_de_reglas_igual_que_claude(self):
        self.abrir()
        self.mercado = lambda simbolo: 80.0
        self.abrir(self.respuesta({**self.plan, 'simbolo': 'ETHUSDT'}))
        plan_reglas = {**self.plan, 'simbolo': 'SOLUSDT', 'consenso': 'ALCISTA',
                       'estado': 'ALCISTA MOMENTUM SANO', 'origen_revision': 'REGLAS_PAPER_V1'}
        identidad, digest = store.registrar_solicitud(plan_reglas, True)
        with self.assertRaisesRegex(ValueError, 'Halt de riesgo activo'):
            store.ejecutar_reglas(identidad, digest, 100, lambda: True)

    def test_cerrar_posiciones_sigue_permitido_con_halt_activo(self):
        trade = self.abrir()
        self.mercado = lambda simbolo: 80.0
        store.evaluar_riesgo()
        self.assertEqual(self.estado_halt()['activo'], 1)
        cerrada = store.cerrar(trade['id'], 80, 'CERRADA_STOP')
        self.assertTrue(cerrada['cerrada'])
        self.assertEqual(self.trades_abiertos(), 0)

    def test_halt_sobrevive_reinicio_y_inicializar_no_lo_borra(self):
        self.abrir()
        self.mercado = lambda simbolo: 80.0
        store.evaluar_riesgo()
        store.inicializar()  # simula arranque: migraciones idempotentes
        self.assertEqual(self.estado_halt()['activo'], 1)
        with self.assertRaisesRegex(ValueError, 'Halt de riesgo activo'):
            self.abrir(self.respuesta({**self.plan, 'simbolo': 'ETHUSDT'}))

    def test_pico_se_fija_con_mtm_sin_intentos_de_entrada(self):
        self.abrir()
        self.mercado = lambda simbolo: 110.0
        store.evaluar_riesgo()
        pico = self.estado_halt()['pico_equity']
        self.assertGreater(pico, 103.9)
        self.mercado = lambda simbolo: 100.0  # ~3.84 % desde el pico MTM
        with patch.object(config, 'DRAWDOWN_HALT_PCT', 3.0):
            estado = store.evaluar_riesgo()
        self.assertTrue(estado['nuevo'])
        self.assertIn('DRAWDOWN_HALT', estado['motivo'])
        self.assertAlmostEqual(self.estado_halt()['pico_equity'], pico)

    def test_drawdown_bajo_umbral_no_activa(self):
        self.abrir()
        self.mercado = lambda simbolo: 97.0  # ~1.28 % de drawdown
        estado = store.evaluar_riesgo()
        self.assertFalse(estado['bloqueado'])
        self.assertEqual(self.estado_halt()['activo'], 0)

    def test_fallo_de_precio_bloquea_entrada_sin_activar_halt(self):
        self.abrir()
        def sin_red(simbolo):
            raise OSError('sin red')
        self.mercado = sin_red
        with self.assertRaisesRegex(ValueError, 'Precio no disponible'):
            self.abrir(self.respuesta({**self.plan, 'simbolo': 'ETHUSDT'}))
        self.assertEqual(self.estado_halt()['activo'], 0)
        self.assertEqual(self.trades_abiertos(), 1)

    def test_fila_de_halt_ausente_bloquea_fail_closed(self):
        with store.conectar() as con:
            con.execute('DELETE FROM paper_halt')
        with self.assertRaisesRegex(ValueError, 'ausente o corrupto'):
            self.abrir()
        self.assertEqual(self.trades_abiertos(), 0)

    def test_liberar_exige_confirmacion_y_drawdown_por_debajo_del_umbral(self):
        self.abrir()
        self.mercado = lambda simbolo: 80.0
        store.evaluar_riesgo()
        with self.assertRaisesRegex(ValueError, 'confirmación'):
            store.liberar_halt()
        with self.assertRaisesRegex(ValueError, 'por encima del umbral'):
            store.liberar_halt(confirmado=True)
        self.assertEqual(self.estado_halt()['activo'], 1)

    def test_liberacion_confirmada_reabre_entradas_y_queda_auditada(self):
        self.abrir()
        self.mercado = lambda simbolo: 80.0
        store.evaluar_riesgo()
        self.mercado = lambda simbolo: 100.0
        resultado = store.liberar_halt(confirmado=True)
        self.assertTrue(resultado['liberado'])
        self.assertEqual(self.estado_halt()['activo'], 0)
        self.assertEqual(self.eventos('HALT_LIBERADO'), 1)
        r = self.abrir(self.respuesta({**self.plan, 'simbolo': 'ETHUSDT'}))
        self.assertTrue(r['registrada'])

    def test_liberar_sin_halt_no_hace_nada(self):
        self.assertEqual(store.liberar_halt(confirmado=True), {'liberado': False, 'motivo': 'Sin halt activo.'})

    def test_fallo_de_evaluacion_en_monitor_no_impide_revisar(self):
        with patch.object(store, 'evaluar_riesgo', side_effect=RuntimeError('disco')):
            with self.assertLogs(monitor.__name__, level=logging.WARNING):
                resumen = monitor.revisar_operaciones()
        self.assertEqual(resumen['revisadas'], 0)


class DailyLossContractTests(_Base):
    """Finding 2: el día de pérdidas es el día local UTC-5 (corte 05:00 UTC), igual que la base diaria."""
    umbral = 50.0

    def setUp(self):
        self.reloj = _instante(2026, 10, 4, 15, 0)
        super().setUp()

    def cerrar_en(self, trade, instante, precio):
        self.reloj = instante
        return store.cerrar(trade['id'], precio, 'CERRADA_STOP')

    def test_corte_del_dia_es_05_utc(self):
        with store.conectar() as con:
            dia_antes, _ = store.asegurar_dia(con, _instante(2026, 10, 5, 4, 59), 100)
            dia_despues, _ = store.asegurar_dia(con, _instante(2026, 10, 5, 5, 0), 100)
        self.assertEqual(dia_antes, '2026-10-04')
        self.assertEqual(dia_despues, '2026-10-05')

    def test_perdidas_se_cuentan_en_el_dia_local_no_en_el_utc(self):
        # Tres stops cierran a 04:00-04:25 UTC (= 23:00-23:25 local del 04). Base del día: 100; límite: 3.
        trade = self.abrir()  # 15:00 UTC del 04, base 04 = 100
        self.cerrar_en(trade, _instante(2026, 10, 5, 4, 0), 98)
        self.reloj = _instante(2026, 10, 5, 4, 5)
        t2 = self.abrir()
        self.cerrar_en(t2, _instante(2026, 10, 5, 4, 10), 98)
        self.reloj = _instante(2026, 10, 5, 4, 20)
        t3 = self.abrir()
        self.cerrar_en(t3, _instante(2026, 10, 5, 4, 25), 98)
        # 04:30 UTC sigue siendo día 04 local: 2.637 realizados + 0.879 > 3 -> rechazado.
        self.reloj = _instante(2026, 10, 5, 4, 30)
        with self.assertRaisesRegex(ValueError, 'Límite diario'):
            self.abrir(self.respuesta({**self.plan, 'simbolo': 'ETHUSDT'}))
        # 05:01 UTC ya es día 05 local: base nueva y sin pérdidas previas -> permitido.
        self.reloj = _instante(2026, 10, 5, 5, 1)
        self.assertTrue(self.abrir(self.respuesta({**self.plan, 'simbolo': 'ETHUSDT'}))['registrada'])
        with store.conectar() as con:
            base = con.execute("SELECT capital_base FROM paper_days WHERE dia='2026-10-05'").fetchone()[0]
        self.assertAlmostEqual(base, 97.363, places=2)


if __name__ == '__main__':
    unittest.main()
