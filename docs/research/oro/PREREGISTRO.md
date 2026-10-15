# Preregistro: tres estrategias públicas de oro, y las mismas en BTC (2026-10-15)

Escrito el 2026-10-15, **antes** de correr nada. Encargo del líder (2026-10-15): nueva línea de oro, en diario e
intradía, que es lo que opera el trader amigo del dueño; luego BTC con las mismas reglas. Las que pasen van a un bot de
práctica en la demo de XM (dinero ficticio). Nada se cambia después de ver el resultado.

## Datos

- **Oro:** velas de PAXGUSDT en Spot de Binance (`data-api.binance.vision`). PAXG es una moneda respaldada por una onza
  de oro física; su precio sigue al oro de contado (XAUUSD) muy de cerca. Es la única fuente pública de velas de 1 hora
  de varios años que se puede bajar desde GitHub sin cuenta. PAXG cotiza también sábado y domingo; el oro no, así que
  **se quitan las velas de sábado y domingo (UTC)** y el lunes abre con el salto del fin de semana, como en XM.
- **BTC:** velas de BTCUSDT en Spot de Binance, todos los días.
- Velas de 1 hora y diarias UTC, desde 2024-06-01 para calentar indicadores.

## Costes (supuestos, porque no hay registro de XM en el repo)

- **Oro (como la cuenta Standard de XM):** diferencial de 0,40 USD por onza ida y vuelta, más 0,05 USD de deslizamiento
  por lado. Swap por cada noche abierta (posición abierta a las 21:00 UTC): largo −0,015% del tamaño, corto −0,005%; la
  noche del miércoles cuenta triple. Claude local debe confirmar estos números en la demo (`symbol_info` de GOLD); si
  son peores, se dice.
- **BTC:** comisión 0,05% y deslizamiento 0,02% por lado; financiación 0,01% cada 8 h (00, 08 y 16 UTC): el largo paga,
  el corto cobra.
- **Sensibilidad (solo informativa):** todos los costes al doble.

## Tamaño

Capital 1.000 USD al empezar cada año. Una posición a la vez por estrategia y activo. Riesgo 1% del capital por
operación: tamaño = 1% del capital ÷ distancia al stop, con tope de 5 veces el capital en tamaño.

## Las tres estrategias

**1. Ruptura de Londres** (rango asiático; descrita por Kathy Lien, *Day Trading and Swing Trading the Currency
Market*, 2008). Velas de 1 hora, días de semana.
- Rango asiático = máximo y mínimo de las velas de 00:00 a 06:00 UTC (7 velas).
- De 07:00 a 15:00 UTC: orden de compra en el máximo del rango y de venta en el mínimo; vale la primera que se toque.
  Si la vela abre más allá, se entra en la apertura.
- Stop en el otro extremo del rango. Meta a 1 vez el rango desde la entrada.
- Si sigue abierta, sale en la apertura de la vela de 20:00 UTC. Una operación por día como máximo.
- Si en la misma vela se tocan la entrada y el stop, o el stop y la meta, cuenta el stop.

**2. Tendencia diaria con ATR** (reglas de las Tortugas, sistema 1; Curtis Faith, *Way of the Turtle*, 2007). Velas
diarias.
- Entra largo si el máximo del día toca el máximo de los 20 días anteriores; corto si el mínimo toca el mínimo de los
  20 días anteriores. Entrada en ese nivel, o en la apertura si abrió más allá.
- Stop a 2 N, con N = ATR de 20 días del día anterior.
- Sale si el precio toca el mínimo de los 10 días anteriores (largo) o el máximo de los 10 días anteriores (corto).
- Sin piramidar y sin el filtro de "saltar después de una ganadora" (simplificación, fijada ahora).
- Si en el día de entrada también se toca el stop, cuenta el stop.

**3. Reversión tras noticia** (desvanecer el primer impulso de FOMC e IPC). Velas de 1 hora.
- Vela de la noticia = la vela de 1 hora que contiene la hora de la noticia (fechas de `research_mesa.FOMC_DAYS` y
  `CPI_DAYS`).
- Solo si su rango (máximo − mínimo) es al menos 2 veces el ATR 14 de 1 hora de la vela anterior.
- Entrada en contra del cuerpo de esa vela (si cerró arriba de su apertura, corto; si cerró abajo, largo) en la
  apertura de la vela siguiente.
- Stop en el extremo de la vela de la noticia (el máximo para un corto, el mínimo para un largo). Meta en la mitad del
  rango de esa vela. Si la entrada ya está más allá de la meta, no se entra.
- Si no tocó nada, sale en la apertura de la octava vela después de la entrada. Stop y meta en la misma vela: stop.
- Son unas 20 noticias al año: será **muestra corta** siempre.

## Cómo se juzga (fijado ahora)

- Años: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13. Cada estrategia y cada activo se juzga por separado, con
  los costes base.
- **Pasa a práctica en la demo de XM** si en **los dos años**: neto positivo, neto/caída de al menos 1,0 (caída medida
  sobre el capital marcado a mercado en cada cierre de vela) y al menos 3 de 4 trimestres con neto ≥ 0.
- Menos de 100 operaciones en un año: "muestra corta". Puede ir a práctica igual (es dinero ficticio), pero marcada así.
- Se informa al lado: comprar y mantener el mismo activo, y la mesa de práctica (neto/caída 1,67 y −0,21; re-medida
  1,73 y 0,20).
- Son 6 intentos (3 estrategias × 2 activos). Con tantos intentos alguno puede pasar por suerte; por eso lo que pase va
  solo a práctica con dinero ficticio, nunca directo a dinero real.
- No se toca `config/`, `live/` ni los límites.
