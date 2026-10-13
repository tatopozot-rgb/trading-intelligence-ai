# "BTC régimen": BTC comprado solo por encima de su media (preregistro 2, 2026-10-13)

Reglas escritas antes de la prueba en `PREREGISTRO.md`. Solo BTC, solo largos, todo el capital sin apalancamiento; la señal del cierre diario se ejecuta en la apertura de la hora siguiente. Comisión 0,05% y deslizamiento 0,02% por lado, financiación real. Cada año empieza con 1.000 USDT. La mesa (mesa_r3) son los números ya publicados para las mismas ventanas. Caída medida con el cierre diario.

## 2024-10-12 a 2025-10-12

| Estrategia | Operaciones | Neto % | Máx. caída | Neto/caída | Días comprado | Caída vs BTC | Captura de BTC | Trimestres positivos | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| mesa_r3 | 692 | +4.85% | 53.07% | 0.09 | — | — | — | 2 de 5 | referencia |
| BTC comprar y mantener | 1 | +76.92% | 28.1% | 2.74 | 100% | 0 | 100% | 3 de 5 | referencia |
| btc_sma200 | 6 | +20.53% | 33.26% | 0.62 | 89.6% | +5.16 pts | 26.7% | 3 de 5 | NO se sostiene: falla positiva en 4+ trimestres |
| btc_sma50 | 12 | +53.42% | 21.17% | 2.52 | 67.4% | -6.93 pts | 69.4% | 2 de 5 | NO se sostiene: falla positiva en 4+ trimestres |
| btc_sma200_stop10 | 6 | +34.05% | 15.42% | 2.21 | 89.6% | -12.68 pts | 44.3% | 2 de 5 | NO se sostiene: falla positiva en 4+ trimestres |

| Por trimestre | 2024-T4 | 2025-T1 | 2025-T2 | 2025-T3 | 2025-T4 |
|---|---|---|---|---|---|
| mesa_r3 | +4.78% | -23.90% | -8.95% | +57.04% | -8.03% |
| BTC | +49.63% | -11.78% | +29.80% | +6.44% | -2.99% |
| btc_sma200 | +37.48% | -23.78% | +13.84% | +4.56% | -3.38% |
| btc_sma50 | +46.42% | -7.17% | +18.72% | -3.56% | -1.41% |
| btc_sma200_stop10 | +38.77% | -9.87% | +7.18% | +0.00% | +0.00% |

## 2025-10-12 a 2026-10-12

| Estrategia | Operaciones | Neto % | Máx. caída | Neto/caída | Días comprado | Caída vs BTC | Captura de BTC | Trimestres positivos | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| mesa_r3 | 743 | -53.06% | 70.33% | -0.75 | — | — | — | 2 de 5 | referencia |
| BTC comprar y mantener | 1 | -24.29% | 49.1% | -0.49 | 100% | 0 | 100% | 2 de 5 | referencia |
| btc_sma200 | 5 | +8.18% | 13.0% | 0.63 | 19.7% | -36.10 pts | -33.7% | 1 de 5 | NO se sostiene: falla positiva en 4+ trimestres |
| btc_sma50 | 12 | +14.06% | 17.69% | 0.79 | 44.4% | -31.41 pts | -57.9% | 2 de 5 | NO se sostiene: falla positiva en 4+ trimestres |
| btc_sma200_stop10 | 5 | +6.08% | 14.68% | 0.41 | 19.7% | -34.42 pts | -25.0% | 1 de 5 | NO se sostiene: falla positiva en 4+ trimestres |

| Por trimestre | 2025-T4 | 2026-T1 | 2026-T2 | 2026-T3 | 2026-T4 |
|---|---|---|---|---|---|
| mesa_r3 | -45.73% | -36.30% | -11.85% | +49.79% | +2.83% |
| BTC | -20.78% | -22.09% | -14.15% | +42.64% | +0.18% |
| btc_sma200 | -9.49% | +0.00% | +0.00% | +19.65% | -0.11% |
| btc_sma50 | -2.36% | -11.23% | +8.03% | +21.94% | -0.11% |
| btc_sma200_stop10 | -11.24% | +0.00% | +0.00% | +19.65% | -0.11% |

## Veredicto

- **btc_sma200**: no pasa en los dos años (NO se sostiene: falla positiva en 4+ trimestres; NO se sostiene: falla positiva en 4+ trimestres).
- **btc_sma50**: no pasa en los dos años (NO se sostiene: falla positiva en 4+ trimestres; NO se sostiene: falla positiva en 4+ trimestres).
- **btc_sma200_stop10**: no pasa en los dos años (NO se sostiene: falla positiva en 4+ trimestres; NO se sostiene: falla positiva en 4+ trimestres).

Advertencias: una regla de régimen opera pocas veces, así que dos años son pocos cambios de régimen; el precio Spot aproxima al perpetuo. Un resultado pasado no promete uno futuro.
