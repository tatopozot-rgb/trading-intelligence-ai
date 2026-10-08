"""Salud observada de los componentes; no autoriza operaciones."""
import copy
import threading
import time
from datetime import datetime, timezone


class Salud:
    def __init__(self, reloj=None):
        self.reloj = reloj or time.monotonic
        self.lock = threading.Lock()
        self.componentes = {nombre:{'estado':'PENDIENTE','ciclos':0,'errores_total':0}
                            for nombre in ('scanner','monitor','bandeja')}

    def registrar_bandeja(self, archivo, fallo=None):
        """Los fallos siguen visibles hasta procesar correctamente ese archivo."""
        with self.lock:
            dato = self.componentes['bandeja']
            dato['ciclos'] += 1
            dato['_fin_monotono'] = self.reloj()
            dato['fin_utc'] = datetime.now(timezone.utc).isoformat()
            pendientes = dato.setdefault('fallos_pendientes',{})
            if fallo is not None:
                detalle = {**copy.deepcopy(fallo),'fecha_utc':dato['fin_utc']}
                pendientes[archivo] = detalle
                dato['errores_total'] += 1
                dato['ultimo_error'] = detalle
            else:
                pendientes.pop(archivo,None)
                dato['ultimo_exito_utc'] = dato['fin_utc']
            dato['ultimo_archivo'] = archivo
            dato['estado'] = 'DEGRADADO' if pendientes else 'OK'

    def iniciar(self,nombre):
        with self.lock:
            dato = self.componentes[nombre]
            dato['estado'] = 'EN_CURSO'
            dato['inicio_utc'] = datetime.now(timezone.utc).isoformat()

    def terminar(self,nombre,resultado=None,error=None):
        with self.lock:
            dato = self.componentes[nombre]
            dato['ciclos'] += 1
            dato['_fin_monotono'] = self.reloj()
            dato['fin_utc'] = datetime.now(timezone.utc).isoformat()
            if error is not None:
                dato['estado'] = 'ERROR'
                dato['errores_total'] += 1
                dato['ultimo_error'] = {'tipo':type(error).__name__}
                dato['resultado'] = None
            elif isinstance(resultado,dict):
                errores = resultado.get('errores',0)
                dato['estado'] = 'CANCELADO' if resultado.get('cancelado') else ('DEGRADADO' if errores else 'OK')
                dato['errores_total'] += errores
                dato['resultado'] = copy.deepcopy(resultado)
                dato['ultimo_error'] = copy.deepcopy(resultado.get('ultimo_error'))
                if not errores and not resultado.get('cancelado'):
                    dato['ultimo_exito_utc'] = dato['fin_utc']
            else:
                dato['estado'] = 'SIN_DATOS'
                dato['resultado'] = None

    def snapshot(self):
        with self.lock:
            salida = copy.deepcopy(self.componentes)
        for dato in salida.values():
            fin = dato.pop('_fin_monotono',None)
            dato['segundos_desde_fin'] = None if fin is None else round(max(0,self.reloj()-fin),3)
        return salida
