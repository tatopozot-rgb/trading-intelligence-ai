"""Consultas compatibles y apertura exclusivamente por autorización verificada."""
import paper_store as store
from config import BASE_DATOS


def conectar():
    import sqlite3
    return sqlite3.connect(BASE_DATOS)


def crear_tabla():
    store.inicializar()


def existe_operacion_abierta(simbolo):
    crear_tabla()
    with store.conectar() as con:
        return con.execute("SELECT 1 FROM paper_trades WHERE simbolo=? AND estado='ABIERTA'", (simbolo,)).fetchone() is not None


def estado_abierto():
    crear_tabla()
    with store.conectar() as con:
        return dict(store.resumen(con))


def contar_operaciones_abiertas():
    return estado_abierto()['n']


def obtener_riesgo_abierto():
    return estado_abierto()['riesgo']


def obtener_capital_comprometido():
    return estado_abierto()['capital']


def obtener_capital_disponible():
    return max(store.cuenta()['saldo_actual']-obtener_capital_comprometido(), 0)


def abrir_operacion_paper(simbolo, plan=None):
    # Una importación o llamada antigua nunca elude el circuito de autorización.
    return {'registrada': False, 'motivo': 'Usa claude_authorizer: solicitud, revisión y autorización local.'}


if __name__ == '__main__':
    print('Cuenta PAPER:', store.cuenta())
    print('Operaciones abiertas:', estado_abierto())
