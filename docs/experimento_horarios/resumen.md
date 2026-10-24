# Experimento horarios — resumen acumulado

Simulación con datos públicos (PAPER): **sin cuenta, sin claves, sin órdenes reales**. Entradas cada 20 min (velas de 20 min); con posición abierta se revisa la salida cada 3 min (velas de 1 min): stop de la estrategia, su condición de salida y cierre forzado al final de la ventana. 10 USDT por operación, comisión 0.1% por lado + 5 bps. Horas en **Ecuador (UTC−5)**, UTC entre paréntesis. Reglas en `docs/PREREG_HORARIOS.md` (con las Enmiendas 1 y 2).

Días forward: 14/14 (días hábiles lun–vie: 10/10) · días de referencia: 15

## Resultado de las reglas pre-registradas

### Alcance lun-vie (decide)
- **PRINCIPAL — ventana del dueño, todos los símbolos, por estrategia (α = 0.0125):** 0 califican · 2 sin operaciones suficientes
- **Ventana del dueño, baseline por símbolo (BH q = 0.10 sobre 13):** 0 califican
- **Búsqueda: baseline ventana × símbolo (BH sobre candidatas):** 0 califican
- **Búsqueda: tendencia por ventana, todos los símbolos (BH sobre 12):** 0 califican · 12 sin operaciones suficientes
- **Búsqueda: tendencia por símbolo, todas las ventanas (BH sobre 13):** 0 califican · 13 sin operaciones suficientes
- **Búsqueda: rango por ventana, todos los símbolos (BH sobre 12):** 0 califican · 12 sin operaciones suficientes
- **Búsqueda: rango por símbolo, todas las ventanas (BH sobre 13):** 0 califican · 13 sin operaciones suficientes
- **Búsqueda: ruptura por ventana, todos los símbolos (BH sobre 12):** 0 califican · 1 sin operaciones suficientes
- **Búsqueda: ruptura por símbolo, todas las ventanas (BH sobre 13):** 0 califican
- **Búsqueda: baseline por ventana, todos los símbolos (BH sobre 12):** 0 califican
- **Búsqueda: baseline por símbolo, todas las ventanas (BH sobre 13):** 0 califican
- **Ninguna hora ni mercado resultó mejor que el azar en este alcance.**

### Alcance lun-sab (alternativa, a elegir por el dueño)
- **PRINCIPAL — ventana del dueño, todos los símbolos, por estrategia (α = 0.0125):** 0 califican · 2 sin operaciones suficientes
- **Ventana del dueño, baseline por símbolo (BH q = 0.10 sobre 13):** 0 califican
- **Búsqueda: baseline ventana × símbolo (BH sobre candidatas):** 0 califican
- **Búsqueda: tendencia por ventana, todos los símbolos (BH sobre 12):** 0 califican · 12 sin operaciones suficientes
- **Búsqueda: tendencia por símbolo, todas las ventanas (BH sobre 13):** 0 califican · 13 sin operaciones suficientes
- **Búsqueda: rango por ventana, todos los símbolos (BH sobre 12):** 0 califican · 12 sin operaciones suficientes
- **Búsqueda: rango por símbolo, todas las ventanas (BH sobre 13):** 0 califican · 13 sin operaciones suficientes
- **Búsqueda: ruptura por ventana, todos los símbolos (BH sobre 12):** 0 califican
- **Búsqueda: ruptura por símbolo, todas las ventanas (BH sobre 13):** 0 califican
- **Búsqueda: baseline por ventana, todos los símbolos (BH sobre 12):** 0 califican
- **Búsqueda: baseline por símbolo, todas las ventanas (BH sobre 13):** 0 califican
- **Ninguna hora ni mercado resultó mejor que el azar en este alcance.**


## FORWARD — por día de la semana

| Día | tendencia: n / media % | rango: n / media % | ruptura: n / media % | baseline: n / media % |
|---|---|---|---|---|
| lunes | 16 / -0.007 | · | 131 / -0.493 | 338 / -0.511 |
| martes | 15 / -0.790 | 1 / -0.564 | 190 / -0.206 | 338 / -0.057 |
| miércoles | 5 / -0.671 | 20 / -1.366 | 186 / -0.397 | 338 / -0.409 |
| jueves | 11 / -0.092 | · | 135 / -0.251 | 338 / -0.361 |
| viernes | 13 / -0.631 | · | 181 / -0.430 | 338 / -0.387 |
| sábado (aparte) | 1 / -0.268 | 9 / -0.211 | 156 / -0.309 | 338 / -0.334 |
| domingo (no decide) | 7 / +0.240 | 8 / -0.387 | 183 / -0.139 | 338 / -0.270 |

## FORWARD — tendencia: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | +0.10 | -0.19 | +0.31 | +0.42 | +0.01 | +0.16 | -0.99 | +0.82 | -0.27 | -0.48 | · | +1.41 | -0.57 | +0.73 |
| 21–23 Ecuador (02–04 UTC) | · | · | -0.20 | · | · | · | · | -0.34 | · | -0.72 | -0.21 | · | · | -1.47 |
| 23–01 Ecuador (04–06 UTC) | -0.03 | · | · | · | · | -0.22 | -0.65 | -1.30 | -0.52 | -0.35 | · | -0.38 | -0.21 | -3.66 |
| 01–03 Ecuador (06–08 UTC) | · | -0.47 | -0.46 | -0.69 | -0.53 | · | · | -0.44 | · | · | -0.30 | · | · | -2.88 |
| 03–05 Ecuador (08–10 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 05–07 Ecuador (10–12 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 07–09 Ecuador (12–14 UTC) | · | · | · | · | · | · | · | · | · | · | · | -1.23 | · | -1.23 |
| 09–11 Ecuador (14–16 UTC) | -1.02 | -2.33 | · | · | · | · | -1.68 | · | -2.59 | -2.66 | · | · | · | -10.27 |
| 11–13 Ecuador (16–18 UTC) | -0.13 | +0.49 | -1.23 | -0.46 | -0.83 | · | +0.57 | +0.27 | -0.44 | · | · | · | · | -1.75 |
| 13–15 Ecuador (18–20 UTC) | · | · | · | · | · | · | · | · | · | · | · | -0.39 | · | -0.39 |
| 15–17 Ecuador (20–22 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 17–19 Ecuador (22–00 UTC) | · | · | · | -0.76 | -0.82 | · | · | · | · | · | · | · | · | -1.59 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | -1.02 | -1.05 | · | · | · | · | +0.23 | · | +0.20 | · | · | -0.38 | · | -2.03 |

## FORWARD — rango: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 21–23 Ecuador (02–04 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 23–01 Ecuador (04–06 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 01–03 Ecuador (06–08 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 03–05 Ecuador (08–10 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 05–07 Ecuador (10–12 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 07–09 Ecuador (12–14 UTC) | -1.09 | -1.32 | -0.97 | -1.59 | · | -1.58 | -1.67 | -1.66 | -1.93 | · | · | · | · | -11.80 |
| 09–11 Ecuador (14–16 UTC) | · | · | -1.01 | · | -0.91 | · | · | · | -1.00 | · | · | · | · | -2.92 |
| 11–13 Ecuador (16–18 UTC) | · | · | -0.37 | · | · | · | · | · | · | · | · | · | -0.56 | -0.94 |
| 13–15 Ecuador (18–20 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 15–17 Ecuador (20–22 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 17–19 Ecuador (22–00 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | -1.09 | -1.32 | -0.97 | -1.66 | · | -1.58 | -2.01 | -1.66 | -1.93 | · | · | · | · | -12.21 |

## FORWARD — ruptura: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | -2.98 | -2.07 | -1.89 | -2.74 | -1.16 | -2.74 | -3.01 | -3.60 | -3.05 | -3.06 | -0.74 | +0.95 | -1.65 | -27.75 |
| 21–23 Ecuador (02–04 UTC) | -1.40 | -0.56 | -1.74 | -1.34 | -1.22 | -1.06 | -0.60 | -0.20 | -0.79 | -2.56 | -2.23 | +0.42 | -2.25 | -15.51 |
| 23–01 Ecuador (04–06 UTC) | -3.04 | -3.31 | -4.05 | -3.60 | -5.44 | -3.06 | -3.38 | -3.39 | -5.35 | -4.40 | -1.13 | -4.30 | -1.50 | -45.97 |
| 01–03 Ecuador (06–08 UTC) | -1.48 | -2.03 | -1.69 | -2.26 | -1.87 | -2.83 | -2.28 | -1.72 | -0.50 | -1.98 | -0.89 | -4.47 | -1.60 | -25.61 |
| 03–05 Ecuador (08–10 UTC) | -1.36 | -1.74 | -1.47 | -2.18 | -1.12 | -2.57 | -1.37 | -0.22 | +0.82 | -1.89 | -0.75 | -4.00 | -0.95 | -18.81 |
| 05–07 Ecuador (10–12 UTC) | -0.59 | +0.39 | -0.19 | -2.15 | -1.67 | -3.15 | -2.25 | -2.74 | -2.24 | -1.07 | -1.49 | -1.15 | -1.39 | -19.71 |
| 07–09 Ecuador (12–14 UTC) | -2.62 | -0.77 | -1.30 | -2.76 | -1.93 | -0.92 | -4.42 | -2.87 | -2.54 | -1.97 | -0.54 | -3.55 | -3.09 | -29.27 |
| 09–11 Ecuador (14–16 UTC) | -0.39 | +0.74 | -0.62 | +2.07 | -1.98 | -1.44 | +0.43 | +0.23 | -2.25 | -0.52 | -0.95 | -3.55 | -1.47 | -9.71 |
| 11–13 Ecuador (16–18 UTC) | -2.84 | -2.41 | -2.07 | -2.58 | -2.24 | -3.20 | -2.98 | -4.02 | -2.48 | -2.21 | -1.56 | -4.22 | -1.54 | -34.37 |
| 13–15 Ecuador (18–20 UTC) | -2.10 | -1.09 | -0.55 | -1.61 | -0.92 | -1.65 | -1.25 | -1.98 | -0.28 | -1.57 | -1.71 | -3.31 | -0.65 | -18.66 |
| 15–17 Ecuador (20–22 UTC) | -2.14 | -1.81 | -1.69 | -1.30 | -1.77 | -3.57 | -2.71 | -4.12 | -0.46 | -1.63 | -0.44 | -5.83 | -1.35 | -28.81 |
| 17–19 Ecuador (22–00 UTC) | · | -0.96 | -1.45 | · | -1.88 | -1.71 | -1.48 | -1.83 | -1.47 | -0.86 | -0.42 | +1.08 | -0.89 | -11.89 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | -3.04 | +1.77 | -0.39 | -2.46 | +1.23 | +1.49 | -2.65 | -0.77 | +1.46 | +0.92 | -0.93 | +3.08 | -2.93 | -3.23 |

## FORWARD — baseline: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | -3.14 | -2.66 | -2.93 | -2.78 | -3.66 | -2.99 | -5.05 | -1.83 | -5.38 | -2.46 | -1.90 | -1.68 | -3.22 | -39.66 |
| 21–23 Ecuador (02–04 UTC) | -2.09 | -2.05 | -3.05 | -2.26 | -2.70 | -2.53 | -4.40 | -2.49 | -4.01 | -2.65 | -2.03 | -1.58 | -1.00 | -32.85 |
| 23–01 Ecuador (04–06 UTC) | -3.22 | -3.08 | -2.35 | -2.68 | -2.66 | -3.16 | -3.74 | -3.58 | -2.10 | -3.66 | -3.17 | -5.43 | -4.09 | -42.93 |
| 01–03 Ecuador (06–08 UTC) | -2.02 | -1.22 | -1.37 | -0.51 | -0.65 | -0.26 | -0.98 | +0.05 | -3.29 | -1.23 | -2.33 | -0.51 | -3.35 | -17.69 |
| 03–05 Ecuador (08–10 UTC) | -4.81 | -5.74 | -3.92 | -7.00 | -5.40 | -6.45 | -7.10 | -7.59 | -4.28 | -6.99 | -2.37 | -9.86 | -3.42 | -74.94 |
| 05–07 Ecuador (10–12 UTC) | -3.40 | -3.47 | -3.92 | -4.65 | -4.29 | -3.18 | -4.55 | -5.23 | -6.90 | -6.71 | -3.29 | +0.25 | -3.58 | -52.93 |
| 07–09 Ecuador (12–14 UTC) | -5.47 | -5.47 | -4.44 | -4.86 | -5.89 | -6.94 | -6.33 | -7.79 | -6.55 | -6.11 | -3.66 | -4.68 | -4.27 | -72.45 |
| 09–11 Ecuador (14–16 UTC) | -1.21 | +1.07 | -1.91 | -0.80 | -1.85 | -1.18 | -2.37 | +0.85 | -1.70 | -2.99 | -3.65 | -0.94 | -4.66 | -21.35 |
| 11–13 Ecuador (16–18 UTC) | -4.10 | -4.85 | -3.40 | -4.31 | -4.75 | -4.78 | -3.47 | -5.13 | -5.10 | -1.94 | -2.82 | -2.97 | -3.39 | -51.01 |
| 13–15 Ecuador (18–20 UTC) | -2.27 | -3.84 | -2.90 | -4.21 | -3.21 | -1.92 | -2.86 | -3.29 | -3.90 | -1.00 | -2.66 | -5.67 | -2.17 | -39.88 |
| 15–17 Ecuador (20–22 UTC) | -1.81 | -2.24 | -2.74 | -1.80 | -2.68 | -3.51 | -2.83 | -2.66 | -2.00 | -7.43 | -4.05 | -5.65 | -2.95 | -42.35 |
| 17–19 Ecuador (22–00 UTC) | -5.98 | -7.56 | -5.14 | -7.32 | -6.10 | -6.63 | -8.00 | -6.24 | -7.24 | -3.29 | -3.09 | -4.47 | -4.43 | -75.48 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | -1.62 | -0.11 | -1.04 | +0.15 | -1.22 | -2.87 | -1.76 | -2.04 | +0.04 | -2.62 | -3.78 | +2.11 | -4.60 | -19.36 |

## FORWARD — mejores y peores celdas (lun–vie)

**Mejores 5 (descriptivo, puede ser suerte):**
- DOTUSDT · ruptura · 07–10 Ecuador (12–15 UTC) — ventana del dueño: +3.08% neto en 6 operación(es)
- DOTUSDT · baseline · 07–10 Ecuador (12–15 UTC) — ventana del dueño: +2.11% neto en 10 operación(es)
- SOLUSDT · ruptura · 09–11 Ecuador (14–16 UTC): +2.07% neto en 3 operación(es)
- ETHUSDT · ruptura · 07–10 Ecuador (12–15 UTC) — ventana del dueño: +1.77% neto en 6 operación(es)
- DOGEUSDT · ruptura · 07–10 Ecuador (12–15 UTC) — ventana del dueño: +1.49% neto en 5 operación(es)

**Peores 5:**
- DOTUSDT · baseline · 03–05 Ecuador (08–10 UTC): -9.86% neto en 10 operación(es)
- ADAUSDT · baseline · 17–19 Ecuador (22–00 UTC): -8.00% neto en 10 operación(es)
- LINKUSDT · baseline · 07–09 Ecuador (12–14 UTC): -7.79% neto en 10 operación(es)
- LINKUSDT · baseline · 03–05 Ecuador (08–10 UTC): -7.59% neto en 10 operación(es)
- ETHUSDT · baseline · 17–19 Ecuador (22–00 UTC): -7.56% neto en 10 operación(es)

## referencia: datos pasados — por día de la semana

| Día | tendencia: n / media % | rango: n / media % | ruptura: n / media % | baseline: n / media % |
|---|---|---|---|---|
| lunes | 12 / -0.859 | 3 / -0.167 | 143 / -0.487 | 338 / -0.431 |
| martes | 3 / -0.419 | 5 / -0.117 | 154 / -0.398 | 338 / -0.331 |
| miércoles | 2 / -0.359 | · | 148 / -0.514 | 338 / -0.493 |
| jueves | 10 / -0.474 | 1 / -0.921 | 175 / -0.416 | 338 / -0.497 |
| viernes | 12 / -0.023 | · | 233 / -0.440 | 507 / -0.266 |
| sábado (aparte) | 9 / +0.238 | · | 156 / -0.258 | 338 / -0.250 |
| domingo (no decide) | 9 / -0.176 | · | 144 / -0.268 | 338 / -0.262 |

## referencia: datos pasados — tendencia: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | · | · | · | · | · | · | -0.74 | · | · | -0.95 | -0.33 | +2.86 | · | +0.84 |
| 21–23 Ecuador (02–04 UTC) | · | · | · | · | · | · | · | · | · | · | -0.39 | · | -0.38 | -0.76 |
| 23–01 Ecuador (04–06 UTC) | · | · | · | · | -0.23 | · | +1.14 | -0.62 | -0.17 | -0.49 | · | -1.51 | -0.50 | -2.37 |
| 01–03 Ecuador (06–08 UTC) | · | · | · | · | -0.47 | · | · | · | · | · | -0.36 | · | · | -0.83 |
| 03–05 Ecuador (08–10 UTC) | · | +0.02 | · | · | · | · | · | · | -0.37 | · | -0.21 | · | · | -0.55 |
| 05–07 Ecuador (10–12 UTC) | · | · | -0.55 | · | · | · | · | · | · | -0.43 | -0.12 | · | · | -1.10 |
| 07–09 Ecuador (12–14 UTC) | · | -0.45 | · | · | · | · | · | +0.91 | · | · | · | · | · | +0.45 |
| 09–11 Ecuador (14–16 UTC) | · | · | · | · | -2.48 | · | · | · | · | · | -0.00 | · | -0.70 | -3.18 |
| 11–13 Ecuador (16–18 UTC) | · | · | · | · | · | · | · | · | · | -0.24 | -0.33 | · | · | -0.57 |
| 13–15 Ecuador (18–20 UTC) | -0.88 | · | · | · | -0.72 | · | · | · | · | · | · | · | · | -1.60 |
| 15–17 Ecuador (20–22 UTC) | · | · | · | · | · | · | · | · | · | · | · | -0.38 | · | -0.38 |
| 17–19 Ecuador (22–00 UTC) | · | · | · | -0.50 | -0.25 | · | · | · | +0.44 | · | · | · | · | -0.31 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | · | -1.32 | · | · | -2.48 | · | · | -2.71 | · | · | · | · | -0.43 | -6.94 |

## referencia: datos pasados — rango: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 21–23 Ecuador (02–04 UTC) | -0.44 | · | · | · | · | · | · | · | · | · | · | · | · | -0.44 |
| 23–01 Ecuador (04–06 UTC) | · | · | · | · | · | -0.06 | · | -0.52 | -0.92 | · | · | · | · | -1.50 |
| 01–03 Ecuador (06–08 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 03–05 Ecuador (08–10 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 05–07 Ecuador (10–12 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 07–09 Ecuador (12–14 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 09–11 Ecuador (14–16 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 11–13 Ecuador (16–18 UTC) | · | +0.16 | · | · | · | · | · | · | · | · | · | · | · | +0.16 |
| 13–15 Ecuador (18–20 UTC) | · | -0.21 | · | · | · | · | · | · | · | · | · | · | · | -0.21 |
| 15–17 Ecuador (20–22 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 17–19 Ecuador (22–00 UTC) | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | · | · | · | · | · | · | · | · | · | · | · | · | · | +0.00 |

## referencia: datos pasados — ruptura: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | -0.34 | -1.91 | -1.86 | -0.51 | -3.86 | -4.12 | -4.21 | -3.77 | -1.88 | -3.30 | -0.72 | -0.23 | -1.19 | -27.90 |
| 21–23 Ecuador (02–04 UTC) | -1.04 | -2.00 | -1.87 | -1.02 | -0.66 | -0.73 | -1.13 | -3.14 | -0.67 | -5.03 | -1.03 | -2.83 | -1.67 | -22.83 |
| 23–01 Ecuador (04–06 UTC) | -4.09 | -3.60 | -3.26 | -3.28 | -3.52 | -6.37 | -4.07 | -5.59 | -2.03 | -2.00 | -1.75 | -5.38 | -2.17 | -47.10 |
| 01–03 Ecuador (06–08 UTC) | -1.29 | -0.94 | -1.34 | -2.63 | -2.59 | -0.88 | +0.45 | +0.49 | +1.85 | -0.68 | -2.42 | -1.25 | -1.22 | -12.45 |
| 03–05 Ecuador (08–10 UTC) | -0.97 | -0.32 | -0.33 | +0.17 | -1.59 | -3.18 | -1.36 | +0.52 | -1.28 | -2.05 | -1.19 | +1.26 | -0.81 | -11.13 |
| 05–07 Ecuador (10–12 UTC) | -2.45 | -1.23 | -1.45 | -0.15 | -0.25 | +0.79 | -2.47 | -0.81 | -0.91 | -3.09 | -0.34 | +0.28 | -2.33 | -14.42 |
| 07–09 Ecuador (12–14 UTC) | -2.09 | -4.39 | -1.46 | -2.24 | -5.13 | -5.70 | -5.28 | -4.32 | -2.25 | -1.49 | · | -4.46 | -2.25 | -41.05 |
| 09–11 Ecuador (14–16 UTC) | -2.35 | -1.25 | -1.80 | -2.45 | -3.94 | -1.32 | -2.68 | -5.35 | -1.57 | -2.62 | -0.36 | -3.07 | -2.05 | -30.81 |
| 11–13 Ecuador (16–18 UTC) | -1.16 | -1.86 | -0.11 | -1.41 | -0.36 | -0.31 | -2.29 | -2.76 | -0.77 | -0.92 | -2.15 | -3.01 | -2.34 | -19.46 |
| 13–15 Ecuador (18–20 UTC) | -2.28 | -1.97 | -0.76 | -1.61 | -2.06 | -0.78 | -0.40 | -0.76 | +0.68 | -1.66 | -3.35 | -1.71 | -2.91 | -19.59 |
| 15–17 Ecuador (20–22 UTC) | -1.52 | -0.98 | -3.21 | -2.59 | -3.84 | -2.29 | -4.10 | -3.65 | -4.82 | -4.65 | -0.27 | -7.55 | -1.58 | -41.05 |
| 17–19 Ecuador (22–00 UTC) | -3.38 | -1.96 | -2.49 | -1.43 | -1.41 | -1.20 | -1.26 | -1.86 | -0.86 | -3.83 | -0.54 | -2.38 | -0.55 | -23.15 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | -5.78 | -5.39 | -2.58 | -4.77 | -7.75 | -10.70 | -10.50 | -5.25 | -2.82 | -4.63 | -0.90 | -6.40 | -3.86 | -71.35 |

## referencia: datos pasados — baseline: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | -6.20 | -6.14 | -5.34 | -6.45 | -5.32 | -7.68 | -5.57 | -7.07 | -8.57 | -7.43 | -2.91 | -5.78 | -3.31 | -77.77 |
| 21–23 Ecuador (02–04 UTC) | -4.28 | -6.02 | -4.98 | -3.38 | -4.33 | -6.06 | -4.01 | -6.88 | -6.28 | -4.98 | -4.60 | -4.33 | -3.46 | -63.58 |
| 23–01 Ecuador (04–06 UTC) | -2.11 | -2.06 | -2.34 | -3.29 | -2.78 | -3.15 | +2.05 | -2.64 | +0.29 | -2.14 | -3.17 | +0.98 | -3.82 | -24.18 |
| 01–03 Ecuador (06–08 UTC) | -2.95 | -1.75 | -4.21 | -3.90 | -1.34 | -1.02 | +0.79 | -2.80 | +2.37 | -2.69 | -2.52 | +1.41 | -2.90 | -21.52 |
| 03–05 Ecuador (08–10 UTC) | -1.66 | -1.68 | -2.65 | -2.70 | -1.27 | -1.53 | +0.51 | +1.89 | -1.61 | -2.29 | -3.41 | -2.97 | -3.11 | -22.46 |
| 05–07 Ecuador (10–12 UTC) | -1.63 | -1.89 | -1.71 | -0.38 | +0.13 | -0.44 | -1.56 | -0.59 | +1.45 | -2.30 | -3.56 | -2.18 | -2.22 | -16.87 |
| 07–09 Ecuador (12–14 UTC) | -3.97 | -5.12 | -4.47 | -4.07 | -2.44 | -3.25 | -4.73 | -3.47 | -9.24 | -6.72 | -3.83 | -9.72 | -5.13 | -66.13 |
| 09–11 Ecuador (14–16 UTC) | -9.67 | -13.83 | -10.64 | -13.85 | -15.98 | -16.27 | -22.46 | -18.18 | -17.04 | -11.28 | -3.61 | -17.69 | -5.67 | -176.16 |
| 11–13 Ecuador (16–18 UTC) | -3.29 | -3.79 | -3.23 | -3.01 | -7.20 | -5.83 | -3.95 | -1.01 | -2.62 | -7.68 | -2.13 | -2.59 | -2.66 | -48.98 |
| 13–15 Ecuador (18–20 UTC) | -2.94 | -2.25 | -4.80 | -4.76 | -2.80 | -4.76 | -9.61 | -3.91 | -6.22 | -2.83 | -3.26 | -2.77 | -2.23 | -53.14 |
| 15–17 Ecuador (20–22 UTC) | -3.50 | -2.58 | -2.25 | -1.95 | -3.77 | -1.54 | -0.10 | -1.90 | -0.08 | +0.03 | -4.07 | +2.34 | -3.22 | -22.57 |
| 17–19 Ecuador (22–00 UTC) | -2.10 | -1.94 | -0.98 | -0.60 | -0.31 | +0.22 | +3.64 | +0.87 | +5.59 | -0.59 | -3.89 | +2.38 | -2.95 | -0.66 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | -6.70 | -9.24 | -7.24 | -8.95 | -8.22 | -10.21 | -14.82 | -11.38 | -15.21 | -12.09 | -4.12 | -18.12 | -6.75 | -133.04 |

## referencia: datos pasados — mejores y peores celdas (lun–vie)

**Mejores 5 (descriptivo, puede ser suerte):**
- AVAXUSDT · baseline · 17–19 Ecuador (22–00 UTC): +5.59% neto en 11 operación(es)
- ADAUSDT · baseline · 17–19 Ecuador (22–00 UTC): +3.64% neto en 11 operación(es)
- DOTUSDT · tendencia · 19–21 Ecuador (00–02 UTC): +2.86% neto en 1 operación(es)
- DOTUSDT · baseline · 17–19 Ecuador (22–00 UTC): +2.38% neto en 11 operación(es)
- AVAXUSDT · baseline · 01–03 Ecuador (06–08 UTC): +2.37% neto en 11 operación(es)

**Peores 5:**
- ADAUSDT · baseline · 09–11 Ecuador (14–16 UTC): -22.46% neto en 11 operación(es)
- LINKUSDT · baseline · 09–11 Ecuador (14–16 UTC): -18.18% neto en 11 operación(es)
- DOTUSDT · baseline · 07–10 Ecuador (12–15 UTC) — ventana del dueño: -18.12% neto en 11 operación(es)
- DOTUSDT · baseline · 09–11 Ecuador (14–16 UTC): -17.69% neto en 11 operación(es)
- AVAXUSDT · baseline · 09–11 Ecuador (14–16 UTC): -17.04% neto en 11 operación(es)

Las tablas y listas son descriptivas: con cientos de celdas, algunas se ven bien por azar. Solo las reglas pre-registradas pueden declarar una hora o mercado mejor.
