import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import * as S from "../lib/life-store.mjs";

const dir = () => fs.mkdtempSync(path.join(os.tmpdir(), "life-"));
const persona = { id: "p1", nombre: "Ana", edad: 20, etapa: "YOUNG_ADULT", hogar: "h1", estudios: null, empleo: null, relaciones: [] };

test("primera apertura: vida vacía, sin progresión, y se guarda el instante", () => {
  const d = dir();
  const r = S.abrirVida(d, Date.parse("2026-10-06T00:00:00Z"));
  assert.equal(r.diasSim, 0);
  assert.equal(S.cargarVida(d).ultimoTs, Date.parse("2026-10-06T00:00:00Z"));
});

test("reabrir tras un cierre progresa la vida de forma agregada y persiste", () => {
  const d = dir();
  const t0 = Date.parse("2026-10-06T00:00:00Z");
  S.guardarVida(d, { version: 1, ultimoTs: t0, poblacion: [persona] });
  const r = S.abrirVida(d, t0 + 48 * 3600000);
  assert.equal(r.diasSim, 48);
  assert.ok(r.poblacion[0].edad > 20);
  assert.ok(S.cargarVida(d).poblacion[0].edad > 20);
});

test("escritura atómica: un .tmp huérfano no corrompe la vida previa", () => {
  const d = dir();
  S.guardarVida(d, { version: 1, ultimoTs: 1, poblacion: [persona] });
  fs.writeFileSync(path.join(d, S.FILE_LIFE + ".tmp"), "{ basura", "utf8");
  assert.equal(S.cargarVida(d).poblacion.length, 1);
});

test("la vida simulada vive en su propio archivo, separado de cualquier state de trading", () => {
  assert.equal(S.FILE_LIFE, "life.json");
  assert.ok(!S.FILE_LIFE.includes("trading") && !S.FILE_LIFE.includes("paper"));
});
