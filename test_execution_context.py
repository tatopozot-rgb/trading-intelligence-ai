import copy
import tempfile
from pathlib import Path
import unittest

from execution_context import ContextoInvalido, cargar_json_contexto, hash_contenido, validar_contexto_offline, validar_contexto_intencion
from execution_filters import FiltroInvalido
from execution_orders import OrdenesOffline


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.parametros = dict(symbol='FIXTUREUSDT', side='BUY', type='LIMIT', timeInForce='GTC', price='10', quantity='1')
        self.snapshot = dict(schema='SNAPSHOT_OFFLINE_V1', entorno='TESTNET_FIXTURE', obtenido_ms=1000,
            simbolo=dict(symbol='FIXTUREUSDT', status='TRADING', isSpotTradingAllowed=True, orderTypes=['LIMIT'], filters=[
                dict(filterType='PRICE_FILTER', minPrice='1', maxPrice='100', tickSize='0.01'),
                dict(filterType='LOT_SIZE', minQty='0.001', maxQty='10', stepSize='0.001'),
                dict(filterType='MIN_NOTIONAL', minNotional='10')]))
        self.plan = dict(schema='PLAN_OFFLINE_V1', entorno='TESTNET_FIXTURE', cuenta='FICTICIA',
                         parametros=self.parametros, snapshot_hash=hash_contenido(self.snapshot), creado_ms=1100, vence_ms=2000)
        self.hash_fijado = hash_contenido(self.plan)

    def validar(self, **kwargs):
        return validar_contexto_offline(self.plan, self.snapshot, **{
            'plan_hash_esperado':self.hash_fijado, 'cuenta_esperada':'FICTICIA', 'ahora_ms':1200,
            'max_edad_ms':500, **kwargs})

    def intencion(self):
        return dict(id_local='fixture1', entorno='TESTNET_FIXTURE', cuenta='FICTICIA', simbolo='FIXTUREUSDT',
                    parametros=copy.deepcopy(self.parametros), plan_hash=self.hash_fijado,
                    snapshot_hash=self.plan['snapshot_hash'])

    def test_valida_sin_mutacion_ni_autorizacion(self):
        antes = copy.deepcopy((self.plan, self.snapshot))
        a, b = self.validar(), self.validar()
        self.assertEqual(a, b)
        self.assertEqual(a['estado'], 'CONTEXTO_OFFLINE_VERIFICADO')
        self.assertFalse(a['enviable'])
        self.assertFalse(a['autorizado'])
        self.assertEqual((self.plan, self.snapshot), antes)

    def test_orden_claves_no_cambia_hash_pero_listas_y_textos_si(self):
        self.assertEqual(hash_contenido({'b':'2','a':'1'}), hash_contenido({'a':'1','b':'2'}))
        self.assertNotEqual(hash_contenido(['1','2']), hash_contenido(['2','1']))
        self.assertNotEqual(hash_contenido('1'), hash_contenido('1.0'))
        self.assertNotEqual(hash_contenido(1), hash_contenido(True))
        self.assertNotEqual(hash_contenido(1), hash_contenido('1'))

    def test_snapshot_alterado_rechaza_incluso_si_filtro_sigue_permitiendo(self):
        self.snapshot['simbolo']['filters'][0]['maxPrice'] = '200'
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_recalcular_hash_snapshot_no_elude_plan_fijado(self):
        self.snapshot['obtenido_ms'] = 1100
        self.plan['snapshot_hash'] = hash_contenido(self.snapshot)
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_parametros_cambiados_no_eluden_hash_fijado(self):
        self.plan['parametros']['price'] = '11'
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_fronteras_edad_y_vencimiento(self):
        self.validar(ahora_ms=1500)
        with self.assertRaises(ContextoInvalido): self.validar(ahora_ms=1501)
        self.validar(ahora_ms=1999, max_edad_ms=1000)
        with self.assertRaises(ContextoInvalido): self.validar(ahora_ms=2000, max_edad_ms=1000)
        self.validar(ahora_ms=1100)
        with self.assertRaises(ContextoInvalido): self.validar(ahora_ms=1099)

    def test_cronologia_y_snapshot_futuro_rechazados_con_hash_valido(self):
        for obtenido, creado, vence in [(1300,1400,2000), (1150,1100,2000), (1000,1500,1400)]:
            with self.subTest(obtenido=obtenido, creado=creado, vence=vence):
                self.snapshot['obtenido_ms'] = obtenido
                self.plan.update(snapshot_hash=hash_contenido(self.snapshot), creado_ms=creado, vence_ms=vence)
                self.hash_fijado = hash_contenido(self.plan)
                with self.assertRaises(ContextoInvalido): self.validar()

    def test_edad_cero_solo_instante_exacto(self):
        self.plan['creado_ms'] = 1000
        self.hash_fijado = hash_contenido(self.plan)
        self.validar(ahora_ms=1000, max_edad_ms=0)
        with self.assertRaises(ContextoInvalido): self.validar(ahora_ms=1001, max_edad_ms=0)

    def test_tiempos_sin_coercion_y_sin_defaults(self):
        for campo in ('ahora_ms','max_edad_ms'):
            for valor in (True, '1200', 1200.0, -1, 2**63, None):
                with self.subTest(campo=campo, valor=valor), self.assertRaises(ContextoInvalido):
                    self.validar(**{campo:valor})
        with self.assertRaises(TypeError):
            validar_contexto_offline(self.plan, self.snapshot, plan_hash_esperado=self.hash_fijado, cuenta_esperada='FICTICIA')

    def test_cuenta_entorno_esquema_campos(self):
        with self.assertRaises(ContextoInvalido): self.validar(cuenta_esperada='OTRA')
        for clave, valor in [('entorno','PRODUCTION'), ('schema','PLAN_V2'), ('extra',True)]:
            plan = {**self.plan, clave:valor}
            with self.subTest(clave=clave), self.assertRaises(ContextoInvalido):
                validar_contexto_offline(plan, self.snapshot, plan_hash_esperado=hash_contenido(plan),
                                        cuenta_esperada='FICTICIA', ahora_ms=1200, max_edad_ms=500)
        del self.plan['vence_ms']
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_hash_correcto_no_sustituye_filtros(self):
        self.snapshot['simbolo']['filters'].append(dict(filterType='PERCENT_PRICE'))
        self.plan['snapshot_hash'] = hash_contenido(self.snapshot)
        self.hash_fijado = hash_contenido(self.plan)
        with self.assertRaises(FiltroInvalido): self.validar()

    def test_hash_correcto_no_sustituye_simbolo(self):
        self.snapshot['simbolo']['symbol'] = 'OTRO'
        self.plan['snapshot_hash'] = hash_contenido(self.snapshot)
        self.hash_fijado = hash_contenido(self.plan)
        with self.assertRaises(FiltroInvalido): self.validar()

    def test_hash_no_admite_float_objetos_complejos_ni_ciclos(self):
        ciclo = []; ciclo.append(ciclo)
        for valor in (0.1, float('nan'), float('inf'), None, {1:'x'}, ('x',), 'x'*10001,
                      2**64, [0]*10001, ciclo, ['x'*10000]*11):
            with self.subTest(tipo=type(valor).__name__), self.assertRaises(ContextoInvalido):
                hash_contenido(valor)

    def test_referencias_hash_invalidas(self):
        for h in ('a'*63, 'A'*64, 'not-a-hash', 1, None):
            with self.subTest(h=h), self.assertRaises(ContextoInvalido): self.validar(plan_hash_esperado=h)

    def test_integracion_intencion_persistida_no_cambia_estado(self):
        with tempfile.TemporaryDirectory() as tmp:
            ordenes = OrdenesOffline(Path(tmp)/'context.offline.sqlite3')
            ordenes.crear_intencion(self.intencion())
            antes = ordenes.informe_orden('fixture1')
            resultado = validar_contexto_intencion(antes['intencion'], self.plan, self.snapshot, ahora_ms=1200, max_edad_ms=500)
            self.assertFalse(resultado['enviable'])
            self.assertEqual(antes, ordenes.informe_orden('fixture1'))

    def test_intencion_y_plan_no_intercambiables(self):
        for cambio in ({'snapshot_hash':'c'*64}, {'plan_hash':'c'*64}, {'cuenta':'OTRA'},
                       {'parametros':{**self.parametros,'quantity':'2'}}):
            with self.subTest(cambio=cambio), self.assertRaises(ContextoInvalido):
                validar_contexto_intencion({**self.intencion(), **cambio}, self.plan, self.snapshot, ahora_ms=1200, max_edad_ms=500)

    def test_json_duplicados_en_todos_los_niveles(self):
        for contenido in ('{"cuenta":"FICTICIA","cuenta":"OTRA"}',
                          '{"parametros":{"price":"1","price":"2"}}',
                          '{"a":1,"\\u0061":1}'):
            with self.subTest(contenido=contenido), self.assertRaises(ContextoInvalido):
                cargar_json_contexto(contenido)
        a = cargar_json_contexto('{"b":"2","a":"1"}')
        b = cargar_json_contexto('{"a":"1","b":"2"}')
        self.assertEqual(hash_contenido(a), hash_contenido(b))

    def test_json_rechaza_no_finitos_floats_sobrecarga_y_sintaxis(self):
        for contenido in ('{"x":NaN}', '{"x":Infinity}', '{"x":1.0}', '{"x":1e2}',
                          '{', 'null', '['*1500 + '0' + ']'*1500, ' '*100001,
                          '"'+'é'*60000+'"', b'{}'):
            with self.subTest(inicio=str(contenido)[:20]), self.assertRaises(ContextoInvalido):
                cargar_json_contexto(contenido)


if __name__ == '__main__':
    unittest.main()
