# Cartera de tendencia multi-mercado en XM

Preregistro: `docs/research/cartera_xm/PREREGISTRO.md`, escrito antes de correr. EWMAC de Carver (cuatro pares, escalas fijas) en todos los mercados a la vez, riesgo igual por mercado, lotes de XM; spread y swap de XM. Sharpe deflactado con N = 258 decisorias y V = 1/T.

## Veredicto

- **No pasa.** Neto/caída con 200 USD -0.48 ; -0.42 contra la mesa 1.67 ; -0.21 (no gana los dos años); Sharpe deflactado 2025-26 0.0 (listón 0.95, no pasa).
- **Lotes con 200 USD:** caben 1 de 15 mercados con riesgo igual (JP225Cash); con 1.000 USD caben 10 y con 5.000 USD 12.
- **Desde qué capital funciona** (gana a la mesa los dos años y pasa el Sharpe deflactado): con ninguno de 200, 1.000 o 5.000 USD.

## 2024-10-12 → 2025-10-12 (mesa de práctica neto/caída 1.67)

| Fila | Neto % | Máx. caída | Neto/caída | Órdenes | Entradas | Spread % | Swap % | Sharpe anual | Sharpe deflactado | Trimestres (neto %) | Mercados operados |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Cartera EWMAC, 200 USD, lotes de XM | -3.5% | 7.33% | -0.48 | 24 | 7 | 0.09 | 0.41 | -0.54 | 0.0 | -0.2 / -0.1 / -5.6 / +2.5 | 2 |
| Cartera EWMAC, 1.000 USD, lotes de XM | -17.3% | 24.14% | -0.72 | 224 | 54 | 1.09 | 4.74 | -1.03 | 0.0 | +5.4 / -11.8 / -9.6 / -1.6 | 10 |
| Cartera EWMAC, 5.000 USD, lotes de XM | +13.6% | 17.63% | 0.77 | 779 | 75 | 1.51 | 18.78 | 0.59 | 0.013 | +7.7 / -2.5 / -3.3 / +11.8 | 15 |
| Misma regla con 100.000 USD (sin efecto del lote mínimo) | +9.7% | 17.24% | 0.56 | 1771 | 67 | 1.31 | 19.23 | 0.46 | 0.009 | +5.4 / -3.3 / -2.1 / +10.0 | 15 |
| 200 USD, spread y swap ×2 | -4.0% | 7.44% | -0.54 | 24 | 7 | 0.19 | 0.82 | -0.62 | 0.0 | -0.3 / -0.2 / -5.7 / +2.3 | 2 |

Aporte por mercado, fila de 100.000 USD (neto % del capital): AUDUSD -1.4, BTCUSD +0.5, ETHUSD -1.5, EURUSD -0.9, GBPUSD -3.0, GER40Cash +3.5, GOLD +15.2, JP225Cash +1.9, OILCash -2.8, SILVER +7.4, US100Cash -1.4, US500Cash -5.0, USDCAD +1.4, USDCHF -0.7, USDJPY -3.3

## 2025-10-13 → 2026-10-13 (mesa de práctica neto/caída -0.21)

| Fila | Neto % | Máx. caída | Neto/caída | Órdenes | Entradas | Spread % | Swap % | Sharpe anual | Sharpe deflactado | Trimestres (neto %) | Mercados operados |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Cartera EWMAC, 200 USD, lotes de XM | -4.6% | 10.94% | -0.42 | 39 | 12 | 0.37 | 0.97 | -0.6 | 0.0 | -0.0 / -1.3 / +5.0 / -7.9 | 3 |
| Cartera EWMAC, 1.000 USD, lotes de XM | -7.1% | 11.98% | -0.59 | 233 | 50 | 1.06 | 3.61 | -0.44 | 0.0 | -1.2 / -3.2 / +1.4 / -4.3 | 9 |
| Cartera EWMAC, 5.000 USD, lotes de XM | -26.5% | 32.51% | -0.82 | 660 | 82 | 1.29 | 6.62 | -1.2 | 0.0 | -11.1 / -8.4 / +5.7 / -14.6 | 15 |
| Misma regla con 100.000 USD (sin efecto del lote mínimo) | -13.6% | 33.02% | -0.41 | 1762 | 89 | 1.36 | 9.96 | -0.4 | 0.0 | +8.6 / -7.3 / +2.9 / -16.5 | 15 |
| 200 USD, spread y swap ×2 | -3.1% | 10.62% | -0.3 | 35 | 11 | 0.63 | 1.95 | -0.4 | 0.001 | -0.7 / +1.0 / +4.4 / -7.5 | 3 |

Aporte por mercado, fila de 100.000 USD (neto % del capital): AUDUSD +1.3, BTCUSD -2.1, ETHUSD -1.8, EURUSD -1.6, GBPUSD -3.1, GER40Cash -5.0, GOLD +3.5, JP225Cash +2.6, OILCash +2.0, SILVER +4.0, US100Cash -1.6, US500Cash -3.2, USDCAD -1.7, USDCHF -2.3, USDJPY -4.6

## Lote mínimo contra el tamaño de riesgo igual (pronóstico 10)

| Mercado | Lote mínimo (USD expuestos) | Buscado con 200 USD | Veces | Cabe con 200 | con 1.000 | con 5.000 |
|---|---|---|---|---|---|---|
| AUDUSD | 695.71 | 132.61 | 5.2 | no | sí | sí |
| BTCUSD | 830.72 | 28.95 | 28.7 | no | no | sí |
| ETHUSD | 50.36 | 21.98 | 2.3 | no | sí | sí |
| EURUSD | 1115.37 | 163.38 | 6.8 | no | sí | sí |
| GBPUSD | 1320.58 | 162.82 | 8.1 | no | sí | sí |
| GER40Cash | 2816.09 | 66.03 | 42.6 | no | no | sí |
| GOLD | 4171.49 | 35.28 | 118.2 | no | no | no |
| JP225Cash | 43.0 | 36.34 | 1.2 | sí | sí | sí |
| OILCash | 94.31 | 18.88 | 5.0 | no | sí | sí |
| SILVER | 3013.6 | 20.7 | 145.6 | no | no | no |
| US100Cash | 3064.8 | 53.9 | 56.9 | no | no | no |
| US500Cash | 780.69 | 86.68 | 9.0 | no | sí | sí |
| USDCAD | 1000.0 | 211.27 | 4.7 | no | sí | sí |
| USDCHF | 1000.0 | 137.7 | 7.3 | no | sí | sí |
| USDJPY | 1000.0 | 107.49 | 9.3 | no | sí | sí |

El spread y el swap son los de la ficha de hoy y el spread de cada vela; el swap histórico pudo ser otro. El capital diario está en el JSON. Un resultado pasado no promete uno futuro.
