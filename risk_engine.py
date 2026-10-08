import math

from config import (
    MODO,
    CAPITAL_USD,
    RIESGO_POR_OPERACION_PCT,
    RIESGO_MAXIMO_DIARIO_PCT,
)

from paper_account import obtener_cuenta


def obtener_capital_operativo():
    if MODO == "PAPER":
        cuenta = obtener_cuenta()

        return cuenta["saldo_actual"]

    return CAPITAL_USD


def calcular_riesgo_base(
    capital=None,
):
    if capital is None:
        capital = obtener_capital_operativo()
    if (isinstance(capital, bool) or not isinstance(capital, (int, float))
            or not math.isfinite(capital) or capital <= 0):
        raise ValueError('El capital operativo debe ser finito y mayor que 0.')

    riesgo_operacion_usd = (
        capital
        * RIESGO_POR_OPERACION_PCT
        / 100
    )

    riesgo_diario_usd = (
        capital
        * RIESGO_MAXIMO_DIARIO_PCT
        / 100
    )

    return {
        "capital_usd": capital,
        "riesgo_operacion_pct": (
            RIESGO_POR_OPERACION_PCT
        ),
        "riesgo_operacion_usd": (
            riesgo_operacion_usd
        ),
        "riesgo_diario_pct": (
            RIESGO_MAXIMO_DIARIO_PCT
        ),
        "riesgo_diario_usd": (
            riesgo_diario_usd
        ),
    }


def calcular_tamano_posicion(
    distancia_stop_pct,
    capital=None,
    *, comision_entrada_pct=0,
):
    if (isinstance(distancia_stop_pct, bool) or not isinstance(distancia_stop_pct, (int, float))
            or not math.isfinite(distancia_stop_pct) or distancia_stop_pct <= 0):
        raise ValueError(
            "El stop debe ser mayor que 0%."
        )
    if (isinstance(comision_entrada_pct, bool) or not isinstance(comision_entrada_pct, (int, float))
            or not math.isfinite(comision_entrada_pct) or not 0 <= comision_entrada_pct < 100):
        raise ValueError('Comisión de entrada inválida.')

    riesgo = calcular_riesgo_base(
        capital
    )

    capital = riesgo["capital_usd"]

    if capital <= 0:
        raise ValueError(
            "El capital operativo debe "
            "ser mayor que 0."
        )

    riesgo_usd = (
        riesgo["riesgo_operacion_usd"]
    )

    tamano_teorico = (
        riesgo_usd
        / (distancia_stop_pct / 100)
    )

    # Spot sin apalancamiento:
    # nunca usar más dinero
    # que el saldo disponible.
    tamano_posicion = min(
        tamano_teorico,
        capital / (1 + comision_entrada_pct / 100),
    )

    porcentaje_capital = (
        tamano_posicion
        / capital
        * 100
    )

    return {
        "capital_usd": capital,
        "stop_pct": distancia_stop_pct,
        "riesgo_usd": riesgo_usd,
        "tamano_teorico": tamano_teorico,
        "tamano_posicion": tamano_posicion,
        "porcentaje_capital": (
            porcentaje_capital
        ),
    }


if __name__ == "__main__":
    riesgo = calcular_riesgo_base()

    print(
        "\nMOTOR DE RIESGO\n"
    )

    print(
        f"Modo: {MODO}"
    )

    print(
        f"Capital operativo: "
        f"${riesgo['capital_usd']:.2f}"
    )

    print(
        f"Riesgo por operación: "
        f"{riesgo['riesgo_operacion_pct']:.2f}%"
    )

    print(
        f"Máxima pérdida por operación: "
        f"${riesgo['riesgo_operacion_usd']:.2f}"
    )

    print(
        f"Riesgo máximo diario: "
        f"{riesgo['riesgo_diario_pct']:.2f}%"
    )

    print(
        f"Máxima pérdida diaria: "
        f"${riesgo['riesgo_diario_usd']:.2f}"
    )

    ejemplo_stop = 2.0

    posicion = calcular_tamano_posicion(
        ejemplo_stop
    )

    print(
        "\nEJEMPLO DE POSICIÓN"
    )

    print(
        f"Stop: "
        f"{posicion['stop_pct']:.2f}%"
    )

    print(
        f"Tamaño de posición: "
        f"${posicion['tamano_posicion']:.2f}"
    )

    print(
        f"Capital utilizado: "
        f"{posicion['porcentaje_capital']:.2f}%"
    )

    print(
        f"Riesgo máximo: "
        f"${posicion['riesgo_usd']:.2f}"
    )
