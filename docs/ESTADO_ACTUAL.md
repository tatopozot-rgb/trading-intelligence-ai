---
type: estado
tags: [estado-actual, futuros, mesa]
status: living
---

# Estado actual — Trading Intelligence AI

> **Punto de entrada único.** Cualquier sesión nueva empieza aquí: el líder en la nube, Claude local, un hilo nuevo o
> la versión unificada de Claude que llegue después. Este archivo dice qué corre, quién hace qué y cómo retomar.
> Las novedades se anotan en `docs/CHECKPOINT.md` y las fallas en `docs/INCIDENTES.md`. La misma información está en
> Notion: «Trading Intelligence AI — Operations Center», página «Mapa de la empresa».

Actualizado: 2026-10-14 16:20 UTC (Claude Leader). Main: el merge del PR de este día.

## 0. Hoy en una línea

**Futuros reales corriendo desde el 14-10 a las 09:54 de Ecuador** (31,69 USDT, 1x, aislado, sin retiros). Todavía
sin operaciones, porque el freno de mercado está activo con BTC bajo su media de 50 días. Practican 4 bots en Binance
(dinero ficticio) y 3 agentes en XM demo. Las opciones están **en estudio** (sin operar) hasta dic-2026, con
Interactive Brokers como plataforma candidata.

## 1. Qué opera y dónde

| Bot | Dinero | Dónde corre | Estado |
|---|---|---|---|
| Futuros reales Binance | 31,69 USDT reales, 1x, aislado | PC, tarea `TradingIntelligence-FuturosReal` (cada 10 min) | Corriendo desde 14-10 09:54 |
| Mesa de futuros (práctica 1) | 50 USDT ficticios | PC, tarea propia | Corriendo |
| Práctica 3x | 30 USDT ficticios, 3x | PC, tarea propia | Corriendo |
| Núcleo BTC · 50 y · 50/200 | 30 USDT ficticios cada uno | PC, cada hora | Corriendo |
| Operador XM (ETHUSD, OILCash) | XM demo, 1.000 USD virtuales | PC, `TradingIntelligence-XMDemo` | Corriendo |
| XM Cripto (8 cripto, spread ≤1,5 %) | misma cuenta demo | PC, `TradingIntelligence-XMCripto` | Corriendo |
| XM Índices (US500Cash, AUDUSD, BTCUSD) | misma cuenta demo | PC, `TradingIntelligence-XMIndices` | Corriendo |
| Alarma de mercado | — | PC | Corriendo |
| Binance Spot, vigilante `market_watch`, ciudad 3D | — | — | Detenidos por el dueño |

Todos usan el mismo motor (`live/two_way.py`). XM necesita MT5 abierto con «Algo Trading» en verde. Tras un reinicio del
PC, el dueño entra a Windows y abre MT5.

## 1b. Organización: quién hace qué

| Quién | Dónde | Qué hace |
|---|---|---|
| **Líder** (Claude en la nube) | sesión `session_01AaCojVisJUfr9cmMs47yJA`, rama `ccr-b66a9a9e-okj2pl` | Ordena, programa, revisa y une PRs, escribe los reportes. No toca el PC ni mueve dinero. |
| **Claude local** | PC del dueño, Remote Control `qosmio-wp-squishy-fairy` (`session_01W2LeDkr7cYE5bLEzwReHsx`) | Corre los bots, guarda las claves en Windows y ejecuta las órdenes del líder. El dinero real solo arranca con la frase del dueño escrita en su chat. |
| **GPT** | Notion, Task Board (agente «Trading Codex») | Auditor externo con créditos limitados, una pasada por tarea. Se le ordena por Notion. |
| **Agentes de análisis** | `.claude/agents/` | Scout, News, Sentiment, Charts, Escéptico, Chief (mesa); Compliance; Verificador; Maestro XM; Director de Operaciones; Analista de Opciones; Riesgo de Opciones. Ninguno ejecuta órdenes. |

**Rutinas del líder** (claude.ai, en esta sesión; hora de Ecuador):

| Rutina | Cuándo | Qué hace |
|---|---|---|
| `trig_01FnSxUzGVSSS92BiPESWF2R` | diario 06:52 | Inteligencia de mercado, una lección de teoría, un bot público estudiado. |
| `trig_01BkPE7QgQKuBiXYUUZHD5vE` | cada 2 h | Lee los mensajes de Local y actúa. |
| `trig_013qzbkeQXYpG5jgscp4KWt6` | cada 12 h | Monitor general. |
| `trig_018iafb7jhFaL48gb5HWs9Rz` | diario 18:41 | Escribe `docs/reportes/<fecha>.md` para el PDF del dueño. |
| `trig_01Q47Xpwz7FxspbqUhPawX6y` | sábados 10:23 | Estudio del mercado de opciones (ver `docs/opciones/`). |
| `trig_01APn5fTGh7g42ZX1R818rXc` | 13-11 09:00 | Recordatorio al dueño: avance del estudio de opciones. |

**Tareas de Local** (en el PC): revisión diaria con Verificador y Maestro XM a las 19:07; Director de Operaciones los
domingos a las 19:03; reporte PDF por Outlook a las 19:30 cuando el dueño lo confirme.

## 1c. Cómo retomar (sesión nueva o actualización de Claude)

1. Lee este archivo, las últimas secciones de `docs/CHECKPOINT.md` y `docs/INCIDENTES.md`.
2. En Notion, lee «Mapa de la empresa» y el Task Board (lo pendiente de GPT y del dueño).
3. Si no existe la sesión de Local, el dueño ejecuta `claude remote-control` en el PC. El líder no puede crear sesiones
   en el PC.
4. Vuelve a crear las rutinas de la tabla de arriba si no existen. Sus textos están en `docs/AUTOMATIZACION.md`.
5. Nunca arranques dinero real por tu cuenta: solo Local, con la frase del dueño en su chat.

## 2. Límites aprobados por el dueño (Futuros)

Los límites están en `config/futures_limits.json`, con sus palabras citadas:

| Regla | Valor |
|---|---|
| Riesgo por operación | **1% a 15%** de la cuenta, según la calidad de la señal. Nunca sube por pérdidas (sin martingala). |
| Tamaño máximo por posición | **50%** de la cuenta. Todas las posiciones juntas caben en el margen libre. |
| Apalancamiento | 1x, margen aislado, modo unidireccional |
| Posiciones a la vez | 3 |
| Límite de pérdida de la sesión | 45% (banda del dueño 20–50%). 2 USD antes, avisa y pausa las entradas; `continuar` las reanuda. |
| Meta del mes (2026-10-11) | Opera sin parar todos los días hasta ganar +58% en el mes; entonces cierra todo y retoma el día 1 del mes siguiente. Cuando el dueño deposite más, puede fijar la meta en dólares (`monthly_goal_usd`). |
| Stop y meta | El stop se lee del mercado en cada entrada (3–15%). La meta queda a **3 veces lo que se arriesga** (desde el 2026-10-12), sin piso ni modo alcista. Los dos van puestos en Binance. Desde +1R, el stop sigue la ganancia a R/2. |
| Pérdida máxima de una operación | 50% × 15% = **7,5%** de la cuenta. El "1–15%" es lo que pide la señal; el riesgo real lo limitan la posición de 50% y el apalancamiento 1x. |

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

**Ganancia que paga el riesgo (2026-10-12):** la meta de cada operación es 3 veces lo que arriesga. En 60 días de datos reales ganó casi lo mismo que la meta del mercado (+50,6% frente a +57,8%) con la mitad de la caída (9% frente a 18%); en los últimos 30 días ganó más (+29,9% frente a +25%). Detalle en `docs/APRENDIZAJE_FUTUROS.md` §3c.

**El líder decide la estrategia (2026-10-12):** el dueño pidió "busca estrategias y olvida lo que yo dije y mis marcas". La mesa corre ahora exactamente lo que ganó en la prueba (`mesa_r3`): se quitaron el piso de 3% (con stops de 3-15%, una meta a 3 veces ya es 9% o más) y el modo alcista (costó unos 9 puntos en 60 días). Ambos se siguen midiendo cada lunes. La búsqueda de estrategias nuevas sigue `docs/research/PROTOCOLO.md`: 365 días, fuera de muestra, costes reales, y comparación contra `mesa_r3`.

**Freno de riesgo (2026-10-13):** la práctica solo compra, y solo mientras BTC cierra sobre su media de 50 días; si no, no abre nada y cierra lo abierto (`regime_btc_sma: 50`). En dos años de datos no volvió ganadora a la mesa, pero recortó el año malo de −65% a −7% (`docs/research/mesa/`). Junto a la mesa corre en práctica el **Núcleo BTC** (`live/core_btc.py`): BTC sobre su media de 50 días o efectivo; en 6 años creció ×9,4 frente a ×7,4 de tener BTC, pero perdió −49% en 2022.

**Bots por posición:** cada posición abierta tiene su propio bot ("🤖 Bot SOLUSDT"). Ese bot la revisa,
mueve su stop y avisa de su estado.

**Telegram nunca dice algo falso.** Solo llega lo que la cuenta confirma: compras, ventas, cierres, el estado de cada posición, avisos de límite y la meta, cada uno revisado 2 veces. El Scout, el Escéptico y los movimientos del stop quedan en la consola y en el diario de la mesa (orden del dueño, 2026-10-11). Un aviso de "compré", "vendí" o "se cerró" sale solo después de
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

## 6. Pendiente que el líder debe recordar

- **IP de la casa:** la clave de futuros solo acepta la IP de confianza. Si el internet cambia de IP, Binance da -2015
  y el bot real no arranca (falla cerrado). El dueño agrega la IP nueva en Binance. Si se repite: IP fija.
- **Alejandro Cardona:** revisar sus notas o estrategia cuando el dueño las consiga (`docs/opciones/ESTUDIO.md`).
- **Reporte PDF por Outlook:** espera el «sí» del dueño en el chat de Local y el Outlook clásico con su cuenta abierta.
- **Tablero de operaciones en Notion:** se arma cuando Futuros lleve unos días estable, desde el 15-10. Orden del dueño,
  2026-10-10: «tienes que recordarlo porque si no yo me olvido».
- **Opciones:** recordar al dueño el 13-11 el avance del estudio; decidir en dic-2026 si se prueba en práctica.
- **Decimales:** redondear la meta en los avisos de la práctica 3x (va con el próximo cambio del motor).

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
