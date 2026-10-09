# Experimento horarios — resumen acumulado

Simulación con datos públicos (PAPER): **sin cuenta, sin claves, sin órdenes reales**. Entradas cada 20 min (velas de 20 min); con posición abierta se revisa la salida cada 3 min (velas de 1 min): stop de la estrategia, su condición de salida y cierre forzado al final de la ventana. 10 USDT por operación, comisión 0.1% por lado + 5 bps. Horas en **Ecuador (UTC−5)**, UTC entre paréntesis. Reglas en `docs/PREREG_HORARIOS.md` (con la Enmienda 1).

Días forward: 0/14 (días hábiles lun–vie: 0/10) · días de referencia: 14

Las reglas se aplican cuando el período forward esté completo (2026-10-10 → 2026-10-23).

## referencia: datos pasados — por día de la semana

| Día | tendencia: n / media % | rango: n / media % | baseline: n / media % |
|---|---|---|---|
| lunes | 12 / -0.859 | 3 / -0.167 | 338 / -0.431 |
| martes | 3 / -0.419 | 5 / -0.117 | 338 / -0.331 |
| miércoles | 2 / -0.359 | · | 338 / -0.493 |
| jueves | 10 / -0.474 | 1 / -0.921 | 338 / -0.497 |
| viernes | 6 / -0.198 | · | 338 / -0.298 |
| sábado (aparte) | 9 / +0.238 | · | 338 / -0.250 |
| domingo (no decide) | 9 / -0.176 | · | 338 / -0.262 |

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
- AVAXUSDT · baseline · 05–07 Ecuador (10–12 UTC): +1.82% neto en 10 operación(es)
- AVAXUSDT · baseline · 01–03 Ecuador (06–08 UTC): +1.69% neto en 10 operación(es)

**Peores 5:**
- ADAUSDT · baseline · 09–11 Ecuador (14–16 UTC): -22.54% neto en 10 operación(es)
- DOTUSDT · baseline · 09–11 Ecuador (14–16 UTC): -18.93% neto en 10 operación(es)
- LINKUSDT · baseline · 09–11 Ecuador (14–16 UTC): -18.38% neto en 10 operación(es)
- AVAXUSDT · baseline · 09–11 Ecuador (14–16 UTC): -16.87% neto en 10 operación(es)
- DOTUSDT · baseline · 07–10 Ecuador (12–15 UTC) — ventana del dueño: -16.72% neto en 10 operación(es)

Las tablas y listas son descriptivas: con cientos de celdas, algunas se ven bien por azar. Solo las reglas pre-registradas pueden declarar una hora o mercado mejor.
