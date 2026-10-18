# Supertrend de freqtrade (FSupertrendStrategy) en BTC y ETH

Preregistro: `docs/research/supertrend/PREREGISTRO.md`, escrito antes de correr. Parámetros del código tal cual (salieron de una optimización: riesgo alto de sobreajuste). Velas de 1 hora; 0,05% de comisión y 0,02% de deslizamiento por lado; financiación real; 1.000 USDT. Sharpe deflactado con N = 272 decisorias.

## Veredicto

- **A tal cual, BTC: no pasa.** Neto/caída -0.37 ; -0.73 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.0 (listón 0.95); operaciones 198 ; 217.
- **A tal cual, ETH: no pasa.** Neto/caída -0.1 ; -0.83 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.0 (listón 0.95); operaciones 265 ; 249.
- **A tal cual, BTC y ETH: no pasa.** Neto/caída -0.24 ; -0.79 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.0 (listón 0.95); operaciones 463 ; 466.
- **B con frenos, BTC: no pasa.** Neto/caída 0.59 ; -0.65 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.0 (listón 0.95); operaciones 97 ; 64 (muestra corta).
- **B con frenos, ETH: no pasa.** Neto/caída 2.29 ; -0.42 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.001 (listón 0.95); operaciones 134 ; 77 (muestra corta).
- **B con frenos, BTC y ETH: no pasa.** Neto/caída 1.53 ; -0.55 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.001 (listón 0.95); operaciones 231 ; 141.

## 2024-10-12 → 2025-10-12

Mantener BTC: +76.9% / caída 30.94% (neto/caída 2.49).

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Ops | Largos/cortos | Acierto | Media por op. | Salidas | Comisiones | Financiación | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A tal cual, BTC | decisoria | -19.5% | 53.26% | -0.37 | 198 | 117/81 | 51.5% | -0.059% | fin 1, roi 100, señal 97 | 177.37 | -1.56 | -0.28 | 0.001 | +12.4 / -27.6 / -14.1 / -8.4 / +25.7 |
| A tal cual, ETH | decisoria | -6.2% | 60.54% | -0.1 | 265 | 153/112 | 65.3% | +0.054% | fin 1, roi 173, señal 91 | 220.28 | 1.98 | 0.2 | 0.004 | -2.3 / -14.5 / -33.6 / +32.9 / +27.4 |
| A tal cual, BTC y ETH | decisoria | -12.8% | 53.69% | -0.24 | 463 | 270/193 | 59.4% | +0.006% | fin 2, roi 273, señal 188 | 198.82 | 0.21 | -0.08 | 0.002 | +5.0 / -21.5 / -24.0 / +9.8 / +26.6 |
| B con frenos, BTC | decisoria | +7.0% | 11.88% | 0.59 | 97 | 97/0 | 45.4% | +0.078% | roi 43, señal 51, stop 3 | 66.32 | 16.46 | 0.54 | 0.009 | +10.4 / -6.1 / +2.0 / -3.3 / +4.6 |
| B con frenos, ETH | decisoria | +26.9% | 11.74% | 2.29 | 134 | 134/0 | 60.4% | +0.188% | roi 81, régimen 1, señal 35, stop 17 | 84.73 | 15.64 | 1.36 | 0.053 | +8.2 / -1.6 / +5.4 / +10.5 / +2.3 |
| B con frenos, BTC y ETH | decisoria | +16.9% | 11.06% | 1.53 | 231 | 231/0 | 54.1% | +0.142% | roi 124, régimen 1, señal 86, stop 20 | 75.53 | 16.05 | 1.17 | 0.035 | +9.3 / -3.9 / +3.7 / +3.8 / +3.3 |
| A juntas, costos ×2 | sensibilidad | -35.6% | 60.99% | -0.58 | 461 | 269/192 | 59.0% | -0.125% | fin 2, roi 271, señal 188 | 349.17 | 0.35 | -0.76 | 0.0 | -2.2 / -26.7 / -28.5 / +2.4 / +22.7 |
| B juntas, costos ×2 | sensibilidad | +6.7% | 13.15% | 0.51 | 230 | 230/0 | 53.9% | +0.064% | roi 123, régimen 1, señal 87, stop 19 | 142.59 | 15.36 | 0.54 | 0.009 | +6.2 / -4.3 / +0.9 / +1.4 / +2.5 |

## 2025-10-13 → 2026-10-13

Mantener BTC: -28.8% / caída 49.77% (neto/caída -0.58).

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Ops | Largos/cortos | Acierto | Media por op. | Salidas | Comisiones | Financiación | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A tal cual, BTC | decisoria | -33.2% | 45.23% | -0.73 | 217 | 115/102 | 49.3% | -0.147% | fin 1, roi 98, señal 118 | 196.56 | -6.2 | -0.66 | 0.0 | -22.5 / +20.4 / -6.8 / -19.3 / -4.7 |
| A tal cual, ETH | decisoria | -50.1% | 60.54% | -0.83 | 249 | 130/119 | 54.6% | -0.219% | fin 1, roi 135, señal 113 | 196.76 | 3.09 | -0.89 | 0.0 | -24.8 / +6.9 / -15.6 / -26.4 / -0.3 |
| A tal cual, BTC y ETH | decisoria | -41.6% | 52.51% | -0.79 | 466 | 245/221 | 52.1% | -0.186% | fin 2, roi 233, señal 231 | 196.66 | -1.56 | -0.88 | 0.0 | -23.6 / +13.8 / -10.9 / -22.4 / -2.9 |
| B con frenos, BTC | decisoria | -7.5% | 11.47% | -0.65 | 64 | 64/0 | 39.1% | -0.113% | roi 21, señal 40, stop 3 | 40.55 | 3.21 | -0.63 | 0.0 | -2.0 / -0.1 / -3.3 / +0.1 / -2.4 |
| B con frenos, ETH | decisoria | -6.3% | 15.19% | -0.42 | 77 | 77/0 | 44.2% | -0.074% | roi 33, señal 38, stop 6 | 44.49 | 4.26 | -0.4 | 0.001 | -1.2 / -3.3 / -7.5 / +8.2 / -2.0 |
| B con frenos, BTC y ETH | decisoria | -6.9% | 12.43% | -0.55 | 141 | 141/0 | 41.8% | -0.092% | roi 54, señal 78, stop 9 | 42.52 | 3.73 | -0.56 | 0.001 | -1.6 / -1.7 / -5.4 / +4.0 / -2.2 |
| A juntas, costos ×2 | sensibilidad | -58.1% | 64.15% | -0.91 | 463 | 243/220 | 51.0% | -0.331% | fin 2, roi 230, señal 231 | 337.96 | -1.9 | -1.61 | 0.0 | -29.7 / +5.5 / -16.8 / -29.2 / -4.0 |
| B juntas, costos ×2 | sensibilidad | -12.7% | 14.24% | -0.89 | 139 | 139/0 | 39.6% | -0.186% | roi 52, señal 78, stop 9 | 80.41 | 3.46 | -1.18 | 0.0 | -1.8 / -2.7 / -6.8 / +0.5 / -2.6 |

Precio del contado de Binance; financiación del perpetuo. En una vela que toca el stop y la meta cuenta el stop. La media por operación es sobre el capital de la moneda. El capital diario está en el JSON. Un resultado pasado no promete uno futuro.
