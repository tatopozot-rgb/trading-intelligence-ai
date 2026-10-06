import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from contextlib import redirect_stdout, closing
from unittest.mock import patch

import config
import paper_store as store
import claude_bridge as bridge
import claude_authorizer as auth
import system_runner as runner
import paper_monitor as monitor
from runner_health import Salud
import threading


class PaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [patch.object(config, 'BASE_DATOS', self.root/'test.db'),
            patch.object(config, 'DIRECTORIO', self.root),
            # Fixture explícito: la política real de halt sigue sin aprobar (None = bloqueo).
            patch.object(config, 'DRAWDOWN_HALT_PCT', 50.0),
            # Sin red: el equity no realizado usa precio inyectado (entrada simulada).
            patch.object(store, '_precio_para_equity', side_effect=lambda simbolo: 100.0),
            patch.object(monitor, 'BASE_DATOS', self.root/'test.db'),
            patch.object(bridge, 'DIRECTORIO', self.root),
            patch.object(bridge, 'RUTA_JSON', self.root/'request.json'),
            patch.object(bridge, 'RUTA_TEXTO', self.root/'request.txt'),
            patch.object(runner, 'ESTADO', self.root/'status.json'),
            patch.object(runner, 'PARADA', self.root/'STOP')]
        for p in self.patches:
            p.start()
        store.inicializar()
        self.plan = {'modo': 'PAPER', 'decision': 'PAPER CANDIDATE', 'simbolo': 'BTCUSDT',
            'comision_paper_pct': .1,
            'entrada': 100., 'stop_precio': 98., 'objetivo_precio': 104.,
            'tamano_posicion': 40., 'riesgo_usd': .88}

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def respuesta(self, plan=None, ejecutable=True):
        plan = plan or self.plan
        identidad, digest = store.registrar_solicitud(plan, ejecutable)
        return {'request_id': identidad, 'plan_hash': digest, 'simbolo': plan['simbolo'],
                'decision': 'APROBAR_PAPER', 'confianza': 80, 'razon': 'Fixture determinista'}

    def abrir(self, respuesta=None):
        r = respuesta or self.respuesta()
        return store.ejecutar_respuesta(r, 'OK '+r['request_id'], 100)

    def test_apertura_cierre_y_repeticion(self):
        r = self.respuesta()
        resultado = self.abrir(r)
        cerrado = store.cerrar(resultado['id'], 104, 'CERRADA_OBJETIVO')
        self.assertTrue(cerrado['cerrada'])
        self.assertAlmostEqual(cerrado['resultado_usd'], 1.5184)
        self.assertAlmostEqual(store.cuenta()['saldo_actual'], 101.5184)
        self.assertFalse(store.cerrar(resultado['id'], 104, 'CERRADA_OBJETIVO')['cerrada'])
        with self.assertRaisesRegex(ValueError, 'consumida'):
            self.abrir(r)

    def test_autorizacion_precio_caducidad(self):
        r = self.respuesta()
        with self.assertRaisesRegex(ValueError, 'autorización'):
            store.ejecutar_respuesta(r, '', 100)
        with self.assertRaisesRegex(ValueError, 'precio cambió'):
            store.ejecutar_respuesta(r, 'OK '+r['request_id'], 102)
        with store.conectar() as con:
            con.execute('UPDATE paper_requests SET expira=?', ((store.ahora()-timedelta(minutes=1)).isoformat(),))
        with self.assertRaisesRegex(ValueError, 'caducada'):
            self.abrir(r)

    def test_prueba_y_rechazo(self):
        r = self.respuesta(ejecutable=False)
        with self.assertRaisesRegex(ValueError, 'prueba'):
            self.abrir(r)
        r['decision'] = 'RECHAZAR'
        self.assertFalse(store.ejecutar_respuesta(r, '')['registrada'])

    def test_hash_simbolo_booleano(self):
        r = self.respuesta()
        for clave, valor in [('plan_hash','otro'), ('simbolo','ETHUSDT'), ('confianza',True), ('confianza',0.92)]:
            otro = {**r, clave: valor}
            with self.assertRaises(ValueError):
                self.abrir(otro)
        with store.conectar() as con:
            con.execute('UPDATE paper_requests SET plan=? WHERE id=?', (store.serializar({**self.plan,'entrada':99}),r['request_id']))
        with self.assertRaisesRegex(ValueError, 'alterada'):
            self.abrir(r)

    def test_concurrencia_doble_apertura(self):
        r = self.respuesta()
        def intento():
            try:
                return self.abrir(r)['registrada']
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(lambda _: intento(), range(2))), 1)

    def test_capital_operacion_limite_y_real(self):
        self.abrir()
        with self.assertRaisesRegex(ValueError, 'símbolo'):
            self.abrir()
        self.abrir(self.respuesta({**self.plan,'simbolo':'ETHUSDT'}))
        with self.assertRaisesRegex(ValueError, 'Capital disponible'):
            self.abrir(self.respuesta({**self.plan,'simbolo':'SOLUSDT'}))
        with patch.object(config, 'USAR_DINERO_REAL', True):
            with self.assertRaisesRegex(ValueError, 'PAPER'):
                self.abrir()

    def test_perdidas_realizadas_limite_diario(self):
        for _ in range(3):
            trade = self.abrir()
            store.cerrar(trade['id'],98,'CERRADA_STOP')
        with self.assertRaisesRegex(ValueError, 'Límite diario'):
            self.abrir()

    def test_movimientos_no_son_pnl(self):
        store.movimiento(900,'aporte')
        store.movimiento(-100,'retiro')
        self.assertEqual(store.cuenta()['saldo_actual'],900)
        self.assertEqual(store.cuenta()['pnl_acumulado'],0)
        with self.assertRaises(ValueError):
            store.movimiento(-1000,'exceso')

    def test_rollback_cierre(self):
        trade = self.abrir()
        with patch.object(store,'evento',side_effect=RuntimeError('fallo')):
            with self.assertRaises(RuntimeError):
                store.cerrar(trade['id'],98,'CERRADA_STOP')
        self.assertEqual(store.cuenta()['saldo_actual'],100)
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT estado FROM paper_trades').fetchone()[0],'ABIERTA')

    def test_monitor_cierra_con_precio_simulado(self):
        self.abrir()
        with patch.object(monitor,'obtener_precio_actual',return_value=98), redirect_stdout(io.StringIO()):
            monitor.revisar_operaciones()
        self.assertLess(store.cuenta()['saldo_actual'],100)

    def test_monitor_reporta_fallo_y_recuperacion(self):
        self.abrir()
        with patch.object(monitor,'obtener_precio_actual',side_effect=ValueError('datos')), redirect_stdout(io.StringIO()):
            fallido = monitor.revisar_operaciones()
        self.assertEqual(fallido['errores'],1)
        self.assertEqual(fallido['cerradas'],0)
        with patch.object(monitor,'obtener_precio_actual',return_value=104), redirect_stdout(io.StringIO()):
            recuperado = monitor.revisar_operaciones()
        self.assertEqual(recuperado['errores'],0)
        self.assertEqual(recuperado['cerradas'],1)

    def test_salud_monitor_con_fallo_y_exito(self):
        detener = threading.Event()
        salud = Salud()
        llamadas = [0]
        def revisar():
            llamadas[0] += 1
            if llamadas[0] == 1:
                raise ValueError('fallo temporal')
            detener.set()
            return {'errores':0,'revisadas':1,'cerradas':0}
        with patch.object(runner,'revisar_operaciones',side_effect=revisar):
            runner.monitor_continuo(detener,.001,salud)
        estado = salud.snapshot()['monitor']
        self.assertEqual(estado['estado'],'OK')
        self.assertEqual(estado['errores_total'],1)
        self.assertEqual(estado['ciclos'],2)

    def test_plan_reutilizado_autorizacion_manual(self):
        r = self.respuesta()
        with patch.object(auth,'obtener_precio_actual',return_value=100) as precio, redirect_stdout(io.StringIO()):
            self.assertFalse(auth.procesar(r, confirmar=lambda _: 'NO')['registrada'])
            precio.assert_not_called()
            self.assertTrue(auth.procesar(r, confirmar=lambda _: 'OK '+r['request_id'])['registrada'])
            precio.assert_called_once()

    def test_bridge_prueba_siempre_no_ejecutable(self):
        datos = {'plan': self.plan, 'analisis': {'temporalidades': {'1h': {'tendencia':'ALCISTA','rsi':50,'atr_pct':2}}}}
        bridge.crear_solicitud_claude([datos], True)
        paquete = json.loads(bridge.RUTA_JSON.read_text(encoding='utf-8'))
        self.assertFalse(paquete['solicitudes'][0]['ejecutable'])
        bridge.crear_solicitud_claude([],False)
        self.assertEqual(json.loads(bridge.RUTA_JSON.read_text(encoding='utf-8'))['solicitudes'],[])

    def test_cancelacion_antes_de_scanner_no_consulta(self):
        with patch.object(runner,'ejecutar_scanner') as scanner:
            resultado = runner.escanear(sesion_activa=lambda:False)
        scanner.assert_not_called()
        self.assertTrue(resultado['cancelado'])
        self.assertIsNone(resultado['solicitud'])

    def test_fin_durante_consulta_no_genera_solicitud(self):
        activa = [True]
        def consultar():
            activa[0] = False
            return [{'plan':self.plan}]
        with patch.object(runner,'ejecutar_scanner',side_effect=consultar):
            resultado = runner.escanear(sesion_activa=lambda:activa[0])
        self.assertTrue(resultado['cancelado'])
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_requests').fetchone()[0],0)
        self.assertFalse(bridge.RUTA_JSON.exists())

    def test_fin_en_transaccion_revierte_solicitud_y_evento(self):
        activa = [True]
        evento_original = store.evento
        def evento(con,tipo,datos):
            evento_original(con,tipo,datos)
            if tipo=='SOLICITUD':
                activa[0] = False
        with patch.object(store,'evento',side_effect=evento):
            with self.assertRaises(store.SesionFinalizada):
                store.registrar_solicitud(self.plan,True,lambda:activa[0])
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_requests').fetchone()[0],0)
            self.assertEqual(con.execute("SELECT count(*) FROM paper_events WHERE tipo='SOLICITUD'").fetchone()[0],0)

    def test_fin_tras_confirmacion_conserva_registro_sin_exportar(self):
        activa = [True]
        registrar_original = store.registrar_solicitud
        def registrar(*args):
            resultado = registrar_original(*args)
            activa[0] = False
            return resultado
        datos = {'plan':self.plan,'analisis':{'temporalidades':{'1h':{'tendencia':'ALCISTA','rsi':50,'atr_pct':2}}}}
        with patch.object(store,'registrar_solicitud',side_effect=registrar):
            with self.assertRaises(store.SesionFinalizada):
                bridge.crear_solicitud_claude([datos],sesion_activa=lambda:activa[0])
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_requests').fetchone()[0],1)
        self.assertFalse(bridge.RUTA_JSON.exists())

    def test_ciclo_unico_sin_predicado_sigue_exportando(self):
        datos = {'plan':self.plan,'analisis':{'temporalidades':{'1h':{'tendencia':'ALCISTA','rsi':50,'atr_pct':2}}}}
        with patch.object(runner,'ejecutar_scanner',return_value=[datos]):
            resultado = runner.escanear()
        self.assertFalse(resultado['cancelado'])
        self.assertEqual(resultado['solicitud']['cantidad'],1)

    def test_cancelacion_no_se_confunde_con_exito_en_salud(self):
        salud = Salud()
        salud.terminar('scanner',{'errores':0,'cancelado':True})
        estado = salud.snapshot()['scanner']
        self.assertEqual(estado['estado'],'CANCELADO')
        self.assertNotIn('ultimo_exito_utc',estado)

    def test_runner_monitor_independiente_y_final(self):
        llamadas=[]
        def fallo(**kwargs):
            time.sleep(.12)
            raise ValueError('caída del scanner')
        with patch.object(runner,'preparar'), patch.object(runner,'escanear',side_effect=fallo), \
             patch.object(runner,'revisar_operaciones',side_effect=lambda: llamadas.append(time.monotonic())):
            runner.ejecutar_continuo(horas=.00012, intervalo_scanner=.03, intervalo_monitor=.04)
        self.assertGreater(len(llamadas),2)
        self.assertEqual(json.loads(runner.ESTADO.read_text())['estado'],'DETENIDO')
        self.assertEqual(json.loads(runner.ESTADO.read_text())['salud']['scanner']['estado'],'ERROR')

    def test_instancia_unica(self):
        with runner.instancia_unica():
            with self.assertRaises(RuntimeError):
                with runner.instancia_unica():
                    pass

    def test_stop_durante_scanner_y_salud_final(self):
        def escaneo(**kwargs):
            runner.PARADA.touch()
            return {'analizados':1,'errores':0,'solicitud':None}
        with patch.object(runner,'preparar'),patch.object(runner,'escanear',side_effect=escaneo), \
             patch.object(runner,'revisar_operaciones',return_value={'revisadas':0,'cerradas':0,'errores':0}):
            runner.ejecutar_continuo(horas=.0002,intervalo_scanner=.05,intervalo_monitor=.02)
        estado = json.loads(runner.ESTADO.read_text())
        self.assertEqual(estado['estado'],'DETENIDO')
        self.assertFalse(estado['monitor_vivo'])
        self.assertEqual(estado['salud']['scanner']['estado'],'OK')
        self.assertEqual(estado['salud']['scanner']['ciclos'],1)

    def test_intervalos_no_finitos_rechazados(self):
        for valor in (float('nan'),float('inf'),0,-1):
            with self.assertRaisesRegex(ValueError,'Intervalos'):
                runner.ejecutar_continuo(intervalo_scanner=valor)

    def test_comision_congelada_desde_propuesta_hasta_cierre(self):
        r = self.respuesta()
        with patch.object(config, 'COMISION_PAPER_PCT', .5):
            trade = self.abrir(r)
        with patch.object(config, 'COMISION_PAPER_PCT', 2):
            cerrado = store.cerrar(trade['id'],104,'CERRADA_OBJETIVO')
        self.assertAlmostEqual(cerrado['resultado_usd'],1.5184)
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT comision_pct_apertura FROM paper_trades').fetchone()[0],.1)

    def test_caducidad_durable_idempotente_y_limite_exacto(self):
        r = self.respuesta()
        fecha = store.ahora()
        with store.conectar() as con:
            con.execute('UPDATE paper_requests SET expira=? WHERE id=?',(fecha.isoformat(),r['request_id']))
        with patch.object(store,'ahora',return_value=fecha):
            with self.assertRaisesRegex(ValueError,'caducada'):
                self.abrir(r)
            self.assertEqual(store.caducar_solicitudes(),0)
        self.assertEqual(store.leer_solicitud(r['request_id'])['estado'],'CADUCADA')
        with store.conectar() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM paper_events WHERE tipo='SOLICITUD_CADUCADA'").fetchone()[0],1)
            self.assertEqual(store.resumen(con)['n'],0)

    def test_rechazo_de_validacion_auditado_sin_consumir_plan(self):
        r = self.respuesta()
        with self.assertRaises(ValueError):
            auth.procesar({**r,'confianza':.92})
        self.assertEqual(store.leer_solicitud(r['request_id'])['estado'],'PENDIENTE')
        with store.conectar() as con:
            evento = con.execute("SELECT datos FROM paper_events WHERE tipo='VALIDACION_RECHAZADA'").fetchone()
            self.assertEqual(json.loads(evento[0])['request_id'],r['request_id'])

    def test_json_externo_estricto_y_auditable(self):
        archivo = self.root/'invalido.json'
        for contenido in ('{"respuestas":[],"respuestas":[]}', '{"respuestas":[NaN]}',
                          '{"respuestas":[]}', 'x'*100001):
            archivo.write_text(contenido,encoding='utf-8')
            with self.assertRaises(ValueError):
                auth.procesar_archivo(archivo)
        with store.conectar() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM paper_events WHERE tipo='VALIDACION_RECHAZADA'").fetchone()[0],4)

    def test_rollback_estado_caducidad(self):
        r = self.respuesta()
        with store.conectar() as con:
            con.execute('UPDATE paper_requests SET expira=?',((store.ahora()-timedelta(minutes=1)).isoformat(),))
        with patch.object(store,'evento',side_effect=RuntimeError('disco')):
            with self.assertRaises(RuntimeError):
                store.caducar_solicitudes()
        self.assertEqual(store.leer_solicitud(r['request_id'])['estado'],'PENDIENTE')

    def test_comision_desconocida_no_se_inventa(self):
        for tarifa in (None, True, -1, float('nan'),float('inf'),100):
            with self.subTest(tarifa=tarifa), self.assertRaisesRegex(ValueError,'Comisión'):
                self.respuesta({**self.plan,'comision_paper_pct':tarifa})
        trade = self.abrir()
        with store.conectar() as con:
            con.execute('UPDATE paper_trades SET comision_pct_apertura=NULL WHERE id=?',(trade['id'],))
        with self.assertRaisesRegex(ValueError,'histórica'):
            store.cerrar(trade['id'],104,'CERRADA_OBJETIVO')
        self.assertEqual(store.cuenta()['saldo_actual'],100)

    def test_migracion_tarifa_nula_idempotente(self):
        import sqlite3
        antigua = self.root/'antigua.db'
        with closing(sqlite3.connect(antigua)) as con:
            con.executescript('''CREATE TABLE paper_trades (
              id INTEGER PRIMARY KEY AUTOINCREMENT, simbolo TEXT NOT NULL,
              fecha_apertura TEXT NOT NULL, estado TEXT NOT NULL, entrada REAL NOT NULL,
              stop_precio REAL NOT NULL, objetivo_precio REAL NOT NULL,
              tamano_posicion REAL NOT NULL, riesgo_usd REAL NOT NULL,
              precio_salida REAL, fecha_cierre TEXT, resultado_usd REAL, resultado_pct REAL);
              INSERT INTO paper_trades VALUES(1,'BTCUSDT','2026-09-20','ABIERTA',100,98,104,40,.88,NULL,NULL,NULL,NULL);''')
        with patch.object(config,'BASE_DATOS',antigua):
            store.inicializar()
            store.inicializar()
            with store.conectar() as con:
                self.assertIsNone(con.execute('SELECT comision_pct_apertura FROM paper_trades').fetchone()[0])
                self.assertEqual(con.execute("SELECT count(*) FROM paper_events WHERE tipo='MIGRACION_COMISION'").fetchone()[0],1)
            with self.assertRaisesRegex(ValueError,'Comisión'):
                store.cerrar(1,104,'CERRADA_OBJETIVO')

    def test_auto_sesion_revalidada_despues_de_cotizar(self):
        r = self.respuesta()
        activa = [True]
        def cotizar(_):
            activa[0] = False
            return 100
        with patch.object(auth, 'obtener_precio_actual', side_effect=cotizar):
            with self.assertRaisesRegex(ValueError, 'Sesión automática'):
                auth.procesar(r, automatico=True, sesion_activa=lambda: activa[0])
        self.assertEqual(store.leer_solicitud(r['request_id'])['estado'], 'PENDIENTE')
        with store.conectar() as con:
            self.assertEqual(store.resumen(con)['n'], 0)

    def test_auto_requiere_sesion_y_funciona_con_sesion(self):
        r = self.respuesta()
        with patch.object(auth, 'obtener_precio_actual', return_value=100) as cotizar:
            with self.assertRaisesRegex(ValueError, 'Sesión automática'):
                auth.procesar(r, automatico=True)
            cotizar.assert_not_called()
            self.assertTrue(auth.procesar(r, automatico=True, sesion_activa=lambda: True)['registrada'])

    def test_limites_riesgo_y_numero(self):
        with self.assertRaisesRegex(ValueError, 'riesgo por operación'):
            self.abrir(self.respuesta({**self.plan, 'tamano_posicion': 50}))
        for simbolo in ('BTCUSDT', 'ETHUSDT', 'SOLUSDT'):
            self.abrir(self.respuesta({**self.plan, 'simbolo': simbolo, 'tamano_posicion': 10}))
        with self.assertRaisesRegex(ValueError, 'Máximo'):
            self.abrir(self.respuesta({**self.plan, 'simbolo': 'AVAXUSDT', 'tamano_posicion': 10}))


if __name__ == '__main__':
    unittest.main()
