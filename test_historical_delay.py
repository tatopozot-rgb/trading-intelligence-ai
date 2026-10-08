import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import historical_delay as delay
from historical_batch_report import generar as base_generar, SELECCION, ENTRADA
from historical_case import evaluar_caso, MODELO_ENTRADA, MODELO_SALIDA
from historical_dataset import cargar_dataset
from historical_replay import reproducir
from historical_path import PASO_MS, evaluar_trayectoria
import test_historical_batch as fixtures


class RetrasoTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.BatchTests(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        # La fixture base acaba en su primera señal: añadir futuro sintético
        # permite comprobar resultados retrasados, no sólo exclusiones.
        ultima = self.fx.filas['15m'][-1]
        for i in (1, 2):
            nueva = dict(ultima)
            for campo in ('tiempo_apertura', 'tiempo_cierre'):
                nueva[campo] += i*PASO_MS
            for campo in ('apertura', 'cierre', 'maximo', 'minimo'):
                nueva[campo] += i*.05
            self.fx.filas['15m'].append(nueva)
        self.fx.guardar_serie('15m'); self.fx.guardar()
        self.fx.r = reproducir(self.fx.ruta, self.fx.ahora-4*PASO_MS, self.fx.ahora+3*PASO_MS)
        self.fx.guardar_replay()
        self.base_path = self.fx.root/'base.json'
        self.preparar_base()

    def preparar_base(self):
        self.base = base_generar(self.fx.ruta, self.fx.replay, sha256_replay_esperado=self.fx.digest,
                                 capital=100, comision_pct=.1, seleccion=SELECCION, entrada=ENTRADA)
        self.guardar_base()

    def guardar_base(self):
        self.base_path.write_text(json.dumps(self.base), encoding='utf-8')
        self.hb = hashlib.sha256(self.base_path.read_bytes()).hexdigest()

    def ejecutar(self, **cambios):
        args = dict(sha256_replay_esperado=self.fx.digest, sha256_casos_esperado=self.hb,
                    escenario=delay.ESCENARIO)
        return delay.generar(self.fx.ruta, self.fx.replay, self.base_path, **(args | cambios))

    def test_paridad_con_individual_y_conservacion_de_senal(self):
        r = self.ejecutar()
        self.assertGreater(r['resumen']['comparables'], 0)
        ds = cargar_dataset(self.fx.ruta)
        for p in r['pares']:
            if p['categoria_retardo'] is None: continue
            k = p['indice_retardo']; lote = r['lote_retrasado']
            caso = lote['casos_aportados'][k]
            esperado = evaluar_caso('BTCUSDT', ds['series'], **caso,
                                    modelo_entrada=MODELO_ENTRADA, modelo_salida=MODELO_SALIDA)
            self.assertEqual(lote['resultados'][k], esperado)
            self.assertEqual(esperado['senal'], self.base['resultados'][p['indice_base']]['senal'])
            self.assertEqual(caso['instante_entrada_ms'], caso['instante_senal_ms']+PASO_MS)
            self.assertEqual(caso['fin_exclusivo_ms'], self.fx.r['fin_exclusivo_ms'])

    def test_sin_recalculo_ni_mutacion_y_periodos_conciliados(self):
        antes = {p.name:p.read_bytes() for p in self.fx.root.iterdir() if p.is_file()}
        with patch('analysis_engine.analizar_temporalidad', side_effect=AssertionError), \
             patch('historical_proposal.analizar_instante', side_effect=AssertionError):
            r = self.ejecutar()
        self.assertEqual(antes, {p.name:p.read_bytes() for p in self.fx.root.iterdir() if p.is_file()})
        for grupos in r['periodos'].values():
            for clave in ('casos_base', 'comparables', 'excluidos'):
                self.assertEqual(sum(g[clave] for g in grupos), r['resumen'][clave])
            for g in grupos:
                self.assertEqual(g['casos_base'], g['comparables']+g['excluidos'])
                self.assertEqual(sum(t['casos'] for t in g['transiciones']), g['comparables'])
        self.assertFalse(r['ejecutable']); self.assertNotIn('pnl_total', r)

    def test_fin_exacto_excluido_sin_llamar_evaluador(self):
        self.fx.r = reproducir(self.fx.ruta, self.fx.ahora, self.fx.ahora+PASO_MS)
        self.fx.guardar_replay(); self.preparar_base()
        with patch.object(delay, 'evaluar_lote', side_effect=AssertionError):
            r = self.ejecutar()
        self.assertEqual(r['resumen']['comparables'], 0)
        self.assertEqual(r['resumen']['excluidos'], len(self.base['casos_aportados']))
        self.assertIsNone(r['lote_retrasado'])
        self.assertEqual(r['excluidos'][0]['motivo'], 'SIN_HORIZONTE_TRAS_RETRASO')
        self.assertEqual(sum(r['resumen']['retardo'].values()), 0)

    def test_falta_apertura_identificada_no_truncada(self):
        ds = cargar_dataset(self.fx.ruta)
        caso = copy.deepcopy(self.base['casos_aportados'][0])
        caso['fin_exclusivo_ms'] = caso['instante_entrada_ms']+3*PASO_MS
        serie = ds['series']['15m']
        serie = serie[serie.tiempo_apertura != caso['instante_entrada_ms']+PASO_MS]
        original = copy.deepcopy(caso)
        seleccion, excluidos = delay.preparar_retraso([caso], serie, escenario=delay.ESCENARIO)
        self.assertEqual(seleccion, [])
        self.assertEqual(excluidos[0]['motivo'], 'SIN_APERTURA_PARA_ENTRADA')
        self.assertEqual(excluidos[0]['indice_base'], 0)
        self.assertEqual(caso, original)

    def test_hashes_reglas_y_precio_base_alterados(self):
        for cambios in ({'sha256_casos_esperado':'0'*64}, {'sha256_replay_esperado':'0'*64},
                        {'escenario':'OTRO'}):
            with self.subTest(cambios=cambios), self.assertRaises(ValueError): self.ejecutar(**cambios)
        original = copy.deepcopy(self.base)
        self.base['codigo_evaluacion_sha256']['config.py'] = '0'*64; self.guardar_base()
        with self.assertRaisesRegex(ValueError, 'reglas'): self.ejecutar()
        self.base = original
        self.base['entrada_diagnostica'] = 'OTRA'; self.guardar_base()
        with self.assertRaisesRegex(ValueError, 'simultánea'): self.ejecutar()

    def test_casos_preparados_preservan_parametros_y_validan_base(self):
        serie = cargar_dataset(self.fx.ruta)['series']['15m']
        casos = copy.deepcopy(self.base['casos_aportados'])
        seleccion, _ = delay.preparar_retraso(casos, serie, escenario=delay.ESCENARIO)
        self.assertGreater(len(seleccion), 0)
        for s in seleccion:
            for k in ('instante_senal_ms', 'capital', 'comision_pct', 'fin_exclusivo_ms'):
                self.assertEqual(s['caso'][k], casos[s['indice_base']][k])
        casos[0]['precio_entrada'] += 1
        with self.assertRaisesRegex(ValueError, 'Precio base'):
            delay.preparar_retraso(casos, serie, escenario=delay.ESCENARIO)
        casos[0]['instante_entrada_ms'] = True
        with self.assertRaises(ValueError): delay.preparar_retraso(casos, serie, escenario=delay.ESCENARIO)

    def test_transiciones_diagonal_ambiguedad_y_denominador(self):
        t = self.fx.r['inicio_ms']; fin = self.fx.r['fin_exclusivo_ms']
        categorias = [('STOP_PRIMERO','OBJETIVO_PRIMERO'),('OBJETIVO_PRIMERO','STOP_PRIMERO'),
                      ('AMBIGUO','SIN_SALIDA_EN_RANGO'),('STOP_PRIMERO','STOP_PRIMERO'),
                      ('OBJETIVO_PRIMERO',None)]
        pares = [dict(instante_senal_ms=t+i*PASO_MS, categoria_base=b, categoria_retardo=r)
                 for i,(b,r) in enumerate(categorias)]
        resumen, _ = delay.comparar(pares,t,fin)
        self.assertEqual((resumen['casos_base'], resumen['comparables'], resumen['excluidos']), (5,4,1))
        self.assertEqual(resumen['cambios_categoria'],3)
        self.assertIn(dict(base='STOP_PRIMERO', retardo='STOP_PRIMERO', casos=1), resumen['transiciones'])
        self.assertEqual(sum(resumen['base_comparable'].values()),4)
        self.assertEqual(sum(resumen['retardo'].values()),4)

    def test_barrera_previa_no_cierra_posicion_aun_no_abierta(self):
        t = self.fx.ahora
        velas = [dict(tiempo_apertura=t+i*PASO_MS, tiempo_cierre=t+(i+1)*PASO_MS-1,
                      apertura=100, cierre=100, maximo=120 if i==0 else 101,
                      minimo=80 if i==0 else 99) for i in range(2)]
        r = evaluar_trayectoria(velas[1:], inicio_ms=t+PASO_MS, fin_exclusivo_ms=t+2*PASO_MS,
                                entrada=100, tamano_posicion=20, stop=95, objetivo=110,
                                comision_pct=.1, modelo=MODELO_SALIDA)
        self.assertEqual(r['estado'],'SIN_SALIDA_EN_RANGO')

    def test_integracion_ignora_barreras_en_vela_anterior_a_entrada(self):
        r = self.ejecutar()
        self.assertGreater(r['resumen']['comparables'], 0)
        caso = r['lote_retrasado']['casos_aportados'][0]
        esperado = r['lote_retrasado']['resultados'][0]
        ds = cargar_dataset(self.fx.ruta)
        velas = ds['series']['15m']
        previa = velas.tiempo_apertura == caso['instante_senal_ms']
        self.assertEqual(int(previa.sum()), 1)
        # Ambas barreras se cruzan antes de la apertura retrasada. No había
        # posición: no se cancela ni cambia la señal ya cerrada en t original.
        velas.loc[previa, 'maximo'] = 10000
        velas.loc[previa, 'minimo'] = .01
        obtenido = evaluar_caso('BTCUSDT', ds['series'], **caso,
                                 modelo_entrada=MODELO_ENTRADA, modelo_salida=MODELO_SALIDA)
        self.assertEqual(obtenido, esperado)

    def test_cli_no_sobrescribe(self):
        salida = self.fx.root/'retraso.json'
        args = ['--manifest',str(self.fx.ruta),'--replay',str(self.fx.replay),'--casos',str(self.base_path),
                '--sha256-replay-esperado',self.fx.digest,'--sha256-casos-esperado',self.hb,
                '--escenario',delay.ESCENARIO,'--salida',str(salida)]
        with patch('builtins.print'): delay.main(args)
        anterior = salida.read_bytes()
        with self.assertRaises(FileExistsError): delay.main(args)
        self.assertEqual(anterior,salida.read_bytes())


if __name__ == '__main__': unittest.main()
