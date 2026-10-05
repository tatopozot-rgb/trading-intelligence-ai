import math
import logging
from market_http import get_publico, numero_finito, DatosInvalidos

from analysis_engine import analizar_simbolo
from trade_planner import crear_plan


TICKER_URL = (
    "https://data-api.binance.vision"
    "/api/v3/ticker/24hr"
)

EXCHANGE_INFO_URL = (
    "https://data-api.binance.vision"
    "/api/v3/exchangeInfo"
)

STABLES_Y_FIAT = {
    "USDC",
    "FDUSD",
    "TUSD",
    "USDP",
    "DAI",
    "USD1",
    "RLUSD",
    "EUR",
    "AEUR",
    "TRY",
    "BRL",
}

VOLUMEN_MINIMO_USDT = 20_000_000
MOVIMIENTO_MINIMO_PCT = 2.0

NUMERO_CANDIDATOS = 5


def obtener_simbolos_validos():
    mercados = get_publico('/api/v3/exchangeInfo')
    if not isinstance(mercados, dict) or not isinstance(mercados.get('symbols'), list):
        raise DatosInvalidos('exchangeInfo sin lista de símbolos.')

    simbolos = set()

    for mercado in mercados["symbols"]:
        if not isinstance(mercado, dict) or not isinstance(mercado.get('symbol'), str):
            raise DatosInvalidos('Registro de símbolo inválido.')
        if (
            mercado.get("quoteAsset") == "USDT"
            and mercado.get("status") == "TRADING"
            and mercado.get(
                "isSpotTradingAllowed",
                False,
            ) is True
        ):
            simbolos.add(
                mercado["symbol"]
            )

    return simbolos


def obtener_candidatos(limite=None):
    limite = NUMERO_CANDIDATOS if limite is None else limite
    if type(limite) is not int or limite <= 0:
        raise ValueError('Límite de candidatos debe ser entero positivo.')
    simbolos_validos = (
        obtener_simbolos_validos()
    )

    mercado = get_publico('/api/v3/ticker/24hr')
    if not isinstance(mercado, list):
        raise DatosInvalidos('Ticker global no es una lista.')

    candidatos = []

    for datos in mercado:
        if not isinstance(datos, dict) or not isinstance(datos.get('symbol'), str):
            raise DatosInvalidos('Registro ticker inválido.')
        simbolo = datos["symbol"]

        if simbolo not in simbolos_validos:
            continue

        base = simbolo[:-4]

        if base in STABLES_Y_FIAT:
            continue

        try:
            precio = numero_finito(datos["lastPrice"], positivo=True)
            cambio = numero_finito(datos["priceChangePercent"])
            volumen = numero_finito(datos["quoteVolume"], no_negativo=True)

        except (ValueError, TypeError, KeyError):
            logging.warning('Ticker descartado por datos inválidos: %s', simbolo)
            continue

        if precio <= 0:
            continue

        if volumen < VOLUMEN_MINIMO_USDT:
            continue

        if (
            abs(cambio)
            < MOVIMIENTO_MINIMO_PCT
        ):
            continue

        movimiento_score = min(
            abs(cambio),
            20,
        )

        score = (
            movimiento_score
            * math.log10(volumen)
        )

        candidatos.append({
            "simbolo": simbolo,
            "precio": precio,
            "cambio": cambio,
            "volumen": volumen,
            "score": score,
        })

    candidatos.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    return candidatos[
        :limite
    ]


def ejecutar_scanner():
    print(
        "\nTRADING SCANNER AUTOMÁTICO\n"
    )

    candidatos = obtener_candidatos()
    resultados = []

    for numero, candidato in enumerate(
        candidatos,
        start=1,
    ):
        simbolo = candidato["simbolo"]
        resultado = {
            "candidato": candidato,
        }

        print(
            "\n==========================="
        )

        print(
            f"CANDIDATO #{numero}: "
            f"{simbolo}"
        )

        print(
            f"Movimiento 24h: "
            f"{candidato['cambio']:+.2f}%"
        )

        print(
            f"Volumen: "
            f"${candidato['volumen']:,.0f}"
        )

        print(
            f"Score radar: "
            f"{candidato['score']:.2f}"
        )

        try:
            # El análisis se calcula una sola vez.
            analisis = analizar_simbolo(
                simbolo
            )
            resultado["analisis"] = analisis

            print(
                "Consenso:",
                analisis["consenso"]
            )

            print(
                "Estado:",
                analisis["estado"]
            )

            for temporalidad, datos in (
                analisis[
                    "temporalidades"
                ].items()
            ):
                print(
                    f"{temporalidad}: "
                    f"{datos['tendencia']} | "
                    f"RSI {datos['rsi']:.2f} | "
                    f"ATR {datos['atr_pct']:.2f}%"
                )

            # Reutilizamos el análisis anterior.
            plan = crear_plan(
                simbolo,
                analisis,
            )
            resultado["plan"] = plan

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
                    f"Entrada: "
                    f"${plan['entrada']:,.4f}"
                )

                print(
                    f"Stop: "
                    f"{plan['stop_pct']:.2f}%"
                )

                print(
                    f"Objetivo: "
                    f"{plan['objetivo_pct']:.2f}%"
                )

                print(
                    f"Posición: "
                    f"${plan['tamano_posicion']:.2f}"
                )

                print(
                    f"Riesgo máximo: "
                    f"${plan['riesgo_usd']:.2f}"
                )

                resultado["pendiente_claude"] = True
                print("Estado: CANDIDATO; pendiente de controles y autorización del modo de sesión")

        except Exception as error:
            resultado["error"] = str(error)

            print(
                "Error analizando:",
                error
            )

        resultados.append(resultado)

    return resultados


if __name__ == "__main__":
    ejecutar_scanner()
