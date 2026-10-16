# Preregistro: RSI-2 de Larry Connors en las 12 monedas, y Sharpe deflactado de Londres en oro (2026-10-16)

Escrito el 2026-10-16, **antes** de correr nada. Las reglas del RSI-2 son las del líder
(`docs/inteligencia/BOTS_PUBLICOS.md`, sección "2026-10-16 · RSI-2 de Larry Connors"); aquí se fija lo que esas
reglas no dicen. La segunda parte fija cómo se calcula el Sharpe deflactado (lección del tema 6,
`docs/inteligencia/2026-10-16.md`). Nada se cambia después de ver el resultado.

## Parte 1 · RSI-2

### Regla (umbral 10)

- Velas diarias UTC de Spot de Binance (`data-api.binance.vision`), las 12 monedas de la mesa. Solo largos.
- RSI de 2 días sobre el cierre, con la media de Wilder (exponencial con α = 1/2). Media de 200 y de 5 días: media
  simple de los cierres, incluido el del día.
- **Señal** al cierre del día t: cierre > media de 200 y RSI-2 < 10. **Entrada** en la apertura de t+1, con 0,02%
  de deslizamiento en contra. Si la apertura de t+1 falta, la señal se pierde.
- **Salida:** al primer cierre (desde el mismo día de la entrada) que quede sobre la media de 5, se sale en la
  apertura siguiente con 0,02% de deslizamiento en contra. Sin stop y sin tope de días.
- Comisión 0,05% por lado. Financiación: la suma de los pagos reales de cada día UTC que la posición está abierta
  (archivo público `data.binance.vision`; sin dato, 0,01% cada 8 h), sobre el tamaño: el largo paga si es positiva.
- Capital 1.000 USDT al empezar cada año, 1x. Máximo 3 posiciones; cada una con un tercio del capital marcado al
  cierre del día de la señal. Una moneda ya abierta no se vuelve a comprar. Si hay más señales que huecos libres,
  entran las de RSI-2 más bajo.
- Las señales cuentan solo dentro del año. Lo que siga abierto al cierre del último día del año se cierra a ese
  cierre, con deslizamiento y comisión.
- La caída se mide sobre el capital marcado a mercado en cada cierre diario.

### Dos versiones

- **A, pura:** como arriba.
- **B, con los frenos de la mesa:** régimen b (solo se abre si el cierre de BTC del día de la señal está sobre la
  media de sus últimos 50 cierres) y sin entradas si el día de la entrada (t+1) es día UTC de decisión FOMC o de
  dato de IPC (`research_mesa.FOMC_DAYS` y `CPI_DAYS`). Los frenos no fuerzan salidas.

### Sensibilidad (solo informativa, nunca decide)

- Umbral 5 en las dos versiones.
- Espejo en corto, versión A: cierre < media de 200 y RSI-2 > 90 → corto; sale al primer cierre bajo la media de 5;
  el corto cobra la financiación positiva. Entran los de RSI-2 más alto.

### Cómo se juzga (fijado ahora)

- Años: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13.
- **Pasa a práctica** solo si su neto/caída, con umbral 10, supera al de la mesa de práctica en **los dos años**
  (referencia del líder: 1,67 y −0,21). Se informa también contra la mesa re-medida (1,73 y 0,20,
  `docs/research/saturado/`); si las dos comparaciones no coinciden, se dice.
- Menos de 100 operaciones en un año: "muestra corta".
- Se informa la peor operación de cada versión y año, los días medios abiertos y comprar y mantener BTC.
- El dinero real no cambia por este estudio.

## Parte 2 · Sharpe deflactado de la ruptura de Londres en oro (2025-26)

- **Número de pruebas N:** el total del registro único `docs/research/REGISTRO_PRUEBAS.md`, contado desde el
  2026-10-12 **antes** de esta corrida e incluyendo las 5 filas de RSI-2 de este estudio (decisorias y de
  sensibilidad; la regla de conteo está en el registro). Se informa también con N = solo las decisorias, y con N = 1
  (sin deflactar) como referencia.
- **Datos:** la misma corrida de `research_oro` (PAXGUSDT sin fines de semana, costes base), año 2025-10-13 →
  2026-10-13. Rendimiento diario = cambio del capital marcado entre el último cierre de 1 h de cada día hábil.
- **Fórmula** (Bailey y López de Prado, 2014), con el Sharpe por día SR, T días, asimetría γ3 y curtosis γ4 (no
  excesiva) de los rendimientos diarios:
  - SR0 = √V · ((1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e))), con γ = 0,5772 (Euler-Mascheroni).
  - DSR = Φ((SR − SR0)·√(T − 1) / √(1 − γ3·SR + (γ4 − 1)/4·SR²)).
- **V (varianza de los Sharpe entre pruebas):** principal = 1/T, la varianza del Sharpe estimado de una estrategia
  sin ventaja. Sensibilidad: la varianza real de los Sharpe diarios de las 12 filas de `research_oro` en 2025-26
  (3 estrategias × 2 activos × costes base y ×2), medida en la misma corrida.
- **Listón:** DSR ≥ 0,95 (95% de confianza en que el Sharpe real es mayor que cero, ya descontadas las pruebas).
  Es un segundo listón, no reemplaza el de los dos años. Londres en oro ya no pasó el de los dos años; esto mide
  cuánto se puede creer su año bueno.
