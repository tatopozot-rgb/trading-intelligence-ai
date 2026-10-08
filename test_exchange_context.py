from copy import deepcopy
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import unittest

from exchange_context import ORIGEN, normalizar_exchange_info, diagnosticar_limite_publico, permisos_compatibles, consultar_contexto_publico
from execution_context import ContextoInvalido, hash_contenido, validar_contexto_offline, cargar_json_contexto
from execution_filters import FiltroInvalido


class ExchangeContextTests(unittest.TestCase):
    def setUp(self):
        self.orden = dict(symbol='FIXTUREUSDT',side='BUY',type='LIMIT',timeInForce='GTC',price='10',quantity='1')
        self.s = dict(symbol='FIXTUREUSDT',status='TRADING',baseAsset='FIXTURE',quoteAsset='USDT',
            orderTypes=['LIMIT','MARKET'],isSpotTradingAllowed=True,permissionSets=[['SPOT','MARGIN'],['GROUP_A']],filters=[
                dict(filterType='PRICE_FILTER',minPrice='1',maxPrice='100',tickSize='0.01'),
                dict(filterType='LOT_SIZE',minQty='0.001',maxQty='10',stepSize='0.001'),
                dict(filterType='NOTIONAL',minNotional='5',maxNotional='100',applyMinToMarket=True,applyMaxToMarket=False,avgPriceMins=5),
                dict(filterType='MARKET_LOT_SIZE',minQty='0',maxQty='100',stepSize='0'),
                dict(filterType='ICEBERG_PARTS',limit=100),
                dict(filterType='TRAILING_DELTA',minTrailingAboveDelta=10,maxTrailingAboveDelta=2000,minTrailingBelowDelta=10,maxTrailingBelowDelta=2000),
                dict(filterType='PERCENT_PRICE_BY_SIDE',bidMultiplierUp='1.2',bidMultiplierDown='0.5',askMultiplierUp='2',askMultiplierDown='0.8',avgPriceMins=5),
                dict(filterType='MAX_NUM_ORDERS',maxNumOrders=200)])
        self.dato = dict(timezone='UTC',serverTime=1000,exchangeFilters=[],symbols=[self.s],
                         rateLimits=[dict(rateLimitType='REQUEST_WEIGHT',interval='MINUTE',intervalNum=1,limit=6000)])

    def normal(self, **kwargs):
        return normalizar_exchange_info(self.dato, **{'simbolo_esperado':'FIXTUREUSDT','obtenido_ms':1100,'origen':ORIGEN,**kwargs})

    def informe(self, orden=None):
        return diagnosticar_limite_publico(orden or self.orden,self.dato,obtenido_ms=1100,origen=ORIGEN)

    def test_preserva_todo_sin_mutar_y_copia_independiente(self):
        antes = deepcopy(self.dato)
        n = self.normal()
        self.assertEqual(n['respuesta'],antes)
        self.assertEqual(n['hash_respuesta'],hash_contenido(antes))
        n['respuesta']['symbols'][0]['filters'].clear()
        self.assertEqual(self.dato,antes)
        self.assertEqual(n['origen'],ORIGEN)
        self.assertFalse(n['enviable'])

    def test_diagnostico_no_oculta_dinamicos_cuenta_ni_privados(self):
        r = self.informe()
        self.assertEqual(r['estado'],'NO_VALIDABLE_PARA_ENVIO')
        self.assertFalse(r['enviable'])
        self.assertFalse(r['autorizado'])
        self.assertEqual(r['clasificacion']['MARKET_LOT_SIZE'],'NO_APLICA_LIMIT_SIMPLE')
        self.assertEqual(r['clasificacion']['PERCENT_PRICE_BY_SIDE'],'REQUIERE_PRECIO_REFERENCIA')
        self.assertIn('MAX_NUM_ORDERS',r['pendientes'])
        self.assertIn('FILTROS_PRIVADOS_NO_VERIFICADOS',r['pendientes'])
        self.assertEqual(len(r['normalizado']['respuesta']['symbols'][0]['filters']),8)

    def test_permisos_and_entre_grupos_or_dentro(self):
        grupos = self.s['permissionSets']
        self.assertFalse(permisos_compatibles(grupos,['SPOT']))
        self.assertTrue(permisos_compatibles(grupos,['SPOT','GROUP_A']))
        self.assertTrue(permisos_compatibles(grupos,['MARGIN','GROUP_A']))
        self.assertFalse(permisos_compatibles(grupos,[]))
        for conjuntos,cuenta in [([],[]),([[]],['SPOT']),([['SPOT','SPOT']],[]),([['SPOT']],True),([['SPOT']],[1])]:
            with self.assertRaises(ValueError): permisos_compatibles(conjuntos,cuenta)

    def test_no_reetiqueta_produccion_testnet(self):
        with self.assertRaises(ContextoInvalido): self.normal(origen='TESTNET_FIXTURE')
        n=self.normal()
        plan=dict(schema='PLAN_OFFLINE_V1',entorno='TESTNET_FIXTURE',cuenta='FICTICIA',
                  parametros=self.orden,snapshot_hash=hash_contenido(n),creado_ms=1100,vence_ms=1500)
        with self.assertRaises(ContextoInvalido):
            validar_contexto_offline(plan,n,plan_hash_esperado=hash_contenido(plan),cuenta_esperada='FICTICIA',ahora_ms=1200,max_edad_ms=500)

    def test_simbolo_unico_y_coincidente(self):
        with self.assertRaises(ContextoInvalido): self.normal(simbolo_esperado='OTRO')
        self.dato['symbols'].append(deepcopy(self.s))
        with self.assertRaises(ContextoInvalido): self.normal()
        self.dato['symbols'] = []
        with self.assertRaises(ContextoInvalido): self.normal()

    def test_filtro_desconocido_y_global_se_preservan_bloqueados(self):
        nuevo = dict(filterType='FUTURO',valor='123')
        self.s['filters'].append(nuevo)
        self.dato['exchangeFilters'] = [dict(filterType='EXCHANGE_MAX_NUM_ORDERS',maxNumOrders=1000)]
        r = self.informe()
        self.assertIn('FUTURO',r['pendientes'])
        self.assertIn('EXCHANGE_MAX_NUM_ORDERS',r['pendientes'])
        self.assertEqual(r['normalizado']['respuesta']['symbols'][0]['filters'][-1],nuevo)

    def test_campos_nuevos_en_filtro_no_se_ignoran(self):
        self.s['filters'][0]['reglaNueva'] = '1'
        self.dato['nuevoControl'] = True
        self.s['nuevaRestriccion'] = 'NO_ASUMIR'
        r = self.informe()
        self.assertIn('PRICE_FILTER:CAMPOS_NUEVOS',r['pendientes'])
        self.assertIn('CAMPOS_RAIZ_NUEVOS',r['pendientes'])
        self.assertIn('METADATOS_SIMBOLO_NO_EVALUADOS',r['pendientes'])
        self.assertIn('nuevaRestriccion',r['normalizado']['campos_simbolo_no_evaluados'])

    def test_no_aplicabilidad_solo_orden_limit_simple(self):
        for cambios in ({'type':'MARKET'}, {'icebergQty':'0.1'}, {'trailingDelta':10}, {'orderListId':1}):
            with self.subTest(cambios=cambios),self.assertRaises(FiltroInvalido):
                self.informe({**self.orden,**cambios})

    def test_validacion_estatica_no_se_omite(self):
        with self.assertRaises(FiltroInvalido): self.informe({**self.orden,'price':'10.001'})
        self.s['status']='BREAK'
        with self.assertRaises(FiltroInvalido): self.informe()

    def test_campos_malformados_no_coercion(self):
        original = deepcopy(self.dato)
        for cambiar in (lambda d:d['symbols'][0].update(isSpotTradingAllowed=1),
                        lambda d:d.update(serverTime=True),
                        lambda d:d['rateLimits'][0].update(limit=True),
                        lambda d:d['symbols'][0]['filters'][2].update(applyMinToMarket='true'),
                        lambda d:d['symbols'][0]['filters'][6].update(avgPriceMins=True),
                        lambda d:d['symbols'][0]['filters'][0].pop('tickSize'),
                        lambda d:d['symbols'][0].update(permissionSets=[])):
            self.dato = deepcopy(original)
            cambiar(self.dato)
            with self.assertRaises(ValueError): self.normal()

    def test_filtros_duplicados_y_rate_limits_ausentes(self):
        self.s['filters'].append(deepcopy(self.s['filters'][0]))
        with self.assertRaises(ContextoInvalido): self.normal()
        self.s['filters'].pop()
        self.dato['rateLimits']=[]
        with self.assertRaises(ContextoInvalido): self.normal()

    def test_server_time_no_se_usa_como_recepcion_o_frescura(self):
        self.dato['serverTime']=999999999
        n=self.normal()
        self.assertEqual(n['obtenido_ms'],1100)
        self.assertEqual(n['respuesta']['serverTime'],999999999)
        self.assertIn('VIGENCIA_NO_VERIFICADA',self.informe()['pendientes'])

    def test_transporte_estricto_rechaza_duplicados_antes_de_normalizar(self):
        from market_http import ClientePublico, DatosInvalidos
        with tempfile.TemporaryDirectory() as tmp:
            respuesta=Mock(status_code=200,text='{"symbols":[],"symbols":[{}]}')
            transporte=Mock(return_value=respuesta)
            cliente=ClientePublico(ruta_bloqueo=Path(tmp)/'cooldown.json',transporte=transporte)
            with self.assertRaises(DatosInvalidos):
                cliente.get('/api/v3/exchangeInfo',{'symbol':'FIXTUREUSDT'},decodificador=cargar_json_contexto)
            respuesta.json.assert_not_called()
            respuesta.close.assert_called_once()
            transporte.assert_called_once()
            self.assertFalse(transporte.call_args.kwargs['allow_redirects'])

    def test_hash_reglas_excluye_solo_server_time(self):
        primero=self.normal()
        self.dato['serverTime']+=1
        segundo=self.normal()
        self.assertNotEqual(primero['hash_respuesta'],segundo['hash_respuesta'])
        self.assertEqual(primero['hash_reglas'],segundo['hash_reglas'])
        self.s['filters'][0]['tickSize']='0.02'
        self.assertNotEqual(primero['hash_reglas'],self.normal()['hash_reglas'])
        self.s['filters'][0]['tickSize']='0.01'
        self.dato['rateLimits'][0]['limit']=5000
        self.assertNotEqual(primero['hash_reglas'],self.normal()['hash_reglas'])
        self.dato['rateLimits'][0]['limit']=6000
        self.s['baseAssetPrecision']=7
        self.assertNotEqual(primero['hash_reglas'],self.normal()['hash_reglas'])

    def test_entrada_publica_obliga_lector_y_ruta_fijos(self):
        with patch('market_http.get_publico',return_value=self.dato) as get:
            n=consultar_contexto_publico('FIXTUREUSDT')
        get.assert_called_once_with('/api/v3/exchangeInfo',{'symbol':'FIXTUREUSDT'},decodificador=cargar_json_contexto)
        self.assertEqual(n['origen'],ORIGEN)
        self.assertFalse(n['enviable'])


if __name__ == '__main__':
    unittest.main()
