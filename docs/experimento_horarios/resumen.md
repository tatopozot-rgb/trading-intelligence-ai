# Experimento horarios — resumen acumulado

Simulación con datos públicos (PAPER): **sin cuenta, sin claves, sin órdenes reales**. Entradas cada 20 min (velas de 20 min); con posición abierta se revisa la salida cada 3 min (velas de 1 min): stop de la estrategia, su condición de salida y cierre forzado al final de la ventana. 10 USDT por operación, comisión 0.1% por lado + 5 bps. Horas en **Ecuador (UTC−5)**, UTC entre paréntesis. Reglas en `docs/PREREG_HORARIOS.md` (con las Enmiendas 1 y 2).

Días forward: 0/14 (días hábiles lun–vie: 0/10) · días de referencia: 14

Las reglas se aplican cuando el período forward esté completo (2026-10-10 → 2026-10-23).

## referencia: datos pasados — por día de la semana

| Día | tendencia: n / media % | rango: n / media % | ruptura: n / media % | baseline: n / media % |
|---|---|---|---|---|
| lunes | 12 / -0.859 | 3 / -0.167 | 143 / -0.487 | 338 / -0.431 |
| martes | 3 / -0.419 | 5 / -0.117 | 154 / -0.398 | 338 / -0.331 |
| miércoles | 2 / -0.359 | · | 148 / -0.514 | 338 / -0.493 |
| jueves | 10 / -0.474 | 1 / -0.921 | 175 / -0.416 | 338 / -0.497 |
| viernes | 6 / -0.198 | · | 161 / -0.535 | 338 / -0.298 |
| sábado (aparte) | 9 / +0.238 | · | 156 / -0.258 | 338 / -0.250 |
| domingo (no decide) | 9 / -0.176 | · | 144 / -0.268 | 338 / -0.262 |

## referencia: datos pasados — tendencia: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | · | · | · | · | · | · | -0.74 | · | · | -0.95 | -0.33 | · | · | -2.02 |
| 21–23 Ecuador (02–04 UTC) | · | · | · | · | · | · | · | · | · | · | -0.39 | · | -0.38 | -0.76 |
| 23–01 Ecuador (04–06 UTC) | · | · | · | · | · | · | +1.14 | · | -0.17 | · | · | -1.51 | -0.50 | -1.04 |
| 01–03 Ecuador (06–08 UTC) | · | · | · | · | -0.47 | · | · | · | · | · | -0.36 | · | · | -0.83 |
| 03–05 Ecuador (08–10 UTC) | · | +0.02 | · | · | · | · | · | · | · | · | -0.21 | · | · | -0.19 |
| 05–07 Ecuador (10–12 UTC) | · | · | -0.55 | · | · | · | · | · | · | -0.43 | -0.12 | · | · | -1.10 |
| 07–09 Ecuador (12–14 UTC) | · | -0.45 | · | · | · | · | · | +0.91 | · | · | · | · | · | +0.45 |
| 09–11 Ecuador (14–16 UTC) | · | · | · | · | -2.48 | · | · | · | · | · | -0.00 | · | -0.70 | -3.18 |
| 11–13 Ecuador (16–18 UTC) | · | · | · | · | · | · | · | · | · | -0.24 | -0.33 | · | · | -0.57 |
| 13–15 Ecuador (18–20 UTC) | -0.88 | · | · | · | -0.72 | · | · | · | · | · | · | · | · | -1.60 |
| 15–17 Ecuador (20–22 UTC) | · | · | · | · | · | · | · | · | · | · | · | -0.38 | · | -0.38 |
| 17–19 Ecuador (22–00 UTC) | · | · | · | -0.50 | · | · | · | · | +0.44 | · | · | · | · | -0.06 |
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
| 19–21 Ecuador (00–02 UTC) | -0.34 | -1.91 | -1.86 | -0.51 | -3.69 | -3.98 | -4.21 | -3.77 | -2.56 | -3.14 | -0.72 | -0.72 | -1.29 | -28.73 |
| 21–23 Ecuador (02–04 UTC) | -1.02 | -1.87 | -1.68 | -0.84 | -0.44 | -0.73 | -1.43 | -3.00 | -0.09 | -5.03 | -1.03 | -2.19 | -1.38 | -20.72 |
| 23–01 Ecuador (04–06 UTC) | -3.61 | -3.60 | -2.86 | -3.28 | -2.93 | -5.89 | -3.94 | -4.97 | -1.43 | -1.52 | -1.75 | -5.08 | -1.71 | -42.57 |
| 01–03 Ecuador (06–08 UTC) | -1.12 | -0.78 | -0.84 | -1.87 | -2.43 | -0.46 | +0.87 | +0.87 | +2.27 | -0.68 | -2.42 | -2.40 | -1.22 | -10.22 |
| 03–05 Ecuador (08–10 UTC) | -0.97 | -0.32 | -0.33 | +0.17 | -1.59 | -3.18 | -1.36 | +0.52 | -1.28 | -1.75 | -0.72 | +1.26 | -0.81 | -10.36 |
| 05–07 Ecuador (10–12 UTC) | -2.42 | -1.02 | -1.45 | -0.27 | -0.25 | +0.79 | -2.47 | -0.81 | -0.91 | -3.09 | -0.13 | +0.28 | -2.33 | -14.08 |
| 07–09 Ecuador (12–14 UTC) | -2.09 | -4.39 | -1.46 | -2.24 | -5.13 | -5.70 | -5.28 | -4.32 | -2.25 | -1.49 | · | -4.46 | -2.25 | -41.05 |
| 09–11 Ecuador (14–16 UTC) | -2.35 | -0.85 | -1.40 | -1.72 | -3.94 | -1.32 | -2.68 | -5.04 | -1.57 | -2.62 | -0.06 | -3.07 | -2.05 | -28.66 |
| 11–13 Ecuador (16–18 UTC) | -1.16 | -1.86 | -0.11 | -1.41 | -0.15 | -0.31 | -2.29 | -2.76 | -0.77 | -0.92 | -2.15 | -3.01 | -2.34 | -19.24 |
| 13–15 Ecuador (18–20 UTC) | -2.28 | -1.97 | -0.76 | -1.61 | -2.06 | -0.78 | -0.40 | -0.76 | +0.68 | -1.66 | -2.85 | -1.71 | -2.91 | -19.09 |
| 15–17 Ecuador (20–22 UTC) | -1.24 | -0.76 | -3.14 | -2.18 | -3.51 | -2.54 | -5.06 | -3.33 | -5.80 | -4.43 | -0.27 | -7.55 | -1.19 | -41.00 |
| 17–19 Ecuador (22–00 UTC) | -3.08 | -1.55 | -2.06 | -0.93 | -1.16 | -0.84 | -1.42 | -1.37 | -0.42 | -3.01 | -0.54 | -2.57 | -0.55 | -19.50 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | -5.78 | -5.39 | -2.58 | -4.77 | -7.75 | -10.70 | -10.50 | -5.25 | -2.82 | -4.63 | -0.90 | -6.40 | -3.38 | -70.86 |

## referencia: datos pasados — baseline: neto % acumulado lun–vie por ventana × símbolo

| Ventana | BTC | ETH | BNB | SOL | XRP | DOGE | ADA | LINK | AVAX | LTC | TRX | DOT | PAXG | Todas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19–21 Ecuador (00–02 UTC) | -6.17 | -6.14 | -5.16 | -5.99 | -5.70 | -8.21 | -5.83 | -7.54 | -9.47 | -7.94 | -2.49 | -10.14 | -3.66 | -84.44 |
| 21–23 Ecuador (02–04 UTC) | -4.53 | -6.18 | -5.23 | -3.99 | -4.42 | -6.11 | -4.56 | -6.94 | -6.88 | -4.80 | -4.21 | -5.08 | -3.23 | -66.18 |
| 23–01 Ecuador (04–06 UTC) | -1.72 | -1.66 | -2.24 | -2.87 | -2.55 | -3.02 | +1.59 | -2.41 | +0.53 | -2.26 | -2.93 | +0.59 | -3.83 | -22.78 |
| 01–03 Ecuador (06–08 UTC) | -3.02 | -1.99 | -4.25 | -3.96 | -1.56 | -0.96 | +0.17 | -3.19 | +1.69 | -2.69 | -2.10 | -0.61 | -2.49 | -24.97 |
| 03–05 Ecuador (08–10 UTC) | -1.35 | -1.29 | -2.08 | -2.17 | -0.74 | -0.89 | +1.26 | +2.52 | -1.55 | -2.22 | -3.14 | -2.00 | -2.77 | -16.41 |
| 05–07 Ecuador (10–12 UTC) | -2.04 | -1.76 | -1.50 | -0.88 | +0.37 | -0.03 | -1.77 | -0.38 | +1.82 | -1.76 | -3.53 | -1.88 | -1.86 | -15.21 |
| 07–09 Ecuador (12–14 UTC) | -2.93 | -3.93 | -3.54 | -2.25 | -0.61 | -2.31 | -3.10 | -1.89 | -6.71 | -5.70 | -3.35 | -8.91 | -4.98 | -50.21 |
| 09–11 Ecuador (14–16 UTC) | -9.68 | -13.72 | -10.52 | -13.65 | -15.87 | -16.18 | -22.54 | -18.38 | -16.87 | -10.76 | -3.34 | -18.93 | -5.31 | -175.73 |
| 11–13 Ecuador (16–18 UTC) | -2.79 | -3.46 | -3.06 | -2.92 | -7.45 | -5.92 | -4.11 | -0.93 | -2.66 | -7.44 | -1.77 | -3.55 | -2.51 | -48.58 |
| 13–15 Ecuador (18–20 UTC) | -2.18 | -1.51 | -4.00 | -3.16 | -2.05 | -3.80 | -8.10 | -2.91 | -4.98 | -1.87 | -2.87 | -2.39 | -1.91 | -41.75 |
| 15–17 Ecuador (20–22 UTC) | -3.44 | -2.59 | -2.59 | -2.15 | -4.17 | -2.33 | -1.95 | -2.14 | -1.74 | -0.38 | -3.68 | +1.32 | -2.78 | -28.61 |
| 17–19 Ecuador (22–00 UTC) | -1.92 | -1.73 | -0.67 | -0.39 | -0.18 | +0.44 | +3.07 | +1.27 | +5.88 | +0.02 | -3.53 | +1.46 | -2.65 | +1.07 |
| 07–10 Ecuador (12–15 UTC) — ventana del dueño | -6.15 | -8.33 | -6.54 | -7.57 | -6.65 | -9.47 | -13.69 | -10.24 | -12.86 | -10.40 | -3.76 | -16.72 | -6.42 | -118.81 |

## referencia: datos pasados — mejores y peores celdas (lun–vie)

**Mejores 5 (descriptivo, puede ser suerte):**
- AVAXUSDT · baseline · 17–19 Ecuador (22–00 UTC): +5.88% neto en 10 operación(es)
- ADAUSDT · baseline · 17–19 Ecuador (22–00 UTC): +3.07% neto en 10 operación(es)
- LINKUSDT · baseline · 03–05 Ecuador (08–10 UTC): +2.52% neto en 10 operación(es)
- AVAXUSDT · ruptura · 01–03 Ecuador (06–08 UTC): +2.27% neto en 6 operación(es)
- AVAXUSDT · baseline · 05–07 Ecuador (10–12 UTC): +1.82% neto en 10 operación(es)

**Peores 5:**
- ADAUSDT · baseline · 09–11 Ecuador (14–16 UTC): -22.54% neto en 10 operación(es)
- DOTUSDT · baseline · 09–11 Ecuador (14–16 UTC): -18.93% neto en 10 operación(es)
- LINKUSDT · baseline · 09–11 Ecuador (14–16 UTC): -18.38% neto en 10 operación(es)
- AVAXUSDT · baseline · 09–11 Ecuador (14–16 UTC): -16.87% neto en 10 operación(es)
- DOTUSDT · baseline · 07–10 Ecuador (12–15 UTC) — ventana del dueño: -16.72% neto en 10 operación(es)

Las tablas y listas son descriptivas: con cientos de celdas, algunas se ven bien por azar. Solo las reglas pre-registradas pueden declarar una hora o mercado mejor.
