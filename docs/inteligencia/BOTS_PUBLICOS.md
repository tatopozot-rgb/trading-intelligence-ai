# Bots y estrategias públicas estudiadas

Orden del dueño (2026-10-13): "hay bots ya entrenados ver sus formas de hacerlo ... cambiar un plan que resultó
mejor". Una estrategia por día. Ninguna se copia sin probarla: solo pasa a práctica la que gane a la mesa en los
**dos** años (2024-25 y 2025-26) con costes. El dinero real nunca cambia sin la revisión del líder y los límites
aprobados por el dueño.

Ya probadas antes de este registro (familias de `research_tendencia.py`, un año, 2026-10-12; ninguna ganó):
canal de Donchian (reglas "Turtle"), cruce de medias EMA y momento de serie temporal (tsmom). Ver
`docs/research/tendencia/tendencia_2026-10-12.md`.

| Fecha | Estrategia | Fuente | Estado |
|---|---|---|---|
| 2026-10-14 | EWMAC de Carver | [pysystemtrade](https://github.com/robcarver17/pysystemtrade) | No pasa, ni sola ni en cartera con la mesa (2026-10-14). Archivada |
| 2026-10-15 | Ruptura de volatilidad de Larry Williams | *Long-Term Secrets to Short-Term Trading* (1999), cap. 4; [resumen LuxAlgo](https://www.luxalgo.com/library/concept/volatility-breakout/) | No pasa: pierde en los dos años, con y sin frenos (2026-10-15). Archivada |
| 2026-10-16 | Traders y bots que operan con Claude u otras IA | Alpha Arena (nof1), repos ai-hedge-fund, TradingAgents, NOFX; casos virales de Polymarket | Ningún caso verificable gana de forma sostenida; sin reglas nuevas que probar. Ver [`IA_QUE_OPERA.md`](IA_QUE_OPERA.md) |
| 2026-10-15 | Rebote a la media en lateral (Bollinger 20/2 + ADX < 20), diario y 4 h | Bollinger, *Bollinger on Bollinger Bands* (2001); Wilder, *New Concepts in Technical Trading Systems* (1978) | No pasa en ningún marco ni versión (2026-10-15). Archivada |
| 2026-10-15 | Oro: ruptura de Londres, Tortugas diaria y reversión tras noticia (y en BTC) | Kathy Lien (2008); Curtis Faith, *Way of the Turtle* (2007) | Ninguna pasa en los dos años (2026-10-15). Archivadas; Londres en oro, a vigilar |
| 2026-10-16 | RSI-2 de Larry Connors (comprar caídas cortas sobre la media de 200 días) | Connors y Alvarez, *Short Term Trading Strategies That Work* (2008); [resumen LuxAlgo](https://www.luxalgo.com/library/concept/rsi-2/) | No pasa en ninguna versión (2026-10-16). Archivada |
| 2026-10-16 | Horizonte largo en oro y BTC: media de 10 meses, momento de 12 meses y momento dual | Faber (2007); Moskowitz, Ooi y Pedersen (2012); Antonacci, *Dual Momentum Investing* (2014) | Ninguna pasa (2026-10-16): el oro gana a la mesa en los dos años, pero su Sharpe deflactado es 0,002. Archivadas. Ver `docs/research/largo/` |

---

## 2026-10-14 · EWMAC de Robert Carver (pysystemtrade)

**Qué es.** Robert Carver fue gestor en AHL (Man Group) y publica su sistema de futuros completo como código
abierto, `pysystemtrade`. Su regla principal de tendencia se llama EWMAC: la diferencia entre una media rápida y
una lenta.
([pysystemtrade](https://github.com/robcarver17/pysystemtrade), libro *Systematic Trading*, 2015; resumen en
[QuantConnect](https://www.quantconnect.com/research/15989/futures-trend-following-and-carry-in-different-risk-regimes/))

**Reglas, en simple:**

1. Para cada moneda se calcula media exponencial rápida menos lenta, en varios pares: 8/32, 16/64, 32/128 y
   64/256 días.
2. Esa diferencia se divide por la volatilidad diaria del precio. Así sale una "convicción" comparable entre
   monedas.
3. La convicción se escala para que su promedio absoluto sea 10, con un tope de ±20. Los pares se promedian.
4. El tamaño de la posición es proporcional a la convicción y al revés de la volatilidad. Más convicción, más
   tamaño; más volatilidad, menos tamaño.
5. **No usa stops.** Sale cuando la convicción baja a cero o cambia de signo. Opera largos y cortos.
6. Solo se ajusta la posición si cambió más de un 10% (evita comisiones por cambios chicos).

**En qué se diferencia de lo que ya probamos:** nuestro `ema` es todo o nada, con un stop por ATR. EWMAC cambia
el tamaño poco a poco y mezcla varias velocidades, así que no depende de un solo parámetro.

**Señales de sobreajuste:** bajas. Carver usa las mismas reglas y pares para todos los mercados y no los optimiza
por activo. Sus resultados publicados son de décadas en futuros tradicionales, no en cripto. Un lector reporta que
las escalas del libro no le daban el promedio de 10 con sus datos. Por eso la escala se mide en la ventana de
ajuste, nunca sobre el periodo de prueba.

**Cómo se prueba con nuestros datos:**

- las 12 monedas de la mesa, velas de 1 día, largos y cortos;
- 1x, máximo 50% por posición, 3 posiciones;
- comisión 0,05% y deslizamiento 0,02% por lado, más la financiación real;
- años 2024-25 y 2025-26, contra la mesa y contra mantener BTC.

Se descartan las 3 monedas con menor convicción para respetar el tope de 3 posiciones.

**Resultado (Quant, 2026-10-14, preregistrado antes de correr; `docs/research/ewmac/`):**

| Año | EWMAC neto | Caída | Neto/caída | Mesa de práctica (freno b) | BTC |
|---|---|---|---|---|---|
| 2024-10 → 2025-10 | +31,5% | 42,8% | 0,74 | 1,67 | +76,9% |
| 2025-10 → 2026-10 | +14,4% | 30,7% | 0,47 | −0,21 | −28,8% |

- **No pasa el listón:** le gana a la mesa de práctica solo en el año bajista.
- **Es la primera estrategia que gana dinero en los dos años.** Gana con cortos en los trimestres bajistas y pierde
  en los giros bruscos. En abril-julio de 2025 BTC subió 41% y EWMAC perdió 34%.
- **Sus rachas son opuestas a las de la mesa.** Por eso el líder pidió medirla como cartera junto a la mesa, con su
  propio preregistro.
- **Cuidados:**
  - su caída de 43% está pegada al límite de pérdida de 45%;
  - muestra corta: 58 y 67 entradas, menos de 100;
  - sin stops, un hueco grande pega entero.
- No va a práctica ni a dinero real con este resultado.

**Cartera mesa de práctica + EWMAC (Quant, 2026-10-14; preregistrada antes de correr; `docs/research/cartera/`):**

| Año | Mesa sola, neto/caída (caída) | 50/50 | 70/30 |
|---|---|---|---|
| 2024-25 | 1,86 (43,6%) | 1,76 (39,7%) | 1,86 (40,5%) |
| 2025-26 | 0,21 (31,5%) | 1,08 (19,6%) | 1,01 (16,6%) |

- **No pasa.** En 2024-25 la caída supera el 35% y la cartera no gana a la mesa sola.
- En 2025-26 la cartera es mucho mejor: 5 veces el neto/caída y la caída baja casi a la mitad.
- Bajar el riesgo de las dos patas no cambia el neto/caída, así que no arreglaría el año 2024-25. **El líder
  archiva la idea.** Se puede reabrir con datos nuevos o con más capital.
- **Aprendizaje:** la mesa de práctica sola tuvo una caída de 44–47% en 2024-25, en el límite de pérdida de 45% del
  dueño. Si eso pasa con dinero real, el freno de 45% la detiene, como está diseñado.

---

## 2026-10-15 · Ruptura de volatilidad de Larry Williams

**Qué es.** Larry Williams es un trader de futuros que ganó un campeonato real de trading en 1987. Usa esta idea
desde 1982 y la publicó en *Long-Term Secrets to Short-Term Trading* (1999), capítulo 4, "Volatility Breakouts".
La idea: si el precio se aleja de la apertura más que una parte del rango de ayer, el día probablemente siga en esa
dirección. En cripto se hizo muy popular en Corea, con bots para el exchange Upbit.
([resumen LuxAlgo](https://www.luxalgo.com/library/concept/volatility-breakout/),
[indicador abierto en TradingView](https://www.tradingview.com/script/P8cxeiJy/))

**Reglas, en simple (fijadas hoy por el líder, antes de probar):**

1. Velas diarias UTC. Rango de ayer = máximo − mínimo de ayer.
2. **Compra** si hoy el precio sube hasta apertura + 0,5 × rango de ayer. **Venta en corto** si baja hasta
   apertura − 0,5 × rango de ayer. Se entra al precio del disparo, más el deslizamiento.
3. Se sale en la apertura del día siguiente. Sin stop, como el original.
4. Si en la misma vela se tocan los dos disparos, se cuenta la peor de las dos operaciones, porque la vela diaria no
   dice cuál se tocó primero.
5. Máximo 3 posiciones, cada una con un tercio del capital y sin apalancamiento (1x). Si se disparan más de 3, se
   toman las 3 con más volumen en USDT ayer.

**En qué se diferencia de lo que ya probamos:**

- La "ruptura" de 2026-10-12 usaba el rango de la sesión de Asia en velas de 5 minutos, solo BTC y ETH, y 90 días
  (`docs/research/segunda_estrategia_2026-10-12.md`).
- Esta usa el rango del día anterior, mantiene la posición un día y opera las 12 monedas de la mesa durante dos
  años.

**Señales de sobreajuste: altas.**

- El factor k (0,5) se elige casi siempre con el mejor resultado del pasado. Las fuentes usan desde 0,25 hasta 0,6.
- Las versiones populares de cripto eligen k por moneda.
- Un script cerrado en TradingView dice ser "la mejor estrategia para BTC y ETH" sin mostrar su código. Es
  publicidad.
- El propio Williams escribió que la idea funciona peor en los últimos años.
- Por eso k queda fijo en 0,5 antes de probar. k = 0,25 y 0,75 se informan solo para ver la sensibilidad, nunca para
  elegir.

**Cómo se prueba con nuestros datos:**

- Las 12 monedas de la mesa, en dos versiones:
  - (A) pura, con largos y cortos;
  - (B) con los frenos de la mesa: régimen b y sin entradas los días de FOMC o IPC.
- Comisión 0,05% y deslizamiento 0,02% por lado, más la financiación real (se cuenta el día completo).
- Años 2024-25 y 2025-26, contra la mesa de práctica y contra mantener BTC.

**Cómo se juzga (fijado hoy):**

- Pasa a práctica solo si su neto/caída supera al de la mesa de práctica en **los dos años**. La mesa de práctica
  (con el freno b) dio 1,67 en 2024-25 y −0,21 en 2025-26.
- Con menos de 100 operaciones en un año, se informa como muestra corta.
- El dinero real no cambia por este estudio.

**Resultado (Quant, 2026-10-15, preregistrado antes de correr; `docs/research/breakout/`):** **no pasa.** Pierde
en los dos años, en las dos versiones, con k = 0,5:

| Año | Pura (A): neto / caída / neto/caída | Con frenos (B) | Mesa de práctica | BTC |
|---|---|---|---|---|
| 2024-25 | −55,7% / 72,5% / −0,77 | −59,5% / 73,0% / −0,81 | 1,67 | +76,9% |
| 2025-26 | −64,7% / 66,3% / −0,98 | −21,2% / 24,7% / −0,86 | −0,21 | −28,8% |

- Más de 1.000 operaciones al año en la versión pura, así que no es mala suerte de muestra. La operación media
  pierde entre −0,18% y −0,44%, después de costes. Acierta en ~40% de las operaciones.
- Comprar la ruptura del día y salir a la mañana siguiente no tiene ventaja en estas 12 monedas. Los costes
  (~0,14% por operación de ida y vuelta) se comen lo poco que haya.
- La sensibilidad confirma que el resultado no depende de k: con k = 0,25 pierde mucho más (−89% y −90%) y con
  k = 0,75 pierde menos, pero sigue perdiendo en los dos años (−14% y −46% pura). Elegir k = 0,75 viendo esto sería
  justo el sobreajuste que el preregistro prohíbe.
- Lo que dijo el propio Williams se cumple: la idea ya no funciona, al menos aquí.

---

## 2026-10-15 · Rebote a la media en mercado lateral (Bollinger + ADX), diario y 4 h

**Qué es.** La idea clásica de las bandas de Bollinger: cuando el precio se sale de su banda y el mercado no tiene
tendencia (ADX de Wilder bajo 20), apostar a que vuelve a su media. Encargo del líder del 2026-10-15, en diario y
4 h porque en 1 h ya falló (PR #46). El intento del 2026-10-06 (`BollingerReversion`) se probó solo con datos
sintéticos; este es el primero con datos reales, largos y cortos, y con costes.

**Reglas, en simple** (preregistro completo en `docs/research/rango/PREREGISTRO.md`):

1. Si una vela cierra bajo la banda inferior (20 velas, 2 desviaciones) y el ADX 14 está bajo 20, se compra en la
   apertura siguiente. Sobre la banda superior, se vende en corto.
2. Sale cuando una vela cierra de vuelta en la media de 20, o por un stop de 1,5 ATR, o a las 10 velas.
3. Tres posiciones como máximo, un tercio del capital cada una, 1x, con comisión, deslizamiento y financiación reales.

**Resultado** (`docs/research/rango/rango_2026-10-15.md`), neto/caída de la regla base:

| Año | Diario A | Diario B (frenos) | 4 h A | 4 h B (frenos) | Mesa de práctica | BTC |
|---|---|---|---|---|---|---|
| 2024-25 | −0,75 (−34%) | 1,77 (+16%, 10 ops) | −1,00 (−53%) | −0,90 (−20%) | 1,67 | +76,9% |
| 2025-26 | −0,96 (−27%) | −0,22 (−2%, 6 ops) | −0,76 (−28%) | −0,59 (−7%) | −0,21 | −28,8% |

- Ninguna de las 4 combinaciones gana a la mesa en los dos años. La única que le gana un año (diario con frenos,
  2024-25) tiene 10 operaciones: es muestra corta y en 2025-26 pierde.
- En 4 h hay muestra suficiente (400+ operaciones al año en la versión pura) y pierde en los dos años: la operación
  media pierde −0,2% a −0,5% después de costes y acierta ~42%. Cerca de la mitad de las salidas son por stop: en
  estas monedas, salirse de la banda suele ser el inicio de un movimiento, no un exceso que vuelve.
- La sensibilidad no lo salva: con 2,5 desviaciones en 4 h la versión pura gana +5,5% en 2025-26, pero pierde
  −51% en 2024-25. Elegirla por eso sería sobreajuste.
- Con este estudio el rebote a la media queda probado en 1 h, 4 h y diario, y falla en los tres. No se vuelve a
  probar otra variante de lo mismo.

---

## 2026-10-15 · Oro: tres estrategias públicas, y las mismas en BTC

**Por qué.** El dueño pidió buscar flujos más largos con dinero ficticio, y su amigo trader opera sobre todo oro. El
líder abrió la línea de oro (diario e intradía) y luego BTC con las mismas reglas. Preregistro completo en
`docs/research/oro/PREREGISTRO.md`; informe en `docs/research/oro/oro_2026-10-15.md`.

**Datos y costes.** Oro = PAXG en Binance (una moneda respaldada por una onza de oro; sigue al oro de cerca), sin
sábados ni domingos. Costes como una cuenta Standard de XM (0,40 USD por onza de diferencial, swap por noche), por
confirmar en la demo. Riesgo 1% del capital por operación.

**Las tres reglas, en simple:**

1. **Ruptura de Londres:** se mide el rango de la noche asiática (00:00 a 06:00 UTC). Desde las 07:00 se entra a
   favor del lado que se rompa, con stop en el otro lado y meta a una vez el rango. Se cierra a las 20:00.
2. **Tortugas:** se entra cuando el precio toca el máximo (o mínimo) de 20 días, con stop a 2 ATR, y se sale al tocar
   el extremo contrario de 10 días.
3. **Reversión tras noticia:** si la vela de 1 hora de una noticia FOMC o IPC es enorme, se apuesta a que devuelve la
   mitad del movimiento.

**Resultado** (neto y neto/caída; pasa si es positivo, con neto/caída ≥ 1 y 3 de 4 trimestres sin pérdida, en los
dos años):

| | 2024-25 | 2025-26 |
|---|---|---|
| Oro, Londres | −7,7% (−0,58) | +26,6% (3,72) |
| Oro, Tortugas | −0,4% (14 ops) | +1,2% (10 ops) |
| Oro, noticia | −1,0% (5 ops) | +0,2% (10 ops) |
| BTC, Londres | −14,8% (−0,58) | −17,8% (−0,80) |
| BTC, Tortugas | −4,8% (21 ops) | +9,2% (2,82, 13 ops) |
| BTC, noticia | −5,5% (11 ops) | −6,4% (9 ops) |
| Comprar y mantener | oro +49,6%, BTC +76,9% | oro +3,4%, BTC −28,8% |

- **Ninguna pasa en los dos años.**
- **Lo único interesante: la ruptura de Londres en oro.** En 2025-26 ganó +26,6% con una caída de solo 7%, y siguió
  ganando con los costes al doble (+23,1%). Pero en 2024-25 perdió −7,7%. Un año bueno de dos no es prueba: puede ser
  suerte de ese año. No se cambia la regla para arreglar 2024-25 (eso sería sobreajuste).
- En BTC la misma ruptura pierde los dos años: BTC no tiene "sesión de Londres", opera igual a toda hora.
- Tortugas y noticia operan muy poco (10 a 21 veces al año): muestra corta. No dicen nada todavía.
- Comprar y mantener oro le ganó a todo en 2024-25 (+49,6%).

---

## 2026-10-16 · RSI-2 de Larry Connors

**Qué es.** Larry Connors y Cesar Alvarez la publicaron en *Short Term Trading Strategies That Work* (2008). Es una
de las estrategias públicas más copiadas en bots de acciones y ETF. La idea: en un mercado que sube, una caída
fuerte de dos o tres días suele rebotar pronto.
([resumen LuxAlgo](https://www.luxalgo.com/library/concept/rsi-2/),
[diagrama en StockSharp](https://doc.stocksharp.com/en/designer-gallery/Larry_Connors_Rsi2),
[prueba en el S&P 500, Backtrex](https://backtrex.com/en/backtests/connors-rsi-2-sp-500))

**Reglas, en simple (fijadas hoy por el líder, antes de probar):**

1. Velas diarias UTC. RSI de 2 días con el cierre.
2. **Compra** si al cierre el precio está sobre su media de 200 días y el RSI-2 está bajo 10. Se entra en la
   apertura del día siguiente, más el deslizamiento.
3. **Venta** cuando un cierre queda sobre la media de 5 días. Se sale en la apertura siguiente. Sin stop, como el
   original.
4. Solo compras (el original es para acciones y ETF; el espejo en corto se informa aparte, no decide).
5. Máximo 3 posiciones, cada una con un tercio del capital y sin apalancamiento (1x). Si hay más de 3 señales, se
   toman las 3 con el RSI-2 más bajo.

**En qué se diferencia de lo que ya probamos:**

- El rebote a la media del 15-10 (Bollinger + ADX) buscaba mercado **lateral**. Este busca caídas cortas dentro
  de una **tendencia alcista** (sobre la media de 200).
- La reversión 1h/4h/diario descartada antes no tenía filtro de tendencia.
- Se parece en espíritu a la regla de la mesa: la mesa solo compra con BTC sobre su media; aquí el filtro es por
  moneda.

**Señales de sobreajuste: medias.**

- Los números (2, 10, 200, 5) vienen del libro de 2008, probados en acciones de EE. UU. No se eligen con nuestros
  datos.
- Los sitios que la venden cambian el umbral (5 o 10) o la salida según qué dio mejor. Aquí queda fijo en 10 y en
  la media de 5. El umbral 5 se informa solo para ver la sensibilidad.
- Sin stop, una caída que no rebota puede costar mucho. Por eso se mira también la peor operación.

**Cómo se prueba con nuestros datos:**

- Las 12 monedas de la mesa, en dos versiones:
  - (A) pura;
  - (B) con los frenos de la mesa: régimen b y sin entradas los días de FOMC o IPC.
- Comisión 0,05% y deslizamiento 0,02% por lado, más la financiación real.
- Años 2024-25 y 2025-26, contra la mesa de práctica y contra mantener BTC.

**Cómo se juzga (fijado hoy):**

- Pasa a práctica solo si su neto/caída supera al de la mesa de práctica en **los dos años** (mesa con freno b:
  1,67 en 2024-25 y −0,21 en 2025-26).
- Con menos de 100 operaciones en un año, se informa como muestra corta.
- Desde hoy también se informa el número total de pruebas hechas y el Sharpe deflactado (ver la lección del tema 6
  en `docs/inteligencia/2026-10-16.md`).
- El dinero real no cambia por este estudio.

**Estado:** enviada a Quant el 2026-10-16. No se pudo correr en la nube (Binance bloqueado en este contenedor).

**Resultado (Quant, 2026-10-16, preregistrado antes de correr; `docs/research/rsi2/`):**

| Año | A pura: neto (caída), neto/caída | B con frenos: neto (caída), neto/caída | Mesa de práctica | BTC |
|---|---|---|---|---|
| 2024-10 → 2025-10 | +2,6% (24,7%), 0,11 | −11,4% (24,0%), −0,47 | 1,67 | +76,9% |
| 2025-10 → 2026-10 | +3,1% (10,5%), 0,29 | +1,9% (3,9%), 0,49 | −0,21 | −28,8% |

- **No pasa:** gana a la mesa solo en el año bajista, en las dos versiones. Archivada.
- **Muestra corta:** de 9 a 71 operaciones por año. Con los frenos casi no opera en 2025-26 (9 entradas).
- **Peor operación:** −23,3% del tamaño (AVAX, 8 → 11 de octubre de 2025, la caída grande del 10-10). Sin stop,
  un desplome pega entero, como se temía.
- **Sensibilidad (no decide):** con umbral 5, la versión pura hizo 2,43 en 2024-25, pero perdió en 2025-26. Es el
  caso típico de un número que se ve bien en un año y no en el otro. El espejo en corto pierde en los dos años.
- **Pruebas hechas desde el 12-10:** 292 (247 decisorias), en `docs/research/REGISTRO_PRUEBAS.md`.
- **Sharpe deflactado de Londres en oro 2025-26:** 0,21 con N = 292 (listón 0,95). Su Sharpe anual de 2,04 está
  bajo el 2,84 que daría por suerte la mejor de 292 pruebas sin ventaja. Su año bueno puede ser suerte; por eso
  sigue solo en observación con dinero ficticio (`docs/research/deflactado/`).
