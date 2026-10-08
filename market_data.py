"""Radar de demostración: datos públicos validados, sin operaciones ni red al importar."""
from trading_scanner import obtener_candidatos


def main():
    print("\nRADAR DE OPORTUNIDADES — BINANCE SPOT / USDT\n")
    for numero, activo in enumerate(obtener_candidatos(limite=15), start=1):
        cambio = activo['cambio']
        direccion = 'ALZA' if cambio > 0 else 'BAJA'
        riesgo = 'EXTREMO' if abs(cambio) >= 30 else ('ALTO' if abs(cambio) >= 15 else 'NORMAL')
        print(
            f"{numero:02}. {activo['simbolo']:12} | {direccion:4} | "
            f"Riesgo: {riesgo:7} | Precio: {activo['precio']:,.6f} | "
            f"24h: {cambio:+.2f}% | Volumen: ${activo['volumen']:,.0f} | "
            f"Score: {activo['score']:.2f}"
        )


if __name__ == '__main__':
    main()
