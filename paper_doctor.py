"""Diagnóstico técnico PAPER de solo lectura; no inicia ni repara el sistema."""
import sys

sys.dont_write_bytecode = True

import argparse
import ast
from datetime import datetime, timezone
from importlib import metadata
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import time


DEPENDENCIAS = ('requests', 'pandas')
_SONDEO = '''import contextlib, importlib, io, json, sys
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        importlib.import_module(sys.argv[1])
    resultado = {"ok": True}
except Exception as error:
    resultado = {"ok": False, "tipo": type(error).__name__,
                 "mensaje": str(error)[:4096], "winerror": getattr(error, "winerror", None)}
print(json.dumps(resultado, ensure_ascii=True))
'''


def clasificar_error_importacion(tipo, mensaje='', winerror=None):
    """Clasifica indicios; no acredita por sí solo una política de Windows."""
    detalle = mensaje.lower()
    if (winerror in (4551, 577) or any(s in detalle for s in (
            'application control', 'control de aplicaciones', 'app control',
            'blocked by group policy', 'bloqueado por una directiva', 'winerror 4551'))):
        return 'POSIBLE_BLOQUEO_APPLICATION_CONTROL'
    if 'dll' in detalle and any(s in detalle for s in ('failed', 'error', 'fall', 'load', 'carga')):
        return 'ERROR_CARGA_DLL'
    if tipo == 'ModuleNotFoundError':
        return 'MODULO_NO_ENCONTRADO'
    if tipo == 'ImportError':
        return 'IMPORT_ERROR'
    if tipo == 'TimeoutExpired':
        return 'TIEMPO_AGOTADO'
    return 'ERROR_IMPORTACION'


def sondear_dependencia(nombre):
    """Importa solo nombres fijos en un proceso aislado del mismo intérprete."""
    if nombre not in DEPENDENCIAS:
        raise ValueError('Dependencia no admitida.')
    try:
        version = metadata.version(nombre)
    except metadata.PackageNotFoundError:
        version = None
    except (OSError, ValueError):
        version = 'NO_VERIFICADA'
    salida = {'version_instalada_metadata':version, 'importable':False,
              'metodo':'MISMO_INTERPRETE_SUBPROCESO_AISLADO_SIN_BYTECODE'}
    try:
        proceso = subprocess.run([sys.executable, '-I', '-B', '-c', _SONDEO, nombre],
            capture_output=True, text=True, timeout=15, check=False)
        if proceso.returncode != 0:
            return {**salida, 'estado':'ERROR', 'codigo':'SUBPROCESO_FALLIDO',
                    'codigo_salida':proceso.returncode}
        dato = json.loads(proceso.stdout)
        if type(dato) is not dict or type(dato.get('ok')) is not bool:
            raise ValueError('Respuesta de sondeo inválida.')
        if dato['ok']:
            return {**salida, 'estado':'OK', 'importable':True}
        if type(dato.get('tipo')) is not str or type(dato.get('mensaje')) is not str:
            raise ValueError('Error de sondeo inválido.')
        codigo = clasificar_error_importacion(dato['tipo'], dato['mensaje'], dato.get('winerror'))
        return {**salida, 'estado':'ERROR', 'codigo':codigo, 'tipo_error':dato['tipo']}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {**salida, 'estado':'ERROR', 'codigo':clasificar_error_importacion(
            type(error).__name__, str(error), getattr(error, 'winerror', None)),
            'tipo_error':type(error).__name__}
    except (ValueError, TypeError):
        return {**salida, 'estado':'ERROR', 'codigo':'RESPUESTA_SONDEO_INVALIDA'}


def _leer(ruta, limite=262144):
    with ruta.open('rb') as archivo:
        contenido = archivo.read(limite + 1)
    if len(contenido) > limite:
        raise ValueError('Archivo demasiado grande.')
    return contenido.decode('utf-8-sig')


def _json(ruta):
    def pares(items):
        dato = {}
        for k, v in items:
            if k in dato:
                raise ValueError('Clave duplicada.')
            dato[k] = v
        return dato

    def no_finito(_):
        raise ValueError('Constante no finita.')

    dato = json.loads(_leer(ruta), object_pairs_hook=pares, parse_constant=no_finito)
    if type(dato) is not dict:
        raise ValueError('Objeto requerido.')
    return dato


def leer_configuracion(directorio):
    """Inspecciona literales; no ejecuta un config.py de la ruta suministrada."""
    try:
        arbol = ast.parse(_leer(directorio/'config.py'))
        valores = {}
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                destinos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
                for destino in destinos:
                    if isinstance(destino, ast.Name) and destino.id in ('MODO', 'USAR_DINERO_REAL'):
                        if nodo not in arbol.body or destino.id in valores or isinstance(nodo, ast.AugAssign):
                            raise ValueError('Configuración dinámica o ambigua.')
                        valores[destino.id] = ast.literal_eval(nodo.value)
        if set(valores) != {'MODO', 'USAR_DINERO_REAL'}:
            raise ValueError('Faltan ajustes explícitos.')
        correcto = valores['MODO'] == 'PAPER' and valores['USAR_DINERO_REAL'] is False
        return {'estado':'OK' if correcto else 'BLOQUEADO', 'paper_y_real_false':correcto,
                'metodo':'LECTURA_ESTATICA_DE_LITERALES_NO_EJECUTADA'}
    except FileNotFoundError:
        return {'estado':'NO_VERIFICADO', 'codigo':'CONFIG_AUSENTE'}
    except (OSError, UnicodeError, ValueError, SyntaxError, RecursionError):
        return {'estado':'NO_VERIFICADO', 'codigo':'CONFIG_NO_INTERPRETABLE'}


def conciliar_base(base):
    try:
        if not base.is_file():
            return {'estado':'NO_VERIFICADO', 'codigo':'BD_AUSENTE', 'solo_lectura':True}
        with base.open('rb') as archivo:
            cabecera = archivo.read(20)
        # Evita que SQLite cree/actualice sidecars al abrir una base WAL.
        if ((cabecera[:16] == b'SQLite format 3\x00' and cabecera[18:20] != b'\x01\x01') or
                any(base.with_name(base.name + sufijo).exists() for sufijo in ('-wal', '-shm', '-journal'))):
            return {'estado':'NO_VERIFICADO', 'codigo':'BD_CON_JOURNAL_NO_ABIERTA', 'solo_lectura':True}
        # Módulo de esta instalación; nunca importa código del directorio fixture.
        from paper_report import informe
        reporte = informe(base)  # El lector existente usa mode=ro y query_only.
        return {'estado':reporte['estado'], 'solo_lectura':True,
                'conteos':reporte['conteos'], 'problemas':reporte['problemas']}
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, ImportError) as error:
        return {'estado':'ERROR', 'codigo':'CONCILIACION_NO_COMPLETADA',
                'tipo_error':type(error).__name__, 'solo_lectura':True}


def leer_cooldown(directorio, ahora):
    try:
        dato = _json(directorio/'market_cooldown.json')
        if 'hasta' not in dato:
            raise ValueError('Plazo ausente.')
        status = dato.get('status')
        if status is not None and (type(status) is not int or status not in (403, 418, 429, 451)):
            raise ValueError('Estado HTTP inválido.')
        if dato['hasta'] is None or status == 451:
            return {'estado':'BLOQUEADO', 'codigo':'REQUIERE_REVISION_LOCAL', 'http_status':status}
        if isinstance(dato['hasta'], bool):
            raise ValueError('Plazo booleano.')
        hasta = float(dato['hasta'])
        if not math.isfinite(hasta) or hasta <= 0:
            raise ValueError('Plazo inválido.')
        return {'estado':'BLOQUEADO' if ahora < hasta else 'EXPIRADO',
                'hasta_epoch':hasta, 'http_status':status,
                'red_disponible':'NO_VERIFICADA', 'bloqueo_memoria':'NO_VERIFICADO'}
    except FileNotFoundError:
        return {'estado':'SIN_REGISTRO', 'red_disponible':'NO_VERIFICADA',
                'bloqueo_memoria':'NO_VERIFICADO'}
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        return {'estado':'BLOQUEADO', 'codigo':'COOLDOWN_NO_INTERPRETABLE'}


def leer_runner(directorio, ahora, max_edad):
    salida = {'proceso_vivo':'NO_VERIFICADO', 'metodo':'SOLO_REGISTRO_GUARDADO'}
    try:
        dato = _json(directorio/'runner_status.json')
        if dato.get('modo') != 'PAPER':
            raise ValueError('Registro no PAPER.')
        estado = dato.get('estado')
        if estado not in ('ACTIVO', 'DETENIENDO', 'DETENIDO', 'ERROR'):
            raise ValueError('Estado inválido.')
        # El latido ACTIVO usa heartbeat_utc; el apagado publica fecha.
        campo_fecha = ('heartbeat_utc' if estado == 'ACTIVO' and 'heartbeat_utc' in dato else 'fecha')
        instante = datetime.fromisoformat(dato[campo_fecha])
        if instante.tzinfo is None:
            raise ValueError('Fecha sin zona horaria.')
        edad = ahora - instante.timestamp()
        if edad < 0:
            raise ValueError('Registro futuro.')
        salud = dato.get('salud')
        if type(salud) is not dict:
            raise ValueError('Salud ausente.')
        resumen = {}
        for nombre in ('scanner', 'monitor', 'bandeja'):
            componente = salud.get(nombre)
            if type(componente) is not dict:
                raise ValueError('Componente ausente.')
            estado_componente = componente.get('estado')
            if estado_componente not in ('PENDIENTE', 'EN_CURSO', 'OK', 'DEGRADADO', 'ERROR', 'CANCELADO', 'SIN_DATOS'):
                raise ValueError('Estado de salud desconocido.')
            detalle = {'estado_registrado':estado_componente}
            for k in ('ciclos', 'errores_total'):
                n = componente.get(k)
                if type(n) is not int or n < 0:
                    raise ValueError('Contador inválido.')
                detalle[k] = n
            resumen[nombre] = detalle
        return {**salida, 'estado':'REGISTRO_RECIENTE' if edad <= max_edad else 'REGISTRO_ANTIGUO',
                'estado_registrado':estado, 'fecha_registrada':dato[campo_fecha],
                'edad_registro_seg':round(edad, 3), 'salud_registrada':resumen}
    except FileNotFoundError:
        return {**salida, 'estado':'NO_VERIFICADO', 'codigo':'ESTADO_AUSENTE'}
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        return {**salida, 'estado':'NO_VERIFICADO', 'codigo':'ESTADO_NO_INTERPRETABLE'}


def diagnosticar(*, directorio, base, ahora_epoch=None, max_edad_estado_seg=180):
    """No inicia sesiones ni evalúa rentabilidad, disponibilidad de red o permisos."""
    root, ruta = Path(directorio).resolve(), Path(base).resolve()
    ahora = time.time() if ahora_epoch is None else ahora_epoch
    for valor in (ahora, max_edad_estado_seg):
        if type(valor) not in (int, float) or not math.isfinite(valor) or valor < 0:
            raise ValueError('Tiempo/límite no negativo y finito requerido.')
    configuracion = leer_configuracion(root)
    dependencias = {nombre:sondear_dependencia(nombre) for nombre in DEPENDENCIAS}
    conciliacion = conciliar_base(ruta)
    cooldown = leer_cooldown(root, ahora)
    runner = leer_runner(root, ahora, max_edad_estado_seg)
    bloqueos = []
    if configuracion['estado'] == 'BLOQUEADO': bloqueos.append('CONFIGURACION_NO_PAPER')
    if any(not d['importable'] for d in dependencias.values()): bloqueos.append('DEPENDENCIAS_NO_IMPORTABLES')
    if conciliacion['estado'] in ('DISCREPANCIA', 'ERROR'): bloqueos.append('CONCILIACION')
    if cooldown['estado'] == 'BLOQUEADO': bloqueos.append('COOLDOWN_HTTP')
    if runner['estado'] == 'REGISTRO_RECIENTE' and (runner['estado_registrado'] == 'ERROR' or any(
            c['estado_registrado'] in ('ERROR', 'DEGRADADO') for c in runner['salud_registrada'].values())):
        bloqueos.append('SALUD_REGISTRADA_CON_ERRORES')
    pendientes = []
    if configuracion['estado'] == 'NO_VERIFICADO': pendientes.append('CONFIGURACION')
    if conciliacion['estado'] == 'NO_VERIFICADO': pendientes.append('BASE_DATOS')
    if runner['estado'] != 'REGISTRO_RECIENTE': pendientes.append('REGISTRO_RUNNER')
    estado = 'BLOQUEADO' if bloqueos else ('NO_VERIFICADO' if pendientes else 'OK_LOCAL')
    adaptador = (Path(__file__).resolve().parent/'broker_adapters.py').is_file()
    return {'schema':'PAPER_DOCTOR_V1', 'estado':estado, 'aptitud_tecnica':'COMPROBACIONES_LOCALES_PAPER',
        'solo_lectura':True, 'no_evalua_rentabilidad':True, 'autoriza_operar':False,
        'directorio':str(root), 'base':str(ruta), 'observado_utc':datetime.fromtimestamp(ahora, timezone.utc).isoformat(),
        'interprete':sys.executable, 'python':sys.version.split()[0],
        'configuracion':configuracion, 'dependencias':dependencias, 'conciliacion':conciliacion,
        'cooldown_http':cooldown, 'runner':runner, 'bloqueos':bloqueos, 'pendientes_locales':pendientes,
        'capacidades':{
            'binance':{'via':'DATOS_PUBLICOS_SIN_CUENTA', 'conexion_probada':False,
                       'archivo_adaptador_snapshots_presente':adaptador, 'permiso_envio':False},
            'xm':{'via':'SNAPSHOTS_SINTETICOS_O_EXPORTACION_DEMO_MT5', 'conexion_probada':False,
                  'archivo_adaptador_snapshots_presente':adaptador, 'cuenta':'NO_VERIFICADA',
                  'terminal':'NO_INSPECCIONADO', 'permiso_envio':False}},
        'limites':['El registro ACTIVO no prueba que el proceso esté vivo.',
                   'Cooldown ausente/expirado no demuestra acceso de red.',
                   'Importabilidad y conciliación no demuestran rentabilidad.',
                   'No se ha iniciado ni autorizado ninguna sesión.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directorio', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--max-edad-estado-seg', type=float, default=180)
    args = parser.parse_args(argv)
    try:
        resultado = diagnosticar(directorio=args.directorio,
            base=args.base if args.base is not None else args.directorio/'trading.db',
            max_edad_estado_seg=args.max_edad_estado_seg)
    except (OSError, ValueError, OverflowError) as error:
        print(json.dumps({'estado':'NO_VERIFICADO', 'solo_lectura':True, 'tipo_error':type(error).__name__}))
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False))
    return {'OK_LOCAL':0, 'BLOQUEADO':1, 'NO_VERIFICADO':2}[resultado['estado']]


if __name__ == '__main__':
    raise SystemExit(main())
