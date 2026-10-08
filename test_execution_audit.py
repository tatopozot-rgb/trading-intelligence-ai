from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from execution_audit import AuditoriaOffline


class AuditTests(unittest.TestCase):
    def setUp(self):
        from test_execution_bundle import BundleTests
        fixture=BundleTests(); fixture.setUp()
        self.intencion=fixture.intencion
        self.paquete=dict(plan=fixture.plan,snapshot=fixture.snapshot,evidencias=fixture.evidencias)
        self.limites=fixture.limites
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.ruta=Path(self.tmp.name)/'audit.offline.sqlite3'
        self.db=AuditoriaOffline(self.ruta)
        self.db.crear_intencion(self.intencion)

    def registrar(self,id='e1',ahora=1200,paquete=None):
        return self.db.evaluar_y_registrar('i1',id,self.paquete if paquete is None else paquete,
                                         ahora_ms=ahora,limites_politica=self.limites)

    def reporte(self):
        return self.db.informe_auditoria('i1')

    def test_paquete_y_resultado_persisten_no_inician_simulacion(self):
        r=self.registrar()
        self.assertFalse(r['enviable']); self.assertFalse(r['autorizado'])
        self.db=AuditoriaOffline(self.ruta)
        informe=self.reporte()
        self.assertEqual(informe['estado_local'],'INTENCION')
        self.assertEqual(informe['estado'],'REGISTRO_INTEGRO')
        self.assertEqual(informe['paquete'],self.paquete)
        registro=informe['evaluaciones'][0]['registro']
        self.assertEqual(registro['entrada']['limites_politica'],self.limites)
        self.assertEqual(registro['entrada']['ahora_ms'],1200)
        self.assertEqual(registro['intencion'],self.intencion)
        self.assertIn('evaluador',registro)

    def test_duplicado_identico_historico_no_revalida(self):
        self.registrar()
        with patch('execution_audit.evaluar_paquete_fixture',side_effect=AssertionError('no revalidar')):
            r=self.registrar()
        self.assertTrue(r['duplicado']); self.assertTrue(r['historico'])
        self.assertEqual(r['estado'],'REGISTRO_HISTORICO_NO_AUTORIZANTE')
        self.assertEqual(len(self.reporte()['evaluaciones']),1)

    def test_id_reusado_distinto_conserva_original_y_conflicto(self):
        original=self.registrar()['registro']
        self.assertEqual(self.registrar(ahora=1201)['estado'],'ID_EVALUACION_CONFLICTIVO')
        self.registrar(ahora=1201)
        self.db=AuditoriaOffline(self.ruta)
        informe=self.reporte()
        self.assertEqual(informe['evaluaciones'][0]['registro'],original)
        self.assertEqual(len(informe['conflictos']),1)
        self.assertEqual(informe['estado'],'DISCREPANCIA')
        r=self.registrar()
        self.assertTrue(r['duplicado']); self.assertTrue(r['conflicto_actual'])

    def test_paquete_diferente_marca_conflicto_sin_sobrescribir(self):
        self.registrar()
        recibido=deepcopy(self.paquete)
        recibido['plan']['parametros']['price']='110'
        r=self.registrar('e2',paquete=recibido)
        self.assertEqual(r['registro']['resultado']['estado'],'PAQUETE_CONFLICTIVO')
        self.assertEqual(self.reporte()['paquete'],self.paquete)
        self.assertEqual(self.reporte()['evaluaciones'][1]['registro']['entrada']['paquete'],recibido)
        self.assertEqual(self.registrar('e3')['registro']['resultado']['estado'],'BLOQUEADO_POR_CONFLICTO')

    def test_rechazo_no_fija_paquete_invalido(self):
        malo=deepcopy(self.paquete); malo['snapshot']['entorno']='PRODUCTION'
        r=self.registrar(paquete=malo)
        self.assertEqual(r['registro']['resultado']['estado'],'RECHAZADO_VALIDACION')
        self.assertIsNone(self.reporte()['paquete'])
        self.registrar('e2')
        self.assertEqual(self.reporte()['paquete'],self.paquete)
        self.assertEqual(len(self.reporte()['evaluaciones']),2)

    def test_nueva_evaluacion_caducada_no_reusa_exito(self):
        self.registrar()
        r=self.registrar('e2',ahora=2000)
        self.assertEqual(r['registro']['resultado']['estado'],'RECHAZADO_VALIDACION')
        self.assertEqual(self.reporte()['evaluaciones'][0]['registro']['resultado']['estado'],
                         'FILTROS_DECLARADOS_VERIFICADOS_OFFLINE')

    def test_estado_en_curso_no_se_reautoriza(self):
        self.db.iniciar_simulacion('i1')  # Sólo cambio de etiqueta en fixture temporal.
        self.assertEqual(self.registrar()['registro']['resultado']['estado'],'BLOQUEADO_POR_ESTADO')
        self.assertEqual(self.reporte()['estado_local'],'ENVIO_SIMULADO')

    def test_rollback_si_evento_falla(self):
        with patch.object(self.db,'_evento',side_effect=RuntimeError('disco simulado')):
            with self.assertRaises(RuntimeError): self.registrar()
        self.assertIsNone(self.reporte()['paquete'])
        self.assertEqual(self.reporte()['evaluaciones'],[])

    def test_rollback_conflicto_si_evento_falla(self):
        self.registrar()
        with patch.object(self.db,'_evento',side_effect=RuntimeError('fallo')):
            with self.assertRaises(RuntimeError): self.registrar(ahora=1201)
        informe=self.reporte()
        self.assertEqual(informe['estado'],'REGISTRO_INTEGRO')
        self.assertEqual(informe['conflictos'],[])

    def test_fallo_inesperado_evaluador_no_se_oculta(self):
        with patch('execution_audit.evaluar_paquete_fixture',side_effect=RuntimeError('bug')):
            with self.assertRaises(RuntimeError): self.registrar()
        self.assertEqual(self.reporte()['evaluaciones'],[])

    def test_concurrencia_idempotente(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            resultados=list(pool.map(lambda _:self.registrar(),range(8)))
        self.assertEqual(sum(not r['duplicado'] for r in resultados),1)
        self.assertEqual(len(self.reporte()['evaluaciones']),1)

    def test_informe_solo_lee_una_transaccion(self):
        self.registrar()
        antes=self.ruta.read_bytes()
        with patch.object(self.db,'conectar',wraps=self.db.conectar) as conectar:
            self.reporte()
        self.assertEqual(conectar.call_count,1)
        self.assertEqual(self.ruta.read_bytes(),antes)

    def test_integridad_detecta_datos_alterados_y_no_los_reescribe(self):
        self.registrar()
        with self.db.conectar() as con:
            fila=con.execute('SELECT datos FROM evaluaciones').fetchone()
            dato=json.loads(fila['datos']); dato['entrada']['ahora_ms']=999
            con.execute('UPDATE evaluaciones SET datos=?',(json.dumps(dato),))
        self.assertEqual(self.reporte()['estado'],'DISCREPANCIA')
        with self.assertRaises(ValueError): self.registrar()

    def test_intencion_inexistente_o_paquete_no_json_sin_guardar(self):
        with self.assertRaises(ValueError):
            self.db.evaluar_y_registrar('otra','e1',self.paquete,ahora_ms=1200,limites_politica=self.limites)
        with self.assertRaises(ValueError): self.registrar(paquete={'plan':float('nan'),'snapshot':{},'evidencias':{}})
        self.assertEqual(self.reporte()['evaluaciones'],[])

    def test_evento_o_evaluacion_faltante_se_detecta(self):
        self.registrar()
        with self.db.conectar() as con:
            con.execute("DELETE FROM evidencia_orden WHERE clase='EVALUACION_REGISTRADA'")
        self.assertIn('EVENTOS_EVALUACION_DISCORDANTES',self.reporte()['problemas'])
        with self.db.conectar() as con:
            con.execute('DELETE FROM evaluaciones')
        self.assertIn('PAQUETE_SIN_EVALUACION_ORIGINAL',self.reporte()['problemas'])

    def test_json_corrupto_es_no_verificado_sin_reparar(self):
        self.registrar()
        with self.db.conectar() as con:
            con.execute("UPDATE evaluaciones SET datos='{' ")
        antes=self.ruta.read_bytes()
        self.assertEqual(self.reporte()['estado'],'NO_VERIFICADO')
        self.assertEqual(self.ruta.read_bytes(),antes)

    def test_bug_value_error_o_decimal_no_es_rechazo_legitimo(self):
        from decimal import InvalidOperation
        for error in (ValueError('bug'),InvalidOperation(),AssertionError('bug')):
            with self.subTest(tipo=type(error).__name__):
                with patch('execution_audit.evaluar_paquete_fixture',side_effect=error):
                    with patch('execution_audit.logging.Logger.error') as log:
                        with self.assertRaises(type(error)): self.registrar()
                        log.assert_called_once_with('Evaluación OFFLINE no registrada: %s',type(error).__name__)
                self.assertEqual(self.reporte()['evaluaciones'],[])
                self.assertIsNone(self.reporte()['paquete'])

    def test_decimal_invalido_de_entrada_rechazo_de_dominio(self):
        from execution_context import hash_contenido
        malo=deepcopy(self.paquete)
        malo['evidencias']['PERCENT_PRICE']['referencia']['precio']='NaN'
        malo['plan']['evidencias_hash']['PERCENT_PRICE']=hash_contenido(malo['evidencias']['PERCENT_PRICE'])
        nueva=deepcopy(self.intencion); nueva['plan_hash']=hash_contenido(malo['plan'])
        self.db=AuditoriaOffline(Path(self.tmp.name)/'invalid-decimal.offline.sqlite3')
        self.db.crear_intencion(nueva)
        r=self.registrar(paquete=malo)
        self.assertEqual(r['registro']['resultado']['estado'],'RECHAZADO_VALIDACION')
        self.assertEqual(r['registro']['resultado']['error_tipo'],'FiltroInvalido')

    def test_conflicto_historico_no_desaparece_por_bandera(self):
        self.registrar(); self.registrar(ahora=1201)
        with self.db.conectar() as con:
            con.execute('UPDATE intenciones SET conflicto=0')
        self.assertEqual(self.reporte()['estado'],'DISCREPANCIA')
        self.assertIn('BANDERA_CONFLICTO_INCOHERENTE',self.reporte()['problemas'])


if __name__ == '__main__':
    unittest.main()
