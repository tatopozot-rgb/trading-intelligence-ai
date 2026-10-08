import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import config
import paper_store as store
from paper_report import informe


class InformeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name)/'paper.db'
        self.patches = [patch.object(config,'BASE_DATOS',self.ruta),patch.object(config,'DIRECTORIO',Path(self.tmp.name)),
            patch.object(config,'DRAWDOWN_HALT_PCT',50.0), patch.object(config, 'DRAWDOWN_PAUSE_PCT', None),
            patch.object(store,'_precio_para_equity',side_effect=lambda simbolo: 100.0)]
        for p in self.patches:
            p.start()
        store.inicializar()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def abrir(self):
        plan = {'modo':'PAPER','decision':'PAPER CANDIDATE','simbolo':'BTCUSDT',
            'entrada':100.,'stop_precio':98.,'objetivo_precio':104.,'tamano_posicion':40.,'comision_paper_pct':.1}
        identidad,digest = store.registrar_solicitud(plan,True)
        r = {'request_id':identidad,'plan_hash':digest,'simbolo':'BTCUSDT','decision':'APROBAR_PAPER','confianza':80,'razon':'Prueba'}
        return store.ejecutar_respuesta(r,'OK '+identidad,100)['id']

    def codigos(self):
        return {p['codigo'] for p in informe()['problemas']}

    def test_base_sana_y_sin_escrituras(self):
        identidad = self.abrir()
        self.assertEqual(informe()['estado'],'OK')
        store.cerrar(identidad,104,'CERRADA_OBJETIVO')
        store.movimiento(50,'aporte simulado')
        store.movimiento(-20,'retiro simulado')
        antes = (hashlib.sha256(self.ruta.read_bytes()).hexdigest(),self.ruta.stat().st_mtime_ns)
        uno,dos = informe(),informe()
        self.assertEqual(uno,dos)
        self.assertEqual(uno['estado'],'OK')
        self.assertAlmostEqual(uno['cuenta']['saldo_actual'],131.5184)
        self.assertEqual(antes,(hashlib.sha256(self.ruta.read_bytes()).hexdigest(),self.ruta.stat().st_mtime_ns))

    def test_saldo_corrupto_no_se_repara(self):
        with store.conectar() as con:
            con.execute('UPDATE paper_account SET saldo_actual=999')
        self.assertIn('SALDO_NO_CONCILIA',self.codigos())
        self.assertEqual(store.cuenta()['saldo_actual'],999)

    def test_cierre_sin_evento_y_hash_alterado(self):
        identidad=self.abrir()
        store.cerrar(identidad,98,'CERRADA_STOP')
        with store.conectar() as con:
            con.execute("DELETE FROM paper_events WHERE tipo='CIERRE'")
            con.execute("UPDATE paper_requests SET plan_hash='alterado'")
        self.assertTrue({'CIERRE_EVENTO_FALTANTE_O_DUPLICADO','PLAN_HASH_NO_COINCIDE'}<=self.codigos())

    def test_pnl_cuenta_y_trade_manipulados_se_detectan(self):
        identidad = self.abrir()
        store.cerrar(identidad,104,'CERRADA_OBJETIVO')
        with store.conectar() as con:
            con.execute('UPDATE paper_account SET saldo_actual=105,pnl_acumulado=5')
            con.execute('UPDATE paper_trades SET resultado_usd=5')
        self.assertIn('PNL_CALCULADO_NO_COINCIDE',self.codigos())

    def test_solicitud_huerfana_y_evento_inexistente(self):
        self.abrir()
        with store.conectar() as con:
            con.execute('UPDATE paper_requests SET trade_id=999')
            store.evento(con,'CIERRE',{'id':999,'pnl':0})
        self.assertTrue({'SOLICITUD_SIN_TRADE','EVENTO_TRADE_INEXISTENTE'}<=self.codigos())

    def test_comision_y_riesgo_no_coinciden_con_plan(self):
        self.abrir()
        with store.conectar() as con:
            con.execute('UPDATE paper_trades SET comision_pct_apertura=.5,riesgo_usd=0')
        self.assertTrue({'COMISION_PLAN_NO_COINCIDE','RIESGO_TRADE_NO_COINCIDE'}<=self.codigos())

    def test_base_ausente_no_se_crea(self):
        ruta = Path(self.tmp.name)/'ausente.db'
        with self.assertRaises(sqlite3.OperationalError):
            informe(ruta)
        self.assertFalse(ruta.exists())

    def test_json_evento_invalido_no_aborta_diagnostico(self):
        with store.conectar() as con:
            con.execute("INSERT INTO paper_events(fecha,tipo,datos) VALUES('x','CIERRE','[]')")
        self.assertIn('JSON_INVALIDO',self.codigos())


if __name__ == '__main__':
    unittest.main()
