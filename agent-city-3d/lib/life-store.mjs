// Persistencia de la vida SIMULADA en su propio archivo (life.json). Nunca toca state de trading ni la BD PAPER.
// Escritura atómica: .tmp y renombrado. La progresión offline se aplica al abrir con aplicarOffline (lifecycle.mjs).
import fs from "node:fs";
import path from "node:path";
import * as LC from "./lifecycle.mjs";

export const FILE_LIFE = "life.json";

export function vidaVacia() {
  return { version: 1, ultimoTs: null, poblacion: [], updated_at: null };
}

export function cargarVida(dir) {
  const ruta = path.join(dir, FILE_LIFE);
  if (!fs.existsSync(ruta)) return vidaVacia();
  return JSON.parse(fs.readFileSync(ruta, "utf8"));
}

export function guardarVida(dir, datos) {
  fs.mkdirSync(dir, { recursive: true });
  const ruta = path.join(dir, FILE_LIFE);
  const tmp = ruta + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify({ ...datos, updated_at: new Date().toISOString() }, null, 2), "utf8");
  fs.renameSync(tmp, ruta);
}

// Abre la vida: aplica la progresión offline desde el último cierre y guarda el nuevo instante.
export function abrirVida(dir, ahoraTs = Date.now()) {
  const previo = cargarVida(dir);
  const { poblacion, diasSim, motivo } = LC.aplicarOffline(previo.poblacion, { ultimoTs: previo.ultimoTs, ahoraTs });
  const nuevo = { version: 1, ultimoTs: ahoraTs, poblacion };
  guardarVida(dir, nuevo);
  return { ...nuevo, diasSim, motivo };
}
