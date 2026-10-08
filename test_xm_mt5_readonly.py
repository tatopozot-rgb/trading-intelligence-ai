from decimal import Decimal
import inspect
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import broker_adapters
import xm_mt5_readonly as modulo
from xm_mt5_readonly import (CuentaNoDemo, ErrorMt5, LectorMt5, Mt5NoConectado, Mt5NoDisponible,
    OrdenesDeshabilitadas, cargar_mt5, main)

LOGIN_FICTICIO = 987654321


def cuenta(**cambios):
    return SimpleNamespace(**{'login': LOGIN_FICTICIO, 'name': 'Titular Ficticio', 'trade_mode': 0,
        'leverage': 30, 'currency': 'USD', 'balance': 10000.0, 'equity': 9990.5,
        'server': 'Servidor-Ficticio-Demo', **cambios})


class Mt5Falso:
    """Sustituto en memoria del paquete MetaTrader5. Las funciones de escritura fallan si se tocan."""

    def __init__(self, info=None, iniciado=True, posiciones=(), simbolos=None):
        self.info = cuenta() if info is None else info
        self.iniciado = iniciado
        self._posiciones = posiciones
        self.simbolos = simbolos or {}
        self.llamadas = []

    def initialize(self, *args, **kwargs):
        self.llamadas.append(('initialize', args, kwargs))
        return self.iniciado

    def shutdown(self):
        self.llamadas.append(('shutdown', (), {}))

    def account_info(self):
        self.llamadas.append(('account_info', (), {}))
        return self.info

    def positions_get(self, *args, **kwargs):
        self.llamadas.append(('positions_get', args, kwargs))
        return self._posiciones

    def symbol_info(self, nombre):
        self.llamadas.append(('symbol_info', (nombre,), {}))
        return self.simbolos.get(nombre)

    def _prohibida(self, *args, **kwargs):
        raise AssertionError('Se llamó a una función de escritura o de login de MT5.')

    order_send = order_check = login = _prohibida

    def nombres(self):
        return [c[0] for c in self.llamadas]


class XmMt5SoloLecturaTests(unittest.TestCase):
    def conectado(self, **kwargs):
        falso = Mt5Falso(**kwargs)
        lector = LectorMt5(falso)
        lector.conectar()
        return lector, falso

    def test_initialize_se_llama_sin_login_contrasena_ni_servidor(self):
        _, falso = self.conectado()
        self.assertEqual(falso.llamadas[0], ('initialize', (), {}))
        fuente = inspect.getsource(modulo)
        for prohibido in ('password', 'getpass', 'environ', 'login=', 'server=', '.login('):
            self.assertNotIn(prohibido, fuente)

    def test_lecturas_no_exponen_identidad_de_la_cuenta(self):
        posiciones = (SimpleNamespace(symbol='CFD_FICTICIO', type=1, volume=0.1, price_open=101.25, ticket=5),)
        simbolos = {'CFD_FICTICIO': SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01,
                                                    trade_contract_size=10.0, point=0.01)}
        lector, falso = self.conectado(posiciones=posiciones, simbolos=simbolos)
        datos = lector.cuenta()
        self.assertEqual(datos, {'modo': 'DEMO', 'divisa': 'USD', 'apalancamiento': 30,
                                 'balance': Decimal('10000.0'), 'equity': Decimal('9990.5')})
        self.assertEqual(lector.posiciones(), [{'simbolo': 'CFD_FICTICIO', 'lado': 'SELL',
            'lotes': Decimal('0.1'), 'precio_apertura': Decimal('101.25')}])
        self.assertEqual(lector.simbolo('CFD_FICTICIO')['volume_step'], Decimal('0.01'))
        for texto in (repr(datos), repr(lector.posiciones())):
            self.assertNotIn(str(LOGIN_FICTICIO), texto)
            self.assertNotIn('Titular', texto)
        self.assertLessEqual(set(falso.nombres()), set(modulo.FUNCIONES_LECTURA))

    def test_order_send_esta_deshabilitado_y_nunca_se_alcanza(self):
        lector, falso = self.conectado()
        with self.assertRaises(OrdenesDeshabilitadas):
            lector.enviar_orden({'action': 1, 'symbol': 'CFD_FICTICIO', 'volume': 0.01})
        for nombre in ('order_send', 'order_check', 'login', 'order_calc_margin', 'copy_rates_from_pos',
                       'terminal_info', '__class__x'):
            with self.subTest(nombre=nombre), self.assertRaises(OrdenesDeshabilitadas):
                getattr(lector._mt5, nombre)
        self.assertEqual(modulo.FUNCIONES_LECTURA, {'initialize', 'shutdown', 'account_info',
                                                    'positions_get', 'symbol_info'})
        fuente = inspect.getsource(modulo)
        self.assertEqual(fuente.count('order_send'), 1)  # solo la mención del docstring
        self.assertNotIn('order_check', fuente)
        # Fuera del proxy no queda ninguna referencia al paquete real.
        self.assertFalse(hasattr(lector, 'mt5'))
        self.assertIs(type(lector._mt5), modulo._SoloLectura)

    def test_cuenta_real_concurso_o_indeterminada_se_rechaza_y_se_cierra(self):
        for modo in (2, 1, None, '0', 0.0, False, -1):
            with self.subTest(modo=modo):
                falso = Mt5Falso(info=cuenta(trade_mode=modo))
                lector = LectorMt5(falso)
                with self.assertRaises(CuentaNoDemo):
                    lector.conectar()
                self.assertEqual(falso.nombres()[-1], 'shutdown')
                for lectura in (lector.cuenta, lector.posiciones, lambda: lector.simbolo('X')):
                    with self.assertRaises(Mt5NoConectado):
                        lectura()
                self.assertNotIn('positions_get', falso.nombres())

    def test_si_la_terminal_cambia_a_cuenta_real_las_lecturas_se_detienen(self):
        lector, falso = self.conectado()
        lector.cuenta()
        falso.info = cuenta(trade_mode=2)
        for lectura in (lector.posiciones, lambda: lector.simbolo('CFD_FICTICIO')):
            with self.assertRaises(ErrorMt5):
                lectura()
        self.assertNotIn('positions_get', falso.nombres())
        self.assertNotIn('symbol_info', falso.nombres())
        falso.info = cuenta()
        with self.assertRaises(Mt5NoConectado):  # exige volver a conectar()
            lector.cuenta()

    def test_terminal_cerrada_o_sin_sesion(self):
        for falso in (Mt5Falso(iniciado=False), Mt5Falso(iniciado=None), Mt5Falso(iniciado=1)):
            lector = LectorMt5(falso)
            with self.assertRaises(Mt5NoConectado):
                lector.conectar()
            self.assertNotIn('account_info', falso.nombres())
        falso = Mt5Falso()
        falso.info = None
        falso.account_info = lambda: None
        with self.assertRaises(Mt5NoConectado):
            LectorMt5(falso).conectar()
        with self.assertRaises(Mt5NoConectado):
            LectorMt5(Mt5Falso()).cuenta()  # sin conectar()

    def test_datos_inesperados_fallan(self):
        for info in (cuenta(leverage=0), cuenta(leverage='30'), cuenta(currency='usd'), cuenta(currency=None),
                     cuenta(balance=float('nan')), cuenta(equity='1')):
            with self.subTest(info=info), self.assertRaises(ErrorMt5):
                self.conectado(info=info)[0].cuenta()
        with self.assertRaises(ErrorMt5):
            self.conectado(posiciones=None)[0].posiciones()
        with self.assertRaises(ErrorMt5):
            self.conectado(posiciones=(SimpleNamespace(symbol='X', type=5, volume=1.0, price_open=1.0),))[0].posiciones()
        lector, falso = self.conectado()
        with self.assertRaises(ErrorMt5):
            lector.simbolo('NO_EXISTE')
        for malo in ('', 'A B', 'x' * 33, None, 'A;B'):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                lector.simbolo(malo)

    def test_paquete_ausente_o_bloqueado_se_informa_sin_rodeos(self):
        with patch.object(modulo.importlib, 'import_module', side_effect=ModuleNotFoundError('x')):
            with self.assertRaisesRegex(Mt5NoDisponible, 'no está instalado'):
                cargar_mt5()
        for error in (ImportError('DLL load failed'), OSError('bloqueado')):
            with patch.object(modulo.importlib, 'import_module', side_effect=error):
                with self.assertRaisesRegex(Mt5NoDisponible, 'No desactives protecciones'):
                    cargar_mt5()
        salida = io.StringIO()
        with patch.object(modulo.importlib, 'import_module', side_effect=ModuleNotFoundError('x')):
            self.assertEqual(main([], salida=salida), 2)
        self.assertIn('BLOCKED', salida.getvalue())

    def test_comando_muestra_solo_datos_no_sensibles_y_cierra(self):
        falso = Mt5Falso(posiciones=(SimpleNamespace(symbol='X', type=0, volume=1.0, price_open=1.0),))
        salida = io.StringIO()
        self.assertEqual(main([], salida=salida, mt5=falso), 0)
        self.assertEqual(salida.getvalue().splitlines()[1:], ['Conectado: SI', 'Cuenta: DEMO', 'Divisa: USD',
            'Apalancamiento: 1:30', 'Posiciones abiertas: 1'])
        for dato in (str(LOGIN_FICTICIO), 'Titular', '10000', 'Servidor'):
            self.assertNotIn(dato, salida.getvalue())
        self.assertEqual(falso.nombres()[-1], 'shutdown')
        falso = Mt5Falso(info=cuenta(trade_mode=2))
        salida = io.StringIO()
        self.assertEqual(main([], salida=salida, mt5=falso), 1)
        self.assertIn('no es DEMO', salida.getvalue())
        self.assertEqual(main(['--real'], salida=io.StringIO(), mt5=falso), 2)

    def test_integracion_separada_de_binance_y_de_los_lectores_paper(self):
        fuente = inspect.getsource(modulo)
        for ajeno in ('binance', 'broker_adapters', 'urllib', 'requests'):
            self.assertNotIn(f'import {ajeno}', fuente)
            self.assertNotIn(f'from {ajeno}', fuente)
        self.assertNotIn('import MetaTrader5', inspect.getsource(broker_adapters))
        self.assertNotIn('import_module', inspect.getsource(broker_adapters))

if __name__ == '__main__':
    unittest.main()
