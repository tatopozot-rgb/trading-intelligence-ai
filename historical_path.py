"""Trayectoria LONG hipotética aislada; no cartera, órdenes ni monitor real."""
from historical_economics import diagnosticar_vela, resultado_hipotetico, escenarios_ambiguedad
from paper_store import numero

MODELO = 'BARRERA_TOQUE_APERTURA_SALTO_SIN_DESLIZAMIENTO_V1'
PASO_MS = 900_000


def evaluar_trayectoria(velas, *, inicio_ms, fin_exclusivo_ms, entrada,
                       tamano_posicion, stop, objetivo, comision_pct, modelo):
    """Posición hipotéticamente abierta al inicio de la primera vela15m.

    El llamante aporta precio/tamaño de entrada: no deduce un fill de una señal.
    Modelo obligatorio y explícito: toque -> barrera, salto -> apertura OHLC.
    Son precios hipotéticos sin deslizamiento ni promesa de ejecución. Si una
    vela toca ambos niveles, conserva ambos resultados y termina sin elegir.
    Si acaba el rango sin toque, NO liquida ni inventa una ganancia realizada.
    """
    if modelo != MODELO:
        raise ValueError('Modelo hipotético explícito no admitido.')
    if (any(type(t) is not int or not 0 < t <= 2**53 or t % PASO_MS
            for t in (inicio_ms, fin_exclusivo_ms))
            or not 0 < fin_exclusivo_ms-inicio_ms <= 366*86_400_000):
        raise ValueError('Rango15m explícito inválido o superior a366d.')
    entrada, stop, objetivo = (numero(v) for v in (entrada, stop, objetivo))
    if not stop < entrada < objetivo:
        raise ValueError('Entrada LONG debe estar entre stop y objetivo.')
    # Valida tamaño, comisión y aritmética incluso cuando no habrá salida.
    for precio in (stop, objetivo):
        resultado_hipotetico(entrada=entrada, tamano_posicion=tamano_posicion,
                            salida_aportada=precio, comision_pct=comision_pct)
    cantidad = (fin_exclusivo_ms-inicio_ms)//PASO_MS
    if not isinstance(velas, list) or len(velas) != cantidad:
        raise ValueError('Se requiere cobertura exacta sin huecos.')
    diagnósticos = []
    for i, vela in enumerate(velas):
        apertura_ms = inicio_ms + i*PASO_MS
        if (not isinstance(vela, dict)
                or type(vela.get('tiempo_apertura')) is not int
                or type(vela.get('tiempo_cierre')) is not int
                or vela['tiempo_apertura'] != apertura_ms
                or vela['tiempo_cierre'] != apertura_ms+PASO_MS-1):
            raise ValueError('Orden, cobertura o timestamps de vela inválidos.')
        try:
            d = diagnosticar_vela(**{k:vela[k] for k in ('apertura','maximo','minimo','cierre')},
                                 stop=stop, objetivo=objetivo)
        except KeyError as exc:
            raise ValueError('Faltan datos OHLC.') from exc
        diagnósticos.append(d)
    base = dict(tipo='TRAYECTORIA_HIPOTETICA_NO_EJECUTABLE', modelo=modelo,
                ejecutable=False, fill_confirmado=False, seleccionado=None,
                inicio_ms=inicio_ms, fin_exclusivo_ms=fin_exclusivo_ms,
                entrada_aportada=entrada, tamano_posicion_aportado=numero(tamano_posicion),
                comision_pct_aportada=comision_pct, escenarios={}, evento=None,
                estado='SIN_SALIDA_EN_RANGO',
                limites=['Posición supuesta abierta al inicio; no deduce fill de la señal.',
                         'Sin deslizamiento, liquidez, latencia ni monitor60s.',
                         'No es cartera ni verifica riesgo diario/capital disponible.',
                         'No asigna probabilidades, no promedia ni fuerza cierre al final.'])
    for vela, d in zip(velas, diagnósticos):
        estado = d['estado']
        if estado == 'NINGUN_NIVEL':
            continue
        base['evento'] = dict(primera_apertura_ms=vela['tiempo_apertura'],
                              cierre_ms=vela['tiempo_cierre'], diagnostico=d,
                              instante_fill=None)
        if estado == 'AMBIGUO_AMBOS_NIVELES':
            r = escenarios_ambiguedad(entrada=entrada, tamano_posicion=tamano_posicion,
                                     comision_pct=comision_pct, stop=stop, objetivo=objetivo,
                                     **{k:vela[k] for k in ('apertura','maximo','minimo','cierre')})
            base.update(estado='DOS_SALIDAS_HIPOTETICAS', escenarios=r['escenarios'])
        else:
            precio = (vela['apertura'] if estado.startswith('APERTURA_') else
                      stop if estado == 'SOLO_STOP_OBSERVADO' else objetivo)
            r = resultado_hipotetico(entrada=entrada, tamano_posicion=tamano_posicion,
                                    salida_aportada=precio, comision_pct=comision_pct)
            base.update(estado='SALIDA_HIPOTETICA', escenarios={estado:r})
        return base
    return base
