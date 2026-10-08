"""Panel local PAPER. Abrirlo nunca arranca el runner; inicio explícito confirmado."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

import config
from paper_control import ControlPaper, validar_horas


def snapshot(directorio=None, base=None):
    """Lectura acotada, sin inicialización/migraciones ni consultas de mercado."""
    root = Path(directorio or config.DIRECTORIO)
    ruta = Path(base or config.BASE_DATOS).resolve()
    salida = {'modo': 'PAPER', 'solo_lectura': True,
              'observado_utc': datetime.now(timezone.utc).isoformat(),
              'cuenta': None, 'posiciones': [], 'solicitudes': [], 'eventos': [],
              'runner': None, 'errores': [], 'limite_listas': 100}
    if config.MODO != 'PAPER' or config.USAR_DINERO_REAL is not False:
        salida['errores'].append('CONFIGURACION_NO_PAPER: lectura bloqueada')
        return salida
    try:
        with closing(sqlite3.connect(ruta.as_uri()+'?mode=ro', uri=True, timeout=.2)) as con:
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA query_only=ON')
            con.execute('BEGIN')
            cuenta = con.execute('SELECT * FROM paper_account WHERE id=1').fetchone()
            if cuenta is None:
                raise ValueError('Cuenta ausente')
            # Publicar sólo si TODAS las consultas de esta instantánea terminan.
            datos = {'cuenta': dict(cuenta)}
            for nombre, consulta in (
                ('posiciones', "SELECT * FROM paper_trades WHERE estado='ABIERTA' ORDER BY id DESC LIMIT 100"),
                ('solicitudes', 'SELECT id,creado,expira,estado,ejecutable,plan FROM paper_requests ORDER BY creado DESC,id DESC LIMIT 100'),
                ('eventos', 'SELECT id,fecha,tipo,datos FROM paper_events ORDER BY id DESC LIMIT 100')):
                datos[nombre] = [dict(r) for r in con.execute(consulta)]
        salida.update(datos)
    except (sqlite3.Error, OSError, ValueError) as error:
        salida['errores'].append('BD_NO_VERIFICADA: '+type(error).__name__)
    try:
        with (root/'runner_status.json').open('rb') as archivo:
            texto = archivo.read(262145)
        if len(texto) > 262144:
            raise ValueError('Estado demasiado grande')
        runner = json.loads(texto)
        if not isinstance(runner, dict) or runner.get('modo') != 'PAPER':
            raise ValueError('Estado no PAPER')
        salida['runner'] = runner
    except (OSError, ValueError, UnicodeError) as error:
        salida['errores'].append('ESTADO_NO_VERIFICADO: '+type(error).__name__)
    try:
        # Las señales no demuestran que un proceso las haya aceptado.
        salida['pausa_solicitada'] = (root/'PAUSA_ENTRADAS').is_file()
        salida['parada_solicitada'] = (root/'DETENER_RUNNER').is_file()
    except OSError:
        salida['errores'].append('SENALES_NO_VERIFICADAS')
    return salida


def presentar(dato):
    """Texto reutilizado por UI y tests; no presenta un latido como prueba de vida."""
    cuenta = dato['cuenta']
    resumen = ('Saldo contable simulado: '+str(cuenta['saldo_actual'])+' USD\n'
               'Resultado realizado registrado: '+str(cuenta['pnl_acumulado'])+' USD\n'
               'No incluye valoración actual de posiciones abiertas.' if cuenta else
               'Saldo NO VERIFICADO. No se conservan cifras de una lectura anterior.')
    runner = dato['runner'] or {}
    resumen += ('\n\nÚltimo estado guardado: '+str(runner.get('estado', 'DESCONOCIDO'))+
                '\nFecha del estado: '+str(runner.get('heartbeat_utc') or runner.get('fecha') or 'DESCONOCIDA')+
                '\nProceso vivo: NO VERIFICADO. ACTIVO guardado no acredita actividad actual.'+
                '\nPausa solicitada: '+str(dato.get('pausa_solicitada', 'DESCONOCIDO'))+
                ' | Parada solicitada: '+str(dato.get('parada_solicitada', 'DESCONOCIDO'))+
                '\nLectura del panel: '+dato['observado_utc']+
                '\n\n'+('\n'.join(dato['errores']) or 'Lectura completada; no es una auditoría financiera.'))
    return {'Resumen': resumen,
            'Posiciones abiertas': json.dumps(dato['posiciones'], ensure_ascii=False, indent=2),
            'Solicitudes históricas': json.dumps(dato['solicitudes'], ensure_ascii=False, indent=2),
            'Eventos y errores': json.dumps(dato['eventos'], ensure_ascii=False, indent=2),
            'Salud guardada': json.dumps(dato['runner'], ensure_ascii=False, indent=2)}


def numero_visible(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        return 'NO VERIFICADO'
    # Conservar precisión de precios pequeños; no redondear a cero una posición.
    return str(valor)


def tablas(dato):
    """Filas de presentación; ningún estado histórico se convierte en permiso."""
    posiciones, solicitudes, eventos = [], [], []
    for fila in dato['posiciones']:
        posiciones.append((fila.get('id'), fila.get('simbolo'),
            *(numero_visible(fila.get(k)) for k in ('entrada', 'stop_precio', 'objetivo_precio',
                                                  'tamano_posicion', 'riesgo_usd')),
            fila.get('fecha_apertura')))
    for fila in dato['solicitudes']:
        try:
            plan = json.loads(fila['plan'])
            if not isinstance(plan, dict):
                raise ValueError('Plan no objeto')
            simbolo = plan.get('simbolo', 'DESCONOCIDO')
            origen = plan.get('origen_revision', 'CLAUDE (histórico)')
        except (ValueError, TypeError, KeyError):
            simbolo, origen = 'PLAN INVÁLIDO', 'NO VERIFICADO'
        prueba = {0: 'Prueba no ejecutable', 1: 'Normal; no es autorización'}.get(fila.get('ejecutable'), 'NO VERIFICADO')
        solicitudes.append((fila.get('id'), simbolo, fila.get('estado'), origen, prueba,
                            fila.get('creado'), fila.get('expira')))
    for fila in dato['eventos']:
        eventos.append((fila.get('id'), fila.get('fecha'), fila.get('tipo')))
    return {'Posiciones abiertas': posiciones, 'Solicitudes históricas': solicitudes,
            'Eventos y errores': eventos}


COLUMNAS = {
    'Posiciones abiertas': ('ID', 'Símbolo', 'Entrada', 'Stop', 'Objetivo', 'Capital USD', 'Riesgo USD', 'Apertura UTC'),
    'Solicitudes históricas': ('ID', 'Símbolo', 'Estado registrado', 'Origen', 'Clase', 'Creación UTC', 'Caducidad UTC'),
    'Eventos y errores': ('ID', 'Fecha UTC', 'Tipo'),
}


class ControlesPanel:
    """Enlace UI/controlador: ningún temporizador ni lectura llama a iniciar."""
    def __init__(self, ventana, controlador=None):
        import tkinter as tk
        from tkinter import ttk, messagebox
        self.ventana = ventana
        self.control = controlador or ControlPaper()
        self.dialogos = messagebox
        self.timer = None
        self.cerrado = False
        self.horas = tk.StringVar(master=ventana, value='')
        self.profundidad = tk.BooleanVar(master=ventana, value=False)
        self.estado = tk.StringVar(master=ventana)
        self.mensaje = tk.StringVar(master=ventana, value='Sin sesión iniciada desde este panel. Elige duración y confirma para iniciar PAPER.')
        marco = ttk.LabelFrame(ventana, text='Sesión PAPER por reglas · sin dinero real')
        marco.pack(fill='x', padx=12, pady=5)
        self.selector_fill = ttk.Checkbutton(marco, variable=self.profundidad,
            text='Nuevas entradas: profundidad visible FOK (optativo; sin parciales en el ledger)')
        self.selector_fill.pack(anchor='w', padx=6, pady=4)
        fila = ttk.Frame(marco)
        fila.pack(fill='x', padx=6, pady=5)
        ttk.Label(fila, text='Duración (horas, máximo 8):').pack(side='left')
        ttk.Entry(fila, textvariable=self.horas, width=7).pack(side='left', padx=6)
        self.botones = {}
        for nombre, accion in (('Iniciar PAPER', self.iniciar), ('Pausar entradas', self.pausar),
                               ('Reanudar entradas', self.reanudar), ('Detener sesión', self.detener)):
            boton = ttk.Button(fila, text=nombre, command=accion)
            boton.pack(side='left', padx=4)
            self.botones[nombre] = boton
        ttk.Label(marco, textvariable=self.estado, wraplength=930).pack(anchor='w', padx=6)
        ttk.Label(marco, textvariable=self.mensaje, wraplength=930).pack(anchor='w', padx=6, pady=4)
        self.refrescar()

    def refrescar(self):
        if self.cerrado:
            return
        if self.timer is not None:
            self.ventana.after_cancel(self.timer)
            self.timer = None
        try:
            observado = self.control.observar()
        except Exception:
            observado = {'estado':'PROCESO_NO_VERIFICADO', 'proceso_vivo':None}
        bloqueado = observado.get('proceso_vivo') is not False
        self.botones['Iniciar PAPER'].configure(state='disabled' if bloqueado else 'normal')
        self.selector_fill.configure(state='disabled' if bloqueado else 'normal')
        self.estado.set('Proceso de este panel: '+observado['estado']+
            '. Modelo solicitado: '+observado.get('modelo_solicitado', 'NO_VERIFICADO')+
            '. Otros procesos: no verificados. El registro no acredita salud ni rentabilidad.')
        self.timer = self.ventana.after(1000, self.refrescar)

    def error(self, error):
        # No volcar mensajes de excepción arbitrarios en el panel.
        texto = 'No se completó la acción ('+type(error).__name__+'). Sin reintento automático; revisa los registros.'
        self.mensaje.set(texto)
        self.dialogos.showerror('Acción no completada', texto, parent=self.ventana)
        self.refrescar()

    def iniciar(self):
        try:
            horas = validar_horas(float(self.horas.get().strip().replace(',', '.')))
        except (ValueError, OverflowError):
            self.dialogos.showerror('Duración inválida', 'Indica horas mayores que cero y hasta 8. Ejemplo: 0,5 = 30 minutos.', parent=self.ventana)
            return
        profundidad = self.profundidad.get()
        modelo = 'profundidad visible FOK' if profundidad else 'ticker legado (sin profundidad)'
        if not self.dialogos.askyesno('Confirmar inicio PAPER',
                f'¿Iniciar simulación autónoma durante {horas:g} horas?\n\n'
                f'Nuevas entradas: {modelo}. Posiciones anteriores conservan su modelo.\n'
                'Usará datos públicos y saldo ficticio; no accederá a tu cuenta Binance.\n'
                'No necesita revisiones IA por operación. La pausa previa se conserva.\n'
                'Cerrar el panel no detiene la sesión. Detener/apagar no liquida posiciones y deja de vigilarlas.',
                parent=self.ventana, default='no'):
            return
        self.botones['Iniciar PAPER'].configure(state='disabled')
        try:
            self.control.iniciar(horas, confirmado=True, profundidad=profundidad)
            self.mensaje.set('Inicio solicitado. Comprueba estado y salud; no se garantiza que haya entradas.')
        except Exception as error:
            self.error(error)
        finally:
            self.refrescar()

    def pausar(self):
        try:
            self.control.pausar()
            self.mensaje.set('Pausa solicitada: bloquea nuevas entradas al comprobar controles; el monitor continúa.')
        except Exception as error:
            self.error(error)

    def reanudar(self):
        if not self.dialogos.askyesno('Confirmar reanudación de entradas',
                '¿Quitar la pausa de entradas PAPER? No inicia un proceso ni quita la señal de parada ni extiende la sesión.',
                parent=self.ventana, default='no'):
            return
        try:
            self.control.reanudar_entradas(confirmado=True)
            self.mensaje.set('Pausa retirada. Esto NO inicia una sesión ni confirma que el monitor esté activo.')
        except Exception as error:
            self.error(error)

    def detener(self):
        try:
            self.control.detener()
            self.mensaje.set('Parada solicitada; espera terminación. No liquida posiciones ni elimina la pausa.')
        except Exception as error:
            self.error(error)
        finally:
            self.refrescar()

    def cerrar(self):
        try:
            vivo = self.control.observar().get('proceso_vivo')
        except Exception:
            vivo = None
        if vivo is not False and not self.dialogos.askyesno('Cerrar sólo el panel',
                'Hay un proceso propio vivo o no verificado. Cerrar esta ventana NO lo detiene.\n'
                'Para solicitar parada, cancela y pulsa Detener sesión. ¿Cerrar sólo el panel?',
                parent=self.ventana, default='no'):
            return
        self.cerrado = True
        if self.timer is not None:
            self.ventana.after_cancel(self.timer)
            self.timer = None
        self.ventana.destroy()


def abrir_panel():
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    ventana = tk.Tk()
    ventana.title('TRADING INTELLIGENCE · Panel PAPER')
    ventana.geometry('1000x790')
    ventana.minsize(950, 650)
    ttk.Label(ventana, text='PAPER · DINERO SIMULADO', font=('Segoe UI', 18, 'bold')).pack(pady=12)
    ttk.Label(ventana, text='Abrir o cerrar esta ventana NO inicia ni detiene el programa. No usa dinero real.').pack()
    ttk.Label(ventana, text='Últimos 100 registros por lista. No consulta precios ni calcula beneficios futuros.').pack(pady=5)
    controles = ControlesPanel(ventana)
    ventana.protocol('WM_DELETE_WINDOW', controles.cerrar)
    pestañas = ttk.Notebook(ventana)
    pestañas.pack(fill='both', expand=True, padx=12, pady=10)
    campos = {}
    vistas, contadores, detalles = {}, {}, {}
    for nombre in ('Resumen', 'Posiciones abiertas', 'Solicitudes históricas', 'Eventos y errores', 'Salud guardada'):
        marco = ttk.Frame(pestañas)
        pestañas.add(marco, text=nombre)
        if nombre in COLUMNAS:
            contador = ttk.Label(marco)
            contador.pack(anchor='w', padx=5, pady=4)
            contadores[nombre] = contador
            caja = ttk.Frame(marco)
            caja.pack(fill='both', expand=True)
            columnas = tuple(str(i) for i in range(len(COLUMNAS[nombre])))
            vista = ttk.Treeview(caja, columns=columnas, show='headings', selectmode='browse', height=8)
            for columna, titulo in zip(columnas, COLUMNAS[nombre]):
                vista.heading(columna, text=titulo)
                vista.column(columna, width=150, minwidth=80)
            vertical = ttk.Scrollbar(caja, orient='vertical', command=vista.yview)
            horizontal = ttk.Scrollbar(caja, orient='horizontal', command=vista.xview)
            vista.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
            vista.grid(row=0, column=0, sticky='nsew')
            vertical.grid(row=0, column=1, sticky='ns')
            horizontal.grid(row=1, column=0, sticky='ew')
            caja.rowconfigure(0, weight=1)
            caja.columnconfigure(0, weight=1)
            vistas[nombre] = vista
            ttk.Label(marco, text='Selecciona una fila para consultar su registro completo (sin modificarlo).').pack(anchor='w')
        campo = ScrolledText(marco, wrap='word', font=('Consolas', 11))
        campo.configure(height=6)
        campo.pack(fill='both', expand=nombre not in COLUMNAS)
        campos[nombre] = campo
        if nombre in COLUMNAS:
            def seleccionar(_evento, nombre=nombre):
                seleccion = vistas[nombre].selection()
                if seleccion:
                    mostrar(nombre, detalles[nombre][int(seleccion[0])])
            vistas[nombre].bind('<<TreeviewSelect>>', seleccionar)

    def mostrar(nombre, contenido):
        campo = campos[nombre]
        campo.configure(state='normal')
        campo.delete('1.0', 'end')
        campo.insert('1.0', contenido)
        campo.configure(state='disabled')

    def actualizar():
        dato = snapshot()
        textos = presentar(dato)
        for nombre in ('Resumen', 'Salud guardada'):
            mostrar(nombre, textos[nombre])
        claves = {'Posiciones abiertas': 'posiciones', 'Solicitudes históricas': 'solicitudes',
                  'Eventos y errores': 'eventos'}
        for nombre, filas in tablas(dato).items():
            vista = vistas[nombre]
            for identidad in vista.get_children():
                vista.delete(identidad)
            detalles[nombre] = [json.dumps(f, ensure_ascii=False, indent=2) for f in dato[claves[nombre]]]
            for i, fila in enumerate(filas):
                vista.insert('', 'end', iid=str(i), values=fila)
            contadores[nombre].configure(text=f'{len(filas)} registros mostrados (máximo 100). Históricos, no autorizantes.')
            mostrar(nombre, 'Selecciona una fila.' if filas else
                    'Sin registros en esta lectura. Consulta Resumen para ver errores o datos no verificados.')

    acciones = ttk.Frame(ventana)
    acciones.pack(pady=8)
    ttk.Button(acciones, text='Actualizar lectura', command=actualizar).pack(side='left', padx=8)
    ttk.Button(acciones, text='Cerrar observador', command=controles.cerrar).pack(side='left', padx=8)
    actualizar()
    ventana.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Leer estado sin abrir ventana')
    args = parser.parse_args()
    if args.json:
        dato = snapshot()
        print(json.dumps(dato, ensure_ascii=False, indent=2))
        return 2 if dato['errores'] else 0
    abrir_panel()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
