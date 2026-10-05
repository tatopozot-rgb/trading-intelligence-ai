import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

import config
import paper_dashboard as panel
import paper_store as store


class DashboardTests(unittest.TestCase):
    def setUp(self):
        from test_paper_system import PaperTests
        PaperTests.setUp(self)
        self.addCleanup(lambda: PaperTests.tearDown(self))
        self.base = config.BASE_DATOS
        (self.root/'runner_status.json').write_text(json.dumps({
            'modo': 'PAPER', 'estado': 'ACTIVO', 'fecha': '2000-01-01T00:00:00Z'}), encoding='utf-8')
        self.red = self.enterContext(patch('requests.sessions.Session.request', side_effect=AssertionError('RED')))
        self.proceso = self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('PROCESO')))
        self.addCleanup(self.red.assert_not_called)
        self.addCleanup(self.proceso.assert_not_called)

    def leer(self):
        return panel.snapshot(self.root, self.base)

    def test_lectura_sin_mutacion_ni_inicializacion(self):
        antes = hashlib.sha256(self.base.read_bytes()).digest()
        with patch.object(store, 'inicializar', side_effect=AssertionError('MIGRACION')):
            dato = self.leer()
        self.assertEqual(dato['cuenta']['saldo_actual'], 100)
        self.assertEqual(dato['errores'], [])
        self.assertEqual(hashlib.sha256(self.base.read_bytes()).digest(), antes)
        self.assertTrue(dato['solo_lectura'])

    def test_sql_solo_lectura_y_unica_transaccion(self):
        conectar = sqlite3.connect
        sentencias = []
        def vigilada(*args, **kwargs):
            self.assertTrue(args[0].endswith('?mode=ro'))
            con = conectar(*args, **kwargs)
            con.set_trace_callback(sentencias.append)
            return con
        with patch.object(panel.sqlite3, 'connect', side_effect=vigilada):
            self.leer()
        self.assertEqual(sentencias.count('BEGIN'), 1)
        self.assertIn('PRAGMA query_only=ON', sentencias)
        self.assertTrue(all(s.startswith(('SELECT', 'PRAGMA query_only=ON', 'BEGIN')) for s in sentencias))

    def test_base_ausente_no_se_crea(self):
        self.base = self.root/'ausente.db'
        dato = self.leer()
        self.assertIsNone(dato['cuenta'])
        self.assertFalse(self.base.exists())
        self.assertIn('BD_NO_VERIFICADA', dato['errores'][0])

    def test_estado_faltante_corrupto_tipo_y_modo(self):
        ruta = self.root/'runner_status.json'
        for contenido in ('{', '[]', '{"modo":"REAL"}', 'x'*262145):
            ruta.write_text(contenido, encoding='utf-8')
            dato = self.leer()
            self.assertIsNone(dato['runner'])
            self.assertTrue(any('ESTADO_NO_VERIFICADO' in e for e in dato['errores']))
        ruta.unlink()
        self.assertIsNone(self.leer()['runner'])

    def test_no_declara_vivo_y_senales_no_son_confirmacion(self):
        (self.root/'DETENER_RUNNER').touch()
        (self.root/'PAUSA_ENTRADAS').touch()
        dato = self.leer()
        texto = panel.presentar(dato)['Resumen']
        self.assertIn('Proceso vivo: NO VERIFICADO', texto)
        self.assertIn('2000-01-01', texto)
        self.assertTrue(dato['pausa_solicitada'])
        self.assertTrue(dato['parada_solicitada'])

    def test_no_paper_no_lee_base(self):
        for nombre, valor in (('MODO', 'REAL'), ('USAR_DINERO_REAL', True)):
            with patch.object(config, nombre, valor), patch.object(panel.sqlite3, 'connect') as conectar:
                dato = self.leer()
                conectar.assert_not_called()
                self.assertIn('CONFIGURACION_NO_PAPER', dato['errores'][0])

    def test_fallo_no_publica_instantanea_parcial_o_anterior(self):
        self.assertIsNotNone(self.leer()['cuenta'])
        with store.conectar() as con:
            con.execute('DROP TABLE paper_events')
        dato = self.leer()
        self.assertIsNone(dato['cuenta'])
        self.assertEqual(dato['posiciones'], [])
        self.assertIn('Saldo NO VERIFICADO', panel.presentar(dato)['Resumen'])

    def test_registros_acotados_y_historicos_no_autorizan(self):
        store.registrar_solicitud(self.plan, False)
        with store.conectar() as con:
            for numero in range(105):
                store.evento(con, 'PRUEBA', {'numero': numero})
        dato = self.leer()
        self.assertEqual(len(dato['eventos']), 100)
        self.assertEqual(json.loads(dato['eventos'][0]['datos'])['numero'], 104)
        self.assertEqual(dato['solicitudes'][0]['ejecutable'], 0)
        self.assertEqual(dato['posiciones'], [])

    def test_ventana_oculta_actualizar_y_cerrar_sin_runner(self):
        import tkinter as tk
        from tkinter import ttk
        original = tk.Tk
        ventanas = []
        store.registrar_solicitud(self.plan, False)
        primero = self.leer()
        segundo = {**primero, 'cuenta': None, 'solicitudes': [], 'posiciones': [], 'eventos': [],
                   'errores': ['BD_NO_VERIFICADA: prueba']}
        def oculta():
            ventana = original()
            ventana.withdraw()
            ventanas.append(ventana)
            return ventana
        def probar(ventana):
            ventana.update_idletasks()
            notebook = next(w for w in ventana.winfo_children() if isinstance(w, ttk.Notebook))
            tablas = []
            for marco in notebook.winfo_children():
                for hijo in marco.winfo_children():
                    tablas.extend(w for w in hijo.winfo_children() if isinstance(w, ttk.Treeview))
            self.assertEqual(len(tablas), 3)
            solicitudes = tablas[1]
            self.assertEqual(len(solicitudes.get_children()), 1)
            solicitudes.selection_set('0')
            ventana.update()
            marco = notebook.winfo_children()[2]
            detalle = next(w for h in marco.winfo_children() for w in h.winfo_children() if isinstance(w, tk.Text))
            self.assertIn('BTCUSDT', detalle.get('1.0', 'end'))
            acciones = ventana.winfo_children()[-1]
            botones = [w for w in acciones.winfo_children() if isinstance(w, ttk.Button)]
            self.assertEqual([b.cget('text') for b in botones], ['Actualizar lectura', 'Cerrar observador'])
            botones[0].invoke()
            ventana.update()
            self.assertFalse(solicitudes.get_children())
            self.assertNotIn('BTCUSDT', detalle.get('1.0', 'end'))
            botones[1].invoke()
        try:
            with patch.object(tk, 'Tk', side_effect=oculta), patch.object(tk.Misc, 'mainloop', probar), \
                    patch.object(panel, 'snapshot', side_effect=[primero, segundo]) as leer:
                panel.abrir_panel()
                self.assertEqual(leer.call_count, 2)
        finally:
            for ventana in ventanas:
                try:
                    ventana.destroy()
                except tk.TclError:
                    pass

    def test_fecha_latido_activo_y_fecha_final(self):
        dato = self.leer()
        dato['runner'] = {'modo': 'PAPER', 'estado': 'ACTIVO', 'heartbeat_utc': '2026-09-23T03:00:00Z'}
        self.assertIn('Fecha del estado: 2026-09-23T03:00:00Z', panel.presentar(dato)['Resumen'])
        dato['runner'] = {'modo': 'PAPER', 'estado': 'DETENIDO', 'fecha': '2026-09-23T04:00:00Z'}
        self.assertIn('Fecha del estado: 2026-09-23T04:00:00Z', panel.presentar(dato)['Resumen'])

    def test_numeros_no_inventados_ni_redondeados_a_cero(self):
        for valor in (None, True, '100', float('nan'), float('inf')):
            self.assertEqual(panel.numero_visible(valor), 'NO VERIFICADO')
        self.assertEqual(float(panel.numero_visible(.00000001)), .00000001)
        self.assertEqual(panel.numero_visible(0), '0')

    def test_tablas_plan_invalido_y_origen(self):
        dato = self.leer()
        for plan in ('{', '[]', 'null'):
            dato['solicitudes'] = [{'plan': plan, 'ejecutable': 0}]
            self.assertEqual(panel.tablas(dato)['Solicitudes históricas'][0][1], 'PLAN INVÁLIDO')
        dato['solicitudes'] = [{'plan': json.dumps({'simbolo':'BTCUSDT','origen_revision':'REGLAS_PAPER_V1'}), 'ejecutable': 1}]
        fila = panel.tablas(dato)['Solicitudes históricas'][0]
        self.assertEqual(fila[3], 'REGLAS_PAPER_V1')
        self.assertIn('no es autorización', fila[4])

    def test_columnas_y_posicion_preservan_valores(self):
        dato = self.leer()
        dato['posiciones'] = [{'id': 1, 'simbolo': 'BTCUSDT', 'entrada': 10., 'stop_precio': 9.,
                             'objetivo_precio': 12., 'tamano_posicion': 20., 'riesgo_usd': .5,
                             'fecha_apertura': 'fecha_fixture'}]
        salida = panel.tablas(dato)
        self.assertEqual(salida['Posiciones abiertas'][0], (1, 'BTCUSDT', '10.0', '9.0', '12.0', '20.0', '0.5', 'fecha_fixture'))
        for nombre, filas in salida.items():
            for fila in filas:
                self.assertEqual(len(fila), len(panel.COLUMNAS[nombre]))


if __name__ == '__main__':
    unittest.main()
