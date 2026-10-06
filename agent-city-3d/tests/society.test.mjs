import { test } from "node:test";
import assert from "node:assert/strict";
import * as S from "../lib/society.mjs";

const propuesta = (over = {}) => ({
  name: "Market Trainee", id: "market-trainee", role: "Market Watch", mission: "vigilar datos públicos",
  need: "faltan datos de mercado con evidencia", inputs: ["klines públicos"], outputs: ["informe de datos"],
  tools: ["lectura pública"], permissions: ["READ_PUBLIC_DATA"], skills: ["market-data"],
  owner_mentor: "Trading Codex (Claude Leader)", graduation_criteria: "examen ≥ 80 con evidencia",
  success_criteria: "datos verificados", retirement_condition: "sustituido por especialista", ...over,
});

test("Foundry rechaza propuesta incompleta y decorativa", () => {
  const sinCampos = S.validateFoundryProposal({ ...propuesta(), need: "", owner_mentor: undefined });
  assert.equal(sinCampos.ok, false);
  assert.match(sinCampos.errores.join(), /faltan campos/);
  const decorativa = S.validateFoundryProposal({ ...propuesta(), need: "agente decorativo para la ciudad" });
  assert.equal(decorativa.ok, false);
  assert.throws(() => S.createAgentRecord({ ...propuesta(), need: "" }, []), /Foundry rechaza/);
});

test("Foundry no concede permisos sensibles al crear", () => {
  const v = S.validateFoundryProposal({ ...propuesta(), permissions: ["PAPER_ORDER"] });
  assert.equal(v.ok, false);
  assert.throws(() => S.createAgentRecord({ ...propuesta(), permissions: ["READ_PUBLIC_DATA", "PAPER_ORDER"] }, []), /permisos sensibles/);
});

test("un bot empieza en BOT, con status LOCKED y sin permisos sensibles", () => {
  const r = S.createAgentRecord(propuesta(), []);
  assert.equal(r.stage, "BOT");
  assert.equal(r.status, "LOCKED");
  assert.deepEqual(r.permissions, ["READ_PUBLIC_DATA"]);
  assert.equal(r.level, 1);
  assert.equal(r.xp, 0);
});

test("id duplicado se rechaza", () => {
  const r = S.createAgentRecord(propuesta(), []);
  assert.throws(() => S.createAgentRecord(propuesta(), [r]), /id duplicado/);
});

test("no se puede saltar etapas del pipeline", () => {
  const r = S.createAgentRecord(propuesta(), []);
  assert.throws(() => S.promote(r, "GRADUATED_AGENT", { ref: "x" }), /transición inválida/);
  assert.equal(S.canPromote(r, "RECRUIT"), true);
});

test("graduar exige examen aprobado con puntuación y evidencia; el tiempo no cuenta", () => {
  let r = S.createAgentRecord(propuesta({ start_stage: "TRAINEE" }), []);
  r = S.recordExam(r, { curriculum: "market", score: 70, min_score: 80, ref: "exam-1" });
  assert.throws(() => S.promote({ ...r, stage: "EXAM" }, "GRADUATED_AGENT", { ref: "exam-1" }), /examen aprobado/);
  r = S.recordExam(r, { curriculum: "market", score: 85, min_score: 80, ref: "exam-2" });
  assert.throws(() => S.promote({ ...r, stage: "EXAM" }, "GRADUATED_AGENT", null), /evidencia/);
  const g = S.promote({ ...r, stage: "EXAM" }, "GRADUATED_AGENT", { ref: "exam-2" });
  assert.equal(g.stage, "GRADUATED_AGENT");
  assert.equal(g.graduated_evidence, "exam-2");
});

test("suspender un examen devuelve a TRAINEE y no gradúa", () => {
  const r = S.recordExam(S.createAgentRecord(propuesta({ start_stage: "TRAINEE" }), []),
    { curriculum: "market", score: 40, min_score: 80, ref: "exam-x" });
  assert.equal(r.exams[0].passed, false);
  assert.equal(S.canPromote({ ...r, stage: "EXAM" }, "TRAINEE"), true);
  assert.throws(() => S.promote({ ...r, stage: "EXAM" }, "GRADUATED_AGENT", { ref: "exam-x" }), /examen aprobado/);
});

test("passed declarado no puede contradecir la puntuación", () => {
  const r = S.createAgentRecord(propuesta({ start_stage: "TRAINEE" }), []);
  assert.throws(() => S.recordExam(r, { curriculum: "m", score: 40, min_score: 80, passed: true }), /no coincide/);
});

test("permisos sensibles: sólo Claude Leader, sólo graduados, con referencia", () => {
  const bot = S.createAgentRecord(propuesta(), []);
  assert.throws(() => S.grantSensitive(bot, "PAPER_ORDER", { approvedBy: S.CLAUDE_LEADER, ref: "d1" }), /no reciben/);
  const grad = { ...bot, stage: "GRADUATED_AGENT" };
  assert.throws(() => S.grantSensitive(grad, "PAPER_ORDER", { approvedBy: "GPT Work", ref: "d1" }), /solo Claude Leader/);
  assert.throws(() => S.grantSensitive(grad, "PAPER_ORDER", { approvedBy: S.CLAUDE_LEADER }), /sin referencia/);
  const ok = S.grantSensitive(grad, "PAPER_ORDER", { approvedBy: S.CLAUDE_LEADER, ref: "d1" });
  assert.ok(ok.permissions.includes("PAPER_ORDER"));
});

test("XP tiene tope diario y no concede permisos", () => {
  const eventos = Array.from({ length: 30 }, () => ({ type: "TASK_COMPLETED", agent_id: "a", observed_at: "2026-10-06T10:00:00Z" }));
  const xp = S.xpFromEvents(eventos, "2026-10-06");
  assert.equal(xp.a, S.XP_DAILY_CAP);
  assert.equal(S.xpFromEvents([{ type: "TASK_COMPLETED", agent_id: "a", observed_at: "2026-10-05T10:00:00Z" }], "2026-10-06").a, undefined);
});

const grad = (id, skills = ["market-data"], state = "IDLE") => ({ id, stage: "GRADUATED_AGENT", state, skills });

test("supervisor asigna a agente graduado compatible y ocioso", () => {
  const r = S.supervise({ backlog: [{ id: "T1", skills: ["market-data"] }], agents: [grad("m1")], now: "2026-10-06T10:00:00Z" });
  assert.deepEqual(r.recomendaciones[0], { task: "T1", agent: "m1", accion: "ASIGNAR", motivo: "habilidades compatibles y disponible" });
});

test("supervisor no inventa trabajo si el backlog está vacío", () => {
  const r = S.supervise({ backlog: [], agents: [grad("m1")], now: "2026-10-06T10:00:00Z" });
  assert.equal(r.recomendaciones.length, 0);
  assert.match(r.nota, /no se inventa trabajo/);
});

test("bots y trainees nunca reciben trabajo operativo", () => {
  const bot = { id: "b1", stage: "TRAINEE", state: "IDLE", skills: ["market-data"] };
  const r = S.supervise({ backlog: [{ id: "T1", skills: ["market-data"] }], agents: [bot], now: "2026-10-06T10:00:00Z" });
  assert.equal(r.recomendaciones.length, 0);
  assert.equal(r.escalados.length, 1);
});

test("tarea crítica sin nadie despierto: despertar a un dormido compatible", () => {
  const r = S.supervise({ backlog: [{ id: "T1", skills: ["market-data"] }], agents: [grad("m1", ["market-data"], "SLEEPING")], now: "2026-10-06T10:00:00Z" });
  assert.equal(r.recomendaciones[0].accion, "DESPERTAR_Y_ASIGNAR");
});

test("tarea sensible se escala a Claude Leader; bloqueo largo se escala", () => {
  const r = S.supervise({ backlog: [{ id: "T9", sensitive: true }],
    agents: [{ id: "x", state: "BLOCKED", blocked_since: "2026-10-04T00:00:00Z" }], now: "2026-10-06T10:00:00Z" });
  assert.equal(r.authority, S.CLAUDE_LEADER);
  assert.ok(r.escalados.some((e) => e.task === "T9"));
  assert.ok(r.escalados.some((e) => e.agent === "x"));
});

test("debate: una sola ronda de challenge y después decide Claude Leader", () => {
  let d = S.newDebate("subir umbral", "GPT Work");
  d = S.debateStep(d, { from: "Codex", type: "CHALLENGE" });
  d = S.debateStep(d, { from: "Local", type: "CHALLENGE" });
  assert.equal(d.state, "DECISION");
  assert.equal(d.decided_by, S.CLAUDE_LEADER);
  d = S.debateStep(d, { from: S.CLAUDE_LEADER, type: "OUTCOME", outcome: "TASK" });
  assert.equal(d.state, "EXECUTION");
  d = S.debateStep(d, { from: "Local", type: "DONE" });
  d = S.debateStep(d, { from: "Codex", type: "REVIEWED" });
  assert.equal(d.state, "CLOSED");
  assert.equal(d.outcome, "TASK");
});

test("debate: acuerdo directo y resultado de rechazo; resultado inválido se rechaza", () => {
  let d = S.debateStep(S.newDebate("x", "A"), { from: "B", type: "AGREE" });
  assert.equal(d.decided_by, "consensus");
  d = S.debateStep(d, { from: "A", type: "OUTCOME", outcome: "REJECTED" });
  assert.equal(d.state, "CLOSED");
  assert.throws(() => S.debateStep(S.debateStep(S.newDebate("y", "A"), { from: "B", type: "AGREE" }), { from: "A", type: "OUTCOME", outcome: "MAYBE" }), /resultado inválido/);
  assert.throws(() => S.debateStep(S.newDebate("z", "A"), { from: "A", type: "REVIEWED" }), /transición/);
});
