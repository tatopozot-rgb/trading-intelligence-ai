# Preregistro: salida por régimen sobre la mesa actual (2026-10-20)

Escrito el 2026-10-20, **antes** de correr nada. Encargo del líder (teoría del tema 2, segunda vuelta,
`docs/inteligencia/2026-10-20.md`). Las filas quedan "pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo
commit. Datos públicos, sin cuenta, sin clave y sin órdenes. No se toca `config/` ni `live/`.

## La mesa que se mide

La mesa de `docs/research/real/` y `docs/research/freno_caida/`: `research_mesa.replay` en velas de 5 minutos con
las 12 monedas, riesgo de 1% a 15% según la calidad, 3 posiciones, freno de régimen b para entrar (BTC sobre su media
de 50 días: solo largos) y freno de eventos de ±2 horas. Costos de Binance Futuros (0,05% por lado, 0,02% de
deslizamiento, financiación real) y mínimos por orden. Bloques de 30 días encadenados, 1.000 USDT. 1x
(`SIZINGS[0]`) y 3x (`SIZINGS[4]`).

## Lo que se prueba

- **Con salida por régimen:** cuando el cierre diario de BTC queda bajo su media de 50 días, los largos abiertos se
  cierran en la primera vela de 5 minutos del día siguiente (a su cierre, ≈ la apertura del día).
  Es `close_on_gate=True` en `research_mesa.replay`.
- **Referencia (no cuenta):** el freno solo impide entrar; los abiertos siguen hasta su stop, su meta o la señal
  contraria (`close_on_gate=False`).

**Nota antes de correr:** la mesa medida en `real/` y en `freno_caida/` ya usaba `close_on_gate=True`, y
`live/two_way.py` (`_decide`, desde el 13-10) ya cierra los largos cuando el freno está activo. Esta prueba mide si esa
salida vale la pena contra esperar el stop. Las filas con salida coinciden en reglas con las referencias "sin freno"
de `freno_caida/`, que no contaron; aquí cuentan por primera vez.

## Filas

Decisorias (N llega a 288, con las 6 del MACD del mismo commit): 1. 1x con salida por régimen. 2. 3x con salida por
régimen.

Referencias (no cuentan): 1x y 3x sin salida por régimen.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 288 y V = 1/T, sobre los rendimientos de días naturales.

Pasa solo con los dos. Se informa también el cambio contra la referencia (neto, caída, neto/caída, operaciones
cerradas por régimen). El dinero real no cambia por este estudio.
