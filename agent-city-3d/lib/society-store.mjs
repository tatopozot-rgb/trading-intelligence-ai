// Persistencia de la sociedad: snapshot atómico (society.json) + log de eventos (events.jsonl, mismo bus que la ciudad).
// Escritura atómica: se escribe un .tmp y luego se renombra. Un cierre a mitad no corrompe el estado anterior.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import * as S from "./society.mjs";

export const FILE_SOCIETY = "society.json";
export const FILE_EVENTS = "events.jsonl";

export const FUNDADORES = [
  { id: "trading-codex", name: "Trading Codex", alias: "Claude Leader", stage: "CORE", status: "ACTIVE", building: "engineering_lab", role: "Engineering / Command Center" },
  { id: "trading-claude-work", name: "Trading Claude-Work", alias: "GPT Work", stage: "CORE", status: "ACTIVE", building: "gpt_ops", role: "Quant / Risk review" },
  { id: "claude-code-local", name: "Claude Code Local", alias: "PowerShell", stage: "CORE", status: "ACTIVE", building: "local_ops", role: "Local operations" },
];

// Roles previstos: existen en el modelo, pero NO activos hasta tener trabajo real y gradúan por evidencia.
export const ROLES_PREVISTOS = ["Operations Supervisor", "Agent Creator", "Mission Control Agent", "Market Watch Agent",
  "Quant Research Agent", "Risk Agent", "Execution Agent", "Portfolio Agent", "QA / Red Team Agent", "Infra / Recovery Agent", "Knowledge Agent"];

export function sociedadVacia() {
  return {
    version: 1,
    mode: "BUILD",
    founders: FUNDADORES,
    agents: [],
    planned_roles: ROLES_PREVISTOS.map((r) => ({ id: r.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""), name: r, status: "PLANNED" })),
    debates: [],
    updated_at: null,
  };
}

export function leerSociedad(dir) {
  const ruta = path.join(dir, FILE_SOCIETY);
  if (!fs.existsSync(ruta)) return sociedadVacia();
  return JSON.parse(fs.readFileSync(ruta, "utf8"));
}

export function guardarSociedad(dir, data) {
  const ids = (data.agents || []).map((a) => a.id);
  if (new Set(ids).size !== ids.length) throw new Error("ids de agente duplicados");
  fs.mkdirSync(dir, { recursive: true });
  const ruta = path.join(dir, FILE_SOCIETY);
  const tmp = ruta + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify({ ...data, updated_at: new Date().toISOString() }, null, 2), "utf8");
  fs.renameSync(tmp, ruta);
}

export function registrarEvento(dir, evento) {
  fs.mkdirSync(dir, { recursive: true });
  const e = { ...evento, observed_at: evento.observed_at || new Date().toISOString() };
  e.id = crypto.createHash("sha1").update(`${e.type}|${e.agent_id || ""}|${e.detail || ""}|${e.observed_at}`).digest("hex").slice(0, 12);
  fs.appendFileSync(path.join(dir, FILE_EVENTS), JSON.stringify(e) + "\n", "utf8");
  return e;
}

// Acciones de la sociedad: cada una valida con lib/society.mjs, guarda y registra evento.
export function accionCrear(dir, propuesta) {
  const data = leerSociedad(dir);
  const nuevo = S.createAgentRecord(propuesta, data.agents);
  data.agents.push(nuevo);
  guardarSociedad(dir, data);
  registrarEvento(dir, { type: "AGENT_CREATED", agent_id: nuevo.id, subject: nuevo.name, detail: `Foundry: ${nuevo.role}` });
  return nuevo;
}

export function accionExamen(dir, id, examen) {
  const data = leerSociedad(dir);
  const i = data.agents.findIndex((a) => a.id === id);
  if (i < 0) throw new Error(`agente desconocido: ${id}`);
  data.agents[i] = S.recordExam(data.agents[i], examen);
  const ultimo = data.agents[i].exams.at(-1);
  guardarSociedad(dir, data);
  registrarEvento(dir, { type: ultimo.passed ? "EXAM_PASSED" : "EXAM_FAILED", agent_id: id, subject: data.agents[i].name,
    detail: `${ultimo.curriculum} ${ultimo.score}/${ultimo.min_score}`, evidence: ultimo.ref });
  return data.agents[i];
}

export function accionPromover(dir, id, a, evidencia = null) {
  const data = leerSociedad(dir);
  const i = data.agents.findIndex((x) => x.id === id);
  if (i < 0) throw new Error(`agente desconocido: ${id}`);
  data.agents[i] = S.promote(data.agents[i], a, evidencia);
  guardarSociedad(dir, data);
  const tipo = a === "GRADUATED_AGENT" ? "GRADUATED" : "AGENT_PROMOTED";
  registrarEvento(dir, { type: tipo, agent_id: id, subject: data.agents[i].name, detail: `${a}`, evidence: evidencia?.ref || null });
  return data.agents[i];
}

export function accionConcederSensible(dir, id, permiso, { approvedBy, ref }) {
  const data = leerSociedad(dir);
  const i = data.agents.findIndex((x) => x.id === id);
  if (i < 0) throw new Error(`agente desconocido: ${id}`);
  data.agents[i] = S.grantSensitive(data.agents[i], permiso, { approvedBy, ref });
  guardarSociedad(dir, data);
  registrarEvento(dir, { type: "DECISION_MADE", agent_id: id, subject: approvedBy, detail: `permiso ${permiso} concedido`, evidence: ref });
  return data.agents[i];
}
