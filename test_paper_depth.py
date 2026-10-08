"""Integración profundidad: SQLite temporal, ninguna consulta remota real."""
import copy
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import config
import paper_fills as fills
import paper_store as store
import paper_monitor as monitor
import paper_rules as rules
import paper_report


class DepthTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix='paper-depth-test-')
        self.addCleanup(temporal.cleanup)
        self.root = Path(temporal.name)
        self.t = datetime(2026,9,28,12,tzinfo=timezone.utc)
        for p in (patch.object(config, 'BASE_DATOS', self.root/'test.db'),
                  patch.object(config, 'DIRECTORIO', self.root),
                  patch.object(monitor, 'BASE_DATOS', self.root/'test.db'),
                  patch.object(store, 'ahora', return_value=self.t),
                  patch.object(config, 'DRAWDOWN_HALT_PCT', 50.0), patch.object(config, 'DRAWDOWN_PAUSE_PCT', None),
                  patch.object(store, '_precio_para_equity', side_effect=lambda simbolo: 100.0),
                  patch('requests.sessions.Session.request', side_effect=AssertionError('Red prohibida'))):
            p.start(); self.addCleanup(p.stop)
        store.inicializar()
        self.plan = dict(modo='PAPER', decision='PAPER CANDIDATE', simbolo='BTCUSDT',
                         entrada=100., stop_precio=98., objetivo_precio=104., tamano_posicion=40.,
                         riesgo_usd=.88, comision_paper_pct=.1, consenso='ALCISTA',
                         estado='ALCISTA MOMENTUM SANO', origen_revision='REGLAS_PAPER_V1',
                         modelo_fill_paper=fills.MODELO)

    def libro(self, *, bid='99.9', ask='100.1', cantidad='10'):
        t = int(self.t.timestamp()*1000)
        return dict(fuente='FIXTURE', simbolo='BTCUSDT', solicitado_ms=t-200, recibido_ms=t-100,
                    libro=dict(lastUpdateId=42,bids=[[bid,cantidad]], asks=[[ask,cantidad]]))

    def evidencia(self, snapshot=None, lado='BUY', monto=40):
        return fills.evidencia(snapshot or self.libro(), lado=lado, monto=monto, comision_pct=.1,
                               ahora_ms=int(self.t.timestamp()*1000))

    def abrir(self, e=None):
        e = e or self.evidencia()
        return store.ejecutar_reglas(*store.registrar_solicitud(self.plan, True),
                                    float(e['resultado']['precio_medio']), lambda:True, evidencia_fill=e)

    def test_reglas_y_monitor_persisten_modelo_y_evidencia(self):
        with patch.object(fills, 'cotizar', return_value=self.libro()):
            r = rules.procesar_candidatos([{'plan':self.plan}], lambda:True, profundidad=True)
        self.assertTrue(r[0]['registrada'])
        with store.conectar() as con:
            e = json.loads(con.execute("SELECT datos FROM paper_events WHERE tipo='APERTURA'").fetchone()[0])
        self.assertEqual(e['evidencia_fill']['resultado']['estado'], 'COMPLETO')
        # Nueva llamada simula reinicio: modelo viene del plan, sin flag monitor.
        with patch.object(fills, 'cotizar', return_value=self.libro(bid='104.1',ask='104.2')), \
             patch.object(monitor, 'obtener_precio_actual', side_effect=AssertionError('No degradar')), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(monitor.revisar_operaciones()['cerradas'], 1)
        self.assertEqual(paper_report.informe()['estado'], 'OK')
        with store.conectar() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM paper_events WHERE tipo='CIERRE'").fetchone()[0], 1)
        self.assertFalse(store.cerrar(r[0]['id'],104.1,'CERRADA_OBJETIVO')['cerrada'])

    def test_modelo_exige_evidencia_y_rechaza_parcial(self):
        solicitud = store.registrar_solicitud(self.plan, True)
        with self.assertRaises(ValueError): store.ejecutar_reglas(*solicitud,100.1,lambda:True)
        e = self.evidencia(self.libro(cantidad='.01'))
        with self.assertRaisesRegex(ValueError, 'incompleto'):
            store.ejecutar_reglas(*solicitud,100.1,lambda:True,evidencia_fill=e)
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_trades').fetchone()[0],0)
        self.assertEqual(store.leer_solicitud(solicitud[0])['estado'],'PENDIENTE')

    def test_no_cierra_depth_con_ticker_o_evidencia_manipulada(self):
        r = self.abrir()
        with self.assertRaises(ValueError): store.cerrar(r['id'],97,'CERRADA_STOP')
        e = self.evidencia(self.libro(bid='97',ask='97.1'), 'SELL', 40/100.1)
        e['resultado']['comision_quote']='0'
        with self.assertRaises(ValueError): store.cerrar(r['id'],97,'CERRADA_STOP',evidencia_fill=e)
        self.assertEqual(store.cuenta()['saldo_actual'],100)

    def test_rechazo_de_caducidad_antes_commit_revierte_todo(self):
        e = self.evidencia(); evento = store.evento
        def lento(con,tipo,datos):
            evento(con,tipo,datos)
            if tipo=='APERTURA':
                store.ahora.return_value = datetime(2026,9,28,12,0,10,tzinfo=timezone.utc)
        with patch.object(store, 'evento', side_effect=lento), self.assertRaisesRegex(ValueError,'antiguo'):
            self.abrir(e)
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_trades').fetchone()[0],0)
            self.assertEqual(con.execute("SELECT count(*) FROM paper_events WHERE tipo='APERTURA'").fetchone()[0],0)

    def test_parcial_salida_deja_posicion_y_alerta(self):
        self.abrir()
        with patch.object(fills,'cotizar',return_value=self.libro(bid='97',ask='97.1',cantidad='.001')), \
             redirect_stdout(io.StringIO()), self.assertLogs(level='ERROR'):
            r = monitor.revisar_operaciones()
        self.assertEqual((r['cerradas'],r['errores']), (0,1))
        with store.conectar() as con: self.assertEqual(store.resumen(con)['n'],1)

    def test_informe_historico_recalcula_evidencia_sin_edad_actual(self):
        self.abrir()
        store.ahora.return_value = datetime(2026,10,1,tzinfo=timezone.utc)
        self.assertEqual(paper_report.informe()['estado'],'OK')
        with store.conectar() as con:
            row = con.execute("SELECT id,datos FROM paper_events WHERE tipo='APERTURA'").fetchone()
            d = json.loads(row['datos']); d.pop('evidencia_fill')
            con.execute('UPDATE paper_events SET datos=? WHERE id=?',(store.serializar(d),row['id']))
        self.assertIn('EVIDENCIA_FILL_INVALIDA_BUY', [p['codigo'] for p in paper_report.informe()['problemas']])

    def test_cierre_exacto_usa_toda_la_base_original_y_fees_una_vez(self):
        for precio in ('100.3', '100.1'):
            with self.subTest(precio=precio):
                self.plan['entrada'] = float(precio)
                compra = self.evidencia(self.libro(bid='100', ask=precio))
                trade = self.abrir(compra)
                cantidad = compra['resultado']['base_ejecutada']
                # La liquidez coincide exactamente con la compra Decimal, no con nominal/VWAP float.
                with patch.object(fills, 'cotizar', return_value=self.libro(
                        bid='104.1', ask='104.2', cantidad=cantidad)), redirect_stdout(io.StringIO()):
                    revision = monitor.revisar_operaciones()
                self.assertEqual((revision['cerradas'], revision['errores']), (1, 0))
                with store.conectar() as con:
                    evento = con.execute("SELECT datos FROM paper_events WHERE tipo='CIERRE' "
                                         "AND json_extract(datos,'$.id')=?", (trade['id'],)).fetchone()
                    datos = json.loads(evento['datos'])
                    fila = con.execute('SELECT * FROM paper_trades WHERE id=?', (trade['id'],)).fetchone()
                venta = datos['evidencia_fill']
                self.assertEqual(venta['parametros']['monto'], cantidad)
                self.assertEqual(venta['resultado']['base_ejecutada'], cantidad)
                self.assertEqual(Decimal(venta['resultado']['restante']), 0)
                with localcontext() as contexto:
                    contexto.prec = 100
                    ingreso = Decimal(venta['resultado']['quote_ejecutado'])
                    comisiones = Decimal(compra['resultado']['comision_quote']) + Decimal(venta['resultado']['comision_quote'])
                    esperado = ingreso-Decimal(40)-comisiones
                self.assertEqual(fila['resultado_usd'], float(esperado))
                self.assertEqual(datos['comisiones_estimadas'], float(comisiones))
                self.assertEqual(paper_report.informe()['estado'], 'OK')

    def cierre_con_apertura_danada(self, tipo):
        compra = self.evidencia()
        trade = self.abrir(compra)
        venta = self.evidencia(self.libro(bid='104.1', ask='104.2'),
                               'SELL', compra['resultado']['base_ejecutada'])
        with store.conectar() as con:
            fila = con.execute("SELECT * FROM paper_events WHERE tipo='APERTURA'").fetchone()
            if tipo == 'ausente':
                con.execute('DELETE FROM paper_events WHERE id=?', (fila['id'],))
            elif tipo == 'duplicada':
                con.execute('INSERT INTO paper_events(fecha,tipo,datos) VALUES (?,?,?)',
                            (fila['fecha'], fila['tipo'], fila['datos']))
            else:
                dato = json.loads(fila['datos'])
                dato['evidencia_fill']['resultado']['base_ejecutada'] = '999'
                con.execute('UPDATE paper_events SET datos=? WHERE id=?', (store.serializar(dato), fila['id']))
        with self.assertRaises(ValueError):
            store.cerrar(trade['id'], 104.1, 'CERRADA_OBJETIVO', evidencia_fill=venta)
        self.assertEqual(store.cuenta()['saldo_actual'], 100)
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT estado FROM paper_trades').fetchone()[0], 'ABIERTA')
            self.assertEqual(con.execute("SELECT count(*) FROM paper_events WHERE tipo='CIERRE'").fetchone()[0], 0)
        self.assertEqual(paper_report.informe()['estado'], 'DISCREPANCIA')

    def test_apertura_ausente_impide_cierre_sin_inventar_base(self):
        self.cierre_con_apertura_danada('ausente')

    def test_apertura_duplicada_impide_cierre_sin_elegir_una(self):
        self.cierre_con_apertura_danada('duplicada')

    def test_apertura_alterada_impide_cierre(self):
        self.cierre_con_apertura_danada('alterada')

    def test_cero_de_exponente_grande_se_canoniza_antes_de_formatear(self):
        self.assertEqual(fills.texto(fills.decimal('0e-10000', cero=True)), '0')
        e = fills.evidencia(self.libro(), lado='BUY', monto=40,
                            comision_pct='0e-10000', ahora_ms=int(self.t.timestamp()*1000))
        self.assertEqual(e['parametros']['comision_pct'], '0')
        self.assertEqual(Decimal(e['resultado']['comision_quote']), 0)

    def test_comision_historica_desconocida_se_rechaza_antes_de_solicitud(self):
        with store.conectar() as con:
            con.execute("INSERT INTO paper_trades(simbolo,fecha_apertura,estado,entrada,stop_precio,"
                        "objetivo_precio,tamano_posicion,riesgo_usd) VALUES "
                        "('BTCUSDT',?,'ABIERTA',100,98,104,40,.88)", (self.t.isoformat(),))
        with self.assertRaisesRegex(ValueError, 'Comisión'):
            store.cerrar(1, 104, 'CERRADA_OBJETIVO')

    def test_caducidad_durante_cierre_revierte_saldo_y_evento(self):
        compra = self.evidencia()
        trade = self.abrir(compra)
        venta = self.evidencia(self.libro(bid='104.1', ask='104.2'),
                               'SELL', compra['resultado']['base_ejecutada'])
        evento = store.evento
        def lento(con, tipo, datos):
            evento(con, tipo, datos)
            if tipo == 'CIERRE':
                store.ahora.return_value = datetime(2026, 9, 28, 12, 0, 10, tzinfo=timezone.utc)
        with patch.object(store, 'evento', side_effect=lento), self.assertRaisesRegex(ValueError, 'antiguo'):
            store.cerrar(trade['id'], 104.1, 'CERRADA_OBJETIVO', evidencia_fill=venta)
        self.assertEqual(store.cuenta()['saldo_actual'], 100)
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT estado FROM paper_trades').fetchone()[0], 'ABIERTA')
            self.assertEqual(con.execute("SELECT count(*) FROM paper_events WHERE tipo='CIERRE'").fetchone()[0], 0)

    def test_reinicio_dias_despues_conserva_compra_y_usa_libro_nuevo(self):
        compra = self.evidencia()
        self.abrir(compra)
        self.t = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        store.ahora.return_value = self.t
        with patch.object(fills, 'cotizar', return_value=self.libro(bid='104.1', ask='104.2',
                cantidad=compra['resultado']['base_ejecutada'])), redirect_stdout(io.StringIO()):
            r = monitor.revisar_operaciones()
        self.assertEqual((r['cerradas'],r['errores']), (1,0))
        self.assertEqual(paper_report.informe()['estado'], 'OK')


if __name__ == '__main__': unittest.main()
