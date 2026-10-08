// Modelo puro de Agent City 3D: sin three.js, sin red, probado en tests/.
// Regla central: un agente sólo se mueve o aparece como "trabajando" por evidencia (evento real reciente o estado documentado).
// WORKING requiere AGENT_WORKING o TASK_STARTED recientes; nunca se deduce de un commit ni de un estado REVIEW.

import { residentes, actividadPara, actividadRol, ROLES_SIMULADOS, horaVisual, SIM_NOTE as SIM_NOTE_VIDA } from "./life.mjs";
import { perfilEtapa, actividadJubilado } from "./lifecycle.mjs";
import { asignarEspacios } from "./espacio.mjs";

export const MODE = "BUILD"; // OPERATIONS queda preparado, no activo

// Edificios: (x, z) en la cuadrícula de calles. district separa Operational Reality de Life Simulation.
export const BUILDINGS = [
  { id: "command_center", label: "🏛 Command Center", pos: [0, 0], district: "operational" },
  { id: "engineering_lab", label: "💻 Engineering Lab", pos: [1, 0], district: "operational" },
  { id: "local_ops", label: "🖥 Local Operations", pos: [2, 0], district: "operational" },
  { id: "gpt_ops", label: "🤖 GPT Operations", pos: [0, 1], district: "operational" },
  { id: "risk_tower", label: "🛡 Risk Tower", pos: [1, 1], district: "operational" },
  { id: "quant_lab", label: "📊 Quant Lab", pos: [2, 1], district: "operational" },
  { id: "qa_facility", label: "🧪 QA Facility", pos: [0, 2], district: "operational" },
  { id: "market_intel", label: "📡 Market Intelligence", pos: [1, 2], district: "operational" },
  { id: "trading_floor", label: "🏦 Trading Floor", pos: [2, 2], district: "operational" },
  { id: "knowledge_center", label: "📚 Knowledge Center", pos: [0, 3], district: "operational" },
  { id: "foundry", label: "🏭 Agent Foundry", pos: [1, 3], district: "operational" },
  { id: "university", label: "🎓 University", pos: [2, 3], district: "operational" },
  { id: "hall", label: "🏆 Hall of Achievements", pos: [3, 1], district: "operational" },
  { id: "academy", label: "📘 Agent Academy", pos: [3, 0], district: "operational" },
  // Life Simulation: creativo, separado. Nunca fuente de estado operativo.
  { id: "residential", label: "🏘 Residential District", pos: [3, 2], district: "simulation" },
  { id: "park", label: "🌳 Parque", pos: [3, 3], district: "simulation" },
  // Casas del barrio residencial (simulación), al este de la cuadrícula operativa (x>=33, fuera de
  // la columna i=3 en x=27 donde están residential/hall/academy/park). Separación de 6-8 unidades
  // en cada eje: ni las paredes ni los puntos de ruta (puerta/calle, hasta 3.6 desde el centro) caen
  // dentro de otro edificio (verificado con script geométrico; antes, a 4 unidades de "residential",
  // las 4 casas y ese edificio se solapaban entre sí en sus cuatro esquinas).
  { id: "house_a", label: "🏠 Casa A", pos: [3, 2], world: [33, 14], district: "simulation" },
  { id: "house_b", label: "🏠 Casa B", pos: [3, 2], world: [39, 14], district: "simulation" },
  { id: "house_c", label: "🏠 Casa C", pos: [3, 2], world: [33, 22], district: "simulation" },
  { id: "house_d", label: "🏠 Casa D", pos: [3, 2], world: [39, 22], district: "simulation" },
  // 5ª casa: con 8 camas/casa (litera, ver espacio.mjs) y POBLACION_MAX=40, 5 casas cubren el tope
  // exacto (40 = 5x8) sin que nadie tenga que repetir cama por round-robin nunca.
  { id: "house_e", label: "🏠 Casa E", pos: [3, 2], world: [45, 18], district: "simulation" },
];
export const SIM_NOTE = SIM_NOTE_VIDA;

// Categorías de roles previstos (agrupación de la UI). Coincide por nombre con society-store.
export const ROLE_CATEGORY = {
  "Operations Supervisor": "liderazgo", "Mission Control Agent": "liderazgo", "Agent Creator": "expansión",
  "Market Watch Agent": "operaciones", "Execution Agent": "operaciones", "Portfolio Agent": "operaciones",
  "Quant Research Agent": "research", "Knowledge Agent": "research", "Risk Agent": "riesgo",
  "QA / Red Team Agent": "QA", "Infra / Recovery Agent": "ingeniería", "Trainer": "formación",
};
export const CATEGORIAS = ["liderazgo", "ingeniería", "research", "operaciones", "QA", "riesgo", "formación", "expansión"];

// Fundadores: identidades reales. Un alias = misma entidad; no se duplican.
export const AGENTS = [
  { key: "codex", name: "Trading Codex", alias: "Claude Leader", home: "engineering_lab", color: 0x3b82f6 },
  { key: "gpt", name: "Trading Claude-Work", alias: "GPT Work", home: "gpt_ops", color: 0xa855f7 },
  { key: "local", name: "Claude Code Local", alias: "PowerShell", home: "local_ops", color: 0x10b981 },
];

// Bus de eventos: tipo → edificio destino. null = sin destino fijo (usa el edificio del agente).
export const EVENT_BUILDING = {
  AGENT_CREATED: "foundry", AGENT_PROMOTED: "hall", AGENT_RETIRED: null,
  AGENT_WORKING: null, AGENT_REVIEWING: "command_center", AGENT_IDLE: "residential", AGENT_SLEEPING: "residential",
  AGENT_BLOCKED: null,
  TASK_ASSIGNED: "command_center", TASK_STARTED: null, TASK_COMPLETED: null, TASK_FAILED: null,
  STUDY_STARTED: "academy", TRAINING_STARTED: "academy", EXAM_STARTED: "academy", EXAM_PASSED: "academy", EXAM_FAILED: "academy",
  GRADUATED: "hall", SPECIALIZATION_EARNED: "hall",
  MEETING_STARTED: "command_center", DECISION_MADE: "command_center",
  TEST_STARTED: "qa_facility", TEST_PASSED: "qa_facility", TEST_FAILED: "qa_facility",
  PR_OPENED: "engineering_lab", PR_REVIEWED: "engineering_lab", PR_MERGED: "engineering_lab",
  BACKTEST_STARTED: "quant_lab", BACKTEST_FINISHED: "quant_lab",
  RISK_APPROVED: "risk_tower", RISK_REJECTED: "risk_tower", KILL_SWITCH_TRIGGERED: "risk_tower",
  NO_TRADE: "trading_floor", TRADE_OPENED: "trading_floor", TRADE_CLOSED: "trading_floor",
  SYSTEM_RECOVERED: "command_center",
};
export const ALL_EVENT_TYPES = Object.keys(EVENT_BUILDING);

// Estados visuales válidos (los únicos que la UI puede pintar).
export const VISUAL_STATES = ["WORKING", "WALKING_TO_WORK", "REVIEWING", "STUDYING", "TRAINING", "EXAMINING", "MEETING",
  "IDLE", "SLEEPING", "BLOCKED", "ERROR", "OFFLINE", "STALE", "NOT_SYNCED", "LOCKED", "PLANNED"];

const VENTANA_ACTIVA_MS = 2 * 3600 * 1000;
const SNAPSHOT_STALE_MS = 2 * 3600 * 1000;

export function agentByAlias(texto) {
  if (!texto) return null;
  const t = String(texto).toLowerCase();
  const claves = {
    local: ["claude code", "powershell"],
    gpt: ["gpt work", "claude-work", "claude work", "gpt"],
    codex: ["trading codex", "codex", "claude leader"],
  };
  for (const a of AGENTS) {
    if (claves[a.key].some((k) => t.includes(k))) return a;
  }
  return null;
}

function estadoDesdeSnapshot(snap, key) {
  const a = (snap?.agents || []).find((x) => x.key === key);
  return a ? a.state : "NOT_SYNCED";
}

// Agentes de la sociedad (Foundry/Academy) que tienen presencia visual. Planned/Locked no aparecen.
function visualDeSociedad(rec, ultimo) {
  if (["PLANNED", "LOCKED"].includes(rec.status) && rec.stage !== "TRAINEE") return null;
  if (rec.stage === "CORE") return null; // fundadores se pintan con snapshot
  if (rec.stage === "EXAM") return { target: "academy", state: "EXAMINING", razon: "etapa EXAM" };
  if (rec.stage === "TRAINEE" || rec.status === "IN_ACADEMY") return { target: "academy", state: "TRAINING", razon: "etapa TRAINEE en academia" };
  if (rec.status === "BLOCKED") return { target: rec.building || "academy", state: "BLOCKED", razon: "bloqueado" };
  if (ultimo && ["AGENT_WORKING", "TASK_STARTED"].includes(ultimo.type)) return { target: rec.building || "residential", state: "WORKING", razon: `evento ${ultimo.type}` };
  if (ultimo && ultimo.type === "AGENT_SLEEPING") return { target: "residential", state: "SLEEPING", razon: "evento AGENT_SLEEPING" };
  return { target: "residential", state: "IDLE", razon: "sin trabajo asignado" };
}

// Deriva la escena. Función pura: (snapshot, society, events, now) → modelo.
export function deriveCity({ snapshot, society, events, now, life = null }) {
  const ahoraMs = now instanceof Date ? now.getTime() : Date.parse(now);
  const ev = [...(events || [])].filter((e) => e && ALL_EVENT_TYPES.includes(e.type));
  // Edad de una marca de tiempo. Una fecha ilegible o FUTURA no es evidencia reciente: sin
  // tolerancia de desfase de reloj, se trata como infinitamente vieja (nunca como "fresca").
  const edadMs = (marca) => {
    const edad = ahoraMs - Date.parse(marca);
    return Number.isFinite(edad) && edad >= 0 ? edad : Infinity;
  };
  const snapAge = snapshot?.generated_at ? edadMs(snapshot.generated_at) : Infinity;
  const syncOk = Boolean(snapshot?.sync?.ok) && snapAge < SNAPSHOT_STALE_MS;

  const pulses = Object.fromEntries(BUILDINGS.map((b) => [b.id, []]));
  const recientes = ev.filter((e) => edadMs(e.observed_at || e.ts || 0) < VENTANA_ACTIVA_MS);
  const ultimoDe = (predicado) => [...recientes].reverse().find(predicado);

  for (const e of recientes.slice(-300)) {
    const agente = agentByAlias(e.subject);
    let edificio = EVENT_BUILDING[e.type];
    if (edificio === null) edificio = agente ? AGENTS.find((a) => a.key === agente.key).home : null;
    if (edificio && pulses[edificio]) pulses[edificio].push({ type: e.type, subject: e.subject || "", detail: e.detail || "", at: e.observed_at || e.ts });
  }

  // Fundadores (agentes reales): estado documentado + evento real más reciente.
  const fundadores = AGENTS.map((a) => {
    const ultimo = ultimoDe((e) => agentByAlias(e.subject)?.key === a.key);
    const estadoDoc = estadoDesdeSnapshot(snapshot, a.key);
    let destino = null;
    let estado = syncOk ? estadoDoc : "STALE";
    let razon = "estado documentado";
    // WORKING sólo lo concede un evento observado (rama siguiente). El texto "WORKING" de un
    // snapshot es un estado documentado: se muestra como IN_PROGRESS, sin animación de trabajo.
    if (estado === "WORKING") { estado = "IN_PROGRESS"; razon = "WORKING documentado sin evento observado"; }
    if (ultimo) {
      if (ultimo.type === "AGENT_BLOCKED") { destino = a.home; estado = "BLOCKED"; razon = "evento AGENT_BLOCKED"; }
      else if (["AGENT_WORKING", "TASK_STARTED"].includes(ultimo.type)) { destino = a.home; estado = "WORKING"; razon = `evento ${ultimo.type}`; }
      else if (ultimo.type === "AGENT_REVIEWING") { destino = "command_center"; estado = "REVIEWING"; razon = "evento AGENT_REVIEWING"; }
      else if (ultimo.type === "AGENT_SLEEPING") { destino = "residential"; estado = "SLEEPING"; razon = "evento AGENT_SLEEPING"; }
      else if (ultimo.type === "AGENT_IDLE") { destino = "residential"; estado = "IDLE"; razon = "evento AGENT_IDLE"; }
      else if (ultimo.type === "TASK_COMPLETED") { destino = a.home; estado = "DONE"; razon = "evento TASK_COMPLETED"; }
    }
    if (destino === null) {
      if (estado === "REVIEW") { destino = "command_center"; estado = "REVIEWING"; razon = "estado REVIEW documentado"; }
      else if (["BLOCKED", "WAITING_FOR_USER", "STALE", "IN_PROGRESS", "PENDING", "DONE"].includes(estado)) { destino = a.home; razon = estado === "STALE" ? "fuente vieja o caída" : razon; }
      else { destino = "residential"; if (estado === "NOT_SYNCED") razon = "sin evidencia: NOT_SYNCED"; }
    }
    const doc = (snapshot?.agents || []).find((x) => x.key === a.key) || {};
    return { key: a.key, name: a.name, alias: a.alias, color: a.color, target: destino, state: estado, reason: razon,
      currentTask: doc.current_task || null, lastResult: doc.last_result?.text || null,
      heartbeat: doc.heartbeat?.date || null, lastEvent: ultimo ? { type: ultimo.type, detail: ultimo.detail, at: ultimo.observed_at } : null,
      kind: "founder", stage: "CORE" };
  });

  // Sociedad: bots/trainees/graduados visibles. Los planned/locked no se pintan.
  const sociedad = [];
  for (const rec of society?.agents || []) {
    const ultimo = ultimoDe((e) => e.agent_id === rec.id);
    const vis = visualDeSociedad(rec, ultimo);
    if (!vis) continue;
    sociedad.push({ key: rec.id, name: rec.name, alias: rec.role, color: 0x64748b, target: vis.target, state: vis.state,
      reason: vis.razon, currentTask: rec.current_task || null, lastResult: rec.last_result || null,
      heartbeat: rec.heartbeat || null, lastEvent: ultimo ? { type: ultimo.type, detail: ultimo.detail, at: ultimo.observed_at } : null,
      kind: "society", stage: rec.stage });
  }

  // Graduación simulada: pulso propio en la universidad y aviso separado del banner real.
  const VENTANA_GRADUACION_MS = 2 * 3600 * 1000;
  const graduacionesRecientes = (life?.poblacion || []).filter((p) => p.graduadoEn && ahoraMs - Date.parse(p.graduadoEn) < VENTANA_GRADUACION_MS);
  for (const p of graduacionesRecientes) {
    (pulses["university"] ||= []).push({ type: "GRADUATED_SIM", subject: p.nombre, detail: "graduación simulada", at: p.graduadoEn });
  }
  const simBanners = graduacionesRecientes.map((p) => `🎓 Graduación simulada: ${p.nombre} (${SIM_NOTE})`);
  const banners = [];
  if (!syncOk) banners.push(snapshot ? "SYNC STALE — última observación" : "SIN DATOS: sincronización no disponible");
  if (recientes.some((e) => e.type === "NO_TRADE")) banners.push("CAPITAL PRESERVED — NO_TRADE");
  if (recientes.some((e) => e.type === "KILL_SWITCH_TRIGGERED")) banners.push("KILL SWITCH — revisar Risk Tower");
  const graduados = recientes.filter((e) => e.type === "GRADUATED");
  if (graduados.length) banners.push(`🎓 Graduación reciente: ${graduados.map((g) => g.subject).join(", ")}`);

  const planeados = (society?.planned_roles || []).map((r) => ({ name: r.name, state: r.status, categoria: ROLE_CATEGORY[r.name] || "expansión" }));

  // Vida simulada: demanda = tareas abiertas (snapshot) + actividad real de 24 h. Sólo decide tamaño de población.
  const abiertas = (snapshot?.tasks || []).filter((t) => ["IN_PROGRESS", "PENDING", "BLOCKED", "WAITING_FOR_USER"].includes(t.status)).length;
  const actividad24h = ev.filter((e) => ahoraMs - Date.parse(e.observed_at || e.ts || 0) < 24 * 3600 * 1000).length;
  const demanda = abiertas + Math.ceil(actividad24h / 2);
  // Reloj visual acelerado (SIM): decide la rutina horaria para que la ciudad se vea viva en minutos reales.
  // La edad/envejecimiento sigue el tiempo real en lifecycle.mjs; esto NO lo toca.
  const hora = horaVisual(ahoraMs);
  const vidaPorId = Object.fromEntries((life?.poblacion || []).map((p) => [p.id, p]));
  const listaResidentes = residentes(demanda);
  const espacios = asignarEspacios(listaResidentes); // cama y estación estables: nadie decorativo en fila
  const EDIFICIO_JUBILADO = { home: "residential", park: "park", residential: "residential" };
  const vida = listaResidentes.map((r) => {
    const persona = vidaPorId[r.id];
    // Un jubilado ya no sigue el horario laboral: vive su propia rutina, nunca desaparece.
    const a = persona && persona.etapa === "RETIRED"
      ? (() => { const j = actividadJubilado(hora); return { ...j, destino: EDIFICIO_JUBILADO[j.destino] || j.destino, transporte: "caminar" }; })()
      : actividadPara(r, hora);
    const perfil = persona ? perfilEtapa(persona.etapa) : { escala: 1, velocidad: 1 };
    return { key: r.id, name: r.name, alias: r.tipo, color: 0xcbd5e1, target: a.destino, state: "SIM_" + a.actividad,
      reason: a.etiqueta, currentTask: null, lastResult: null, heartbeat: null, lastEvent: null,
      kind: "simulated", stage: r.stage, tipo: r.tipo, home: r.home, workplace: r.workplace,
      transporte: a.transporte, conPuesto: Boolean(r.conPuesto), skills: r.skills || [], xp: r.xp || 0,
      nivel: r.tipo === "trainee" ? "APRENDIZ (sim)" : r.tipo === "worker" ? "TRABAJADOR (sim)" : "VECINO (sim)",
      etapaVital: persona ? persona.etapa : null, edadSim: persona ? Math.floor(persona.edad) : null,
      escalaVisual: perfil.escala, velocidadVisual: perfil.velocidad,
      cama: espacios[r.id].cama, estacion: espacios[r.id].estacion };
  });
  const simRoles = ROLES_SIMULADOS.map((r) => {
    const a = actividadRol(r, hora);
    return { key: r.id, name: r.name, alias: "rol simulado", color: 0xfacc15, target: a.destino, state: "SIM_" + a.actividad,
      reason: `${a.etiqueta} · rol simulado, sin fuente real`, currentTask: null, lastResult: null, heartbeat: null, lastEvent: null,
      kind: "simulated", stage: "SIM_ROLE", tipo: r.role, home: r.home, workplace: a.destino, transporte: "caminar",
      skills: [], xp: 0, nivel: "ROL SIMULADO" };
  });
  return { mode: MODE, syncOk, snapshotAt: snapshot?.generated_at || null, banners,
    buildings: BUILDINGS.map((b) => ({ ...b, pulses: pulses[b.id].slice(-5) })),
    agents: [...fundadores, ...sociedad, ...simRoles, ...vida],
    planned: planeados,
    demand: { abiertas, actividad24h, total: demanda },
    simBanners,
    simulation: { note: SIM_NOTE, residents: vida.map((v) => v.key), population: vida.length, roles: simRoles.length },
    feed: ev.slice(-30).reverse() };
}

export const STATE_COLOR = { SIM_SEEKING_WORK: 0xfb923c, SIM_COMMUTING: 0x67e8f9, SIM_MEETING: 0x06b6d4, SIM_MENTORING: 0xc084fc, SIM_RESTING: 0xbef264, SIM_TRAVEL: 0xcbd5e1, SIM_WORKING: 0x86efac, SIM_STUDYING: 0xfcd34d, SIM_SLEEPING: 0x818cf8, SIM_TRAVEL: 0xcbd5e1, SIM_LEISURE: 0x93c5fd, SIM_BREAK: 0xd9f99d, SIM_ON_DUTY: 0xfacc15, WORKING: 0x22c55e, WALKING_TO_WORK: 0x22c55e, REVIEWING: 0x3b82f6, REVIEW: 0x3b82f6,
  STUDYING: 0xf59e0b, TRAINING: 0xf59e0b, EXAMINING: 0xf59e0b, MEETING: 0x06b6d4, WAITING_FOR_USER: 0xeab308,
  BLOCKED: 0xf97316, IDLE: 0x9ca3af, SLEEPING: 0x6366f1, DONE: 0x16a34a, ERROR: 0xdc2626, OFFLINE: 0x374151,
  NOT_SYNCED: 0x6b7280, STALE: 0x78716c, IN_PROGRESS: 0x9ca3af, PENDING: 0x9ca3af };
