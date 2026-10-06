import { test } from "node:test";
import assert from "node:assert/strict";
import * as L from "../lib/life.mjs";

const REAL = ["WORKING", "REVIEWING", "BLOCKED", "IDLE", "NOT_SYNCED", "STALE", "DONE", "IN_PROGRESS"];

test("población crece con la demanda real y tiene tope", () => {
  assert.equal(L.poblacionObjetivo(0), L.POBLACION_BASE);
  assert.ok(L.poblacionObjetivo(5) > L.poblacionObjetivo(1));
  assert.equal(L.poblacionObjetivo(10000), L.POBLACION_MAX);
  assert.equal(L.residentes(3).length, L.poblacionObjetivo(3));
});

test("residentes deterministas: mismo índice, mismo residente", () => {
  assert.deepEqual(L.residentes(4), L.residentes(4));
});

test("tipos de residente: trainees, trabajadores y vecinos; los trainees van a academia", () => {
  const r = L.residentes(10);
  assert.ok(r.some((x) => x.tipo === "trainee") && r.some((x) => x.tipo === "worker") && r.some((x) => x.tipo === "resident"));
  for (const x of r.filter((x) => x.tipo === "trainee")) assert.equal(L.actividadPara(x, 9).destino, "academy");
});

test("cada hora tiene destino: nadie se queda botado", () => {
  const r = L.residentes(6);
  for (const x of r) for (let h = 0; h < 24; h++) {
    const a = L.actividadPara(x, h);
    assert.ok(a.destino, `sin destino ${x.id} a las ${h}h`);
  }
});

test("de noche duermen en casa; por la mañana trabajan o estudian", () => {
  const r = L.residentes(6);
  for (const x of r) {
    assert.equal(L.actividadPara(x, 23).actividad, "SLEEPING");
    assert.equal(L.actividadPara(x, 2).destino, x.home);
  }
  const trabajador = r.find((x) => x.tipo === "worker");
  assert.equal(L.actividadPara(trabajador, 10).actividad, "WORKING");
  assert.equal(L.actividadPara(trabajador, 10).destino, trabajador.workplace);
});

test("standby útil: nunca se queda quieto, sin destino vacío", () => {
  for (const x of L.residentes(6)) {
    const s = L.standbyPara(x);
    assert.ok(s.destino);
    assert.notEqual(s.actividad, "IDLE");
  }
});

test("graduación simulada sólo con examen aprobado; con XP insuficiente no hay examen", () => {
  const t = L.residentes(6).find((x) => x.tipo === "trainee");
  const pronto = L.progresarTrainee(t, 2);
  assert.equal(pronto.examen, null);
  assert.equal(pronto.stage, "TRAINEE");
  let r = t;
  for (let i = 0; i < 30; i++) r = L.progresarTrainee(r, 1);
  assert.ok(r.examen);
  assert.equal(r.examen.simulated, true);
  assert.equal(r.stage === "GRADUATED_SIM", r.examen.passed === true);
});

test("vocabulario de actividad simulada fijo; el modelo lo prefija con SIM_ (ver model.test)", () => {
  const acts = new Set();
  for (const x of L.residentes(20)) for (let h = 0; h < 24; h++) acts.add(L.actividadPara(x, h).actividad);
  assert.deepEqual([...acts].sort(), ["BREAK", "LEISURE", "SLEEPING", "STUDYING", "TRAVEL", "WORKING"]);
  assert.ok(REAL.includes("WORKING"), "WORKING es estado real y no debe emitirse sin prefijo");
});

test("roles simulados están marcados como simulados", () => {
  for (const r of L.ROLES_SIMULADOS) assert.equal(r.kind, "simulated");
  assert.ok(L.ROLES_SIMULADOS.some((r) => r.role === "recruiter"));
  assert.ok(L.ROLES_SIMULADOS.some((r) => r.role === "auditor"));
});
