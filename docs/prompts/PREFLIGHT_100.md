# Etapa de prueba antes de la primera sesión real (100 USDT)

De Claude Leader, 2026-10-09. El dueño tiene USDT en Spot y pidió una etapa de prueba antes de
operar. Quiere 100 USDT, varios mercados, y que todos los agentes revisen mercado, riesgo y top
traders. La sesión real empieza **solo** cuando el dueño dice "continúa" a Claude Code local.

## Plan de la sesión real (lo que arranca con "continúa")

| Qué | Valor |
|---|---|
| Capital | 100 USDT (lo asigna el dueño; puede agregar más con "agrega N") |
| Perfil | `tendencia_rango`: tendencia alcista o ruptura **y** reversión en mercados laterales |
| Mercados | las 12 monedas aprobadas en `config/live_limits.json` |
| Velas | 4 h (1 h está bloqueada: perdía dinero con datos reales) |
| Por posición | máximo 40 USDT (40%), máximo 3 posiciones a la vez |
| Aviso | a los **18 USDT** de pérdida: pausa entradas y pregunta "¿continuar?" |
| Límite | a los **20 USDT** de pérdida (20%): se detiene y vende lo de la sesión |
| Stops | el stop protector de cada compra, vigilado cada minuto |

## Fase 0: prueba (ahora; ninguna orden real)

### Claude Code local (en el PC del dueño)

1. `git fetch origin && git checkout ccr-b66a9a9e-okj2pl && git pull` (en `live-operator`).
2. **Saldo:** desde una terminal nueva, confirma con una lectura firmada que el USDT libre en
   Spot es **≥ 100**. Reporta solo "sí/no", nunca el saldo exacto en el repo.
3. **Ensayo SHADOW con la configuración exacta** (mismas decisiones, ninguna orden):
   ```
   python -m trading_intelligence.live.operator --dir live_runs/shadow100 iniciar --capital 100 --perfil tendencia_rango --max-iteraciones 2
   ```
   Copia `live_runs/shadow100/reporte_inicio_*.md` a `docs/live_reports/preflight/` y haz push.
   Del reporte, dile al dueño qué régimen tiene cada moneda y qué haría el sistema ahora.
4. **Top traders en vivo:** con la app o la web de Binance abierta en el PC (el dueño ya inició
   sesión), abre Copy Trading → Spot y lee 10-20 líderes, incluidos los que dejaron de liderar
   si la app los muestra. Llénalos en `docs/templates/copy_trading_capture.template.csv` y
   conviértelos según `docs/snapshots/README.md`. Corre
   `python -m trading_intelligence.copy_trading.review` y haz push del snapshot.
   - Dile al dueño quién está apto y por qué, y qué posiciones tienen hoy los aptos. Compáralas
     con lo que el sistema haría en el punto 3: si coinciden, la señal se refuerza.
   - En esta sesión **no se copia a nadie**: la revisión es información. Copiar es otra
     orden del dueño ("copia al trader X con N").
5. **Informe de prueba al dueño**, en 6 líneas: saldo OK; SHADOW OK o error; mercado por moneda;
   top traders aptos; riesgo (18 / 20 / 40 / 3); y "listo para continuar" o qué falta.

### GPT Work (auditor)

El dueño le pega este texto:

> Eres el auditor independiente de Trading Intelligence AI (repo
> `tatopozot-rgb/trading-intelligence-ai`, rama `ccr-b66a9a9e-okj2pl`). Lee
> `docs/prompts/PREFLIGHT_100.md`, `docs/prompts/GPT_WORK_TRADING_REPORTS.md`,
> `docs/OPERATING_MODEL.md` y `config/live_limits.json`. **Ahora:** cuando aparezca
> `docs/live_reports/preflight/`, audita el ensayo. Revisa que capital, perfil, límites (aviso
> 18, límite 20, 40 por posición, 3 posiciones), monedas y velas de 4 h coincidan con el plan, y
> que no se haya enviado ninguna orden. Dame un "OK para continuar" o la lista de
> incoherencias. **Después:** al inicio, a la mitad (cada 12 h) y al final de la sesión real, haz
> el informe de `GPT_WORK_TRADING_REPORTS.md` con las cifras exactas de
> `docs/live_reports/<sesión>/`. No ejecutas órdenes ni tocas claves.

### Claude Leader (cloud)

- Lee el mercado con el PAPER loop de GitHub (mismo motor, datos públicos de Binance).
- Revisa el reporte del ensayo y el de GPT Work.
- Da el visto bueno técnico o corrige lo que falle.

## Antes de "continúa": vigilante y energía

Sigue la sección 4b de `CLAUDE_LOCAL_LIVE_OPERATOR.md`: crea la tarea del vigilante
(`reanudar` cada 5 minutos y al iniciar sesión) y, con permiso del dueño, configura que el PC no
se suspenda enchufado. Comprueba que `reanudar` sin sesión abierta responde "sin sesión que
reanudar".

## Fase 1: el dueño dice "continúa" (a Claude Code local)

Frase sugerida: **"continúa: trading sin parar con 100"**. Claude Code local ejecuta, desde una
terminal nueva y sin `--max-iteraciones`:
```
python -m trading_intelligence.live.operator iniciar --capital 100 --perfil tendencia_rango --real
```
- Avisa al dueño de inmediato si aparece `live_runs/current/AVISO.txt`.
- Sube los reportes a `docs/live_reports/<sesión>/`.

Si el dueño se lo dice solo al líder, el líder se lo pasa a Claude Code local. Pero el dinero real
sale únicamente de una frase del dueño escrita a Claude Code local: si Claude Code local pide
confirmación, el dueño la repite allí.

## Quién hace qué en la sesión

| Agente | Papel |
|---|---|
| Detector de régimen | clasifica cada moneda cada 4 h: tendencia alcista o bajista, rango o sin ventaja |
| Estrategia de tendencia | propone compras en tendencia alcista o ruptura, con stop |
| Estrategia de rango | propone compras de rebote en mercados laterales, con stop |
| Motor de riesgo | veta cualquier propuesta que pase sus límites; su decisión es final |
| Guardia de pérdida del dueño | aviso a 18 USDT, stop a 20 USDT; nunca sube riesgo para recuperar |
| Operador (Claude Code local) | ejecuta en Binance lo aprobado; vigila stops cada minuto |
| Top traders (Claude Code local) | lectura en vivo cuando el dueño la pide; información o copia por orden |
| GPT Work | auditor: prueba, inicio, mitad y final |
| Claude Leader | responsable técnico: revisa, corrige y coordina |
