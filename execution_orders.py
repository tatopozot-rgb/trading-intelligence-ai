"""Máquina de evidencia OFFLINE: no transporte, cuenta real ni autorización."""
import json
import re

from execution_filters import decimal_texto
from execution_ledger import ENTORNO, LedgerOffline, identificador, serializar, texto

TERMINALES = {'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED', 'EXPIRED_IN_MATCH'}
ESTADOS = TERMINALES | {'NEW', 'PARTIALLY_FILLED', 'PENDING_CANCEL'}


def resultado(estado):
    return {'modo': 'OFFLINE', 'enviable': False, 'estado': estado}


def validar_intencion(dato):
    campos = {'id_local', 'entorno', 'cuenta', 'simbolo', 'parametros', 'plan_hash', 'snapshot_hash'}
    if type(dato) is not dict or set(dato) != campos or dato['entorno'] != ENTORNO:
        raise ValueError('Intención completa TESTNET_FIXTURE requerida.')
    for campo in ('id_local', 'cuenta', 'simbolo'):
        texto(dato[campo], campo)
    for campo in ('plan_hash', 'snapshot_hash'):
        if type(dato[campo]) is not str or re.fullmatch('[0-9a-f]{64}', dato[campo]) is None:
            raise ValueError('Hash textual inválido.')
    p = dato['parametros']
    if type(p) is not dict or set(p) != {'symbol', 'side', 'type', 'timeInForce', 'price', 'quantity'}:
        raise ValueError('Parámetros exactos requeridos.')
    if p['symbol'] != dato['simbolo'] or p['side'] not in ('BUY', 'SELL') or p['type'] != 'LIMIT' or p['timeInForce'] not in ('GTC', 'IOC', 'FOK'):
        raise ValueError('Solo fixture LIMIT; no decisión operativa.')
    if decimal_texto(p['price']) <= 0 or decimal_texto(p['quantity']) <= 0:
        raise ValueError('Precio/cantidad no positivos.')


def validar_snapshot(s):
    campos = {'entorno', 'cuenta', 'simbolo', 'client_order_id', 'order_id', 'status',
              'orig_qty', 'executed_qty', 'quote_qty', 'update_time'}
    if type(s) is not dict or set(s) != campos or s['entorno'] != ENTORNO:
        raise ValueError('Snapshot normalizado TESTNET_FIXTURE requerido.')
    for campo in ('cuenta', 'simbolo', 'client_order_id'):
        texto(s[campo], campo)
    identificador(s['order_id'], 'order_id')
    if type(s['status']) is not str or s['status'] not in ESTADOS:
        raise ValueError('Estado desconocido.')
    if type(s['update_time']) is not int or not 0 < s['update_time'] < 2**63:
        raise ValueError('Timestamp entero positivo requerido.')
    original, ejecutada, quote = (decimal_texto(s[c]) for c in ('orig_qty', 'executed_qty', 'quote_qty'))
    if original <= 0 or ejecutada > original or (ejecutada == 0) != (quote == 0):
        raise ValueError('Acumulados incompatibles.')
    if s['status'] in ('NEW', 'REJECTED') and ejecutada != 0:
        raise ValueError('Estado incompatible con fills.')
    if s['status'] == 'PARTIALLY_FILLED' and not 0 < ejecutada < original:
        raise ValueError('Parcial inválido.')
    if s['status'] == 'FILLED' and ejecutada != original:
        raise ValueError('Total inválido.')


class OrdenesOffline(LedgerOffline):
    def __init__(self, ruta):
        super().__init__(ruta)
        with self.conectar() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('''CREATE TABLE IF NOT EXISTS intenciones (
                id_local TEXT PRIMARY KEY, cuenta TEXT NOT NULL, simbolo TEXT NOT NULL,
                datos TEXT NOT NULL, estado_local TEXT NOT NULL,
                order_id TEXT, snapshot TEXT, conflicto INTEGER NOT NULL DEFAULT 0,
                UNIQUE(cuenta,simbolo,order_id))''')
            con.execute('''CREATE TABLE IF NOT EXISTS evidencia_orden (
                id_local TEXT NOT NULL, clase TEXT NOT NULL, datos TEXT NOT NULL,
                resultado TEXT NOT NULL, PRIMARY KEY(id_local,clase,datos))''')

    @staticmethod
    def _fila(con, id_local):
        texto(id_local, 'id_local')
        fila = con.execute('SELECT * FROM intenciones WHERE id_local=?', (id_local,)).fetchone()
        if fila is None:
            raise ValueError('Intención inexistente.')
        return fila

    @staticmethod
    def _evento(con, id_local, clase, datos, estado):
        con.execute('INSERT OR IGNORE INTO evidencia_orden VALUES(?,?,?,?)',
                    (id_local, clase, datos, estado))

    def crear_intencion(self, dato):
        validar_intencion(dato)
        recibido = serializar(dato)
        id_local = dato['id_local']
        with self.conectar() as con:
            con.execute('BEGIN IMMEDIATE')
            previa = con.execute('SELECT datos FROM intenciones WHERE id_local=?', (id_local,)).fetchone()
            if previa is not None:
                if previa['datos'] == recibido:
                    return resultado('DUPLICADO_IDENTICO')
                self._evento(con, id_local, 'INTENCION_CONFLICTIVA', recibido, 'DISCREPANCIA')
                con.execute('UPDATE intenciones SET conflicto=1 WHERE id_local=?', (id_local,))
                return resultado('DISCREPANCIA')
            # No liberamos el ámbito por un estado terminal: exposición aún no modelada.
            if con.execute('SELECT 1 FROM intenciones WHERE cuenta=? AND simbolo=?',
                           (dato['cuenta'], dato['simbolo'])).fetchone():
                return resultado('AMBITO_BLOQUEADO')
            con.execute('INSERT INTO intenciones(id_local,cuenta,simbolo,datos,estado_local) VALUES(?,?,?,?,?)',
                        (id_local, dato['cuenta'], dato['simbolo'], recibido, 'INTENCION'))
            self._evento(con, id_local, 'LOCAL', 'INTENCION', 'INTENCION')
            return resultado('INTENCION')

    def iniciar_simulacion(self, id_local):
        """Solo marca una transición persistida; jamás invoca un transporte."""
        with self.conectar() as con:
            con.execute('BEGIN IMMEDIATE')
            fila = self._fila(con, id_local)
            if fila['conflicto'] or fila['estado_local'] != 'INTENCION':
                return resultado('BLOQUEADO_SIN_REENVIO')
            con.execute("UPDATE intenciones SET estado_local='ENVIO_SIMULADO' WHERE id_local=?", (id_local,))
            self._evento(con, id_local, 'LOCAL', 'ENVIO_SIMULADO', 'ENVIO_SIMULADO')
            return resultado('ENVIO_SIMULADO')

    def marcar_incierto(self, id_local):
        with self.conectar() as con:
            con.execute('BEGIN IMMEDIATE')
            fila = self._fila(con, id_local)
            if fila['estado_local'] == 'INCIERTO':
                return resultado('INCIERTO')
            if fila['estado_local'] != 'ENVIO_SIMULADO':
                return resultado('TRANSICION_BLOQUEADA')
            con.execute("UPDATE intenciones SET estado_local='INCIERTO' WHERE id_local=?", (id_local,))
            self._evento(con, id_local, 'LOCAL', 'INCIERTO', 'INCIERTO')
            return resultado('INCIERTO')

    def registrar_snapshot(self, id_local, s):
        validar_snapshot(s)
        recibido = serializar(s)
        with self.conectar() as con:
            con.execute('BEGIN IMMEDIATE')
            fila = self._fila(con, id_local)
            anterior_evento = con.execute("SELECT resultado FROM evidencia_orden WHERE id_local=? AND clase='SNAPSHOT' AND datos=?",
                                         (id_local, recibido)).fetchone()
            if anterior_evento:
                return resultado('DISCREPANCIA' if fila['conflicto'] else 'DUPLICADO_IDENTICO')
            p = json.loads(fila['datos'])['parametros']
            actual = json.loads(fila['snapshot']) if fila['snapshot'] else None
            otro = con.execute('SELECT id_local FROM intenciones WHERE cuenta=? AND simbolo=? AND order_id=? AND id_local<>?',
                               (s['cuenta'], s['simbolo'], s['order_id'], id_local)).fetchone()
            conflicto = (s['client_order_id'] != id_local or s['cuenta'] != fila['cuenta'] or
                         s['simbolo'] != fila['simbolo'] or decimal_texto(s['orig_qty']) != decimal_texto(p['quantity']) or
                         (fila['order_id'] is not None and s['order_id'] != fila['order_id']) or
                         fila['estado_local'] == 'INTENCION' or otro is not None)
            estado = 'SNAPSHOT_ACEPTADO'
            if actual:
                tiempo = s['update_time'] - actual['update_time']
                nuevos = tuple(decimal_texto(s[k]) for k in ('executed_qty', 'quote_qty'))
                previos = tuple(decimal_texto(actual[k]) for k in ('executed_qty', 'quote_qty'))
                if tiempo < 0:
                    estado = 'EVIDENCIA_ANTIGUA'
                    conflicto |= any(n > a for n, a in zip(nuevos, previos))
                    conflicto |= s['status'] in TERMINALES and actual['status'] != s['status']
                elif tiempo == 0:
                    conflicto |= recibido != fila['snapshot']
                else:
                    conflicto |= any(n < a for n, a in zip(nuevos, previos))
                    conflicto |= actual['status'] in TERMINALES and s['status'] != actual['status']
                    conflicto |= actual['status'] in TERMINALES and nuevos != previos
                    conflicto |= actual['status'] == 'PARTIALLY_FILLED' and s['status'] == 'NEW'
            if conflicto:
                estado = 'DISCREPANCIA'
                con.execute('UPDATE intenciones SET conflicto=1 WHERE id_local=?', (id_local,))
                if otro:
                    con.execute('UPDATE intenciones SET conflicto=1 WHERE id_local=?', (otro['id_local'],))
                    self._evento(con, otro['id_local'], 'COLISION', serializar({'otro_id': id_local, 'snapshot': s}), estado)
            elif estado == 'SNAPSHOT_ACEPTADO':
                con.execute("UPDATE intenciones SET snapshot=?,order_id=?,estado_local='CON_EVIDENCIA' WHERE id_local=?",
                            (recibido, s['order_id'], id_local))
            self._evento(con, id_local, 'SNAPSHOT', recibido, estado)
            return resultado('DISCREPANCIA' if fila['conflicto'] else estado)

    def informe_orden(self, id_local):
        with self.conectar() as con:
            con.execute('BEGIN')
            fila = self._fila(con, id_local)
            s = json.loads(fila['snapshot']) if fila['snapshot'] else None
            eventos = [dict(r) for r in con.execute('SELECT clase,datos,resultado FROM evidencia_orden WHERE id_local=? ORDER BY rowid', (id_local,))]
            ledger = None
            if s:
                ledger = self._conciliar_en(con, (ENTORNO, fila['cuenta'], fila['simbolo'], fila['order_id']),
                                            (decimal_texto(s['executed_qty']), decimal_texto(s['quote_qty'])))
            estado = 'SIN_EVIDENCIA_EXCHANGE'
            problemas = []
            if ledger:
                estado = 'ACUMULADOS_COINCIDEN' if not ledger['problemas'] else 'EVIDENCIA_NO_CONCILIADA'
                # Datos asincrónicos: diferencias no prueban fraude/error ni permiten liberar el ámbito.
                if ledger['conflictos']:
                    estado = 'DISCREPANCIA'
                if decimal_texto(ledger['cantidad']) > decimal_texto(s['orig_qty']):
                    problemas.append('FILLS_SUPERAN_INTENCION')
                if s['status'] in TERMINALES and (decimal_texto(ledger['cantidad']) > decimal_texto(s['executed_qty']) or
                                                  decimal_texto(ledger['quote_bruto']) > decimal_texto(s['quote_qty'])):
                    problemas.append('FILLS_SUPERAN_TERMINAL')
                # Evidencia inmutable: estos excesos no se solucionan agregando fills/snapshots.
                if problemas:
                    estado = 'DISCREPANCIA'
            if fila['conflicto']:
                estado = 'DISCREPANCIA'
            return {**resultado(estado), 'intencion': json.loads(fila['datos']),
                    'estado_local': fila['estado_local'], 'estado_exchange': s['status'] if s else 'DESCONOCIDO',
                    'recuperacion_necesaria': fila['estado_local'] in ('ENVIO_SIMULADO', 'INCIERTO'),
                    'ambito_bloqueado': True, 'snapshot': s, 'ledger': ledger, 'evidencia': eventos,
                    'problemas_orden': problemas}
