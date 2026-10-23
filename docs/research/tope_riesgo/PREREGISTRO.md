# Preregistro: tope al riesgo abierto total en la mesa de futuros (2026-10-23)

Escrito el 2026-10-23, **antes** de correr nada. Encargo del líder (teoría, tema 5, `docs/inteligencia/2026-10-23.md`):
en una caída todo se mueve junto, así que tres posiciones del mismo lado son una sola apuesta. La fila queda
"pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Datos públicos, sin cuenta, sin clave y sin
órdenes. No se toca `config/` ni `live/`.

## La base: la mesa de práctica 1x (`docs/research/salida_regimen/`, fila de referencia 1x)

`research_mesa.replay` en velas de 5 minutos con las 12 monedas, 1.000 USDT, 1x, riesgo de 1% a 15% según la
calidad, 50% por posición, 3 posiciones, freno de régimen b (cierra los largos cuando BTC queda bajo su media de 50
días) y freno de eventos de ±2 horas. Costos de Binance Futuros (0,05% por lado, 0,02% de deslizamiento,
financiación real) y mínimos por orden. Bloques de 30 días encadenados. Salidas de la mesa (stop, meta 3R, trailing
desde 1R a R/2, señal contraria).

## La regla (una sola, nada más cambia)

Antes de abrir una posición nueva, se suma el riesgo abierto de las posiciones **del mismo lado**: por cada una,
(entrada − stop actual) × cantidad en compras, (stop actual − entrada) × cantidad en ventas, y 0 si el trailing ya
pasó la entrada (lo que se perdería si todos los stops saltan a la vez). Se divide por el saldo marcado de esa vela.
Si pasa del **2%**, no se abre. Las del otro lado no cuentan. Las posiciones abiertas no se tocan.

## Filas

Decisoria (N pasa a 301, junto con las 3 del Parabolic SAR del mismo commit): 1. Mesa de práctica 1x con tope de 2%
al riesgo abierto del mismo lado.

Referencia (no cuenta): la misma mesa sin tope, mismos bloques.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 301 y V = 1/T.

Pasa solo con los dos. Se informa también el cambio contra la referencia y cuántas entradas frenó el tope. El
dinero real no cambia por este estudio: si pasa, decide el líder.
