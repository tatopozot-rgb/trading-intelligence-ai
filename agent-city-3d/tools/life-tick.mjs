// Paso de arranque: aplica la progresión offline de la VIDA SIMULADA. No toca trading ni la BD PAPER.
// Uso: node tools/life-tick.mjs   (lo ejecuta start-agent-city-3d.ps1 antes de abrir la ciudad)
import path from "node:path";
import * as LS from "../lib/life-store.mjs";
import * as LC from "../lib/lifecycle.mjs";
import { residentes } from "../lib/life.mjs";

const DIR = process.env.AGENT_CITY_LIFE || String.raw`C:\Users\tatop\agent-city-sync\state`;
const previo = LS.cargarVida(DIR);
if (!previo.poblacion.length) {
  // Primera vez: se crea la población base (sin demanda, para no inventar trabajo).
  previo.poblacion = residentes(0).map(LC.personaInicial);
  LS.guardarVida(DIR, previo);
}
const r = LS.abrirVida(DIR, Date.now());
console.log(JSON.stringify({ archivo: path.join(DIR, LS.FILE_LIFE), diasSimulados: r.diasSim, motivo: r.motivo, habitantes: r.poblacion.length }));
