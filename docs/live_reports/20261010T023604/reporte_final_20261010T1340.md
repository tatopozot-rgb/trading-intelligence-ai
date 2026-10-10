# Reporte de trading — FINAL

- sesión `20261010T023604` · modo **REAL** · perfil **tendencia_rango** · temporalidad 1m · estado **STOPPED**
- capital asignado: **37.78 USDT** · valor actual: **37.73** · resultado: **-0.05 USDT** (realizado -0.06, abierto +0.01) · comisiones 0.04
- límite de pérdida: 17.00 USDT (45%) · aviso a 15.00 USDT · máximo por posición 40% · posiciones abiertas máx. 3
- mercados vigilados: ADAUSDT AVAXUSDT BNBUSDT BTCUSDT DOGEUSDT DOTUSDT ETHUSDT LINKUSDT LTCUSDT SOLUSDT TRXUSDT XRPUSDT
- monedas operadas: BTCUSDT, ETHUSDT, SOLUSDT · ventas 2 (ganadoras 0)

## Posiciones abiertas

| moneda | cantidad | costo | valor | resultado |
|---|---|---|---|---|
| BTCUSDT | 0.00006993 | 5.78 | 5.79 | +0.01 |
| ETHUSDT | 0.00009530 | 0.24 | 0.24 | +0.00 |
| SOLUSDT | 0.00091000 | 0.10 | 0.10 | -0.00 |

## Operaciones

| hora | lado | moneda | cantidad | USDT | comisión | resultado | motivo |
|---|---|---|---|---|---|---|---|
| 2026-10-10T02:36:39+00:00 | BUY | SOLUSDT | 0.08991000 | 9.89 | 0.0099 |  | tendencia_rango:OPEN |
| 2026-10-10T02:37:46+00:00 | BUY | BTCUSDT | 0.00006993 | 5.78 | 0.0000 |  | ADOPTED |
| 2026-10-10T02:41:36+00:00 | BUY | ETHUSDT | 0.00469530 | 11.72 | 0.0117 |  | tendencia_rango:OPEN |
| 2026-10-10T02:56:34+00:00 | SELL | ETHUSDT | 0.00460000 | 11.45 | 0.0115 | -0.03 | tendencia_rango:CLOSE |
| 2026-10-10T03:01:34+00:00 | SELL | SOLUSDT | 0.08900000 | 9.77 | 0.0098 | -0.02 | tendencia_rango:CLOSE |

## Cómo se tomaron las decisiones

Decisiones del motor por vela (todas las monedas): NO_SIGNAL 174, HOLDING 62, NO_TRADE 60, ENTRY_SUBMITTED 2, RISK_REJECTED 2

| moneda | vela | régimen | decisión |
|---|---|---|---|
| ADAUSDT | 2026-10-10T13:37:00+00:00 | BREAKOUT_UP | NO_SIGNAL |
| AVAXUSDT | 2026-10-10T13:37:00+00:00 | RANGE | NO_SIGNAL |
| BNBUSDT | 2026-10-10T13:37:00+00:00 | TREND_UP | NO_SIGNAL |
| BTCUSDT | 2026-10-10T13:37:00+00:00 | NO_EDGE | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| DOGEUSDT | 2026-10-10T13:37:00+00:00 | RANGE | NO_SIGNAL |
| DOTUSDT | 2026-10-10T13:37:00+00:00 | TREND_UP | NO_SIGNAL |
| ETHUSDT | 2026-10-10T13:37:00+00:00 | TREND_UP | NO_SIGNAL |
| LINKUSDT | 2026-10-10T13:37:00+00:00 | BREAKOUT_UP | NO_SIGNAL |
| LTCUSDT | 2026-10-10T13:37:00+00:00 | None | HOLDING |
| SOLUSDT | 2026-10-10T13:37:00+00:00 | RANGE | NO_SIGNAL |
| TRXUSDT | 2026-10-10T13:37:00+00:00 | None | HOLDING |
| XRPUSDT | 2026-10-10T13:37:00+00:00 | None | HOLDING |

## Agentes

Usados: Detector de régimen, Estrategia de tendencia (cruce de medias), Estrategia de rango (Bollinger), Motor de riesgo (veto), Guardia de pérdida del dueño, Ejecución real (Binance Spot).
No usados en esta sesión: Ejecución simulada (SHADOW, sin órdenes), Posiciones del líder leídas en la app, Revisión de top traders, Seguidor de copias (simulación).
Todas las órdenes salen del operador; el motor de riesgo y la guardia de pérdida pueden vetarlas.

## Eventos

- 2026-10-10T02:36:42+00:00 **PLAN**: SOLUSDT: stop -3.09% · meta +1.85% · rango · stop del motor; rango: meta cercana, en la resistencia
- 2026-10-10T02:37:46+00:00 **OWNER**: el dueño asignó 5.78 USDT más (capital 37.78)
- 2026-10-10T02:41:37+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.78
- 2026-10-10T02:41:40+00:00 **PLAN**: ETHUSDT: stop -3.07% · meta +1.84% · rango · stop del motor; rango: meta cercana, en la resistencia
- 2026-10-10T03:01:36+00:00 **SKIP**: ETHUSDT: DUST_BELOW_EXCHANGE_MINIMUM:0.24
- 2026-10-10T03:06:21+00:00 **SKIP**: SOLUSDT: DUST_BELOW_EXCHANGE_MINIMUM:0.10
- 2026-10-10T03:11:17+00:00 **SKIP**: TRXUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T03:16:13+00:00 **SKIP**: ADAUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T03:22:07+00:00 **SKIP**: XRPUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T03:56:40+00:00 **SKIP**: LINKUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T04:06:31+00:00 **SKIP**: BNBUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T04:42:08+00:00 **SKIP**: AVAXUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T04:47:06+00:00 **SKIP**: DOTUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T07:46:39+00:00 **SKIP**: BTCUSDT: BELOW_EXCHANGE_MINIMUM:0.00<5.00000000
- 2026-10-10T07:56:29+00:00 **SKIP**: ETHUSDT: NO_ADDING_TO_A_LOSING_POSITION
- 2026-10-10T08:06:19+00:00 **SKIP**: ETHUSDT: BELOW_EXCHANGE_MINIMUM:0.00<5.00000000
- 2026-10-10T08:31:52+00:00 **SKIP**: DOGEUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T10:46:34+00:00 **SKIP**: LTCUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T12:26:36+00:00 **RESUMED**: operador reanudado tras una interrupción
- 2026-10-10T12:27:22+00:00 **SKIP**: ETHUSDT: DUST_BELOW_EXCHANGE_MINIMUM:0.24
- 2026-10-10T12:27:22+00:00 **SKIP**: SOLUSDT: DUST_BELOW_EXCHANGE_MINIMUM:0.10
- 2026-10-10T12:27:22+00:00 **SKIP**: BTCUSDT: BELOW_EXCHANGE_MINIMUM:0.00<5.00000000
- 2026-10-10T12:27:22+00:00 **SKIP**: LTCUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T12:30:10+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.79
- 2026-10-10T12:45:11+00:00 **SKIP**: XRPUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T13:20:11+00:00 **SKIP**: TRXUSDT: MAX_OPEN_POSITIONS
- 2026-10-10T13:40:29+00:00 **FIN**: OWNER_STOP: parada ordenada por el dueño
