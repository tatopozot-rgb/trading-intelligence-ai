from market_http import get_publico, DatosInvalidos
import pandas as pd
import math
import time


URL = "https://data-api.binance.vision/api/v3/klines"

TEMPORALIDADES = [
    "15m",
    "1h",
    "4h",
]

LIMITE = 200
INTERVALOS_MS = {'15m': 900_000, '1h': 3_600_000, '4h': 14_400_000}


def obtener_velas(simbolo, intervalo):
    if intervalo not in INTERVALOS_MS:
        raise DatosInvalidos('Intervalo no soportado.')
    datos = get_publico('/api/v3/klines', {
            "symbol": simbolo,
            "interval": intervalo,
            "limit": LIMITE,
        })
    if not isinstance(datos, list) or any(not isinstance(fila, list) or len(fila) != 12 for fila in datos):
        raise DatosInvalidos('Formato de velas inválido.')

    columnas = [
        "tiempo_apertura",
        "apertura",
        "maximo",
        "minimo",
        "cierre",
        "volumen",
        "tiempo_cierre",
        "volumen_quote",
        "operaciones",
        "volumen_compra_base",
        "volumen_compra_quote",
        "ignorar",
    ]

    df = pd.DataFrame(
        datos,
        columns=columnas,
    )

    df.attrs['intervalo'] = intervalo
    return df


def validar_velas(df, intervalo, ahora_ms):
    if intervalo not in INTERVALOS_MS:
        raise DatosInvalidos('Falta intervalo explícito de las velas.')
    if len(df) < 60:
        raise DatosInvalidos('Historial insuficiente para indicadores.')
    campos = ['apertura','maximo','minimo','cierre','volumen','tiempo_apertura','tiempo_cierre']
    if any(c not in df for c in campos):
        raise DatosInvalidos('Faltan campos de velas.')
    df = df.copy()
    for campo in campos:
        if any(isinstance(v, bool) for v in df[campo].tolist()):
            raise DatosInvalidos('Booleano en velas.')
        try:
            df[campo] = pd.to_numeric(df[campo], errors='raise')
        except (ValueError, TypeError) as exc:
            raise DatosInvalidos('Campo de vela no numérico.') from exc
        if not all(math.isfinite(float(v)) for v in df[campo]):
            raise DatosInvalidos('NaN/infinito en velas.')
    precios = df[['apertura','maximo','minimo','cierre']]
    if (precios <= 0).any().any() or (df['volumen'] < 0).any():
        raise DatosInvalidos('Precio/volumen de vela inválido.')
    if ((df['minimo'] > precios[['apertura','cierre']].min(axis=1)) |
        (df['maximo'] < precios[['apertura','cierre']].max(axis=1))).any():
        raise DatosInvalidos('OHLC incoherente.')
    paso = INTERVALOS_MS[intervalo]
    for campo in ('tiempo_apertura','tiempo_cierre'):
        if ((df[campo] <= 0) | (df[campo] % 1 != 0) | (df[campo] > 2**53)).any():
            raise DatosInvalidos('Timestamp inválido.')
    if (df['tiempo_apertura'] % paso != 0).any() or (df['tiempo_apertura'].diff().iloc[1:] != paso).any():
        raise DatosInvalidos('Velas discontinuas, duplicadas o fuera de intervalo.')
    if (df['tiempo_cierre'] != df['tiempo_apertura'] + paso - 1).any():
        raise DatosInvalidos('Cierre temporal de vela incoherente.')
    if (df['tiempo_apertura'] > ahora_ms).any():
        raise DatosInvalidos('Vela con apertura futura.')
    cerradas = df[df['tiempo_cierre'] < ahora_ms]
    if cerradas.empty:
        raise DatosInvalidos('Sin velas cerradas.')
    if ahora_ms - float(cerradas.iloc[-1]['tiempo_cierre']) > paso + 120_000:
        raise DatosInvalidos('Velas obsoletas.')
    return cerradas.copy()


def analizar_temporalidad(df, intervalo=None, ahora_ms=None):
    ahora_ms = time.time()*1000 if ahora_ms is None else ahora_ms
    intervalo = intervalo or df.attrs.get('intervalo')
    df = validar_velas(df, intervalo, ahora_ms)
    df["EMA20"] = df["cierre"].ewm(
        span=20,
        adjust=False,
    ).mean()

    df["EMA50"] = df["cierre"].ewm(
        span=50,
        adjust=False,
    ).mean()

    delta = df["cierre"].diff()

    ganancias = delta.clip(lower=0)
    perdidas = -delta.clip(upper=0)

    media_ganancias = ganancias.ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    media_perdidas = perdidas.ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    rs = media_ganancias / media_perdidas

    df["RSI14"] = 100 - (
        100 / (1 + rs)
    )

    cierre_anterior = df["cierre"].shift(1)

    rango_1 = (
        df["maximo"] - df["minimo"]
    )

    rango_2 = abs(
        df["maximo"] - cierre_anterior
    )

    rango_3 = abs(
        df["minimo"] - cierre_anterior
    )

    rango_real = pd.concat(
        [
            rango_1,
            rango_2,
            rango_3,
        ],
        axis=1,
    ).max(axis=1)

    df["ATR14"] = rango_real.ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    # Usamos la última vela cerrada.
    ultima = df.iloc[-1]
    if not all(math.isfinite(float(ultima[k])) for k in ('cierre','EMA20','EMA50','RSI14','ATR14')):
        raise ValueError('Indicadores incompletos o no finitos.')

    precio = float(
        ultima["cierre"]
    )

    atr = float(
        ultima["ATR14"]
    )

    atr_pct = (
        atr / precio
    ) * 100

    if (
        ultima["cierre"]
        > ultima["EMA20"]
        > ultima["EMA50"]
    ):
        tendencia = "ALCISTA"

    elif (
        ultima["cierre"]
        < ultima["EMA20"]
        < ultima["EMA50"]
    ):
        tendencia = "BAJISTA"

    else:
        tendencia = "MIXTA"

    return {
        "precio": precio,
        "ema20": float(
            ultima["EMA20"]
        ),
        "ema50": float(
            ultima["EMA50"]
        ),
        "rsi": float(
            ultima["RSI14"]
        ),
        "atr": atr,
        "atr_pct": atr_pct,
        "tendencia": tendencia,
        "vela_cierre_utc_ms": int(ultima['tiempo_cierre']),
    }


def analizar_simbolo(simbolo):
    resultados = {}

    for temporalidad in TEMPORALIDADES:
        df = obtener_velas(
            simbolo,
            temporalidad,
        )

        resultados[temporalidad] = (
            analizar_temporalidad(df, temporalidad)
        )

    return resumir_temporalidades(simbolo, resultados)


def resumir_temporalidades(simbolo, resultados):
    """Consenso común para análisis actual e histórico, sin red ni ejecución."""
    tendencias = [
        resultados[t]["tendencia"]
        for t in TEMPORALIDADES
    ]

    rsi_valores = [
        resultados[t]["rsi"]
        for t in TEMPORALIDADES
    ]

    if all(
        tendencia == "ALCISTA"
        for tendencia in tendencias
    ):
        consenso = "ALCISTA"

    elif all(
        tendencia == "BAJISTA"
        for tendencia in tendencias
    ):
        consenso = "BAJISTA"

    else:
        consenso = "SIN CONSENSO"

    rsi_maximo = max(rsi_valores)
    rsi_minimo = min(rsi_valores)

    if consenso == "ALCISTA":

        if rsi_maximo >= 80:
            estado = (
                "ALCISTA MUY SOBREEXTENDIDA"
            )

        elif rsi_maximo >= 70:
            estado = (
                "ALCISTA SOBREEXTENDIDA"
            )

        else:
            estado = (
                "ALCISTA MOMENTUM SANO"
            )

    elif consenso == "BAJISTA":

        if rsi_minimo <= 20:
            estado = (
                "BAJISTA MUY SOBREEXTENDIDA"
            )

        elif rsi_minimo <= 30:
            estado = (
                "BAJISTA SOBREEXTENDIDA"
            )

        else:
            estado = (
                "BAJISTA MOMENTUM SANO"
            )

    else:
        estado = (
            "SIN VENTAJA DIRECCIONAL"
        )

    return {
        "simbolo": simbolo,
        "consenso": consenso,
        "estado": estado,
        "temporalidades": resultados,
    }


if __name__ == "__main__":
    resultado = analizar_simbolo(
        "BTCUSDT"
    )

    print(
        "\nMOTOR DE ANÁLISIS\n"
    )

    print(
        "Activo:",
        resultado["simbolo"],
    )

    print(
        "Consenso:",
        resultado["consenso"],
    )

    print(
        "Estado:",
        resultado["estado"],
    )

    for temporalidad, datos in (
        resultado[
            "temporalidades"
        ].items()
    ):
        print(
            f"\n{temporalidad}"
        )

        print(
            f"Precio: "
            f"{datos['precio']:,.2f}"
        )

        print(
            f"RSI: "
            f"{datos['rsi']:.2f}"
        )

        print(
            f"ATR: "
            f"{datos['atr']:,.2f}"
        )

        print(
            f"ATR %: "
            f"{datos['atr_pct']:.2f}%"
        )

        print(
            f"Tendencia: "
            f"{datos['tendencia']}"
        )
