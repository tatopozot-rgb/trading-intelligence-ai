# ¿Predice algo el sentimiento de la mesa?

Investigación con datos públicos. El sentimiento de la mesa (`desk.sentiment`): financiación (40%) y top traders (40%); el Miedo y Codicia (20%) no tiene historia aquí. "Acuerdo" (lean) = el sentimiento con el signo de la operación: positivo si favorece al lado de la operación. Resultado = el movimiento a 24 h a favor de la operación (sin stops ni costes). Una configuración por moneda cada 24 h como máximo.

## Veredicto

**El sentimiento no predice nada útil:** la correlación entre el acuerdo del sentimiento con la operación y su resultado a 24 h no es positiva y significativa en los dos años.
Mejor umbral por neto/caída en la mesa repetida: 2024-10-12 a 2025-10-12: apagada; 2025-10-12 a 2026-10-12: -0.1.
Financiación sola, 2020-01-02 a 2026-10-01 (28535 días-moneda): Spearman 0.003 (p 0.6087) entre el componente de financiación del sentimiento y la subida de las 24 h siguientes.

## A. Entradas de la mesa, 2024-10-12 a 2025-10-12

### Todas

| Acuerdo (lean) | n | Media 24 h % | Mediana % | Acierto | t |
|---|---|---|---|---|---|
| -1.0 a -0.5 | 0 | None | None | None | None |
| -0.5 a -0.3 | 0 | None | None | None | None |
| -0.3 a -0.1 | 30 | 0.539 | 0.307 | 53.3 | 1.53 |
| -0.1 a +0.1 | 237 | 0.327 | -0.059 | 48.9 | 1.56 |
| +0.1 a +0.3 | 426 | 0.171 | -0.16 | 47.2 | 0.91 |
| +0.3 a +0.5 | 2463 | 0.173 | -0.039 | 49.2 | 1.68 |
| +0.5 a +1.0 | 3 | -1.018 | -0.084 | 33.3 | -0.26 |

Spearman -0.037 (p 0.0365), n 3159, media 0.186%.

### Largos

| Acuerdo (lean) | n | Media 24 h % | Mediana % | Acierto | t |
|---|---|---|---|---|---|
| -1.0 a -0.5 | 0 | None | None | None | None |
| -0.5 a -0.3 | 0 | None | None | None | None |
| -0.3 a -0.1 | 8 | 1.216 | 0.526 | 75.0 | 1.97 |
| -0.1 a +0.1 | 131 | 0.792 | 0.328 | 57.3 | 2.47 |
| +0.1 a +0.3 | 392 | 0.21 | -0.111 | 48.5 | 1.04 |
| +0.3 a +0.5 | 2462 | 0.173 | -0.042 | 49.1 | 1.67 |
| +0.5 a +1.0 | 3 | -1.018 | -0.084 | 33.3 | -0.26 |

Spearman -0.049 (p 0.0072), n 2996, media 0.206%.

### Cortos

| Acuerdo (lean) | n | Media 24 h % | Mediana % | Acierto | t |
|---|---|---|---|---|---|
| -1.0 a -0.5 | 0 | None | None | None | None |
| -0.5 a -0.3 | 0 | None | None | None | None |
| -0.3 a -0.1 | 22 | 0.292 | -0.16 | 45.5 | 0.69 |
| -0.1 a +0.1 | 106 | -0.247 | -0.384 | 38.7 | -1.02 |
| +0.1 a +0.3 | 34 | -0.284 | -0.285 | 32.4 | -0.83 |
| +0.3 a +0.5 | 1 | 0.926 | 0.926 | 100.0 | None |
| +0.5 a +1.0 | 0 | None | None | None | None |

Spearman -0.041 (p 0.6021), n 163, media -0.175%.

### La mesa repetida con otro umbral del Escéptico de sentimiento (bloques de 30 días encadenados)

| Umbral | Neto % | Máx. caída | Neto/caída | Ops |
|---|---|---|---|---|
| apagada | +17.6% | 58.18% | 0.3 | 675 |
| -0.5 | +17.6% | 58.18% | 0.3 | 675 |
| -0.3 | +17.6% | 58.18% | 0.3 | 675 |
| -0.2 | +17.6% | 58.18% | 0.3 | 675 |
| -0.1 | +3.6% | 54.76% | 0.07 | 647 |

## A. Entradas de la mesa, 2025-10-12 a 2026-10-12

### Todas

| Acuerdo (lean) | n | Media 24 h % | Mediana % | Acierto | t |
|---|---|---|---|---|---|
| -1.0 a -0.5 | 0 | None | None | None | None |
| -0.5 a -0.3 | 0 | None | None | None | None |
| -0.3 a -0.1 | 28 | -1.4 | 0.683 | 53.6 | -1.08 |
| -0.1 a +0.1 | 380 | -0.038 | 0.036 | 50.8 | -0.26 |
| +0.1 a +0.3 | 548 | 0.06 | -0.091 | 48.2 | 0.49 |
| +0.3 a +0.5 | 2024 | -0.188 | -0.265 | 45.1 | -2.46 |
| +0.5 a +1.0 | 11 | 2.499 | 1.86 | 72.7 | 1.16 |

Spearman -0.051 (p 0.0051), n 2991, media -0.125%.

### Largos

| Acuerdo (lean) | n | Media 24 h % | Mediana % | Acierto | t |
|---|---|---|---|---|---|
| -1.0 a -0.5 | 0 | None | None | None | None |
| -0.5 a -0.3 | 0 | None | None | None | None |
| -0.3 a -0.1 | 4 | 1.535 | 0.51 | 50.0 | 0.92 |
| -0.1 a +0.1 | 196 | 0.008 | 0.041 | 51.0 | 0.04 |
| +0.1 a +0.3 | 389 | 0.115 | -0.108 | 48.3 | 0.69 |
| +0.3 a +0.5 | 1970 | -0.194 | -0.288 | 45.0 | -2.48 |
| +0.5 a +1.0 | 11 | 2.499 | 1.86 | 72.7 | 1.16 |

Spearman -0.052 (p 0.0079), n 2570, media -0.118%.

### Cortos

| Acuerdo (lean) | n | Media 24 h % | Mediana % | Acierto | t |
|---|---|---|---|---|---|
| -1.0 a -0.5 | 0 | None | None | None | None |
| -0.5 a -0.3 | 0 | None | None | None | None |
| -0.3 a -0.1 | 24 | -1.889 | 0.683 | 54.2 | -1.28 |
| -0.1 a +0.1 | 184 | -0.086 | 0.032 | 50.5 | -0.44 |
| +0.1 a +0.3 | 159 | -0.074 | -0.032 | 47.8 | -0.68 |
| +0.3 a +0.5 | 54 | 0.039 | -0.035 | 48.1 | 0.23 |
| +0.5 a +1.0 | 0 | None | None | None | None |

Spearman -0.004 (p 0.9276), n 421, media -0.168%.

### La mesa repetida con otro umbral del Escéptico de sentimiento (bloques de 30 días encadenados)

| Umbral | Neto % | Máx. caída | Neto/caída | Ops |
|---|---|---|---|---|
| apagada | -60.1% | 73.15% | -0.82 | 738 |
| -0.5 | -60.1% | 73.15% | -0.82 | 738 |
| -0.3 | -60.1% | 73.15% | -0.82 | 738 |
| -0.2 | -60.1% | 73.15% | -0.82 | 738 |
| -0.1 | -59.5% | 73.89% | -0.81 | 707 |

## B. Financiación sola, 2020-01-02 a 2026-10-01 (una fila por moneda y día, 00:00 UTC)

"Acuerdo" = componente de financiación del sentimiento para un largo (financiación negativa = acuerdo positivo). Resultado = subida del spot en las 24 h siguientes.

| Acuerdo (lean) | n | Media 24 h % | Mediana % | Acierto | t |
|---|---|---|---|---|---|
| -1.0 a -0.5 | 1579 | 0.818 | -0.188 | 48.4 | 3.99 |
| -0.5 a -0.3 | 980 | 0.681 | 0.119 | 52.0 | 3.06 |
| -0.3 a -0.1 | 1435 | 0.188 | 0.174 | 51.9 | 1.13 |
| -0.1 a +0.1 | 21860 | 0.147 | 0.025 | 50.3 | 4.18 |
| +0.1 a +0.3 | 1834 | 0.152 | 0.206 | 52.9 | 1.35 |
| +0.3 a +0.5 | 425 | -0.184 | 0.03 | 50.4 | -0.67 |
| +0.5 a +1.0 | 422 | 1.407 | 0.797 | 58.3 | 3.59 |

Spearman 0.003 (p 0.6087), n 28535, media 0.219%.

| Año | n | Spearman | p |
|---|---|---|---|
| 2020 | 3335 | 0.072 | 0.0 |
| 2021 | 4380 | 0.004 | 0.7953 |
| 2022 | 4380 | 0.053 | 0.0004 |
| 2023 | 4380 | 0.022 | 0.1444 |
| 2024 | 4392 | 0.005 | 0.7509 |
| 2025 | 4380 | 0.01 | 0.4893 |
| 2026 | 3288 | 0.012 | 0.5017 |

Advertencias: el resultado a 24 h no es el de la operación con stop y meta (eso está en la tabla de umbrales); los datos de top traders cubren solo los dos años de la parte A; el Miedo y Codicia no entra.
