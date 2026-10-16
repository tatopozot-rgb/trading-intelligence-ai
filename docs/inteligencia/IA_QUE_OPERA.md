# Traders y bots que operan con Claude u otras IA (revisión 2026-10-16)

Orden del dueño (2026-10-16): "he visto en línea traders con Claude que lo están logrando ... muchos en 1 mes
lograron increíbles resultados, intenta revisarlos, busca en repertorios públicos algo".

Se separa cada caso en dos clases:

- **Verificable:** dinero real con historial público que cualquiera puede revisar (billetera en cadena, cuenta
  auditada, señal verificada).
- **No verificable:** backtest, captura de pantalla, nota de prensa o "me fue bien" sin historial.

## Resumen en simple

1. **No encontramos ningún caso verificable de una IA que gane de forma sostenida.** Los pocos casos con dinero
   real y historial público perdieron o no le ganaron a comprar y mantener.
2. **Los "increíbles resultados en 1 mes" que circulan no tienen historial**, o la IA solo escribió el código y la
   ganancia vino de otra cosa (copiar a otros, arbitraje en apuestas deportivas).
3. **Los estudios serios de 2025-2026 dicen lo mismo:** cuando se cuentan costos, más años y el número de pruebas,
   la ventaja desaparece.
4. **No hay candidata nueva para probar.** Las reglas concretas que salen de estos casos ya las probamos y
   fallaron (ruptura de volatilidad, tendencia).
5. **Un aviso importante:** un backtest de Claude decidiendo sobre 2024-2026 no vale, porque el modelo ya "leyó"
   lo que pasó esos años. La única prueba honesta de una IA que decide es hacia adelante, con dinero ficticio.

## Casos con dinero real e historial público

| Caso | Qué hizo | Resultado | Verificable |
|---|---|---|---|
| **Alpha Arena, temporada 1** (nof1.ai, 18-oct → 3-nov-2025) | 6 IA con 10.000 USD reales cada una, futuros perpetuos cripto en Hyperliquid (BTC, ETH, SOL, BNB, XRP, DOGE), apalancamiento libre | Qwen3 Max +22%, DeepSeek +5%, **Claude Sonnet 4.5 −42%**, Gemini −46%, Grok −58%, GPT-5 −59%. 4 de 6 perdieron | Sí: billeteras públicas en cadena. Pero son 2 semanas y una sola corrida por modelo: es suerte hasta que se demuestre lo contrario |
| **Alpha Arena, temporada 1.5** (nov-dic 2025, acciones de EE. UU.) | 8 IA, 4 modos (normal, "monje", ver a los rivales, apalancamiento máximo) | Solo un modelo (Grok 4.20) ganó, ~+12% en promedio; los demás perdieron | Parcial: anuncios de nof1. Desde agosto 2026 los modelos ya no operan; no hay temporada 2 publicada |
| **ChatGPT Micro-Cap Experiment** (Nathan Smith, GitHub, 2025-26) | ChatGPT elige acciones pequeñas con 100 USD reales, 6 meses | Iba +24% en agosto 2025 (titulares). En enero 2026: 83 USD (−17%), con una caída de −50%; el S&P 500 dio +10% | Sí: lo publica cada semana. **Es el ejemplo perfecto de "gran resultado en 1 mes" que después se cae** |
| **"Claude convirtió 1 USD en 3,3 millones"** en Polymarket (cuenta sovereign2013) | Apuestas deportivas a gran velocidad, 37.000 apuestas | La cuenta es pública, pero nada prueba que la maneje Claude. Es arbitraje deportivo, no trading de BTC ni oro | No (la parte "Claude") |
| **"Claude convirtió 2.000 en 12.000 en una noche"** (Finbold, abril 2026) | Claude escribió un bot que copia a otros apostadores en Polymarket | Una sola operación. Claude no decidió nada; copió a quien ya iba ganando (sesgo del sobreviviente) | No |
| **"Bots de Claude ganan el 68,4% en Polymarket"** (mayo 2026) | Cifra de "la comunidad"; cuenta de 1.430 → 238.006 USD en 11 días | El PDF que la promovía tenía capturas falsas | No |

Dato de contexto: Bloomberg revisó todas las billeteras de Polymarket desde 2025. La mayoría de la gente pierde y
la mayor parte de la ganancia se la llevan unos pocos bots automáticos. Nada indica que sean "IA que adivina".

## Repositorios públicos más citados

| Repositorio | Qué es | Resultados en vivo |
|---|---|---|
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (~50 mil estrellas) | Varios agentes LLM "estilo Buffett, Munger..." que opinan sobre acciones | Ninguno. Dice ser educativo y no opera |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | Mesa de agentes LLM (analistas, investigador alcista y bajista, operador, riesgo) | Ninguno propio. Reproducido por terceros en 2025-26 con costos: Sharpe 0,22 y pierde contra comprar y mantener en 4 de 5 acciones ([*The Alpha Illusion*](https://www.alphaxiv.org/abs/2605.16895)) |
| [NoFxAiOS/nofx](https://github.com/NoFxAiOS/nofx) (~11 mil estrellas) y réplicas de Alpha Arena (Hyper-Alpha-Arena y otras) | Bots donde un LLM decide entradas en futuros cripto | Tablas de competencia sin auditoría; ninguna muestra historial verificable que gane |
| Asesores "aprobados por Claude" en MQL5 (por ejemplo *Gold Verdict AI XAUUSD M5*) | Robot para oro | Solo backtest (Sharpe 3,0, caída 7,8%). Sin señal en vivo, 0 reseñas, 297 USD. Es publicidad |

## Estudios serios (2025-2026)

- **Gençay, 2026** ([arXiv 2608.27734](https://arxiv.org/pdf/2608.27734)): un LLM busca estrategias solo, con
  herramientas que impiden ver el futuro, y cada intento se anota y se castiga con el Sharpe deflactado (el mismo
  método que usamos nosotros). **Ninguna estrategia hallada por GPT-4.1 ni por Claude Sonnet 5 pasó.** La mejor de
  GPT-4.1 tenía Sharpe 1,69 en diseño y 0,18 fuera de muestra (+4,7% contra +40,8% de comprar y mantener). Cinco
  corridas independientes terminaron en la misma familia, la **ruptura de volatilidad**, y ninguna pasó el Sharpe
  deflactado (0,15 a 0,29). Un sistema humano de oro en producción también falló fuera de muestra. Solo pasaron
  "comprar y mantener" y la canasta pareja de ETF.
- **FINSABER, 2025** ([arXiv 2505.07078](https://arxiv.org/html/2505.07078v3)): con 20 años y más de 100
  acciones, la ventaja de las estrategias con LLM "se deteriora mucho". Son demasiado prudentes cuando el mercado
  sube y demasiado agresivas cuando baja.
- **LiveTradeBench, 2025** ([arXiv 2511.03628](https://arxiv.org/html/2511.03628v1)): 21 LLM operando en vivo 50
  días. Ser el mejor modelo en los rankings de chat no significa operar mejor.
- **The Alpha Illusion, 2026** ([arXiv 2605.16895](https://www.alphaxiv.org/abs/2605.16895)): los buenos números
  de los agentes LLM se explican por contaminación (el modelo ya vio ese periodo), costos que no se cuentan y
  muestras cortas. Recomienda usar el LLM solo para leer información, y dejar las señales, el riesgo y la
  ejecución a módulos cuantitativos fijos. **Es justo como está armado nuestro sistema.**
- **Desarrollador con Claude Code** (marzo 2026, citado por [algotrader.ch](https://algotrader.ch/ai-trading/claude-ai-trading/)):
  de 15 estrategias, el backtest descartó 14; la que quedó ganaba 0,32% en backtest y en vivo acertó el 60% de las
  veces pero perdió dinero.

## Qué se puede sacar de esto

- **Lo que hacen los que pierden menos:** pocas operaciones, stop y meta definidos antes de entrar, tamaño chico y
  poco apalancamiento. En Alpha Arena, Gemini hizo 238 operaciones y pagó en comisiones más del 13% del capital.
  Nuestra mesa ya funciona así (motor de riesgo, stop y meta obligatorios, 1x).
- **Por qué no probamos candidatas esta vez:** el protocolo pide reglas fijas que se puedan correr sobre 2024-25
  y 2025-26. Las reglas fijas que salen de estos casos son la ruptura de volatilidad (probada el 15-oct, perdió los
  dos años) y la tendencia (Donchian, EMA, tsmom, EWMAC, Faber: probadas, no pasaron). Correrlas otra vez solo
  subiría la N del Sharpe deflactado sin aportar nada. Por eso **no se agregan filas al registro de pruebas**.
- **Si se quiere probar "Claude decide":** la única forma honesta es hacia adelante, con dinero ficticio, bajo el
  motor de riesgo, y medirlo contra la mesa. No puede cumplir el listón de dos años, así que solo serviría como
  observación (como "Londres en oro"). Lo decide el líder.

## Fuentes

- Alpha Arena T1: [Forklog](https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/),
  [HelloACM](https://helloacm.com/alpha-arena-how-ai-performs-in-the-real-crypto-market/),
  [Buildix](https://www.buildix.trade/blog/nof1-alpha-arena-lessons-ai-trading-byok-strategy-advisor-2026).
  Algunas notas de prensa intercambian el 1.º y 2.º puesto (Qwen y DeepSeek) según la hora de la foto; se usa el
  cierre que publicó nof1.
- Alpha Arena T1.5 y estado 2026: [Forklog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/),
  [TradeRank](https://www.traderank.ai/blog/alpha-arena-alternatives-2026).
- Micro-cap: [Benzinga](https://www.benzinga.com/markets/equities/25/08/46783783/redditors-100-chatgpt-day-trading-experiment-trounces-two-benchmark-indexes-with-24-returns-here),
  [Hackernoon semana 25](https://hackernoon.com/can-chatgpt-outperform-the-market-week-25).
- Polymarket: [Medium (Rondanini)](https://medium.com/@info_38412/claude-didnt-earn-10k-overnight-and-that-isn-t-how-markets-work-b2bb2717aa76),
  [Let's Data Science](https://letsdatascience.com/news/claude-posts-684-success-rate-on-polymarket-b7bc0ad1),
  [MEXC](https://www.mexc.com/news/1003307),
  [Bloomberg Government](https://news.bgov.com/crypto/prediction-market-users-suffer-broad-losses-as-bots-reap-gains).
- Repositorios: [Menon Lab](https://themenonlab.blog/blog/ai-finance-github-repos-march-2026),
  [MQL5](https://www.mql5.com/en/market/product/178653).
