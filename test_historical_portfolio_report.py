"""Adapter H6c: fixtures only, network/SQLite prohibited."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import historical_overlap as solapes
import historical_periods as periodos
import historical_portfolio_report as informe
from test_historical_overlap import fuente, T, P


class PortfolioReportTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.ruta = Path(temporal.name)
        for destino in ('socket.create_connection', 'sqlite3.connect'):
            bloqueo = patch(destino, side_effect=AssertionError('No red ni BD'))
            bloqueo.start()
            self.addCleanup(bloqueo.stop)
        self.datos = [fuente('BTCUSDT', [(0, 2, 'SOLO_OBJETIVO_OBSERVADO'),
            (2, 3, 'SOLO_STOP_OBSERVADO'), (4, 6, 'APERTURA_EN_O_BAJO_STOP')]),
            fuente('ETHUSDT', [(0, 2, 'APERTURA_EN_O_SOBRE_OBJETIVO'),
            (2, 4, 'AMBIGUO_AMBOS_NIVELES'), (6, None, None)])]
        precios = {'SOLO_OBJETIVO_OBSERVADO':104, 'SOLO_STOP_OBSERVADO':99,
            'STOP_PRIMERO':99, 'OBJETIVO_PRIMERO':104,
            'APERTURA_EN_O_BAJO_STOP':97, 'APERTURA_EN_O_SOBRE_OBJETIVO':106}
        for datos, _ in self.datos:
            for r in datos['resultados']:
                r['plan_hipotetico'].update(stop_precio=99, objetivo_precio=104)
                for nombre, escenario in r['trayectoria']['escenarios'].items():
                    escenario['salida_aportada'] = precios[nombre]
        self.parametros = dict(capital_inicial='100', riesgo_operacion_pct='.1',
                               perdida_diaria_pct='100', max_posiciones=3)

    def escribir(self, nombre, dato):
        ruta = self.ruta / nombre
        ruta.write_text(json.dumps(dato, allow_nan=False), encoding='utf-8')
        return ruta, hashlib.sha256(ruta.read_bytes()).hexdigest()

    def preparar(self):
        fuentes = []
        for i, (datos, replay) in enumerate(self.datos):
            rr, hr = self.escribir(f'replay{i}.json', replay)
            datos['replay_sha256'] = hr
            rc, hc = self.escribir(f'casos{i}.json', datos)
            fuentes.append(dict(casos=rc, replay=rr, sha256_casos_esperado=hc, sha256_replay_esperado=hr))
        mapa = solapes.generar(fuentes)
        rm, hm = self.escribir('mapa.json', mapa)
        return fuentes, dict(mapa=rm, sha256_mapa_esperado=hm)

    def generar(self, **cambios):
        fuentes, args = self.preparar()
        return informe.generar(fuentes, **args, **(self.parametros | cambios))

    def test_cuatro_escenarios_todas_identidades_y_determinismo(self):
        fuentes, args = self.preparar()
        hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.ruta.iterdir()}
        r = informe.generar(fuentes, **args, **self.parametros)
        self.assertEqual(r, informe.generar(fuentes[::-1], **args, **self.parametros))
        self.assertEqual(r['resumen'], dict(casos=6, censurados=1, ambiguos=1))
        self.assertEqual(len(r['variantes']), 4)
        ids = {c['id'] for c in r['identidades']}
        for v in r['variantes'].values():
            self.assertEqual(ids, {d['id'] for d in v['cartera']['decisiones']})
            self.assertEqual(ids, {c['id'] for c in v['candidatos']})
        self.assertFalse(r['ejecutable'])
        self.assertFalse(r['limites_pnl_garantizados'])
        self.assertIsNone(r['ganador_seleccionado'])
        self.assertEqual(hashes, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.ruta.iterdir()})

    def test_tiempo_aplica_no_ambiguos_y_gaps_permanecen_exactos(self):
        r = self.generar()
        a = r['variantes']['TEMPRANA_STOP_PRIMERO']['candidatos']
        b = r['variantes']['TARDIA_STOP_PRIMERO']['candidatos']
        por_a, por_b = ({c['id']:c for c in datos} for datos in (a,b))
        for identidad in ('BTCUSDT_000000', 'BTCUSDT_000001', 'ETHUSDT_000001'):
            self.assertEqual(por_b[identidad]['salida_ms']-por_a[identidad]['salida_ms'], P-1)
            self.assertEqual(por_b[identidad]['salida'], por_a[identidad]['salida'])
        for identidad in ('BTCUSDT_000002', 'ETHUSDT_000000'):
            self.assertEqual(por_a[identidad], por_b[identidad])
        self.assertEqual(por_a['BTCUSDT_000002']['salida'], '97')

    def test_ambiguo_preserva_ambos_precios_sin_sumar_resultado_aislado(self):
        r = self.generar()
        for tiempo in informe.TIEMPOS:
            for barrera, precio in (('STOP_PRIMERO','99'), ('OBJETIVO_PRIMERO','104')):
                v = r['variantes'][f'{tiempo}_{barrera}']
                c = next(c for c in v['candidatos'] if c['id']=='ETHUSDT_000001')
                self.assertEqual(c['salida'], precio)
                self.assertNotIn('resultado_usd', json.dumps(v))

    def test_censura_no_cierre_al_fin_y_solo_aceptados_abiertos(self):
        r = self.generar()
        for v in r['variantes'].values():
            c = next(c for c in v['candidatos'] if c['id']=='ETHUSDT_000002')
            self.assertIsNone(c['salida_ms'])
            self.assertIsNone(c['salida'])
            self.assertIn(c['id'], [p['id'] for p in v['cartera']['abiertas']])
            self.assertFalse(any(e['id']==c['id'] and e['tipo']=='CIERRE' for e in v['cartera']['eventos']))

    def test_rechazos_conservados_y_sensibilidad_de_trayectoria(self):
        r = self.generar(max_posiciones=1)
        a, b = (r['variantes'][f'{tiempo}_STOP_PRIMERO']['cartera'] for tiempo in informe.TIEMPOS)
        da, db = ({d['id']:d for d in datos['decisiones']} for datos in (a,b))
        self.assertEqual(da['BTCUSDT_000001']['estado'], 'ACEPTADO')
        self.assertEqual(db['BTCUSDT_000001']['estado'], 'RECHAZADO')
        self.assertEqual(set(da), set(db))
        for v in r['variantes'].values():
            self.assertEqual(sum(v['rechazos_por_motivo'].values()), v['cartera']['metricas']['rechazados'])

    def test_hashes_externos_no_se_autogeneran(self):
        fuentes, args = self.preparar()
        for campo in ('sha256_casos_esperado', 'sha256_replay_esperado'):
            malas = copy.deepcopy(fuentes)
            malas[0][campo] = '0'*64
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                informe.generar(malas, **args, **self.parametros)
        args['sha256_mapa_esperado'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            informe.generar(fuentes, **args, **self.parametros)

    def test_mapa_rehash_no_oculta_cambio_identidad_intervalo_o_fuente(self):
        fuentes, args = self.preparar()
        original = json.loads(args['mapa'].read_text(encoding='utf-8'))
        for mutacion in ('duplicado','falta','fecha','bool','fuente'):
            mapa = copy.deepcopy(original)
            if mutacion=='duplicado': mapa['casos'].append(mapa['casos'][0])
            if mutacion=='falta': mapa['casos'].pop()
            if mutacion=='fecha': mapa['casos'][0]['salida_hipotetica']['limite_superior_ms'] += 1
            if mutacion=='bool': mapa['casos'][0]['indice_original'] = False
            if mutacion=='fuente': mapa['fuentes']['BTCUSDT']['casos_archivo_sha256'] = '0'*64
            rm, hm = self.escribir('alterado.json', mapa)
            with self.subTest(mutacion=mutacion), self.assertRaises(ValueError):
                informe.generar(fuentes, mapa=rm, sha256_mapa_esperado=hm, **self.parametros)

    def test_salida_en_barrera_incoherente_rechazada(self):
        self.datos[0][0]['resultados'][0]['trayectoria']['escenarios']['SOLO_OBJETIVO_OBSERVADO']['salida_aportada']=103
        with self.assertRaisesRegex(ValueError, 'barrera'):
            self.generar()

    def test_gap_en_lado_incorrecto_rechazado(self):
        self.datos[0][0]['resultados'][2]['trayectoria']['escenarios']['APERTURA_EN_O_BAJO_STOP']['salida_aportada']=101
        with self.assertRaisesRegex(ValueError, 'gap'):
            self.generar()

    def test_niveles_invalidos_rechazados_aun_con_hash_valido(self):
        self.datos[0][0]['resultados'][0]['plan_hipotetico']['stop_precio']=105
        with self.assertRaisesRegex(ValueError, 'LONG'):
            self.generar()

    def test_limites_explicitos_validan_y_no_modifican_config(self):
        for campo, valor in [('capital_inicial','NaN'), ('riesgo_operacion_pct',True),
                              ('perdida_diaria_pct','-1'), ('max_posiciones',False)]:
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                self.generar(**{campo:valor})

    def test_cli_exclusivo_y_json_reproducible(self):
        fuentes, parametros = self.preparar()
        args = []
        for prefijo, f in zip(('btc','eth'), fuentes):
            for campo, valor in f.items(): args += [f'--{prefijo}-{campo.replace("_","-")}', str(valor)]
        for campo, valor in (parametros | self.parametros).items():
            args += ['--'+campo.replace('_','-'), str(valor)]
        salida = self.ruta/'resultado.json'
        args += ['--salida',str(salida)]
        with patch('builtins.print'):
            self.assertEqual(informe.main(args), 0)
        esperado = informe.generar(fuentes, **parametros, **self.parametros)
        self.assertEqual(json.loads(salida.read_text(encoding='utf-8')), esperado)
        antes = salida.read_bytes()
        with patch.object(informe, 'generar', side_effect=AssertionError('No repetir cálculo')):
            with self.assertRaises(FileExistsError): informe.main(args)
        self.assertEqual(antes, salida.read_bytes())


if __name__ == '__main__':
    unittest.main()
