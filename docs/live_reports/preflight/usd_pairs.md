# Pares en USD de Binance Spot (consulta pública, sin clave ni órdenes)

Leído por Claude Code local el 2026-10-09 ~02:58 UTC de `GET /api/v3/exchangeInfo?symbol=…` y
`/api/v3/ticker/bookTicker` en `api.binance.com`. Motivo: la billetera Spot del dueño tiene USD
fiat y 0 USDT; el operador solo compra con USDT.

| Símbolo | Estado | Base/Cotización | orderTypes | minNotional | LOT_SIZE paso / mín. | MARKET_LOT_SIZE paso | quoteOrderQty en MARKET | Spot permitido | Compra / venta |
|---|---|---|---|---|---|---|---|---|---|
| USDTUSD | TRADING | USDT/USD | LIMIT, LIMIT_MAKER, MARKET, STOP_LOSS, STOP_LOSS_LIMIT, TAKE_PROFIT, TAKE_PROFIT_LIMIT | 5 | 1 / 1 | 0 | sí | sí | 0,99905 / 0,99907 |
| BTCUSD | TRADING | BTC/USD | los mismos | 5 | 0,00001 / 0,00001 | 0 | sí | sí | 82090,99 / 82149,53 |
| ETHUSD | TRADING | ETH/USD | los mismos | 5 | 0,0001 / 0,0001 | 0 | sí | sí | 2488,53 / 2489,53 |

Notas:
- En USDTUSD el paso de cantidad es 1 USDT entero: una compra MARKET por cantidad deja sin
  convertir la fracción; `quoteOrderQty` permite gastar un importe exacto en USD.
- `MARKET_LOT_SIZE` trae paso 0, así que rige `LOT_SIZE`.
- No se comprobó con una lectura firmada si esta cuenta y esta clave pueden operar estos pares
  (elegibilidad por región); solo que existen y están en TRADING.
- Claude Code local no ejecutó ninguna conversión: su control de permisos bloquea en esta sesión
  las transacciones con dinero real.
