"""Paquetes y evaluaciones append-only por API en SQLite OFFLINE. Nunca envía."""
import json
import logging
import sqlite3

from execution_bundle import evaluar_paquete_fixture
from execution_context import ContextoInvalido, hash_contenido, _campos, _tiempo
from execution_filters import FiltroInvalido
from execution_ledger import serializar, texto
from execution_orders import OrdenesOffline

VERSION_EVALUADOR = 'E3D_V2_1'


class AuditoriaOffline(OrdenesOffline):
    def __init__(self, ruta):
        super().__init__(ruta)
        with self.conectar() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('''CREATE TABLE IF NOT EXISTS paquetes_evaluacion (
                id_local TEXT PRIMARY KEY, datos TEXT NOT NULL, hash TEXT NOT NULL)''')
            con.execute('''CREATE TABLE IF NOT EXISTS evaluaciones (
                id_local TEXT NOT NULL, evaluacion_id TEXT NOT NULL,
                entrada_hash TEXT NOT NULL, datos TEXT NOT NULL, hash TEXT NOT NULL,
                PRIMARY KEY(id_local,evaluacion_id))''')
            con.execute('''CREATE TABLE IF NOT EXISTS conflictos_evaluacion (
                id_local TEXT NOT NULL, evaluacion_id TEXT NOT NULL, entrada_hash TEXT NOT NULL,
                datos TEXT NOT NULL, hash TEXT NOT NULL,
                PRIMARY KEY(id_local,evaluacion_id,entrada_hash))''')

    @staticmethod
    def _salida(registro, duplicado, conflicto):
        return {'modo':'OFFLINE','enviable':False,'autorizado':False,
                'estado':'REGISTRO_HISTORICO_NO_AUTORIZANTE',
                'historico':True,'duplicado':duplicado,'conflicto_actual':bool(conflicto),
                'registro':registro}

    def evaluar_y_registrar(self, id_local, evaluacion_id, paquete, *, ahora_ms, limites_politica):
        try:
            return self._evaluar_y_registrar(id_local,evaluacion_id,paquete,ahora_ms=ahora_ms,
                                            limites_politica=limites_politica)
        except Exception as error:
            # Ocurre DESPUÉS del rollback/cierre. No incluir paquetes ni mensajes arbitrarios.
            logging.getLogger(__name__).error('Evaluación OFFLINE no registrada: %s',type(error).__name__)
            raise

    def _evaluar_y_registrar(self, id_local, evaluacion_id, paquete, *, ahora_ms, limites_politica):
        """ID nuevo para cada evaluación; repetir ID idéntico sólo recupera historia.

        La intención se carga de esta BD, no desde el paquete. Fallos inesperados o
        de disco revierten todo; errores de validación acotados se registran rechazados.
        """
        texto(evaluacion_id, 'evaluacion_id')
        _campos(paquete, ('plan','snapshot','evidencias'))
        _tiempo(ahora_ms)
        entrada = {'paquete':paquete,'ahora_ms':ahora_ms,'limites_politica':limites_politica}
        hash_contenido(entrada)
        # Congela una copia para que la evaluación use exactamente lo que se registra.
        entrada = json.loads(serializar(entrada))
        entrada_hash = hash_contenido(entrada)
        paquete = entrada['paquete']
        paquete_hash = hash_contenido(paquete)
        clave = (id_local,evaluacion_id)
        with self.conectar() as con:
            con.execute('BEGIN IMMEDIATE')
            fila = self._fila(con,id_local)
            anterior = con.execute('SELECT * FROM evaluaciones WHERE id_local=? AND evaluacion_id=?',clave).fetchone()
            if anterior:
                guardado = json.loads(anterior['datos'])
                if hash_contenido(guardado) != anterior['hash'] or hash_contenido(guardado['entrada']) != anterior['entrada_hash']:
                    raise ValueError('Registro previo inconsistente; no sobrescribir.')
                if anterior['entrada_hash'] == entrada_hash:
                    return self._salida(guardado,True,fila['conflicto'])
                conflicto = {'entrada_original_hash':anterior['entrada_hash'],'entrada_recibida':entrada}
                con.execute('INSERT OR IGNORE INTO conflictos_evaluacion VALUES(?,?,?,?,?)',
                            (*clave,entrada_hash,serializar(conflicto),hash_contenido(conflicto)))
                con.execute('UPDATE intenciones SET conflicto=1 WHERE id_local=?',(id_local,))
                self._evento(con,id_local,'EVALUACION_CONFLICTIVA',serializar({'id':evaluacion_id,'entrada_hash':entrada_hash}),'DISCREPANCIA')
                return {**self._salida(guardado,False,True),'estado':'ID_EVALUACION_CONFLICTIVO'}
            intencion = json.loads(fila['datos'])
            canonico = con.execute('SELECT * FROM paquetes_evaluacion WHERE id_local=?',(id_local,)).fetchone()
            if canonico and hash_contenido(json.loads(canonico['datos'])) != canonico['hash']:
                raise ValueError('Paquete previo inconsistente; no sobrescribir.')
            conflicto_actual = fila['conflicto']
            if canonico and canonico['hash'] != paquete_hash:
                conflicto_actual = 1
                con.execute('UPDATE intenciones SET conflicto=1 WHERE id_local=?',(id_local,))
                evaluacion = {'estado':'PAQUETE_CONFLICTIVO','enviable':False,'autorizado':False}
            elif conflicto_actual:
                evaluacion = {'estado':'BLOQUEADO_POR_CONFLICTO','enviable':False,'autorizado':False}
            elif fila['estado_local'] != 'INTENCION':
                evaluacion = {'estado':'BLOQUEADO_POR_ESTADO','enviable':False,'autorizado':False}
            else:
                try:
                    evaluacion = evaluar_paquete_fixture(intencion,paquete['plan'],paquete['snapshot'],paquete['evidencias'],
                        ahora_ms=entrada['ahora_ms'],limites_politica=entrada['limites_politica'])
                except (ContextoInvalido,FiltroInvalido) as error:
                    evaluacion = {'estado':'RECHAZADO_VALIDACION','enviable':False,'autorizado':False,
                                  'error_tipo':type(error).__name__,'motivo':str(error)[:240]}
                else:
                    if canonico is None:
                        con.execute('INSERT INTO paquetes_evaluacion VALUES(?,?,?)',
                                    (id_local,serializar(paquete),paquete_hash))
            registro = {'schema':'REGISTRO_EVALUACION_OFFLINE_V1','evaluador':VERSION_EVALUADOR,
                        'intencion':intencion,'estado_local_observado':fila['estado_local'],
                        'conflicto_observado':bool(fila['conflicto']),'entrada':entrada,
                        'paquete_hash':paquete_hash,'resultado':evaluacion}
            con.execute('INSERT INTO evaluaciones VALUES(?,?,?,?,?)',
                        (*clave,entrada_hash,serializar(registro),hash_contenido(registro)))
            self._evento(con,id_local,'EVALUACION_REGISTRADA',
                         serializar({'id':evaluacion_id,'entrada_hash':entrada_hash}),evaluacion['estado'])
            return self._salida(registro,False,conflicto_actual)

    def informe_auditoria(self, id_local):
        """Una transacción de lectura. Integridad histórica, NO revalidación vigente."""
        try:
            return self._informe_auditoria(id_local)
        except (ValueError,KeyError,TypeError,sqlite3.DatabaseError) as error:
            return {'modo':'OFFLINE','enviable':False,'autorizado':False,'historico':True,
                    'estado':'NO_VERIFICADO','error_tipo':type(error).__name__}

    def _informe_auditoria(self, id_local):
        with self.conectar() as con:
            con.execute('BEGIN')
            return informe_auditoria_en(con, id_local)


def informe_auditoria_en(con, id_local):
    """Lee usando una transacción del llamador; no abre, cierra ni modifica BD.

    Requiere sqlite3.Row y una transacción activa. El llamador es responsable
    de verificar identidad/esquema de la base y de capturar errores de lectura.
    No inicializa tablas ni vuelve a evaluar vigencia o autorización.
    """
    if not con.in_transaction:
        raise ValueError('La auditoría requiere una transacción de lectura activa.')
    fila = OrdenesOffline._fila(con,id_local)
    intencion = json.loads(fila['datos'])
    paquete = con.execute('SELECT * FROM paquetes_evaluacion WHERE id_local=?',(id_local,)).fetchone()
    evaluaciones = con.execute('SELECT * FROM evaluaciones WHERE id_local=? ORDER BY rowid',(id_local,)).fetchall()
    conflictos = con.execute('SELECT * FROM conflictos_evaluacion WHERE id_local=? ORDER BY rowid',(id_local,)).fetchall()
    eventos = con.execute("SELECT clase,datos,resultado FROM evidencia_orden WHERE id_local=? AND clase IN ('EVALUACION_REGISTRADA','EVALUACION_CONFLICTIVA')",(id_local,)).fetchall()
    eventos_recibidos = {(e['clase'],e['datos'],e['resultado']) for e in eventos}
    eventos_esperados = set()
    problemas = []
    if paquete and hash_contenido(json.loads(paquete['datos'])) != paquete['hash']:
        problemas.append('HASH_PAQUETE')
    registros = []
    for e in evaluaciones:
        r = json.loads(e['datos'])
        if hash_contenido(r) != e['hash'] or hash_contenido(r['entrada']) != e['entrada_hash']:
            problemas.append('HASH_EVALUACION:'+e['evaluacion_id'])
        if r['intencion'] != intencion or hash_contenido(r['entrada']['paquete']) != r['paquete_hash']:
            problemas.append('VINCULO_EVALUACION:'+e['evaluacion_id'])
        if r['resultado']['estado']=='FILTROS_DECLARADOS_VERIFICADOS_OFFLINE' and (paquete is None or paquete['hash'] != r['paquete_hash']):
            problemas.append('PAQUETE_CANONICO_AUSENTE_O_DISTINTO')
        registros.append({'evaluacion_id':e['evaluacion_id'],'registro':r})
        eventos_esperados.add(('EVALUACION_REGISTRADA',serializar({'id':e['evaluacion_id'],'entrada_hash':e['entrada_hash']}),r['resultado']['estado']))
    entradas = {e['evaluacion_id']:e['entrada_hash'] for e in evaluaciones}
    for c in conflictos:
        dato = json.loads(c['datos'])
        if hash_contenido(dato) != c['hash'] or hash_contenido(dato['entrada_recibida']) != c['entrada_hash']:
            problemas.append('HASH_CONFLICTO:'+c['evaluacion_id'])
        if entradas.get(c['evaluacion_id']) != dato['entrada_original_hash']:
            problemas.append('VINCULO_CONFLICTO:'+c['evaluacion_id'])
        eventos_esperados.add(('EVALUACION_CONFLICTIVA',serializar({'id':c['evaluacion_id'],'entrada_hash':c['entrada_hash']}),'DISCREPANCIA'))
    if eventos_recibidos != eventos_esperados:
        problemas.append('EVENTOS_EVALUACION_DISCORDANTES')
    if paquete and not any(r['registro']['resultado']['estado']=='FILTROS_DECLARADOS_VERIFICADOS_OFFLINE' for r in registros):
        problemas.append('PAQUETE_SIN_EVALUACION_ORIGINAL')
    conflicto_historico = bool(conflictos) or any(r['registro']['resultado']['estado']=='PAQUETE_CONFLICTIVO' for r in registros)
    if conflicto_historico and not fila['conflicto']:
        problemas.append('BANDERA_CONFLICTO_INCOHERENTE')
    return {'modo':'OFFLINE','enviable':False,'autorizado':False,'historico':True,
            'estado':'DISCREPANCIA' if problemas or fila['conflicto'] else 'REGISTRO_INTEGRO',
            'estado_local':fila['estado_local'],'problemas':problemas,
            'paquete':json.loads(paquete['datos']) if paquete else None,
            'evaluaciones':registros,'conflictos':[json.loads(c['datos']) for c in conflictos]}
