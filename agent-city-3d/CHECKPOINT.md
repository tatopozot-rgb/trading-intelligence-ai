# Agent City 3D — checkpoint

Rama: `claude-code/agent-city-3d-mvp`. Ejecutor: Claude Code Local. Fuente de verdad técnica: GitHub; este
checkpoint describe sólo lo que hay en esta rama.

## Separación de capas (regla)
- **REAL**: sync de git/docs, eventos reales, estados documentados. Sólo `WORKING` sale de un evento real reciente.
- **SIMULADO**: residentes, roles simulados y sus estados `SIM_*`. Siempre etiquetados; nunca evidencia de trabajo.

## Hecho en esta tanda
- Panel lateral rediseñado: tarjetas, secciones plegables (Realidad operativa / Simulación visual / Roles / Eventos / Leyenda), badges REAL/SIMULADO, panel por ciudad, por edificio y por agente.
- Avatares humanoides: torso, cabeza, cabello, brazos y piernas con pivote; marcha alterna al moverse; respiración al estar quieto; anillo de estado y anillo amarillo de selección.
- Edificios semitransparentes con interiores (mesas, pantallas, camas, sofás); botón para ocultar interiores.
- Casas (A–D) en el barrio residencial; residentes simulados viven allí y van a academia, universidad, oficinas de simulación o parque según la hora (`lib/life.mjs`).
- Población simulada crece con demanda real (tareas abiertas + actividad 24 h), con tope de 40.
- Estados simulados prefijados con `SIM_`; `WORKING` queda reservado al estado real (test explícito).
- Trainees simulados ganan XP estudiando y sólo se gradúan con examen simulado aprobado (puntuación determinista).
- Roles simulados activos (supervisor, recruiter/creator, trainer, auditor/filter), marcados como sin fuente real.
- Roles previstos agrupados por categoría (liderazgo, ingeniería, research, operaciones, QA, riesgo, formación, expansión) y separados en conectados / simulados / planificados.
- HR / Performance Auditor (`lib/hr.mjs`): recomienda TRAIN/PROMOTE/REASSIGN/MENTOR/RETIRE/REPLACE con evidencia; nunca aplica.
- Sync de Obsidian: nota `02 Agents/Sociedad de agentes.md` generada desde `state/society.json`.

## Verificación
- `node --test tests/` → 52/52 (model, life, hr, society, society-store).
- Validación del vault (`sync_agent_city.py --validate`) → OK.
- Captura real con Chrome headless: la ciudad renderiza, el panel carga y las etiquetas simuladas no se apilan.

## Limitaciones conocidas
- Sin animación de bicicleta/transporte; sin entrada real dentro de los interiores (los avatares se paran en el umbral o en el centro, sin modelar puertas).
- Los simulados no se muestran en "Roles conectados" (correcto: no tienen fuente real).
- Las etiquetas de fundadores siguen visibles siempre (son reales); pueden solaparse con edificios en vistas cercanas.
- El watchdog/pausa de Finding 3 vive en `claude-code/finding-3-persistent-halt` (no en esta rama) y todavía no tiene revisión de Trading Claude-Work.
- Sin conexión a Notion ni a GitHub PR desde la escena (NOT_SYNCED).

## Siguiente
1. Entradas y salidas de puertas (animación de transición interior/exterior).
2. Bicicletas o transporte entre barrio y oficinas, sólo como simulación.
3. Presencia visual del Supervisor en Command Center cuando exista backlog real.
4. Medir rendimiento con 100+ avatares y reducir draw calls si hace falta.
