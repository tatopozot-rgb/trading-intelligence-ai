---
type: estado
tags: [estado-actual, futuros, mesa]
status: living
---

# Estado actual — Trading Intelligence AI

> **Regla del dueño (2026-10-10):** "deben revisar obsidian y git para no revisar todo el hilo y solo
> donde se quedaron". Cada agente empieza leyendo **Obsidian "Estado actual"** (`09 Checkpoints/Memoria
> viva.md`, sección de arriba) y **este archivo**, y sigue desde aquí. No hace falta releer la
> conversación ni el historial viejo.
>
> Las novedades se anotan en `docs/CHECKPOINT.md`. El historial anterior al 2026-10-10 está en
> `docs/archivo/`.

Actualizado: 2026-10-10 (Claude Leader).

## 1. Qué opera y dónde

| Mercado | Estado | Cómo |
|---|---|---|
| **Binance Futuros USDⓈ-M** (principal) | Listo. Con dinero real **desde el lunes**, cuando el dueño conecte la clave nueva con Futuros y escriba su frase a Claude local. | `python -m trading_intelligence.live.binance_futures --modo real`. Hasta entonces se puede correr en `--modo shadow` (precios reales, sin dinero). |
| **XM / MetaTrader 5** | Listo para DEMO; el dueño lo instala y conecta el lunes. | `python -m trading_intelligence.live.xm_auto`. El dinero real va en la fase 3, con la frase del dueño y los límites de XM. |
| **Binance Spot** | En pausa. Orden del dueño: "no vuelvas a comprar criptos" salvo en una alcista brutal. | Si el dueño escribe "para" a Local, se detiene sin vender. El vigilante `market_watch` avisa si BTC entra en una alcista brutal. |

Las dos plataformas usan **el mismo sistema** (`live/two_way.py`), porque "los 2 mercados son futuros".

## 2. Límites aprobados por el dueño (Futuros)

Los límites están en `config/futures_limits.json`, con sus palabras citadas:

| Regla | Valor |
|---|---|
| Riesgo por operación | **1% a 15%** de la cuenta, según la calidad de la señal. Nunca sube por pérdidas (sin martingala). |
| Tamaño máximo por posición | **50%** de la cuenta. Todas las posiciones juntas caben en el margen libre. |
| Apalancamiento | 1x, margen aislado, modo unidireccional |
| Posiciones a la vez | 3 |
| Límite de pérdida de la sesión | 45% (banda del dueño 20–50%). 2 USD antes, avisa y pausa las entradas; `continuar` las reanuda. |
| Meta de la sesión | +58%: cierra todo y termina |
| Stop y meta | Leídos del mercado en cada entrada (3–15%) y puestos en Binance. Desde +1R, el stop sigue la ganancia a R/2. |
| Pérdida máxima de una operación | 50% × 15% = **7,5%** de la cuenta |

## 3. Horario (orden del dueño)

- **07–10 y 17–19 (Ecuador): sin parar.** Decide cada 30 segundos.
- **Fuera de esas horas:** decide cada 5 minutos.
- **Todos los días, 24/7:** el Scout revisa cada 30 segundos y, si ve algo, avisa al Chief para que lo
  evalúe al momento. El horario de revisión no cambia por esto.
- **Con una operación abierta:** su bot la revisa cada 30 segundos en la cuenta y avisa su estado por
  Telegram cada 2 minutos.

## 4. La mesa de trading (6 agentes, `live/desk.py`)

| Agente | Qué hace |
|---|---|
| **Scout** | Busca volumen anormal (≥2x) o un movimiento fuerte (≥1,5% en 15 min) 24/7 y avisa al Chief. |
| **News** | Titulares recientes de la moneda, de medios fijos (CoinDesk, Cointelegraph), con enlace y hora. Solo dan contexto: nunca abren una operación. |
| **Sentiment** | Mide la financiación (el lado saturado paga), los top traders de Binance y el índice de miedo y codicia. Da un puntaje de −1 a +1. |
| **Charts** | Señal "tendencia_rango" en los dos sentidos, más la tendencia de 1 hora y los top traders. Fija el stop y la meta según el mercado. |
| **Escéptico** | Reglas fijas de `config/desk_rules.json`, que no decide una IA: beneficio/riesgo mínimo de 1,5:1, nada de stops pegados a números redondos, nada contra una financiación saturada ni contra un sentimiento muy en contra. Cada veto se anota y se mide (¿evitó una pérdida?). |
| **Chief** | El motor: junta todo, fija el riesgo de 1–15%, ejecuta, ignora o vigila, y escribe el diario de la mesa (Markdown para Obsidian). |

**Bots por posición:** cada posición abierta tiene su propio bot ("🤖 Bot SOLUSDT"). Ese bot la revisa,
mueve su stop y avisa de su estado.

**Telegram nunca dice algo falso.** Un aviso de "compré", "vendí" o "se cerró" sale solo después de
**leer la cuenta 2 veces** y que las dos lecturas coincidan. Si no coinciden, el aviso lo dice.

**Interruptor de emergencia:** con 3 fallos seguidos de conexión, no abre nada nuevo hasta que la
conexión vuelva. Los stops siguen puestos en el servidor.

## 5. Medición con datos reales

- `backtesting/two_way_backtest.py` y el workflow "Futuros en los dos sentidos" se corren cada lunes y
  a pedido.
- Repiten los últimos 30 días con las reglas en vivo, el riesgo de 1–15%, los top traders y la
  financiación reales, y la mesa con sus vetos.
- Los reportes quedan en `docs/two_way_backtest/`.
- Resultado con el modelo de hoy (2026-09-10 a 2026-10-10, 37 USDT, riesgo de 1–15%, con comisiones y
  financiación reales):

  | Variante | Operaciones | Acierto | Resultado | Caída máx. |
  |---|---|---|---|---|
  | `regimen` | 942 | 23% | −45% (tocó el límite) | 45% |
  | `tendencia_rango` | 512 | 36% | −24% | 25% |
  | `tendencia_rango_1h` | 138 | 36% | −6% | 14% |
  | `tendencia_rango_1h_top` (señal por defecto) | 19 | 63% | +8,8% | 6,6% |
  | **`mesa`** (lo que corre en vivo: señal + mesa) | 25 | 64% | **+17,3%** | 12,7% |

- Lo que en vivo se usa (`mesa`) fue lo mejor, pero con solo 25 operaciones en 30 días: es poca muestra
  para confirmarlo. Todas sus operaciones fueron compras; ninguna venta en corto pasó los filtros.
- El Escéptico vetó más operaciones que habrían ganado (1565) que las que habrían perdido (1040). Sus
  reglas se revisan con más datos antes de cambiarlas.
- El resultado se lee como una comparación entre variantes, no como una promesa.

## 6. Lunes: checklist para operar con dinero real

1. El dueño crea la **clave nueva de Binance con Futuros**: lectura y Futuros, IP restringida, **sin
   retiros**. La guarda él mismo en Windows como `BINANCE_FUTURES_API_KEY` y
   `BINANCE_FUTURES_SECRET_KEY`.
2. Revisa que la cuenta de futuros esté en modo **unidireccional (One-way)** y que tenga saldo.
3. Claude local actualiza a `main` y corre `binance_futures --modo real --una-vez`. Esa pasada
   comprueba la clave, el modo y el saldo, y toma una decisión.
4. Con la frase del dueño escrita a Local, lo deja corriendo con su vigilante.
5. XM: el dueño instala MT5 (DEMO) e inicia sesión él mismo. Local corre `cuenta`, `fichas`, la prueba
   de `xm_demo` y después `xm_auto`.

### Pendiente que el líder debe recordar al dueño

- **Tablero de operaciones en Notion.** Se arma cuando Futuros lleve unos días operando estable, desde el
  jueves 2026-10-15. El bot del PC escribe en una tabla de Notion cada operación ya verificada en la cuenta.
  Con una sola conexión, a una sola página, y la clave la guarda el dueño en Windows. Telegram sigue siendo el
  aviso al momento y Notion no decide nada. Orden del dueño, 2026-10-10: "tienes que recordarlo porque si no
  yo me olvido".
- **Riesgo:** el dueño confirmó el 2026-10-10 que se mantienen sus porcentajes: "1% no es nada, debe ser 15%
  y los porcentajes que yo ya puse". Sigue el 1–15% según la calidad de la señal, como dice
  `config/futures_limits.json`. En la prueba de 30 días, el riesgo medio fue 12,9%.

## 7. Reglas que nunca cambian

- Sin retiros ni transferencias automáticas. Ninguna clave en GitHub, Notion, Obsidian ni en los logs.
- El dinero real se mueve solo con la frase del dueño escrita a Claude local.
- Nadie salta el motor de riesgo. Sin martingala, y nunca se sube el riesgo para recuperar pérdidas.
- Cambiar `config/futures_limits.json` o `config/live_limits.json` exige la aprobación escrita del dueño.

## 8. Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Motor común | `trading_intelligence/live/two_way.py` |
| Mesa (6 agentes) | `trading_intelligence/live/desk.py`, reglas en `config/desk_rules.json` |
| Señales | `trading_intelligence/strategy/two_way_signals.py` |
| Binance Futuros | `trading_intelligence/live/binance_futures.py`, límites en `config/futures_limits.json` |
| XM | `trading_intelligence/live/xm_auto.py`, `xm_demo.py`, `xm_mt5.py` |
| Spot (en pausa) | `trading_intelligence/live/operator.py` |
| Instrucciones para Claude local | `docs/prompts/CLAUDE_LOCAL_LIVE_OPERATOR.md` (4h: futuros y mesa) |
| Automatización y memoria | `docs/AUTOMATIZACION.md` |
| Subagentes de análisis (no ejecutan) | `.claude/agents/` |
| Historial anterior | `docs/archivo/` |
