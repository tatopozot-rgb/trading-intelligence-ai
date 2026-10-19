# Preregistro: freno por caída de la cuenta sobre la mesa actual (2026-10-19)

Escrito el 2026-10-19, **antes** de correr nada. Encargo del líder (rutina de inteligencia del 19-10, teoría del
tema 1, segunda vuelta, `docs/inteligencia/2026-10-19.md`). Las filas quedan "pendiente" en
`docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Datos públicos, sin cuenta, sin clave y sin órdenes. No se
toca `config/` ni `live/`.

## La mesa que se mide (sin cambios)

La mesa actual, como en `docs/research/real/`: `research_mesa.replay` en velas de 5 minutos con las 12 monedas.

- Riesgo de 1% a 15% según la calidad, 3 posiciones.
- Freno de régimen b (BTC sobre su media de 50 días: solo largos; si no, fuera) y freno de eventos de ±2 horas.
- Costos de Binance Futuros: 0,05% por lado, 0,02% de deslizamiento, financiación real, mínimos por orden.
- Bloques de 30 días encadenados: cada uno empieza con el capital con que terminó el anterior. 1.000 USDT.
- **1x:** 50% por posición. **3x:** apalancamiento 3 y 150% por posición (`research_mesa.SIZINGS[4]`).

## El freno (solo baja el riesgo, nunca lo sube)

- El máximo es el capital más alto alcanzado (al cierre de cada vela de 5 minutos), arrastrado entre bloques.
- Caída de 10% o más desde el máximo: el riesgo de cada entrada nueva se multiplica por 0,5. Los topes de tamaño no
  cambian.
- Caída de 20% o más: no hay entradas nuevas. Las abiertas siguen con su stop y su meta.
- **La revisión del líder:** una pausa dura hasta el inicio del bloque de 30 días siguiente. Ahí el máximo vuelve a
  ser el capital de ese momento (el líder revisó y es el nuevo punto de partida). Sin pausa no hay reinicio.

## Filas

Decisorias (N llega a 280, con las 6 de Ichimoku del mismo commit):

1. Mesa 1x con freno por caída. 2. Mesa 3x con freno por caída.

Sensibilidad (no cuentan): 3. 1x con pausa sin reinicio (la pausa no termina nunca). 4. 3x con pausa sin reinicio.

Referencias (no cuentan, regla de conteo): mesa 1x y 3x sin freno, mismos bloques.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 280 y V = 1/T, sobre los rendimientos de días naturales.

Pasa solo con los dos. Se informa también cuánto cambia cada año contra la misma mesa sin freno (neto, caída y
neto/caída). El dinero real no cambia por este estudio.
