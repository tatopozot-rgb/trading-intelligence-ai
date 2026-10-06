"""Conciliación PAPER de solo lectura. No inicializa, migra ni repara datos."""
import argparse
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from datetime import datetime

import config


def informe(ruta=None):
    ruta = Path(ruta or config.BASE_DATOS).resolve()
    problemas = []

    def fallo(codigo, entidad):
        problemas.append({'codigo':codigo,'entidad':str(entidad)})

    def numero(valor, entidad):
        if isinstance(valor,bool) or not isinstance(valor,(float,int)) or not math.isfinite(valor):
            fallo('NUMERO_INVALIDO',entidad)
            return None
        return valor

    def iguales(a,b,codigo,entidad):
        if a is None or b is None or not math.isclose(a,b,rel_tol=0,abs_tol=1e-8):
            fallo(codigo,entidad)

    def suma(valores):
        if any(v is None for v in valores):
            return None
        try:
            total = math.fsum(valores)
        except OverflowError:
            fallo('TOTAL_NO_FINITO','conciliacion')
            return None
        if not math.isfinite(total):
            fallo('TOTAL_NO_FINITO','conciliacion')
            return None
        return total

    def objeto(texto,entidad):
        try:
            dato = json.loads(texto)
            if not isinstance(dato,dict):
                raise ValueError('No objeto')
            return dato
        except (ValueError,TypeError):
            fallo('JSON_INVALIDO',entidad)
            return {}

    # mode=ro evita crear una base vacía si la ruta es incorrecta.
    with closing(sqlite3.connect(ruta.as_uri()+'?mode=ro',uri=True,timeout=10)) as con:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        integridad = [r[0] for r in con.execute('PRAGMA integrity_check')]
        if integridad != ['ok']:
            fallo('INTEGRIDAD_SQLITE','base')
        cuentas = con.execute('SELECT * FROM paper_account ORDER BY id').fetchall()
        # Estado del halt persistente (solo lectura). Fila ausente = fail-closed, se reporta.
        tabla_halt = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_halt'").fetchone()
        filas_halt = con.execute('SELECT * FROM paper_halt WHERE id=1').fetchall() if tabla_halt else []
        trades = con.execute('SELECT * FROM paper_trades ORDER BY id').fetchall()
        flujos = con.execute('SELECT * FROM paper_flows ORDER BY id').fetchall()
        solicitudes = con.execute('SELECT * FROM paper_requests ORDER BY id').fetchall()
        eventos = con.execute('SELECT * FROM paper_events ORDER BY id').fetchall()

    eventos_apertura, eventos_cierre = {}, {}
    for e in eventos:
        d = objeto(e['datos'],f'evento:{e["id"]}')
        if e['tipo'] in ('APERTURA','CIERRE'):
            clave = d.get('trade_id' if e['tipo']=='APERTURA' else 'id')
            if type(clave) is not int:
                fallo('EVENTO_SIN_TRADE',e['id'])
                continue
            destino = eventos_apertura if e['tipo']=='APERTURA' else eventos_cierre
            destino.setdefault(clave,[]).append(d)

    por_trade = {}
    ids_trades = {t['id'] for t in trades}
    for r in solicitudes:
        plan = objeto(r['plan'],f'solicitud:{r["id"]}')
        try:
            digest = hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False,
                allow_nan=False,separators=(',',':')).encode()).hexdigest()
        except (TypeError,ValueError):
            digest = None
        if digest != r['plan_hash']:
            fallo('PLAN_HASH_NO_COINCIDE',r['id'])
        if r['estado'] not in ('PENDIENTE','CADUCADA','RECHAZADA','EJECUTADA'):
            fallo('ESTADO_SOLICITUD_INVALIDO',r['id'])
        if r['estado'] == 'EJECUTADA':
            por_trade.setdefault(r['trade_id'],[]).append(r)
            if r['trade_id'] not in ids_trades:
                fallo('SOLICITUD_SIN_TRADE',r['id'])
            d = objeto(r['respuesta'],f'respuesta:{r["id"]}')
            origen = plan.get('origen_revision', 'CLAUDE')
            decision_esperada = {'CLAUDE':'APROBAR_PAPER', 'REGLAS_PAPER_V1':'EJECUTAR_REGLAS_PAPER'}.get(origen)
            if (d.get('request_id') != r['id'] or d.get('plan_hash') != r['plan_hash']
                    or d.get('simbolo') != plan.get('simbolo') or decision_esperada is None
                    or d.get('decision') != decision_esperada
                    or d.get('origen_revision', 'CLAUDE') != origen
                    or r['ejecutable'] != 1):
                fallo('RESPUESTA_EJECUTADA_INCOHERENTE',r['id'])
        elif r['trade_id'] is not None:
            fallo('TRADE_EN_SOLICITUD_NO_EJECUTADA',r['id'])

    pnl_cierres, capital_abierto, comisiones_entrada = [], [], []
    simbolos = set()
    for t in trades:
        identidad = t['id']
        modelo, apertura_fill, cierre_fill, calculo_depth = None, None, None, None
        entrada = numero(t['entrada'],f'entrada:{identidad}')
        tamano = numero(t['tamano_posicion'],f'tamano:{identidad}')
        if (entrada is not None and entrada <= 0) or (tamano is not None and tamano <= 0):
            fallo('TRADE_VALORES_NO_POSITIVOS',identidad)
        apertura = eventos_apertura.get(identidad,[])
        cierres = eventos_cierre.get(identidad,[])
        solicitudes_trade = por_trade.get(identidad,[])
        if len(apertura) != 1:
            fallo('APERTURA_EVENTO_FALTANTE_O_DUPLICADO',identidad)
        if len(solicitudes_trade) != 1:
            fallo('TRADE_SOLICITUD_FALTANTE_O_DUPLICADA',identidad)
        elif len(apertura) == 1:
            if apertura[0].get('request_id') != solicitudes_trade[0]['id']:
                fallo('APERTURA_SOLICITUD_NO_COINCIDE',identidad)
            plan = objeto(solicitudes_trade[0]['plan'],f'plan_trade:{identidad}')
            origen = plan.get('origen_revision', 'CLAUDE')
            if (apertura[0].get('origen_revision', 'CLAUDE') != origen
                    or (origen == 'REGLAS_PAPER_V1' and apertura[0].get('autorizacion') != 'SESION_REGLAS_PAPER')):
                fallo('APERTURA_ORIGEN_NO_COINCIDE', identidad)
            if plan.get('simbolo') != t['simbolo']:
                fallo('TRADE_SIMBOLO_NO_COINCIDE',identidad)
            for campo in ('stop_precio','objetivo_precio','tamano_posicion'):
                iguales(numero(plan.get(campo),f'plan:{identidad}:{campo}'),
                    numero(t[campo],f'trade:{identidad}:{campo}'),'TRADE_PLAN_NO_COINCIDE',identidad)
        tarifa = t['comision_pct_apertura'] if 'comision_pct_apertura' in t.keys() else None
        tarifa = numero(tarifa,f'comision:{identidad}')
        if tarifa is not None and not 0 <= tarifa < 100:
            fallo('COMISION_INVALIDA',identidad)
        if len(solicitudes_trade) == 1:
            plan = objeto(solicitudes_trade[0]['plan'],f'plan_comision:{identidad}')
            iguales(numero(plan.get('comision_paper_pct'),f'plan_comision:{identidad}'),
                    tarifa,'COMISION_PLAN_NO_COINCIDE',identidad)
            modelo = plan.get('modelo_fill_paper')
            eventos_fill = [(apertura, 'BUY', entrada, t['fecha_apertura'])]
            if t['estado'] != 'ABIERTA':
                eventos_fill.append((cierres, 'SELL', t['precio_salida'], t['fecha_cierre']))
            for registros, lado, precio, fecha in eventos_fill:
                if modelo is None:
                    if any('evidencia_fill' in e for e in registros):
                        fallo('FILL_SIN_MODELO_EN_PLAN', identidad)
                    continue
                try:
                    from paper_fills import MODELO, validar_evidencia
                    if modelo != MODELO or len(registros) != 1:
                        raise ValueError('Modelo/evento no verificable.')
                    instante = datetime.fromisoformat(fecha)
                    if instante.tzinfo is None:
                        raise ValueError('Fecha de fill sin zona horaria.')
                    monto = (tamano if lado == 'BUY' else
                             apertura_fill['resultado']['base_ejecutada'] if apertura_fill else None)
                    verificada = validar_evidencia(registros[0].get('evidencia_fill'), simbolo=t['simbolo'],
                                                  lado=lado, monto=monto, comision_pct=tarifa, precio=precio,
                                                  ahora_ms=int(instante.timestamp()*1000))
                    if lado == 'BUY':
                        apertura_fill = verificada
                    else:
                        cierre_fill = verificada
                except (ValueError, TypeError, KeyError, OverflowError):
                    fallo('EVIDENCIA_FILL_INVALIDA_'+lado, identidad)
            if apertura_fill is not None and cierre_fill is not None:
                from paper_fills import resultado_cierre
                calculo_depth = resultado_cierre(apertura_fill, cierre_fill)
        stop = numero(t['stop_precio'],f'stop:{identidad}')
        objetivo = numero(t['objetivo_precio'],f'objetivo:{identidad}')
        riesgo = numero(t['riesgo_usd'],f'riesgo:{identidad}')
        if all(v is not None for v in (entrada,stop,objetivo)) and not 0 < stop < entrada < objetivo:
            fallo('NIVELES_TRADE_INVALIDOS',identidad)
        if all(v is not None for v in (entrada,stop,tamano,tarifa)) and entrada > 0:
            riesgo_calculado = tamano*((entrada-stop)/entrada+2*tarifa/100)
            iguales(riesgo,riesgo_calculado,'RIESGO_TRADE_NO_COINCIDE',identidad)
        if t['estado'] == 'ABIERTA':
            capital_abierto.append(tamano)
            comisiones_entrada.append(tamano*tarifa/100 if tamano is not None and tarifa is not None else None)
            if t['simbolo'] in simbolos:
                fallo('SIMBOLO_ABIERTO_DUPLICADO',t['simbolo'])
            simbolos.add(t['simbolo'])
            if cierres or any(t[c] is not None for c in ('precio_salida','fecha_cierre','resultado_usd','resultado_pct')):
                fallo('ABIERTA_CON_DATOS_CIERRE',identidad)
        elif t['estado'] in ('CERRADA_STOP','CERRADA_OBJETIVO','CERRADA_MANUAL'):
            pnl = numero(t['resultado_usd'],f'pnl:{identidad}')
            pnl_cierres.append(pnl)
            salida = numero(t['precio_salida'],f'salida:{identidad}')
            if not t['fecha_cierre']:
                fallo('CIERRE_SIN_FECHA',identidad)
            if len(cierres) != 1:
                fallo('CIERRE_EVENTO_FALTANTE_O_DUPLICADO',identidad)
            else:
                iguales(numero(cierres[0].get('pnl'),f'evento_pnl:{identidad}'),pnl,'CIERRE_PNL_NO_COINCIDE',identidad)
            if calculo_depth is not None:
                iguales(pnl,float(calculo_depth['resultado_usd']),'PNL_CALCULADO_NO_COINCIDE',identidad)
                iguales(numero(t['resultado_pct'],f'pnl_pct:{identidad}'),
                        float(calculo_depth['resultado_pct']),'PNL_PCT_NO_COINCIDE',identidad)
                iguales(numero(cierres[0].get('comisiones_estimadas'),f'evento_comision:{identidad}'),
                        float(calculo_depth['comisiones_estimadas']),'CIERRE_COMISION_NO_COINCIDE',identidad)
            elif modelo is None and all(v is not None for v in (entrada,tamano,tarifa,salida)) and entrada > 0 and tamano > 0:
                retorno = salida/entrada-1
                calculado = tamano*retorno-tamano*(2+retorno)*tarifa/100
                iguales(pnl,calculado,'PNL_CALCULADO_NO_COINCIDE',identidad)
                iguales(numero(t['resultado_pct'],f'pnl_pct:{identidad}'),
                        calculado/tamano*100,'PNL_PCT_NO_COINCIDE',identidad)
        else:
            fallo('ESTADO_TRADE_INVALIDO',identidad)

    for identidad in set(eventos_apertura)|set(eventos_cierre):
        if identidad not in ids_trades:
            fallo('EVENTO_TRADE_INEXISTENTE',identidad)
    total_pnl = suma(pnl_cierres)
    total_flujos = suma([numero(f['monto'],f'flujo:{f["id"]}') for f in flujos])
    total_capital = suma(capital_abierto)
    total_comisiones_entrada = suma(comisiones_entrada)
    total_comprometido = suma([total_capital, total_comisiones_entrada])
    saldo_esperado = saldo = None
    if len(cuentas) != 1 or cuentas[0]['id'] != 1:
        fallo('CUENTA_UNICA_INVALIDA','cuenta')
    else:
        c = cuentas[0]
        inicial = numero(c['capital_inicial'],'capital_inicial')
        saldo = numero(c['saldo_actual'],'saldo_actual')
        saldo_esperado = suma([inicial,total_flujos,total_pnl])
        iguales(saldo,saldo_esperado,'SALDO_NO_CONCILIA','cuenta')
        iguales(numero(c['pnl_acumulado'],'pnl_acumulado'),total_pnl,'PNL_NO_CONCILIA','cuenta')
        if saldo is not None and total_comprometido is not None and total_comprometido > saldo+1e-8:
            fallo('CAPITAL_ABIERTO_SUPERA_SALDO','cuenta')
    halt = None
    if len(filas_halt) == 1 and filas_halt[0]['activo'] in (0, 1):
        h = filas_halt[0]
        halt = {'activo': bool(h['activo']), 'razon': h['razon'], 'pico_equity': h['pico_equity'],
                'equity_activacion': h['equity_activacion']}
    else:
        fallo('HALT_AUSENTE_O_CORRUPTO', 'paper_halt')
    return {'estado':'DISCREPANCIA' if problemas else 'OK','solo_lectura':True,
        'halt': halt,
        'cuenta':{'saldo_actual':saldo,'saldo_esperado':saldo_esperado,'pnl_cerrado':total_pnl,
                  'flujos_netos':total_flujos,'capital_abierto':total_capital,
                  'comisiones_entrada_reservadas':total_comisiones_entrada,
                  'capital_comprometido':total_comprometido},
        'conteos':{'trades':len(trades),'solicitudes':len(solicitudes),'eventos':len(eventos)},
        'problemas':problemas}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=config.BASE_DATOS)
    args = parser.parse_args()
    try:
        resultado = informe(args.base)
    except (sqlite3.Error,OSError) as exc:
        print(json.dumps({'estado':'NO_VERIFICADO','error':type(exc).__name__},ensure_ascii=False))
        return 2
    print(json.dumps(resultado,ensure_ascii=False,indent=2,allow_nan=False))
    return 0 if resultado['estado']=='OK' else 1


if __name__ == '__main__':
    raise SystemExit(main())
