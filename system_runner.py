"""Ciclo periódico PAPER: escaneo, solicitudes Claude, autorización y monitor."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import signal
import threading
import time
import uuid

import config
import paper_store as store
from claude_bridge import crear_solicitud_claude, guardar_atomico
from claude_authorizer import procesar_archivo
from paper_monitor import revisar_operaciones
from trading_scanner import ejecutar_scanner
from runner_health import Salud
from paper_rules import procesar_candidatos
from paper_control import validar_id, validar_horas, cancelacion_sesion

ESTADO = config.DIRECTORIO/'runner_status.json'
PARADA = config.DIRECTORIO/'DETENER_RUNNER'


@contextmanager
def instancia_unica():
    # Bloqueo de SO: se libera incluso si el proceso termina abruptamente.
    archivo = (config.DIRECTORIO/'runner.lock').open('a+b')
    try:
        archivo.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        archivo.close()
        raise RuntimeError('No se pudo adquirir el bloqueo del runner.') from error
    try:
        yield
    finally:
        archivo.close()


def validar_arranque():
    store.validar_paper()
    store.inicializar()
    from paper_report import informe
    if informe(config.BASE_DATOS)['estado'] != 'OK':
        raise ValueError('Conciliación PAPER fallida: revisar antes de iniciar trabajadores.')


def preparar():
    validar_arranque()
    carpeta = config.DIRECTORIO/'logs'
    carpeta.mkdir(exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not any(isinstance(h,RotatingFileHandler) and Path(h.baseFilename)==carpeta/'runner.log'
               for h in logger.handlers):
        handler = RotatingFileHandler(carpeta/'runner.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
        logger.addHandler(logging.StreamHandler())


def escanear(prueba=False, sesion_activa=None, reglas=False, profundidad=False):
    resultados = []
    cancelado = False
    solicitud = None
    decisiones_reglas = []
    try:
        store.comprobar_sesion(sesion_activa)
        resultados = ejecutar_scanner()
        if reglas:
            if prueba:
                raise ValueError('Prueba Claude incompatible con reglas.')
            decisiones_reglas = (procesar_candidatos(resultados, sesion_activa, profundidad=True)
                                 if profundidad else procesar_candidatos(resultados, sesion_activa))
        else:
            solicitud = crear_solicitud_claude(resultados, prueba, sesion_activa)
    except store.SesionFinalizada:
        cancelado = True
    resumen = {'fecha': store.ahora().isoformat(), 'analizados': len(resultados),
        'errores': sum('error' in r for r in resultados), 'solicitud': solicitud,
        'cancelado':cancelado, 'reglas_paper':reglas, 'decisiones_reglas':decisiones_reglas}
    with store.conectar() as con:
        store.evento(con, 'CICLO', resumen)
    logging.info('Escaneo: %s', resumen)
    return resumen


def ejecutar_ciclo(modo_prueba_claude=False):
    preparar()
    try:
        return escanear(modo_prueba_claude)
    finally:
        revisar_operaciones()


def monitor_continuo(parar, intervalo, salud=None):
    while not parar.is_set():
        try:
            if salud:
                salud.iniciar('monitor')
            resultado = revisar_operaciones()
            if salud:
                salud.terminar('monitor',resultado)
        except Exception as error:
            if salud:
                salud.terminar('monitor',error=error)
            logging.exception('Fallo monitor: se reintentará.')
        parar.wait(intervalo)


def procesar_entrada_bandeja(ruta, procesadas, vistas, salud, automatico, sesion_activa):
    """Un intento por marca de archivo en esta sesión; nunca reintenta por error."""
    marca = (str(ruta), None, None)
    etapa = 'METADATOS'
    try:
        datos = ruta.stat()
        marca = (str(ruta), datos.st_mtime_ns, datos.st_size)
        if marca in vistas:
            return
        if not automatico:
            logging.info('Respuesta pendiente: ejecutar claude_authorizer.py --archivo "%s"', ruta)
            vistas.add(marca)
            return
        if not sesion_activa():
            return
        etapa = 'IMPORTACION'
        resultados = procesar_archivo(ruta, automatico=True, sesion_activa=sesion_activa)
        etapa = 'AUDITORIA'
        with store.conectar() as con:
            store.evento(con,'RESPUESTA_PROCESADA',{'archivo':ruta.name,'resultados':resultados})
        etapa = 'ARCHIVADO'
        ruta.rename(procesadas/(str(time.time_ns())+'_'+ruta.name))
        salud.registrar_bandeja(ruta.name)
        logging.info('Respuesta procesada %s: %s', ruta.name, resultados)
    except Exception as error:
        if marca in vistas:
            return
        vistas.add(marca)
        fallo = {'archivo':ruta.name,'mtime_ns':marca[1],'tamano':marca[2],
                 'etapa':etapa,'tipo':type(error).__name__, 'reintento_automatico':False}
        # No guardar contenido JSON, mensaje arbitrario de excepción ni ruta absoluta.
        try:
            with store.conectar() as con:
                store.evento(con,'BANDEJA_FALLO',fallo)
        except Exception as error_auditoria:
            fallo['error_auditoria'] = type(error_auditoria).__name__
            logging.error('No se pudo auditar fallo de bandeja: %s',type(error_auditoria).__name__)
        salud.registrar_bandeja(ruta.name,fallo)
        logging.error('Fallo de bandeja %s, etapa %s, tipo %s; sin reintento automático.',
                      ruta.name,etapa,type(error).__name__)


@contextmanager
def proteger_apagado():
    # Un segundo Ctrl+C no debe interrumpir join ni liberar la exclusión.
    principal = threading.current_thread() is threading.main_thread()
    anterior = signal.getsignal(signal.SIGINT) if principal else None
    if principal:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        yield
    finally:
        if principal:
            signal.signal(signal.SIGINT, anterior)


def finalizar_trabajadores(parar, monitor, pool, futuro, salud, estado_final, sesion_id=None):
    """Retorna solo tras terminar trabajadores; errores de estado no omiten cleanup."""
    with proteger_apagado():
        parar.set()
        error_escritura = None
        fallos_escritura = 0
        inicio_apagado = time.monotonic()

        def publicar(estado):
            nonlocal error_escritura, fallos_escritura
            try:
                guardar_atomico(ESTADO, store.serializar({'pid':os.getpid(), 'parent_pid':os.getppid(),
                    'estado':estado, 'fecha':store.ahora().isoformat(), 'modo':'PAPER', 'sesion_id':sesion_id,
                    'espera_apagado_seg':round(time.monotonic()-inicio_apagado,3),
                    'fallos_escritura_apagado':fallos_escritura,
                    'salud':salud.snapshot(), 'monitor_vivo':monitor.is_alive(),
                    'scanner_en_curso':futuro is not None and not futuro.done()}))
            except Exception as error:
                fallos_escritura += 1
                if error_escritura is None:
                    error_escritura = error
                    logging.exception('No se pudo guardar estado; continúa el apagado seguro.')

        try:
            if futuro is not None:
                futuro.cancel()  # Solo cancela trabajo que aún no comenzó.
            publicar('DETENIENDO')
            while monitor.is_alive() or (futuro is not None and not futuro.done()):
                if monitor.is_alive():
                    monitor.join(timeout=1)
                else:
                    time.sleep(.1)
                publicar('DETENIENDO')
        finally:
            # Incluso si falla observabilidad, nunca retornar con trabajadores vivos.
            try:
                if monitor.ident is not None:
                    monitor.join()
            finally:
                pool.shutdown(wait=True, cancel_futures=True)
        if futuro is not None and not futuro.cancelled():
            try:
                salud.terminar('scanner', futuro.result())
            except Exception as error:
                salud.terminar('scanner', error=error)
        publicar('ERROR' if error_escritura else estado_final)
        if error_escritura is not None:
            raise error_escritura


def ejecutar_continuo(horas=8, automatico=False, intervalo_scanner=None, intervalo_monitor=None, reglas=False, sesion_id=None, profundidad=False):
    if type(profundidad) is not bool or (profundidad and not reglas):
        raise ValueError('Profundidad sólo disponible como selección explícita por reglas PAPER.')
    if reglas and automatico:
        raise ValueError('Modos Claude y reglas mutuamente excluyentes.')
    validar_horas(horas)
    sesion_id = validar_id(sesion_id) if sesion_id is not None else uuid.uuid4().hex
    cancelacion = cancelacion_sesion(config.DIRECTORIO, sesion_id)
    intervalo_scanner = config.INTERVALO_SCANNER_SEG if intervalo_scanner is None else intervalo_scanner
    intervalo_monitor = config.INTERVALO_MONITOR_SEG if intervalo_monitor is None else intervalo_monitor
    if not all(math.isfinite(i) and i>0 for i in (intervalo_scanner,intervalo_monitor)):
        raise ValueError('Intervalos inválidos.')
    preparar()
    if PARADA.exists() or cancelacion.exists():
        raise ValueError('DETENER_RUNNER existe. Usa --reanudar para retirarlo explícitamente.')
    finalizar = time.monotonic()+horas*3600
    parar = threading.Event()
    def sesion_activa():
        return time.monotonic() < finalizar and not PARADA.exists() and not cancelacion.exists() and not parar.is_set()
    salud = Salud()
    monitor = threading.Thread(target=monitor_continuo, args=(parar, intervalo_monitor, salud), name='paper-monitor')
    bandeja = config.DIRECTORIO/'respuestas'
    procesadas = bandeja/'procesadas'
    procesadas.mkdir(parents=True, exist_ok=True)
    vistas = set()
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='scanner')
    futuro = None
    siguiente = 0
    estado_final = 'DETENIDO'
    try:
        monitor.start()
        while sesion_activa():
            store.validar_paper()
            if futuro is not None and futuro.done():
                try:
                    salud.terminar('scanner',futuro.result())
                except Exception as error:
                    salud.terminar('scanner',error=error)
                    logging.exception('Fallo scanner: monitor sigue activo.')
                futuro = None
                siguiente = time.monotonic()+intervalo_scanner
            if futuro is None and time.monotonic() >= siguiente:
                salud.iniciar('scanner')
                if reglas:
                    futuro = pool.submit(escanear, sesion_activa=sesion_activa, reglas=True, profundidad=profundidad)
                else:
                    futuro = pool.submit(escanear, sesion_activa=sesion_activa)
            for ruta in (() if reglas else bandeja.glob('*.json')):
                if not sesion_activa():
                    break
                procesar_entrada_bandeja(ruta,procesadas,vistas,salud,automatico,
                    sesion_activa)
            guardar_atomico(ESTADO, store.serializar({'pid': os.getpid(), 'parent_pid':os.getppid(), 'modo': 'PAPER', 'sesion_id':sesion_id,
                'autorizacion': 'REGLAS_PAPER' if reglas else 'AUTO_PAPER' if automatico else 'MANUAL', 'estado': 'ACTIVO',
                'modelo_nuevas_entradas': 'PROFUNDIDAD_VISIBLE_FOK_PAPER_V1' if profundidad else 'TICKER_LEGADO',
                'heartbeat_utc': store.ahora().isoformat(), 'scanner_en_curso': futuro is not None,
                'salud':salud.snapshot(),
                'segundos_restantes': max(0, round(finalizar-time.monotonic()))}))
            parar.wait(min(1, max(0, finalizar-time.monotonic())))
    except KeyboardInterrupt:
        logging.info('Detención solicitada.')
    except Exception:
        estado_final = 'ERROR'
        raise
    finally:
        finalizar_trabajadores(parar, monitor, pool, futuro, salud, estado_final, sesion_id)
        logging.info('Sesión terminada. Posiciones PAPER pendientes requieren otro inicio del monitor.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--continuo', action='store_true')
    parser.add_argument('--auto-paper', action='store_true', help='Solo consume revisiones válidas; no consulta Claude por API.')
    parser.add_argument('--reglas-paper', action='store_true', help='Simulación autónoma por reglas, sin llamadas a IA; sesión explícita.')
    parser.add_argument('--profundidad-paper', action='store_true', help='Fills PAPER FOK con profundidad visible y evidencia; requiere --reglas-paper.')
    parser.add_argument('--horas', type=float, default=8)
    parser.add_argument('--prueba-claude', action='store_true')
    parser.add_argument('--detener', action='store_true')
    parser.add_argument('--reanudar', action='store_true')
    parser.add_argument('--sesion-id', help='Identificador técnico del intento explícito del panel.')
    args = parser.parse_args()
    if args.profundidad_paper and not args.reglas_paper:
        parser.error('--profundidad-paper requiere --reglas-paper')
    if args.reglas_paper and (not args.continuo or args.auto_paper or args.prueba_claude):
        parser.error('--reglas-paper requiere --continuo y excluye --auto-paper/--prueba-claude')
    if args.detener:
        PARADA.touch()
        print('Detención solicitada. Se terminarán las consultas en curso.')
        return
    if args.auto_paper and not args.continuo:
        parser.error('--auto-paper requiere --continuo')
    if args.prueba_claude and args.continuo:
        parser.error('La prueba Claude se realiza en un ciclo único.')
    try:
        if args.continuo:
            validar_horas(args.horas)
        if args.sesion_id is not None:
            validar_id(args.sesion_id)
            if not args.continuo or not args.reglas_paper:
                raise ValueError('--sesion-id requiere sesión continua PAPER por reglas.')
        store.validar_paper()
    except ValueError as error:
        parser.error(str(error))
    with instancia_unica():
        if args.sesion_id and cancelacion_sesion(config.DIRECTORIO, args.sesion_id).exists():
            raise ValueError('Inicio cancelado por petición de parada de esta sesión.')
        if args.reanudar:
            # Una BD discrepante no debe retirar siquiera la señal de parada.
            validar_arranque()
            PARADA.unlink(missing_ok=True)
        if args.continuo:
            ejecutar_continuo(args.horas, args.auto_paper, reglas=args.reglas_paper, sesion_id=args.sesion_id,
                              profundidad=args.profundidad_paper)
        else:
            print(ejecutar_ciclo(args.prueba_claude))


if __name__ == '__main__':
    main()
