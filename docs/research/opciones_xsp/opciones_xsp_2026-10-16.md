# Spreads alcistas de 1 USD en XSP (Black-Scholes con VIX, costes de IBKR)

Preregistro: `PREREGISTRO.md`. Capital 200 USD por año. N del Sharpe deflactado = 259.
**Sin precios grabados de opciones: es un modelo.** Muestra corta (~12 spreads por año).

| Regla | Año | Neto % | Caída % | Spreads | Ganadores | Comisiones USD | Sharpe anual | Sharpe deflactado |
|---|---|---|---|---|---|---|---|---|
| siempre | 2024-25 | +72.25 | 52.75 | 12 | 8 | 23.40 | 1.22 | 0.050 |
| siempre | 2025-26 | +51.22 | 73.14 | 12 | 8 | 23.40 | 0.91 | 0.025 |
| media200 | 2024-25 | +79.68 | 35.17 | 10 | 7 | 19.50 | 1.48 | 0.075 |
| media200 | 2025-26 | +51.22 | 73.14 | 12 | 8 | 23.40 | 0.91 | 0.025 |
| siempre, costes ×2 | 2024-25 | +24.55 | 70.64 | 12 | 8 | 46.80 | 0.68 | 0.015 |
| siempre, costes ×2 | 2025-26 | +3.52 | 90.63 | 12 | 8 | 46.80 | 0.77 | 0.015 |
| media200, costes ×2 | 2024-25 | +39.93 | 48.78 | 10 | 7 | 39.00 | 0.87 | 0.022 |
| media200, costes ×2 | 2025-26 | +3.52 | 90.63 | 12 | 8 | 46.80 | 0.77 | 0.015 |

Referencia, SPX comprar y mantener: 2024: +11.82% ; 2025: +17.29%

## Veredicto

- **siempre:** no pasa (listón: neto > 4% en los dos años y Sharpe deflactado 2025-26 ≥ 0.95).
- **media200:** no pasa (listón: neto > 4% en los dos años y Sharpe deflactado 2025-26 ≥ 0.95).

Aunque pasara, no va a práctica sin repetir la prueba con precios reales de opciones.

## Lectura (escrita después del resultado)

- El spread de 1 USD en el dinero es casi una apuesta de sí o no a que el S&P 500 sube en 30 días: se paga ~50 USD
  y se cobra ~100 o 0. Ganó 8 de 12 porque el S&P subió en los dos años (+11,8% y +17,3%), no por una ventaja.
- Cada spread arriesga ~25% de la cuenta de 200 USD: la caída llegó a 73% en 2025-26, y a 91% con costes al doble.
- Con 12 operaciones por año, el Sharpe deflactado (0,025) queda muy lejos del 0,95: con 259 pruebas ya hechas, este
  resultado se explica por suerte. **No pasa.** No se escala al Líder.
- Lo que sí deja: los costes de IBKR pesan ~4 USD por spread (8% del precio). Con costes al doble, el resultado de
  2025-26 casi desaparece.
