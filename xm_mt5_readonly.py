"""Lectura de XM/MT5 en cuenta DEMO (hito H3). Integración separada de Binance.

El dueño inicia sesión él mismo en la terminal MT5. Este módulo llama a
initialize() SIN argumentos: no maneja login, contraseña ni servidor. Solo lee
account_info, positions_get y symbol_info, y solo mientras la cuenta sea DEMO.
El envío de órdenes está deshabilitado: no hay ruta de código hacia order_send.

No traduce lotes MT5 a cantidades Spot ni calcula P&L o margen (ver
PLATAFORMAS_BINANCE_XM.md). Si Smart App Control impide cargar el paquete
MetaTrader5, se informa y se para: no se desactivan protecciones del sistema.
"""
from __future__ import annotations

from decimal import Decimal
import importlib
import logging
import math
import re
import sys
from typing import Optional, Sequence, TextIO

logger = logging.getLogger(__name__)

FUNCIONES_LECTURA = frozenset({'initialize', 'shutdown', 'account_info', 'positions_get', 'symbol_info'})
ACCOUNT_TRADE_MODE_DEMO = 0  # Valor documentado por MetaQuotes; REAL = 2, CONTEST = 1.
CAMPOS_SIMBOLO = ('volume_min', 'volume_max', 'volume_step', 'trade_contract_size', 'point')


class ErrorMt5(RuntimeError):
    pass


class Mt5NoDisponible(ErrorMt5):
    pass


class Mt5NoConectado(ErrorMt5):
    pass


class CuentaNoDemo(ErrorMt5):
    pass


class OrdenesDeshabilitadas(ErrorMt5):
    pass


def cargar_mt5() -> object:
    try:
        return importlib.import_module('MetaTrader5')
    except ModuleNotFoundError:
        raise Mt5NoDisponible('El paquete MetaTrader5 no está instalado en este Python.') from None
    except (ImportError, OSError):
        raise Mt5NoDisponible('El paquete MetaTrader5 está instalado pero Windows no permitió cargarlo '
                              '(posible bloqueo de Smart App Control). No desactives protecciones.') from None


class _SoloLectura:
    """Única vía hacia el paquete: cualquier función fuera de la lista lanza un error."""
    __slots__ = ('_modulo',)

    def __init__(self, modulo: object) -> None:
        self._modulo = modulo

    def __getattr__(self, nombre: str) -> object:
        if nombre not in FUNCIONES_LECTURA:
            raise OrdenesDeshabilitadas(f'Función MT5 no permitida en solo lectura: {nombre}.')
        return getattr(self._modulo, nombre)


def _decimal(valor: object) -> Decimal:
    if type(valor) not in (int, float) or not math.isfinite(valor):
        raise ErrorMt5('Dato numérico de MT5 con formato inesperado.')
    return Decimal(str(valor))


class LectorMt5:
    def __init__(self, mt5: Optional[object] = None) -> None:
        self._mt5 = _SoloLectura(cargar_mt5() if mt5 is None else mt5)
        self._conectado = False

    def conectar(self) -> None:
        """Se adjunta a la terminal ya abierta y con sesión iniciada por el dueño."""
        self._conectado = False
        if self._mt5.initialize() is not True:  # type: ignore[operator]
            raise Mt5NoConectado('La terminal MT5 no respondió. Ábrela e inicia sesión en tu cuenta demo.')
        self._conectado = True
        try:
            self._exigir_demo()
        except ErrorMt5:
            self.cerrar()
            raise
        logger.info('MT5 conectado en solo lectura a una cuenta DEMO.')

    def cerrar(self) -> None:
        self._conectado = False
        self._mt5.shutdown()  # type: ignore[operator]

    def _exigir_demo(self) -> object:
        """Antes de cada lectura: la cuenta activa en la terminal puede cambiar."""
        if not self._conectado:
            raise Mt5NoConectado('Sin conexión verificada con la terminal MT5.')
        info = self._mt5.account_info()  # type: ignore[operator]
        if info is None:
            raise Mt5NoConectado('La terminal MT5 no tiene una sesión de cuenta iniciada.')
        modo = getattr(info, 'trade_mode', None)
        if type(modo) is not int or modo != ACCOUNT_TRADE_MODE_DEMO:
            self._conectado = False
            raise CuentaNoDemo('La cuenta activa en MT5 no es DEMO (o no se pudo determinar). No se lee.')
        return info

    def cuenta(self) -> dict[str, object]:
        """Sin número de cuenta ni nombre del titular."""
        info = self._exigir_demo()
        divisa, apalancamiento = getattr(info, 'currency', None), getattr(info, 'leverage', None)
        if type(divisa) is not str or re.fullmatch(r'[A-Z]{3,5}', divisa) is None or \
                type(apalancamiento) is not int or apalancamiento <= 0:
            raise ErrorMt5('Datos de cuenta MT5 con formato inesperado.')
        return {'modo': 'DEMO', 'divisa': divisa, 'apalancamiento': apalancamiento,
                'balance': _decimal(getattr(info, 'balance', None)),
                'equity': _decimal(getattr(info, 'equity', None))}

    def posiciones(self) -> list[dict[str, object]]:
        self._exigir_demo()
        posiciones = self._mt5.positions_get()  # type: ignore[operator]
        if posiciones is None:
            raise ErrorMt5('MT5 no devolvió las posiciones.')
        resultado = []
        for p in posiciones:
            tipo = getattr(p, 'type', None)
            if tipo not in (0, 1) or type(getattr(p, 'symbol', None)) is not str:
                raise ErrorMt5('Posición MT5 con formato inesperado.')
            resultado.append({'simbolo': p.symbol, 'lado': 'BUY' if tipo == 0 else 'SELL',
                              'lotes': _decimal(getattr(p, 'volume', None)),
                              'precio_apertura': _decimal(getattr(p, 'price_open', None))})
        return resultado

    def simbolo(self, nombre: str) -> dict[str, object]:
        if type(nombre) is not str or re.fullmatch(r'[A-Za-z0-9._#-]{1,32}', nombre) is None:
            raise ValueError('Símbolo MT5 inválido.')
        self._exigir_demo()
        info = self._mt5.symbol_info(nombre)  # type: ignore[operator]
        if info is None:
            raise ErrorMt5('Símbolo no disponible en esta cuenta MT5.')
        return {'simbolo': nombre, **{campo: _decimal(getattr(info, campo, None)) for campo in CAMPOS_SIMBOLO}}

    def enviar_orden(self, *args: object, **kwargs: object) -> None:
        raise OrdenesDeshabilitadas('El envío de órdenes a MT5 está deshabilitado en esta fase.')


def main(argv: Optional[Sequence[str]] = None, *, salida: Optional[TextIO] = None,
         mt5: Optional[object] = None) -> int:
    """Comprobación que ejecuta el dueño con la terminal MT5 abierta en su cuenta demo."""
    salida = salida or sys.stdout
    if argv:
        print('Uso: python xm_mt5_readonly.py   (sin argumentos)', file=salida)
        return 2
    print('XM / MetaTrader 5 - comprobación de SOLO LECTURA en cuenta DEMO (sin órdenes)', file=salida)
    try:
        lector = LectorMt5(mt5)
    except Mt5NoDisponible as error:
        print(f'Conectado: NO\nBLOCKED: {error}', file=salida)
        return 2
    try:
        lector.conectar()
        cuenta = lector.cuenta()
        abiertas = len(lector.posiciones())
    except ErrorMt5 as error:
        print(f'Conectado: NO\nMotivo: {error}', file=salida)
        return 1
    finally:
        lector.cerrar()
    print(f'Conectado: SI\nCuenta: DEMO\nDivisa: {cuenta["divisa"]}\n'
          f'Apalancamiento: 1:{cuenta["apalancamiento"]}\nPosiciones abiertas: {abiertas}', file=salida)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
