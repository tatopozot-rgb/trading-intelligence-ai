# Preregistro: TTM Squeeze de John Carter en BTC y ETH diario (2026-10-21)

Escrito el 2026-10-21, **antes** de correr nada. Las reglas las fijó el líder en `docs/inteligencia/BOTS_PUBLICOS.md`
(sección 2026-10-21, PR #118). Aquí solo se fija cómo se simulan. Las filas quedan "pendiente" en
`docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Datos públicos de Binance, sin cuenta, sin clave y sin
órdenes. No se toca `config/` ni `live/`.

## Indicador (parámetros de Carter, no se afinan)

- Bollinger: media simple de 20 cierres ± 2 desviaciones típicas de esos 20 cierres (poblacional, ddof = 0).
- Keltner: media simple de 20 cierres ± 1,5 × ATR(20). ATR(20) = media simple de 20 días del rango verdadero.
- **Apretón** el día t: banda alta de Bollinger < alta de Keltner **y** banda baja de Bollinger > baja de Keltner.
- **Impulso** el día t: x = cierre − ((máximo de 20 días + mínimo de 20 días)/2 + media de 20 cierres)/2; el impulso es
  el valor ajustado en el último día de la recta de mínimos cuadrados sobre los últimos 20 valores de x.
- Velas desde 2023-10-01, para que el indicador y el stop de la mesa estén asentados.

## Reglas

1. **Compra** al abrir el día siguiente a un cierre t con apretón en t−1, sin apretón en t, impulso(t) > 0 e
   impulso(t) > impulso(t−1).
2. **Venta** al abrir el día siguiente a un cierre t con impulso(t) < impulso(t−1) e impulso(t−1) < impulso(t−2).
3. Solo compras. Una posición a la vez por moneda. Una señal que llega con la posición ya abierta (o cerrada) no
   hace nada.
4. Costos de la mesa: 0,05% de comisión y 0,02% de deslizamiento por lado. Financiación real del perpetuo por cada
   día dentro.
5. Velas diarias UTC del contado de Binance (BTCUSDT, ETHUSDT). 1.000 USDT al empezar cada año. Juntas: dos cuentas
   de 500. Lo abierto al final del año se cierra al último cierre.

## Dos versiones (el mismo simulador del MACD, `research_macd.simulate`)

- **A, tal cual:** 100% del capital de la moneda a 1x, sin stop.
- **B, con los frenos de la mesa:** stop de la mesa (`plan_exits` sobre 300 velas diarias cerradas, fijo), tamaño de
  2% de riesgo con tope de 1x, régimen b (BTC sobre su media de 50 días; si deja de estarlo, se cierra en la
  apertura siguiente) y sin entradas el día UTC de FOMC o IPC.

## Filas

Decisorias (N pasa de 288 a 294): 1. A, BTC. 2. A, ETH. 3. A, juntas. 4. B, BTC. 5. B, ETH. 6. B, juntas.

Sensibilidad (no cuentan): 7. A juntas, costos ×2. 8. B juntas, costos ×2.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 296 (las 294 de aquí más las 2 del riesgo macro, preregistradas en
   el mismo commit) y V = 1/T.

Pasa solo con los dos. Menos de 10 operaciones en un año: "muestra corta" (el líder avisa que habrá pocas). El dinero
real no cambia por este estudio.
