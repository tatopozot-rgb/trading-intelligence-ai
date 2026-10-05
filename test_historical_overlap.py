"""H6a offline: intervalos, censura, límites, empates e integridad de fuentes."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import historical_overlap as solapes
import historical_periods as periodos

T = 1_790_121_600_000
P = periodos.PASO_MS


def fuente(simbolo, definiciones, fin=T + 8 * P):
    senales = {T + entrada * P for entrada, _, _ in definiciones}
    filas = [dict(instante_utc_ms=t, cumple_condicion_tecnica=t in senales,
                  analisis=dict(simbolo=simbolo, estado='CONDICION' if t in senales else 'ESPERAR'),
                  ventanas={'15m': {'ultima_cierre_ms': t - 1}})
             for t in range(T, fin, P)]
    replay = dict(tipo='REPLAY_SENALES_NO_EJECUTABLE_V1', simbolo=simbolo,
                  manifiesto_sha256='a' * 64, inicio_ms=T, fin_exclusivo_ms=fin,
                  paso_ms=P, evaluaciones=len(filas), condiciones_cumplidas=len(senales),
                  episodios_condicion=len(senales), estados=dict(Counter(f['analisis']['estado'] for f in filas)),
                  filas=filas, filas_sha256=periodos._hash(filas))
    casos, resultados = [], []
    for entrada, salida, nombre in definiciones:
        t = T + entrada * P
        caso = dict(instante_senal_ms=t, instante_entrada_ms=t, fin_exclusivo_ms=fin,
                    precio_entrada=100., capital=100., comision_pct=.1)
        casos.append(caso)
        trayectoria = dict(tipo='TRAYECTORIA_HIPOTETICA_NO_EJECUTABLE', modelo=periodos.MODELO_SALIDA,
                           inicio_ms=t, fin_exclusivo_ms=fin, entrada_aportada=100., comision_pct_aportada=.1,
                           ejecutable=False, fill_confirmado=False, seleccionado=None,
                           estado='SIN_SALIDA_EN_RANGO', evento=None, escenarios={})
        if nombre:
            ambiguo = nombre == 'AMBIGUO_AMBOS_NIVELES'
            escenarios = ('STOP_PRIMERO', 'OBJETIVO_PRIMERO') if ambiguo else (nombre,)
            trayectoria.update(estado='DOS_SALIDAS_HIPOTETICAS' if ambiguo else 'SALIDA_HIPOTETICA',
                                evento=dict(primera_apertura_ms=T + salida * P,
                                            cierre_ms=T + (salida + 1) * P - 1,
                                            diagnostico=dict(estado=nombre, fill_confirmado=False, precio_fill=None),
                                            instante_fill=None), escenarios={e: {'resultado_usd': 999.} for e in escenarios})
        fila = filas[entrada]
        resultados.append(dict(tipo='CASO_HISTORICO_AISLADO_NO_EJECUTABLE', ejecutable=False,
                               fill_confirmado=False, modelo_entrada=periodos.MODELO_ENTRADA,
                               modelo_salida=periodos.MODELO_SALIDA, estado='CASO_HIPOTETICO_EVALUADO',
                               entrada_hipotetica=dict(instante_ms=t, precio_aportado=100.),
                               senal=dict(comision_pct_aportada=.1, analisis_historico=dict(
                                   instante_utc_ms=t, analisis=copy.deepcopy(fila['analisis']),
                                   ventanas=copy.deepcopy(fila['ventanas']))),
                               plan_hipotetico=dict(simbolo=simbolo, capital=100., entrada=100., comision_paper_pct=.1),
                               trayectoria=trayectoria))
    informe = dict(tipo='LOTE_CASOS_AISLADOS_NO_EJECUTABLE', ejecutable=False, simbolo=simbolo,
                   manifiesto_sha256='a' * 64, replay_sha256='', casos_sha256=periodos._hash(casos),
                   casos_aportados=casos, resultados=resultados, modelo_entrada=periodos.MODELO_ENTRADA,
                   modelo_salida=periodos.MODELO_SALIDA, seleccion_diagnostica=periodos.SELECCION,
                   entrada_diagnostica=solapes.ENTRADA,
                   resumen=dict(casos=len(casos), estados=dict(Counter(r['trayectoria']['estado'] for r in resultados)),
                                eventos=dict(Counter((r['trayectoria']['evento'] or {}).get('diagnostico', {}).get('estado', 'SIN_EVENTO') for r in resultados))))
    return informe, replay


class SolapesTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.ruta = Path(temporal.name)
        for destino in ('socket.create_connection', 'sqlite3.connect'):
            bloqueo = patch(destino, side_effect=AssertionError('Red/cuentas prohibidas'))
            bloqueo.start(); self.addCleanup(bloqueo.stop)
        self.btc = fuente('BTCUSDT', [(0, 2, 'SOLO_OBJETIVO_OBSERVADO'),
                                      (2, 3, 'SOLO_STOP_OBSERVADO'), (4, 6, 'APERTURA_EN_O_BAJO_STOP')])
        self.eth = fuente('ETHUSDT', [(0, 2, 'APERTURA_EN_O_SOBRE_OBJETIVO'),
                                      (2, 4, 'AMBIGUO_AMBOS_NIVELES'), (6, None, None)])

    def guardar(self):
        fuentes = []
        for i, (informe, replay) in enumerate((self.btc, self.eth)):
            rc, rr = self.ruta / f'casos{i}.json', self.ruta / f'replay{i}.json'
            rr.write_text(json.dumps(replay), encoding='utf-8')
            hr = hashlib.sha256(rr.read_bytes()).hexdigest()
            informe['replay_sha256'] = hr
            rc.write_text(json.dumps(informe), encoding='utf-8')
            fuentes.append(dict(casos=rc, replay=rr, sha256_casos_esperado=hashlib.sha256(rc.read_bytes()).hexdigest(),
                                sha256_replay_esperado=hr))
        return fuentes

    def generar(self):
        return solapes.generar(self.guardar())

    def test_global_indices_todos_determinismo_y_no_prioridad(self):
        fuentes = self.guardar()
        r = solapes.generar(fuentes)
        self.assertEqual(r, solapes.generar(fuentes[::-1]))
        self.assertEqual([c['indice_global'] for c in r['casos']], list(range(6)))
        for simbolo in solapes.SIMBOLOS:
            self.assertEqual([c['indice_original'] for c in r['casos'] if c['simbolo'] == simbolo], [0, 1, 2])
        self.assertEqual(r['resumen']['casos_en_entradas_simultaneas'], 4)
        self.assertEqual(r['cronologia'][0]['entradas_hipoteticas'], ['BTCUSDT:0', 'ETHUSDT:0'])
        self.assertEqual([c['instante_entrada_ms'] for c in r['casos']], sorted(c['instante_entrada_ms'] for c in r['casos']))
        self.assertFalse(r['ejecutable'])

    def test_limites_intravela_solape_posible_y_apertura_exacta_contacto(self):
        r = self.generar()
        pares = {frozenset((p['caso_a'], p['caso_b'])): p for p in r['pares_solape']}
        p = pares[frozenset(('BTCUSDT:0', 'BTCUSDT:1'))]
        self.assertEqual(p['clasificacion'], 'POSIBLE_NO_CONFIRMADO')
        self.assertEqual((p['duracion_minima_ms'], p['duracion_maxima_ms']), (0, P - 1))
        self.assertEqual(pares[frozenset(('BTCUSDT:0', 'ETHUSDT:0'))]['clasificacion'], 'CIERTO')
        self.assertNotIn(frozenset(('BTCUSDT:1', 'ETHUSDT:0')), pares)
        contacto = next(c for c in r['contactos_entrada_salida']
                        if c['caso_con_salida'] == 'ETHUSDT:0' and c['caso_con_entrada'] == 'BTCUSDT:1')
        self.assertEqual(contacto['tipo'], 'MISMO_INSTANTE_MODELADO')
        self.assertIsNone(contacto['orden_ejecucion'])

    def test_ambiguo_conserva_dos_escenarios_sin_economia(self):
        r = self.generar()
        ambiguo = next(c for c in r['casos'] if c['id_caso'] == 'ETHUSDT:1')
        self.assertEqual(ambiguo['categoria'], 'AMBIGUO')
        self.assertTrue(ambiguo['ambiguo_resultado'])
        self.assertEqual(ambiguo['escenarios_conservados'], ['OBJETIVO_PRIMERO', 'STOP_PRIMERO'])
        self.assertEqual(ambiguo['salida_hipotetica']['limite_superior_ms'], T + 5 * P - 1)
        for prohibido in ('resultado_usd', 'capital', 'tamano_posicion', 'aceptado', 'rechazado'):
            self.assertNotIn('"' + prohibido + '"', json.dumps(r))

    def test_censura_sin_cierre_fin_exclusivo_y_cobertura_sin_huecos(self):
        r = self.generar()
        censurado = next(c for c in r['casos'] if c['id_caso'] == 'ETHUSDT:2')
        self.assertTrue(censurado['censurado_derecha'])
        self.assertIsNone(censurado['salida_hipotetica'])
        self.assertEqual(r['cronologia'][-1]['censuras_fin_observacion'], ['ETHUSDT:2'])
        self.assertEqual(r['cronologia'][-1]['salidas_en_apertura_modelada'], [])
        self.assertEqual(r['tramos'][-1]['casos_con_permanencia_cierta'], ['ETHUSDT:2'])
        self.assertEqual(r['tramos'][0]['inicio_ms'], T)
        self.assertEqual(r['tramos'][-1]['fin_exclusivo_ms'], T + 8 * P)
        self.assertEqual(sum(t['fin_exclusivo_ms'] - t['inicio_ms'] for t in r['tramos']), 8 * P)
        self.assertTrue(all(a['fin_exclusivo_ms'] == b['inicio_ms'] for a, b in zip(r['tramos'], r['tramos'][1:])))

    def test_tramos_cotas_y_conteos_concilian(self):
        r = self.generar()
        for tramo in r['tramos']:
            self.assertLessEqual(tramo['cantidad_minima'], tramo['cantidad_maxima'])
            self.assertEqual(tramo['cantidad_minima'], len(tramo['casos_con_permanencia_cierta']))
            self.assertEqual(tramo['cantidad_maxima'], len(tramo['casos_con_permanencia_posible']))
            self.assertLessEqual(set(tramo['casos_con_permanencia_cierta']), set(tramo['casos_con_permanencia_posible']))
        s = r['resumen']
        self.assertEqual(s['pares_solape'], s['pares_solape_cierto'] + s['pares_solape_posible_no_confirmado'])
        self.assertEqual(s['pares_solape'], s['pares_mismo_simbolo'] + s['pares_entre_simbolos'])
        self.assertEqual(s['casos'], s['salidas_en_apertura_modelada'] + s['salidas_intravela'] + s['sin_salida_censurados'])

    def test_dos_censuras_solapan_hasta_fin_sin_salida_inventada(self):
        self.btc = fuente('BTCUSDT', [(0, None, None)])
        self.eth = fuente('ETHUSDT', [(2, None, None)])
        r = self.generar()
        self.assertEqual(len(r['pares_solape']), 1)
        par = r['pares_solape'][0]
        self.assertEqual(par['clasificacion'], 'CIERTO')
        self.assertEqual((par['duracion_minima_ms'], par['duracion_maxima_ms']), (6 * P, 6 * P))
        self.assertTrue(par['incluye_caso_censurado'])
        self.assertTrue(all(c['salida_hipotetica'] is None for c in r['casos']))
        self.assertEqual(r['resumen']['cota_inferior_pico_concurrencia'], 2)
        self.assertEqual(r['resumen']['cota_superior_pico_concurrencia'], 2)
        self.assertEqual(r['contactos_entrada_salida'], [])

    def test_intervalos_vacios_conservan_casos_y_contactos_sin_solape(self):
        self.btc = fuente('BTCUSDT', [(0, 0, 'APERTURA_EN_O_BAJO_STOP')])
        for nombre, pico, contactos in ((None, 1, 1), ('APERTURA_EN_O_SOBRE_OBJETIVO', 0, 2)):
            self.eth = fuente('ETHUSDT', [(0, 0 if nombre else None, nombre)])
            r = self.generar()
            self.assertEqual(r['resumen']['casos'], 2)
            self.assertEqual(r['pares_solape'], [])
            self.assertEqual(r['resumen']['cota_inferior_pico_concurrencia'], pico)
            self.assertEqual(r['resumen']['cota_superior_pico_concurrencia'], pico)
            self.assertEqual(len(r['contactos_entrada_salida']), contactos)
            self.assertTrue(all(c['orden_ejecucion'] is None for c in r['contactos_entrada_salida']))

    def test_ultima_vela_y_salida_en_primera_vela_sin_inventar_hora(self):
        self.btc = fuente('BTCUSDT', [(0, 0, 'SOLO_STOP_OBSERVADO'), (2, 7, 'SOLO_OBJETIVO_OBSERVADO')])
        r = self.generar()
        ultimo = next(c for c in r['casos'] if c['id_caso'] == 'BTCUSDT:1')
        self.assertEqual(ultimo['salida_hipotetica']['limite_superior_ms'], r['fin_exclusivo_ms'] - 1)
        primero = r['casos'][0]
        self.assertEqual(primero['salida_hipotetica']['limite_inferior_ms'], primero['instante_entrada_ms'])
        self.assertEqual(r['tramos'][0]['cantidad_minima'], 1)
        self.assertEqual(r['tramos'][0]['cantidad_maxima'], 2)

    def test_hashes_externos_obligatorios_y_originales_intactos(self):
        fuentes = self.guardar()
        antes = {f[k]: f[k].read_bytes() for f in fuentes for k in ('casos', 'replay')}
        solapes.generar(fuentes)
        self.assertEqual(antes, {ruta: ruta.read_bytes() for ruta in antes})
        for clave in ('sha256_casos_esperado', 'sha256_replay_esperado'):
            for invalido in (None, '', True, '0' * 64):
                alteradas = copy.deepcopy(fuentes); alteradas[0][clave] = invalido
                with self.subTest(clave=clave, invalido=invalido), self.assertRaises(ValueError):
                    solapes.generar(alteradas)
            alteradas = copy.deepcopy(fuentes); del alteradas[0][clave]
            with self.assertRaises(ValueError): solapes.generar(alteradas)

    def test_json_duplicado_no_finito_o_hash_interno_alterado(self):
        fuentes = self.guardar()
        for contenido in ('{"tipo":"a","tipo":"b"}', '{"x":NaN}', '{"x":1e999}'):
            fuentes[0]['casos'].write_text(contenido, encoding='utf-8')
            fuentes[0]['sha256_casos_esperado'] = hashlib.sha256(fuentes[0]['casos'].read_bytes()).hexdigest()
            with self.assertRaises(ValueError): solapes.generar(fuentes)
        self.btc[0]['casos_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.generar()

    def test_rechaza_fuente_unica_duplicada_y_cobertura_distinta(self):
        fuentes = self.guardar()
        for incorrectas in (fuentes[:1], [fuentes[0], fuentes[0]]):
            with self.assertRaises(ValueError): solapes.generar(incorrectas)
        self.eth = fuente('ETHUSDT', [(0, 1, 'SOLO_STOP_OBSERVADO')], fin=T + 10 * P)
        with self.assertRaisesRegex(ValueError, 'Coberturas'): self.generar()

    def test_rechaza_estres_retraso_horizonte_cambiado_y_casos_omitidos(self):
        original = copy.deepcopy(self.btc)
        cambios = (lambda r: r.update(entrada_diagnostica='ENTRADA_MAS_UNA_VELA_15M'),
                   lambda r: r['casos_aportados'][0].update(instante_entrada_ms=T + P),
                   lambda r: r['casos_aportados'][0].update(fin_exclusivo_ms=T + 7 * P),
                   lambda r: r['casos_aportados'].pop(),
                   lambda r: r['resultados'].reverse())
        for cambiar in cambios:
            self.btc = copy.deepcopy(original); cambiar(self.btc[0])
            self.btc[0]['casos_sha256'] = periodos._hash(self.btc[0]['casos_aportados'])
            with self.assertRaises(ValueError): self.generar()

    def test_rechaza_booleanos_eventos_desconocidos_y_fuera_de_rango(self):
        original = copy.deepcopy(self.btc)
        for cambio in ({'primera_apertura_ms': True}, {'cierre_ms': True},
                       {'primera_apertura_ms': T + 8 * P}, {'diagnostico': {'estado': 'NUEVO'}}):
            self.btc = copy.deepcopy(original)
            self.btc[0]['resultados'][0]['trayectoria']['evento'].update(cambio)
            with self.assertRaises(ValueError): self.generar()

    def test_rechaza_fill_y_resolucion_silenciosa_de_ambiguedad(self):
        original = copy.deepcopy(self.eth)
        for campo, valor in (('seleccionado', 'STOP_PRIMERO'), ('fill_confirmado', True), ('escenarios', {'STOP_PRIMERO': {}})):
            self.eth = copy.deepcopy(original)
            self.eth[0]['resultados'][1]['trayectoria'][campo] = valor
            with self.assertRaises(ValueError): self.generar()
        self.eth = copy.deepcopy(original)
        self.eth[0]['resultados'][1]['trayectoria']['evento']['instante_fill'] = T + 4 * P
        with self.assertRaises(ValueError): self.generar()

    def test_cli_nuevo_no_sobrescribe_y_no_toca_fuentes(self):
        fuentes = self.guardar()
        originales = {f[k]: f[k].read_bytes() for f in fuentes for k in ('casos', 'replay')}
        salida = self.ruta / 'solapes.json'
        args = ['--salida', str(salida)]
        for simbolo, f in zip(('btc', 'eth'), fuentes):
            for campo, valor in f.items(): args += ['--' + simbolo + '-' + campo.replace('_', '-'), str(valor)]
        with patch('builtins.print'): solapes.main(args)
        anterior = salida.read_bytes()
        self.assertEqual(json.loads(anterior)['resumen']['casos'], 6)
        with self.assertRaises(FileExistsError): solapes.main(args)
        self.assertEqual(anterior, salida.read_bytes())
        self.assertEqual(originales, {ruta: ruta.read_bytes() for ruta in originales})


if __name__ == '__main__':
    unittest.main()
