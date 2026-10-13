# Preregistro: dos reglas de tendencia fijas en un año no usado (2024-10-12 a 2025-10-12)

Reglas escritas el 2026-10-12 en `PREREGISTRO.md`, elegidas en retrospectiva sobre 2025-10-12 a 2026-10-12 y probadas aquí sin cambiar nada en el año anterior. Parámetros fijos, nunca reajustados; empiezan con 1.000 USDT. Mismos costes y tamaños que el estudio de tendencia. La mesa (mesa_r3) y comprar y mantener BTC se miden en las mismas ventanas de 30 días.

| Estrategia | Operaciones | Neto % | Máx. caída | Neto/caída | Acierto | Ganancia media | Pérdida media | Comisiones | Financiación | Correlación con la mesa | Trimestres positivos | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **mesa_r3 (la mesa en vivo)** | 692 | +4.85% | 53.07% | 0.09 | 43.1% | +14.52 | -10.86 | 225.55 | +74.20 | — | 2 de 5 | referencia |
| BTC comprar y mantener | — | +76.92% | 28.1% | 2.74 | — | — | — | — | — | 0.62 | 3 de 5 | referencia |
| ema_1d_20_50_atr3 | 42 | -4.21% | 41.86% | -0.1 | 31.0% | +58.86 | -27.84 | 13.55 | +54.32 | 0.253 | 2 de 5 | NO se sostiene: falla neto positivo, neto/caída mejor que la mesa, positiva en 4+ trimestres |
| tsmom_60d | 137 | +64.88% | 41.0% | 1.58 | 46.7% | +47.47 | -32.73 | 75.30 | +86.59 | 0.313 | 2 de 5 | NO se sostiene: falla positiva en 4+ trimestres |

## Por trimestre (neto %)

| Estrategia | 2024-T4 | 2025-T1 | 2025-T2 | 2025-T3 | 2025-T4 |
|---|---|---|---|---|---|
| mesa_r3 | +4.78% | -23.90% | -8.95% | +57.04% | -8.03% |
| BTC | +49.63% | -11.78% | +29.80% | +6.44% | -2.99% |
| ema_1d_20_50_atr3 | +18.90% | -1.45% | +7.03% | -12.75% | -12.47% |
| tsmom_60d | +77.44% | +43.54% | -25.10% | -6.30% | -7.75% |

Advertencias: el precio Spot aproxima al perpetuo; un año más de historia no garantiza el futuro.

## Datos de la mesa por ventana (control)

| Ventana | Operaciones | Sin mínimo | Vetos (evitó pérdida / dejó pasar ganancia) | Final | Velas con top traders (mín. / media por moneda) |
|---|---|---|---|---|---|
| 2024-10-12 | 55 | 11 | 0 / 0 | fin del periodo | 100.0% / 100.0% |
| 2024-11-11 | 59 | 15 | 6 / 6 | fin del periodo | 100.0% / 100.0% |
| 2024-12-11 | 27 | 0 | 0 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-01-10 | 34 | 1 | 0 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-02-09 | 56 | 24 | 5 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-03-11 | 96 | 0 | 0 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-04-10 | 69 | 0 | 0 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-05-10 | 75 | 11 | 2 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-06-09 | 44 | 5 | 0 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-07-09 | 47 | 1 | 0 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-08-08 | 56 | 190 | 1 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-09-07 | 59 | 0 | 13 / 0 | fin del periodo | 100.0% / 100.0% |
| 2025-10-07 | 15 | 7 | 0 / 0 | fin del periodo | 100.0% / 100.0% |
