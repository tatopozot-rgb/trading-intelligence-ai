"""Demostración del motor validado; exclusivamente velas cerradas, sin ejecutar órdenes."""
from analysis_engine import obtener_velas, analizar_temporalidad, analizar_simbolo, TEMPORALIDADES, LIMITE

SIMBOLO = 'BTCUSDT'


def analizar(df, intervalo=None, ahora_ms=None):
    """Compatibilidad con la demo; exige intervalo explícito o attrs del DataFrame."""
    return analizar_temporalidad(df, intervalo, ahora_ms)


def main():
    resultado = analizar_simbolo(SIMBOLO)
    print(f"\nANÁLISIS MULTITEMPORAL — {SIMBOLO}\n")
    for temporalidad, datos in resultado['temporalidades'].items():
        print(f"--- {temporalidad} ---")
        print(f"Precio: {datos['precio']:,.2f}")
        print(f"EMA20:  {datos['ema20']:,.2f}")
        print(f"EMA50:  {datos['ema50']:,.2f}")
        print(f"RSI14:  {datos['rsi']:.2f}")
        print(f"Tendencia: {datos['tendencia']}\n")
    print('CONSENSO MULTITEMPORAL:', resultado['consenso'])
    print('ESTADO DEL MERCADO:', resultado['estado'])


if __name__ == '__main__':
    main()
