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
| 2026-10-14 | EWMAC de Carver | [pysystemtrade](https://github.com/robcarver17/pysystemtrade) | Enviada a Quant; sin resultado |

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

**Estado:** enviada a Quant el 2026-10-14. Desde la nube no se pueden bajar los datos de Binance.
