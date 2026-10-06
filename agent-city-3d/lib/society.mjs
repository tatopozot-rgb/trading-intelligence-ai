// Reglas de la sociedad de agentes. Módulo puro (sin red, sin escritura).
// Principios: graduar por evidencia, nunca por tiempo; los bots no reciben permisos sensibles;
// el supervisor no inventa trabajo ni salta a Claude Leader; XP es progresión visual, no decide riesgo.

export const PIPELINE = ["BOT", "RECRUIT", "STUDENT", "TRAINEE", "EXAM", "GRADUATED_AGENT", "SPECIALIST", "SENIOR", "MENTOR"];
const NEXT = {
  BOT: ["RECRUIT"], RECRUIT: ["STUDENT"], STUDENT: ["TRAINEE"], TRAINEE: ["EXAM"],
  EXAM: ["GRADUATED_AGENT", "TRAINEE"], // suspender vuelve a TRAINEE
  GRADUATED_AGENT: ["SPECIALIST"], SPECIALIST: ["SENIOR"], SENIOR: ["MENTOR"], MENTOR: [],
};
export const SENSITIVE_PERMISSIONS = ["PAPER_ORDER", "LIVE_ORDER", "RISK_OVERRIDE", "CAPITAL_CHANGE", "REPO_WRITE", "SECRETS"];
export const SAFE_PERMISSIONS = ["READ_PUBLIC_DATA", "READ_STATE", "RUN_TESTS", "WRITE_NOTES", "PROPOSE_TASK"];
export const REQUIRED_FOUNDRY_FIELDS = ["need", "mission", "role", "inputs", "outputs", "tools", "permissions",
  "skills", "owner_mentor", "graduation_criteria", "success_criteria", "retirement_condition"];
export const CLAUDE_LEADER = "Claude Leader";
export const XP_TABLE = { TASK_COMPLETED: 10, TEST_PASSED: 3, PR_REVIEWED: 5, EXAM_PASSED: 20, SYSTEM_RECOVERED: 8, INCIDENT_RESOLVED: 12 };
export const XP_DAILY_CAP = 100;

const vacio = (v) => v === undefined || v === null || (Array.isArray(v) ? v.length === 0 : String(v).trim() === "");

// --- Foundry: una propuesta sólo se acepta si trae todos los campos y no pide permisos sensibles.
export function validateFoundryProposal(p) {
  const faltan = REQUIRED_FOUNDRY_FIELDS.filter((k) => vacio(p?.[k]));
  const sensibles = (p?.permissions || []).filter((x) => SENSITIVE_PERMISSIONS.includes(x));
  const errores = [];
  if (faltan.length) errores.push(`faltan campos: ${faltan.join(", ")}`);
  if (sensibles.length) errores.push(`permisos sensibles no concedibles en la creación: ${sensibles.join(", ")}`);
  if (!vacio(p?.need) && /decorat|decoración|decorative/i.test(p.need)) errores.push("necesidad decorativa: no se crea agente por decoración");
  return { ok: errores.length === 0, errores };
}

// Registro nuevo: siempre entra por BOT (o TRAINEE si se pide explícitamente) con permisos seguros.
export function createAgentRecord(p, existentes = []) {
  const v = validateFoundryProposal(p);
  if (!v.ok) throw new Error("Foundry rechaza la propuesta: " + v.errores.join("; "));
  const id = String(p.id || p.name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  if (existentes.some((a) => a.id === id)) throw new Error(`id duplicado: ${id}`);
  const etapa = p.start_stage === "TRAINEE" ? "TRAINEE" : "BOT";
  return {
    id, name: p.name, role: p.role, mission: p.mission, generation: p.generation ?? 1, level: 1, xp: 0,
    stage: etapa, status: "TRAINEE" === etapa ? "IN_ACADEMY" : "LOCKED",
    skills: p.skills || [], specializations: p.specializations || [], tools: p.tools || [],
    permissions: (p.permissions || []).filter((x) => SAFE_PERMISSIONS.includes(x)),
    building: "academy", mentor: p.owner_mentor, current_task: null, heartbeat: null, last_result: null,
    next_action: "estudiar curriculum", graduation_requirements: p.graduation_criteria,
    success_criteria: p.success_criteria, retirement_condition: p.retirement_condition,
    outputs: p.outputs, inputs: p.inputs, need: p.need, exams: [], lineage: p.lineage || null,
  };
}

// --- Pipeline. Ascender sólo por transición válida y, para graduar, con examen aprobado con evidencia.
export function canPromote(record, to) {
  return (NEXT[record.stage] || []).includes(to);
}

export function promote(record, to, evidence = null) {
  if (!canPromote(record, to)) throw new Error(`transición inválida ${record.stage} → ${to}`);
  if (to === "GRADUATED_AGENT") {
    const ultimo = [...(record.exams || [])].reverse().find((e) => e.passed !== undefined);
    if (!ultimo || ultimo.passed !== true) throw new Error("graduación requiere examen aprobado");
    if (!(typeof ultimo.score === "number" && ultimo.score >= ultimo.min_score)) throw new Error("puntuación por debajo del mínimo");
    if (!evidence || !evidence.ref) throw new Error("graduación requiere evidencia (ref de examen/prueba)");
    return { ...record, stage: to, status: "ACTIVE", graduated_evidence: evidence.ref,
      permissions: [...new Set([...record.permissions, ...SAFE_PERMISSIONS.filter((x) => !record.permissions.includes(x))])] };
  }
  if (to === "EXAM") return { ...record, stage: to, status: "IN_EXAM" };
  return { ...record, stage: to, status: to === "TRAINEE" ? "IN_ACADEMY" : record.status };
}

export function recordExam(record, { curriculum, score, min_score, passed, ref }) {
  if (typeof score !== "number" || typeof min_score !== "number") throw new Error("examen sin puntuación numérica");
  const aprobado = score >= min_score;
  if (passed !== undefined && passed !== aprobado) throw new Error("passed no coincide con la puntuación");
  return { ...record, exams: [...(record.exams || []), { curriculum, score, min_score, passed: aprobado, ref: ref || null }] };
}

// Permiso sensible: sólo lo concede Claude Leader, sólo a agentes graduados, con referencia.
export function grantSensitive(record, permiso, { approvedBy, ref }) {
  if (!SENSITIVE_PERMISSIONS.includes(permiso)) throw new Error("no es un permiso sensible");
  if (approvedBy !== CLAUDE_LEADER) throw new Error("solo Claude Leader concede permisos sensibles");
  if (record.stage === "BOT" || record.stage === "RECRUIT" || record.stage === "STUDENT" || record.stage === "TRAINEE" || record.stage === "EXAM")
    throw new Error("bots y trainees no reciben permisos sensibles");
  if (!ref) throw new Error("concesión sin referencia de decisión");
  return { ...record, permissions: [...new Set([...record.permissions, permiso])] };
}

// --- XP: progresión visual. Tope diario. No modifica límites de riesgo.
export function xpFromEvents(events, dia) {
  const porAgente = {};
  for (const e of events) {
    if (!XP_TABLE[e.type] || !e.agent_id) continue;
    if (dia && (e.observed_at || "").slice(0, 10) !== dia) continue;
    porAgente[e.agent_id] = Math.min(XP_DAILY_CAP, (porAgente[e.agent_id] || 0) + XP_TABLE[e.type]);
  }
  return porAgente;
}

// --- Supervisor (Operations Supervisor / Foreman). Recomienda; no ejecuta ni salta a Claude Leader.
export function supervise({ backlog = [], agents = [], now, horasBloqueado = 24 }) {
  const ahora = new Date(now).getTime();
  // Sólo agentes graduados o superiores pueden recibir trabajo operativo; bots y trainees no.
  const GRADUADOS = ["GRADUATED_AGENT", "SPECIALIST", "SENIOR", "MENTOR"];
  const disponibles = agents.filter((a) => GRADUADOS.includes(a.stage) && ["IDLE", "SLEEPING"].includes(a.state));
  const recomendaciones = [];
  const escalados = [];
  const usados = new Set();
  for (const t of backlog) {
    if (t.sensitive) { escalados.push({ task: t.id, motivo: "tarea sensible: requiere Claude Leader" }); continue; }
    const candidato = disponibles.find((a) => !usados.has(a.id) && (t.skills || []).every((s) => (a.skills || []).includes(s)));
    if (candidato) {
      usados.add(candidato.id);
      recomendaciones.push({ task: t.id, agent: candidato.id, accion: candidato.state === "SLEEPING" ? "DESPERTAR_Y_ASIGNAR" : "ASIGNAR", motivo: "habilidades compatibles y disponible" });
    } else {
      const dormido = agents.find((a) => a.state === "SLEEPING" && (t.skills || []).every((s) => (a.skills || []).includes(s)) && !usados.has(a.id));
      if (dormido) { usados.add(dormido.id); recomendaciones.push({ task: t.id, agent: dormido.id, accion: "DESPERTAR_Y_ASIGNAR", motivo: "trabajo crítico sin nadie despierto" }); }
      else escalados.push({ task: t.id, motivo: "sin agente compatible: proponer formación o Foundry (no crear por decoración)" });
    }
  }
  for (const a of agents) {
    if (a.state === "BLOCKED" && a.blocked_since && ahora - new Date(a.blocked_since).getTime() > horasBloqueado * 3600000) {
      escalados.push({ agent: a.id, motivo: `bloqueado más de ${horasBloqueado} h: escalar a ${CLAUDE_LEADER}` });
    }
  }
  const ociososUtiles = disponibles.filter((a) => !usados.has(a.id)).map((a) => a.id);
  return { authority: CLAUDE_LEADER, recomendaciones, escalados, descansando: ociososUtiles,
    nota: backlog.length === 0 ? "sin trabajo real: los agentes pueden descansar; no se inventa trabajo" : undefined };
}

// --- Debate: PROPOSAL → CHALLENGE (máx. 1 ronda) → EVIDENCE → DECISION → EXECUTION → REVIEW.
// Sin consenso tras la ronda, decide Claude Leader. Todo termina en un resultado explícito.
export const DEBATE_STATES = ["PROPOSAL", "CHALLENGE", "EVIDENCE", "DECISION", "EXECUTION", "REVIEW", "CLOSED"];
export const DEBATE_OUTCOMES = ["DECISION", "TASK", "REJECTED", "WAITING_FOR_USER"];
export function newDebate(topic, proposer) {
  return { topic, proposer, state: "PROPOSAL", challenge_rounds: 0, messages: [{ from: proposer, type: "PROPOSAL" }], outcome: null, decided_by: null };
}
export function debateStep(d, msg) {
  if (d.state === "CLOSED") throw new Error("debate cerrado");
  const t = msg.type;
  const next = { ...d, messages: [...d.messages, msg] };
  if (d.state === "PROPOSAL" && t === "CHALLENGE") { next.state = "CHALLENGE"; next.challenge_rounds = 1; }
  else if (d.state === "PROPOSAL" && t === "AGREE") { next.state = "DECISION"; next.decided_by = "consensus"; }
  else if (d.state === "CHALLENGE" && t === "EVIDENCE") next.state = "EVIDENCE";
  else if (d.state === "CHALLENGE" && t === "CHALLENGE") { // no hay segunda ronda: se decide por autoridad
    next.state = "DECISION"; next.decided_by = CLAUDE_LEADER; next.note = "máximo una ronda de challenge"; }
  else if (d.state === "EVIDENCE" && (t === "AGREE" || t === "REJECT")) { next.state = "DECISION"; next.decided_by = t === "AGREE" ? "consensus" : CLAUDE_LEADER; }
  else if (d.state === "EVIDENCE") { next.state = "DECISION"; next.decided_by = CLAUDE_LEADER; next.note = "sin consenso tras evidencia"; }
  else if (d.state === "DECISION" && t === "OUTCOME") {
    if (!DEBATE_OUTCOMES.includes(msg.outcome)) throw new Error("resultado inválido");
    next.outcome = msg.outcome; next.state = msg.outcome === "TASK" ? "EXECUTION" : "CLOSED";
  }
  else if (d.state === "EXECUTION" && t === "DONE") next.state = "REVIEW";
  else if (d.state === "REVIEW" && t === "REVIEWED") { next.state = "CLOSED"; next.outcome = d.outcome || "TASK"; }
  else throw new Error(`transición de debate inválida: ${d.state} con ${t}`);
  return next;
}
