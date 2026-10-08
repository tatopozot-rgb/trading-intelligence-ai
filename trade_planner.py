import math

from analysis_engine import analizar_simbolo

from risk_engine import (
    calcular_tamano_posicion,
    obtener_capital_operativo,
)

from config import (
    MODO,
    USAR_DINERO_REAL,
    COMISION_PAPER_PCT,
)


MULTIPLICADOR_ATR_STOP = 1.5
RATIO_BENEFICIO_RIESGO = 2.0


def motivo_espera(analisis, real_bloqueado):
    if real_bloqueado:
        return "Ejecución real bloqueada en esta fase."
    if analisis["consenso"] != "ALCISTA":
        return "No existe consenso alcista en 15m, 1h y 4h."
    if "SOBREEXTENDIDA" in analisis["estado"]:
        return "Tendencia alcista, pero el mercado está sobreextendido."
    if analisis["estado"] != "ALCISTA MOMENTUM SANO":
        return "No existe una condición técnica suficientemente clara."
    return ""


def crear_plan_con_datos(simbolo, analisis, *, capital, precio, comision_pct,
                         modo, real_bloqueado):
    """Constructor sin red/BD: precios y capital explícitos, mismas reglas."""
    from paper_store import numero, validar_comision
    capital, precio = numero(capital), numero(precio)
    comision = validar_comision(comision_pct)
    plan = dict(simbolo=simbolo, modo=modo, capital=capital,
                consenso=analisis["consenso"], estado=analisis["estado"],
                decision="ESPERAR", motivo=motivo_espera(analisis, real_bloqueado))
    if plan["motivo"]:
        return plan
    atr_pct = analisis["temporalidades"]["1h"]["atr_pct"]
    if (isinstance(atr_pct, bool) or not isinstance(atr_pct, (int, float))
            or not math.isfinite(atr_pct) or atr_pct < 0):
        raise ValueError('ATR porcentual inválido.')
    stop_pct = max(atr_pct * MULTIPLICADOR_ATR_STOP, 1.0)
    objetivo_pct = stop_pct * RATIO_BENEFICIO_RIESGO
    stop_precio = numero(precio * (1 - stop_pct / 100))
    objetivo_precio = numero(precio * (1 + objetivo_pct / 100))
    posicion = calcular_tamano_posicion(stop_pct + 2 * comision, capital,
                                        comision_entrada_pct=comision)
    tamano = numero(posicion["tamano_posicion"])
    riesgo = numero(tamano * (stop_pct + 2 * comision) / 100)
    plan.update(comision_paper_pct=comision, decision="PAPER CANDIDATE",
                motivo="Consenso alcista con momentum sano.", entrada=precio,
                stop_pct=stop_pct, stop_precio=stop_precio,
                objetivo_pct=objetivo_pct, objetivo_precio=objetivo_precio,
                tamano_posicion=tamano, riesgo_usd=riesgo)
    return plan


def crear_plan(simbolo, analisis=None):
    if analisis is None:
        analisis = analizar_simbolo(simbolo)
    capital = obtener_capital_operativo()
    precio = analisis["temporalidades"]["1h"]["precio"]
    if not motivo_espera(analisis, USAR_DINERO_REAL):
        from paper_monitor import obtener_precio_actual
        precio = obtener_precio_actual(simbolo)
    return crear_plan_con_datos(
        simbolo, analisis, capital=capital, precio=precio,
        comision_pct=COMISION_PAPER_PCT, modo=MODO,
        real_bloqueado=USAR_DINERO_REAL)


if __name__ == "__main__":
    simbolo_prueba = "BTCUSDT"

    plan = crear_plan(
        simbolo_prueba
    )

    print(
        "\nTRADE PLANNER\n"
    )

    print(
        "Modo:",
        plan["modo"]
    )

    print(
        "Activo:",
        plan["simbolo"]
    )

    print(
        "Capital operativo:",
        f"${plan['capital']:.2f}"
    )

    print(
        "Consenso:",
        plan["consenso"]
    )

    print(
        "Estado:",
        plan["estado"]
    )

    print(
        "Decisión:",
        plan["decision"]
    )

    print(
        "Motivo:",
        plan["motivo"]
    )

    if (
        plan["decision"]
        == "PAPER CANDIDATE"
    ):
        print(
            f"Entrada estimada: "
            f"${plan['entrada']:,.4f}"
        )

        print(
            f"Stop: "
            f"{plan['stop_pct']:.2f}%"
        )

        print(
            f"Stop precio: "
            f"${plan['stop_precio']:,.4f}"
        )

        print(
            f"Objetivo: "
            f"{plan['objetivo_pct']:.2f}%"
        )

        print(
            f"Objetivo precio: "
            f"${plan['objetivo_precio']:,.4f}"
        )

        print(
            f"Tamaño posición: "
            f"${plan['tamano_posicion']:.2f}"
        )

        print(
            f"Riesgo máximo: "
            f"${plan['riesgo_usd']:.2f}"
        )
