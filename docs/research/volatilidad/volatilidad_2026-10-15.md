# "Freno de volatilidad" para la mesa

Preregistrado en `docs/research/volatilidad/PREREGISTRO.md` antes de correr. Volatilidad de 7 días de BTC (desviación de los últimos 7 rendimientos logarítmicos diarios cerrados) contra su percentil 80 / 90 / 95 de los 365 días anteriores; por encima, sin entradas nuevas. La mesa (`mesa_r3`, reglas de hoy) repetida en sesiones de 30 días con 1.000 USDT. Decide V90 en la mesa de práctica (régimen b + eventos): ayuda si mejora el neto/caída de su base en los dos años sin quitar más de la mitad de las operaciones.

## Veredicto

**El freno de volatilidad (V90) no ayuda** en la mesa de práctica — neto/caída 2024-10-12 → 2025-10-12: 1.52 contra 1.73 (350 de 361 operaciones); 2025-10-13 → 2026-10-13: -0.3 contra 0.2 (215 de 218 operaciones).

Tiempo con el freno puesto, 2024-10-12 → 2025-10-12: V80 10.1%, V90 7.4%, V95 3.0%.

## 2024-10-12 → 2025-10-12 — régimen b + eventos (la mesa de práctica)

| Filtro | Neto % | Máx. caída | Neto/caída | Ops | Trimestres (neto %) |
|---|---|---|---|---|---|
| base | +81.2% | 46.89% | 1.73 | 361 | +66.8 / -10.6 / -25.5 / +63.0 |
| V80 | +34.9% | 43.95% | 0.79 | 330 | +16.9 / -10.6 / -20.8 / +63.0 |
| V90 | +66.9% | 44.02% | 1.52 | 350 | +44.6 / -10.6 / -20.8 / +63.0 |
| V95 | +87.1% | 45.14% | 1.93 | 356 | +66.8 / -10.6 / -23.0 / +63.0 |

## 2024-10-12 → 2025-10-12 — solo freno de eventos

| Filtro | Neto % | Máx. caída | Neto/caída | Ops | Trimestres (neto %) |
|---|---|---|---|---|---|
| base | +23.7% | 56.73% | 0.42 | 672 | +14.3 / -33.6 / -6.1 / +73.7 |
| V80 | +15.8% | 50.04% | 0.32 | 591 | -0.4 / -19.5 / -16.8 / +73.7 |
| V90 | +26.9% | 55.06% | 0.49 | 632 | +25.6 / -30.1 / -16.8 / +73.7 |
| V95 | +21.4% | 57.53% | 0.37 | 654 | +14.3 / -27.8 / -15.2 / +73.7 |

Tiempo con el freno puesto, 2025-10-13 → 2026-10-13: V80 24.1%, V90 11.5%, V95 3.3%.

## 2025-10-13 → 2026-10-13 — régimen b + eventos (la mesa de práctica)

| Filtro | Neto % | Máx. caída | Neto/caída | Ops | Trimestres (neto %) |
|---|---|---|---|---|---|
| base | +6.6% | 32.33% | 0.2 | 218 | -8.4 / -10.8 / -3.1 / +34.7 |
| V80 | -21.3% | 28.14% | -0.76 | 189 | -6.4 / -10.2 / +0.9 / -7.2 |
| V90 | -9.5% | 31.44% | -0.3 | 215 | -6.4 / -10.8 / -3.1 / +11.8 |
| V95 | +6.6% | 32.33% | 0.2 | 218 | -8.4 / -10.8 / -3.1 / +34.7 |

## 2025-10-13 → 2026-10-13 — solo freno de eventos

| Filtro | Neto % | Máx. caída | Neto/caída | Ops | Trimestres (neto %) |
|---|---|---|---|---|---|
| base | -62.0% | 76.83% | -0.81 | 725 | -46.9 / -41.5 / -14.4 / +42.9 |
| V80 | -53.0% | 61.63% | -0.86 | 572 | -35.2 / -22.0 / -16.9 / +11.9 |
| V90 | -50.0% | 67.76% | -0.74 | 653 | -34.2 / -36.4 / -12.6 / +36.7 |
| V95 | -63.3% | 78.08% | -0.81 | 701 | -46.9 / -44.7 / -12.6 / +42.9 |

Advertencias: precio Spot como aproximación del perpetuo; la volatilidad realizada no es la implícita (DVOL) del que habla la teoría; el freno solo impide entradas. Un resultado pasado no promete uno futuro.
