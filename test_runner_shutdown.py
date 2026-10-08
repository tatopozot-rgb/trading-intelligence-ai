"""Pruebas offline del apagado; no inician el runner operativo."""
from concurrent.futures import Future
import json
from pathlib import Path
import signal
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import config
import system_runner as runner
from runner_health import Salud


class ShutdownTests(unittest.TestCase):
    def test_hilo_real_termina_antes_de_liberar_bloqueo(self):
        with tempfile.TemporaryDirectory() as carpeta, patch.object(config,'DIRECTORIO',Path(carpeta)):
            liberar = threading.Event()
            terminado = threading.Event()
            def trabajo():
                liberar.wait()
                terminado.set()
            monitor = threading.Thread(target=trabajo)
            monitor.start()
            def guardar(_,texto):
                dato = json.loads(texto)
                if dato['estado']=='DETENIENDO':
                    with self.assertRaises(RuntimeError):
                        with runner.instancia_unica():
                            pass
                    liberar.set()
                else:
                    self.assertTrue(terminado.is_set())
                    self.assertFalse(monitor.is_alive())
            try:
                with runner.instancia_unica(),patch.object(runner,'guardar_atomico',side_effect=guardar):
                    runner.finalizar_trabajadores(threading.Event(),monitor,Mock(),None,Salud(),'DETENIDO')
                with runner.instancia_unica():
                    pass
            finally:
                liberar.set()
                monitor.join()

    def test_escritura_siempre_falla_pero_limpieza_termina(self):
        monitor = Mock()
        monitor.is_alive.return_value = False
        pool = Mock()
        with patch.object(runner,'guardar_atomico',side_effect=OSError('sin disco')):
            with self.assertRaises(OSError):
                runner.finalizar_trabajadores(threading.Event(),monitor,pool,None,Salud(),'DETENIDO')
        monitor.join.assert_called_once_with()
        pool.shutdown.assert_called_once_with(wait=True,cancel_futures=True)

    def test_monitor_no_iniciado_no_se_join_y_pool_cierra(self):
        monitor = threading.Thread(target=lambda:None)
        pool = Mock()
        with patch.object(runner,'guardar_atomico'):
            runner.finalizar_trabajadores(threading.Event(),monitor,pool,None,Salud(),'ERROR')
        pool.shutdown.assert_called_once_with(wait=True,cancel_futures=True)

    def test_monitor_lento_conserva_bloqueo_y_no_declara_detenido(self):
        with tempfile.TemporaryDirectory() as carpeta, patch.object(config,'DIRECTORIO',Path(carpeta)):
            vivos = [65]  # Más de 60 joins de un segundo, sin demora real.
            monitor = Mock()
            monitor.is_alive.side_effect = lambda: vivos[0]>0
            monitor.join.side_effect = lambda **kw: vivos.__setitem__(0,max(0,vivos[0]-1))
            pool = Mock()
            estados = []
            def guardar(_, texto):
                dato = json.loads(texto)
                estados.append(dato)
                with self.assertRaises(RuntimeError):
                    with runner.instancia_unica():
                        pass
                if vivos[0]:
                    self.assertEqual(dato['estado'],'DETENIENDO')
            with runner.instancia_unica(), patch.object(runner,'guardar_atomico',side_effect=guardar):
                runner.finalizar_trabajadores(threading.Event(),monitor,pool,None,Salud(),'DETENIDO')
            self.assertEqual(estados[-1]['estado'],'DETENIDO')
            self.assertFalse(estados[-1]['monitor_vivo'])
            self.assertGreater(len(estados),60)
            pool.shutdown.assert_called_once_with(wait=True,cancel_futures=True)

    def test_error_escritura_no_omite_join_y_shutdown(self):
        monitor = Mock()
        monitor.is_alive.return_value = False
        pool = Mock()
        estados = []
        def guardar(_,texto):
            estados.append(json.loads(texto)['estado'])
            if len(estados)==1:
                raise OSError('disco simulado')
            monitor.join.assert_called_once_with()
            pool.shutdown.assert_called_once_with(wait=True,cancel_futures=True)
        with patch.object(runner,'guardar_atomico',side_effect=guardar):
            with self.assertRaisesRegex(OSError,'disco simulado'):
                runner.finalizar_trabajadores(threading.Event(),monitor,pool,None,Salud(),'DETENIDO')
        self.assertEqual(estados,['DETENIENDO','ERROR'])

    def test_scanner_en_curso_no_se_omite(self):
        futuro = Future()
        futuro.set_running_or_notify_cancel()
        monitor = Mock()
        monitor.is_alive.return_value = False
        salud = Salud()
        estados = []
        def terminar(_):
            self.assertEqual(estados[-1]['estado'],'DETENIENDO')
            self.assertTrue(estados[-1]['scanner_en_curso'])
            futuro.set_result({'errores':0})
        with patch.object(runner,'guardar_atomico',side_effect=lambda _,t:estados.append(json.loads(t))), \
             patch.object(runner.time,'sleep',side_effect=terminar):
            runner.finalizar_trabajadores(threading.Event(),monitor,Mock(),futuro,salud,'DETENIDO')
        self.assertFalse(estados[-1]['scanner_en_curso'])
        self.assertEqual(salud.snapshot()['scanner']['ciclos'],1)

    def test_scanner_pendiente_se_cancela_sin_resultado(self):
        futuro = Future()
        monitor = Mock()
        monitor.is_alive.return_value = False
        salud = Salud()
        with patch.object(runner,'guardar_atomico'):
            runner.finalizar_trabajadores(threading.Event(),monitor,Mock(),futuro,salud,'DETENIDO')
        self.assertTrue(futuro.cancelled())
        self.assertEqual(salud.snapshot()['scanner']['ciclos'],0)

    def test_scanner_fallido_queda_visible(self):
        futuro = Future()
        futuro.set_exception(ValueError('fixture'))
        monitor = Mock()
        monitor.is_alive.return_value = False
        salud = Salud()
        with patch.object(runner,'guardar_atomico'):
            runner.finalizar_trabajadores(threading.Event(),monitor,Mock(),futuro,salud,'ERROR')
        self.assertEqual(salud.snapshot()['scanner']['estado'],'ERROR')

    def test_sigint_protegido_y_restaurado_aun_con_error(self):
        anterior = signal.getsignal(signal.SIGINT)
        with self.assertRaisesRegex(OSError,'fixture'):
            with runner.proteger_apagado():
                self.assertEqual(signal.getsignal(signal.SIGINT),signal.SIG_IGN)
                raise OSError('fixture')
        self.assertEqual(signal.getsignal(signal.SIGINT),anterior)

    def test_error_del_cuerpo_no_se_confunde_con_error_de_bloqueo(self):
        with tempfile.TemporaryDirectory() as carpeta, patch.object(config,'DIRECTORIO',Path(carpeta)):
            with self.assertRaisesRegex(OSError,'fixture'):
                with runner.instancia_unica():
                    raise OSError('fixture')
            with runner.instancia_unica():
                pass


if __name__=='__main__':
    unittest.main()
