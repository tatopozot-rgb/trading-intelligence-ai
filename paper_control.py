"""Controles PAPER explícitos. Importar/crear controlador no arranca procesos."""
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import uuid

import config


def validar_paper():
    if config.MODO != 'PAPER' or config.USAR_DINERO_REAL is not False:
        raise ValueError('Controles disponibles exclusivamente en PAPER.')


def validar_horas(horas):
    if isinstance(horas, bool) or not isinstance(horas, (int, float)) or not math.isfinite(horas) or not 0 < horas <= 8:
        raise ValueError('Indica una duración mayor que cero y máximo ocho horas.')
    return float(horas)


def validar_id(sesion_id):
    if not isinstance(sesion_id, str) or len(sesion_id) != 32 or any(c not in '0123456789abcdef' for c in sesion_id):
        raise ValueError('Identificador de sesión inválido.')
    return sesion_id


def cancelacion_sesion(root, sesion_id):
    return Path(root)/('DETENER_SESION_'+validar_id(sesion_id))


class ControlPaper:
    def __init__(self, directorio=None, launcher=None):
        self.root = Path(directorio or config.DIRECTORIO).resolve()
        self.launcher = launcher or subprocess.Popen
        self.lock = threading.RLock()
        self.proceso = None
        self.sesion_id = None
        self.parada_solicitada = False
        self.ultimo = 'SIN_PROCESO_PROPIO'
        self.profundidad = False

    def iniciar(self, horas, *, confirmado=False, profundidad=False):
        with self.lock:
            validar_paper()
            horas = validar_horas(horas)
            if type(profundidad) is not bool:
                raise ValueError('La selección de profundidad debe ser booleana.')
            if confirmado is not True:
                raise ValueError('Se requiere confirmación explícita de inicio PAPER.')
            # poll incierto lanza error: nunca liberar el bloqueo por una suposición.
            if self.proceso is not None and self.proceso.poll() is None:
                raise ValueError('Ya existe un lanzamiento o proceso propio pendiente.')
            identidad = uuid.uuid4().hex
            interprete = self.root/'.venv'/'Scripts'/'python.exe'
            script = self.root/'system_runner.py'
            if not interprete.is_file() or not script.is_file():
                raise ValueError('No se encontró el intérprete o ejecutor del proyecto.')
            self.sesion_id = identidad
            self.proceso = None
            self.parada_solicitada = False
            self.ultimo = 'SOLICITADO'
            self.profundidad = profundidad
            argumentos = [str(interprete), str(script), '--continuo', '--reglas-paper',
                          '--horas', str(horas), '--reanudar', '--sesion-id', identidad]
            if profundidad:
                argumentos.append('--profundidad-paper')
            try:
                logs = self.root/'logs'
                logs.mkdir(exist_ok=True)
                with (logs/('inicio_'+identidad+'.log')).open('ab') as registro:
                    self.proceso = self.launcher(argumentos, cwd=str(self.root), shell=False,
                        stdin=subprocess.DEVNULL, stdout=registro, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            except Exception:
                self.ultimo = 'FALLO_LANZAMIENTO'
                raise
            return identidad

    def observar(self):
        with self.lock:
            salida = {'sesion_id': self.sesion_id, 'estado': self.ultimo,
                      'modelo_solicitado': 'PROFUNDIDAD_VISIBLE_FOK_PAPER_V1' if self.profundidad else 'TICKER_LEGADO',
                      'proceso_vivo': False, 'parada_solicitada': self.parada_solicitada}
            if self.proceso is None:
                return salida
            try:
                codigo = self.proceso.poll()
            except Exception:
                return {**salida, 'estado': 'PROCESO_NO_VERIFICADO', 'proceso_vivo': None}
            if codigo is not None:
                self.ultimo = 'TERMINADO' if codigo == 0 else 'FALLO_TERMINADO'
                return {**salida, 'estado': self.ultimo, 'codigo_salida': codigo}
            salida.update(proceso_vivo=True, estado='INICIO_NO_CONFIRMADO')
            try:
                with (self.root/'runner_status.json').open('rb') as archivo:
                    texto = archivo.read(262145)
                if len(texto) > 262144:
                    raise ValueError('Estado demasiado grande')
                dato = json.loads(texto)
                if (isinstance(dato, dict) and dato.get('modo') == 'PAPER'
                        and dato.get('sesion_id') == self.sesion_id
                        # Windows venv puede mantener un launcher padre esperando al intérprete.
                        # ID por intento y handle vivo siguen obligatorios; no aceptar sólo un PID.
                        and (dato.get('pid') == self.proceso.pid or dato.get('parent_pid') == self.proceso.pid)
                        and dato.get('estado') in ('ACTIVO', 'DETENIENDO')):
                    salida.update(estado=dato['estado']+'_REGISTRADO', registro=dato)
            except (OSError, ValueError, UnicodeError):
                pass
            # Registro no es prueba de salud; la vida se obtiene sólo del handle propio.
            if self.parada_solicitada:
                salida['estado'] = 'PARADA_SOLICITADA'
            return salida

    def pausar(self):
        with self.lock:
            validar_paper()
            (self.root/'PAUSA_ENTRADAS').touch(exist_ok=True)

    def reanudar_entradas(self, *, confirmado=False):
        with self.lock:
            validar_paper()
            if confirmado is not True:
                raise ValueError('Se requiere confirmar reanudar entradas PAPER.')
            (self.root/'PAUSA_ENTRADAS').unlink(missing_ok=True)

    def detener(self):
        with self.lock:
            validar_paper()
            # Escribir ambas señales aun si falla una; comunicar el fallo al llamante.
            fallo = None
            if self.sesion_id is not None:
                try:
                    cancelacion_sesion(self.root, self.sesion_id).touch(exist_ok=True)
                except OSError as error:
                    fallo = error
            try:
                (self.root/'DETENER_RUNNER').touch(exist_ok=True)
            except OSError as error:
                fallo = fallo or error
            self.parada_solicitada = True
            if fallo is not None:
                raise fallo
