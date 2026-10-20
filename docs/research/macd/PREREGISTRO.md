# Preregistro: cruce del MACD en BTC y ETH diario (2026-10-20)

Escrito el 2026-10-20, **antes** de correr nada. Las reglas las fijó el líder en `docs/inteligencia/BOTS_PUBLICOS.md`
(sección 2026-10-20, PR #112). Aquí solo se fija cómo se simulan. Las filas quedan "pendiente" en
`docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Datos públicos de Binance, sin cuenta, sin clave y sin
órdenes. No se toca `config/` ni `live/`.

## Indicador (12/26/9 fijos, no se afinan)

- MACD = media exponencial de 12 cierres diarios menos la de 26 (`ewm(span, adjust=False)`). Señal = media
  exponencial de 9 del MACD. Se calcula desde 2023-10-01, así que los dos años arrancan con el indicador asentado.

## Reglas

1. **Compra:** el cierre del día en que el MACD pasa de estar en o bajo la señal a quedar sobre ella. Se entra en la
   apertura del día siguiente.
2. **Venta:** el cierre del día en que el MACD pasa de estar en o sobre la señal a quedar bajo ella. Se sale en la
   apertura del día siguiente.
3. Solo compras. Una posición a la vez por moneda. Un cruce que llega con la posición ya abierta (o ya cerrada) no
   hace nada.
4. Costos de la mesa: 0,05% de comisión y 0,02% de deslizamiento por lado. Financiación real del perpetuo por cada
   día con la posición abierta.
5. Velas diarias UTC del contado de Binance (BTCUSDT, ETHUSDT). 1.000 USDT al empezar cada año. Juntas: dos cuentas
   de 500 USDT, una por moneda. Lo abierto al final del año se cierra al último cierre.

## Dos versiones

- **A, tal cual:** 100% del capital de la moneda a 1x, sin stop.
- **B, con los frenos de la mesa:**
  - Stop de la mesa: `strategy.exit_plan.plan_exits` sobre las últimas 300 velas diarias cerradas, con el precio de
    entrada. Queda fijo. Se llena en el stop, o en la apertura si el día abrió por debajo.
  - Tamaño: 2% del capital de la moneda en riesgo hasta el stop, con tope de 1x.
  - Freno de mercado (régimen b): solo se entra si el cierre de ayer de BTC está sobre su media de 50 días. Si deja
    de estarlo, el largo se cierra en la apertura siguiente.
  - Freno de eventos: sin entradas el día UTC de una decisión FOMC o un dato de IPC.
  - La salida por cruce bajista sigue igual.

## Filas

Decisorias (N pasa de 280 a 286):

1. A, BTC. 2. A, ETH. 3. A, juntas. 4. B, BTC. 5. B, ETH. 6. B, juntas.

Sensibilidad (no cuentan): 7. A juntas, costos ×2. 8. B juntas, costos ×2.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 288 (las 286 de aquí más las 2 decisorias de la salida por régimen,
   preregistradas en el mismo commit) y V = 1/T, sobre rendimientos de días naturales.

Pasa solo con los dos. Menos de 10 operaciones en un año: "muestra corta". Se informa también contra mantener BTC y
ETH. El dinero real no cambia por este estudio.
