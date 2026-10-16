# Carry de financiación en BTC y ETH (spot comprado + perpetuo vendido)

Preregistro: `docs/research/carry_btceth/PREREGISTRO.md`, escrito antes de correr. Datos 2020-01-01 → 2026-09-30. Entra con la media de 21 pagos ≥ 0.0042%/8h, sale bajo 0%. Mitad spot, mitad margen del corto (1x). Costes: spot 0,10% y perpetuo 0,05% por lado, más 0,02% de deslizamiento en cada pata. Efectivo de referencia: 4% al año.

## Veredicto

- **regla, BTCUSDT: no pasa.** Neto +3.47% y +0.95% (efectivo 4%); neto/caída 12.79 ; 3.97 contra 1,67 ; −0,21; Sharpe deflactado 2025-26 0.788 (listón 0.95).
- **regla, ETHUSDT: no pasa.** Neto +2.56% y +0.66% (efectivo 4%); neto/caída 6.62 ; 2.62 contra 1,67 ; −0,21; Sharpe deflactado 2025-26 0.405 (listón 0.95).

## 2024-10-12 → 2025-10-12

| Prueba | Neto % | Anual % | Máx. caída | Neto/caída | Financiación % | Costes % | Base % | Tiempo dentro | Sharpe anual | Sharpe deflactado | Trimestres |
|---|---|---|---|---|---|---|---|---|---|---|---|
| regla, BTCUSDT | +3.47% | +3.47% | 0.27% | 12.79 | +3.89% | 0.43% | +0.01% | 95.8% | 6.88 | 0.987 | +1.45 / +0.65 / +0.22 / +0.98 / +0.14 |
| regla, ETHUSDT | +2.56% | +2.56% | 0.39% | 6.62 | +3.76% | 1.2% | +0.00% | 88.9% | 4.25 | 0.912 | +1.61 / +0.35 / +0.13 / +0.52 / -0.07 |
| siempre dentro, BTCUSDT | +3.14% | +3.14% | 0.22% | 13.98 | +3.32% | 0.18% | -0.00% | 100.0% | 9.37 | 0.998 | +1.14 / +0.56 / +0.40 / +0.89 / +0.12 |
| siempre dentro, ETHUSDT | +2.39% | +2.39% | 0.13% | 17.86 | +2.38% | 0.0% | +0.01% | 100.0% | 12.42 | 1.0 | +1.08 / +0.37 / +0.26 / +0.60 / +0.05 |

## 2025-10-13 → 2026-10-13

| Prueba | Neto % | Anual % | Máx. caída | Neto/caída | Financiación % | Costes % | Base % | Tiempo dentro | Sharpe anual | Sharpe deflactado | Trimestres |
|---|---|---|---|---|---|---|---|---|---|---|---|
| regla, BTCUSDT | +0.95% | +0.98% | 0.24% | 3.97 | +1.60% | 0.66% | +0.00% | 61.7% | 3.45 | 0.788 | +0.16 / +0.12 / -0.07 / +0.73 |
| regla, ETHUSDT | +0.66% | +0.68% | 0.25% | 2.62 | +1.28% | 0.64% | +0.02% | 63.6% | 2.08 | 0.405 | +0.33 / +0.08 / -0.03 / +0.27 |
| siempre dentro, BTCUSDT | +1.02% | +1.05% | 0.14% | 7.14 | +1.10% | 0.07% | -0.01% | 100.0% | 8.07 | 1.0 | +0.38 / +0.13 / +0.07 / +0.43 |
| siempre dentro, ETHUSDT | +0.62% | +0.64% | 0.13% | 4.59 | +0.67% | 0.05% | -0.00% | 100.0% | 6.4 | 1.0 | +0.31 / +0.05 / +0.04 / +0.22 |

## Todo el periodo (2020-01-01 → 2026-09-30)

| Prueba | Neto % | Anual % | Máx. caída | Financiación % | Costes % | Tiempo dentro | Entradas | Rebalanceos |
|---|---|---|---|---|---|---|---|---|
| regla, BTCUSDT | +45.7% | +5.73% | 1.19% | +52.7% | 7.09% | 81.8% | 21 | 8 |
| regla, ETHUSDT | +52.4% | +6.44% | 1.74% | +62.1% | 9.32% | 82.0% | 20 | 16 |
| siempre dentro, BTCUSDT | +39.6% | +5.06% | 1.6% | +41.4% | 1.62% | 100.0% | 1 | 6 |
| siempre dentro, ETHUSDT | +47.1% | +5.88% | 0.61% | +49.6% | 2.08% | 100.0% | 1 | 8 |

## ¿Cabe en 31 USDT?

- **BTCUSDT: no cabe.** El perpetuo pide al menos 100 USDT de tamaño (no verificado (Claude local debe confirmarlo)); con 31 USDT no queda margen para el corto después de comprar el spot.
- **ETHUSDT:** pata mínima 20 USDT (perpetuo 20, no verificado (Claude local debe confirmarlo); spot 5), margen del corto 11 USDT, apalancamiento del corto 1.82x. Lo liquida una subida de 54.2% (margen aislado, mantenimiento 0.5%). En 20 tenencias de la regla desde 2020, la peor subida fue 3004.9% y hubo 8 que habrían liquidado sin rebalancear. Ingreso neto aproximado: +2.58 USDT al año.

Advertencias: el spot y el perpetuo viven en carteras distintas; la ganancia del spot no protege al corto de la liquidación salvo que se pase dinero entre carteras (el rebalanceo). Un resultado pasado no promete uno futuro. Nada de esto mueve dinero real.
