import sqlite3
from datetime import datetime, timezone

from market_http import precio_actual

from paper_trader import (
    BASE_DATOS,
    crear_tabla,
)

import logging
import json


PRECIO_URL = (
    "https://data-api.binance.vision"
    "/api/v3/ticker/price"
)


def obtener_precio_actual(simbolo):
    return precio_actual(simbolo)


def obtener_operaciones_abiertas():
    crear_tabla()

    conexion = sqlite3.connect(
        BASE_DATOS
    )

    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT
            id,
            simbolo,
            entrada,
            stop_precio,
            objetivo_precio,
            tamano_posicion
        FROM paper_trades
        WHERE estado = 'ABIERTA'
        ORDER BY id
        """
    )

    operaciones = cursor.fetchall()

    conexion.close()

    return operaciones


def cerrar_operacion(operacion_id, entrada, precio_salida, tamano_posicion, motivo_cierre):
    # Entrada y tamaño se leen de SQLite, nunca de parámetros externos.
    from paper_store import cerrar
    return cerrar(operacion_id, precio_salida, motivo_cierre)


def revisar_operaciones():
    resumen_revision = {'revisadas':0,'cerradas':0,'errores':0,'ultimo_error':None}
    operaciones = (
        obtener_operaciones_abiertas()
    )

    if not operaciones:
        print(
            "No hay operaciones PAPER "
            "abiertas."
        )
        return resumen_revision

    for operacion in operaciones:
        (
            operacion_id,
            simbolo,
            entrada,
            stop_precio,
            objetivo_precio,
            tamano_posicion,
        ) = operacion

        try:
            # Modelo persistido: reiniciar sin flag no puede degradar el fill.
            from paper_store import conectar, preparar_cierre, cerrar, ahora
            with conectar() as con:
                fila = con.execute('SELECT * FROM paper_trades WHERE id=?', (operacion_id,)).fetchone()
                plan_guardado, apertura_fill = preparar_cierre(con, fila)
            modelo = plan_guardado.get('modelo_fill_paper')
            if modelo is not None:
                from paper_fills import MODELO, cotizar, evidencia
                if modelo != MODELO:
                    raise ValueError('Modelo de fill desconocido; no usar ticker como sustituto.')
                snapshot = cotizar(simbolo)
                bid = float(snapshot['libro']['bids'][0][0])
                resumen_revision['revisadas'] += 1
                motivo = ('CERRADA_STOP' if bid <= stop_precio else
                          'CERRADA_OBJETIVO' if bid >= objetivo_precio else None)
                if motivo:
                    fill = evidencia(snapshot, lado='SELL', monto=apertura_fill['resultado']['base_ejecutada'],
                                     comision_pct=fila['comision_pct_apertura'], ahora_ms=int(ahora().timestamp()*1000))
                    if fill['resultado']['estado'] != 'COMPLETO':
                        raise ValueError('PROFUNDIDAD_VISIBLE_INSUFICIENTE: posición sigue abierta.')
                    resultado = cerrar(operacion_id, float(fill['resultado']['precio_medio']),
                                       motivo, evidencia_fill=fill)
                    resumen_revision['cerradas'] += int(resultado['cerrada'])
                continue
            precio_actual = (
                obtener_precio_actual(
                    simbolo
                )
            )
            resumen_revision['revisadas'] += 1

            print(
                "\n---------------------------"
            )

            print(
                f"ID: {operacion_id}"
            )

            print(
                f"Activo: {simbolo}"
            )

            print(
                f"Entrada: "
                f"${entrada:,.6f}"
            )

            print(
                f"Precio actual: "
                f"${precio_actual:,.6f}"
            )

            print(
                f"Stop: "
                f"${stop_precio:,.6f}"
            )

            print(
                f"Objetivo: "
                f"${objetivo_precio:,.6f}"
            )

            if precio_actual <= stop_precio:
                resultado = cerrar_operacion(
                    operacion_id,
                    entrada,
                    precio_actual,
                    tamano_posicion,
                    "CERRADA_STOP",
                )

                if resultado["cerrada"]:
                    resumen_revision['cerradas'] += 1
                    print(
                        "Resultado: STOP"
                    )

                    print(
                        f"P&L: "
                        f"${resultado['resultado_usd']:.2f}"
                    )

                    print(
                        f"P&L %: "
                        f"{resultado['resultado_pct']:.2f}%"
                    )

                    print(
                        f"Nuevo saldo PAPER: "
                        f"${resultado['saldo_actual']:.2f}"
                    )

            elif (
                precio_actual
                >= objetivo_precio
            ):
                resultado = cerrar_operacion(
                    operacion_id,
                    entrada,
                    precio_actual,
                    tamano_posicion,
                    "CERRADA_OBJETIVO",
                )

                if resultado["cerrada"]:
                    resumen_revision['cerradas'] += 1
                    print(
                        "Resultado: OBJETIVO"
                    )

                    print(
                        f"P&L: "
                        f"${resultado['resultado_usd']:.2f}"
                    )

                    print(
                        f"P&L %: "
                        f"{resultado['resultado_pct']:.2f}%"
                    )

                    print(
                        f"Nuevo saldo PAPER: "
                        f"${resultado['saldo_actual']:.2f}"
                    )

            else:
                variacion_pct = (
                    (
                        precio_actual
                        / entrada
                    )
                    - 1
                ) * 100

                pnl_temporal = (
                    tamano_posicion
                    * (
                        variacion_pct
                        / 100
                    )
                )

                print(
                    "Estado: ABIERTA"
                )

                print(
                    f"P&L temporal: "
                    f"${pnl_temporal:.2f}"
                )

                print(
                    f"Variación: "
                    f"{variacion_pct:+.2f}%"
                )

        except Exception as error:
            resumen_revision['errores'] += 1
            resumen_revision['ultimo_error'] = {'simbolo':simbolo,'tipo':type(error).__name__}
            logging.exception("Fallo monitor %s", simbolo)
            print(
                f"Error revisando "
                f"{simbolo}: {error}"
            )
    return resumen_revision


if __name__ == "__main__":
    print(
        "\nMONITOR PAPER\n"
    )

    revisar_operaciones()
