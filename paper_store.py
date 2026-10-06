"""Persistencia transaccional PAPER. No contiene un conector de órdenes reales."""
import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

import config


def ahora():
    return datetime.now(timezone.utc)


def serializar(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def huella(obj):
    return hashlib.sha256(serializar(obj).encode()).hexdigest()


@contextmanager
def conectar():
    con = sqlite3.connect(config.BASE_DATOS, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def inicializar():
    with conectar() as con:
        halt_nuevo = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_halt'").fetchone() is None
        con.executescript('''
        CREATE TABLE IF NOT EXISTS paper_account (
          id INTEGER PRIMARY KEY, capital_inicial REAL NOT NULL,
          saldo_actual REAL NOT NULL, pnl_acumulado REAL NOT NULL,
          fecha_creacion TEXT NOT NULL, fecha_actualizacion TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS paper_trades (
          id INTEGER PRIMARY KEY AUTOINCREMENT, simbolo TEXT NOT NULL,
          fecha_apertura TEXT NOT NULL, estado TEXT NOT NULL, entrada REAL NOT NULL,
          stop_precio REAL NOT NULL, objetivo_precio REAL NOT NULL,
          tamano_posicion REAL NOT NULL, riesgo_usd REAL NOT NULL,
          precio_salida REAL, fecha_cierre TEXT, resultado_usd REAL, resultado_pct REAL);
        CREATE TABLE IF NOT EXISTS paper_requests (
          id TEXT PRIMARY KEY, creado TEXT NOT NULL, expira TEXT NOT NULL,
          ejecutable INTEGER NOT NULL, plan TEXT NOT NULL, plan_hash TEXT NOT NULL,
          estado TEXT NOT NULL DEFAULT 'PENDIENTE', respuesta TEXT, trade_id INTEGER);
        CREATE TABLE IF NOT EXISTS paper_events (
          id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, tipo TEXT NOT NULL, datos TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS paper_flows (
          id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, monto REAL NOT NULL, nota TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS paper_days (
          dia TEXT PRIMARY KEY, capital_base REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS paper_halt (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          activo INTEGER NOT NULL CHECK (activo IN (0, 1)),
          razon TEXT NOT NULL, pico_equity REAL, equity_activacion REAL,
          fecha_actualizacion TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS paper_equity_hist (
          id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, equity REAL NOT NULL);
        ''')
        columnas_halt = {r['name'] for r in con.execute('PRAGMA table_info(paper_halt)')}
        if 'ultimo_ok' not in columnas_halt:
            con.execute('ALTER TABLE paper_halt ADD COLUMN ultimo_ok TEXT')
        con.execute('BEGIN IMMEDIATE')
        columnas = {r['name'] for r in con.execute('PRAGMA table_info(paper_trades)')}
        if 'comision_pct_apertura' not in columnas:
            con.execute('ALTER TABLE paper_trades ADD COLUMN comision_pct_apertura REAL')
            evento(con, 'MIGRACION_COMISION', {
                'version': 1, 'politica': 'No rellenar tarifas históricas desconocidas',
                'operaciones_sin_tarifa': con.execute('SELECT COUNT(*) FROM paper_trades').fetchone()[0]})
        fecha = ahora().isoformat()
        con.execute('INSERT OR IGNORE INTO paper_account VALUES (1,?,?,?,?,?)',
                    (config.CAPITAL_USD, config.CAPITAL_USD, 0, fecha, fecha))
        # Fila inicial sólo al crear la tabla: si luego desaparece, es corrupción y se bloquea (fail-closed).
        if halt_nuevo:
            con.execute('INSERT OR IGNORE INTO paper_halt(id,activo,razon,fecha_actualizacion) VALUES (1,0,?,?)',
                        ('', fecha))
            evento(con, 'HALT_INICIALIZADO', {'activo': 0})


def evento(con, tipo, datos):
    con.execute('INSERT INTO paper_events(fecha,tipo,datos) VALUES (?,?,?)',
                (ahora().isoformat(), tipo, serializar(datos)))


def cuenta():
    inicializar()
    with conectar() as con:
        return dict(con.execute('SELECT * FROM paper_account WHERE id=1').fetchone())


def resumen(con):
    filas = con.execute("SELECT tamano_posicion,riesgo_usd,comision_pct_apertura "
                        "FROM paper_trades WHERE estado='ABIERTA'").fetchall()
    nominal = math.fsum(numero(f['tamano_posicion']) for f in filas)
    capital = math.fsum(capital_requerido(f['tamano_posicion'], f['comision_pct_apertura'])
                        for f in filas)
    riesgo = math.fsum(numero(f['riesgo_usd']) for f in filas)
    if not all(math.isfinite(v) for v in (nominal, capital, riesgo)):
        raise ValueError('Compromisos financieros no finitos.')
    return {'n': len(filas), 'capital': capital, 'riesgo': riesgo,
            'nominal': nominal, 'comisiones_entrada': capital-nominal}


def capital_requerido(tamano_posicion, comision_pct):
    """Efectivo reservado: compra más comisión de entrada, aún no liquidada."""
    capital = numero(tamano_posicion) * (1 + validar_comision(comision_pct)/100)
    return numero(capital)


def asegurar_dia(con, fecha, saldo):
    """Fija la base antes del primer cierre o apertura del día local."""
    dia = fecha.astimezone(timezone(timedelta(hours=-5))).date().isoformat()
    con.execute('INSERT OR IGNORE INTO paper_days VALUES (?,?)', (dia, saldo))
    base = con.execute('SELECT capital_base FROM paper_days WHERE dia=?', (dia,)).fetchone()[0]
    return dia, base


def validar_paper():
    if config.MODO != 'PAPER' or config.USAR_DINERO_REAL:
        raise ValueError('Este ejecutor solo admite PAPER.')


def numero(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor) or valor <= 0:
        raise ValueError('Valor financiero inválido.')
    return float(valor)


def validar_comision(valor):
    if (isinstance(valor, bool) or not isinstance(valor, (int, float))
            or not math.isfinite(valor) or not 0 <= valor < 100):
        raise ValueError('Comisión PAPER ausente o inválida; requiere propuesta nueva o revisión histórica.')
    return float(valor)


def validar_plan(plan):
    if plan.get('modo') != 'PAPER' or plan.get('decision') != 'PAPER CANDIDATE':
        raise ValueError('Plan no ejecutable.')
    entrada, stop, objetivo, posicion = (numero(plan[k]) for k in
        ('entrada', 'stop_precio', 'objetivo_precio', 'tamano_posicion'))
    if not 0 < stop < entrada < objetivo:
        raise ValueError('Niveles de entrada/stop/objetivo inválidos.')
    comision = validar_comision(plan.get('comision_paper_pct')) / 100
    riesgo = posicion * ((entrada-stop)/entrada + 2*comision)
    return entrada, stop, objetivo, posicion, riesgo


class SesionFinalizada(RuntimeError):
    """Cancelación cooperativa; no es un fallo de mercado."""


def comprobar_sesion(sesion_activa):
    if sesion_activa is not None and not sesion_activa():
        raise SesionFinalizada('La sesión terminó; no generar solicitudes nuevas.')


def registrar_solicitud(plan, ejecutable, sesion_activa=None):
    import uuid
    comprobar_sesion(sesion_activa)
    inicializar()
    if ejecutable:
        validar_plan(plan)
    fecha = ahora()
    identidad = uuid.uuid4().hex
    digest = huella(plan)
    with conectar() as con:
        con.execute('BEGIN IMMEDIATE')
        comprobar_sesion(sesion_activa)
        con.execute('INSERT INTO paper_requests(id,creado,expira,ejecutable,plan,plan_hash) VALUES(?,?,?,?,?,?)',
            (identidad, fecha.isoformat(), (fecha+timedelta(minutes=config.MINUTOS_MAXIMOS_RESPUESTA_CLAUDE)).isoformat(),
             int(ejecutable), serializar(plan), digest))
        evento(con, 'SOLICITUD', {'id': identidad, 'ejecutable': ejecutable})
        comprobar_sesion(sesion_activa)
    return identidad, digest


def caducar_solicitudes():
    """Transición durable independiente del rollback de una apertura rechazada."""
    inicializar()
    fecha = ahora()
    with conectar() as con:
        con.execute('BEGIN IMMEDIATE')
        pendientes = con.execute("SELECT id,expira FROM paper_requests WHERE estado='PENDIENTE'").fetchall()
        caducadas = [r for r in pendientes if datetime.fromisoformat(r['expira']) <= fecha]
        for fila in caducadas:
            con.execute("UPDATE paper_requests SET estado='CADUCADA' WHERE id=?",(fila['id'],))
            evento(con,'SOLICITUD_CADUCADA',{'request_id':fila['id'],'expira':fila['expira']})
    return len(caducadas)


def registrar_rechazo(origen, respuesta, motivo):
    """Audita metadatos acotados, nunca guarda el archivo externo completo."""
    inicializar()
    identidad = respuesta.get('request_id') if isinstance(respuesta,dict) else None
    if not isinstance(identidad,str) or len(identidad) != 32 or any(c not in '0123456789abcdef' for c in identidad):
        identidad = None
    with conectar() as con:
        evento(con,'VALIDACION_RECHAZADA',{'origen':origen,'request_id':identidad,'motivo':str(motivo)[:300]})


def leer_solicitud(identidad):
    inicializar()
    with conectar() as con:
        fila = con.execute('SELECT * FROM paper_requests WHERE id=?', (identidad,)).fetchone()
        if fila is None:
            raise ValueError('Solicitud desconocida.')
        return dict(fila)


def validar_respuesta(fila, respuesta):
    if fila['estado'] == 'CADUCADA':
        raise ValueError('Solicitud caducada; generar datos nuevos.')
    if fila['estado'] != 'PENDIENTE':
        raise ValueError('Solicitud ya consumida.')
    if ahora() >= datetime.fromisoformat(fila['expira']):
        raise ValueError('Solicitud caducada; generar datos nuevos.')
    plan = json.loads(fila['plan'])
    if plan.get('origen_revision', 'CLAUDE') != 'CLAUDE':
        raise ValueError('Esta solicitud no pertenece al circuito Claude.')
    if respuesta.get('request_id') != fila['id'] or respuesta.get('plan_hash') != fila['plan_hash']:
        raise ValueError('Respuesta no corresponde a esta propuesta.')
    if huella(plan) != fila['plan_hash'] or respuesta.get('simbolo') != plan['simbolo']:
        raise ValueError('Propuesta alterada o símbolo incorrecto.')
    if respuesta.get('decision') not in ('APROBAR_PAPER', 'RECHAZAR'):
        raise ValueError('Decisión inválida.')
    confianza = respuesta.get('confianza')
    if type(confianza) is not int or not 0 <= confianza <= 100:
        raise ValueError('Confianza inválida.')
    if not isinstance(respuesta.get('razon'), str) or len(respuesta['razon']) > 500:
        raise ValueError('Razón inválida.')
    if respuesta['decision'] == 'APROBAR_PAPER':
        if not fila['ejecutable']:
            raise ValueError('La prueba no puede abrir operaciones.')
        if confianza < config.CONFIANZA_MINIMA_CLAUDE:
            raise ValueError('Confianza insuficiente.')
        validar_plan(plan)
    return plan


def ejecutar_respuesta(respuesta, autorizacion, precio_actual=None, automatico=False, sesion_activa=None):
    """Validación, consumo del ID e inserción en una sola transacción."""
    validar_paper()
    caducar_solicitudes()
    with conectar() as con:
        con.execute('BEGIN IMMEDIATE')
        fila = con.execute('SELECT * FROM paper_requests WHERE id=?', (respuesta.get('request_id'),)).fetchone()
        if fila is None:
            raise ValueError('Solicitud desconocida.')
        plan = validar_respuesta(fila, respuesta)
        if respuesta['decision'] == 'RECHAZAR':
            con.execute("UPDATE paper_requests SET estado='RECHAZADA',respuesta=? WHERE id=?",
                        (serializar(respuesta), fila['id']))
            evento(con, 'RECHAZO_CLAUDE', respuesta)
            return {'registrada': False, 'motivo': respuesta['razon']}
        if not automatico and autorizacion != 'OK ' + fila['id']:
            raise ValueError('Falta autorización local OK <ID>.')
        return _abrir_validado(con, fila, plan, respuesta, precio_actual, automatico,
                              sesion_activa, autorizacion, 'CLAUDE')


def _abrir_validado(con, fila, plan, respuesta, precio_actual, automatico,
                    sesion_activa, autorizacion, origen, evidencia_fill=None):
    """Controles financieros y apertura atómica comunes a ambos modos PAPER."""
    entrada, stop, objetivo, posicion, riesgo = validar_plan(plan)
    precio_actual = numero(precio_actual)
    if abs(precio_actual/entrada-1)*100 > config.DESVIACION_MAXIMA_PRECIO_PCT:
        raise ValueError('El precio cambió: generar y revisar una propuesta nueva.')
    if not stop < precio_actual < objetivo:
        raise ValueError('Precio fuera del rango del plan.')
    if (config.DIRECTORIO / 'PAUSA_ENTRADAS').exists():
        raise ValueError('Nuevas entradas pausadas.')
    bloqueado, nuevo, motivo = _evaluar_halt(con)
    if bloqueado:
        if nuevo:
            # Retorno normal: la activación se confirma aunque la entrada quede rechazada.
            return {'registrada': False, 'motivo': motivo}
        raise ValueError(motivo)
    saldo = con.execute('SELECT saldo_actual FROM paper_account WHERE id=1').fetchone()[0]
    estado = resumen(con)
    dia, base = asegurar_dia(con, ahora(), saldo)
    perdidas = con.execute("SELECT COALESCE(-SUM(resultado_usd),0) FROM paper_trades "
        "WHERE resultado_usd < 0 AND date(fecha_cierre,'-5 hours')=?", (dia,)).fetchone()[0]
    # Se registra el fill simulado actual y se conserva el plan exacto en la solicitud.
    comision_pct = validar_comision(plan.get('comision_paper_pct'))
    riesgo = posicion * ((precio_actual-stop)/precio_actual + 2*comision_pct/100)
    if saldo <= 0 or riesgo > saldo*config.RIESGO_POR_OPERACION_PCT/100 + 1e-8:
        raise ValueError('Supera riesgo por operación.')
    if estado['n'] >= config.MAX_OPERACIONES_ABIERTAS:
        raise ValueError('Máximo de operaciones abiertas alcanzado.')
    if con.execute("SELECT 1 FROM paper_trades WHERE simbolo=? AND estado='ABIERTA'", (plan['simbolo'],)).fetchone():
        raise ValueError('Ya existe una operación abierta del símbolo.')
    if capital_requerido(posicion, comision_pct) > saldo-estado['capital'] + 1e-8:
        raise ValueError('Capital disponible insuficiente.')
    if perdidas+estado['riesgo']+riesgo > base*config.RIESGO_MAXIMO_DIARIO_PCT/100 + 1e-8:
        raise ValueError('Límite diario: pérdidas realizadas más riesgo abierto.')
    if automatico and (sesion_activa is None or not sesion_activa()):
        raise ValueError('Sesión automática ausente, detenida o caducada.')
    fill_validado = comprobar_fill(plan, evidencia_fill, lado='BUY', monto=posicion,
                                  precio=precio_actual, comision_pct=comision_pct)
    fecha = ahora().isoformat()
    cur = con.execute('''INSERT INTO paper_trades
      (simbolo,fecha_apertura,estado,entrada,stop_precio,objetivo_precio,tamano_posicion,riesgo_usd,comision_pct_apertura)
      VALUES (?,?,'ABIERTA',?,?,?,?,?,?)''',
      (plan['simbolo'], fecha, precio_actual, stop, objetivo, posicion, riesgo, comision_pct))
    con.execute("UPDATE paper_requests SET estado='EJECUTADA',respuesta=?,trade_id=? WHERE id=?",
                (serializar(respuesta), cur.lastrowid, fila['id']))
    datos_apertura = {'request_id': fila['id'], 'trade_id': cur.lastrowid,
                            'comision_paper_pct': comision_pct,
                            'autorizacion': ('SESION_REGLAS_PAPER' if origen == 'REGLAS_PAPER_V1' else
                                                 'SESION_AUTO_PAPER') if automatico else autorizacion,
                                'origen_revision': origen}
    if fill_validado is not None:
        datos_apertura['evidencia_fill'] = fill_validado
    evento(con, 'APERTURA', datos_apertura)
    if automatico and (sesion_activa is None or not sesion_activa()):
        raise ValueError('Sesión automática terminada antes de confirmar.')
    validar_paper()
    if fill_validado is not None:
        from paper_fills import validar_snapshot, MAX_EDAD_MS
        validar_snapshot(fill_validado['snapshot'], ahora_ms=int(ahora().timestamp()*1000), max_edad_ms=MAX_EDAD_MS)
    return {'registrada': True, 'id': cur.lastrowid, 'simbolo': plan['simbolo'], 'entrada': precio_actual}


def ejecutar_reglas(identidad, digest, precio_actual, sesion_activa, *, evidencia_fill=None):
    """Ruta independiente; nunca inventa revisión ni confianza de Claude."""
    validar_paper()
    if sesion_activa is None or not sesion_activa():
        raise ValueError('Sesión de reglas ausente, detenida o caducada.')
    caducar_solicitudes()
    with conectar() as con:
        con.execute('BEGIN IMMEDIATE')
        fila = con.execute('SELECT * FROM paper_requests WHERE id=?', (identidad,)).fetchone()
        if fila is None or fila['estado'] != 'PENDIENTE':
            raise ValueError('Solicitud desconocida o consumida.')
        if ahora() >= datetime.fromisoformat(fila['expira']):
            raise ValueError('Solicitud caducada.')
        plan = json.loads(fila['plan'])
        if not fila['ejecutable'] or plan.get('origen_revision') != 'REGLAS_PAPER_V1':
            raise ValueError('Solicitud no pertenece al modo de reglas PAPER.')
        if fila['plan_hash'] != digest or huella(plan) != digest:
            raise ValueError('Propuesta de reglas alterada.')
        if plan.get('consenso') != 'ALCISTA' or plan.get('estado') != 'ALCISTA MOMENTUM SANO':
            raise ValueError('No cumple las reglas de la estrategia vigente.')
        decision = {'origen_revision': 'REGLAS_PAPER_V1', 'request_id': identidad,
                    'plan_hash': digest, 'simbolo': plan['simbolo'], 'decision': 'EJECUTAR_REGLAS_PAPER'}
        return _abrir_validado(con, fila, plan, decision, precio_actual, True,
                              sesion_activa, '', 'REGLAS_PAPER_V1', evidencia_fill)


def comprobar_fill(plan, evidencia_fill, *, lado, monto, precio, comision_pct):
    modelo = plan.get('modelo_fill_paper')
    if modelo is None:
        if evidencia_fill is not None:
            raise ValueError('Evidencia no admitida sin modelo en plan inmutable.')
        return None
    from paper_fills import MODELO, validar_evidencia
    if modelo != MODELO:
        raise ValueError('Modelo de fill no admitido.')
    return validar_evidencia(evidencia_fill, simbolo=plan['simbolo'], lado=lado, monto=monto,
                             comision_pct=comision_pct, precio=precio,
                             ahora_ms=int(ahora().timestamp()*1000))


def calcular_resultado_cierre(entrada, tamano_posicion, precio_salida, comision_pct):
    """Cálculo puro compartido PAPER/historia; no elige precios ni ejecuta."""
    entrada, posicion, salida = (numero(v) for v in (entrada, tamano_posicion, precio_salida))
    comision = validar_comision(comision_pct)
    retorno = salida/entrada-1
    comisiones = posicion*(2+retorno)*comision/100
    bruto = posicion*retorno
    pnl = bruto-comisiones
    resultado_pct = pnl/posicion*100
    if not all(math.isfinite(v) for v in (retorno, comisiones, bruto, pnl, resultado_pct)):
        raise ValueError('Resultado financiero no finito.')
    return {'resultado_bruto_usd':bruto, 'comisiones_estimadas':comisiones,
            'resultado_usd':pnl, 'resultado_pct':resultado_pct}


def preparar_cierre(con, fila):
    """Plan inmutable y compra original verificada a su fecha, también tras reinicio."""
    validar_comision(fila['comision_pct_apertura'])
    solicitudes = con.execute('SELECT id,plan,plan_hash FROM paper_requests WHERE trade_id=?',
                              (fila['id'],)).fetchall()
    if len(solicitudes) != 1:
        raise ValueError('Falta solicitud única para verificar modelo de cierre.')
    plan = json.loads(solicitudes[0]['plan'])
    if huella(plan) != solicitudes[0]['plan_hash']:
        raise ValueError('Plan de cierre alterado.')
    if plan.get('modelo_fill_paper') is None:
        return plan, None
    from paper_fills import MODELO, validar_evidencia
    if plan.get('modelo_fill_paper') != MODELO:
        raise ValueError('Modelo de fill no admitido.')
    registros = con.execute("SELECT datos FROM paper_events WHERE tipo='APERTURA' "
                            "AND json_valid(datos) AND json_extract(datos,'$.trade_id')=?",
                            (fila['id'],)).fetchall()
    if len(registros) != 1:
        raise ValueError('Falta evento único de apertura para verificar cantidad base.')
    apertura = json.loads(registros[0]['datos'])
    if apertura.get('request_id') != solicitudes[0]['id']:
        raise ValueError('Evento de apertura no corresponde a la solicitud.')
    fecha = datetime.fromisoformat(fila['fecha_apertura'])
    if fecha.tzinfo is None:
        raise ValueError('Fecha de apertura sin zona horaria.')
    evidencia = validar_evidencia(apertura.get('evidencia_fill'), simbolo=fila['simbolo'],
                                 lado='BUY', monto=fila['tamano_posicion'],
                                 comision_pct=fila['comision_pct_apertura'], precio=fila['entrada'],
                                 ahora_ms=int(fecha.timestamp()*1000))
    return plan, evidencia


def _precio_para_equity(simbolo):
    """Cotización pública; se resuelve en cada llamada para permitir inyección en pruebas."""
    from market_http import precio_actual
    return precio_actual(simbolo)


def equity_mtm(con, precio_fn=None):
    """Saldo realizado más resultado no realizado, con el mismo cálculo que usaría el cierre.
    Un precio ausente o inválido eleva error: nunca se sustituye por saldo_actual."""
    precio_fn = precio_fn or _precio_para_equity
    saldo = con.execute('SELECT saldo_actual FROM paper_account WHERE id=1').fetchone()[0]
    abiertas = con.execute("SELECT simbolo,entrada,tamano_posicion,comision_pct_apertura "
                           "FROM paper_trades WHERE estado='ABIERTA'").fetchall()
    no_realizados = []
    for fila in abiertas:
        try:
            precio = precio_fn(fila['simbolo'])
        except Exception as error:
            raise ValueError('Precio no disponible para calcular equity; entradas bloqueadas.') from error
        no_realizados.append(calcular_resultado_cierre(fila['entrada'], fila['tamano_posicion'],
                                                       precio, fila['comision_pct_apertura'])['resultado_usd'])
    equity = saldo + math.fsum(no_realizados)
    if not math.isfinite(equity):
        raise ValueError('Equity no finito.')
    return equity


def _umbral_valido(umbral):
    return (isinstance(umbral, (int, float)) and not isinstance(umbral, bool)
            and math.isfinite(umbral) and umbral > 0)


def _drawdown_pct(equity, pico):
    return (pico-equity)/pico*100 if pico > 0 else 0.0


DIAS_VENTANA_PICO = 30   # pico = máximo de equity en los últimos 30 días (RISK_ENGINE_SPEC drawdown_lookback_days)
SEG_WATCHDOG = 60        # fallo de valoración con posiciones abiertas durante más de 60 s -> halt persistente


def _pico_rodante(con, equity, instante, registrar):
    """Pico de equity en la ventana rodante. Con registrar=True guarda la muestra y poda lo caducado."""
    limite = (instante - timedelta(days=DIAS_VENTANA_PICO)).isoformat()
    if registrar:
        con.execute('INSERT INTO paper_equity_hist(fecha,equity) VALUES (?,?)', (instante.isoformat(), equity))
        con.execute('DELETE FROM paper_equity_hist WHERE fecha < ?', (limite,))
    pico = con.execute('SELECT MAX(equity) FROM paper_equity_hist WHERE fecha >= ?', (limite,)).fetchone()[0]
    return equity if pico is None else max(equity, pico)


def _watchdog(con, fila, instante, error):
    """Sin valoración válida con posiciones abiertas: halt persistente sólo si el hueco supera 60 s."""
    if fila['ultimo_ok'] is None:
        hueco = float('inf')
    else:
        hueco = (instante - datetime.fromisoformat(fila['ultimo_ok'])).total_seconds()
    if hueco <= SEG_WATCHDOG:
        raise error
    razon = f'CONNECTIVITY_WATCHDOG: sin valoración válida desde hace {hueco:.0f} s (límite {SEG_WATCHDOG} s)'
    fecha = instante.isoformat()
    con.execute('UPDATE paper_halt SET activo=1,razon=?,fecha_actualizacion=? WHERE id=1', (razon, fecha))
    evento(con, 'HALT_ACTIVADO', {'razon': razon, 'hueco_s': None if hueco == float('inf') else hueco})
    return True, True, razon


def _evaluar_halt(con, precio_fn=None):
    """Único punto de decisión de riesgo. Escribe muestra, pico y activación en la transacción del llamante.
    Devuelve (bloqueado, nuevo, motivo).
    - Halt persistente (DRAWDOWN_HALT_PCT): sólo se activa aquí y sólo se libera con liberar_halt.
    - Pausa (DRAWDOWN_PAUSE_PCT): bloquea entradas mientras dure; NO es persistente, se recalcula y se reanuda sola.
    - Watchdog: fallo de valoración con posiciones abiertas > 60 s activa el halt persistente.
    Fail-closed: estado ausente/corrupto o umbral no aprobado lanza error. Cierres nunca se bloquean aquí."""
    fila = con.execute('SELECT activo,razon,ultimo_ok FROM paper_halt WHERE id=1').fetchone()
    if fila is None or fila['activo'] not in (0, 1):
        raise ValueError('Estado de halt ausente o corrupto; entradas bloqueadas.')
    if fila['activo'] == 1:
        return True, False, 'Halt de riesgo activo: ' + fila['razon']
    umbral = config.DRAWDOWN_HALT_PCT
    if not _umbral_valido(umbral):
        raise ValueError('Umbral de halt por drawdown no aprobado; entradas bloqueadas.')
    pausa = config.DRAWDOWN_PAUSE_PCT
    if pausa is not None and not (_umbral_valido(pausa) and pausa < umbral):
        raise ValueError('Umbral de pausa inválido; entradas bloqueadas.')
    instante = ahora()
    try:
        equity = equity_mtm(con, precio_fn)
    except ValueError as error:
        return _watchdog(con, fila, instante, error)
    fecha = instante.isoformat()
    con.execute('UPDATE paper_halt SET ultimo_ok=? WHERE id=1', (fecha,))
    pico = _pico_rodante(con, equity, instante, registrar=True)
    dd = _drawdown_pct(equity, pico)
    con.execute('UPDATE paper_halt SET pico_equity=?,fecha_actualizacion=? WHERE id=1', (pico, fecha))
    if dd >= umbral:
        razon = f'DRAWDOWN_HALT {dd:.4f}% desde pico {pico:.4f} en {DIAS_VENTANA_PICO} d (umbral {umbral}%)'
        con.execute('UPDATE paper_halt SET activo=1,razon=?,equity_activacion=?,fecha_actualizacion=? WHERE id=1',
                    (razon, equity, fecha))
        evento(con, 'HALT_ACTIVADO', {'razon': razon, 'equity': equity, 'pico': pico,
                                      'drawdown_pct': dd, 'umbral_pct': umbral})
        return True, True, razon
    if pausa is not None and dd >= pausa:
        return True, False, f'PAUSA_DRAWDOWN {dd:.4f}% (pausa {pausa}%): entradas pausadas, se reanudan solas; cierres permitidos'
    return False, False, ''


def evaluar_riesgo(precio_fn=None):
    """Evaluación independiente de aperturas: fija el pico con MTM aunque no haya intento de entrada."""
    validar_paper()
    inicializar()
    with conectar() as con:
        con.execute('BEGIN IMMEDIATE')
        bloqueado, nuevo, motivo = _evaluar_halt(con, precio_fn)
    return {'bloqueado': bloqueado, 'nuevo': nuevo, 'motivo': motivo}


def liberar_halt(*, confirmado=False, precio_fn=None):
    """Única salida del halt: exige confirmación explícita y drawdown actual por debajo del umbral."""
    validar_paper()
    if confirmado is not True:
        raise ValueError('Se requiere confirmación explícita para liberar el halt de riesgo.')
    inicializar()
    with conectar() as con:
        con.execute('BEGIN IMMEDIATE')
        fila = con.execute('SELECT activo,pico_equity FROM paper_halt WHERE id=1').fetchone()
        if fila is None or fila['activo'] not in (0, 1):
            raise ValueError('Estado de halt ausente o corrupto; no liberar sin revisión.')
        if fila['activo'] == 0:
            return {'liberado': False, 'motivo': 'Sin halt activo.'}
        umbral = config.DRAWDOWN_HALT_PCT
        if not _umbral_valido(umbral):
            raise ValueError('Umbral de halt por drawdown no aprobado; no liberar.')
        equity = equity_mtm(con, precio_fn)  # sin valoración válida no se libera nunca
        pico = _pico_rodante(con, equity, ahora(), registrar=False)
        dd = _drawdown_pct(equity, pico)
        if dd >= umbral:
            raise ValueError('Drawdown sigue por encima del umbral; halt no liberable.')
        fecha = ahora().isoformat()
        con.execute("UPDATE paper_halt SET activo=0,razon='',pico_equity=?,fecha_actualizacion=? WHERE id=1",
                    (pico, fecha))
        evento(con, 'HALT_LIBERADO', {'equity': equity, 'pico': pico,
                                      'drawdown_pct': dd, 'umbral_pct': umbral})
        return {'liberado': True, 'equity': equity, 'pico': pico, 'drawdown_pct': dd}


def cerrar(identidad, precio, motivo, *, evidencia_fill=None):
    validar_paper()
    precio = numero(precio)
    if motivo not in ('CERRADA_STOP', 'CERRADA_OBJETIVO', 'CERRADA_MANUAL'):
        raise ValueError('Motivo de cierre inválido.')
    inicializar()
    with conectar() as con:
        con.execute('BEGIN IMMEDIATE')
        fila = con.execute("SELECT * FROM paper_trades WHERE id=? AND estado='ABIERTA'", (identidad,)).fetchone()
        if fila is None:
            return {'cerrada': False, 'resultado_usd': 0, 'resultado_pct': 0}
        plan, apertura_fill = preparar_cierre(con, fila)
        cantidad = (apertura_fill['resultado']['base_ejecutada'] if apertura_fill is not None
                    else fila['tamano_posicion']/fila['entrada'])
        fill_validado = comprobar_fill(plan, evidencia_fill, lado='SELL',
                                      monto=cantidad, precio=precio,
                                      comision_pct=fila['comision_pct_apertura'])
        if apertura_fill is not None:
            from paper_fills import resultado_cierre
            calculo = {k: float(v) for k, v in resultado_cierre(apertura_fill, fill_validado).items()}
            if not all(math.isfinite(v) for v in calculo.values()):
                raise ValueError('Resultado financiero no finito.')
        else:
            calculo = calcular_resultado_cierre(fila['entrada'], fila['tamano_posicion'],
                                               precio, fila['comision_pct_apertura'])
        comisiones = calculo['comisiones_estimadas']
        pnl = calculo['resultado_usd']
        instante = ahora()
        saldo = con.execute('SELECT saldo_actual FROM paper_account WHERE id=1').fetchone()[0]
        asegurar_dia(con, instante, saldo)
        fecha = instante.isoformat()
        con.execute('UPDATE paper_trades SET estado=?,precio_salida=?,fecha_cierre=?,resultado_usd=?,resultado_pct=? WHERE id=?',
            (motivo, precio, fecha, pnl, calculo['resultado_pct'], identidad))
        con.execute('UPDATE paper_account SET saldo_actual=saldo_actual+?,pnl_acumulado=pnl_acumulado+?,fecha_actualizacion=? WHERE id=1',
                    (pnl, pnl, fecha))
        cuenta_actual = con.execute('SELECT saldo_actual,pnl_acumulado FROM paper_account WHERE id=1').fetchone()
        datos_cierre = {'id': identidad, 'pnl': pnl, 'comisiones_estimadas': comisiones}
        if fill_validado is not None:
            datos_cierre['evidencia_fill'] = fill_validado
        evento(con, 'CIERRE', datos_cierre)
        if fill_validado is not None:
            from paper_fills import validar_snapshot, MAX_EDAD_MS
            validar_snapshot(fill_validado['snapshot'], ahora_ms=int(ahora().timestamp()*1000), max_edad_ms=MAX_EDAD_MS)
        return {'cerrada': True, 'resultado_usd': pnl, 'resultado_pct': calculo['resultado_pct'], **dict(cuenta_actual)}


def movimiento(monto, nota):
    validar_paper()
    if not isinstance(monto, (int, float)) or isinstance(monto, bool) or not math.isfinite(monto) or monto == 0:
        raise ValueError('Aporte/retiro inválido.')
    inicializar()
    with conectar() as con:
        con.execute('BEGIN IMMEDIATE')
        saldo = con.execute('SELECT saldo_actual FROM paper_account WHERE id=1').fetchone()[0]
        if saldo+monto < resumen(con)['capital']:
            raise ValueError('Retiro excede capital libre.')
        fecha = ahora().isoformat()
        con.execute('INSERT INTO paper_flows(fecha,monto,nota) VALUES (?,?,?)', (fecha,monto,nota))
        con.execute('UPDATE paper_account SET saldo_actual=saldo_actual+?,fecha_actualizacion=? WHERE id=1', (monto,fecha))
        evento(con, 'MOVIMIENTO_CAPITAL', {'monto': monto, 'nota': nota})
