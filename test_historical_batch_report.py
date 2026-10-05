import copy
import unittest
from unittest.mock import patch
from historical_batch_report import preparar_casos, generar, SELECCION, ENTRADA
from historical_dataset import cargar_dataset
import test_historical_batch as fixtures


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.BatchTests(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.ds=cargar_dataset(self.fx.ruta)

    def preparar(self,r):
        return preparar_casos(self.ds,r,capital=100,comision_pct=.1,seleccion=SELECCION,entrada=ENTRADA)

    def test_no_mirar_resultados_y_solo_inicios_de_episodio(self):
        r=copy.deepcopy(self.fx.r)
        for fila,c in zip(r['filas'],(False,True,True,False,True)): fila['cumple_condicion_tecnica']=c
        casos=self.preparar(r)
        self.assertEqual([x['instante_senal_ms'] for x in casos],
                         [r['filas'][1]['instante_utc_ms'],r['filas'][4]['instante_utc_ms']])
        self.assertTrue(all(c['instante_senal_ms']==c['instante_entrada_ms'] for c in casos))
        self.assertTrue(all(c['capital']==100 for c in casos))

    def test_no_hay_senales_no_inventa_casos(self):
        r=copy.deepcopy(self.fx.r)
        for fila in r['filas']: fila['cumple_condicion_tecnica']=False
        self.assertEqual(self.preparar(r),[])

    def test_modelos_no_tienen_default(self):
        with self.assertRaises(TypeError): preparar_casos(self.ds,self.fx.r,capital=100,comision_pct=.1)
        with self.assertRaises(ValueError):
            preparar_casos(self.ds,self.fx.r,capital=100,comision_pct=.1,seleccion='otra',entrada=ENTRADA)

    def test_informe_no_agrega_beneficio(self):
        r=generar(self.fx.ruta,self.fx.replay,sha256_replay_esperado=self.fx.digest,
                   capital=100,comision_pct=.1,seleccion=SELECCION,entrada=ENTRADA)
        self.assertEqual(r['resumen']['casos'],len(r['resultados']))
        self.assertEqual(sum(r['resumen']['estados'].values()),r['resumen']['casos'])
        self.assertNotIn('pnl_total',r); self.assertNotIn('rentabilidad',r['resumen'])


if __name__ == '__main__': unittest.main()
