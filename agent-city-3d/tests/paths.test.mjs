import { test } from "node:test";
import assert from "node:assert/strict";
import * as P from "../lib/paths.mjs";

const casa = { id: "house_a", pos: [3, 2], world: [25, 16] };
const oficina = { id: "quant_lab", pos: [2, 1] };
const calle0 = { x: 40, z: 40 };

const iguales = (a, b) => Math.abs(a.x - b.x) < 1e-9 && Math.abs(a.z - b.z) < 1e-9;

test("entrar desde la calle pasa por la puerta antes del interior", () => {
  const r = P.planRuta({ desde: calle0, origen: null, destino: oficina, adentro: true });
  const n = r.puntos.length;
  assert.ok(iguales(r.puntos[n - 1], P.interior(oficina)), "termina dentro");
  assert.ok(iguales(r.puntos[n - 2], P.puerta(oficina)), "la penúltima parada es la puerta");
  assert.equal(r.fallback, false);
});

test("salir de un edificio recorre puerta y luego calle, en ese orden", () => {
  const dentro = P.interior(casa);
  const r = P.planRuta({ desde: dentro, origen: casa, destino: oficina, adentro: false });
  assert.ok(iguales(r.puntos[0], dentro));
  assert.ok(iguales(r.puntos[1], P.puerta(casa)), "primero la puerta de salida");
  assert.ok(iguales(r.puntos[2], P.calle(casa)), "después la calle");
});

test("no hay teletransporte: cada tramo tiene longitud finita y el recorrido es continuo", () => {
  const r = P.planRuta({ desde: calle0, origen: casa, destino: oficina, adentro: true });
  for (let i = 1; i < r.puntos.length; i++) {
    const d = Math.hypot(r.puntos[i].x - r.puntos[i - 1].x, r.puntos[i].z - r.puntos[i - 1].z);
    assert.ok(Number.isFinite(d) && d < 60, `tramo ${i} anómalo: ${d}`);
  }
  assert.ok(P.longitudRuta(r.puntos) > 0);
});

test("ya dentro del mismo edificio no da la vuelta por la calle", () => {
  const dentro = P.interior(oficina);
  const r = P.planRuta({ desde: dentro, origen: oficina, destino: oficina, adentro: true });
  assert.equal(r.puntos.length, 2);
  assert.ok(iguales(r.puntos[1], P.interior(oficina)));
});

test("fallback documentado: sin posición conocida aparece en la acera del destino", () => {
  const r = P.planRuta({ desde: null, origen: null, destino: oficina, adentro: false });
  assert.equal(r.fallback, true);
  assert.ok(iguales(r.puntos[0], P.calle(oficina)));
});

test("ruta entre dos edificios sale, recorre calle y entra por la puerta del destino", () => {
  const r = P.planRuta({ desde: P.interior(casa), origen: casa, destino: oficina, adentro: true });
  const n = r.puntos.length;
  assert.ok(iguales(r.puntos[n - 2], P.puerta(oficina)));
  assert.ok(iguales(r.puntos[n - 1], P.interior(oficina)));
  assert.ok(r.puntos.some((p) => iguales(p, P.calle(oficina))), "pasa por la acera del destino");
});
