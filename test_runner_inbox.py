"""Importación aislada: DB temporal, cotizaciones simuladas, sin runner operativo."""
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import config
import claude_authorizer as auth
import paper_store as store
import system_runner as runner
from runner_health import Salud


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for nombre,valor in [('BASE_DATOS',self.root/'test.db'),('DIRECTORIO',self.root)]:
            parche = patch.object(config,nombre,valor)
            parche.start()
            self.addCleanup(parche.stop)
        for parche in (patch.object(config,'DRAWDOWN_HALT_PCT',50.0), patch.object(config, 'DRAWDOWN_PAUSE_PCT', None),
                       patch.object(store,'_precio_para_equity',side_effect=lambda simbolo: 100.0)):
            parche.start()
            self.addCleanup(parche.stop)
        store.inicializar()
        plan = {'modo':'PAPER','decision':'PAPER CANDIDATE','simbolo':'BTCUSDT',
                'comision_paper_pct':.1,'entrada':100.,'stop_precio':98.,
                'objetivo_precio':104.,'tamano_posicion':40.,'riesgo_usd':.88}
        self.identidad,digest = store.registrar_solicitud(plan,True)
        self.respuesta = {'request_id':self.identidad,'plan_hash':digest,'simbolo':'BTCUSDT',
                         'decision':'APROBAR_PAPER','confianza':80,'razon':'Fixture'}
        self.ruta = self.root/'respuesta.json'
        self.contenido = json.dumps({'respuestas':[self.respuesta]})
        self.ruta.write_text(self.contenido,encoding='utf-8')
        self.procesadas = self.root/'procesadas'
        self.procesadas.mkdir()
        self.vistas = set()
        self.salud = Salud()

    def procesar(self,automatico=True,activa=lambda:True):
        runner.procesar_entrada_bandeja(self.ruta,self.procesadas,self.vistas,self.salud,automatico,activa)

    def eventos(self,tipo):
        with store.conectar() as con:
            return [json.loads(r[0]) for r in con.execute('SELECT datos FROM paper_events WHERE tipo=?',(tipo,))]

    def test_fallo_no_consume_y_no_reintenta_misma_marca(self):
        with patch.object(auth,'obtener_precio_actual',side_effect=RuntimeError('no copiar este contenido')) as precio:
            self.procesar()
            self.procesar()
        precio.assert_called_once()
        self.assertEqual(store.leer_solicitud(self.identidad)['estado'],'PENDIENTE')
        self.assertEqual(store.cuenta()['saldo_actual'],100)
        eventos = self.eventos('BANDEJA_FALLO')
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0]['etapa'],'IMPORTACION')
        self.assertNotIn('no copiar',json.dumps(eventos))
        salud = self.salud.snapshot()['bandeja']
        self.assertEqual(salud['errores_total'],1)
        self.assertEqual(salud['estado'],'DEGRADADO')
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_trades').fetchone()[0],0)

    def test_modificacion_revalida_y_rechaza_caducada_sin_cotizar(self):
        with patch.object(auth,'obtener_precio_actual',side_effect=RuntimeError('fixture')):
            self.procesar()
        with store.conectar() as con:
            con.execute('UPDATE paper_requests SET expira=?',((store.ahora()-timedelta(minutes=1)).isoformat(),))
        self.ruta.write_text(self.contenido+' ',encoding='utf-8')
        with patch.object(auth,'obtener_precio_actual') as precio:
            self.procesar()
            precio.assert_not_called()
        self.assertEqual(store.leer_solicitud(self.identidad)['estado'],'CADUCADA')
        self.assertFalse(self.ruta.exists())
        self.assertEqual(len(list(self.procesadas.iterdir())),1)
        self.assertFalse(self.eventos('RESPUESTA_PROCESADA')[0]['resultados'][0]['registrada'])
        salud = self.salud.snapshot()['bandeja']
        self.assertEqual(salud['estado'],'OK')  # Ingesta resuelta, NO aprobación de trading.
        self.assertEqual(salud['errores_total'],1)
        self.assertEqual(salud['fallos_pendientes'],{})

    def test_error_archivado_no_repite_apertura_ya_confirmada(self):
        with patch.object(auth,'obtener_precio_actual',return_value=100) as precio, \
             patch.object(Path,'rename',side_effect=OSError('fixture')):
            self.procesar()
            self.procesar()
            precio.assert_called_once()
        self.assertEqual(store.leer_solicitud(self.identidad)['estado'],'EJECUTADA')
        self.assertEqual(self.eventos('BANDEJA_FALLO')[0]['etapa'],'ARCHIVADO')
        self.ruta.write_text(self.contenido+'  ',encoding='utf-8')
        with patch.object(auth,'obtener_precio_actual') as precio:
            self.procesar()
            precio.assert_not_called()
        with store.conectar() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM paper_trades').fetchone()[0],1)

    def test_fallo_auditoria_visible_aunque_db_no_registre(self):
        with patch.object(runner,'procesar_archivo',side_effect=RuntimeError('fixture')) as importar, \
             patch.object(store,'evento',side_effect=OSError('fixture')):
            self.procesar()
            self.procesar()
        importar.assert_called_once()
        fallo = self.salud.snapshot()['bandeja']['fallos_pendientes'][self.ruta.name]
        self.assertEqual(fallo['error_auditoria'],'OSError')
        self.assertFalse(fallo['reintento_automatico'])

    def test_manual_y_sesion_inactiva_no_importan(self):
        with patch.object(runner,'procesar_archivo') as importar:
            self.procesar(automatico=False)
            self.vistas.clear()
            self.procesar(activa=lambda:False)
        importar.assert_not_called()
        self.assertEqual(self.eventos('BANDEJA_FALLO'),[])
        self.assertTrue(self.ruta.exists())

    def test_archivo_desaparece_se_audita_una_vez(self):
        self.ruta.unlink()  # Fixture temporal desechable.
        self.procesar()
        self.procesar()
        eventos = self.eventos('BANDEJA_FALLO')
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0]['etapa'],'METADATOS')

    def test_exito_otro_archivo_no_oculta_fallo_pendiente(self):
        self.salud.registrar_bandeja('uno.json',{'tipo':'OSError'})
        self.salud.registrar_bandeja('dos.json')
        estado = self.salud.snapshot()['bandeja']
        self.assertEqual(estado['estado'],'DEGRADADO')
        estado['fallos_pendientes'].clear()
        self.assertIn('uno.json',self.salud.snapshot()['bandeja']['fallos_pendientes'])


if __name__=='__main__':
    unittest.main()
