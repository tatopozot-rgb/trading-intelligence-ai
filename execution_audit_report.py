"""Lector E4b Windows de una base OFFLINE cerrada. Sin crear, migrar o reparar."""
import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sqlite3

from execution_audit import informe_auditoria_en
from execution_ledger import APP_ID, texto


class LecturaNoVerificada(ValueError):
    pass


# Esquema E4 conocido. No invocar constructores para inferirlo o migrarlo.
ESQUEMA = {
    'fills': ('entorno cuenta simbolo trade_id orden_id datos', 'entorno cuenta simbolo trade_id', ''),
    'conflictos': ('entorno cuenta simbolo trade_id orden_original orden_recibida original recibido',
                   'entorno cuenta simbolo trade_id recibido', ''),
    'intenciones': ('id_local cuenta simbolo datos estado_local order_id snapshot conflicto',
                    'id_local', 'id_local order_id snapshot'),
    'evidencia_orden': ('id_local clase datos resultado', 'id_local clase datos', ''),
    'paquetes_evaluacion': ('id_local datos hash', 'id_local', 'id_local'),
    'evaluaciones': ('id_local evaluacion_id entrada_hash datos hash', 'id_local evaluacion_id', ''),
    'conflictos_evaluacion': ('id_local evaluacion_id entrada_hash datos hash',
                             'id_local evaluacion_id entrada_hash', ''),
}


@contextmanager
def archivo_estable(ruta):
    """Handle Windows de lectura que niega escritores y reemplazo hasta el cierre.

    No constituye protección frente a administrador hostil, mappings preexistentes
    o manipulación ajena al protocolo. Destinado a archivos locales del proyecto.
    """
    if os.name != 'nt':
        raise LecturaNoVerificada('PLATAFORMA_NO_SOPORTADA')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    abrir = kernel.CreateFileW
    abrir.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                     wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    abrir.restype = wintypes.HANDLE
    cerrar = kernel.CloseHandle
    cerrar.argtypes = (wintypes.HANDLE,)
    cerrar.restype = wintypes.BOOL
    handle = abrir(str(ruta), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise LecturaNoVerificada('ARCHIVO_NO_DISPONIBLE_PARA_LECTURA_ESTABLE')
    try:
        yield
    finally:
        cerrar(handle)


def verificar_archivo(ruta):
    with ruta.open('rb') as archivo:
        cabecera = archivo.read(100)
    if len(cabecera) != 100 or cabecera[:16] != b'SQLite format 3\x00':
        raise LecturaNoVerificada('CABECERA_INVALIDA')
    if cabecera[18:20] != b'\x01\x01':
        raise LecturaNoVerificada('WAL_O_FORMATO_NO_SOPORTADO')
    if any(Path(str(ruta) + sufijo).exists() for sufijo in ('-wal', '-shm', '-journal')):
        raise LecturaNoVerificada('ARCHIVOS_AUXILIARES_PRESENTES')


def verificar_esquema(con):
    if con.execute('PRAGMA application_id').fetchone()[0] != APP_ID:
        raise LecturaNoVerificada('BASE_AJENA')
    if con.execute('PRAGMA user_version').fetchone()[0] != 0:
        raise LecturaNoVerificada('VERSION_NO_SOPORTADA')
    objetos = con.execute("SELECT type,name,sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*'").fetchall()
    if any(r['type'] not in ('table', 'index') for r in objetos):
        raise LecturaNoVerificada('OBJETOS_NO_SOPORTADOS')
    tablas = {r['name']: r['sql'] for r in objetos if r['type'] == 'table'}
    if set(tablas) != set(ESQUEMA):
        raise LecturaNoVerificada('TABLAS_INCOMPATIBLES')
    for nombre, (columnas, primaria, anulables) in ESQUEMA.items():
        if 'VIRTUAL' in tablas[nombre].upper() or 'WITHOUT' in tablas[nombre].upper():
            raise LecturaNoVerificada('TABLA_NO_SOPORTADA')
        pk = primaria.split()
        esperado = [(n, 'INTEGER' if n == 'conflicto' else 'TEXT',
                     int(n not in anulables.split()), '0' if n == 'conflicto' else None,
                     pk.index(n) + 1 if n in pk else 0, 0) for n in columnas.split()]
        actual = [tuple(r)[1:] for r in con.execute('PRAGMA table_xinfo("' + nombre + '")')]
        if actual != esperado:
            raise LecturaNoVerificada('COLUMNAS_INCOMPATIBLES')
    if [r[0] for r in con.execute('PRAGMA quick_check')] != ['ok']:
        raise LecturaNoVerificada('INTEGRIDAD_SQLITE_NO_VERIFICADA')


def leer_auditoria(ruta, id_local):
    base = dict(modo='OFFLINE', solo_lectura=True, historico=True, enviable=False, autorizado=False)
    try:
        texto(id_local, 'id_local')
        ruta = Path(ruta).resolve(strict=True)
        if not ruta.is_file() or not ruta.name.endswith('.offline.sqlite3') or ruta.drive.startswith('\\\\'):
            raise LecturaNoVerificada('RUTA_NO_ADMITIDA')
        with archivo_estable(ruta):
            verificar_archivo(ruta)
            antes = ruta.stat()
            con = sqlite3.connect(ruta.as_uri() + '?mode=ro', uri=True, timeout=1)
            try:
                verificar_archivo(ruta)
                con.row_factory = sqlite3.Row
                con.execute('PRAGMA query_only=ON')
                con.execute('PRAGMA trusted_schema=OFF')
                con.execute('PRAGMA temp_store=MEMORY')
                con.execute('BEGIN')
                if con.execute('PRAGMA journal_mode').fetchone()[0] not in ('delete', 'truncate', 'persist'):
                    raise LecturaNoVerificada('MODO_JOURNAL_NO_SOPORTADO')
                verificar_esquema(con)
                permitidos = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
                con.set_authorizer(lambda accion, *_: sqlite3.SQLITE_OK
                                   if accion in permitidos else sqlite3.SQLITE_DENY)
                informe = informe_auditoria_en(con, id_local)
            finally:
                con.close()
            verificar_archivo(ruta)
            despues = ruta.stat()
            if (antes.st_dev, antes.st_ino, antes.st_size, antes.st_mtime_ns) != (
                    despues.st_dev, despues.st_ino, despues.st_size, despues.st_mtime_ns):
                raise LecturaNoVerificada('ARCHIVO_CAMBIADO_DURANTE_LECTURA')
            return {**informe, **base}
    except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.DatabaseError) as error:
        return {**base, 'estado': 'NO_VERIFICADO', 'error_tipo': type(error).__name__,
                'motivo': str(error) if isinstance(error, LecturaNoVerificada) else 'LECTURA_RECHAZADA'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--id', required=True, dest='id_local')
    args = parser.parse_args(argv)
    informe = leer_auditoria(args.base, args.id_local)
    print(json.dumps(informe, ensure_ascii=True, allow_nan=False))
    return {'REGISTRO_INTEGRO': 0, 'DISCREPANCIA': 1}.get(informe['estado'], 2)


if __name__ == '__main__':
    raise SystemExit(main())
