import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from historical_batch import evaluar_lote, cargar_replay
from historical_replay import reproducir, _hash
from historical_case import evaluar_caso, MODELO_ENTRADA, MODELO_SALIDA
from historical_dataset import cargar_dataset
import test_historical_dataset as fixtures


class BatchTests(unittest.TestCase):
    def setUp(self):
        fixtures.DatasetTests.setUp(self)
        self.replay=self.root/'replay.json'
        self.r=reproducir(self.ruta,self.ahora-4*900000,self.ahora+900000)
        self.guardar_replay()
        self.casos=[dict(instante_senal_ms=self.ahora,instante_entrada_ms=self.ahora,
                         fin_exclusivo_ms=self.ahora+900000,precio_entrada=110,
                         capital=100,comision_pct=.1)]

    guardar_serie=fixtures.DatasetTests.guardar_serie
    guardar=fixtures.DatasetTests.guardar

    def guardar_replay(self, actualizar_filas=False):
        if actualizar_filas: self.r['filas_sha256']=_hash(self.r['filas'])
        self.replay.write_text(json.dumps(self.r,allow_nan=False),encoding='utf-8')
        self.digest=hashlib.sha256(self.replay.read_bytes()).hexdigest()

    def ejecutar(self,**cambios):
        a=dict(sha256_replay_esperado=self.digest,modelo_entrada=MODELO_ENTRADA,
               modelo_salida=MODELO_SALIDA)
        return evaluar_lote(self.ruta,self.replay,self.casos,**(a | cambios))

    def test_paridad_campo_a_campo_y_sin_recalcular_indicadores(self):
        ds=cargar_dataset(self.ruta)
        esperado=evaluar_caso('BTCUSDT',ds['series'],**self.casos[0],
                             modelo_entrada=MODELO_ENTRADA,modelo_salida=MODELO_SALIDA)
        with patch('historical_analysis.analizar_instante',side_effect=AssertionError), \
             patch('historical_proposal.analizar_instante',side_effect=AssertionError), \
             patch('analysis_engine.analizar_temporalidad',side_effect=AssertionError):
            r=self.ejecutar()
        self.assertEqual(r['resultados'],[esperado])
        self.assertFalse(r['indicadores_recalculados']); self.assertFalse(r['autenticidad_verificada'])
        self.assertFalse(r['ejecutable']); self.assertNotIn('pnl_total',r)

    def test_determinismo_no_mutacion_y_solapes_no_agregados(self):
        self.casos.append(copy.deepcopy(self.casos[0]))
        antes=copy.deepcopy(self.casos)
        archivos={p.name:p.read_bytes() for p in self.root.iterdir()}
        a=self.ejecutar(); b=self.ejecutar()
        self.assertEqual(a,b); self.assertEqual(self.casos,antes)
        self.assertEqual(a['resultados'][0],a['resultados'][1])
        self.assertEqual(archivos,{p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_huella_externa_y_filas_adulteradas(self):
        with self.assertRaises(ValueError): self.ejecutar(sha256_replay_esperado='0'*64)
        self.r['filas'][0]['analisis']['temporalidades']['1h']['precio']+=1
        self.guardar_replay()
        with patch('historical_batch._evaluar_caso',side_effect=AssertionError):
            with self.assertRaises(ValueError): self.ejecutar()

    def test_manifiesto_y_codigo_incompatibles(self):
        original=copy.deepcopy(self.r)
        for cambios in (dict(manifiesto_sha256='0'*64),dict(codigo_sha256={}),dict(simbolo='ETHUSDT')):
            self.r=original | cambios; self.guardar_replay()
            with self.subTest(cambios=cambios),self.assertRaises(ValueError): self.ejecutar()

    def test_ventana_anticipada_aun_con_hashes_recalculados(self):
        self.r['filas'][0]['ventanas']['1h']['ultima_cierre_ms']+=3600000
        self.guardar_replay(True)
        with self.assertRaises(ValueError): self.ejecutar()

    def test_precio_y_cierre_no_corresponden_a_datos(self):
        original=copy.deepcopy(self.r)
        for campo,valor in (('precio',12345),('vela_cierre_utc_ms',True),('rsi',101)):
            self.r=copy.deepcopy(original)
            self.r['filas'][0]['analisis']['temporalidades']['1h'][campo]=valor
            self.guardar_replay(True)
            with self.subTest(campo=campo),self.assertRaises(ValueError): self.ejecutar()

    def test_orden_duplicados_y_booleanos(self):
        original=copy.deepcopy(self.r)
        for cambiar in ('orden','duplicado','booleano'):
            self.r=copy.deepcopy(original)
            if cambiar=='orden': self.r['filas'].reverse()
            elif cambiar=='duplicado': self.r['filas'][1]=self.r['filas'][0]
            else: self.r['filas'][0]['instante_utc_ms']=True
            self.guardar_replay(True)
            with self.subTest(cambiar=cambiar),self.assertRaises(ValueError): self.ejecutar()

    def test_conteos_y_consenso_incoherentes(self):
        self.r['condiciones_cumplidas']+=1; self.guardar_replay()
        with self.assertRaises(ValueError): self.ejecutar()
        self.r['condiciones_cumplidas']-=1
        self.r['filas'][0]['analisis']['consenso']='FALSO'; self.guardar_replay(True)
        with self.assertRaises(ValueError): self.ejecutar()

    def test_caso_invalido_no_devuelve_resultados_parciales(self):
        self.casos.append(self.casos[0] | dict(instante_entrada_ms=self.ahora+1))
        with self.assertRaises(ValueError): self.ejecutar()

    def test_senal_ausente_y_fin_fuera_cobertura(self):
        original=self.casos[0]
        for cambio in (dict(instante_senal_ms=self.ahora+1),dict(fin_exclusivo_ms=self.ahora+1800000)):
            self.casos=[original | cambio]
            with self.subTest(cambio=cambio),self.assertRaises(ValueError): self.ejecutar()

    def test_json_duplicado_y_modelo_invalido(self):
        with self.assertRaises(ValueError): self.ejecutar(modelo_entrada='otro')
        self.replay.write_text('{"tipo":1,"tipo":2}',encoding='utf-8')
        self.digest=hashlib.sha256(self.replay.read_bytes()).hexdigest()
        with self.assertRaises(ValueError): self.ejecutar()


if __name__ == '__main__': unittest.main()
