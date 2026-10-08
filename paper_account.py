"""Cuenta PAPER; aportes y retiros separados de la rentabilidad."""
import argparse
import paper_store as store
from config import BASE_DATOS


def crear_cuenta():
    store.inicializar()


def obtener_cuenta():
    return store.cuenta()


def registrar_resultado(resultado_usd):
    raise RuntimeError('El P&L se registra al cerrar la operación en una sola transacción.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--movimiento', type=float, help='Aporte positivo o retiro negativo, solo saldo simulado.')
    parser.add_argument('--nota', default='Movimiento PAPER manual')
    args = parser.parse_args()
    if args.movimiento is not None:
        store.movimiento(args.movimiento, args.nota)
    print(obtener_cuenta())
