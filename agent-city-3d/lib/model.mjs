// Modelo puro de Agent City 3D: sin three.js, sin red, probado en tests/.
// Regla central: un agente sólo se mueve o aparece como "trabajando" por evidencia (evento real reciente o estado documentado).
// WORKING requiere AGENT_WORKING o TASK_STARTED recientes; nunca se deduce de un commit ni de un estado REVIEW.

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
];
export const SIM_NOTE = "SIMULACIÓN — no es actividad real";

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
export function deriveCity({ snapshot, society, events, now }) {
  const ahoraMs = now instanceof Date ? now.getTime() : Date.parse(now);
  const ev = [...(events || [])].filter((e) => e && ALL_EVENT_TYPES.includes(e.type));
  const snapAge = snapshot?.generated_at ? ahoraMs - Date.parse(snapshot.generated_at) : Infinity;
  const syncOk = Boolean(snapshot?.sync?.ok) && snapAge < SNAPSHOT_STALE_MS;

  const pulses = Object.fromEntries(BUILDINGS.map((b) => [b.id, []]));
  const recientes = ev.filter((e) => ahoraMs - Date.parse(e.observed_at || e.ts || 0) < VENTANA_ACTIVA_MS);
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

  const banners = [];
  if (!syncOk) banners.push(snapshot ? "SYNC STALE — última observación" : "SIN DATOS: sincronización no disponible");
  if (recientes.some((e) => e.type === "NO_TRADE")) banners.push("CAPITAL PRESERVED — NO_TRADE");
  if (recientes.some((e) => e.type === "KILL_SWITCH_TRIGGERED")) banners.push("KILL SWITCH — revisar Risk Tower");
  const graduados = recientes.filter((e) => e.type === "GRADUATED");
  if (graduados.length) banners.push(`🎓 Graduación reciente: ${graduados.map((g) => g.subject).join(", ")}`);

  const planeados = (society?.planned_roles || []).map((r) => ({ name: r.name, state: r.status }));
  return { mode: MODE, syncOk, snapshotAt: snapshot?.generated_at || null, banners,
    buildings: BUILDINGS.map((b) => ({ ...b, pulses: pulses[b.id].slice(-5) })),
    agents: [...fundadores, ...sociedad],
    planned: planeados,
    simulation: { note: SIM_NOTE, residents: [] }, // sin residentes simulados: no hay mecánica todavía
    feed: ev.slice(-30).reverse() };
}

export const STATE_COLOR = { WORKING: 0x22c55e, WALKING_TO_WORK: 0x22c55e, REVIEWING: 0x3b82f6, REVIEW: 0x3b82f6,
  STUDYING: 0xf59e0b, TRAINING: 0xf59e0b, EXAMINING: 0xf59e0b, MEETING: 0x06b6d4, WAITING_FOR_USER: 0xeab308,
  BLOCKED: 0xf97316, IDLE: 0x9ca3af, SLEEPING: 0x6366f1, DONE: 0x16a34a, ERROR: 0xdc2626, OFFLINE: 0x374151,
  NOT_SYNCED: 0x6b7280, STALE: 0x78716c, IN_PROGRESS: 0x9ca3af, PENDING: 0x9ca3af };
