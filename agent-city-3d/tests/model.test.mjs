import { test } from "node:test";
import assert from "node:assert/strict";
import { deriveCity, agentByAlias, AGENTS, BUILDINGS, ALL_EVENT_TYPES } from "../lib/model.mjs";

const AHORA = new Date("2026-10-06T04:00:00Z");
const fresco = (estado_por_agente = {}, extra = {}) => ({
  generated_at: "2026-10-06T03:55:00Z",
  sync: { ok: true },
  agents: [
    { key: "codex", state: estado_por_agente.codex ?? "NOT_SYNCED", current_task: null, last_result: null, heartbeat: {} },
    { key: "gpt", state: estado_por_agente.gpt ?? "NOT_SYNCED", current_task: null, last_result: null, heartbeat: {} },
    { key: "local", state: estado_por_agente.local ?? "NOT_SYNCED", current_task: null, last_result: null, heartbeat: {} },
  ],
  ...extra,
});
const ev = (type, subject, minutosAtras = 5, detail = "") => ({
  type, subject, detail, observed_at: new Date(AHORA.getTime() - minutosAtras * 60000).toISOString(),
});
const agente = (city, key) => city.agents.find((a) => a.key === key);

test("WORKING sólo con evento AGENT_WORKING o TASK_STARTED reciente", () => {
  const sin = deriveCity({ snapshot: fresco({ codex: "REVIEW" }), events: [], now: AHORA });
  assert.equal(agente(sin, "codex").state, "REVIEWING");
  assert.equal(agente(sin, "codex").target, "command_center");
  const con = deriveCity({ snapshot: fresco({ codex: "REVIEW" }), events: [ev("TASK_STARTED", "Trading Codex (cloud)")], now: AHORA });
  assert.equal(agente(con, "codex").state, "WORKING");
  assert.equal(agente(con, "codex").target, "engineering_lab");
});

test("un estado documentado nunca se convierte en WORKING", () => {
  const c = deriveCity({ snapshot: fresco({ gpt: "BLOCKED", local: "IN_PROGRESS" }), events: [], now: AHORA });
  assert.equal(agente(c, "gpt").state, "BLOCKED");
  assert.equal(agente(c, "local").state, "IN_PROGRESS");
  for (const a of c.agents) assert.notEqual(a.state, "WORKING");
});

test("sin evidencia el agente va a residential con NOT_SYNCED", () => {
  const c = deriveCity({ snapshot: fresco(), events: [], now: AHORA });
  assert.equal(agente(c, "gpt").state, "NOT_SYNCED");
  assert.equal(agente(c, "gpt").target, "residential");
  assert.match(agente(c, "gpt").reason, /NOT_SYNCED/);
});

test("sync caída o snapshot viejo marca STALE y no inventa estado", () => {
  const caido = deriveCity({ snapshot: { ...fresco({ codex: "REVIEW" }), sync: { ok: false } }, events: [], now: AHORA });
  assert.equal(caido.syncOk, false);
  assert.equal(agente(caido, "codex").state, "STALE");
  assert.ok(caido.banners.some((b) => b.startsWith("SYNC STALE")));
  const viejo = deriveCity({ snapshot: { ...fresco({ codex: "REVIEW" }), generated_at: "2026-10-05T00:00:00Z" }, events: [], now: AHORA });
  assert.equal(viejo.syncOk, false);
});

test("sin snapshot ni eventos: sin datos, nadie trabaja", () => {
  const c = deriveCity({ snapshot: null, events: [], now: AHORA });
  assert.ok(c.banners.some((b) => b.startsWith("SIN DATOS")));
  for (const a of c.agents) assert.notEqual(a.state, "WORKING");
});

test("NO_TRADE pinta Trading Floor y muestra CAPITAL PRESERVED", () => {
  const c = deriveCity({ snapshot: fresco(), events: [ev("NO_TRADE", "Claude Code Local", 2, "sin ventaja")], now: AHORA });
  assert.equal(c.buildings.find((b) => b.id === "trading_floor").pulses.length, 1);
  assert.ok(c.banners.includes("CAPITAL PRESERVED — NO_TRADE"));
});

test("TEST_FAILED y BACKTEST_FINISHED van a sus distritos", () => {
  const c = deriveCity({ snapshot: fresco(), events: [ev("TEST_FAILED", "Claude Code Local"), ev("BACKTEST_FINISHED", "Quant", 3)], now: AHORA });
  assert.equal(c.buildings.find((b) => b.id === "qa_facility").pulses[0].type, "TEST_FAILED");
  assert.equal(c.buildings.find((b) => b.id === "quant_lab").pulses[0].type, "BACKTEST_FINISHED");
});

test("eventos de más de 2 horas no cuentan como actividad actual", () => {
  const c = deriveCity({ snapshot: fresco(), events: [ev("TASK_STARTED", "Claude Code Local", 300)], now: AHORA });
  assert.notEqual(agente(c, "local").state, "WORKING");
});

test("tipos desconocidos se ignoran", () => {
  const c = deriveCity({ snapshot: fresco(), events: [ev("INVENTADO", "Claude Code Local")], now: AHORA });
  assert.equal(c.feed.length, 0);
});

test("tres identidades reales, sin alias duplicados", () => {
  assert.equal(AGENTS.length, 3);
  assert.equal(agentByAlias("Trading Codex (cloud)").key, "codex");
  assert.equal(agentByAlias("Claude Leader").key, "codex");
  assert.equal(agentByAlias("Trading Claude-Work (GPT Work)").key, "gpt");
  assert.equal(agentByAlias("Claude Code local").key, "local");
  assert.equal(agentByAlias("PowerShell").key, "local");
  assert.equal(agentByAlias("alguien nuevo"), null);
});

test("Life Simulation separada: sólo residential y park; academy es operativa (exámenes reales)", () => {
  const sim = BUILDINGS.filter((b) => b.district === "simulation").map((b) => b.id).sort();
  assert.deepEqual(sim, ["house_a", "house_b", "house_c", "house_d", "house_e", "park", "residential"]);
  assert.equal(BUILDINGS.find((b) => b.id === "academy").district, "operational");
  const c = deriveCity({ snapshot: fresco(), events: [], now: AHORA });
  for (const a of c.agents.filter((x) => x.kind === "simulated")) assert.match(a.state, /^SIM_/);
});

test("todos los eventos mínimos requeridos existen en el modelo", () => {
  for (const t of ["TASK_STARTED", "TASK_COMPLETED", "AGENT_WORKING", "AGENT_REVIEWING", "AGENT_IDLE", "AGENT_BLOCKED",
    "TEST_PASSED", "TEST_FAILED", "BACKTEST_STARTED", "BACKTEST_FINISHED", "RISK_APPROVED", "RISK_REJECTED",
    "NO_TRADE", "TRADE_OPENED", "TRADE_CLOSED", "KILL_SWITCH_TRIGGERED", "SYSTEM_RECOVERED"]) {
    assert.ok(ALL_EVENT_TYPES.includes(t), t);
  }
});

test("graduación simulada: pulso en la universidad y aviso separado de los banners reales", () => {
  const life = { poblacion: [{ id: "sim-01", nombre: "Ana", graduadoEn: new Date(AHORA.getTime() - 5 * 60000).toISOString() }] };
  const c = deriveCity({ snapshot: fresco(), events: [], life, now: AHORA });
  const u = c.buildings.find((b) => b.id === "university");
  assert.ok(u.pulses.some((p) => p.type === "GRADUATED_SIM"));
  assert.ok(c.simBanners.some((b) => b.includes("Ana")));
  assert.equal(c.banners.some((b) => b.includes("Ana")), false);
});

test("los residentes simulados llevan cama propia y, si trabajan, estación y planta", () => {
  const c = deriveCity({ snapshot: fresco(), events: [], now: AHORA });
  const sims = c.agents.filter((a) => a.kind === "simulated" && a.stage !== "SIM_ROLE");
  assert.ok(sims.length > 0);
  for (const s of sims) {
    assert.ok(s.cama && typeof s.cama.x === "number");
    if (s.tipo === "worker") assert.ok(s.estacion && typeof s.estacion.planta === "number");
    else assert.equal(s.estacion, null);
  }
});

// Revisión cruzada de GPT Work (reviews/gpt_work/agent_city_acceptance.test.mjs).
test("un snapshot con fecha futura o ilegible no prueba sincronización", () => {
  for (const generated_at of ["2026-10-07T04:00:00Z", "2026-10-06T04:00:01Z", "no-es-fecha"]) {
    const c = deriveCity({ snapshot: fresco({ gpt: "BLOCKED" }, { generated_at }), events: [], now: AHORA });
    assert.equal(c.syncOk, false, generated_at);
    assert.equal(agente(c, "gpt").state, "STALE", generated_at);
  }
  assert.equal(deriveCity({ snapshot: fresco(), events: [], now: AHORA }).syncOk, true);
});

test("un evento con fecha futura o ilegible no cuenta como reciente", () => {
  for (const minutosAtras of [-1, -24 * 60]) {
    const c = deriveCity({ snapshot: fresco(), events: [ev("TASK_STARTED", "GPT Work", minutosAtras), ev("NO_TRADE", "", minutosAtras)], now: AHORA });
    assert.notEqual(agente(c, "gpt").state, "WORKING");
    assert.equal(agente(c, "gpt").lastEvent, null);
    for (const b of c.buildings) assert.equal(b.pulses.length, 0);
    assert.equal(c.banners.some((t) => t.includes("NO_TRADE")), false);
  }
  const ilegible = { type: "TASK_STARTED", subject: "GPT Work", observed_at: "no-es-fecha" };
  assert.notEqual(agente(deriveCity({ snapshot: fresco(), events: [ilegible], now: AHORA }), "gpt").state, "WORKING");
  // El instante exacto de "ahora" sí es reciente.
  assert.equal(agente(deriveCity({ snapshot: fresco(), events: [ev("TASK_STARTED", "GPT Work", 0)], now: AHORA }), "gpt").state, "WORKING");
});

test("el texto WORKING de un snapshot no concede WORKING sin evento observado", () => {
  const sin = deriveCity({ snapshot: fresco({ gpt: "WORKING" }), events: [], now: AHORA });
  assert.equal(agente(sin, "gpt").state, "IN_PROGRESS");
  assert.equal(agente(sin, "gpt").reason, "WORKING documentado sin evento observado");
  assert.equal(agente(sin, "gpt").target, "gpt_ops");
  const con = deriveCity({ snapshot: fresco({ gpt: "WORKING" }), events: [ev("AGENT_WORKING", "GPT Work")], now: AHORA });
  assert.equal(agente(con, "gpt").state, "WORKING");
  const reposo = deriveCity({ snapshot: fresco({ gpt: "WORKING" }), events: [ev("AGENT_IDLE", "GPT Work")], now: AHORA });
  assert.equal(agente(reposo, "gpt").state, "IDLE");
});
