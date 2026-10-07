import { test } from "node:test";
import assert from "node:assert/strict";
import * as L from "../lib/life.mjs";

const ACTIVIDADES = ["SLEEPING", "TRAVEL", "COMMUTING", "STUDYING", "WORKING", "SEEKING_WORK", "MEETING", "RESTING", "LEISURE"];
const ROL_ACTIVIDADES = ["MEETING", "ON_DUTY", "MENTORING", "RESTING"];

test("población crece con la demanda real y tiene tope", () => {
  assert.equal(L.poblacionObjetivo(0), L.POBLACION_BASE);
  assert.ok(L.poblacionObjetivo(5) > L.poblacionObjetivo(1));
  assert.equal(L.poblacionObjetivo(10000), L.POBLACION_MAX);
});

test("sin demanda no hay aprendices ni puestos de trabajo (no se inventa trabajo)", () => {
  const r = L.residentes(0);
  assert.equal(r.length, L.POBLACION_BASE);
  assert.ok(r.every((x) => x.tipo === "resident"));
  assert.equal(L.reparto(0).aprendices, 0);
  assert.equal(L.reparto(0).puestos, 0);
});

test("aprendices y puestos crecen con la demanda y no superan la población", () => {
  const p = L.reparto(9);
  assert.ok(p.aprendices >= 1 && p.aprendices <= L.APRENDICES_MAX);
  assert.equal(p.puestos, Math.min(9, p.n - p.aprendices));
  const r = L.residentes(9);
  assert.equal(r.filter((x) => x.tipo === "trainee").length, p.aprendices);
  assert.equal(r.filter((x) => x.tipo === "worker").length, p.puestos);
});

test("residentes deterministas: mismo índice, mismo residente", () => {
  assert.deepEqual(L.residentes(4), L.residentes(4));
});

test("cada hora tiene destino: nadie se queda botado", () => {
  for (const x of L.residentes(12)) for (let h = 0; h < 24; h++) {
    const a = L.actividadPara(x, h);
    assert.ok(a.destino, `sin destino ${x.id} a las ${h}h`);
    assert.ok(ACTIVIDADES.includes(a.actividad), `actividad inesperada ${a.actividad}`);
  }
});

test("de noche duermen en casa", () => {
  for (const x of L.residentes(6)) {
    assert.equal(L.actividadPara(x, 23).actividad, "SLEEPING");
    assert.equal(L.actividadPara(x, 2).destino, x.home);
  }
});

test("trabajador con puesto trabaja; sin puesto busca trabajo y no se queda quieto", () => {
  const conPuesto = { ...L.residentes(6).find((x) => x.tipo === "resident"), tipo: "worker", conPuesto: true, workplace: "quant_lab" };
  const sinPuesto = { ...conPuesto, conPuesto: false };
  assert.equal(L.actividadPara(conPuesto, 9).actividad, "WORKING");
  assert.equal(L.actividadPara(conPuesto, 9).destino, "quant_lab");
  assert.equal(L.actividadPara(sinPuesto, 9).actividad, "SEEKING_WORK");
  assert.equal(L.actividadPara(sinPuesto, 9).destino, "command_center");
  assert.equal(L.actividadPara(sinPuesto, 14).actividad, "STUDYING");
});

test("reunión de equipo a las 10 para trabajadores", () => {
  const w = { ...L.residentes(6).find((x) => x.tipo === "resident"), tipo: "worker", conPuesto: true, workplace: "risk_tower" };
  const a = L.actividadPara(w, 10);
  assert.equal(a.actividad, "MEETING");
  assert.equal(a.destino, "command_center");
});

test("traslado largo al trabajo usa bicicleta SIM; a pie para el resto", () => {
  const w = { ...L.residentes(6).find((x) => x.tipo === "resident"), tipo: "worker", conPuesto: true, workplace: "qa_facility" };
  assert.equal(L.actividadPara(w, 7).transporte, "bici");
  assert.equal(L.actividadPara(w, 7).actividad, "COMMUTING");
  const vecino = L.residentes(0)[0];
  assert.equal(L.actividadPara(vecino, 7).transporte, "caminar");
});

test("aprendices estudian en academia por la mañana y en universidad por la tarde", () => {
  const t = L.residentes(9).find((x) => x.tipo === "trainee");
  assert.equal(L.actividadPara(t, 9).destino, "academy");
  assert.equal(L.actividadPara(t, 15).destino, "university");
});

test("rutina del supervisor: reunión a las 10, Foundry por la tarde, Command Center de noche", () => {
  const sup = L.ROLES_SIMULADOS.find((r) => r.role === "supervisor");
  assert.equal(L.actividadRol(sup, 10).actividad, "MEETING");
  assert.equal(L.actividadRol(sup, 14).destino, "foundry");
  assert.equal(L.actividadRol(sup, 20).destino, "command_center");
});

test("cada rol simulado tiene destino en todas las horas y actividad conocida", () => {
  for (const rol of L.ROLES_SIMULADOS) for (let h = 0; h < 24; h++) {
    const a = L.actividadRol(rol, h);
    assert.ok(a.destino);
    assert.ok(ROL_ACTIVIDADES.includes(a.actividad), `${rol.role} ${h}h ${a.actividad}`);
  }
});

test("graduación simulada sólo con examen aprobado; sin XP suficiente no hay examen", () => {
  const t = L.residentes(9).find((x) => x.tipo === "trainee");
  const pronto = L.progresarTrainee(t, 2);
  assert.equal(pronto.examen, null);
  assert.equal(pronto.stage, "TRAINEE");
  let r = t;
  for (let i = 0; i < 30; i++) r = L.progresarTrainee(r, 1);
  assert.ok(r.examen);
  assert.equal(r.examen.simulated, true);
  assert.equal(r.stage === "GRADUATED_SIM", r.examen.passed === true);
});

test("roles simulados están marcados como simulados", () => {
  for (const r of L.ROLES_SIMULADOS) assert.equal(r.kind, "simulated");
});

test("reloj visual: cicla 0-23 cada 150 s reales, no depende de la hora real del sistema", () => {
  assert.equal(L.horaVisual(0), 0);
  assert.equal(L.horaVisual(75000), 12); // mitad del ciclo = mediodía simulado
  assert.equal(L.horaVisual(150000), L.horaVisual(0)); // un ciclo completo vuelve a empezar
  const horas = new Set();
  for (let ms = 0; ms < L.SEGUNDOS_POR_DIA_VISUAL * 1000; ms += 1000) horas.add(L.horaVisual(ms));
  assert.equal(horas.size, 24);
});
