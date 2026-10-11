---
type: plan
tags: [futuros, aprendizaje, practica, riesgo]
status: living
---

# Aprender a manejar futuros — plan del líder

Orden del dueño (2026-10-11): "tu última tarea con dinero en las dos cuentas es aprender a manejar el
mercado futuros ... en un futuro puedas arriesgar por operación hasta el 15-30% ... Eres el gerente, esto
funciona por ti." Empieza con saldo ficticio, Binance 30 y XM 30. Después de conectar XM, se pasa a dinero
real "al 100%, con lo aprendido".

## 1. Quién hace qué (sin gastar IA en lo que puede hacer un bot)

| Quién | Qué hace | Cuándo | Costo de IA |
|---|---|---|---|
| **Bots en el PC** (Claude local los deja corriendo) | Operan la práctica 24/7 con precios reales: Binance desde ya, XM desde el lunes con una cuenta DEMO de 30 USD. Usan el mismo motor, la misma mesa y los mismos límites que el dinero real. | 24/7 | Ninguno |
| **Reporte diario** (`live/shadow_report.py`) | Mide la práctica: acierto, neto, esperanza en R, factor de beneficio, caída, por moneda, por lado, por salida y los vetos. | 19:30 Ecuador, lo corre el PC y lo sube a GitHub | Ninguno |
| **Prueba con datos reales** (`backtesting/two_way_backtest.py`) | Repite 30 días con las reglas en vivo y, además, los **escenarios de riesgo** (1x/50%; 3x/150%; 5x/250% con riesgo de 15–30%). | Cada lunes y a pedido (GitHub Actions) | Ninguno |
| **Claude Leader** (gerente) | Lee el reporte cada día, decide qué se prueba y qué se corrige, cambia el código con pruebas y le cuenta al dueño solo lo importante. | Una vez al día | Bajo |
| **GPT Work** (desde el 2026-10-14) | Hace el análisis profundo: busca patrones que se repiten y propone **una** mejora medible por semana. | Cada día (corto) y cada semana (profundo) | Medio |
| **Claude local** | Mantiene los bots vivos, sube el reporte, conecta XM y aplica lo que el líder publica en `main`. | Cuando hace falta | Bajo |

## 2. La práctica (saldo ficticio)

- **Binance:** `python -m trading_intelligence.live.binance_futures --modo shadow --capital 30 --diario "<Obsidian>\09 Checkpoints\Mesa práctica"`.
  - Usa precios reales y públicos de Binance, sin clave y sin dinero.
  - Los avisos de Telegram dicen **"🧪 SIMULADO (dinero ficticio)"** y el estado de cada posición llega cada 30 min, no cada 2.
- **XM:** desde el lunes, cuando el dueño instale MT5, con una cuenta **DEMO** de XM (se puede abrir con 30 USD de saldo) y `xm_auto`.
- **Reporte:** cada día a las 19:30 Ecuador, `python -m trading_intelligence.live.shadow_report --capital 30`.
  - El PC sube `docs/shadow_futures/` a la rama `local/practica`.
  - Es dinero ficticio, así que puede ir a GitHub. **Los saldos reales nunca van a GitHub.**

## 3. Arriesgar 15–30% por operación: lo que dicen los números

**Lo primero que hay que saber:** hoy el riesgo "de 1 a 15%" es lo que pide la señal, pero no es lo que se
puede perder de verdad.
- Con apalancamiento 1x y posición máxima de 50%, una operación pierde como mucho 50% × 15% (el stop más
  lejano) = **7,5% de la cuenta**.
- Normalmente pierde mucho menos: con un stop de 4% se pierde el 2% de la cuenta.
- El 12,9% medio de la prueba del 10 de octubre era el pedido. El reporte nuevo muestra también el
  **riesgo real**.

**Para arriesgar de verdad 15–30% hace falta apalancamiento** (3x a 5x). Eso cambia tres cosas:
1. **Dos pérdidas seguidas al 30% dejan la cuenta en 49%** y ya pasan el límite de pérdida de 45% de la sesión.
   Con un acierto de 64%, la probabilidad de dos pérdidas seguidas en algún momento de 25 operaciones es de 93%.
2. **La liquidación:** a 5x, Binance liquida cerca de −19,5%; a 10x, cerca de −9,5%. Un stop del mercado de 15% a
   10x nunca llegaría a cumplirse, porque antes liquida. El motor no abre una operación cuyo stop esté más
   lejos que la liquidación.
3. **Las comisiones y la financiación** se multiplican por el apalancamiento.

**Regla para subir el riesgo** (la propone el líder; la decide el dueño por escrito):
- Solo con evidencia: al menos **100 operaciones** entre práctica y real, **esperanza mayor que +0,3R**,
  **factor de beneficio mayor que 1,5** y una caída máxima menor que 25% **en el escenario más alto, medido en
  la prueba con datos reales**.
- **Por escalones:** 15% → 20% → 25% → 30%. Se sube un escalón solo después de un periodo ganador, **nunca después
  de pérdidas** (sin martingala).
- Cada escalón cambia `config/futures_limits.json` (riesgo y apalancamiento) **con la aprobación escrita del dueño**.
- Si la esperanza baja de 0 en las últimas 30 operaciones, se baja un escalón automáticamente.

## 3b. Meta de 3–5% y modo alcista (orden del dueño, 2026-10-11)

Sus palabras: "si algún día alguna moneda se va en alza debe dejar el trade de largo xq lo que sucedió con bitcoin
puede suceder nuevamente con algo más mientras yo duermo ... arriesgar algo no todo ... en cada operación intente
tener un profit del 3% al 5% ... ese porcentaje después lo controles tu con lo aprendido y lo varies".

- **Meta de 3–5% (pedido inicial; ver la primera medición abajo):** cada operación toma ganancia entre 3% y 5% desde la entrada. Si el mercado marca una meta más
  cerca, se sube a 3%; si la marca más lejos, se baja a 5%. Está en `config/desk_rules.json`
  (`target_min_pct`, `target_max_pct`), y **el líder la ajusta con lo que se mida**.
- **El cuidado que trae:** el Escéptico pide ganar al menos 1,5 veces lo que se arriesga. Con una meta de 5%, el stop
  debe quedar a 3,3% o menos; las operaciones con stops más lejanos se rechazan. La prueba de cada lunes compara
  `mesa` (con la meta) contra `mesa_libre` (sin ella) para saber si conviene.
- **Modo alcista:**
  - Si una moneda subió 25% o más en 14 días, está sobre su media de 20 días y sigue subiendo, su compra **no se
    cierra en la meta**.
  - El stop sigue la ganancia desde +1R, y una bajada de 5 minutos no la cierra.
  - Arriesga lo de siempre según la señal, nunca todo.
  - Las ventas en corto nunca entran en este modo.
- **Antes de entrar:** el vigilante de mercado (`market_watch`, hoy apagado por el dueño) puede volver a avisar de una
  alcista brutal de BTC si el dueño lo pide. El motor revisa cada moneda por su cuenta, una vez por hora.

**Primera medición (2026-10-11, 30 días de datos reales; muestra corta de 22 a 25 operaciones):**

| Variante | Resultado | Caída máx. |
|---|---|---|
| Mesa sin banda de meta (como el 10 de octubre) | **+18,7%** | 12,7% |
| Mesa con meta de 3–5% | +6,1% | 11,8% |
| Mesa con meta de 3–5% y modo alcista | +4,2% | 15,3% |

- **Lo que muestra:** el tope de 5% recortó las operaciones ganadoras, porque las buenas tendencias suelen ir más allá del 5%.
- **Decisión del líder:** se quita el tope y queda el piso de 3%. Ninguna operación busca menos de 3%, y las que traen tendencia pueden ganar más.
- **Se sigue midiendo:** la banda de 3–5% del dueño se mide cada lunes como `mesa_meta_3_5`. Si en algún periodo gana, vuelve.
- **Modo alcista:** se mantiene. En 30 días hubo solo 4 entradas en ese modo, así que la muestra no dice nada todavía. Está para las subidas grandes y raras como la de BTC, que una ventana de 30 días casi nunca muestra.
- **Riesgo real medido:** en promedio se arriesgó cerca de 2% por operación y como máximo 5%. Ya coincide con el 5% máximo que propuso el dueño.
- **Apalancamiento en la misma muestra:**
  - 3x: **+57,8%** y llegó a la meta, con una caída de 18%.
  - 5x con riesgo de 15–30%: +59%, con una caída de 28,7%.
  - Es el camino al riesgo de 15–30%. Se decide con más operaciones y la aprobación escrita del dueño.

## 4. El ciclo diario de aprendizaje

1. Los bots operan y escriben el diario de la mesa.
2. A las 19:30 Ecuador sale el reporte de práctica (y, desde el lunes, el de la cuenta real, solo en porcentajes).
3. El líder lo lee:
   - ¿Hay un error en el código? Lo corrige con pruebas y lo sube en un PR.
   - ¿Hay un patrón? Lo anota como hipótesis; no se cambia nada con menos de 30 operaciones.
4. GPT Work hace el análisis profundo con `docs/prompts/GPT_WORK_FUTUROS.md` y deja su informe en GitHub.
5. Cada lunes, la prueba con datos reales mide la hipótesis. Si mejora fuera de muestra, entra al motor; si no,
   se descarta y se anota por qué.
6. Lo aprendido va a `docs/aprendizaje_futuros/` (una nota por semana) y a "Estado actual" en Obsidian.

## 5. Lo que no cambia

- Sin retiros ni transferencias. Ninguna clave en GitHub, Notion, Obsidian ni en los logs.
- El dinero real se mueve solo con la frase del dueño escrita a Claude local.
- Nadie salta el motor de riesgo. Sin martingala: el riesgo nunca sube para recuperar pérdidas.
