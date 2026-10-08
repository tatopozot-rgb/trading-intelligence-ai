"""Fixtures JSON temporales; sin red, SQLite ni datos operativos."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis_engine import INTERVALOS_MS
from historical_dataset import cargar_dataset, analizar_dataset
from market_http import DatosInvalidos


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ruta = self.root / 'manifest.json'
        self.ahora = 1_790_121_600_000
        self.m = dict(version=1, simbolo='BTCUSDT', origen_declarado='FIXTURE SINTETICO', series={})
        self.filas = {}
        for marco, paso in INTERVALOS_MS.items():
            filas = []
            for i in range(201):
                t = (self.ahora // paso - 200 + i) * paso
                precio = 100 + i*.05 + (.5 if i%2 else -.5)
                filas.append(dict(tiempo_apertura=t, tiempo_cierre=t+paso-1,
                                  apertura=precio, cierre=precio, maximo=precio+1,
                                  minimo=precio-1, volumen=1000))
            self.filas[marco] = filas
            self.guardar_serie(marco)
        self.guardar()
        for destino in ('requests.sessions.Session.request', 'sqlite3.connect'):
            p = patch(destino, side_effect=AssertionError('Efecto externo prohibido'))
            p.start(); self.addCleanup(p.stop)

    def guardar_serie(self, marco):
        filas = self.filas[marco]
        data = json.dumps(filas).encode()
        (self.root / (marco+'.json')).write_bytes(data)
        self.m['series'][marco] = dict(archivo=marco+'.json', sha256=hashlib.sha256(data).hexdigest(),
                                     filas=len(filas), inicio_ms=filas[0]['tiempo_apertura'],
                                     fin_ms=filas[-1]['tiempo_cierre'])

    def guardar(self):
        self.ruta.write_text(json.dumps(self.m), encoding='utf-8')

    def test_integracion_sin_escrituras_y_sin_certificar_procedencia(self):
        antes = {p.name:p.read_bytes() for p in self.root.iterdir()}
        r = analizar_dataset(self.ruta, self.ahora)
        self.assertEqual(r['analisis']['simbolo'], 'BTCUSDT')
        self.assertFalse(r['dataset']['procedencia_verificada'])
        self.assertEqual(r['dataset']['manifiesto_sha256'], hashlib.sha256(antes['manifest.json']).hexdigest())
        self.assertEqual(antes, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_alteracion_archivo_rechazada(self):
        with (self.root/'1h.json').open('ab') as f: f.write(b' ')
        with self.assertRaisesRegex(DatosInvalidos, 'Huella'): cargar_dataset(self.ruta)

    def test_traversal_y_rutas_rechazadas(self):
        for nombre in ('../1h.json', 'C:\\privado.json', '/tmp/a.json', 'a:b.json'):
            self.m['series']['1h']['archivo'] = nombre
            self.guardar()
            with self.subTest(nombre=nombre), self.assertRaises(DatosInvalidos): cargar_dataset(self.ruta)

    def test_rango_y_conteo_falsos_rechazados(self):
        for campo in ('inicio_ms', 'fin_ms', 'filas'):
            self.m['series']['1h'][campo] += 1
            self.guardar()
            with self.subTest(campo=campo), self.assertRaises(DatosInvalidos): cargar_dataset(self.ruta)
            self.m['series']['1h'][campo] -= 1

    def test_hueco_antiguo_fuera_de_ventana_rechazado(self):
        del self.filas['1h'][1]
        self.guardar_serie('1h'); self.guardar()
        with self.assertRaises(DatosInvalidos): cargar_dataset(self.ruta)

    def test_json_ambiguo_rechazado(self):
        for contenido in ('{"version":1,"version":1}', '{"x":NaN}', '[]'):
            self.ruta.write_text(contenido, encoding='utf-8')
            with self.subTest(contenido=contenido), self.assertRaises(DatosInvalidos): cargar_dataset(self.ruta)

    def test_metadatos_invalidos(self):
        for campo, valor in (('version', True), ('origen_declarado',''), ('simbolo','../BTC')):
            anterior = self.m[campo]; self.m[campo] = valor; self.guardar()
            with self.subTest(campo=campo), self.assertRaises(DatosInvalidos): cargar_dataset(self.ruta)
            self.m[campo] = anterior

    def test_archivo_ausente(self):
        self.m['series']['1h']['archivo'] = 'ausente.json'; self.guardar()
        with self.assertRaises(DatosInvalidos): cargar_dataset(self.ruta)

    def test_manifiesto_grande_rechazado(self):
        self.ruta.write_bytes(b' '*65_537)
        with self.assertRaises(DatosInvalidos): cargar_dataset(self.ruta)


if __name__ == '__main__': unittest.main()
