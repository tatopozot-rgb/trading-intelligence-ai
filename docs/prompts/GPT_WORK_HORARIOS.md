# GPT Work: revisión diaria del experimento de horarios (2 semanas)

De Claude Leader, 2026-10-09. El dueño quiere saber **a qué horas del día y en qué monedas**
conviene operar. Para eso se prueban ventanas de **2 horas**, con análisis **cada 20 minutos**,
durante **2 semanas**: del 2026-10-10 al 2026-10-23. Cada día se publica un reporte, lo revisa
GPT Work, lo revisa el líder y, al final, se decide con la regla registrada de antemano.

## Qué es el experimento

- **Días de operación como trader:** de lunes a viernes, con el sábado aparte para decidir si
  se incluye. El domingo se registra pero no decide.
- **La ventana del dueño: de 07:00 a 10:00, hora de Ecuador (UTC−5).** Es la hipótesis
  principal y se evalúa por separado.
- Además se exploran 12 ventanas de 2 horas para buscar otras horas buenas: 19:00, 21:00 …
  17:00 en hora de Ecuador (00:00, 02:00 … 22:00 UTC).
- Las entradas se deciden **cada 20 minutos**. Con una operación abierta, la salida se revisa
  **cada 3 minutos**: el stop loss analizado de la estrategia, su señal de salida y el cierre
  obligatorio al final de la ventana.
- 13 mercados: las 12 monedas aprobadas y PAXG (oro).
- 3 maneras de operar, solo compras:
  - **tendencia**: cruce de medias;
  - **rango**: bandas de Bollinger;
  - **base**: comprar al inicio de la ventana y vender al final.
- Cada operación se cierra como máximo al terminar su ventana de 2 horas.
- Costos reales de Spot: 0,1% por lado y deslizamiento. Datos públicos de Binance.
- **Es con dinero simulado (PAPER).** No usa claves ni manda órdenes. La sesión real del dueño
  sigue aparte, sin cambios.
- La regla de decisión está en `docs/PREREG_HORARIOS.md`, escrita antes de ver resultados:
  - la semana 1 elige candidatos;
  - la semana 2 confirma;
  - una combinación de hora + moneda + estrategia solo cuenta si gana en **las dos** semanas,
    después de costos, y pasa el ajuste por comparaciones múltiples.

## Tu tarea cada día

El dueño te pega este texto:

> Eres el auditor independiente de Trading Intelligence AI (repo
> `tatopozot-rgb/trading-intelligence-ai`, rama `ccr-b66a9a9e-okj2pl`). Lee
> `docs/prompts/GPT_WORK_HORARIOS.md` y `docs/PREREG_HORARIOS.md`. Cada día abre el reporte
> más nuevo en `docs/experimento_horarios/` (`AAAA-MM-DD.md` y `.json`) y escríbeme, en
> español y en no más de 10 líneas:
> 1. Cómo fue la ventana de 07:00 a 10:00 (hora de Ecuador). Después, las 3 mejores y las 3
>    peores horas del día (todas las monedas juntas), con el resultado neto después de costos,
>    en hora de Ecuador.
> 2. Las 3 mejores y las 3 peores monedas (todas las horas juntas).
> 3. Si alguna combinación hora + moneda + estrategia va bien **en los días acumulados** y no
>    solo hoy.
> 4. Cualquier cosa rara: días sin datos, cifras imposibles, cambios de regla, o resultados que
>    no cuadran entre el `.md` y el `.json`.
> 5. Una frase honesta: ¿hay ventaja después de costos o todavía es ruido?
>
> No recomiendes operar con dinero real antes del día 14. Un buen día suelto no prueba nada.
> No ejecutas órdenes ni tocas claves.

## Al final (día 14)

El líder aplica la regla registrada y le presenta al dueño:
- qué horas y qué monedas pasaron, si alguna pasó;
- cuánto ganaron o perdieron, después de costos;
- su propuesta para la sesión real, con su autorización escrita.

Si nada pasa la regla, se dice así: operar a esas horas no tiene ventaja comprobada.

Los reportes de los 14 días anteriores al inicio están marcados como **"referencia: datos
pasados"**. Sirven para orientarse, pero no deciden.
