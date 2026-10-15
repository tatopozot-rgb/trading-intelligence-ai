# Preregistro: ruptura de volatilidad de Larry Williams (2026-10-15)

Escrito el 2026-10-15, **antes** de correr nada. Las reglas son las del líder (`docs/inteligencia/BOTS_PUBLICOS.md`,
sección "2026-10-15 · Ruptura de volatilidad de Larry Williams"); aquí se fija lo que esas reglas no dicen. Nada
se cambia después de ver el resultado.

## Regla (k = 0,5)

- Velas diarias UTC de Spot de Binance (`data-api.binance.vision`), las 12 monedas de la mesa, largos y cortos.
  Rango de ayer = máximo − mínimo de la vela de ayer.
- Disparo largo = apertura de hoy + 0,5 × rango de ayer; se toca si el máximo de hoy llega. Disparo corto =
  apertura − 0,5 × rango de ayer; se toca si el mínimo de hoy llega. Entrada al precio del disparo con 0,02% de
  deslizamiento en contra; si la apertura ya está más allá del disparo, la entrada es la apertura.
- Salida en la apertura de mañana, con 0,02% de deslizamiento en contra. Comisión 0,05% por lado.
- Financiación: la suma de los pagos reales de ese día UTC (archivo público `data.binance.vision`; sin dato,
  0,01% cada 8 h), sobre el tamaño de la posición: el largo paga si es positiva, el corto cobra.
- Si se tocan los dos disparos en la misma vela, cuenta la peor de las dos operaciones.
- Capital 1.000 USDT al empezar cada año, 1x. Cada posición = un tercio del capital al abrir el día. Si se
  disparan más de 3 monedas, entran las 3 con más volumen en USDT ayer (volumen × cierre de la vela de ayer).

## Dos versiones

- **A, pura:** como arriba.
- **B, con los frenos de la mesa:** régimen b (solo largos, y solo si el cierre diario de ayer de BTC está sobre su
  media de 50 días; si no, ninguna entrada) y sin entradas los días UTC en que cae una decisión FOMC o un dato de
  IPC (fechas de `research_mesa.FOMC_DAYS` y `CPI_DAYS`).

## Sensibilidad (solo informativa)

k = 0,25 y k = 0,75, en las dos versiones. **Nunca se usan para elegir k.**

## Cómo se juzga (fijado ahora)

- Años: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13.
- **Pasa a práctica** solo si su neto/caída (caída con el capital diario) supera al de la mesa de práctica en
  **los dos años**, con k = 0,5. La referencia que fijó el líder es 1,67 (2024-25) y −0,21 (2025-26). Se informa
  también contra la mesa de práctica re-medida con las reglas de hoy (sin inclinación por sentimiento, con freno
  de eventos: 1,73 y 0,20, `docs/research/saturado/`); si las dos comparaciones no coinciden, se dice.
- Menos de 100 operaciones en un año: "muestra corta".
- Se compara también con comprar y mantener BTC. El dinero real no cambia por este estudio.
