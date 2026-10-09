import { test } from "node:test";
import assert from "node:assert/strict";
import { deriveCity } from "../lib/model.mjs";
import { residentes, poblacionObjetivo } from "../lib/life.mjs";

// Presupuesto de CPU para el derivado del modelo (no incluye render). Umbral holgado para no ser flaky.
const AHORA = new Date("2026-10-06T12:00:00Z");
function escenario(demanda) {
  const tasks = Array.from({ length: demanda }, (_, i) => ({ task: `T${i}`, status: "PENDING" }));
  const events = Array.from({ length: 200 }, (_, i) => ({ type: "TASK_COMPLETED", subject: "Claude Code Local",
    detail: `e${i}`, observed_at: new Date(AHORA.getTime() - i * 60000).toISOString() }));
  const society = { agents: Array.from({ length: 60 }, (_, i) => ({ id: `s${i}`, name: `S${i}`, stage: "GRADUATED_AGENT", status: "ACTIVE", state: "IDLE", skills: [] })), planned_roles: [] };
  const snapshot = { generated_at: AHORA.toISOString(), sync: { ok: true }, tasks, agents: [] };
  return { snapshot, society, events, now: AHORA };
}

for (const n of [10, 40, 100]) {
  test(`derivado de ciudad con ${n}+ avatares está dentro de presupuesto`, () => {
    const demanda = Math.ceil((n - 6) / 1.5);
    const e = escenario(demanda);
    const t0 = performance.now();
    const c = deriveCity(e);
    const ms = performance.now() - t0;
    assert.ok(c.simulation.population >= n - 6 || c.simulation.population === poblacionObjetivo(demanda));
    // Cada ciclo de refresco (cada 30 s) debe costar mucho menos que un frame.
    assert.ok(ms < 50, `derivado ${ms.toFixed(1)} ms para ${c.agents.length} agentes`);
    console.log(`perf n≈${n}: agentes=${c.agents.length} derivado=${ms.toFixed(2)} ms`);
  });
}

test("con 100+ residentes la vida simulada no produce estados fuera del vocabulario SIM_", () => {
  const e = escenario(100);
  const c = deriveCity(e);
  for (const a of c.agents.filter((x) => x.kind === "simulated")) assert.match(a.state, /^SIM_/);
  assert.ok(residentes(100).length >= 40 || residentes(100).length === 40);
});
