# Preregistro: rebote a la media en mercado lateral, diario y 4 h (2026-10-15)

Escrito el 2026-10-15, **antes** de correr nada. Encargo del líder (2026-10-15): "rebote a la media en mercado
lateral, en diario o 4 h (no 1 h, que ya falló en el PR #46)". Nada se cambia después de ver el resultado.

## En qué se diferencia de lo que ya falló

- **PR #46 (`docs/research/rotacion/rotacion_2026-10-13.md`):** reversión corta en velas de 1 h. Aquí son velas
  diarias y de 4 h, con un filtro que exige que la moneda esté de lado.
- **`BollingerReversion` (2026-10-06):** la misma idea de bandas, pero se probó solo con datos **sintéticos** y
  solo largos. Aquí es con datos reales de Binance, largos y cortos, y con costes.

## Regla (fuente pública)

Reversión con bandas de Bollinger (John Bollinger, *Bollinger on Bollinger Bands*, 2001) filtrada por ADX bajo
(J. Welles Wilder, *New Concepts in Technical Trading Systems*, 1978: ADX bajo 20 = mercado sin tendencia).

- Velas de Spot de Binance (`data-api.binance.vision`), las 12 monedas de la mesa, largos y cortos.
- Indicadores sobre los cierres, por moneda: bandas de Bollinger 20 velas y 2 desviaciones (media simple 20),
  ADX 14 de Wilder y ATR 14, tal como están en `trading_intelligence/analysis/indicators.py`.
- **Lateral:** ADX 14 < 20 en la vela de la señal.
- **Entrada larga:** la vela cierra bajo la banda inferior y está lateral. **Entrada corta:** cierra sobre la
  banda superior y está lateral. Se entra en la apertura de la vela siguiente, con 0,02% de deslizamiento en
  contra.
- **Salida por la media:** el largo sale cuando una vela cierra en o sobre la media de 20; el corto, en o bajo
  ella. Se sale en la apertura siguiente, con 0,02% de deslizamiento en contra.
- **Stop:** 1,5 × ATR 14 de la vela de la señal, desde el precio de entrada. Se revisa con el mínimo (largo) o el
  máximo (corto) de cada vela abierta, también la de entrada. Si la vela abre más allá del stop, sale en la
  apertura. Deslizamiento 0,02% en contra.
- **Salida por tiempo:** si tras 10 velas no salió, sale en la apertura de la vela 11.
- Si en una misma vela se toca el stop y además cierra cruzando la media, cuenta el stop.
- Comisión 0,05% por lado. Financiación: los pagos reales (archivo público `data.binance.vision`; sin dato, 0,01%
  cada 8 h) cuyo momento cae en una vela en la que la posición estaba abierta, sobre el tamaño de la posición: el
  largo paga si es positiva, el corto cobra.
- Capital 1.000 USDT al empezar cada año, 1x, máximo 3 posiciones, una por moneda. Cada posición = un tercio del
  capital realizado al abrir. Si hay más señales que huecos, entran las de más volumen en USDT en la vela de la
  señal (volumen × cierre).

## Dos marcos y dos versiones

- **Marcos:** diario (velas UTC) y 4 h. Se juzgan por separado.
- **A, pura:** como arriba.
- **B, con los frenos de la mesa:** régimen b (solo largos, y solo si el último cierre diario UTC completo de BTC
  está sobre su media de 50 días; si no, ninguna entrada nueva) y sin entradas nuevas en los días UTC en que cae
  una decisión FOMC o un dato de IPC (`research_mesa.FOMC_DAYS` y `CPI_DAYS`). Las posiciones abiertas siguen
  con sus salidas.

## Sensibilidad (solo informativa, nunca para elegir)

ADX < 25 en lugar de 20, y bandas de 2,5 desviaciones en lugar de 2, cada una por separado, en los dos marcos y
las dos versiones.

## Cómo se juzga (fijado ahora)

- Años: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13. Datos desde 2024-06-01 para calentar indicadores.
- Neto/caída con la caída medida sobre el capital marcado a mercado al cierre de cada vela.
- **Pasa a práctica** solo si su neto/caída supera al de la mesa de práctica en **los dos años**, con la regla
  base (ADX < 20, 2 desviaciones). Referencia del líder: 1,67 (2024-25) y −0,21 (2025-26); también contra la mesa
  re-medida con las reglas de hoy, 1,73 y 0,20 (`docs/research/saturado/`). Si las dos comparaciones no
  coinciden, se dice.
- Son 4 intentos (2 marcos × 2 versiones). Con tantos intentos alguno puede pasar por suerte; si solo pasa uno,
  se dice así y no se promueve sin una confirmación hacia adelante en práctica.
- Menos de 100 operaciones en un año: "muestra corta".
- Se compara también con comprar y mantener BTC. El dinero real no cambia por este estudio. No se toca
  `config/`, `live/` ni los límites.
