// CLI de la sociedad. Cada acción valida con lib/society.mjs y registra evento en el bus.
// Uso:
//   node tools/society.mjs init              (crea society.json si no existe; no toca agentes)
//   node tools/society.mjs show              (resumen)
//   node tools/society.mjs propose <f.json>  (Foundry: valida y crea BOT/TRAINEE)
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import * as St from "../lib/society-store.mjs";

const DIR = process.env.AGENT_CITY_STATE || String.raw`C:\Users\tatop\agent-city-sync\state`;
const [, , orden, arg] = process.argv;

if (orden === "init") {
  if (fs.existsSync(path.join(DIR, St.FILE_SOCIETY))) { console.log("ya existe; no se sobrescribe"); process.exit(0); }
  St.guardarSociedad(DIR, St.sociedadVacia());
  console.log("sociedad inicializada: 3 fundadores, roles previstos inactivos, 0 bots");
} else if (orden === "show") {
  const d = St.leerSociedad(DIR);
  console.log(JSON.stringify({ fundadores: d.founders.map((f) => `${f.name} (${f.alias})`), agentes: d.agents.map((a) => `${a.id}:${a.stage}`),
    previstos: d.planned_roles.map((r) => `${r.name}:${r.status}`) }, null, 2));
} else if (orden === "propose") {
  const p = JSON.parse(fs.readFileSync(arg, "utf8"));
  const nuevo = St.accionCrear(DIR, p);
  console.log(`creado ${nuevo.id} en ${nuevo.stage} (${nuevo.status})`);
} else {
  console.log("uso: init | show | propose <archivo.json>");
  process.exit(1);
}
