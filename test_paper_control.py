from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

import config
import paper_control as control
import paper_store as store
import system_runner as runner

POPEN_PRUEBA_LOCAL = subprocess.Popen


class ControlTests(unittest.TestCase):
    def setUp(self):
        from test_paper_system import PaperTests
        PaperTests.setUp(self)
        self.addCleanup(lambda: PaperTests.tearDown(self))
        (self.root/'.venv'/'Scripts').mkdir(parents=True)
        (self.root/'.venv'/'Scripts'/'python.exe').touch()  # nunca ejecutado
        (self.root/'system_runner.py').touch()
        self.hijo = Mock(pid=7654)
        self.hijo.poll.return_value = None
        self.launcher = Mock(return_value=self.hijo)
        self.c = control.ControlPaper(self.root, self.launcher)
        self.stop = self.root/'DETENER_RUNNER'
        self.stop.touch()
        self.pausa = self.root/'PAUSA_ENTRADAS'
        self.pausa.touch()
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('Proceso real prohibido')))
        self.enterContext(patch('requests.sessions.Session.request', side_effect=AssertionError('Red prohibida')))

    def iniciar(self):
        return self.c.iniciar(1, confirmado=True)

    def estado(self, **cambios):
        dato = {'modo':'PAPER','sesion_id':self.c.sesion_id,'pid':self.hijo.pid,'estado':'ACTIVO'}
        dato.update(cambios)
        (self.root/'runner_status.json').write_text(json.dumps(dato), encoding='utf-8')

    def test_sin_autoinicio_confirmacion_duracion_y_modo(self):
        self.assertEqual(self.c.observar()['estado'], 'SIN_PROCESO_PROPIO')
        for valor in (True, '1', 0, -1, 9, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.c.iniciar(valor, confirmado=True)
        for confirmado in (False, 1, 'sí'):
            with self.assertRaises(ValueError):
                self.c.iniciar(1, confirmado=confirmado)
        with patch.object(config, 'USAR_DINERO_REAL', True), self.assertRaises(ValueError):
            self.iniciar()
        self.launcher.assert_not_called()
        self.assertTrue(self.stop.exists())

    def test_argumentos_fijos_y_senales_conservadas(self):
        identidad = self.iniciar()
        args, kw = self.launcher.call_args
        self.assertEqual(args[0][:2], [str(self.root/'.venv'/'Scripts'/'python.exe'), str(self.root/'system_runner.py')])
        self.assertEqual(args[0][2:], ['--continuo','--reglas-paper','--horas','1.0','--reanudar','--sesion-id',identidad])
        self.assertFalse(kw['shell'])
        self.assertTrue(kw['stdout'].closed)
        self.assertTrue(self.stop.exists())
        self.assertTrue(self.pausa.exists())
        self.assertEqual(self.c.observar()['estado'], 'INICIO_NO_CONFIRMADO')

    def test_doble_click_concurrente_y_hijo_sin_estado(self):
        def intentar(_):
            try:
                return bool(self.iniciar())
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(intentar, range(4))), 1)
        self.launcher.assert_called_once()
        for _ in range(3):
            self.assertTrue(self.c.observar()['proceso_vivo'])
            with self.assertRaises(ValueError):
                self.iniciar()

    def test_profundidad_optativa_estricta_y_una_sola_bandera(self):
        for valor in (1, 'true', None):
            with self.assertRaises(ValueError):
                self.c.iniciar(1, confirmado=True, profundidad=valor)
        self.launcher.assert_not_called()
        self.c.iniciar(1, confirmado=True, profundidad=True)
        args = self.launcher.call_args.args[0]
        self.assertEqual(args.count('--profundidad-paper'), 1)
        self.assertEqual(self.c.observar()['modelo_solicitado'], 'PROFUNDIDAD_VISIBLE_FOK_PAPER_V1')
        self.assertTrue(self.pausa.exists())

    def test_fallo_launcher_y_reintento_solo_manual(self):
        self.launcher.side_effect = OSError('fixture')
        with self.assertRaises(OSError):
            self.iniciar()
        self.assertEqual(self.c.observar()['estado'], 'FALLO_LANZAMIENTO')
        self.assertTrue(self.stop.exists())
        self.assertTrue(self.pausa.exists())
        self.launcher.assert_called_once()
        self.launcher.side_effect = None
        self.iniciar()
        self.assertEqual(self.launcher.call_count, 2)

    def test_hijo_muerto_sin_estado_libera_intento_manual(self):
        primero = self.iniciar()
        self.hijo.poll.return_value = 1
        self.assertEqual(self.c.observar()['estado'], 'FALLO_TERMINADO')
        self.assertTrue(self.stop.exists())
        self.assertNotEqual(self.iniciar(), primero)

    def test_estado_incoherente_no_confirma(self):
        self.iniciar()
        for cambio in ({'sesion_id':'otro'}, {'pid':0}, {'modo':'REAL'}, {'estado':'DETENIDO'}):
            self.estado(**cambio)
            self.assertEqual(self.c.observar()['estado'], 'INICIO_NO_CONFIRMADO')
        (self.root/'runner_status.json').write_text('{')
        self.assertEqual(self.c.observar()['estado'], 'INICIO_NO_CONFIRMADO')
        self.estado()
        self.assertEqual(self.c.observar()['estado'], 'ACTIVO_REGISTRADO')
        self.hijo.poll.return_value = 0
        self.assertEqual(self.c.observar()['estado'], 'TERMINADO')

    def test_poll_incierto_no_admite_otro_inicio(self):
        self.iniciar()
        self.hijo.poll.side_effect = OSError('fixture')
        self.assertIsNone(self.c.observar()['proceso_vivo'])
        with self.assertRaises(OSError):
            self.iniciar()
        self.launcher.assert_called_once()

    def test_launcher_padre_requiere_id_modo_y_handle_vivo(self):
        self.iniciar()
        self.estado(pid=12345, parent_pid=self.hijo.pid)
        self.assertEqual(self.c.observar()['estado'], 'ACTIVO_REGISTRADO')
        self.estado(pid=12345, parent_pid=self.hijo.pid, sesion_id='otro')
        self.assertEqual(self.c.observar()['estado'], 'INICIO_NO_CONFIRMADO')
        self.estado(pid=12345, parent_pid=0)
        self.assertEqual(self.c.observar()['estado'], 'INICIO_NO_CONFIRMADO')
        self.estado(pid=12345, parent_pid=self.hijo.pid)
        self.hijo.poll.return_value = 0
        self.assertEqual(self.c.observar()['estado'], 'TERMINADO')

    @unittest.skipUnless(os.name == 'nt', 'Launcher de venv Windows')
    def test_launcher_venv_real_con_sonda_sin_trading_ni_red(self):
        # Proceso mínimo temporal; NO ejecuta código del runner ni consulta mercado.
        shutil.copyfile(sys.executable, self.root/'.venv'/'Scripts'/'python.exe')
        shutil.copyfile(Path(sys.prefix)/'pyvenv.cfg', self.root/'.venv'/'pyvenv.cfg')
        sonda = '''import json, os, pathlib, sys, time
root = pathlib.Path.cwd()
identidad = sys.argv[sys.argv.index('--sesion-id')+1]
(root/'runner_status.json').write_text(json.dumps({'modo':'PAPER','estado':'ACTIVO',
    'sesion_id':identidad,'pid':os.getpid(),'parent_pid':os.getppid()}))
fin = time.monotonic()+5
while time.monotonic()<fin and not (root/'release').exists():
    time.sleep(.02)
'''
        (self.root/'system_runner.py').write_text(sonda, encoding='utf-8')
        c = control.ControlPaper(self.root, POPEN_PRUEBA_LOCAL)
        c.iniciar(.5, confirmado=True)
        try:
            fin = time.monotonic()+4
            while time.monotonic()<fin and c.observar()['estado'] == 'INICIO_NO_CONFIRMADO':
                time.sleep(.02)
            estado = c.observar()
            self.assertEqual(estado['estado'], 'ACTIVO_REGISTRADO')
            self.assertTrue(estado['proceso_vivo'])
            self.assertIn(c.proceso.pid, (estado['registro']['pid'], estado['registro']['parent_pid']))
        finally:
            (self.root/'release').touch()
            c.proceso.wait(timeout=7)
        self.assertEqual(c.observar()['estado'], 'TERMINADO')
        self.assertTrue(self.stop.exists())

    def test_pausa_reanudar_no_quita_stop_ni_arranca(self):
        with self.assertRaises(ValueError):
            self.c.reanudar_entradas()
        self.c.reanudar_entradas(confirmado=True)
        self.assertFalse(self.pausa.exists())
        self.assertTrue(self.stop.exists())
        self.c.pausar()
        self.assertTrue(self.pausa.exists())
        self.launcher.assert_not_called()

    def test_stop_cancela_intento_y_no_mata_hijo(self):
        identidad = self.iniciar()
        self.c.detener()
        self.assertTrue(control.cancelacion_sesion(self.root, identidad).exists())
        self.assertTrue(self.stop.exists())
        self.assertTrue(self.pausa.exists())
        self.assertEqual(self.c.observar()['estado'], 'PARADA_SOLICITADA')
        self.hijo.kill.assert_not_called()
        self.hijo.terminate.assert_not_called()

    def test_fallo_escritura_senal_se_informa_y_intenta_otra(self):
        self.iniciar()
        original = Path.touch
        def tocar(path, *args, **kwargs):
            if path.name.startswith('DETENER_SESION_'):
                raise OSError('fixture')
            return original(path, *args, **kwargs)
        self.stop.unlink()
        with patch.object(Path, 'touch', tocar), self.assertRaises(OSError):
            self.c.detener()
        self.assertTrue(self.stop.exists())

    def test_id_rechaza_rutas(self):
        for identidad in ('../stop', 'A'*32, '', None, 'a'*33):
            with self.assertRaises(ValueError):
                control.cancelacion_sesion(self.root, identidad)

    def test_cli_invalido_no_borra_stop(self):
        runner.PARADA.touch()
        for extra in (['--horas','nan'], ['--sesion-id','../stop']):
            with patch('sys.argv', ['runner','--continuo','--reglas-paper','--reanudar',*extra]), \
                 patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit):
                runner.main()
            self.assertTrue(runner.PARADA.exists())

    def test_bloqueo_antes_retirar_stop_y_cancelacion_previa(self):
        identidad = 'a'*32
        runner.PARADA.touch()
        with runner.instancia_unica(), patch('sys.argv', ['runner','--continuo','--reglas-paper','--reanudar','--sesion-id',identidad]), \
             patch.object(runner,'ejecutar_continuo') as ejecutar, self.assertRaises(RuntimeError):
            runner.main()
        ejecutar.assert_not_called()
        self.assertTrue(runner.PARADA.exists())
        control.cancelacion_sesion(self.root, identidad).touch()
        with patch('sys.argv', ['runner','--continuo','--reglas-paper','--reanudar','--sesion-id',identidad]), \
             patch.object(runner,'ejecutar_continuo') as ejecutar, self.assertRaises(ValueError):
            runner.main()
        ejecutar.assert_not_called()
        self.assertTrue(runner.PARADA.exists())

    def test_parada_durante_retirada_stop_no_arranca_monitor(self):
        identidad = 'b'*32
        runner.PARADA.touch()
        original = Path.unlink
        def borrar(path, *args, **kwargs):
            if path == runner.PARADA:
                control.cancelacion_sesion(self.root, identidad).touch()
            return original(path, *args, **kwargs)
        with patch.object(Path,'unlink',borrar), patch('sys.argv', ['runner','--continuo','--reglas-paper','--reanudar','--sesion-id',identidad]), \
             patch.object(runner,'preparar'), patch.object(runner,'monitor_continuo') as monitor, self.assertRaises(ValueError):
            runner.main()
        monitor.assert_not_called()
        self.assertTrue(control.cancelacion_sesion(self.root, identidad).exists())

    def test_sesion_id_en_latido_y_terminal_con_datos_ficticios(self):
        identidad = 'c'*32
        publicaciones = []
        original = runner.guardar_atomico
        def guardar(path, texto):
            publicaciones.append(json.loads(texto))
            original(path, texto)
            control.cancelacion_sesion(self.root, identidad).touch()
        with patch.object(runner,'preparar'), patch.object(runner,'monitor_continuo'), \
             patch.object(runner,'escanear',return_value={'errores':0}), patch.object(runner,'guardar_atomico',guardar):
            runner.ejecutar_continuo(horas=.001, reglas=True, sesion_id=identidad)
        self.assertEqual(publicaciones[0]['estado'], 'ACTIVO')
        self.assertEqual(publicaciones[-1]['estado'], 'DETENIDO')
        self.assertTrue(all(p['sesion_id'] == identidad for p in publicaciones))


if __name__ == '__main__':
    unittest.main()
