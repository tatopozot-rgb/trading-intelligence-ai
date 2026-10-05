"""Un filtro porcentual sobre evidencia TESTNET_FIXTURE. Sin red ni autorización."""
from decimal import (Context, DivisionByZero, InvalidOperation, Overflow,
                     ROUND_HALF_EVEN, localcontext, Inexact, Rounded)

from execution_context import ContextoInvalido, hash_contenido, _campos, _hash, _tiempo
from execution_filters import FiltroInvalido, decimal_texto, validar_parametros_limite
from execution_ledger import ENTORNO, texto


def _frescura(evento, ahora, edad_max):
    observado, recibido = (_tiempo(evento[k]) for k in ('observado_ms','recibido_ms'))
    if not observado <= recibido <= ahora or ahora - observado > edad_max:
        raise ContextoInvalido('Evidencia futura, incoherente o caducada.')


def validar_porcentaje_offline(orden, filtro, evidencia, *, simbolo_filtro,
                               filtro_hash_esperado, evidencia_hash_esperado, ahora_ms, max_edad_ms):
    """Evalúa UN filtro, no todos los requisitos ni PRICE_RANGE de ejecución.

    Referencia PRESENTE tiene prioridad; AUSENTE exige evidencia explícita vigente.
    Ninguna etiqueta prueba origen. Reloj/umbral/hash deben ser aportados por llamador confiable.
    """
    precio, _ = validar_parametros_limite(orden)
    texto(simbolo_filtro, 'simbolo_filtro')
    if orden['symbol'] != simbolo_filtro:
        raise ContextoInvalido('Símbolo de filtro discordante.')
    if type(filtro) is not dict:
        raise ContextoInvalido('Filtro requerido.')
    tipo = filtro.get('filterType')
    if tipo == 'PERCENT_PRICE':
        multiplicadores = ('multiplierDown','multiplierUp')
        bajo, alto = multiplicadores
    elif tipo == 'PERCENT_PRICE_BY_SIDE':
        multiplicadores = ('bidMultiplierDown','bidMultiplierUp','askMultiplierDown','askMultiplierUp')
        bajo, alto = multiplicadores[:2] if orden['side']=='BUY' else multiplicadores[2:]
    else:
        raise ContextoInvalido('Filtro porcentual no soportado.')
    _campos(filtro, ('filterType','avgPriceMins',*multiplicadores))
    filtro_hash = hash_contenido(filtro)
    if filtro_hash != _hash(filtro_hash_esperado):
        raise ContextoInvalido('Filtro distinto de la referencia fijada.')
    minutos = _tiempo(filtro['avgPriceMins'])
    valores = {k:decimal_texto(filtro[k]) for k in multiplicadores}
    if any(v<=0 for v in valores.values()) or any(valores[multiplicadores[i]]>valores[multiplicadores[i+1]] for i in range(0,len(multiplicadores),2)):
        raise ContextoInvalido('Multiplicadores no positivos o invertidos.')

    ahora, edad_max = _tiempo(ahora_ms), _tiempo(max_edad_ms)
    if type(evidencia) is not dict:
        raise ContextoInvalido('Falta evidencia de referencia.')
    huella = hash_contenido(evidencia)
    if huella != _hash(evidencia_hash_esperado):
        raise ContextoInvalido('Evidencia modificada.')
    if (evidencia.get('schema') != 'PRECIO_PORCENTUAL_FIXTURE_V1' or evidencia.get('entorno') != ENTORNO or
            evidencia.get('simbolo') != simbolo_filtro):
        raise ContextoInvalido('Versión, entorno o símbolo de evidencia incompatible.')
    ref = evidencia.get('referencia')
    if type(ref) is not dict:
        raise ContextoInvalido('Estado de referencia desconocido; no usar sustituto.')
    estado = ref.get('estado')
    if estado == 'PRESENTE':
        _campos(evidencia, ('schema','entorno','simbolo','referencia'))
        _campos(ref, ('estado','precio','observado_ms','recibido_ms'))
        _frescura(ref, ahora, edad_max)
        base = decimal_texto(ref['precio'])
        fuente = 'REFERENCE_PRICE'
    elif estado == 'AUSENTE':
        _campos(evidencia, ('schema','entorno','simbolo','referencia','sustituto'))
        _campos(ref, ('estado','observado_ms','recibido_ms'))
        _frescura(ref, ahora, edad_max)
        sustituto = evidencia['sustituto']
        _campos(sustituto, ('tipo','precio','avg_price_mins','observado_ms','recibido_ms'))
        _frescura(sustituto, ahora, edad_max)
        # Precondición conservadora de fixture conjunto; igualdad NO prueba atomicidad de red.
        if sustituto['observado_ms'] != ref['observado_ms']:
            raise ContextoInvalido('Ausencia y sustituto pertenecen a observaciones distintas.')
        if _tiempo(sustituto['avg_price_mins']) != minutos:
            raise ContextoInvalido('Ventana de promedio distinta del filtro.')
        fuente = 'ULTIMO_TRADE' if minutos == 0 else 'VWAP'
        if sustituto['tipo'] != fuente:
            raise ContextoInvalido('Fuente sustituta incompatible; ticker/vela no equivalen.')
        base = decimal_texto(sustituto['precio'])
    else:
        raise ContextoInvalido('Estado de referencia no verificado.')
    if base <= 0:
        raise ContextoInvalido('Precio de referencia no positivo.')
    with localcontext(Context(prec=200, rounding=ROUND_HALF_EVEN, Emin=-999999,
                              Emax=999999, capitals=1, clamp=0, flags=[],
                              traps=[InvalidOperation, DivisionByZero, Overflow, Inexact, Rounded])):
        minimo, maximo = base*valores[bajo], base*valores[alto]
        if not minimo <= precio <= maximo:
            raise FiltroInvalido('Precio fuera del filtro porcentual.')
    return {'modo':'OFFLINE','ambito':'FILTRO_PORCENTUAL_UNICO','estado':'FILTRO_COINCIDE',
            'enviable':False,'autorizado':False,'filterType':tipo,'fuente':fuente,
            'minimo':format(minimo,'f'),'maximo':format(maximo,'f'),
            'evidencia_hash':huella,'filtro_hash':filtro_hash,
            'precio_referencia':format(base,'f')}
