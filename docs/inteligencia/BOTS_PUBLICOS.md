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
| 2026-10-17 | Bot de cuadrícula ("Spot Grid"): 20 escalones geométricos en ±10%, cuadrícula nueva cada lunes | Bots de Binance, Pionex, Bybit y KuCoin; [Mobee](https://mobee.com/en/mobee-academy/blog/spot-grid-trading) | No pasa (2026-10-17): BTC −0,0% / −15,0%, ETH −29,4% / −29,0%; lo ganado en idas y vueltas se pierde en inventario. Archivada. Ver `docs/research/grid/` |
| 2026-10-18 | Supertrend de freqtrade (3 Supertrend en 1 h, largo y corto) | [FSupertrendStrategy.py](https://raw.githubusercontent.com/freqtrade/freqtrade-strategies/b8a90bebebfc13a78416635166ebafdece596d3f/user_data/strategies/futures/FSupertrendStrategy.py) | No pasa (2026-10-18): A tal cual pierde en los dos años (juntas −12,8% / −41,6%, caída 53%); B con frenos gana a la mesa solo en ETH 2024-25 (2,29) y pierde en 2025-26; Sharpe deflactado ≤ 0,001. Archivada. Ver `docs/research/supertrend/` |
| 2026-10-19 | Nube de Ichimoku en BTC diario (9/26/52, solo compras) | Goichi Hosoda (1969); [Investopedia](https://www.investopedia.com/terms/i/ichimoku-cloud.asp); [StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/ichimoku-cloud) | No pasa (2026-10-19): A juntas gana a la mesa en 2024-25 (2,92) y pierde en 2025-26 (−0,34); B con frenos pierde en 2025-26; Sharpe deflactado ≤ 0,009; 3 a 8 operaciones al año. Archivada. Ver `docs/research/ichimoku/` |
| 2026-10-20 | Cruce del MACD en BTC y ETH diario (12/26/9, solo compras) | Gerald Appel, *Technical Analysis: Power Tools for Active Investors* (2005); [Investopedia](https://www.investopedia.com/terms/m/macd.asp) | Enviada a Quant (2026-10-20) |

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

---

## 2026-10-17 · Bot de cuadrícula ("Spot Grid") de Binance y Pionex

**Qué es.** El bot que más ofrecen los exchanges a usuarios comunes: Binance, Pionex, Bybit y KuCoin lo traen
listo. La idea es comprar barato y vender caro de forma automática dentro de un rango: se ponen órdenes de compra
escalonadas bajo el precio y de venta sobre él. Gana cuando el precio va y viene; sufre cuando sale del rango.
([Mobee: cuadrícula al contado](https://mobee.com/en/mobee-academy/blog/spot-grid-trading),
[Mobee: aritmética contra geométrica](https://mobee.com/en/mobee-academy/blog/geometric-vs-arithmetic),
[glosario Spark](https://www.spark.money/glossary/grid-trading),
[Binance Square #spotgrid](https://www.binance.com/en/square/hashtag/spotgrid))

**Reglas, en simple (fijadas hoy por el líder, antes de probar):**

1. Velas de 1 hora. Cada lunes a las 00:00 UTC se arma una cuadrícula nueva para la semana, y se cierra la de la
   semana anterior al precio de ese momento.
2. **Rango:** del precio de apertura ±10% (la "IA" de los exchanges suele proponer algo así para BTC en una semana).
3. **20 escalones geométricos** (cada uno ~1% más arriba que el anterior). Cada escalón usa 1/20 del capital.
4. **Compra** al tocar un escalón bajo el precio; cuando el precio sube un escalón desde esa compra, **vende** esa
   porción. Cada ida y vuelta gana ~1% menos costos.
5. Si el precio sale del rango, no se compra más abajo ni se vende más arriba hasta el lunes; se mantiene lo que
   haya. Sin stop, como el bot por defecto.
6. Solo al contado y sin apalancamiento (1x). Monedas: BTC y ETH, cada una por separado y juntas a mitades.

**En qué se diferencia de lo que ya probamos:**

- Nada de lo probado gana en lateral sin predecir dirección; este bot no predice, solo cobra el ir y venir.
- La reversión 1h/4h y el rebote a la media también compran caídas, pero con una señal por vez. Aquí hay 20
  órdenes repartidas a la vez.

**Señales de sobreajuste y trampas: altas.**

- Los exchanges muestran el "rendimiento de la cuadrícula" sin contar la pérdida del inventario cuando el precio
  cae. En una caída fuerte, el bot termina con todo el capital comprado arriba.
- Cuanto más chico el escalón, más idas y vueltas y más pesan los costos. Con ~1% de escalón y 0,1% ida y vuelta,
  el 10% de cada ganancia se va en comisión.
- Se fija ±10% y 20 escalones y no se optimiza. ±5% y ±20% se informan solo para ver la sensibilidad.

**Cómo se prueba con nuestros datos:**

- Velas de 1 hora de Binance; las órdenes límite se llenan solo si el precio cruza el escalón (no si solo lo toca).
- Comisión 0,1% por lado (contado, cuenta normal) y, aparte, 0,02% de maker más 0,01% de deslizamiento (lado
  bueno) para ver el mejor caso.
- Años 2024-25 y 2025-26, contra la mesa de práctica y contra mantener BTC.

**Cómo se juzga (fijado hoy):**

- Pasa a práctica solo si su neto/caída supera al de la mesa de práctica en **los dos años** (mesa con freno b:
  1,67 en 2024-25 y −0,21 en 2025-26) **y** pasa el Sharpe deflactado (ver `docs/research/REGISTRO_PRUEBAS.md`).
- Se informa aparte cuánto se ganó en idas y vueltas y cuánto se perdió en inventario.
- El dinero real no cambia por este estudio.

**Estado: no pasa (2026-10-17, Quant, PR #89). Archivada.** Ver `docs/research/grid/grid_2026-10-17.md`.

- BTC ±10%: −0,0% en 2024-25 y −15,0% en 2025-26 (neto/caída −0,0 y −0,8, contra 1,67 y −0,21 de la mesa).
  Sharpe deflactado 0,0. Ganó +314 y +254 USDT en idas y vueltas, pero perdió −314 y −404 en inventario.
- ETH ±10%: −29,4% y −29,0%. A mitades: −15,8% y −22,2%.
- Ni el mejor caso maker ni ±20% pasan los dos años. Confirma la trampa: lo que muestra el exchange no cuenta el
  inventario.

## 2026-10-18 · Supertrend de freqtrade (versión para futuros)

**Qué es.** Una de las estrategias de ejemplo más copiadas del repositorio público de freqtrade, el bot de código
abierto más usado para cripto. La escribió Juan Carlos Soriano (@juankysoriano). Usa el Supertrend: una línea que va
bajo el precio cuando sube y sobre el precio cuando baja, a una distancia de N veces el rango medio (ATR).
([código](https://raw.githubusercontent.com/freqtrade/freqtrade-strategies/b8a90bebebfc13a78416635166ebafdece596d3f/user_data/strategies/futures/FSupertrendStrategy.py))

**Reglas, tal como están en el código:**

1. Velas de 1 hora. ATR como media simple del rango verdadero.
2. **Entrada en largo:** los tres Supertrend de compra dicen "arriba" (multiplicador y período: 4/8, 7/9 y 1/8).
3. **Entrada en corto:** los tres Supertrend de venta dicen "abajo" (1/16, 3/18 y 6/18).
4. **Salida del largo:** el segundo de venta (3/18) pasa a "abajo". **Salida del corto:** el segundo de compra (7/9)
   pasa a "arriba".
5. Stop fijo de −26,5%. Toma de ganancia escalonada por tiempo (10% al entrar, 5% a la hora, 2,5% a las 2 horas) y
   stop que sigue al precio a 5% una vez que gana 10%.
6. El código no dice apalancamiento ni muestra resultados.

**Señales de sobreajuste: altas.**

- Los seis pares de parámetros salieron de una optimización automática ("hyperopt"), no de una idea. Un ajuste así
  casi siempre se ve bien en el período donde se buscó y mal fuera de él.
- El autor avisa que no la validó contra el trabajo original.
- El stop de −26,5% es mucho más ancho que el de la mesa (1R ≈ 1,5 a 2 ATR); con 1x y nuestro riesgo por
  operación, el tamaño quedaría muy chico.

**Cómo la debe probar Quant (fijado hoy, antes de mirar resultados):**

- Parámetros tal cual del código, sin volver a optimizar. Velas de 1 hora de Binance, BTC y ETH por separado y juntas.
- Dos versiones: A) tal cual (stop −26,5% y salidas del código); B) con los frenos de la mesa (stop a 1R de la mesa,
  freno de mercado y freno de eventos).
- Costos de la mesa: 0,05% por lado, 0,02% de deslizamiento y financiación real. Años 2024-25 y 2025-26, y Sharpe
  deflactado con la N del registro.
- Solo pasa si gana a la mesa en los dos años y pasa el Sharpe deflactado.

**Estado: no pasa (2026-10-18). Archivada.** Quant la probó con el plan de arriba (`docs/research/supertrend/`,
filas 340-347 del registro, N = 272). Neto/caída 2024-25 ; 2025-26, contra la mesa 1,67 ; −0,21:

| Versión | BTC | ETH | Juntas |
|---|---|---|---|
| A, tal cual | −0,37 ; −0,73 | −0,10 ; −0,83 | −0,24 ; −0,79 |
| B, con frenos | 0,59 ; −0,65 | 2,29 ; −0,42 | 1,53 ; −0,55 |

- A juntas pierde −12,8% y −41,6%, con caídas de 53-54%; las comisiones se comen cerca del 20% del capital por año.
- B en ETH gana a la mesa solo en 2024-25 (+26,9%, caída 11,7%) y pierde en 2025-26.
- Sharpe deflactado ≤ 0,001 en todas las filas. Se confirma la señal de sobreajuste.

## 2026-10-19 · Nube de Ichimoku en BTC diario

**Fuente:** sistema de Goichi Hosoda (publicado en 1969). Las reglas de uso común están en
[Investopedia](https://www.investopedia.com/terms/i/ichimoku-cloud.asp) y en
[StockCharts](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/ichimoku-cloud).
Es una de las estrategias de tendencia más usadas en criptomonedas, y muchos bots públicos la traen como plantilla.

**Las piezas (velas diarias, parámetros clásicos sin tocar):**
- **Línea rápida (Tenkan):** el punto medio entre el máximo y el mínimo de los últimos 9 días.
- **Línea lenta (Kijun):** el punto medio de los últimos 26 días.
- **Borde A de la nube:** el promedio de las dos líneas, dibujado 26 días adelante.
- **Borde B de la nube:** el punto medio de los últimos 52 días, dibujado 26 días adelante.
- La nube es el espacio entre A y B. Es verde cuando A está sobre B.

**Reglas (versión A, tal cual):**
1. **Entrada en compra:** el precio cierra sobre la nube de hoy, la línea rápida está sobre la lenta y la nube de 26
   días adelante es verde. Se entra en la apertura del día siguiente.
2. **Salida:** el precio cierra bajo la línea lenta o dentro de la nube (la regla más común). Se sale en la apertura
   siguiente.
3. **Solo compras.** El sistema original no habla de cortos en criptomonedas, y la mesa no opera cortos con el freno
   activo.
4. Posición de 100% a 1x, sin stop aparte. La propia salida hace de stop.

**Versión B (con los frenos de la mesa):** las mismas reglas, más el freno de BTC sobre su media de 50 días, el freno
de eventos y el riesgo por operación de la mesa (stop en la línea lenta, tamaño para perder 2% como máximo).

**Cómo medirla:** BTC y ETH diario, 2024-10 → 2025-10 y 2025-10 → 2026-10. Costos 0,05% por lado, deslizamiento
0,02% y financiación real. Se compara con la mesa (neto/caída) y con comprar y mantener. Los parámetros 9/26/52 se
dejan fijos: no se afinan.

**Señales de sobreajuste a vigilar:**
- 9/26/52 vienen de la semana de 6 días del Japón de los años 30; no se buscaron para criptomonedas. Eso es bueno:
  no hay optimización escondida. Pero si alguien muestra una versión con 10/30/60 "para cripto", eso sí es ajuste.
- Es una regla de tendencia lenta, como la media de 10 meses que ya falló (2026-10-16). Lo más probable es que gane
  en el año alcista y pierda en el lateral. Si gana en los dos años con pocas operaciones (menos de 10 por año), el
  Sharpe deflactado lo dirá.

**Estado: no pasa (2026-10-19). Archivada.** Quant, PR #108 (`docs/research/ichimoku/ichimoku_2026-10-19.md`):

| Versión (BTC y ETH juntas) | 2024-25, neto/caída | 2025-26, neto/caída |
|---|---|---|
| A tal cual | 2,92 (+40,5%) | −0,34 (−3,0%) |
| B con frenos | 0,23 | −0,66 |
| Mesa de práctica | 1,67 | −0,21 |

- Pasó lo esperado: gana en el año alcista y pierde en el lateral, como la media de 10 meses.
- El Sharpe deflactado no pasa de 0,009 en ninguna versión. Cada moneda sola tiene muy pocas operaciones (3 a 8 por
  año) para decir algo.

## Cruce del MACD en BTC y ETH diario (2026-10-20)

- **Fuente:** Gerald Appel, *Technical Analysis: Power Tools for Active Investors* (2005);
  [Investopedia](https://www.investopedia.com/terms/m/macd.asp).
- **Reglas, versión A (tal cual):**
  - MACD = media exponencial de 12 días menos la de 26 días; señal = media exponencial de 9 días del MACD.
  - Compra al abrir el día siguiente al cierre en que el MACD cruza sobre la señal.
  - Vende al abrir el día siguiente al cierre en que el MACD cruza bajo la señal. Sin stop propio. Solo compras.
  - BTC y ETH por separado y juntas (mitad y mitad), 1x, comisión y deslizamiento de la mesa.
- **Versión B (con los frenos de la mesa):** las mismas reglas, más el freno de mercado (BTC sobre su media de 50
  días), el stop de la mesa y el freno de eventos.
- **Prueba:** 2024-10 → 2025-10 y 2025-10 → 2026-10, con costos, contra la mesa de práctica (1,67 y −0,21 de
  neto/caída). Pasa solo si gana a la mesa en los dos años y su Sharpe deflactado pasa el listón.
- **Señales de sobreajuste:** ninguna en los parámetros (son los clásicos y no se afinan). El riesgo es el
  contrario: en mercados laterales el MACD cruza muchas veces y las comisiones se comen la ganancia.

