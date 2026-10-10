# Reporte de trading — FINAL

- sesión `20261010T022607` · modo **REAL** · perfil **tendencia_rango** · temporalidad 1m · estado **STOPPED**
- capital asignado: **37.56 USDT** · valor actual: **37.53** · resultado: **-0.03 USDT** (realizado -0.02, abierto -0.00) · comisiones 0.01
- límite de pérdida: 16.90 USDT (45%) · aviso a 14.90 USDT · máximo por posición 40% · posiciones abiertas máx. 3
- mercados vigilados: ADAUSDT AVAXUSDT BNBUSDT BTCUSDT DOGEUSDT DOTUSDT ETHUSDT LINKUSDT LTCUSDT SOLUSDT TRXUSDT XRPUSDT
- monedas operadas: AVAXUSDT, BTCUSDT · ventas 1 (ganadoras 0)

## Posiciones abiertas

| moneda | cantidad | costo | valor | resultado |
|---|---|---|---|---|
| AVAXUSDT | 0.00717000 | 0.07 | 0.07 | +0.00 |
| BTCUSDT | 0.00006993 | 5.78 | 5.78 | -0.00 |

## Operaciones

| hora | lado | moneda | cantidad | USDT | comisión | resultado | motivo |
|---|---|---|---|---|---|---|---|
| 2026-10-10T02:27:46+00:00 | BUY | AVAXUSDT | 1.41717000 | 14.78 | 0.0000 |  | ADOPTED |
| 2026-10-10T02:27:48+00:00 | BUY | BTCUSDT | 0.00006993 | 5.78 | 0.0000 |  | ADOPTED |
| 2026-10-10T02:31:35+00:00 | SELL | AVAXUSDT | 1.41000000 | 14.68 | 0.0147 | -0.02 | tendencia_rango:CLOSE |

## Cómo se tomaron las decisiones

Decisiones del motor por vela (todas las monedas): NO_SIGNAL 43, NO_TRADE 17

| moneda | vela | régimen | decisión |
|---|---|---|---|
| ADAUSDT | 2026-10-10T02:29:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| AVAXUSDT | 2026-10-10T02:29:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| BNBUSDT | 2026-10-10T02:29:00+00:00 | RANGE | NO_SIGNAL |
| BTCUSDT | 2026-10-10T02:29:00+00:00 | BREAKOUT_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| DOGEUSDT | 2026-10-10T02:29:00+00:00 | RANGE | NO_SIGNAL |
| DOTUSDT | 2026-10-10T02:29:00+00:00 | TREND_UP | NO_SIGNAL |
| ETHUSDT | 2026-10-10T02:29:00+00:00 | RANGE | NO_SIGNAL |
| LINKUSDT | 2026-10-10T02:29:00+00:00 | RANGE | NO_SIGNAL |
| LTCUSDT | 2026-10-10T02:29:00+00:00 | RANGE | NO_SIGNAL |
| SOLUSDT | 2026-10-10T02:29:00+00:00 | RANGE | NO_SIGNAL |
| TRXUSDT | 2026-10-10T02:29:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| XRPUSDT | 2026-10-10T02:29:00+00:00 | RANGE | NO_SIGNAL |

## Agentes

Usados: Detector de régimen, Estrategia de tendencia (cruce de medias), Estrategia de rango (Bollinger), Motor de riesgo (veto), Guardia de pérdida del dueño, Ejecución real (Binance Spot).
No usados en esta sesión: Ejecución simulada (SHADOW, sin órdenes), Posiciones del líder leídas en la app, Revisión de top traders, Seguidor de copias (simulación).
Todas las órdenes salen del operador; el motor de riesgo y la guardia de pérdida pueden vetarlas.

## Eventos

- 2026-10-10T02:27:46+00:00 **OWNER**: el dueño asignó 14.78 USDT más (capital 31.78)
- 2026-10-10T02:27:48+00:00 **OWNER**: el dueño asignó 5.78 USDT más (capital 37.56)
- 2026-10-10T02:31:37+00:00 **SKIP**: BTCUSDT: DUST_BELOW_EXCHANGE_MINIMUM:5.78
- 2026-10-10T02:35:48+00:00 **FIN**: OWNER_STOP: parada ordenada por el dueño
