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
- Lección 2026-10-19 (segunda vuelta): la caída y el apalancamiento. La práctica 3x lleva −23,6% en 6 cierres sin
  freno por caída. Freno propuesto (riesgo a la mitad con 10% de caída, pausa con 20%) medido por Quant (PR #108):
  en 1x gana a la mesa los dos años (1,92 y 0,18), pero el Sharpe deflactado es 0,005; en 3x no rescata nada
  (−0,22 y −0,69). No pasa y no se aplica. El problema del 3x es el apalancamiento, no la falta de freno.

## 2. Régimen de mercado (alcista, bajista, lateral)

- **Teoría:** casi ninguna estrategia gana en todos los regímenes. Los profesionales primero identifican el
  régimen (tendencia de largo plazo, volatilidad, liquidez) y solo operan la estrategia que encaja; en caso de
  duda, se quedan quietos.
- **Hoy:** la mesa gana solo en el régimen alcista y pierde en los demás (−53% en el año).
- ~~**Falta:** el interruptor de régimen~~ **aplicado** 2026-10-13: freno de mercado `regime_btc_sma` 50 (sin
  entradas nuevas con BTC bajo su media de 50 días; si no puede leer los datos, tampoco abre).
- Lección 2026-10-20 (segunda vuelta): el freno no abre, pero lo ya abierto sigue hasta su stop. Desde el 15-10,
  las prácticas cerraron 10 compras viejas por stop a −1R. Propuesta: salida por régimen (cerrar las compras al día
  siguiente de que BTC cierre bajo su media de 50 días), enviada a Quant para medir. Resultado (PR #113): no pasa
  (1x 1,04 y 0,18, DSR 0,005; 3x −0,25 y −0,28); cuesta en el año bueno y salva en el malo. Además, la regla YA
  está en el código (`live/two_way.py`, `_decide`, cierra los largos con el freno activo). La práctica no la usó
  porque BTC cerró sobre su media del 10 al 19-10 (tabla de Quant): el freno nunca se activó.

## 3. Macro y liquidez

- **Teoría:** las criptomonedas se mueven con la liquidez en dólares. Tasas más altas, un dólar fuerte y la
  reducción del balance de la Fed restan liquidez y suelen pesar sobre BTC. Los recortes de tasas y un dólar
  débil ayudan. Los días de FOMC y CPI producen movimientos bruscos y deslizamiento.
- **Hoy:** la mesa no mira la macro.
- **Falta:**
  - Una nota diaria de inteligencia (`docs/inteligencia/`).
  - ~~Un filtro de eventos~~ **aplicado** 2026-10-13: sin entradas ±2 h alrededor de FOMC/CPI (`config/eventos.json`); falta medir el tamaño de la ventana.
  - El estado de tasas y dólar como entrada del régimen.
  - Lección 2026-10-21: la macro decide cuánto arriesgar, no cuándo entrar. Regla "riesgo a la mitad" (bono a 10
    años y DXY sobre su media de 50 días) medida por Quant (PR #119): **no pasa**. En 1x casi no cambia (1,01 / 0,18
    contra 1,04 / 0,18 sin la regla) porque el tope por posición manda; en 3x empeora 2025-26 (−0,59 contra −0,28).
    No se aplica.

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
  - Lección 2026-10-22: el simulador de las prácticas no cobra la financiación de las posiciones abiertas (las
    pruebas de Quant y el real sí). Cobrarla en cada corte de 8 h: **aplicado** 2026-10-22 (`PaperFuturesBroker._fund`,
    PR #131); rige desde que Local actualiza londres-wt, nunca hacia atrás.

## 5. Volatilidad

- **Teoría:** la volatilidad se agrupa en rachas y vuelve a su media. Una volatilidad implícita muy baja suele
  anteceder a movimientos grandes. El tamaño de la posición debe bajar cuando la volatilidad sube, para
  arriesgar lo mismo en dinero.
- **Hoy:** el stop se fija por volatilidad (3–15%) y el tamaño se ajusta al stop.
- **Falta:**
  - Usar el régimen de volatilidad (implícita o realizada) para decidir si se opera.
  - Mirar el riesgo de las 3 posiciones juntas: en las caídas se mueven a la vez.
  - Lección 2026-10-15: "freno de volatilidad" (sin entradas con la volatilidad de 7 días de BTC en el 10% más
    alto del año) enviado a Quant para medir (no aplicado).
  - **Resultado (Quant, 2026-10-15, preregistrado; `docs/research/volatilidad/`): no ayuda.** En la mesa de
    práctica, el freno V90 empeora el neto/caída en los dos años: 1,52 contra 1,73 en 2024-25 y −0,30 contra 0,20
    en 2025-26. Quita muy pocas operaciones (11 y 3), pero algunas eran buenas; probablemente porque después de días
    bruscos también vienen rebotes fuertes. V80 es peor todavía. V95 (activo solo ~3% del tiempo) mejora 2024-25
    (1,93) y empata 2025-26; es informativo y no decide: elegirlo ahora sería sobreajuste.
    Sin el freno de régimen, V90 mejora un poco, pero sigue perdiendo en 2025-26 (−50% contra −62%). Conclusión: el
    stop por volatilidad que ya usa la mesa basta; no frenar las entradas por la volatilidad de BTC.
  - Lección 2026-10-23 (segunda vuelta): en las caídas las monedas se mueven juntas, así que 3 compras son casi una
    sola apuesta; nada suma hoy el riesgo abierto de las 3 (peor caso 3 × 15% = 45%). Medirlo en la revisión
    nocturna (rutina de código, no suma a N) y un tope al riesgo abierto total enviado a Quant (no aplicado).
  - **Resultado (Quant, 2026-10-23, fila 384; `docs/research/tope_riesgo/`): no prueba ventaja.** El tope de 2% al
    riesgo abierto del mismo lado, en la mesa 1x, da 0,58 y 0,74 de neto/caída contra 1,04 y 0,18 sin tope. Sharpe
    deflactado 0,013. Baja la caída los dos años (53,9% → 34,9% y 32,5% → 24,9%), pero el neto pierde 36 puntos
    en 2024-25 (+20% contra +56%) y gana 12 en 2025-26. Es un freno de riesgo que hace lo esperado, no una ventaja.
    Usarlo solo como medida de seguridad es decisión del Líder y del dueño, fuera del listón.

## 6. Ventaja estadística y cómo no engañarse

- **Teoría:** una estrategia vale solo si su ventaja se sostiene fuera de la muestra en la que se eligió.
  Riesgos: sobreajuste, sesgo de supervivencia (elegir monedas que ya subieron), mirar el futuro, costes
  subestimados y muestras cortas. Los profesionales prerregistran las reglas antes de probarlas.
- **Hoy:** `docs/research/PROTOCOLO.md`, walk-forward, prerregistros (`PREREG_*`, `research/tendencia/PREREGISTRO.md`).
- **Lección aprendida:** las ganancias de 30 y 60 días eran de un solo régimen. Un año completo lo desmintió.
- Lección 2026-10-16: con más de 30 pruebas hechas, la mejor sale bien por suerte. Registro único de pruebas y
  Sharpe deflactado (Bailey y López de Prado, 2014) como segundo listón: **aplicado** 2026-10-16
  (`docs/research/REGISTRO_PRUEBAS.md`, PR #83).
- Lección 2026-10-24 (segunda vuelta): largo mínimo del historial (Bailey y López de Prado, 2012). Con Sharpe anual
  1,5 hacen falta ~440 días en vivo para descartar la suerte con 95% de confianza; con Sharpe 3, ~110. El aviso de
  "30 días o 30 operaciones con ganancia" de XM demo es solo un aviso. Mostrar el Sharpe probabilístico y los días
  que faltan en la revisión de cada bot demo (rutina de código, no suma a N; no aplicado).

## 7. Ejecución y costes

- **Teoría:** las comisiones, el deslizamiento y la financiación se comen las estrategias de muchas
  operaciones. Las órdenes límite (maker) pagan menos que las de mercado (taker).
- **Hoy:** costes explícitos (0,05% por lado, deslizamiento 0,02%, financiación real).
- **Falta:** medir las órdenes maker en la práctica y la calibración real de las ejecuciones.
- Lección 2026-10-17: selección adversa de las órdenes límite y deslizamiento real de los stops. Anotar
  señal contra ejecución (pb) en cada cierre real y de práctica, enviado a Quant para medir (no aplicado).

## 8. Psicología y proceso

- **Teoría:** un profesional sigue su plan y no sube el riesgo para recuperar pérdidas (nada de martingala).
  Lleva un diario, revisa cada operación y acepta días sin operar.
- **Hoy:** reglas fijas en código, un diario de la mesa en Obsidian, nada de martingala y límite de pérdida.
- **Falta:** una revisión semanal del diario con lecciones concretas.
- Lección 2026-10-18: separar "¿seguí el plan?" de "¿funcionó?". Cierre semanal de 3 líneas cada domingo en la nota de
  aprendizaje de la semana (fuera de reglas, incidente repetido, una mejora): **aplicado** 2026-10-18, empieza en la W42.

## Lecturas de referencia (teoría clásica)

- Gestión del riesgo y tamaño: Van K. Tharp, *Trade Your Way to Financial Freedom*; Ralph Vince, *The
  Mathematics of Money Management*.
- Tendencia y régimen: Andreas Clenow, *Following the Trend*; Covel, *Trend Following*.
- Ventaja y validación: Marcos López de Prado, *Advances in Financial Machine Learning* (sobreajuste,
  validación); Ernest Chan, *Algorithmic Trading*.
- Psicología: Mark Douglas, *Trading in the Zone*.
- Derivados: John Hull, *Options, Futures, and Other Derivatives* (financiación, base, apalancamiento).
