# Reporte de trading — INICIO

- sesión `20261010T023604` · modo **REAL** · perfil **tendencia_rango** · temporalidad 1m · estado **RUNNING**
- capital asignado: **32.00 USDT** · valor actual: **31.99** · resultado: **-0.01 USDT** (realizado +0.00, abierto -0.01) · comisiones 0.01
- límite de pérdida: 14.40 USDT (45%) · aviso a 12.40 USDT · máximo por posición 40% · posiciones abiertas máx. 3
- mercados vigilados: ADAUSDT AVAXUSDT BNBUSDT BTCUSDT DOGEUSDT DOTUSDT ETHUSDT LINKUSDT LTCUSDT SOLUSDT TRXUSDT XRPUSDT
- monedas operadas: SOLUSDT · ventas 0 (ganadoras 0)

## Posiciones abiertas

| moneda | cantidad | costo | valor | resultado |
|---|---|---|---|---|
| SOLUSDT | 0.08991000 | 9.89 | 9.88 | -0.01 |

## Operaciones

| hora | lado | moneda | cantidad | USDT | comisión | resultado | motivo |
|---|---|---|---|---|---|---|---|
| 2026-10-10T02:36:39+00:00 | BUY | SOLUSDT | 0.08991000 | 9.89 | 0.0099 |  | tendencia_rango:OPEN |

## Cómo se tomaron las decisiones

Decisiones del motor por vela (todas las monedas): NO_SIGNAL 8, NO_TRADE 3, ENTRY_SUBMITTED 1

| moneda | vela | régimen | decisión |
|---|---|---|---|
| ADAUSDT | 2026-10-10T02:35:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| AVAXUSDT | 2026-10-10T02:35:00+00:00 | BREAKOUT_UP | NO_SIGNAL |
| BNBUSDT | 2026-10-10T02:35:00+00:00 | RANGE | NO_SIGNAL |
| BTCUSDT | 2026-10-10T02:35:00+00:00 | TREND_UP | NO_SIGNAL |
| DOGEUSDT | 2026-10-10T02:35:00+00:00 | RANGE | NO_SIGNAL |
| DOTUSDT | 2026-10-10T02:35:00+00:00 | NO_EDGE | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| ETHUSDT | 2026-10-10T02:35:00+00:00 | RANGE | NO_SIGNAL |
| LINKUSDT | 2026-10-10T02:35:00+00:00 | BREAKOUT_UP | NO_SIGNAL |
| LTCUSDT | 2026-10-10T02:35:00+00:00 | RANGE | NO_SIGNAL |
| SOLUSDT | 2026-10-10T02:35:00+00:00 | BREAKOUT_UP | ENTRY_SUBMITTED |
| TRXUSDT | 2026-10-10T02:35:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| XRPUSDT | 2026-10-10T02:35:00+00:00 | RANGE | NO_SIGNAL |

## Agentes

Usados: Detector de régimen, Estrategia de tendencia (cruce de medias), Estrategia de rango (Bollinger), Motor de riesgo (veto), Guardia de pérdida del dueño, Ejecución real (Binance Spot).
No usados en esta sesión: Ejecución simulada (SHADOW, sin órdenes), Posiciones del líder leídas en la app, Revisión de top traders, Seguidor de copias (simulación).
Todas las órdenes salen del operador; el motor de riesgo y la guardia de pérdida pueden vetarlas.

## Eventos

- 2026-10-10T02:36:42+00:00 **PLAN**: SOLUSDT: stop -3.09% · meta +1.85% · rango · stop del motor; rango: meta cercana, en la resistencia
