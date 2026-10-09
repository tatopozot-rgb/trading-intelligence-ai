# Reporte de trading — FINAL

- sesión `20261009T032517` · modo **REAL** · perfil **tendencia_rango** · temporalidad 4h · estado **STOPPED**
- capital asignado: **38.00 USDT** · valor actual: **38.00** · resultado: **+0.00 USDT** (realizado +0.00, abierto +0.00) · comisiones 0.00
- límite de pérdida: 17.10 USDT (45%) · aviso a 15.10 USDT · máximo por posición 40% · posiciones abiertas máx. 3
- mercados vigilados: ADAUSDT AVAXUSDT BNBUSDT BTCUSDT DOGEUSDT DOTUSDT ETHUSDT LINKUSDT LTCUSDT SOLUSDT TRXUSDT XRPUSDT
- monedas operadas: ninguna todavía · ventas 0 (ganadoras 0)

## Posiciones abiertas

Ninguna.

## Operaciones

Ninguna todavía.

## Cómo se tomaron las decisiones

Decisiones del motor por vela (todas las monedas): NO_TRADE 41, NO_SIGNAL 7

| moneda | vela | régimen | decisión |
|---|---|---|---|
| ADAUSDT | 2026-10-09T08:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| AVAXUSDT | 2026-10-09T08:00:00+00:00 | NO_EDGE | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| BNBUSDT | 2026-10-09T08:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| BTCUSDT | 2026-10-09T08:00:00+00:00 | TREND_UP | NO_SIGNAL |
| DOGEUSDT | 2026-10-09T08:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| DOTUSDT | 2026-10-09T08:00:00+00:00 | TREND_UP | NO_SIGNAL |
| ETHUSDT | 2026-10-09T08:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| LINKUSDT | 2026-10-09T08:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| LTCUSDT | 2026-10-09T08:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| SOLUSDT | 2026-10-09T08:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |
| TRXUSDT | 2026-10-09T08:00:00+00:00 | RANGE | NO_SIGNAL |
| XRPUSDT | 2026-10-09T08:00:00+00:00 | TREND_DOWN | NO_TRADE:NO_STRATEGY_FOR_REGIME |

## Agentes

Usados: Detector de régimen, Estrategia de tendencia (cruce de medias), Estrategia de rango (Bollinger), Motor de riesgo (veto), Guardia de pérdida del dueño, Ejecución real (Binance Spot).
No usados en esta sesión: Ejecución simulada (SHADOW, sin órdenes), Posiciones del líder leídas en la app, Revisión de top traders, Seguidor de copias (simulación).
Todas las órdenes salen del operador; el motor de riesgo y la guardia de pérdida pueden vetarlas.

## Eventos

- 2026-10-09T14:10:40+00:00 **FIN**: OWNER_STOP: parada ordenada por el dueño
