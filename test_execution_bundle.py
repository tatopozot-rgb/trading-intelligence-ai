from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from execution_bundle import evaluar_paquete_fixture
from execution_context import ContextoInvalido, hash_contenido, validar_contexto_offline
from execution_orders import OrdenesOffline


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.parametros=dict(symbol='FIXTUREUSDT',side='BUY',type='LIMIT',timeInForce='GTC',price='100',quantity='1')
        self.snapshot=dict(schema='SNAPSHOT_OFFLINE_V1',entorno='TESTNET_FIXTURE',obtenido_ms=900,
            simbolo=dict(symbol='FIXTUREUSDT',status='TRADING',isSpotTradingAllowed=True,orderTypes=['LIMIT'],filters=[
                dict(filterType='PRICE_FILTER',minPrice='1',maxPrice='200',tickSize='0.01'),
                dict(filterType='LOT_SIZE',minQty='0.1',maxQty='10',stepSize='0.1'),
                dict(filterType='MIN_NOTIONAL',minNotional='10'),
                dict(filterType='PERCENT_PRICE',avgPriceMins=5,multiplierDown='0.7',multiplierUp='1.3'),
                dict(filterType='PERCENT_PRICE_BY_SIDE',avgPriceMins=1,bidMultiplierDown='0.8',bidMultiplierUp='1.2',askMultiplierDown='0.5',askMultiplierUp='2')]))
        prueba=dict(schema='PRECIO_PORCENTUAL_FIXTURE_V1',entorno='TESTNET_FIXTURE',simbolo='FIXTUREUSDT',
                    referencia=dict(estado='PRESENTE',precio='100',observado_ms=1000,recibido_ms=1010))
        self.evidencias={tipo:deepcopy(prueba) for tipo in ('PERCENT_PRICE','PERCENT_PRICE_BY_SIDE')}
        self.plan=dict(schema='PLAN_EVALUACION_FIXTURE_V2',entorno='TESTNET_FIXTURE',cuenta='FICTICIA',
                       parametros=deepcopy(self.parametros),snapshot_hash='',creado_ms=1100,vence_ms=2000,
                       evidencias_hash={},politica=dict(max_edad_snapshot_ms=500,max_edad_referencia_ms=200))
        self.intencion=dict(id_local='i1',entorno='TESTNET_FIXTURE',cuenta='FICTICIA',simbolo='FIXTUREUSDT',
                            parametros=deepcopy(self.parametros),snapshot_hash='',plan_hash='')
        self.limites=dict(max_edad_snapshot_ms=500,max_edad_referencia_ms=200,max_vigencia_plan_ms=1000)
        self.fijar()

    def fijar(self):
        """Constructor SOLO de fixtures: simula nueva referencia, no permiso de cambiar planes."""
        self.plan['snapshot_hash']=hash_contenido(self.snapshot)
        self.plan['evidencias_hash']={t:hash_contenido(e) for t,e in self.evidencias.items()}
        self.intencion['snapshot_hash']=self.plan['snapshot_hash']
        self.intencion['plan_hash']=hash_contenido(self.plan)

    def evaluar(self, ahora=1200):
        return evaluar_paquete_fixture(self.intencion,self.plan,self.snapshot,self.evidencias,ahora_ms=ahora,limites_politica=self.limites)

    def test_completo_dos_porcentuales_no_autoriza_ni_muta(self):
        antes=deepcopy((self.intencion,self.plan,self.snapshot,self.evidencias))
        r=self.evaluar()
        self.assertFalse(r['enviable']); self.assertFalse(r['autorizado'])
        self.assertEqual(len(r['porcentuales']),2)
        self.assertEqual(len(r['filtros_evaluados']),5)
        self.assertIn('RIESGO_Y_CUENTA',r['pendientes'])
        self.assertEqual(antes,(self.intencion,self.plan,self.snapshot,self.evidencias))

    def test_estaticos_sin_dinamicos_exigen_mapa_vacio(self):
        self.snapshot['simbolo']['filters']=self.snapshot['simbolo']['filters'][:3]
        self.evidencias={}; self.fijar()
        self.assertEqual(self.evaluar()['porcentuales'],[])

    def test_mutacion_snapshot_y_rehash_no_elude_intencion(self):
        self.snapshot['simbolo']['filters'][3]['multiplierUp']='1.4'
        self.plan['snapshot_hash']=hash_contenido(self.snapshot)
        with self.assertRaises(ContextoInvalido): self.evaluar()
        self.intencion['snapshot_hash']=self.plan['snapshot_hash']
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_cambio_evidencia_y_rehash_no_elude_plan(self):
        self.evidencias['PERCENT_PRICE']['referencia']['precio']='101'
        with self.assertRaises(ContextoInvalido): self.evaluar()
        self.plan['evidencias_hash']['PERCENT_PRICE']=hash_contenido(self.evidencias['PERCENT_PRICE'])
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_evidencia_faltante_sobrante_y_hash_extra(self):
        originales=deepcopy(self.evidencias)
        del self.evidencias['PERCENT_PRICE']
        with self.assertRaises(ContextoInvalido): self.evaluar()
        self.evidencias=originales
        self.evidencias['FUTURO']=deepcopy(originales['PERCENT_PRICE'])
        self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_desconocidos_duplicados_y_metadata_no_se_recortan(self):
        original=deepcopy(self.snapshot)
        for nuevo in (dict(filterType='FUTURO'),dict(filterType='MAX_NUM_ORDERS',maxNumOrders=200),deepcopy(original['simbolo']['filters'][0])):
            self.snapshot=deepcopy(original)
            self.snapshot['simbolo']['filters'].append(nuevo); self.fijar()
            with self.assertRaises(ContextoInvalido): self.evaluar()
        self.snapshot=deepcopy(original)
        self.snapshot['simbolo']['precisionDesconocida']=8; self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_campos_nuevos_estaticos_y_flags_malos(self):
        self.snapshot['simbolo']['filters'][0]['campoNuevo']='1'; self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()
        del self.snapshot['simbolo']['filters'][0]['campoNuevo']
        self.snapshot['simbolo']['filters'][2]['applyToMarket']='false'; self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_politica_no_puede_ampliarse_sin_cambiar_plan(self):
        with self.assertRaises(ContextoInvalido): self.evaluar(1201)
        self.plan['politica']['max_edad_referencia_ms']=1000
        with self.assertRaises(ContextoInvalido): self.evaluar(1201)
        self.plan['politica']['max_edad_referencia_ms']=True; self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_caducidad_snapshot_y_plan_independientes(self):
        self.limites.update(max_edad_referencia_ms=1000,max_edad_snapshot_ms=2000)
        self.plan['politica']['max_edad_referencia_ms']=1000; self.fijar()
        self.evaluar(1400)
        with self.assertRaises(ContextoInvalido): self.evaluar(1401)
        self.plan['politica']['max_edad_snapshot_ms']=2000; self.fijar()
        self.evaluar(1999)
        with self.assertRaises(ContextoInvalido): self.evaluar(2000)

    def test_referencias_cruzadas_incompatibles(self):
        self.evidencias['PERCENT_PRICE_BY_SIDE']['referencia']['precio']='101'; self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_ventanas_distintas_ausencia_comun(self):
        for tipo,minutos in [('PERCENT_PRICE',5),('PERCENT_PRICE_BY_SIDE',1)]:
            e=self.evidencias[tipo]
            e['referencia']=dict(estado='AUSENTE',observado_ms=1000,recibido_ms=1010)
            e['sustituto']=dict(tipo='VWAP',precio='100',avg_price_mins=minutos,observado_ms=1000,recibido_ms=1010)
        self.fijar(); self.evaluar()
        self.evidencias['PERCENT_PRICE_BY_SIDE']['sustituto']['avg_price_mins']=5; self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_evidencia_futura_respecto_creacion_no_admitida(self):
        for e in self.evidencias.values(): e['referencia']['recibido_ms']=1150
        self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_parametros_precio_no_se_ajustan_para_pasar(self):
        self.plan['parametros']['price']='130'; self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()
        self.intencion['parametros']['price']='130'
        with self.assertRaises(ValueError): self.evaluar()  # BY_SIDE máximo 120.
        self.assertEqual(self.plan['parametros']['price'],'130')

    def test_v1_y_origen_publico_no_se_mezclan(self):
        with self.assertRaises(ContextoInvalido):
            validar_contexto_offline(self.plan,self.snapshot,plan_hash_esperado=self.intencion['plan_hash'],
                                     cuenta_esperada='FICTICIA',ahora_ms=1200,max_edad_ms=500)
        self.snapshot['entorno']='BINANCE_PUBLIC_MARKET_DATA'; self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()

    def test_intencion_persistida_inmutable_y_estado_no_cambia(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=OrdenesOffline(Path(tmp)/'bundle.offline.sqlite3')
            db.crear_intencion(self.intencion)
            antes=db.informe_orden('i1')
            r=evaluar_paquete_fixture(antes['intencion'],self.plan,self.snapshot,self.evidencias,ahora_ms=1200,limites_politica=self.limites)
            self.assertFalse(r['autorizado'])
            self.assertEqual(antes,db.informe_orden('i1'))

    def test_limites_externos_igualdad_exceso_ausencia(self):
        self.evaluar()
        for campo in ('max_edad_snapshot_ms','max_edad_referencia_ms'):
            self.plan['politica'][campo]+=1; self.fijar()
            with self.assertRaises(ContextoInvalido): self.evaluar()
            self.plan['politica'][campo]-=1; self.fijar()
        self.limites['max_vigencia_plan_ms']=900; self.evaluar()
        self.limites['max_vigencia_plan_ms']=899
        with self.assertRaises(ContextoInvalido): self.evaluar()
        self.limites={}
        with self.assertRaises(ContextoInvalido): self.evaluar()
        with self.assertRaises(TypeError):
            evaluar_paquete_fixture(self.intencion,self.plan,self.snapshot,self.evidencias,ahora_ms=1200)

    def test_sustituto_distinta_recepcion_se_rechaza(self):
        for tipo,minutos in [('PERCENT_PRICE',5),('PERCENT_PRICE_BY_SIDE',1)]:
            self.evidencias[tipo].update(referencia=dict(estado='AUSENTE',observado_ms=1000,recibido_ms=1010),
                sustituto=dict(tipo='VWAP',precio='100',avg_price_mins=minutos,observado_ms=1000,recibido_ms=1011))
        self.fijar()
        with self.assertRaises(ContextoInvalido): self.evaluar()


if __name__ == '__main__':
    unittest.main()
