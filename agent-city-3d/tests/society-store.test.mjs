import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import * as St from "../lib/society-store.mjs";
import * as S from "../lib/society.mjs";

const propuesta = {
  name: "Market Trainee", id: "market-trainee", role: "Market Watch", mission: "vigilar datos públicos",
  need: "faltan datos de mercado con evidencia", inputs: ["klines públicos"], outputs: ["informe"],
  tools: ["lectura pública"], permissions: ["READ_PUBLIC_DATA"], skills: ["market-data"],
  owner_mentor: "Trading Codex (Claude Leader)", graduation_criteria: "examen ≥ 80 con evidencia",
  success_criteria: "datos verificados", retirement_condition: "sustituido por especialista", start_stage: "TRAINEE",
};

function dirTemporal() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "society-"));
}

test("flujo completo: crear, examinar y graduar por evidencia, con eventos en orden", () => {
  const dir = dirTemporal();
  St.accionCrear(dir, propuesta);
  St.accionExamen(dir, "market-trainee", { curriculum: "market-data", score: 85, min_score: 80, ref: "exam-7" });
  St.accionPromover(dir, "market-trainee", "EXAM");
  St.accionPromover(dir, "market-trainee", "GRADUATED_AGENT", { ref: "exam-7" });
  const data = St.leerSociedad(dir);
  const a = data.agents.find((x) => x.id === "market-trainee");
  assert.equal(a.stage, "GRADUATED_AGENT");
  assert.equal(a.graduated_evidence, "exam-7");
  const tipos = fs.readFileSync(path.join(dir, St.FILE_EVENTS), "utf8").trim().split("\n").map((l) => JSON.parse(l).type);
  assert.deepEqual(tipos, ["AGENT_CREATED", "EXAM_PASSED", "AGENT_PROMOTED", "GRADUATED"]);
});

test("persistencia: el estado sobrevive a un reinicio (nueva lectura desde disco)", () => {
  const dir = dirTemporal();
  St.accionCrear(dir, propuesta);
  const despuesReinicio = St.leerSociedad(dir); // nuevo proceso = nueva lectura
  assert.equal(despuesReinicio.agents[0].id, "market-trainee");
  assert.equal(despuesReinicio.agents[0].stage, "TRAINEE");
});

test("un examen suspendido no permite graduar aunque se intente", () => {
  const dir = dirTemporal();
  St.accionCrear(dir, propuesta);
  St.accionExamen(dir, "market-trainee", { curriculum: "market-data", score: 50, min_score: 80, ref: "exam-x" });
  St.accionPromover(dir, "market-trainee", "EXAM");
  assert.throws(() => St.accionPromover(dir, "market-trainee", "GRADUATED_AGENT", { ref: "exam-x" }), /examen aprobado/);
  assert.equal(St.leerSociedad(dir).agents[0].stage, "EXAM");
});

test("permiso sensible no se concede a un bot aunque lo pida el líder", () => {
  const dir = dirTemporal();
  St.accionCrear(dir, propuesta);
  assert.throws(() => St.accionConcederSensible(dir, "market-trainee", "PAPER_ORDER",
    { approvedBy: S.CLAUDE_LEADER, ref: "decision-1" }), /no reciben/);
});

test("ids duplicados no se persisten", () => {
  const dir = dirTemporal();
  St.accionCrear(dir, propuesta);
  assert.throws(() => St.accionCrear(dir, propuesta), /id duplicado/);
  assert.equal(St.leerSociedad(dir).agents.length, 1);
});

test("escritura atómica: un .tmp huérfano no corrompe el estado previo", () => {
  const dir = dirTemporal();
  St.accionCrear(dir, propuesta);
  fs.writeFileSync(path.join(dir, St.FILE_SOCIETY + ".tmp"), "{ basura a medio escribir", "utf8");
  const data = St.leerSociedad(dir);
  assert.equal(data.agents.length, 1);
  St.accionExamen(dir, "market-trainee", { curriculum: "m", score: 90, min_score: 80, ref: "e" });
  assert.equal(St.leerSociedad(dir).agents[0].exams.length, 1);
});

test("semilla: tres fundadores reales sin duplicar aliases y roles previstos inactivos", () => {
  const v = St.sociedadVacia();
  const aliases = v.founders.flatMap((f) => [f.name, f.alias]);
  assert.equal(new Set(aliases).size, aliases.length);
  assert.equal(v.founders.length, 3);
  assert.ok(v.planned_roles.every((r) => r.status === "PLANNED"));
  assert.ok(v.planned_roles.some((r) => r.name === "Operations Supervisor"));
});
