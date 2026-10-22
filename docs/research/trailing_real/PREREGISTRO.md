# Preregistro: el bot real con trailing desde 2R y sin cierre por señal opuesta (2026-10-22)

Escrito el 2026-10-22, **antes** de correr nada. Encargo del líder: una sola prueba para ir con el estilo de Renato
(pérdida chica, ganancia grande). La fila queda "pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo
commit. Datos públicos, sin cuenta, sin clave y sin órdenes. No se toca `config/` ni `live/`.

## La base: el bot real tal cual (`docs/research/real/`)

`research_mesa.replay` en velas de 5 minutos con las 12 monedas, 31,69 USDT, 1x, riesgo de 1% a 15% según la
calidad, 50% por posición, 3 posiciones, freno de régimen b (solo largos; cierra los largos cuando BTC queda bajo su
media de 50 días) y freno de eventos de ±2 horas. Costos de Binance Futuros (0,05% por lado, 0,02% de
deslizamiento, financiación real) y mínimos por orden. Bloques de 30 días encadenados. Salidas de hoy: stop de la
mesa, meta a 3R, trailing que arranca en +1R a R/2 del precio, y cierre si llega la señal contraria.

## El cambio (dos cosas, nada más)

1. El trailing arranca en **+2R** (antes +1R). La distancia sigue a R/2 y la meta sigue en 3R.
2. **Sin cierre por señal opuesta:** una señal contraria ya no cierra la posición. Sale por stop, meta, trailing,
   freno de régimen o fin de sesión del bloque.

## Filas

Decisoria (N pasa de 296 a 297): 1. Bot real con trailing desde 2R y sin cierre por señal opuesta.

Referencia (no cuenta): el bot real tal cual, mismos bloques.

## Listones (los mismos de siempre)

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 297 y V = 1/T, sobre los rendimientos de días naturales.

Pasa solo con los dos. Se informa también el cambio contra la referencia y cómo cerraron las operaciones (stop,
meta, trailing, régimen). El dinero real no cambia por este estudio: si pasa, decide el líder.
