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
  assert.equal(est.length, 4); // 2 puestos por planta x 2 plantas
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

test("con 3 compañeros en un edificio de 2 plantas, el tercero ya sube al piso de arriba", () => {
  const r = Array.from({ length: 3 }, (_, i) => persona(`w${i}`, "house_a", "risk_tower"));
  const asign = E.asignarEspacios(r);
  assert.equal(asign["w0"].estacion.planta, 0);
  assert.equal(asign["w1"].estacion.planta, 0);
  assert.equal(asign["w2"].estacion.planta, 1); // el 3ro ya no cabe en planta baja (2 puestos)
});

test("hasta llenar la capacidad (4), nadie comparte escritorio; con más gente, se reparte por turno", () => {
  const r4 = Array.from({ length: 4 }, (_, i) => persona(`f${i}`, "house_a", "risk_tower"));
  const asign4 = E.asignarEspacios(r4);
  const puestos4 = new Set(r4.map((p) => JSON.stringify(asign4[p.id].estacion)));
  assert.equal(puestos4.size, 4);
  const r6 = Array.from({ length: 6 }, (_, i) => persona(`g${i}`, "house_a", "risk_tower"));
  const asign6 = E.asignarEspacios(r6);
  const plantas6 = new Set(r6.map((p) => asign6[p.id].estacion.planta));
  assert.deepEqual([...plantas6].sort(), [0, 1]);
  for (const p of r6) assert.ok(asign6[p.id].estacion); // nadie se queda sin estación, aunque se repita
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
