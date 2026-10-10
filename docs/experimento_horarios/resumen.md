# Experimento horarios — resumen acumulado

Simulación con datos públicos (PAPER): **sin cuenta, sin claves, sin órdenes reales**. Entradas cada 20 min (velas de 20 min); con posición abierta se revisa la salida cada 3 min (velas de 1 min): stop de la estrategia, su condición de salida y cierre forzado al final de la ventana. 10 USDT por operación, comisión 0.1% por lado + 5 bps. Horas en **Ecuador (UTC−5)**, UTC entre paréntesis. Reglas en `docs/PREREG_HORARIOS.md` (con las Enmiendas 1 y 2).

Días forward: 0/14 (días hábiles lun–vie: 0/10) · días de referencia: 15

Las reglas se aplican cuando el período forward esté completo (2026-10-10 → 2026-10-23).

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
