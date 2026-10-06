import { test } from "node:test";
import assert from "node:assert/strict";
import * as C from "../lib/lifecycle.mjs";

const base = (over = {}) => ({
  id: "sim-01", nombre: "Ana", edad: 10, etapa: "STUDENT", hogar: "h1",
  estudios: { curso: "curso", xp: 0, graduado: false, enCurso: true }, empleo: null, relaciones: [], ...over,
});

test("etapas vitales por edad: niño, estudiante, joven, adulto, senior, jubilado", () => {
  assert.equal(C.etapaPorEdad(3), "CHILD");
  assert.equal(C.etapaPorEdad(12), "STUDENT");
  assert.equal(C.etapaPorEdad(25), "YOUNG_ADULT");
  assert.equal(C.etapaPorEdad(40), "ADULT");
  assert.equal(C.etapaPorEdad(70), "SENIOR");
  assert.equal(C.etapaPorEdad(85), "RETIRED");
});

test("envejecer avanza la edad y cambia de etapa sin pasos día a día", () => {
  const p = avanzar(base({ edad: 17.9 }), 365);
  assert.ok(p.edad > 18);
  assert.equal(p.etapa, "YOUNG_ADULT");
});

function avanzar(p, dias) { return C.avanzarPersona(p, dias); }

test("graduarse exige examen aprobado y lleva a buscar trabajo simulado", () => {
  // Con xp suficiente el examen se evalúa de forma determinista por id.
  const r = avanzar(base({ id: "sim-07", estudios: { curso: "c", xp: 99, graduado: false, enCurso: true } }), 10);
  assert.ok(r.estudios.examen, "debe haber examen");
  assert.equal(r.estudios.examen.simulado, true);
  if (r.estudios.examen.aprobado) {
    assert.equal(r.estudios.graduado, true);
    assert.equal(r.empleo.estado, "SEEKING_WORK");
  } else {
    assert.equal(r.estudios.graduado, false);
    assert.equal(r.empleo, null);
  }
});

test("un examen suspendido no gradúa", () => {
  // Busca un id cuyo examen suspenda para probar la regla.
  let suspendido = null;
  for (let i = 0; i < 200 && !suspendido; i++) {
    const r = avanzar(base({ id: `sim-${i}`, estudios: { curso: "c", xp: 100, graduado: false, enCurso: true } }), 1);
    if (r.estudios.examen && !r.estudios.examen.aprobado) suspendido = r;
  }
  assert.ok(suspendido, "algún id debe suspender");
  assert.equal(suspendido.estudios.graduado, false);
  assert.equal(suspendido.estudios.enCurso, true);
});

test("jubilación a los 65: deja de trabajar, conserva hogar y relaciones", () => {
  const p = base({ edad: 64.9, etapa: "ADULT", hogar: "h9", relaciones: ["sim-02"], empleo: { estado: "WORKING" }, estudios: null });
  const r = avanzar(p, 60);
  assert.equal(r.empleo.estado, "RETIRED");
  assert.equal(r.hogar, "h9");
  assert.deepEqual(r.relaciones, ["sim-02"]);
  assert.equal(r.etapa, "SENIOR");
});

test("nacimiento sólo con pareja adulta y tope de hijos", () => {
  const sinPareja = { id: "h1", miembros: [{ id: "a", etapa: "ADULT" }] };
  assert.equal(C.posibleNacimiento(sinPareja, 2030), null);
  const pareja = { id: "h2", miembros: [{ id: "a", etapa: "ADULT" }, { id: "b", etapa: "YOUNG_ADULT" }] };
  const tope = { id: "h3", miembros: [...pareja.miembros, ...Array.from({ length: 3 }, (_, i) => ({ id: `c${i}`, etapa: "CHILD" }))] };
  assert.equal(C.posibleNacimiento(tope, 2030), null);
});

test("nacimientos deterministas: mismo hogar y año, mismo resultado", () => {
  const h = { id: "h5", miembros: [{ id: "a", etapa: "ADULT" }, { id: "b", etapa: "ADULT" }] };
  assert.deepEqual(C.posibleNacimiento(h, 2031), C.posibleNacimiento(h, 2031));
});

test("progresión offline: primera ejecución no progresa; el tiempo se convierte en días acotados", () => {
  assert.equal(C.progresoOffline({ ultimoTs: null, ahoraTs: Date.now() }).diasSim, 0);
  const t0 = Date.parse("2026-10-06T00:00:00Z");
  const r = C.progresoOffline({ ultimoTs: t0, ahoraTs: t0 + 5 * 3600000 });
  assert.equal(r.diasSim, 5);
  const enorme = C.progresoOffline({ ultimoTs: t0, ahoraTs: t0 + 365 * 10 * 24 * 3600000 });
  assert.equal(enorme.diasSim, C.MAX_DIAS_SIM_OFFLINE);
  assert.match(enorme.motivo, /tope/);
});

test("aplicar offline agrega sin bucle: dos años de progresión llegan al mismo punto que un salto", () => {
  const p = base({ edad: 20, etapa: "YOUNG_ADULT", estudios: null });
  const un = C.avanzarPersona(p, 730);
  const dos = C.avanzarPersona(C.avanzarPersona(p, 365), 365);
  assert.ok(Math.abs(un.edad - dos.edad) < 1e-9);
  assert.equal(un.etapa, dos.etapa);
});

test("la progresión offline no contiene referencias a trading, órdenes ni riesgo", async () => {
  const fs = await import("node:fs");
  // Sólo código: los comentarios describen lo que NO se toca, y pueden nombrarlo.
  const texto = fs.readFileSync(new URL("../lib/lifecycle.mjs", import.meta.url), "utf8")
    .split(String.fromCharCode(10)).filter((l) => !l.trim().startsWith("//")).join(String.fromCharCode(10));
  for (const palabra of ["trading", "order", "orden", "paper", "risk", "saldo", "capital", "fetch(", "binance"]) {
    assert.ok(!texto.toLowerCase().includes(palabra), `no debe mencionar ${palabra}`);
  }
});

test("aplicarOffline sobre una población mantiene el tamaño y no muta la entrada", () => {
  const pob = [base({ id: "x1" }), base({ id: "x2" })];
  const antes = JSON.stringify(pob);
  const t0 = Date.parse("2026-10-01T00:00:00Z");
  const r = C.aplicarOffline(pob, { ultimoTs: t0, ahoraTs: t0 + 24 * 3600000 });
  assert.equal(r.poblacion.length, 2);
  assert.equal(JSON.stringify(pob), antes);
});
