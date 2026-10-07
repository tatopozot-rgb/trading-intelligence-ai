import { test } from "node:test";
import assert from "node:assert/strict";
import * as E from "../lib/espacio.mjs";

const persona = (id, home, workplace = null) => ({ id, home, workplace });

test("plantas: sólo los edificios altos tienen dos plantas; el resto, una", () => {
  assert.equal(E.plantasDe("risk_tower"), 2);
  assert.equal(E.plantasDe("command_center"), 2);
  assert.equal(E.plantasDe("trading_floor"), 2);
  assert.equal(E.plantasDe("quant_lab"), 1);
  assert.equal(E.plantasDe("house_a"), 1);
});

test("estaciones de un edificio de dos plantas usan ambas plantas, no sólo la 0", () => {
  const est = E.estacionesDe("risk_tower");
  assert.equal(est.length, 8);
  assert.ok(est.some((e) => e.planta === 0) && est.some((e) => e.planta === 1));
});

test("asignación estable: misma lista de residentes, mismo resultado siempre", () => {
  const r = [persona("a", "house_a", "quant_lab"), persona("b", "house_a"), persona("c", "house_a", "quant_lab")];
  assert.deepEqual(E.asignarEspacios(r), E.asignarEspacios(r));
});

test("compañeros de casa no comparten cama mientras haya camas libres", () => {
  const r = Array.from({ length: E.CAPACIDAD_CASA }, (_, i) => persona(`p${i}`, "house_a"));
  const asign = E.asignarEspacios(r);
  const camas = r.map((p) => JSON.stringify(asign[p.id].cama));
  assert.equal(new Set(camas).size, E.CAPACIDAD_CASA, "cada uno debería tener una cama distinta");
});

test("compañeros de trabajo se reparten entre estaciones y plantas, no se apilan en una sola", () => {
  const r = Array.from({ length: 8 }, (_, i) => persona(`w${i}`, "house_a", "risk_tower"));
  const asign = E.asignarEspacios(r);
  const plantas = new Set(r.map((p) => asign[p.id].estacion.planta));
  const puestos = new Set(r.map((p) => JSON.stringify(asign[p.id].estacion)));
  assert.deepEqual([...plantas].sort(), [0, 1]);
  assert.equal(puestos.size, 8);
});

test("quien no trabaja no recibe estación", () => {
  const asign = E.asignarEspacios([persona("solo-casa", "house_b")]);
  assert.equal(asign["solo-casa"].estacion, null);
  assert.ok(asign["solo-casa"].cama);
});

test("con más gente que camas, se reparten por turno (round-robin) en vez de fallar", () => {
  const r = Array.from({ length: E.CAPACIDAD_CASA + 2 }, (_, i) => persona(`q${i}`, "house_c"));
  const asign = E.asignarEspacios(r);
  for (const p of r) assert.ok(asign[p.id].cama);
});
