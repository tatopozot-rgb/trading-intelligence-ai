"""Arranque seguro con SQLite temporal; no trabaja con la cuenta del usuario."""
import io
import unittest
from unittest.mock import patch

import paper_store as store
import system_runner as runner


class PreflightTests(unittest.TestCase):
    def setUp(self):
        from test_paper_system import PaperTests
        PaperTests.setUp(self)
        self.addCleanup(lambda: PaperTests.tearDown(self))
        self.enterContext(patch('requests.sessions.Session.request',
                                side_effect=AssertionError('Red prohibida')))

    def test_conciliacion_valida_no_crea_log_ni_workers(self):
        with patch.object(runner.threading, 'Thread') as hilo, \
             patch.object(runner, 'ThreadPoolExecutor') as pool:
            runner.validar_arranque()
        hilo.assert_not_called()
        pool.assert_not_called()
        self.assertFalse((self.root/'logs').exists())

    def test_discrepancia_bloquea_todos_los_trabajadores(self):
        with store.conectar() as con:
            con.execute('UPDATE paper_account SET saldo_actual=101 WHERE id=1')
        with patch.object(runner.threading, 'Thread') as hilo, \
             patch.object(runner, 'ThreadPoolExecutor') as pool, \
             self.assertRaisesRegex(ValueError, 'Conciliación'):
            runner.ejecutar_continuo(.01, reglas=True, profundidad=True)
        hilo.assert_not_called()
        pool.assert_not_called()
        self.assertFalse((self.root/'logs').exists())

    def test_cli_discrepante_conserva_senal_de_parada(self):
        runner.PARADA.touch()
        with store.conectar() as con:
            con.execute('UPDATE paper_account SET pnl_acumulado=1 WHERE id=1')
        with patch('sys.argv', ['runner','--continuo','--reglas-paper','--profundidad-paper','--reanudar']), \
             patch.object(runner, 'ejecutar_continuo') as ejecutar, \
             self.assertRaisesRegex(ValueError, 'Conciliación'):
            runner.main()
        self.assertTrue(runner.PARADA.exists())
        ejecutar.assert_not_called()

    def test_profundidad_requiere_reglas_incluso_sin_cli(self):
        for valor in (True, 'true', 1, None):
            with self.subTest(valor=valor), patch.object(runner, 'preparar') as preparar, \
                 self.assertRaises(ValueError):
                runner.ejecutar_continuo(.01, profundidad=valor)
            preparar.assert_not_called()

    def test_cli_profundidad_incompatible_no_quita_stop(self):
        runner.PARADA.touch()
        with patch('sys.argv',['runner','--continuo','--profundidad-paper','--reanudar']), \
             patch('sys.stderr',new_callable=io.StringIO), self.assertRaises(SystemExit):
            runner.main()
        self.assertTrue(runner.PARADA.exists())


if __name__ == '__main__':
    unittest.main()
