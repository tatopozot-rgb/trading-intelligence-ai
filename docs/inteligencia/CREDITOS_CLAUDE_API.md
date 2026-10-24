# Cómo usar los 100 USD de créditos de la API de Claude (estudio 2026-10-22)

Pedido del dueño (2026-10-22): poner ~200 USD en XM real sin retirar hasta que crezca, "maximizar eso con más
operaciones, más bots, más todo", y ver cómo usar los 100 USD de créditos de la API de Claude para lograrlo.

## Resumen en simple

1. **Los créditos no crean ganancia por sí solos.** Lo que hace ganar es una regla que pasa el método (ganarle a la
   mesa en 2024-25 y 2025-26 con costos y pasar el Sharpe deflactado). Ya revisamos "Claude decide la operación"
   (`IA_QUE_OPERA.md`): no hay ningún caso verificable y su backtest está contaminado, porque el modelo ya "leyó"
   esos años.
2. **Más operaciones y más bots no suman si cada uno no pasó la prueba.** Cada operación paga spread; con 200 USD
   los lotes mínimos de XM dejan ~1 mercado a la vez. Más bots sin ventaja = más formas de perder.
3. **Donde sí ayudan los créditos: proteger y vigilar**, no decidir entradas. Cuatro usos útiles cuestan juntos
   **~2 a 5 USD al mes**, así los 100 USD duran más de un año y medio.
4. **Lo que no conviene:** que Claude decida compras/ventas cada pocos minutos. Cuesta ~60 USD al mes por bot (se
   come los créditos en menos de 2 meses) y no se puede probar de forma honesta.

## Precios usados (lista oficial de Anthropic, octubre 2026)

| Modelo | Entrada por millón de tokens | Salida por millón | Para qué |
|---|---|---|---|
| Claude Haiku 5.5 | 0,10 USD | 0,50 USD | Leer registros y clasificar, barato |
| Claude Sonnet 5.5 | 2 USD | 10 USD | Buscar en la web y razonar con cuidado |
| Claude Opus 5.5 | 4 USD | 20 USD | Trabajo difícil y de una sola vez |

- Modo lote (Batch): 50% de descuento si la respuesta puede esperar hasta 24 h.
- Caché de instrucciones: lo repetido cuesta ~10% la segunda vez.
- Búsqueda web: unos 10 USD por cada 1.000 búsquedas, más los tokens que se leen (precio aproximado, revisar en la
  consola antes de prender).
- 1 millón de tokens son unas 700.000 palabras.

## Usos recomendados (de más a menos útil)

| # | Uso | Qué hace | Modelo | Costo al mes | Toca entradas |
|---|---|---|---|---|---|
| 1 | **Revisión diaria de riesgo** | Cada noche lee `live_runs` y los reportes, y busca cosas raras: posición sin stop, freno abierto cuando no debía, saldo que no cuadra, bot callado. Si encuentra algo, manda alarma por Telegram | Haiku 5.5; pasa a Sonnet 5.5 solo si hay alarma | ~0,50 a 1 USD | No |
| 2 | **Calendario de eventos** | Una vez por semana busca en la web Fed, IPC, empleo, vencimientos de opciones y feriados, y propone cambios a `config/eventos.json` (el freno que solo **bloquea** entradas). Un humano o el Líder revisa antes de unir | Sonnet 5.5 + búsqueda web | ~0,60 USD | Solo bloquea |
| 3 | **Método del amigo** | Cuando haya videos o el Zoom: de la transcripción saca reglas claras (entrada, stop, salida, días que no opera) para preregistrarlas y probarlas | Opus 5.5, una sola vez | ~3 USD por tanda de 20 videos | No (se prueba antes) |
| 4 | **Resumen semanal para Renato** | Arma en español simple qué pasó en la semana con cada bot, sin saldos en el repo | Haiku 5.5 | ~0,10 USD | No |

**Total: ~2 a 5 USD al mes.** Con 100 USD alcanza para 20 a 50 meses.

El uso 1 habría detectado el incidente del 15 al 19-10 (`INCIDENTES.md`): el reporte decía que el freno de BTC
estaba cerrado y en verdad estaba abierto. Una segunda lectura independiente de los registros sirve justo para eso.

Cuentas aproximadas:

- Uso 1: ~50.000 tokens de registros por noche × 30 noches = 1,5 millones → 0,15 USD con Haiku; unas pocas
  revisiones con Sonnet cuando hay alarma suben el total a ~1 USD.
- Uso 2: ~5 búsquedas + ~50.000 tokens leídos por semana → ~0,15 USD por semana.
- Uso 3: 20 videos de 1 h ≈ 300.000 tokens de texto → ~1,20 USD de entrada + ~1,20 USD de salida. Claude lee
  texto, no audio: la transcripción sale de los subtítulos de YouTube o de un programa gratis en la PC.

## Lo que no conviene

| Idea | Por qué no |
|---|---|
| Claude decide cada entrada (cada 5 min) | ~288 consultas al día por bot ≈ 60 USD al mes. Sin historial verificable en ningún lado; el backtest no vale porque el modelo conoce el pasado |
| "Claude filtra noticias y deja entrar o no" como señal | Ya probado: reversión tras noticia y opciones como señal fallaron. Un filtro que cambia entradas es una estrategia nueva y debe pasar el método completo |
| Que Claude suba el tamaño o el apalancamiento | Prohibido por las reglas: nadie salta el motor de riesgo, sin martingala |
| Vigilancia de bots cada 5 min con IA | Ya lo hace VigilarBots sin costo y sin fallar. La IA sirve para la lectura de la noche, no para el latido |
| Buscar muchas estrategias nuevas con la API | Cada variante mirada suma a la N del Sharpe deflactado. La búsqueda ancha está prohibida por el método |

## Si algún día se quiere probar "Claude decide"

La única prueba honesta es hacia adelante: preregistrada en `docs/research/REGISTRO_PRUEBAS.md`, solo en demo,
con reglas fijas, y con meses de datos antes de concluir. Usando Haiku 5.5 una vez al día en lugar de cada 5 min
costaría menos de 1 USD al mes. No se recomienda ahora: necesita meses para decir algo y hoy no hay ninguna pista
pública de que funcione.

## Reglas para prender cualquiera de estos usos

1. **La clave la pone Renato en la PC** como variable de entorno `ANTHROPIC_API_KEY` de Windows. Nunca en el repo,
   en Notion, en los registros ni en Telegram.
2. **Ponerle un tope de gasto mensual en la consola de Anthropic** (por ejemplo 10 USD). Si algo se descontrola, se
   corta solo.
3. **La IA solo puede avisar o bloquear entradas.** Nunca abre, agranda ni cierra operaciones. El motor de riesgo
   sigue siendo el que decide.
4. Si la API falla o no hay créditos, el bot sigue igual que hoy (la IA es un extra, no una pieza necesaria).
5. El código de los bots lo hace el hilo de Rutinas del Líder; Quant no toca `live/` ni `config/`.

## Orden sugerido

1. Uso 1 (revisión diaria de riesgo): es el más útil para proteger los 200 USD reales.
2. Uso 2 (calendario de eventos): reemplaza el trabajo a mano en `config/eventos.json`.
3. Uso 3 cuando llegue el material del amigo.
4. Uso 4 si Renato quiere el resumen semanal.
