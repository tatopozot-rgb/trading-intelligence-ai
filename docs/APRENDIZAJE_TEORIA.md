---
type: aprendizaje
tags: [teoria, futuros, profesional]
status: living
---

# Teoría del trader profesional de futuros — plan de estudio

Orden del dueño (2026-10-13): "no te bases solo en datos históricos, el mercado varía mucho según cada situación;
estúdialo bien, no solo en la práctica sino también en la teoría; no dejen de aprender hasta que sean traders
profesionales de futuros".

Cada tema tiene tres partes: **qué dice la teoría**, **qué hacemos hoy** y **qué falta**. Cada día, la rutina de
inteligencia estudia un tema, lo contrasta con la mesa y anota la lección en `docs/inteligencia/`. Un tema se
marca "aplicado" solo cuando su regla está en el código o en un experimento medido.

## 1. Gestión del riesgo (lo primero; sin esto nada sirve)

- **Teoría:** un profesional arriesga una fracción pequeña y fija por operación (normalmente 0,5–2% de la
  cuenta). La caída máxima, no la ganancia, decide si sobrevive. Una caída del 50% exige ganar 100% para
  volver. El tamaño óptimo según Kelly se usa a la mitad o menos, porque la ventaja estimada siempre es
  incierta.
- **Hoy:** el riesgo pedido es de 1–15% según la señal, con un tope de posición del 50%. El riesgo real queda
  en ~2% de media y ~5% como máximo. La pérdida tiene un límite.
- **Falta:** la investigación mostró que la mesa no tiene ventaja fuera del tramo alcista; sin ventaja, ningún
  tamaño gana. Medio Kelly solo perdió menos (CHECKPOINT §98). Revisar el 15% de riesgo pedido cuando haya una
  estrategia con ventaja.

## 2. Régimen de mercado (alcista, bajista, lateral)

- **Teoría:** casi ninguna estrategia gana en todos los regímenes. Los profesionales primero identifican el
  régimen (tendencia de largo plazo, volatilidad, liquidez) y solo operan la estrategia que encaja; en caso de
  duda, se quedan quietos.
- **Hoy:** la mesa gana solo en el régimen alcista y pierde en los demás (−53% en el año).
- ~~**Falta:** el interruptor de régimen~~ **aplicado** 2026-10-13: freno de mercado `regime_btc_sma` 50 (sin
  entradas nuevas con BTC bajo su media de 50 días; si no puede leer los datos, tampoco abre).

## 3. Macro y liquidez

- **Teoría:** las criptomonedas se mueven con la liquidez en dólares. Tasas más altas, un dólar fuerte y la
  reducción del balance de la Fed restan liquidez y suelen pesar sobre BTC. Los recortes de tasas y un dólar
  débil ayudan. Los días de FOMC y CPI producen movimientos bruscos y deslizamiento.
- **Hoy:** la mesa no mira la macro.
- **Falta:**
  - Una nota diaria de inteligencia (`docs/inteligencia/`).
  - ~~Un filtro de eventos~~ **aplicado** 2026-10-13: sin entradas ±2 h alrededor de FOMC/CPI (`config/eventos.json`); falta medir el tamaño de la ventana.
  - El estado de tasas y dólar como entrada del régimen.

## 4. Estructura de los futuros perpetuos

- **Teoría:** la **financiación** paga del lado saturado al otro cada 8 h. Si es muy positiva, hay demasiados
  largos apalancados y el riesgo de una cascada de liquidaciones crece. El **interés abierto** que sube con el
  precio confirma la tendencia; si sube mientras el precio no avanza, es apalancamiento frágil. La **base**
  (perpetuo frente a contado) mide el apetito por apalancamiento. Las **liquidaciones** en cascada crean
  extremos que luego se revierten.
- **Hoy:** el Escéptico veta contra una financiación saturada (aportó poco pero algo); los top traders entran
  en la señal.
- **Falta:**
  - El interés abierto y las liquidaciones como datos de entrada (Binance los publica gratis en
    `data.binance.vision` y en su API).
  - Estudiar estrategias de "después de la cascada".
  - Lección 2026-10-14: filtro "lado saturado" enviado a Quant para medir (no aplicado).

## 5. Volatilidad

- **Teoría:** la volatilidad se agrupa en rachas y vuelve a su media. Una volatilidad implícita muy baja suele
  anteceder a movimientos grandes. El tamaño de la posición debe bajar cuando la volatilidad sube, para
  arriesgar lo mismo en dinero.
- **Hoy:** el stop se fija por volatilidad (3–15%) y el tamaño se ajusta al stop.
- **Falta:** usar el régimen de volatilidad (implícita o realizada) para decidir si se opera.

## 6. Ventaja estadística y cómo no engañarse

- **Teoría:** una estrategia vale solo si su ventaja se sostiene fuera de la muestra en la que se eligió.
  Riesgos: sobreajuste, sesgo de supervivencia (elegir monedas que ya subieron), mirar el futuro, costes
  subestimados y muestras cortas. Los profesionales prerregistran las reglas antes de probarlas.
- **Hoy:** `docs/research/PROTOCOLO.md`, walk-forward, prerregistros (`PREREG_*`, `research/tendencia/PREREGISTRO.md`).
- **Lección aprendida:** las ganancias de 30 y 60 días eran de un solo régimen. Un año completo lo desmintió.

## 7. Ejecución y costes

- **Teoría:** las comisiones, el deslizamiento y la financiación se comen las estrategias de muchas
  operaciones. Las órdenes límite (maker) pagan menos que las de mercado (taker).
- **Hoy:** costes explícitos (0,05% por lado, deslizamiento 0,02%, financiación real).
- **Falta:** medir las órdenes maker en la práctica y la calibración real de las ejecuciones.

## 8. Psicología y proceso

- **Teoría:** un profesional sigue su plan y no sube el riesgo para recuperar pérdidas (nada de martingala).
  Lleva un diario, revisa cada operación y acepta días sin operar.
- **Hoy:** reglas fijas en código, un diario de la mesa en Obsidian, nada de martingala y límite de pérdida.
- **Falta:** una revisión semanal del diario con lecciones concretas.

## Lecturas de referencia (teoría clásica)

- Gestión del riesgo y tamaño: Van K. Tharp, *Trade Your Way to Financial Freedom*; Ralph Vince, *The
  Mathematics of Money Management*.
- Tendencia y régimen: Andreas Clenow, *Following the Trend*; Covel, *Trend Following*.
- Ventaja y validación: Marcos López de Prado, *Advances in Financial Machine Learning* (sobreajuste,
  validación); Ernest Chan, *Algorithmic Trading*.
- Psicología: Mark Douglas, *Trading in the Zone*.
- Derivados: John Hull, *Options, Futures, and Other Derivatives* (financiación, base, apalancamiento).
