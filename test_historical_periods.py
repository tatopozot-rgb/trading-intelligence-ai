"""Diez pruebas aisladas con archivos temporales; no leen datasets reales."""
from collections import Counter
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import historical_periods as periodos


def fecha(texto):
    return int(datetime.fromisoformat(texto.replace('Z', '+00:00')).timestamp() * 1000)


def digest(dato):
    return hashlib.sha256(json.dumps(dato, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class PeriodosTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.ruta = Path(temporal.name)
        for destino in ('socket.create_connection', 'sqlite3.connect'):
            bloqueo = patch(destino, side_effect=AssertionError('Red/DB prohibida'))
            bloqueo.start(); self.addCleanup(bloqueo.stop)
        self.inicio = fecha('2020-12-31T12:00:00Z')
        self.fin = fecha('2021-02-02T12:00:00Z')
        senales = [fecha(t) for t in ('2020-12-31T23:30:00Z', '2021-01-01T00:00:00Z',
                                      '2021-01-04T00:00:00Z', '2021-02-01T00:00:00Z')]
        filas = []
        for t in range(self.inicio, self.fin, periodos.PASO_MS):
            cumple = t in senales
            filas.append(dict(instante_utc_ms=t, cumple_condicion_tecnica=cumple,
                              analisis=dict(simbolo='BTCUSDT', estado='CONDICION' if cumple else 'ESPERAR'),
                              ventanas={'15m': {'ultima_cierre_ms': t - 1}}))
        self.replay = dict(tipo='REPLAY_SENALES_NO_EJECUTABLE_V1', simbolo='BTCUSDT',
                           manifiesto_sha256='a' * 64, inicio_ms=self.inicio, fin_exclusivo_ms=self.fin,
                           paso_ms=periodos.PASO_MS, evaluaciones=len(filas), condiciones_cumplidas=4,
                           episodios_condicion=4, estados=dict(Counter(f['analisis']['estado'] for f in filas)),
                           filas=filas, filas_sha256=digest(filas))
        casos, resultados = [], []
        eventos = ('SOLO_OBJETIVO_OBSERVADO', 'SOLO_STOP_OBSERVADO', 'AMBIGUO_AMBOS_NIVELES', None)
        for t, evento in zip(senales, eventos):
            caso = dict(instante_senal_ms=t, instante_entrada_ms=t, fin_exclusivo_ms=self.fin,
                        precio_entrada=100., capital=100., comision_pct=.1)
            casos.append(caso)
            fila = filas[(t - self.inicio) // periodos.PASO_MS]
            trayectoria = dict(tipo='TRAYECTORIA_HIPOTETICA_NO_EJECUTABLE', modelo=periodos.MODELO_SALIDA,
                               inicio_ms=t, fin_exclusivo_ms=self.fin, entrada_aportada=100.,
                               comision_pct_aportada=.1, estado='SIN_SALIDA_EN_RANGO', evento=None, escenarios={})
            if evento:
                apertura = t + periodos.DIA_MS
                trayectoria.update(estado='DOS_SALIDAS_HIPOTETICAS' if evento.startswith('AMBIGUO') else 'SALIDA_HIPOTETICA',
                                    evento=dict(primera_apertura_ms=apertura,
                                                cierre_ms=apertura + periodos.PASO_MS - 1,
                                                diagnostico={'estado': evento}))
            resultados.append(dict(tipo='CASO_HISTORICO_AISLADO_NO_EJECUTABLE', ejecutable=False,
                                   fill_confirmado=False, modelo_entrada=periodos.MODELO_ENTRADA,
                                   modelo_salida=periodos.MODELO_SALIDA, estado='CASO_HIPOTETICO_EVALUADO',
                                   entrada_hipotetica=dict(instante_ms=t, precio_aportado=100.),
                                   senal=dict(comision_pct_aportada=.1,
                                              analisis_historico=dict(instante_utc_ms=t,
                                                                      analisis=copy.deepcopy(fila['analisis']),
                                                                      ventanas=copy.deepcopy(fila['ventanas']))),
                                   plan_hipotetico=dict(simbolo='BTCUSDT', capital=100., entrada=100., comision_paper_pct=.1),
                                   trayectoria=trayectoria))
        self.informe = dict(tipo='LOTE_CASOS_AISLADOS_NO_EJECUTABLE', ejecutable=False, simbolo='BTCUSDT',
                            manifiesto_sha256='a' * 64, replay_sha256='', casos_sha256=digest(casos),
                            casos_aportados=casos, resultados=resultados, modelo_entrada=periodos.MODELO_ENTRADA,
                            modelo_salida=periodos.MODELO_SALIDA, seleccion_diagnostica=periodos.SELECCION,
                            entrada_diagnostica='APERTURA_15M_DE_SENAL_SIN_LATENCIA_NI_DESLIZAMIENTO',
                            resumen=dict(casos=4, estados=dict(Counter(r['trayectoria']['estado'] for r in resultados)),
                                         eventos={e or 'SIN_EVENTO': 1 for e in eventos}))

    def guardar(self):
        replay = self.ruta / 'replay.json'
        casos = self.ruta / 'casos.json'
        replay.write_text(json.dumps(self.replay), encoding='utf-8')
        hash_replay = hashlib.sha256(replay.read_bytes()).hexdigest()
        self.informe['replay_sha256'] = hash_replay
        casos.write_text(json.dumps(self.informe), encoding='utf-8')
        return casos, replay, hashlib.sha256(casos.read_bytes()).hexdigest(), hash_replay

    def generar(self):
        casos, replay, hc, hr = self.guardar()
        return periodos.generar(casos, replay, sha256_casos_esperado=hc, sha256_replay_esperado=hr)

    def test_calendario_senal_ceros_parciales_y_totales(self):
        reporte = self.generar()
        meses = reporte['periodos']['mes']
        self.assertEqual([p['periodo'] for p in meses], ['2020-12', '2021-01', '2021-02'])
        self.assertEqual([p['casos'] for p in meses], [1, 2, 1])
        self.assertEqual(meses[0]['frecuencias']['OBJETIVO_PRIMERO'], 1)  # Evento ocurre en enero.
        self.assertTrue(meses[0]['parcial_inicio']); self.assertTrue(meses[-1]['parcial_fin'])
        self.assertFalse(meses[1]['parcial_inicio']); self.assertFalse(meses[1]['parcial_fin'])
        dias = reporte['periodos']['dia']
        self.assertEqual(len(dias), 34)
        self.assertEqual(next(p for p in dias if p['periodo'] == '2021-01-02')['casos'], 0)
        self.assertEqual(dias[0]['evaluaciones'], 48); self.assertEqual(dias[-1]['evaluaciones'], 48)
        for grupo in reporte['periodos'].values():
            self.assertEqual(sum(p['casos'] for p in grupo), 4)
            self.assertEqual(sum(p['evaluaciones'] for p in grupo), self.replay['evaluaciones'])
            for categoria in periodos.CATEGORIAS:
                self.assertEqual(sum(p['frecuencias'][categoria] for p in grupo), 1)
        self.assertNotIn('pnl', json.dumps(reporte).lower().replace('p&l', ''))

    def test_semana_iso_lunes_y_cambio_de_ano(self):
        semanas = self.generar()['periodos']['semana_iso']
        self.assertEqual(semanas[0]['periodo'], '2020-W53')
        self.assertEqual(semanas[0]['inicio_utc'], '2020-12-28T00:00:00.000Z')
        self.assertEqual(semanas[0]['casos'], 2)
        self.assertEqual(semanas[1]['periodo'], '2021-W01')
        self.assertEqual(semanas[1]['casos'], 1)
        self.assertEqual(semanas[2]['casos'], 0)
        self.assertTrue(semanas[-1]['parcial_fin'])

    def test_fin_exclusivo_y_bordes_completos(self):
        inicio, fin = fecha('2021-02-01T00:00:00Z'), fecha('2021-03-01T00:00:00Z')
        meses = periodos.agrupar([(inicio, 'STOP_PRIMERO')], inicio, fin, 'mes')
        self.assertEqual(len(meses), 1)
        self.assertFalse(meses[0]['parcial_inicio']); self.assertFalse(meses[0]['parcial_fin'])
        self.assertEqual(len(periodos.agrupar([], inicio, fin, 'dia')), 28)
        with self.assertRaises(ValueError): periodos.agrupar([(fin, 'STOP_PRIMERO')], inicio, fin, 'dia')

    def test_hashes_externos_obligatorios_y_archivos_alterados(self):
        casos, replay, hc, hr = self.guardar()
        with self.assertRaises(TypeError): periodos.generar(casos, replay)
        for campo, malo in (('casos', '0' * 64), ('replay', '0' * 64), ('casos', ''), ('replay', True)):
            with self.subTest(campo=campo, malo=malo), self.assertRaises(ValueError):
                periodos.generar(casos, replay, sha256_casos_esperado=malo if campo == 'casos' else hc,
                                  sha256_replay_esperado=malo if campo == 'replay' else hr)
        casos.write_text(casos.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        with self.assertRaises(ValueError):
            periodos.generar(casos, replay, sha256_casos_esperado=hc, sha256_replay_esperado=hr)

    def test_enlaces_hashes_internos_y_conteos(self):
        original = copy.deepcopy(self.informe)
        for mutar in (lambda r: r.update(casos_sha256='0' * 64),
                      lambda r: r.update(manifiesto_sha256='0' * 64),
                      lambda r: r['resumen'].update(casos=True),
                      lambda r: r['resumen']['eventos'].update(SOLO_STOP_OBSERVADO=2)):
            self.informe = copy.deepcopy(original); mutar(self.informe)
            with self.assertRaises(ValueError): self.generar()
        self.informe = original
        casos, replay, hc, hr = self.guardar()
        dato = json.loads(casos.read_text(encoding='utf-8')); dato['replay_sha256'] = '0' * 64
        casos.write_text(json.dumps(dato), encoding='utf-8'); hc = hashlib.sha256(casos.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            periodos.generar(casos, replay, sha256_casos_esperado=hc, sha256_replay_esperado=hr)
        self.replay['filas_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.generar()

    def test_rechaza_formatos_eventos_desconocidos_y_desalineacion(self):
        original = copy.deepcopy(self.informe)
        for mutar in (lambda r: r.update(tipo='V2'),
                      lambda r: r['resultados'][0]['trayectoria']['evento']['diagnostico'].update(estado='NUEVO'),
                      lambda r: r['resultados'][0]['entrada_hipotetica'].update(precio_aportado=101.),
                      lambda r: r['resultados'].reverse(),
                      lambda r: r['resultados'][0]['senal']['analisis_historico']['analisis'].update(estado='OTRO'),
                      lambda r: r['resultados'][0]['trayectoria'].update(estado='SIN_SALIDA_EN_RANGO')):
            self.informe = copy.deepcopy(original); mutar(self.informe)
            with self.assertRaises(ValueError): self.generar()
        self.informe = original; self.replay['tipo'] = 'V2'
        with self.assertRaises(ValueError): self.generar()

    def test_fechas_bool_y_eventos_fuera_de_rango(self):
        original = copy.deepcopy(self.informe)
        for mutar in (lambda r: r['casos_aportados'][0].update(instante_senal_ms=True),
                      lambda r: r['casos_aportados'][0].update(instante_entrada_ms=self.fin),
                      lambda r: r['resultados'][0]['entrada_hipotetica'].update(instante_ms=True),
                      lambda r: r['resultados'][0]['trayectoria']['evento'].update(primera_apertura_ms=self.fin),
                      lambda r: r['resultados'][0]['trayectoria']['evento'].update(cierre_ms=True)):
            self.informe = copy.deepcopy(original); mutar(self.informe)
            self.informe['casos_sha256'] = digest(self.informe['casos_aportados'])
            with self.assertRaises(ValueError): self.generar()
        self.informe = original; self.replay['inicio_ms'] = True
        with self.assertRaises(ValueError): self.generar()

    def test_duplicados_huecos_y_casos_omitidos(self):
        original = copy.deepcopy(self.informe)
        self.informe['casos_aportados'][1] = copy.deepcopy(self.informe['casos_aportados'][0])
        self.informe['resultados'][1] = copy.deepcopy(self.informe['resultados'][0])
        self.informe['casos_sha256'] = digest(self.informe['casos_aportados'])
        with self.assertRaises(ValueError): self.generar()
        self.informe = copy.deepcopy(original)
        self.informe['casos_aportados'].pop(); self.informe['resultados'].pop()
        self.informe['casos_sha256'] = digest(self.informe['casos_aportados'])
        with self.assertRaises(ValueError): self.generar()
        self.informe = original
        self.replay['filas'][1] = copy.deepcopy(self.replay['filas'][0])
        self.replay['filas_sha256'] = digest(self.replay['filas'])
        with self.assertRaises(ValueError): self.generar()

    def test_json_claves_duplicadas_y_no_finitos(self):
        casos, replay, _, hr = self.guardar()
        for texto in ('{"tipo":"A","tipo":"B"}', '{"valor":NaN}', '{"valor":1e999}'):
            casos.write_text(texto, encoding='utf-8'); hc = hashlib.sha256(casos.read_bytes()).hexdigest()
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                periodos.generar(casos, replay, sha256_casos_esperado=hc, sha256_replay_esperado=hr)

    def test_cli_salida_nueva_no_sobrescribe_y_eth(self):
        self.replay['simbolo'] = self.informe['simbolo'] = 'ETHUSDT'
        for f in self.replay['filas']: f['analisis']['simbolo'] = 'ETHUSDT'
        self.replay['filas_sha256'] = digest(self.replay['filas'])
        for r in self.informe['resultados']:
            r['senal']['analisis_historico']['analisis']['simbolo'] = 'ETHUSDT'
            r['plan_hipotetico']['simbolo'] = 'ETHUSDT'
        casos, replay, hc, hr = self.guardar()
        originales = casos.read_bytes(), replay.read_bytes()
        salida = self.ruta / 'periodos.json'
        args = ['--casos', str(casos), '--replay', str(replay), '--sha256-casos-esperado', hc,
                '--sha256-replay-esperado', hr, '--salida', str(salida)]
        with patch('builtins.print'): periodos.main(args)
        self.assertEqual(json.loads(salida.read_text(encoding='utf-8'))['simbolo'], 'ETHUSDT')
        anterior = salida.read_bytes()
        with self.assertRaises(FileExistsError): periodos.main(args)
        self.assertEqual(salida.read_bytes(), anterior)
        self.assertEqual((casos.read_bytes(), replay.read_bytes()), originales)


if __name__ == '__main__':
    unittest.main()
