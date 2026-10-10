# Reporte de trading — FINAL

- sesión `20261009T201607` · modo **REAL** · perfil **tendencia_rango** · temporalidad 20m · estado **STOPPED**
- capital asignado: **37.76 USDT** · valor actual: **37.78** · resultado: **+0.02 USDT** (realizado +0.00, abierto +0.02) · comisiones 0.00
- límite de pérdida: 16.99 USDT (45%) · aviso a 14.99 USDT · máximo por posición 40% · posiciones abiertas máx. 3
- mercados vigilados: ADAUSDT AVAXUSDT BNBUSDT BTCUSDT DOGEUSDT DOTUSDT ETHUSDT LINKUSDT LTCUSDT SOLUSDT TRXUSDT XRPUSDT
- monedas operadas: BTCUSDT · ventas 0 (ganadoras 0)

## Posiciones abiertas

| moneda | cantidad | costo | valor | resultado |
|---|---|---|---|---|
| BTCUSDT | 0.00006993 | 5.76 | 5.78 | +0.02 |

## Operaciones

| hora | lado | moneda | cantidad | USDT | comisión | resultado | motivo |
|---|---|---|---|---|---|---|---|
| 2026-10-09T20:19:37+00:00 | BUY | BTCUSDT | 0.00006993 | 5.76 | 0.0000 |  | ADOPTED |

## Cómo se tomaron las decisiones

Decisiones del motor por vela (todas las monedas): NO_SIGNAL 112, NO_TRADE 19, RISK_REJECTED 1

| moneda | vela | régimen | decisión |
|---|---|---|---|
| ADAUSDT | 2026-10-09T23:00:00+00:00 | BREAKOUT_UP | NO_SIGNAL |
| AVAXUSDT | 2026-10-09T23:00:00+00:00 | RANGE | NO_SIGNAL |
| BNBUSDT | 2026-10-09T23:00:00+00:00 | BREAKOUT_UP | NO_SIGNAL |
| BTCUSDT | 2026-10-09T23:00:00+00:00 | RANGE | NO_SIGNAL |
| DOGEUSDT | 2026-10-09T23:00:00+00:00 | RANGE | NO_SIGNAL |
| DOTUSDT | 2026-10-09T23:00:00+00:00 | BREAKOUT_UP | NO_SIGNAL |
| ETHUSDT | 2026-10-09T23:00:00+00:00 | RANGE | NO_SIGNAL |
| LINKUSDT | 2026-10-09T23:00:00+00:00 | NO_EDGE | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| LTCUSDT | 2026-10-09T23:00:00+00:00 | RANGE | NO_SIGNAL |
| SOLUSDT | 2026-10-09T23:00:00+00:00 | RANGE | NO_SIGNAL |
| TRXUSDT | 2026-10-09T23:00:00+00:00 | BREAKOUT_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| XRPUSDT | 2026-10-09T23:00:00+00:00 | RANGE | NO_SIGNAL |

## Agentes

Usados: Detector de régimen, Estrategia de tendencia (cruce de medias), Estrategia de rango (Bollinger), Motor de riesgo (veto), Guardia de pérdida del dueño, Ejecución real (Binance Spot).
No usados en esta sesión: Ejecución simulada (SHADOW, sin órdenes), Posiciones del líder leídas en la app, Revisión de top traders, Seguidor de copias (simulación).
Todas las órdenes salen del operador; el motor de riesgo y la guardia de pérdida pueden vetarlas.

## Eventos

- 2026-10-09T20:19:37+00:00 **OWNER**: el dueño asignó 5.76 USDT más (capital 37.76)
- 2026-10-09T20:23:05+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.77
- 2026-10-09T20:42:30+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.76
- 2026-10-09T21:02:17+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.77
- 2026-10-09T21:22:10+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.78
- 2026-10-09T21:42:26+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.77
- 2026-10-09T22:02:24+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.77
- 2026-10-09T22:22:01+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.77
- 2026-10-09T22:42:39+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.78
- 2026-10-09T23:02:57+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.78
- 2026-10-09T23:22:37+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.78
- 2026-10-09T23:24:39+00:00 **FIN**: OWNER_STOP: parada ordenada por el dueño
