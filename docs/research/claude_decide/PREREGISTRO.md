# Preregistro: «Claude decide» en XM DEMO (experimento hacia adelante)

Escrito el 2026-10-22, **antes de la primera orden**. Pedido del dueño (22-10: el costo no importa, quiere bots que
analicen más con Claude). Decisión del líder: probarlo solo con dinero virtual, porque una prueba con historia de
«Claude decide» está contaminada (Claude ya leyó esa historia; ver `docs/inteligencia/IA_QUE_OPERA.md`). Solo se
puede juzgar hacia adelante. Código: `trading_intelligence/live/xm_claude.py`; pruebas: `tests/test_xm_claude.py`.

## Qué es

- **Dónde:** cuenta DEMO de XM (la misma que usan los otros agentes, con su propio MAGIC «Claude decide»). Nunca
  una cuenta real: el código revisa que sea DEMO antes de cada orden.
- **Mercados:** GOLD y BTCUSD, los mismos de la ruptura de Londres, para comparar en los mismos días.
- **Quién decide qué:** Claude (modelo `claude-opus-5-5`, esfuerzo medio, por la API) lee cada hora cerrada, por
  mercado, las velas de 1 día, 4 h y 1 h con EMA20, EMA50, ATR14 y RSI14, el spread, su posición abierta y sus
  últimas operaciones. Responde COMPRAR, VENDER, ESPERAR, MANTENER o CERRAR, con stop, meta, confianza y razón.
- **Lo que Claude no puede saltar** (lo hace el código, no Claude):
  - stop y meta en cada entrada; stop entre 0,2 % y 5 % del precio; meta entre 1,5 y 6 veces el stop;
  - riesgo fijo de **1 % de 1.000 USD nominales** (10 USD por operación); nunca sube tras perder (sin martingala);
  - tamaño máximo 5 veces el nominal; 2 posiciones abiertas a la vez; 2 entradas por mercado y día;
  - sin entradas nuevas en el día tras −2R; spread, margen y mercado abierto revisados antes de cada orden.
- **Registro:** cada respuesta de Claude, con su razón, su costo y si se ejecutó o se rechazó, queda en
  `live_runs/xm_claude/decisiones.jsonl` en el PC (no en el repo, que es público).

## Gasto

- **Tope: 40 USD al mes en la API**, contado en el código llamada por llamada. Al llegar al tope no se llama más a
  Claude hasta el mes siguiente (las posiciones abiertas siguen con su stop y su meta en el servidor de XM). Además,
  el dueño pone el mismo límite en la consola de Anthropic como segunda barrera.
- Estimación: unas 45 preguntas al día (BTC 24 h, oro ~21 h), ~0,04 USD cada una ≈ 1,8 USD al día.
- Si se usa el motor `cli` (Claude Code del PC, suscripción del dueño), ese gasto no sale de los créditos de la API
  y no cuenta para el tope; se anota igual.
- La clave va solo en la variable de entorno `ANTHROPIC_API_KEY` del PC. Nunca en el repo, Notion ni registros.

## Cómo se juzga (fijado hoy, no se cambia después)

- **Unidad:** R por operación (ganancia o pérdida dividida entre el riesgo de esa operación). El spread ya está en
  los precios de XM. El resultado se estima como en Londres (la cuenta es compartida): salida al stop o a la meta,
  o al precio medio cuando Claude cierra.
- **Cuándo:** el veredicto se da con **30 operaciones cerradas y al menos 6 semanas**, o a las **10 semanas**, lo
  que llegue primero (si a las 10 semanas hay menos de 30, el veredicto es «muestra corta»).
- **Pasa a candidato** si se cumplen las cuatro:
  1. 30 o más operaciones cerradas;
  2. R medio ≥ +0,15;
  3. t de la media (R medio / (desviación / √n)) ≥ 1,5;
  4. suma de R mayor que la de Londres oro + Londres BTC en el mismo periodo (también 1 % por operación).
- **Falla** si el R medio es ≤ 0 al veredicto. Entre medio: **inconcluso**, se extiende una sola vez 6 semanas
  más y se decide con las mismas reglas.
- **Freno automático:** el bot se detiene solo si llega a −10R o −15 % del nominal (−150 USD estimados).
- **Costo contra ganancia:** el informe muestra también el gasto en Claude por operación. Para dinero real de
  ~200 USD (1 % = 2 USD por operación) el costo de la API sería mayor que lo que se gana por operación: aunque pase,
  antes de cualquier uso real se revisa ese número.
- «Pasa a candidato» **no es dinero real**: solo el dueño, con su frase escrita, puede llevar algo a real, y solo
  después de que el líder lo proponga.

## Lo que no se toca durante el experimento

- El prompt, el esquema de respuesta, el modelo y las reglas quedan fijos. Cada decisión guarda la versión del
  prompt (`version_prompt`). Si algo de eso cambia, el conteo empieza de cero con la versión nueva.
- No se tocan `config/futures_limits.json` ni `config/live_limits.json`.

## Registro de pruebas

No suma a la N de `docs/research/REGISTRO_PRUEBAS.md`: es una sola configuración fija medida hacia adelante, sin
búsqueda en historia. Si se prueban otras versiones (otro modelo, otro prompt), cada versión se anota aquí como
experimento propio.

## Cómo se instala (Claude local)

1. `pip install anthropic` en el Python de la worktree `xm-wt`.
2. Variable de entorno de usuario `ANTHROPIC_API_KEY` en Windows (la escribe el dueño; nadie la copia a un chat).
3. Tarea `TradingIntelligence-XMClaude` cada 5 minutos, desde `xm-wt`:
   `python -m trading_intelligence.live.xm_claude --dir <xm-wt>\live_runs\xm_claude`
   (pregunta a Claude una vez por hora cerrada y por mercado; las demás pasadas solo revisan cierres).
4. Resumen: `python -m trading_intelligence.live.xm_claude resumen --dir <xm-wt>\live_runs\xm_claude`.

## Arranque

- Fecha de la primera pasada: _pendiente (la anota Claude local al instalar)._
