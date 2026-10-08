from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from execution_orders import OrdenesOffline


class OrdenesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = Path(self.tmp.name) / 'orders.offline.sqlite3'
        self.ordenes = OrdenesOffline(self.ruta)
        self.intencion = dict(id_local='fixture1', entorno='TESTNET_FIXTURE', cuenta='FICTICIA',
                              simbolo='FIXTUREUSDT', plan_hash='a'*64, snapshot_hash='b'*64,
                              parametros=dict(symbol='FIXTUREUSDT', side='BUY', type='LIMIT',
                                              timeInForce='GTC', price='100', quantity='1'))
        self.snapshot = dict(entorno='TESTNET_FIXTURE', cuenta='FICTICIA', simbolo='FIXTUREUSDT',
                             client_order_id='fixture1', order_id='10', status='NEW',
                             orig_qty='1', executed_qty='0', quote_qty='0', update_time=100)
        self.fill = dict(entorno='TESTNET_FIXTURE', cuenta='FICTICIA', simbolo='FIXTUREUSDT',
                         trade_id='1', orden_id='10', cantidad='0.4', precio='100',
                         comision='0.04', activo_comision='USDT')

    def preparar(self):
        self.ordenes.crear_intencion(self.intencion)
        return self.ordenes.iniciar_simulacion('fixture1')

    def registrar(self, **cambios):
        return self.ordenes.registrar_snapshot('fixture1', {**self.snapshot, **cambios})

    def informe(self):
        return self.ordenes.informe_orden('fixture1')

    def test_intencion_inmutable_y_conflicto_durable(self):
        self.ordenes.crear_intencion(self.intencion)
        self.assertEqual(self.ordenes.crear_intencion(self.intencion)['estado'], 'DUPLICADO_IDENTICO')
        otro = {**self.intencion, 'plan_hash': 'c'*64}
        self.assertEqual(self.ordenes.crear_intencion(otro)['estado'], 'DISCREPANCIA')
        self.ordenes = OrdenesOffline(self.ruta)
        self.assertEqual(self.informe()['intencion'], self.intencion)
        self.assertEqual(self.informe()['estado'], 'DISCREPANCIA')
        self.assertEqual(self.ordenes.iniciar_simulacion('fixture1')['estado'], 'BLOQUEADO_SIN_REENVIO')

    def test_timeout_reinicio_y_no_reenvio(self):
        self.preparar()
        self.ordenes.marcar_incierto('fixture1')
        self.ordenes.marcar_incierto('fixture1')
        self.ordenes = OrdenesOffline(self.ruta)
        self.assertEqual(self.informe()['estado_local'], 'INCIERTO')
        self.assertTrue(self.informe()['recuperacion_necesaria'])
        self.assertFalse(self.informe()['enviable'])
        self.assertEqual(self.ordenes.iniciar_simulacion('fixture1')['estado'], 'BLOQUEADO_SIN_REENVIO')
        self.assertEqual(self.ordenes.crear_intencion({**self.intencion, 'id_local':'fixture2'})['estado'], 'AMBITO_BLOQUEADO')
        self.assertEqual(sum(e['datos']=='ENVIO_SIMULADO' for e in self.informe()['evidencia']), 1)

    def test_corte_antes_timeout_no_reinicia_envio(self):
        self.preparar()
        self.ordenes = OrdenesOffline(self.ruta)
        self.assertTrue(self.informe()['recuperacion_necesaria'])
        self.assertEqual(self.ordenes.iniciar_simulacion('fixture1')['estado'], 'BLOQUEADO_SIN_REENVIO')
        self.registrar()
        self.assertEqual(self.informe()['estado_local'], 'CON_EVIDENCIA')

    def test_concurrencia_una_intencion_un_envio(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            resultados = list(pool.map(lambda n: self.ordenes.crear_intencion({**self.intencion, 'id_local':f'f{n}'}), range(8)))
        self.assertEqual(sum(r['estado']=='INTENCION' for r in resultados), 1)
        ganador = next(n for n,r in enumerate(resultados) if r['estado']=='INTENCION')
        with ThreadPoolExecutor(max_workers=8) as pool:
            resultados = list(pool.map(lambda _: self.ordenes.iniciar_simulacion(f'f{ganador}'), range(8)))
        self.assertEqual(sum(r['estado']=='ENVIO_SIMULADO' for r in resultados), 1)

    def test_duplicados_empates_y_conflicto_no_desaparece(self):
        self.preparar()
        self.registrar()
        self.assertEqual(self.registrar()['estado'], 'DUPLICADO_IDENTICO')
        self.assertEqual(self.registrar(status='PARTIALLY_FILLED', executed_qty='0.4', quote_qty='40')['estado'], 'DISCREPANCIA')
        self.assertEqual(self.informe()['snapshot'], self.snapshot)
        self.registrar(status='PARTIALLY_FILLED', executed_qty='0.4', quote_qty='40', update_time=101)
        self.ordenes = OrdenesOffline(self.ruta)
        self.assertEqual(self.informe()['estado'], 'DISCREPANCIA')
        self.assertEqual(len([e for e in self.informe()['evidencia'] if e['clase']=='SNAPSHOT']), 3)

    def test_evidencia_antigua_no_retrocede_y_contradiccion_persiste(self):
        self.preparar()
        self.registrar(update_time=200, status='PARTIALLY_FILLED', executed_qty='0.4', quote_qty='40')
        self.assertEqual(self.registrar()['estado'], 'EVIDENCIA_ANTIGUA')
        self.assertEqual(self.informe()['snapshot']['update_time'], 200)
        self.assertEqual(self.registrar(status='PARTIALLY_FILLED', executed_qty='0.5', quote_qty='50')['estado'], 'DISCREPANCIA')

    def test_cantidades_no_decrecen(self):
        self.preparar()
        self.registrar(status='PARTIALLY_FILLED', executed_qty='0.4', quote_qty='40')
        self.assertEqual(self.registrar(status='PARTIALLY_FILLED', executed_qty='0.3', quote_qty='30', update_time=101)['estado'], 'DISCREPANCIA')
        self.assertEqual(self.informe()['snapshot']['executed_qty'], '0.4')

    def test_cancelacion_parcial_preserva_fills_y_terminal(self):
        self.preparar()
        self.registrar(status='PARTIALLY_FILLED', executed_qty='0.4', quote_qty='40')
        self.assertEqual(self.informe()['estado'], 'EVIDENCIA_NO_CONCILIADA')
        self.ordenes.registrar_fill(self.fill)
        self.registrar(status='CANCELED', executed_qty='0.4', quote_qty='40', update_time=101)
        reporte = self.informe()
        self.assertEqual(reporte['estado_exchange'], 'CANCELED')
        self.assertEqual(reporte['ledger']['cantidad'], '0.4')
        self.assertEqual(reporte['ledger']['comisiones_por_activo'], {'USDT':'0.04'})
        self.assertEqual(reporte['estado'], 'ACUMULADOS_COINCIDEN')
        self.assertTrue(reporte['ambito_bloqueado'])
        self.assertEqual(self.registrar(update_time=102)['estado'], 'DISCREPANCIA')
        self.assertEqual(self.informe()['estado_exchange'], 'CANCELED')

    def test_fill_adelantado_no_se_descarta_y_quote_tambien_se_compara(self):
        self.preparar()
        self.registrar()
        self.ordenes.registrar_fill(self.fill)
        self.assertEqual(self.informe()['estado'], 'EVIDENCIA_NO_CONCILIADA')
        self.registrar(status='PARTIALLY_FILLED', executed_qty='0.4', quote_qty='41', update_time=101)
        self.assertEqual(self.informe()['estado'], 'EVIDENCIA_NO_CONCILIADA')
        # Un snapshot posterior coherente puede conciliar; ningún fill se borra.
        self.registrar(status='PARTIALLY_FILLED', executed_qty='0.5', quote_qty='50', update_time=102)
        self.ordenes.registrar_fill({**self.fill, 'trade_id':'2', 'cantidad':'0.1', 'comision':'0.01'})
        self.assertEqual(self.informe()['estado'], 'ACUMULADOS_COINCIDEN')

    def test_conflicto_fill_prevalece_sobre_acumulados_iguales(self):
        self.preparar()
        self.registrar(status='PARTIALLY_FILLED', executed_qty='0.4', quote_qty='40')
        self.ordenes.registrar_fill(self.fill)
        self.ordenes.registrar_fill({**self.fill, 'comision':'0.05'})
        self.assertEqual(self.informe()['estado'], 'DISCREPANCIA')

    def test_identidad_antes_del_timestamp(self):
        for n, cambio in enumerate(({'order_id':'11'}, {'client_order_id':'otra'}, {'cuenta':'OTRA'}, {'simbolo':'OTRO'})):
            with self.subTest(cambio=cambio):
                self.ordenes = OrdenesOffline(Path(self.tmp.name) / f'identity{n}.offline.sqlite3')
                self.preparar()
                self.registrar()
                self.assertEqual(self.registrar(update_time=90, **cambio)['estado'], 'DISCREPANCIA')
                self.assertEqual(self.informe()['snapshot']['order_id'], '10')

    def test_order_id_en_otro_simbolo_no_colisiona(self):
        self.preparar()
        self.registrar()
        otra = {**self.intencion, 'id_local':'otra', 'simbolo':'OTRO',
                'parametros':{**self.intencion['parametros'], 'symbol':'OTRO'}}
        self.ordenes.crear_intencion(otra)
        self.ordenes.iniciar_simulacion('otra')
        r = self.ordenes.registrar_snapshot('otra', {**self.snapshot, 'client_order_id':'otra', 'simbolo':'OTRO'})
        self.assertEqual(r['estado'], 'SNAPSHOT_ACEPTADO')

    def test_colision_entre_intenciones_marca_ambas(self):
        self.preparar()
        self.registrar()
        # Fixture legado imposible de crear por API actual: audita defensa ante colisión.
        from execution_ledger import serializar
        otra = {**self.intencion, 'id_local':'otra'}
        with self.ordenes.conectar() as con:
            con.execute("INSERT INTO intenciones(id_local,cuenta,simbolo,datos,estado_local) VALUES(?,?,?,?,?)",
                        ('otra','FICTICIA','FIXTUREUSDT',serializar(otra),'INCIERTO'))
        r = self.ordenes.registrar_snapshot('otra', {**self.snapshot, 'client_order_id':'otra'})
        self.assertEqual(r['estado'], 'DISCREPANCIA')
        self.assertEqual(self.informe()['estado'], 'DISCREPANCIA')
        self.assertEqual(self.ordenes.informe_orden('otra')['estado'], 'DISCREPANCIA')

    def test_snapshot_invalido_sin_mutaciones(self):
        self.preparar()
        antes = self.informe()
        for cambio in ({'update_time':True}, {'update_time':2**63}, {'status':'???'}, {'executed_qty':'NaN'},
                       {'orig_qty':'0'}, {'status':'FILLED'}, {'executed_qty':'0.1'}, {'order_id':10}):
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                self.registrar(**cambio)
        self.assertEqual(self.informe(), antes)

    def test_hashes_y_parametros_invalidos_sin_mutaciones(self):
        for cambio in ({'plan_hash':'?'}, {'snapshot_hash':'a'*63}, {'entorno':'PRODUCTION'},
                       {'parametros':{**self.intencion['parametros'], 'quantity':1}}):
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                self.ordenes.crear_intencion({**self.intencion, **cambio})
        with self.assertRaises(ValueError):
            self.informe()

    def test_rollback_si_auditoria_falla(self):
        self.preparar()
        with patch.object(self.ordenes, '_evento', side_effect=RuntimeError('fallo simulado')):
            with self.assertRaises(RuntimeError):
                self.registrar()
        self.assertIsNone(self.informe()['snapshot'])
        self.assertEqual(self.informe()['estado_local'], 'ENVIO_SIMULADO')

    def test_informe_usa_una_sola_conexion(self):
        self.preparar()
        self.registrar()
        with patch.object(self.ordenes, 'conectar', wraps=self.ordenes.conectar) as conectar:
            self.informe()
        self.assertEqual(conectar.call_count, 1)

    def test_terminal_mismo_estado_no_cambia_acumulados(self):
        self.preparar()
        self.registrar(status='CANCELED', executed_qty='0.4', quote_qty='40')
        self.assertEqual(self.registrar(status='CANCELED', executed_qty='0.5', quote_qty='50', update_time=101)['estado'], 'DISCREPANCIA')
        self.assertEqual(self.informe()['snapshot']['executed_qty'], '0.4')

    def test_exceso_intencion_persistente_sin_inventar_reparacion(self):
        self.preparar()
        self.registrar()
        self.ordenes.registrar_fill({**self.fill, 'cantidad':'1.1'})
        self.ordenes = OrdenesOffline(self.ruta)
        self.assertEqual(self.informe()['estado'], 'DISCREPANCIA')
        self.assertIn('FILLS_SUPERAN_INTENCION', self.informe()['problemas_orden'])
        self.registrar(status='FILLED', executed_qty='1', quote_qty='100', update_time=101)
        self.assertEqual(self.informe()['estado'], 'DISCREPANCIA')

    def test_exceso_sobre_terminal_no_es_solo_incompleto(self):
        self.preparar()
        self.registrar(status='CANCELED', executed_qty='0.3', quote_qty='30')
        self.ordenes.registrar_fill(self.fill)
        self.ordenes = OrdenesOffline(self.ruta)
        self.assertIn('FILLS_SUPERAN_TERMINAL', self.informe()['problemas_orden'])
        self.assertEqual(self.informe()['estado'], 'DISCREPANCIA')

    def test_representacion_decimal_distinta_conflicto_explicito(self):
        self.preparar()
        self.registrar()
        self.assertEqual(self.registrar(orig_qty='1.00')['estado'], 'DISCREPANCIA')
        self.assertEqual(self.informe()['snapshot']['orig_qty'], '1')


if __name__ == '__main__':
    unittest.main()
