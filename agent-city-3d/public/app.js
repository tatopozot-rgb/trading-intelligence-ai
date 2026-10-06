// Escena three.js de Agent City 3D. Toda decisión de estado vive en lib/model.mjs (probado).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { BUILDINGS, AGENTS, STATE_COLOR, SIM_NOTE, deriveCity } from "/lib/model.mjs";

const REFRESCO_MS = 30000; // conservador: 30 s, sólo lectura local
const ESPACIO = 9;         // separación de la cuadrícula de calles
const CENTRO = new THREE.Vector3(13.5, 0, 13.5);
const COLOR_EDIFICIO = {
  foundry: 0x57534e, university: 0x0f766e, hall: 0xb45309, park: 0x65a30d,
  command_center: 0x1e3a8a, engineering_lab: 0x1d4ed8, local_ops: 0x047857, gpt_ops: 0x6d28d9,
  risk_tower: 0x991b1b, quant_lab: 0x0e7490, qa_facility: 0x4d7c0f, market_intel: 0x0369a1,
  trading_floor: 0x854d0e, knowledge_center: 0x334155, academy: 0xf9a8d4, residential: 0xfde68a,
};
const ALTURA = { foundry: 4.8, university: 6, hall: 5.5, park: 0.6, command_center: 7, risk_tower: 9, trading_floor: 6, knowledge_center: 5, quant_lab: 5.5,
  engineering_lab: 5, gpt_ops: 4.5, local_ops: 4, qa_facility: 4.5, market_intel: 5, academy: 4, residential: 2.5 };
const COLOR_PULSO = { TEST_PASSED: 0x22c55e, TEST_FAILED: 0xef4444, RISK_REJECTED: 0xef4444, KILL_SWITCH_TRIGGERED: 0xdc2626,
  RISK_APPROVED: 0x22c55e, NO_TRADE: 0xfacc15, TRADE_OPENED: 0x38bdf8, TRADE_CLOSED: 0x38bdf8, BACKTEST_FINISHED: 0x67e8f9,
  BACKTEST_STARTED: 0x67e8f9, SYSTEM_RECOVERED: 0x86efac, GRADUATED: 0xfacc15, EXAM_PASSED: 0x22c55e, EXAM_FAILED: 0xef4444 };

const $ = (id) => document.getElementById(id);
const escena = $("escena");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
escena.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b1220);
scene.fog = new THREE.Fog(0x0b1220, 80, 170);
const camara = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
const CAMARA_INICIAL = new THREE.Vector3(CENTRO.x + 34, 30, CENTRO.z + 34);
camara.position.copy(CAMARA_INICIAL);
const controles = new OrbitControls(camara, renderer.domElement);
controles.target.copy(CENTRO);
controles.enableDamping = true;
controles.minDistance = 14;
controles.maxDistance = 110;
controles.maxPolarAngle = Math.PI / 2.05;
controles.update();

scene.add(new THREE.HemisphereLight(0xbfd7ff, 0x1f2937, 0.9));
const sol = new THREE.DirectionalLight(0xffffff, 1.1);
sol.position.set(30, 50, 20);
sol.castShadow = true;
sol.shadow.mapSize.set(2048, 2048);
Object.assign(sol.shadow.camera, { left: -45, right: 45, top: 45, bottom: -45, far: 160 });
scene.add(sol);

// Terreno y calles
const suelo = new THREE.Mesh(new THREE.PlaneGeometry(160, 160), new THREE.MeshStandardMaterial({ color: 0x3f6b3a }));
suelo.rotation.x = -Math.PI / 2;
suelo.receiveShadow = true;
scene.add(suelo);
const materialCalle = new THREE.MeshStandardMaterial({ color: 0x374151 });
for (let k = -1; k <= 4; k++) {
  const x = k * ESPACIO + ESPACIO / 2;
  const calleZ = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.05, 40), materialCalle);
  calleZ.position.set(x, 0.03, CENTRO.z);
  calleZ.receiveShadow = true;
  scene.add(calleZ);
  const calleX = new THREE.Mesh(new THREE.BoxGeometry(40, 0.05, 1.8), materialCalle);
  calleX.position.set(CENTRO.x, 0.03, x);
  calleX.receiveShadow = true;
  scene.add(calleX);
}

// Posición mundo de un edificio (en la cuadrícula) y su punto frontal para los agentes.
const mundoDe = (pos) => new THREE.Vector3(pos[0] * ESPACIO, 0, pos[1] * ESPACIO);
const frente = (id) => {
  const b = BUILDINGS.find((x) => x.id === id);
  return mundoDe(b.pos).add(new THREE.Vector3(0, 0, 3.2));
};

function crearEtiqueta(texto, ancho = 512, alto = 96, color = "#e5e7eb") {
  const c = document.createElement("canvas");
  c.width = ancho; c.height = alto;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(11,18,32,0.78)";
  g.beginPath(); g.roundRect(4, 4, ancho - 8, alto - 8, 16); g.fill();
  g.fillStyle = color; g.font = "bold 40px system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(texto, ancho / 2, alto / 2);
  const tex = new THREE.CanvasTexture(c);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
  sp.scale.set(ancho / 80, alto / 80, 1);
  return sp;
}

// Edificios
const edificios = {};
for (const b of BUILDINGS) {
  const grupo = new THREE.Group();
  const alto = ALTURA[b.id];
  const cuerpo = new THREE.Mesh(new THREE.BoxGeometry(4.2, alto, 4.2),
    new THREE.MeshStandardMaterial({ color: COLOR_EDIFICIO[b.id], roughness: 0.6 }));
  cuerpo.position.y = alto / 2;
  cuerpo.castShadow = true; cuerpo.receiveShadow = true;
  const techo = new THREE.Mesh(new THREE.BoxGeometry(4.6, 0.4, 4.6), new THREE.MeshStandardMaterial({ color: 0x0f172a }));
  techo.position.y = alto + 0.2;
  techo.castShadow = true;
  grupo.add(cuerpo, techo);
  // Ventanas simples (decorativas) en la cara frontal
  const vent = new THREE.MeshStandardMaterial({ color: 0xbef264, emissive: 0x3f6212, emissiveIntensity: 0.6 });
  for (let y = 1; y < alto - 0.5; y += 1.4) {
    const w = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.45, 0.06), vent);
    w.position.set(0, y, 2.13);
    grupo.add(w);
  }
  grupo.position.copy(mundoDe(b.pos));
  const etiqueta = crearEtiqueta(b.label, 640, 96);
  etiqueta.position.set(0, alto + 1.8, 0);
  grupo.add(etiqueta);
  const anillos = new THREE.Group();
  grupo.add(anillos);
  grupo.userData = { kind: "building", id: b.id };
  cuerpo.userData = grupo.userData;
  techo.userData = grupo.userData;
  if (b.district === "simulation") {
    const nota = crearEtiqueta(SIM_NOTE, 1000, 72, "#fbcfe8");
    nota.position.set(0, alto + 3.2, 0);
    nota.scale.multiplyScalar(0.8);
    grupo.add(nota);
  }
  scene.add(grupo);
  edificios[b.id] = { grupo, cuerpo, anillos, anillosActivos: [] };
}

// Árboles decorativos del distrito de simulación (no representan agentes ni actividad).
for (const [x, z] of [[24.5, 27], [28, 22], [26, 30], [21, 24]]) {
  const copa = new THREE.Mesh(new THREE.ConeGeometry(1.3, 3, 8), new THREE.MeshStandardMaterial({ color: 0x15803d }));
  copa.position.set(x, 1.6, z);
  copa.castShadow = true;
  scene.add(copa);
}

// Agentes low-poly: se crean por clave cuando aparecen en el modelo (fundadores o sociedad).
const agentes = {};
const COLOR_SOCIEDAD = 0x64748b;
function crearAvatar(key, nombre, color) {
  const grupo = new THREE.Group();
  const cuerpo = new THREE.Mesh(new THREE.CapsuleGeometry(0.42, 0.7, 4, 8),
    new THREE.MeshStandardMaterial({ color, roughness: 0.5 }));
  cuerpo.position.y = 0.95; cuerpo.castShadow = true;
  const cabeza = new THREE.Mesh(new THREE.SphereGeometry(0.3, 10, 8), new THREE.MeshStandardMaterial({ color: 0xfcd9b6 }));
  cabeza.position.y = 1.9;
  const aro = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.7, 24), new THREE.MeshBasicMaterial({ color: 0x6b7280, side: THREE.DoubleSide }));
  aro.rotation.x = -Math.PI / 2; aro.position.y = 0.05;
  const etiqueta = crearEtiqueta(nombre, 560, 80, "#f8fafc");
  etiqueta.position.y = 2.7;
  grupo.add(cuerpo, cabeza, aro, etiqueta);
  grupo.userData = { kind: "agent", key };
  cuerpo.userData = grupo.userData; cabeza.userData = grupo.userData; aro.userData = grupo.userData;
  scene.add(grupo);
  agentes[key] = { grupo, aro, cuerpo, etiqueta, ruta: [], origen: null, t: 0, destino: null, desfase: Math.random() * 6 };
  return agentes[key];
}
// Sincroniza avatares con el modelo: crea los nuevos, oculta los que ya no aparecen.
function sincronizarAvatares(city) {
  const presentes = new Set(city.agents.map((a) => a.key));
  for (const a of city.agents) {
    if (!agentes[a.key]) {
      const f = AGENTS.find((x) => x.key === a.key);
      crearAvatar(a.key, a.name, f ? f.color : COLOR_SOCIEDAD);
    }
    agentes[a.key].grupo.visible = true;
  }
  for (const key in agentes) if (!presentes.has(key)) agentes[key].grupo.visible = false;
}

// Ruta por calles: del frente del origen, a la altura de la calle del destino, luego al frente del destino.
function rutaHasta(origen, id) {
  const destino = frente(id);
  const desde = origen.clone();
  const mitad = new THREE.Vector3(destino.x, 0, desde.z);
  return [desde, mitad, destino];
}

// Recalcula destinos cuando cambia el modelo. Sólo mueve si el destino cambió.
function asignarDestinos(city) {
  sincronizarAvatares(city);
  const porEdificio = {};
  for (const a of city.agents) {
    (porEdificio[a.target] ||= []).push(a.key);
  }
  for (const a of city.agents) {
    const ag = agentes[a.key];
    const slot = porEdificio[a.target].indexOf(a.key);
    const lugar = frente(a.target).add(new THREE.Vector3((slot - (porEdificio[a.target].length - 1) / 2) * 1.6, 0, 0.6));
    ag.colorEstado = STATE_COLOR[a.state] ?? 0x6b7280;
    ag.grupo.userData.kind = "agent";
    ag.aro.material.color.setHex(ag.colorEstado);
    ag.estado = a.state;
    if (!ag.destino || !ag.destino.equals(lugar)) {
      const origen = ag.grupo.position.clone();
      const base = origen.lengthSq() === 0 ? frente(a.target) : origen;
      ag.ruta = rutaHasta(base, a.target).slice(0, 2).concat([lugar]);
      ag.origen = base;
      ag.destino = lugar;
      ag.t = 0;
    }
    const nueva = crearEtiqueta(`${a.name} · ${a.state}`, 560, 80, "#f8fafc");
    if (a.kind === "society") ag.etiqueta.userData.sociedad = true;
    ag.etiqueta.material.map.dispose();
    ag.etiqueta.material.map = nueva.material.map;
    ag.etiqueta.material.needsUpdate = true;
    nueva.material.dispose();
  }
}

// Animación de caminar: interpola tramos de la ruta a velocidad constante.
const VELOCIDAD = 4.5;
function avanzarAgentes(dt) {
  for (const key in agentes) {
    const ag = agentes[key];
    if (ag.ruta.length < 2) {
      ag.grupo.position.y = Math.sin(performance.now() / 700 + ag.desfase) * 0.05; // ocioso: respiración suave
      continue;
    }
    let restante = VELOCIDAD * dt;
    while (restante > 0 && ag.ruta.length >= 2) {
      const a = ag.ruta[0], b = ag.ruta[1];
      const tramo = a.distanceTo(b);
      const usado = Math.min(restante, tramo - ag.t);
      ag.t += usado;
      restante -= usado;
      const f = tramo === 0 ? 1 : ag.t / tramo;
      ag.grupo.position.lerpVectors(a, b, f);
      ag.grupo.position.y = Math.abs(Math.sin(performance.now() / 120)) * 0.12; // paso
      if (ag.t >= tramo - 1e-6) { ag.ruta.shift(); ag.t = 0; }
    }
    if (ag.ruta.length < 2) ag.grupo.position.y = 0;
    else ag.grupo.lookAt(ag.ruta[1]);
  }
}

// Pulsos de eventos sobre edificios: anillos que se expanden y se desvanecen.
const DURACION_PULSO_S = 25;
const geometriaAnillo = new THREE.RingGeometry(2.6, 3.0, 40);
// Se llama al refrescar el modelo: crea un anillo por evento reciente (no por fotograma).
function actualizarPulsos(city, ahoraMs) {
  for (const b of city.buildings) {
    const e = edificios[b.id];
    if (!e) continue;
    e.anillos.clear();
    for (const p of b.pulses) {
      const nacimiento = Date.parse(p.at);
      if (!(ahoraMs - nacimiento >= 0 && ahoraMs - nacimiento < DURACION_PULSO_S * 1000)) continue;
      const anillo = new THREE.Mesh(geometriaAnillo,
        new THREE.MeshBasicMaterial({ color: COLOR_PULSO[p.type] ?? 0xffffff, transparent: true, opacity: 1, side: THREE.DoubleSide }));
      anillo.rotation.x = -Math.PI / 2;
      anillo.position.y = 0.12;
      anillo.userData.nacimiento = nacimiento;
      e.anillos.add(anillo);
    }
  }
}
// Animación por fotograma: sólo escala y opacidad de anillos existentes.
function animarPulsos(ahoraMs) {
  for (const id in edificios) {
    for (const anillo of [...edificios[id].anillos.children]) {
      const edad = (ahoraMs - anillo.userData.nacimiento) / 1000;
      if (edad >= DURACION_PULSO_S) { edificios[id].anillos.remove(anillo); anillo.material.dispose(); continue; }
      anillo.scale.setScalar(1 + edad / 6);
      anillo.material.opacity = 1 - edad / DURACION_PULSO_S;
    }
  }
}

// Selección por clic
const raycaster = new THREE.Raycaster();
const puntero = new THREE.Vector2();
let seleccion = null;
renderer.domElement.addEventListener("click", (ev) => {
  const r = renderer.domElement.getBoundingClientRect();
  puntero.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(puntero, camara);
  const objetos = [];
  scene.traverse((o) => { if (o.userData && o.userData.kind) objetos.push(o); });
  const hit = raycaster.intersectObjects(objetos, true)[0];
  let objeto = hit ? hit.object : null;
  while (objeto && !(objeto.userData && objeto.userData.kind)) objeto = objeto.parent;
  if (objeto) { seleccion = objeto.userData; mostrarSeleccion(); }
});

let ultimo = null;
function mostrarSeleccion() {
  if (!ultimo) return;
  if (!seleccion) return;
  if (seleccion.kind === "building") {
    const b = BUILDINGS.find((x) => x.id === seleccion.id);
    const bloque = ultimo.buildings.find((x) => x.id === seleccion.id);
    const pulsos = (bloque?.pulses || []).map((p) => `<li>${p.type} — ${p.subject || ""} ${p.detail || ""}</li>`).join("") || "<li class='muted'>sin eventos recientes</li>";
    $("p-titulo").textContent = b.label;
    $("p-cuerpo").innerHTML = `<dl><dt>Distrito</dt><dd>${b.district === "simulation" ? "Life Simulation — " + SIM_NOTE : "Operational Reality"}</dd></dl>
      <h3>Eventos recientes aquí</h3><ul>${pulsos}</ul>`;
  } else {
    const a = ultimo.agents.find((x) => x.key === seleccion.key);
    $("p-titulo").textContent = `${a.name} (${a.alias})`;
    $("p-cuerpo").innerHTML = `<dl>
      <dt>Estado</dt><dd>${a.state}</dd>
      <dt>Motivo</dt><dd>${a.reason}</dd>
      <dt>Tarea actual</dt><dd>${a.currentTask || "NOT_SYNCED"}</dd>
      <dt>Último commit</dt><dd>${a.heartbeat || "NOT_SYNCED (no es heartbeat en vivo)"}</dd>
      <dt>Último resultado</dt><dd>${a.lastResult || "NOT_SYNCED"}</dd>
      <dt>Último evento</dt><dd>${a.lastEvent ? a.lastEvent.type + " · " + a.lastEvent.at : "ninguno en 2 h"}</dd>
    </dl>`;
  }
}

function pintarFeed(city) {
  $("feed").innerHTML = city.feed.map((e) => `<li><b>${e.type}</b> <span class="muted">${e.observed_at || e.ts || ""}</span><br>${e.subject || ""} ${e.detail || ""}</li>`).join("") || "<li class='muted'>sin eventos</li>";
}

function pintarBanners(city) {
  $("banners").innerHTML = city.banners.map((b) => `<div class="b">${b}</div>`).join("");
  $("modo").textContent = `${city.mode} MODE`;
  $("sync").textContent = city.syncOk ? `sync OK · ${city.snapshotAt}` : "sync no verificada";
}

let fallo = null;
async function refrescar() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const datos = await r.json();
    ultimo = deriveCity({ snapshot: datos.snapshot, society: datos.society, events: datos.events, now: new Date() });
    fallo = null;
    asignarDestinos(ultimo);
    actualizarPulsos(ultimo, Date.now());
    pintarFeed(ultimo);
    pintarBanners(ultimo);
    $("planned").innerHTML = (ultimo.planned || []).map((r) => `<li>${r.name} — ${r.state}</li>`).join("") || "<li>ninguno</li>";
    $("refresco").textContent = `actualizado ${new Date().toLocaleTimeString()}`;
    mostrarSeleccion();
  } catch (e) {
    fallo = e.message;
    $("sync").textContent = "servidor no responde";
    $("banners").innerHTML = `<div class="b">SIN DATOS: ${fallo}. Se conserva la última vista.</div>`;
  }
}

$("reset").addEventListener("click", () => {
  camara.position.copy(CAMARA_INICIAL);
  controles.target.copy(CENTRO);
  controles.update();
});

function redimensionar() {
  const r = escena.getBoundingClientRect();
  renderer.setSize(r.width, r.height, false);
  camara.aspect = r.width / Math.max(1, r.height);
  camara.updateProjectionMatrix();
}
window.addEventListener("resize", redimensionar);
redimensionar();

let anterior = performance.now();
renderer.setAnimationLoop(() => {
  const ahora = performance.now();
  const dt = Math.min(0.1, (ahora - anterior) / 1000);
  anterior = ahora;
  avanzarAgentes(dt);
  animarPulsos(Date.now());
  controles.update();
  renderer.render(scene, camara);
});

refrescar();
setInterval(refrescar, REFRESCO_MS);
