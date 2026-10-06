import { test } from "node:test";
import assert from "node:assert/strict";
import { auditar, ACCIONES, AUTORIDAD } from "../lib/hr.mjs";

const AHORA = new Date("2026-10-06T12:00:00Z");
const hace = (dias) => new Date(AHORA.getTime() - dias * 86400000).toISOString();
const graduado = (id, extra = {}) => ({ id, stage: "GRADUATED_AGENT", state: "IDLE", skills: ["market-data"], retirement_condition: "sustituido", exams: [], mentor: "Claude Leader", ...extra });
const ev = (agent_id, type, dias = 1, evidence = null) => ({ agent_id, type, observed_at: hace(dias), evidence });

test("TRAIN: examen suspendido se recomienda con su evidencia", () => {
  const a = graduado("m1", { stage: "TRAINEE", exams: [{ curriculum: "market", score: 40, min_score: 80, passed: false, ref: "exam-9" }] });
  const r = auditar({ agents: [a], eventos: [], ahora: AHORA });
  const t = r.recomendaciones.find((x) => x.accion === "TRAIN");
  assert.ok(t);
  assert.deepEqual(t.evidencia, ["exam-9"]);
});

test("MENTOR: dos o más tests fallidos con mentor asignado", () => {
  const a = graduado("q1");
  const eventos = [ev("q1", "TEST_FAILED", 1), ev("q1", "TEST_FAILED", 2)];
  const r = auditar({ agents: [a], eventos, ahora: AHORA });
  assert.ok(r.recomendaciones.some((x) => x.accion === "MENTOR" && x.agente === "q1"));
});

test("PROMOTE sólo para graduado con evidencia positiva y sin fallos", () => {
  const limpio = graduado("s1");
  const eventos = Array.from({ length: 5 }, (_, i) => ev("s1", "TASK_COMPLETED", i + 1, `t-${i}`));
  assert.ok(auditar({ agents: [limpio], eventos, ahora: AHORA }).recomendaciones.some((x) => x.accion === "PROMOTE"));
  const conFallo = [...eventos, ev("s1", "TASK_FAILED", 1)];
  assert.ok(!auditar({ agents: [limpio], eventos: conFallo, ahora: AHORA }).recomendaciones.some((x) => x.accion === "PROMOTE"));
  const bot = { ...limpio, stage: "TRAINEE" };
  assert.ok(!auditar({ agents: [bot], eventos, ahora: AHORA }).recomendaciones.some((x) => x.accion === "PROMOTE"));
});

test("RETIRE o REPLACE sólo con inactividad verificada por evento", () => {
  const solo = graduado("a1", { skills: ["quant"] });
  const viejo = [ev("a1", "TASK_COMPLETED", 30)];
  const sinReemplazo = auditar({ agents: [solo], eventos: viejo, ahora: AHORA });
  assert.ok(sinReemplazo.recomendaciones.some((x) => x.accion === "RETIRE"));
  const reemplazo = graduado("a2", { skills: ["quant"] });
  const conReemplazo = auditar({ agents: [solo, reemplazo], eventos: viejo, ahora: AHORA });
  assert.ok(conReemplazo.recomendaciones.some((x) => x.accion === "REPLACE" && x.agente === "a1"));
});

test("sin ningún evento no se recomienda retirar: queda como sin evidencia", () => {
  const r = auditar({ agents: [graduado("n1")], eventos: [], ahora: AHORA });
  assert.equal(r.recomendaciones.filter((x) => ["RETIRE", "REPLACE"].includes(x.accion)).length, 0);
  assert.deepEqual(r.sinEvidencia, ["n1"]);
});

test("REASSIGN sugiere a un ocioso compatible; nada se aplica automáticamente", () => {
  const actual = graduado("x1", { skills: ["qa"], state: "WORKING" });
  const libre = graduado("x2", { skills: ["market-data", "qa"], state: "IDLE" });
  const backlog = [{ id: "T7", skills: ["qa"], assignedTo: "x1" }];
  const r = auditar({ agents: [actual, libre], eventos: [ev("x1", "TASK_COMPLETED", 1, "e")], backlog, ahora: AHORA });
  assert.ok(r.recomendaciones.some((x) => x.accion === "REASSIGN" && x.agente === "x1"));
  assert.equal(r.authority, AUTORIDAD);
  assert.match(r.nota, /ninguna recomendación se aplica/i);
});

test("el catálogo de acciones es exactamente el pedido", () => {
  assert.deepEqual(ACCIONES, ["TRAIN", "PROMOTE", "REASSIGN", "MENTOR", "RETIRE", "REPLACE"]);
});
