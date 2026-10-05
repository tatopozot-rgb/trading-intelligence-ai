from contextlib import redirect_stdout
import io
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

import paper_dashboard as panel


class UIControlTests(unittest.TestCase):
    def setUp(self):
        from test_paper_control import ControlTests
        ControlTests.setUp(self)
        self.ventana = tk.Tk()
        self.ventana.withdraw()
        self.ui = panel.ControlesPanel(self.ventana, self.c)
        self.ui.dialogos = Mock()
        self.ui.dialogos.askyesno.return_value = False
        self.addCleanup(self.cerrar_fixture)

    def cerrar_fixture(self):
        try:
            if self.ui.timer is not None:
                self.ventana.after_cancel(self.ui.timer)
            self.ventana.destroy()
        except tk.TclError:
            pass

    def iniciar_ui(self):
        self.ui.horas.set('0,5')
        self.ui.dialogos.askyesno.return_value = True
        self.ui.botones['Iniciar PAPER'].invoke()

    def test_abrir_y_refrescar_no_inicia_ni_muta(self):
        archivos = {p.relative_to(self.root) for p in self.root.rglob('*')}
        for _ in range(3):
            self.ui.refrescar()
        self.launcher.assert_not_called()
        self.assertEqual(archivos, {p.relative_to(self.root) for p in self.root.rglob('*')})
        self.assertEqual(self.ui.horas.get(), '')

    def test_duracion_invalida_no_pide_confirmacion(self):
        for valor in ('', 'nan', 'inf', '9', '-1', '0', 'texto'):
            self.ui.horas.set(valor)
            self.ui.botones['Iniciar PAPER'].invoke()
        self.ui.dialogos.askyesno.assert_not_called()
        self.assertEqual(self.ui.dialogos.showerror.call_count, 7)
        self.launcher.assert_not_called()

    def test_eleccion_profundidad_visible_y_no_cambia_sesion_activa(self):
        self.assertFalse(self.ui.profundidad.get())
        self.ui.profundidad.set(True)
        self.iniciar_ui()
        self.assertIn('--profundidad-paper', self.launcher.call_args.args[0])
        self.assertIn('profundidad visible FOK', self.ui.dialogos.askyesno.call_args.args[1])
        self.assertTrue(self.ui.selector_fill.instate(['disabled']))
        self.ui.profundidad.set(False)
        self.ui.refrescar()
        self.launcher.assert_called_once()
        self.assertIn('PROFUNDIDAD_VISIBLE_FOK_PAPER_V1', self.ui.estado.get())

    def test_cancelar_inicio_y_reanudar_no_muta(self):
        self.ui.horas.set('1')
        self.ui.botones['Iniciar PAPER'].invoke()
        self.ui.botones['Reanudar entradas'].invoke()
        self.launcher.assert_not_called()
        self.assertTrue(self.stop.exists())
        self.assertTrue(self.pausa.exists())
        for llamada in self.ui.dialogos.askyesno.call_args_list:
            self.assertEqual(llamada.kwargs['default'], 'no')

    def test_inicio_confirmado_doble_clic_y_fin(self):
        self.iniciar_ui()
        self.assertEqual(self.launcher.call_count, 1)
        self.assertIn('0.5', self.launcher.call_args.args[0])
        self.assertTrue(self.ui.botones['Iniciar PAPER'].instate(['disabled']))
        self.ui.botones['Iniciar PAPER'].invoke()
        self.assertEqual(self.launcher.call_count, 1)
        self.hijo.poll.return_value = 1
        self.ui.refrescar()
        self.assertIn('FALLO_TERMINADO', self.ui.estado.get())
        self.assertTrue(self.ui.botones['Iniciar PAPER'].instate(['!disabled']))

    def test_pausa_reanudar_y_parada_explicitas(self):
        self.ui.dialogos.askyesno.return_value = True
        self.ui.botones['Reanudar entradas'].invoke()
        self.assertFalse(self.pausa.exists())
        self.assertTrue(self.stop.exists())
        self.ui.botones['Pausar entradas'].invoke()
        self.assertTrue(self.pausa.exists())
        self.iniciar_ui()
        self.ui.botones['Detener sesión'].invoke()
        self.assertIn('PARADA_SOLICITADA', self.ui.estado.get())
        self.assertTrue((self.root/('DETENER_SESION_'+self.c.sesion_id)).exists())
        self.assertTrue(self.pausa.exists())
        self.hijo.terminate.assert_not_called()

    def test_cerrar_vivo_advierte_y_no_detiene(self):
        self.iniciar_ui()
        self.ui.dialogos.askyesno.return_value = False
        self.ui.cerrar()
        self.assertTrue(self.ventana.winfo_exists())
        self.assertFalse(self.ui.cerrado)
        self.ui.dialogos.askyesno.return_value = True
        self.ui.cerrar()
        self.assertTrue(self.ui.cerrado)
        self.assertIsNone(self.ui.timer)
        self.assertFalse((self.root/('DETENER_SESION_'+self.c.sesion_id)).exists())
        self.hijo.terminate.assert_not_called()
        self.hijo.kill.assert_not_called()

    def test_error_lanzamiento_visible_sin_reintentos(self):
        self.launcher.side_effect = OSError('dato privado no publicar')
        self.iniciar_ui()
        self.ui.dialogos.showerror.assert_called_once()
        self.assertIn('OSError', self.ui.mensaje.get())
        self.assertNotIn('dato privado', self.ui.mensaje.get())
        self.ui.refrescar()
        self.launcher.assert_called_once()
        self.assertTrue(self.stop.exists())

    def test_observacion_incierta_bloquea_y_cerrar_advierte(self):
        self.iniciar_ui()
        self.hijo.poll.side_effect = OSError('fixture')
        self.ui.refrescar()
        self.assertTrue(self.ui.botones['Iniciar PAPER'].instate(['disabled']))
        self.ui.dialogos.askyesno.return_value = False
        self.ui.cerrar()
        self.assertFalse(self.ui.cerrado)

    def test_json_no_crea_controlador_ni_ventana(self):
        with patch('sys.argv', ['panel','--json']), patch.object(panel,'ControlPaper') as clase, \
             patch.object(panel,'abrir_panel') as ventana, redirect_stdout(io.StringIO()):
            # Estado ausente de fixture devuelve2; sigue siendo estrictamente lectura.
            self.assertEqual(panel.main(), 2)
        clase.assert_not_called()
        ventana.assert_not_called()
        self.launcher.assert_not_called()


if __name__ == '__main__':
    unittest.main()
