from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from execution_ledger import LedgerOffline


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = Path(self.tmp.name)/'fixture.offline.sqlite3'
        self.ledger = LedgerOffline(self.ruta)
        self.fill = dict(entorno='TESTNET_FIXTURE',cuenta='CUENTA_FICTICIA',simbolo='FIXTUREUSDT',
                         trade_id='1',orden_id='10',cantidad='0.4',precio='100',comision='0.04',activo_comision='USDT')

    def informe(self,**kwargs):
        return self.ledger.conciliar('CUENTA_FICTICIA','FIXTUREUSDT','10',**kwargs)

    def test_duplicado_identico_y_reinicio(self):
        self.assertEqual(self.ledger.registrar_fill(self.fill)['estado'],'REGISTRADO')
        self.assertEqual(self.ledger.registrar_fill(self.fill)['estado'],'DUPLICADO_IDENTICO')
        previo = self.informe(cantidad_reportada='0.4',quote_reportado='40')
        self.ledger = LedgerOffline(self.ruta)
        self.assertEqual(previo,self.informe(cantidad_reportada='0.4',quote_reportado='40'))
        self.assertFalse(previo['enviable'])
        self.assertEqual(previo['fills'],1)

    def test_conflicto_durable_no_sobrescribe_original(self):
        self.ledger.registrar_fill(self.fill)
        otro = {**self.fill,'cantidad':'0.9'}
        self.assertEqual(self.ledger.registrar_fill(otro)['estado'],'DISCREPANCIA')
        self.ledger.registrar_fill(otro)
        self.ledger = LedgerOffline(self.ruta)
        reporte = self.informe(cantidad_reportada='0.4',quote_reportado='40')
        self.assertEqual(reporte['cantidad'],'0.4')
        self.assertEqual(reporte['conflictos'],1)
        self.assertEqual(reporte['estado'],'DISCREPANCIA')

    def test_colision_otra_orden_marca_ambas(self):
        self.ledger.registrar_fill(self.fill)
        self.ledger.registrar_fill({**self.fill,'orden_id':'11'})
        self.assertEqual(self.informe()['estado'],'DISCREPANCIA')
        self.assertEqual(self.ledger.conciliar('CUENTA_FICTICIA','FIXTUREUSDT','11')['estado'],'DISCREPANCIA')

    def test_cuentas_simbolos_no_colisionan(self):
        for cambios in ({},{'cuenta':'OTRA_FICTICIA'},{'simbolo':'OTROUSDT'}):
            self.assertEqual(self.ledger.registrar_fill({**self.fill,**cambios})['estado'],'REGISTRADO')
        self.assertEqual(self.informe()['fills'],1)

    def test_parciales_sumados_fuera_de_orden_y_comisiones_separadas(self):
        segundo = {**self.fill,'trade_id':'2','cantidad':'0.6','precio':'101','comision':'0.001','activo_comision':'BNB'}
        self.ledger.registrar_fill(segundo)
        self.ledger.registrar_fill(self.fill)
        self.ledger.registrar_fill(segundo)
        reporte = self.informe(cantidad_reportada='1',quote_reportado='100.6')
        self.assertEqual(reporte['estado'],'ACUMULADOS_COINCIDEN')
        self.assertEqual(reporte['comisiones_por_activo'],{'BNB':'0.001','USDT':'0.04'})

    def test_evidencia_ausente_o_discrepante_no_se_inventa(self):
        self.ledger.registrar_fill(self.fill)
        self.assertEqual(self.informe()['estado'],'SIN_EVIDENCIA_ACUMULADA')
        self.assertEqual(self.informe(cantidad_reportada='0.5',quote_reportado='40')['estado'],'DISCREPANCIA')
        with self.assertRaises(ValueError): self.informe(cantidad_reportada='0.4')

    def test_concurrencia_un_solo_fill(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            estados = list(pool.map(lambda _:self.ledger.registrar_fill(self.fill)['estado'],range(8)))
        self.assertEqual(estados.count('REGISTRADO'),1)
        self.assertEqual(estados.count('DUPLICADO_IDENTICO'),7)
        self.assertEqual(self.informe()['fills'],1)

    def test_ruta_paper_y_base_ajena_rechazadas(self):
        ruta_paper = Path(self.tmp.name)/'trading.db'
        with self.assertRaises(ValueError): LedgerOffline(ruta_paper)
        self.assertFalse(ruta_paper.exists())
        ajena = Path(self.tmp.name)/'ajena.offline.sqlite3'
        with closing(sqlite3.connect(ajena)) as con:
            con.execute('CREATE TABLE ajena(id INTEGER)')
            con.commit()
        antes = ajena.read_bytes()
        with self.assertRaises(ValueError): LedgerOffline(ajena)
        self.assertEqual(antes,ajena.read_bytes())

    def test_invalidos_no_persisten(self):
        for cambios in ({'entorno':'REAL'},{'cantidad':'NaN'},{'cantidad':0.4},{'precio':'0'},
                        {'comision':'-1'},{'trade_id':'01'},{'activo_comision':''}):
            with self.subTest(cambios=cambios),self.assertRaises(ValueError):
                self.ledger.registrar_fill({**self.fill,**cambios})
        self.assertEqual(self.informe()['fills'],0)


if __name__=='__main__': unittest.main()
