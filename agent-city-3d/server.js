// Servidor local de solo lectura para Agent City 3D.
// Sirve la app, three.js desde node_modules y /api/state con snapshot.json + events.jsonl reales.
// Escucha sólo en 127.0.0.1. No escribe nada, no usa credenciales, no toca trading.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.AGENT_CITY_PORT || 8787);
const STATE_DIR = process.env.AGENT_CITY_STATE || "C:\\Users\\tatop\\agent-city-sync\\state";
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8" };

function leerSnapshot() {
  try { return JSON.parse(fs.readFileSync(path.join(STATE_DIR, "snapshot.json"), "utf8")); } catch { return null; }
}

function leerSociedad() {
  try { return JSON.parse(fs.readFileSync(path.join(STATE_DIR, "society.json"), "utf8")); } catch { return null; }
}

function leerEventos(limite = 200) {
  try {
    const lineas = fs.readFileSync(path.join(STATE_DIR, "events.jsonl"), "utf8").split("\n").filter(Boolean);
    const eventos = [];
    for (const l of lineas.slice(-limite)) {
      try { eventos.push(JSON.parse(l)); } catch { /* línea corrupta: se omite, no se inventa */ }
    }
    return eventos;
  } catch { return []; }
}

function enviarArchivo(res, ruta) {
  fs.readFile(ruta, (err, data) => {
    if (err) { res.writeHead(404); return res.end("no encontrado"); }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(ruta)] || "application/octet-stream", "Cache-Control": "no-cache" });
    res.end(data);
  });
}

// Resuelve sólo dentro de una raíz permitida (evita salir con ..).
function dentroDe(raiz, relativa) {
  const destino = path.normalize(path.join(raiz, relativa));
  return destino.startsWith(raiz) ? destino : null;
}

const server = http.createServer((req, res) => {
  if (req.method !== "GET") { res.writeHead(405); return res.end(); }
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/api/state") {
    const body = { read_at: new Date().toISOString(), state_dir: STATE_DIR, snapshot: leerSnapshot(), society: leerSociedad(), events: leerEventos() };
    res.writeHead(200, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
    return res.end(JSON.stringify(body));
  }
  if (url.pathname.startsWith("/vendor/three/")) {
    const ruta = dentroDe(path.join(here, "node_modules", "three"), url.pathname.slice("/vendor/three/".length));
    return ruta ? enviarArchivo(res, ruta) : (res.writeHead(403), res.end());
  }
  if (url.pathname === "/" || url.pathname === "/index.html") return enviarArchivo(res, path.join(here, "public", "index.html"));
  if (url.pathname.startsWith("/lib/")) {
    const ruta = dentroDe(path.join(here, "lib"), url.pathname.slice("/lib/".length));
    return ruta ? enviarArchivo(res, ruta) : (res.writeHead(403), res.end());
  }
  if (url.pathname.startsWith("/public/") || url.pathname === "/app.js" || url.pathname === "/style.css") {
    const rel = url.pathname.replace(/^\/public\//, "");
    const ruta = dentroDe(path.join(here, "public"), rel);
    return ruta ? enviarArchivo(res, ruta) : (res.writeHead(403), res.end());
  }
  res.writeHead(404); res.end("no encontrado");
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Agent City 3D: http://127.0.0.1:${PORT}  (estado: ${STATE_DIR})`);
});
