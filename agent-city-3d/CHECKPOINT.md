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

## Tanda autónoma (perfeccionamiento)
- Pestañas del panel: CITY, AGENT, BUILDING, OPERATIONS, SIMULATION. "Volver a ciudad" limpia selección y seguimiento.
- Seguir agente (la cámara acompaña) y enfocar edificio (botón o doble clic).
- Rendimiento medido sólo en el modelo (`tests/perf.test.mjs`): derivado de ciudad 3–17 ms para 107 avatares totales
  (peor caso: 40 residentes, 60 agentes de sociedad, 4 roles, 3 fundadores). El coste de render en GPU NO está medido.
- Estados de vida: SIM_STUDYING, SIM_WORKING, SIM_SLEEPING, SIM_LEISURE, SIM_TRAVEL, SIM_BREAK, SIM_ON_DUTY.
- Visual pendiente: la barra de pestañas está en el DOM servido pero no se confirmó en la captura.

## Pendiente real (no hecho)
- Instancing y LOD: no implementados. Hoy cada avatar son ~14 mallas separadas.
- Puertas: la transición calle→puerta→interior es un desplazamiento en línea recta; no hay puertas modeladas.
- Transporte en bicicleta/vehículos: no implementado.
- Estados COMMUTING, SEEKING_WORK, MEETING, MENTORING: sólo como nombres previstos, sin lógica de reunión.
- Sync de Obsidian del panel: sin cambios en esta tanda.

## Tanda de vida y movimiento (ef4a4f9 → siguiente)
- Lógica de vida real-simulada (`lib/life.mjs`): aprendices y puestos sólo existen con demanda real.
  Estados: SEEKING_WORK (busca en el tablón), COMMUTING (en bicicleta SIM), WORKING, STUDYING,
  MEETING (10:00 en Command Center), MENTORING (trainer SIM en academia), RESTING, SLEEPING, LEISURE.
- Rutas por calle → puerta → interior y salida inversa (`lib/paths.mjs`, 6 tests, sin teletransporte).
- Puertas visibles en fachadas de los edificios con interior.
- Bicicleta SIM en trayectos al trabajo y de vuelta; a pie el resto.
- Supervisor con portapapeles y rutina (reunión 10:00, Foundry por la tarde, Command Center).
- Sentado al trabajar o estudiar dentro; tumbado al dormir dentro.
- LOD por distancia a la cámara: lejos se quitan brazos, piernas y cabello; etiquetas sólo cerca.
- Ficha de agente: rol, estado, edificio, destino, siguiente acción, nivel, XP, habilidades, transporte.

## Límites de esta tanda (honestidad)
- Instancing NO implementado: cada avatar sigue siendo mallas separadas. Sólo LOD.
- Rendimiento medido sólo en el modelo (ms de derivado). El coste de GPU no está medido.
- Las puertas son bloques; la animación de cruzar la puerta es un desplazamiento lineal.
- Sin entrada a interiores con cámara de enfoque automática dentro del edificio.
- Trainees simulados: sólo aparecen con demanda real; no hay ceremonia de graduación visual.

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
