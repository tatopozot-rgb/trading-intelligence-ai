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

