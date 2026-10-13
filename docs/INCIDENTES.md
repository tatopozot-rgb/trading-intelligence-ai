# Registro de incidentes

Each failure gets one entry: what happened, root cause, fix, test. The Director de Operaciones reviews this file weekly.
Times are UTC.

| Fecha | Qué pasó | Causa raíz | Arreglo | Prueba |
|-------|----------|------------|---------|--------|
| 2026-10-13 | Small Spot coins left below Binance's minimum: the owner could not sell them or turn them into USDT. | No review of exchange minimums before buying on Spot. | USDT-only rule; Compliance agent reviews minimums and dust before any real-money plan (§103). | `.claude/agents/compliance.md` |
| 2026-10-13 | XM: the regime brake never acted. | It asked XM for `BTCUSDT`; XM names it `BTCUSD`, so the read failed and "no data" meant "no brake". | `XmBroker.candles` maps the name (PR #59). | `test_the_regime_brake_reads_btc_under_xms_own_name` |
| 2026-10-13 | XM: MT5 refused entries with "No money" (OILCash 20:07 and 20:22, BTCUSD 22:41). | Size was capped by 2x effective leverage only; a 1:1 account cannot carry that margin. | Size also capped by the agent's share of free margin (PR #62). | `test_size_lots_stays_inside_the_margin_a_1_to_1_account_can_carry` |
| 2026-10-13 | The 3D city showed an empty page. | `node_modules/three` was never installed (`npm ci` missing). | City paused by the owner; the artifact is the city. | — |

| 2026-10-13 | Design flaw found in review: a brake that could not read its data acted as "no brake" (fail open). | Same root as the XM regime incident. | The regime brake now keeps its last reading and, with none, blocks new entries (fail closed); open positions keep their stops (§109). | `test_without_btc_data_the_brake_fails_closed` |
