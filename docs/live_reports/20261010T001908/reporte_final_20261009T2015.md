# Reporte de trading — FINAL

- sesión `20261009T182043` · modo **REAL** · perfil **tendencia_rango** · temporalidad 4h · estado **STOPPED**
- capital asignado: **37.77 USDT** · valor actual: **37.76** · resultado: **-0.01 USDT** (realizado +0.00, abierto -0.01) · comisiones 0.00
- límite de pérdida: 17.00 USDT (45%) · aviso a 15.00 USDT · máximo por posición 40% · posiciones abiertas máx. 3
- mercados vigilados: ADAUSDT AVAXUSDT BNBUSDT BTCUSDT DOGEUSDT DOTUSDT ETHUSDT LINKUSDT LTCUSDT SOLUSDT TRXUSDT XRPUSDT
- monedas operadas: BTCUSDT · ventas 0 (ganadoras 0)

## Posiciones abiertas

| moneda | cantidad | costo | valor | resultado |
|---|---|---|---|---|
| BTCUSDT | 0.00006993 | 5.77 | 5.76 | -0.01 |

## Operaciones

| hora | lado | moneda | cantidad | USDT | comisión | resultado | motivo |
|---|---|---|---|---|---|---|---|
| 2026-10-09T18:22:30+00:00 | BUY | BTCUSDT | 0.00006993 | 5.77 | 0.0000 |  | ADOPTED |

## Cómo se tomaron las decisiones

Decisiones del motor por vela (todas las monedas): NO_TRADE 21, NO_SIGNAL 3

| moneda | vela | régimen | decisión |
|---|---|---|---|
| ADAUSDT | 2026-10-09T16:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| AVAXUSDT | 2026-10-09T16:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| BNBUSDT | 2026-10-09T16:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| BTCUSDT | 2026-10-09T16:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| DOGEUSDT | 2026-10-09T16:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| DOTUSDT | 2026-10-09T16:00:00+00:00 | NO_EDGE | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| ETHUSDT | 2026-10-09T16:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| LINKUSDT | 2026-10-09T16:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| LTCUSDT | 2026-10-09T16:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| SOLUSDT | 2026-10-09T16:00:00+00:00 | BREAKOUT_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| TRXUSDT | 2026-10-09T16:00:00+00:00 | RANGE | NO_SIGNAL |
| XRPUSDT | 2026-10-09T16:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |

## Agentes

Usados: Detector de régimen, Estrategia de tendencia (cruce de medias), Estrategia de rango (Bollinger), Motor de riesgo (veto), Guardia de pérdida del dueño, Ejecución real (Binance Spot).
No usados en esta sesión: Ejecución simulada (SHADOW, sin órdenes), Posiciones del líder leídas en la app, Revisión de top traders, Seguidor de copias (simulación).
Todas las órdenes salen del operador; el motor de riesgo y la guardia de pérdida pueden vetarlas.

## Eventos

- 2026-10-09T18:22:30+00:00 **OWNER**: el dueño asignó 5.77 USDT más (capital 37.77)
- 2026-10-09T20:01:28+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.76
- 2026-10-09T20:15:53+00:00 **FIN**: OWNER_STOP: parada ordenada por el dueño
