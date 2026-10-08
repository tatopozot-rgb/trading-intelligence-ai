"""Ledger de fixtures OFFLINE. Sin red, envío, autorización ni acceso a trading.db."""
from contextlib import contextmanager
from decimal import Decimal, localcontext, Inexact, Rounded
import json
from pathlib import Path
import re
import sqlite3

from execution_filters import decimal_texto

APP_ID = 0x54494F46
ENTORNO = 'TESTNET_FIXTURE'


def texto(valor, nombre):
    if type(valor) is not str or not 1<=len(valor)<=100 or valor.strip()!=valor or any(ord(c)<32 for c in valor):
        raise ValueError('Identificador inválido: '+nombre)
    return valor


def identificador(valor, nombre):
    if type(valor) is not str or re.fullmatch(r'0|[1-9][0-9]{0,39}',valor) is None:
        raise ValueError('ID numérico textual inválido: '+nombre)
    return valor


def clave_orden(cuenta, simbolo, orden_id):
    return (ENTORNO,texto(cuenta,'cuenta'),texto(simbolo,'simbolo'),identificador(orden_id,'orden_id'))


def serializar(dato):
    return json.dumps(dato,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))


class LedgerOffline:
    def __init__(self, ruta):
        self.ruta = Path(ruta).resolve()
        if not self.ruta.name.endswith('.offline.sqlite3'):
            raise ValueError('Se exige archivo separado con sufijo .offline.sqlite3.')
        with self.conectar() as con:
            tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            app_id = con.execute('PRAGMA application_id').fetchone()[0]
            if (tablas and app_id!=APP_ID) or (not tablas and app_id not in (0,APP_ID)):
                raise ValueError('Base ajena: no se inicializa ni migra.')
            con.execute('BEGIN IMMEDIATE')
            con.execute(f'PRAGMA application_id={APP_ID}')
            con.execute('''CREATE TABLE IF NOT EXISTS fills (
                entorno TEXT NOT NULL, cuenta TEXT NOT NULL, simbolo TEXT NOT NULL,
                trade_id TEXT NOT NULL, orden_id TEXT NOT NULL, datos TEXT NOT NULL,
                PRIMARY KEY(entorno,cuenta,simbolo,trade_id))''')
            con.execute('''CREATE TABLE IF NOT EXISTS conflictos (
                entorno TEXT NOT NULL, cuenta TEXT NOT NULL, simbolo TEXT NOT NULL,
                trade_id TEXT NOT NULL, orden_original TEXT NOT NULL, orden_recibida TEXT NOT NULL,
                original TEXT NOT NULL, recibido TEXT NOT NULL,
                PRIMARY KEY(entorno,cuenta,simbolo,trade_id,recibido))''')

    @contextmanager
    def conectar(self):
        con = sqlite3.connect(self.ruta,timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def registrar_fill(self, fill):
        campos = {'entorno','cuenta','simbolo','trade_id','orden_id','cantidad','precio','comision','activo_comision'}
        if not isinstance(fill,dict) or set(fill)!=campos or fill['entorno']!=ENTORNO:
            raise ValueError('Solo fill completo TESTNET_FIXTURE.')
        _,cuenta,simbolo,orden = clave_orden(fill['cuenta'],fill['simbolo'],fill['orden_id'])
        trade = identificador(fill['trade_id'],'trade_id')
        texto(fill['activo_comision'],'activo_comision')
        if decimal_texto(fill['cantidad'])<=0 or decimal_texto(fill['precio'])<=0:
            raise ValueError('Cantidad/precio deben ser positivos.')
        decimal_texto(fill['comision'])  # Formato no negativo, cero permitido.
        recibido = serializar(fill)
        clave = (ENTORNO,cuenta,simbolo,trade)
        with self.conectar() as con:
            con.execute('BEGIN IMMEDIATE')
            previo = con.execute('SELECT datos,orden_id FROM fills WHERE entorno=? AND cuenta=? AND simbolo=? AND trade_id=?',clave).fetchone()
            if previo is None:
                con.execute('INSERT INTO fills VALUES(?,?,?,?,?,?)',(*clave,orden,recibido))
                return {'estado':'REGISTRADO','enviable':False}
            if previo['datos']==recibido:
                return {'estado':'DUPLICADO_IDENTICO','enviable':False}
            con.execute('INSERT OR IGNORE INTO conflictos VALUES(?,?,?,?,?,?,?,?)',
                        (*clave,previo['orden_id'],orden,previo['datos'],recibido))
            return {'estado':'DISCREPANCIA','enviable':False}

    def conciliar(self, cuenta, simbolo, orden_id, cantidad_reportada=None, quote_reportado=None):
        """Compara evidencia suministrada, no declara estado de orden/posición."""
        clave = clave_orden(cuenta,simbolo,orden_id)
        if (cantidad_reportada is None)!=(quote_reportado is None):
            raise ValueError('Aportar ambos acumulados o ninguno.')
        esperado = None if cantidad_reportada is None else (decimal_texto(cantidad_reportada),decimal_texto(quote_reportado))
        with self.conectar() as con:
            con.execute('BEGIN')
            return self._conciliar_en(con, clave, esperado)

    def _conciliar_en(self, con, clave, esperado):
        """Reutiliza la transacción de lectura del llamador para evidencia coherente."""
        filas = con.execute('SELECT datos FROM fills WHERE entorno=? AND cuenta=? AND simbolo=? AND orden_id=? ORDER BY trade_id',clave).fetchall()
        conflictos = con.execute('SELECT count(*) FROM conflictos WHERE entorno=? AND cuenta=? AND simbolo=? AND (orden_original=? OR orden_recibida=?)',(*clave,clave[3])).fetchone()[0]
        with localcontext() as contexto:
            contexto.prec=200
            contexto.traps[Inexact]=True
            contexto.traps[Rounded]=True
            cantidad,quote = Decimal(0),Decimal(0)
            comisiones = {}
            for fila in filas:
                dato = json.loads(fila['datos'])
                q,p,c = (decimal_texto(dato[k]) for k in ('cantidad','precio','comision'))
                cantidad += q
                quote += q*p
                activo = dato['activo_comision']
                comisiones[activo] = comisiones.get(activo,Decimal(0))+c
            problemas = []
            if conflictos:
                problemas.append('FILL_CONFLICTIVO')
            if esperado is not None and (cantidad,quote)!=esperado:
                problemas.append('ACUMULADOS_DISTINTOS')
            return {'modo':'OFFLINE','enviable':False,
                    'estado':'DISCREPANCIA' if problemas else ('SIN_EVIDENCIA_ACUMULADA' if esperado is None else 'ACUMULADOS_COINCIDEN'),
                    'fills':len(filas),'conflictos':conflictos,'cantidad':format(cantidad,'f'),
                    'quote_bruto':format(quote,'f'),
                    'comisiones_por_activo':{a:format(v,'f') for a,v in sorted(comisiones.items())},
                    'problemas':problemas}
