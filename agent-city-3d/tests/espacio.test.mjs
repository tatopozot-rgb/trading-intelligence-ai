import { test } from "node:test";
import assert from "node:assert/strict";
import * as E from "../lib/espacio.mjs";

const persona = (id, home, workplace = null) => ({ id, home, workplace });

test("plantas: edificios altos y los 5 edificios de trabajo real tienen dos plantas; casas, una", () => {
  assert.equal(E.plantasDe("risk_tower"), 2);
  assert.equal(E.plantasDe("command_center"), 2);
  assert.equal(E.plantasDe("trading_floor"), 2);
  // Edificios de trabajo real (lib/life.mjs EDIFICIOS_TRABAJO): necesitan la 2ª planta para que la
  // capacidad (8 escritorios) cubra el máximo real de trabajadores por edificio (verificado: 8).
  assert.equal(E.plantasDe("quant_lab"), 2);
  assert.equal(E.plantasDe("qa_facility"), 2);
  assert.equal(E.plantasDe("engineering_lab"), 2);
  assert.equal(E.plantasDe("market_intel"), 2);
  assert.equal(E.plantasDe("house_a"), 1);
  assert.equal(E.plantasDe("academy"), 1); // edificio normal, sin necesidad de 2ª planta
});

test("estaciones de un edificio de dos plantas usan ambas plantas, no sólo la 0", () => {
  const est = E.estacionesDe("risk_tower");
  assert.equal(est.length, 8); // 4 puestos por planta x 2 plantas
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

test("cada casa tiene litera: 4 rincones x 2 niveles = 8 camas propias, no 4", () => {
  assert.equal(E.CAPACIDAD_CASA, E.CAMAS_BASE.length * 2);
  const r = Array.from({ length: 8 }, (_, i) => persona(`h${i}`, "house_z"));
  const asign = E.asignarEspacios(r);
  // Los primeros 4 van abajo (nivel 0), los siguientes 4 arriba (nivel 1), mismo rincón que su pareja de litera.
  for (let i = 0; i < 4; i++) {
    assert.equal(asign[`h${i}`].cama.nivel, 0);
    assert.equal(asign[`h${i + 4}`].cama.nivel, 1);
    assert.equal(asign[`h${i}`].cama.x, asign[`h${i + 4}`].cama.x);
    assert.equal(asign[`h${i}`].cama.z, asign[`h${i + 4}`].cama.z);
  }
});

test("con 5 compañeros en un edificio de 2 plantas, el 5º ya sube al piso de arriba", () => {
  const r = Array.from({ length: 5 }, (_, i) => persona(`w${i}`, "house_a", "risk_tower"));
  const asign = E.asignarEspacios(r);
  for (const w of ["w0", "w1", "w2", "w3"]) assert.equal(asign[w].estacion.planta, 0);
  assert.equal(asign["w4"].estacion.planta, 1); // el 5º ya no cabe en planta baja (4 puestos)
});

test("hasta llenar la capacidad (4 por planta, 8 en total), nadie comparte escritorio; con más gente, se reparte por turno", () => {
  const r4 = Array.from({ length: 4 }, (_, i) => persona(`f${i}`, "house_a", "risk_tower"));
  const asign4 = E.asignarEspacios(r4);
  const puestos4 = new Set(r4.map((p) => JSON.stringify(asign4[p.id].estacion)));
  assert.equal(puestos4.size, 4);
  const r6 = Array.from({ length: 6 }, (_, i) => persona(`g${i}`, "house_a", "risk_tower"));
  const asign6 = E.asignarEspacios(r6);
  const plantas6 = new Set(r6.map((p) => asign6[p.id].estacion.planta));
  assert.deepEqual([...plantas6].sort(), [0, 1]);
  for (const p of r6) assert.ok(asign6[p.id].estacion); // nadie se queda sin estación, aunque se repita
  // 8 es el máximo real de trabajadores en un mismo edificio al tope de población (ver life.mjs
  // EDIFICIOS_TRABAJO + POBLACION_MAX): con 8 puestos reales, nadie debería compartir ni ahí.
  const r8 = Array.from({ length: 8 }, (_, i) => persona(`m${i}`, "house_a", "risk_tower"));
  const asign8 = E.asignarEspacios(r8);
  const puestos8 = new Set(r8.map((p) => JSON.stringify(asign8[p.id].estacion)));
  assert.equal(puestos8.size, 8, "el máximo real de trabajadores por edificio no debería compartir escritorio");
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
