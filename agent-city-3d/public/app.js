// Escena three.js de Agent City 3D. Toda decisión de estado vive en lib/model.mjs y lib/life.mjs (probados).
// Regla visual: el badge REAL / SIMULADO se muestra siempre; WORKING sólo viene de estado real.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { BUILDINGS, AGENTS, STATE_COLOR, SIM_NOTE, deriveCity, CATEGORIAS } from "/lib/model.mjs";

const REFRESCO_MS = 30000;
const ESPACIO = 9;
const CENTRO = new THREE.Vector3(13.5, 0, 13.5);
const COLOR_EDIFICIO = {
  foundry: 0x57534e, university: 0x0f766e, hall: 0xb45309, park: 0x65a30d,
  house_a: 0xfde68a, house_b: 0xfca5a5, house_c: 0xbfdbfe, house_d: 0xd9f99d,
  command_center: 0x1e3a8a, engineering_lab: 0x1d4ed8, local_ops: 0x047857, gpt_ops: 0x6d28d9,
  risk_tower: 0x991b1b, quant_lab: 0x0e7490, qa_facility: 0x4d7c0f, market_intel: 0x0369a1,
  trading_floor: 0x854d0e, knowledge_center: 0x334155, academy: 0xf9a8d4, residential: 0xfef3c7,
};
const ALTURA = { house_a: 3.2, house_b: 3.2, house_c: 3.2, house_d: 3.2, foundry: 4.8, university: 6, hall: 5.5,
  park: 0.4, command_center: 7, risk_tower: 9, trading_floor: 6, knowledge_center: 5, quant_lab: 5.5,
  engineering_lab: 5, gpt_ops: 4.5, local_ops: 4, qa_facility: 4.5, market_intel: 5, academy: 4, residential: 2.5 };
const TIENE_INTERIOR = new Set(["house_a", "house_b", "house_c", "house_d", "academy", "university", "quant_lab", "qa_facility",
  "engineering_lab", "risk_tower", "command_center", "gpt_ops", "local_ops", "trading_floor", "knowledge_center", "foundry", "hall"]);
const COLOR_PULSO = { TEST_PASSED: 0x22c55e, TEST_FAILED: 0xef4444, RISK_REJECTED: 0xef4444, KILL_SWITCH_TRIGGERED: 0xdc2626,
  RISK_APPROVED: 0x22c55e, NO_TRADE: 0xfacc15, TRADE_OPENED: 0x38bdf8, TRADE_CLOSED: 0x38bdf8, BACKTEST_FINISHED: 0x67e8f9,
  BACKTEST_STARTED: 0x67e8f9, SYSTEM_RECOVERED: 0x86efac, GRADUATED: 0xfacc15, EXAM_PASSED: 0x22c55e, EXAM_FAILED: 0xef4444 };
const DURACION_PULSO_S = 25;
const VELOCIDAD = 4.5;
const COLOR_SIM = 0xcbd5e1;
const DENTRO_SIM = ["SIM_SLEEPING", "SIM_STUDYING", "SIM_WORKING", "SIM_ON_DUTY"];

const $ = (id) => document.getElementById(id);
const escapar = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const NOMBRE_EDIFICIO = Object.fromEntries(BUILDINGS.map((b) => [b.id, b.label]));
const EDIFICIO_DE = Object.fromEntries(BUILDINGS.map((b) => [b.id, b]));

// ---------- escena base
const escena = $("escena");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
escena.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b1220);
scene.fog = new THREE.Fog(0x0b1220, 90, 180);
const camara = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
const CAMARA_INICIAL = new THREE.Vector3(CENTRO.x + 30, 27, CENTRO.z + 30);
camara.position.copy(CAMARA_INICIAL);
const controles = new OrbitControls(camara, renderer.domElement);
controles.target.copy(CENTRO);
controles.enableDamping = true;
controles.minDistance = 12;
controles.maxDistance = 110;
controles.maxPolarAngle = Math.PI / 2.05;
controles.update();

scene.add(new THREE.HemisphereLight(0xbfd7ff, 0x1f2937, 0.95));
const sol = new THREE.DirectionalLight(0xffffff, 1.1);
sol.position.set(30, 50, 20);
sol.castShadow = true;
sol.shadow.mapSize.set(2048, 2048);
Object.assign(sol.shadow.camera, { left: -50, right: 50, top: 50, bottom: -50, far: 160 });
scene.add(sol);

const suelo = new THREE.Mesh(new THREE.PlaneGeometry(170, 170), new THREE.MeshStandardMaterial({ color: 0x3f6b3a }));
suelo.rotation.x = -Math.PI / 2;
suelo.receiveShadow = true;
scene.add(suelo);
const materialCalle = new THREE.MeshStandardMaterial({ color: 0x374151 });
const materialAcera = new THREE.MeshStandardMaterial({ color: 0x9ca3af });
for (let k = -1; k <= 4; k++) {
  const x = k * ESPACIO + ESPACIO / 2;
  for (const [ancho, largo, px, pz] of [[2.2, 44, x, CENTRO.z], [44, 2.2, CENTRO.x, x]]) {
    const acera = new THREE.Mesh(new THREE.BoxGeometry(ancho + 0.6, 0.04, largo), materialAcera);
    acera.position.set(px, 0.02, pz);
    scene.add(acera);
    const calle = new THREE.Mesh(new THREE.BoxGeometry(ancho, 0.05, largo), materialCalle);
    calle.position.set(px, 0.035, pz);
    calle.receiveShadow = true;
    scene.add(calle);
  }
}

const mundoDe = (b) => (b.world ? new THREE.Vector3(b.world[0], 0, b.world[1]) : new THREE.Vector3(b.pos[0] * ESPACIO, 0, b.pos[1] * ESPACIO));
const frente = (id) => {
  const b = EDIFICIO_DE[id] || EDIFICIO_DE.residential;
  return mundoDe(b).add(new THREE.Vector3(0, 0, 3.2));
};
const dentroDe = (id) => {
  const b = EDIFICIO_DE[id];
  return b ? mundoDe(b).add(new THREE.Vector3(0, 0.6, 0)) : frente(id);
};

function crearEtiqueta(texto, ancho = 512, alto = 96, color = "#e5e7eb", tamano = 40) {
  const c = document.createElement("canvas");
  c.width = ancho; c.height = alto;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(11,18,32,0.82)";
  g.beginPath(); g.roundRect(4, 4, ancho - 8, alto - 8, 16); g.fill();
  g.fillStyle = color; g.font = `bold ${tamano}px system-ui, sans-serif`; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(texto, ancho / 2, alto / 2);
  const tex = new THREE.CanvasTexture(c);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
  sp.scale.set(ancho / 80, alto / 80, 1);
  return sp;
}

// ---------- interiores (visibles por transparencia de las fachadas)
function interiorDe(id) {
  const g = new THREE.Group();
  const piso = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.05, 3.6), new THREE.MeshStandardMaterial({ color: 0xf1f5f9 }));
  piso.position.y = 0.06;
  g.add(piso);
  const madera = new THREE.MeshStandardMaterial({ color: 0x78350f });
  const pantalla = new THREE.MeshStandardMaterial({ color: 0x1e293b, emissive: 0x0ea5e9, emissiveIntensity: 0.5 });
  if (id.startsWith("house")) {
    const cama = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.4, 1.0), new THREE.MeshStandardMaterial({ color: 0x60a5fa }));
    cama.position.set(-0.9, 0.3, -0.9);
    const sofa = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.4, 0.6), new THREE.MeshStandardMaterial({ color: 0xf97316 }));
    sofa.position.set(0.8, 0.3, 0.9);
    g.add(cama, sofa);
  } else {
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      const m = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.12, 0.6), madera);
      m.position.set(x * 0.9, 0.7, z * 0.9);
      const p = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.4, 0.05), pantalla);
      p.position.set(x * 0.9, 1.0, z * 0.9 - 0.25);
      g.add(m, p);
    }
  }
  return g;
}

// ---------- edificios
const edificios = {};
for (const b of BUILDINGS) {
  const grupo = new THREE.Group();
  const alto = ALTURA[b.id] ?? 3;
  const color = COLOR_EDIFICIO[b.id] ?? 0x475569;
  const material = new THREE.MeshStandardMaterial({ color, roughness: 0.6, transparent: true, opacity: 0.62 });
  const cuerpo = new THREE.Mesh(new THREE.BoxGeometry(4.2, alto, 4.2), material);
  cuerpo.position.y = alto / 2;
  cuerpo.castShadow = true;
  const techo = new THREE.Mesh(new THREE.BoxGeometry(4.6, 0.35, 4.6), new THREE.MeshStandardMaterial({ color: 0x0f172a }));
  techo.position.y = alto + 0.18;
  techo.castShadow = true;
  grupo.add(cuerpo, techo);
  const interior = TIENE_INTERIOR.has(b.id) ? interiorDe(b.id) : null;
  if (interior) grupo.add(interior);
  const ventana = new THREE.MeshStandardMaterial({ color: 0xbef264, emissive: 0x3f6212, emissiveIntensity: 0.5, transparent: true, opacity: 0.8 });
  for (let y = 1; y < alto - 0.5; y += 1.4) {
    const w = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.42, 0.06), ventana);
    w.position.set(0, y, 2.13);
    grupo.add(w);
  }
  grupo.position.copy(mundoDe(b));
  const etiqueta = crearEtiqueta(b.label, 600, 80, "#f8fafc", 36);
  etiqueta.position.set(0, alto + 1.4, 0);
  grupo.add(etiqueta);
  const anillos = new THREE.Group();
  grupo.add(anillos);
  if (b.id === "residential") { // una sola nota de simulación en el barrio, no en cada casa
    const nota = crearEtiqueta(SIM_NOTE, 900, 60, "#fde68a", 30);
    nota.position.set(0, alto + 2.8, 0);
    nota.scale.multiplyScalar(0.7);
    grupo.add(nota);
  }
  grupo.userData = { kind: "building", id: b.id };
  cuerpo.userData = grupo.userData;
  techo.userData = grupo.userData;
  scene.add(grupo);
  edificios[b.id] = { grupo, cuerpo, material, anillos, interior };
}

for (const [x, z] of [[24.5, 27], [28, 22], [26, 30], [21, 24], [31, 30]]) {
  const copa = new THREE.Mesh(new THREE.ConeGeometry(1.2, 3, 8), new THREE.MeshStandardMaterial({ color: 0x15803d }));
  copa.position.set(x, 1.6, z);
  copa.castShadow = true;
  scene.add(copa);
}

// ---------- avatares humanoides
const agentes = {};
const PIEL = [0xfcd9b6, 0xe0ac7e, 0xc68642, 0x8d5524];
const PELO = [0x1f2937, 0x78350f, 0xa16207, 0x111827];
function crearAvatar(key, nombre, color, esSimulado) {
  const grupo = new THREE.Group();
  const ropa = new THREE.MeshStandardMaterial({ color, roughness: 0.55, transparent: esSimulado, opacity: esSimulado ? 0.85 : 1 });
  const piel = new THREE.MeshStandardMaterial({ color: PIEL[key.length % PIEL.length] });
  const pelo = new THREE.MeshStandardMaterial({ color: PELO[key.charCodeAt(0) % PELO.length] });
  const pantalon = new THREE.MeshStandardMaterial({ color: 0x1e293b });
  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.7, 0.36), ropa);
  torso.position.y = 1.35;
  torso.castShadow = true;
  const cabeza = new THREE.Mesh(new THREE.SphereGeometry(0.27, 12, 10), piel);
  cabeza.position.y = 2.0;
  const cabello = new THREE.Mesh(new THREE.SphereGeometry(0.29, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2), pelo);
  cabello.position.y = 2.05;
  const brazoI = new THREE.Group(); brazoI.position.set(-0.42, 1.6, 0);
  const brazoD = new THREE.Group(); brazoD.position.set(0.42, 1.6, 0);
  const malI = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.62, 0.18), ropa); malI.position.y = -0.31;
  const malD = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.62, 0.18), ropa); malD.position.y = -0.31;
  brazoI.add(malI); brazoD.add(malD);
  const piernaI = new THREE.Group(); piernaI.position.set(-0.16, 1.0, 0);
  const piernaD = new THREE.Group(); piernaD.position.set(0.16, 1.0, 0);
  const subI = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.85, 0.22), pantalon); subI.position.y = -0.42;
  const subD = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.85, 0.22), pantalon); subD.position.y = -0.42;
  piernaI.add(subI); piernaD.add(subD);
  const aro = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.7, 24), new THREE.MeshBasicMaterial({ color: 0x6b7280, side: THREE.DoubleSide }));
  aro.rotation.x = -Math.PI / 2; aro.position.y = 0.05;
  const seleccionAro = new THREE.Mesh(new THREE.RingGeometry(0.95, 1.12, 32), new THREE.MeshBasicMaterial({ color: 0xfacc15, side: THREE.DoubleSide }));
  seleccionAro.rotation.x = -Math.PI / 2; seleccionAro.position.y = 0.07; seleccionAro.visible = false;
  const etiqueta = crearEtiqueta(esSimulado ? `${nombre} · SIM` : nombre, 520, 74, esSimulado ? "#fde68a" : "#f8fafc", 34);
  etiqueta.position.y = 2.75;
  grupo.add(torso, cabeza, cabello, brazoI, brazoD, piernaI, piernaD, aro, seleccionAro, etiqueta);
  grupo.userData = { kind: "agent", key };
  for (const m of [torso, cabeza, cabello, subI, subD, malI, malD]) m.userData = grupo.userData;
  scene.add(grupo);
  agentes[key] = { grupo, aro, seleccionAro, etiqueta, piernaI, piernaD, brazoI, brazoD,
    ruta: [], t: 0, destino: null, desfase: Math.random() * 6, esSimulado };
  return agentes[key];
}

function sincronizarAvatares(city) {
  const presentes = new Set(city.agents.map((a) => a.key));
  for (const a of city.agents) {
    if (!agentes[a.key]) {
      const f = AGENTS.find((x) => x.key === a.key);
      crearAvatar(a.key, a.name, f ? f.color : (a.kind === "simulated" ? COLOR_SIM : 0x64748b), a.kind === "simulated");
    }
    agentes[a.key].grupo.visible = true;
  }
  for (const key in agentes) if (!presentes.has(key)) agentes[key].grupo.visible = false;
}

// Los simulados con actividad dentro de un edificio entran (visibles por transparencia); el resto espera en la puerta.
function asignarDestinos(city) {
  sincronizarAvatares(city);
  const porEdificio = {};
  for (const a of city.agents) (porEdificio[a.target] ||= []).push(a.key);
  for (const a of city.agents) {
    const ag = agentes[a.key];
    if (!ag) continue;
    const grupo = porEdificio[a.target];
    const slot = grupo.indexOf(a.key);
    const adentro = a.kind === "simulated" && DENTRO_SIM.includes(a.state);
    const base = adentro ? dentroDe(a.target) : frente(a.target);
    const lugar = base.clone().add(new THREE.Vector3((slot - (grupo.length - 1) / 2) * 1.5, 0, adentro ? 0 : 0.6));
    ag.colorEstado = STATE_COLOR[a.state] ?? 0x6b7280;
    ag.etiqueta.visible = !a.kind || a.kind !== "simulated" || ag.seleccionAro.visible; // simulados: etiqueta sólo si están seleccionados
    ag.aro.material.color.setHex(ag.colorEstado);
    if (ag.grupo.position.lengthSq() === 0) {
      const nace = a.kind === "simulated" && a.home ? frente(a.home) : frente(a.target);
      ag.grupo.position.copy(nace);
    }
    if (!ag.destino || !ag.destino.equals(lugar)) {
      const desde = ag.grupo.position.clone();
      ag.ruta = [desde, new THREE.Vector3(lugar.x, 0, desde.z), lugar];
      ag.t = 0;
      ag.destino = lugar;
    }
    const nueva = crearEtiqueta(`${a.name} · ${a.state}`, 560, 74, a.kind === "simulated" ? "#fde68a" : "#f8fafc", 32);
    ag.etiqueta.material.map.dispose();
    ag.etiqueta.material.map = nueva.material.map;
    ag.etiqueta.material.needsUpdate = true;
    nueva.material.dispose();
  }
}

// Marcha (piernas y brazos alternos) al moverse; respiración suave al estar quieto.
function avanzarAgentes(dt, tiempo) {
  for (const key in agentes) {
    const ag = agentes[key];
    if (!ag.grupo.visible) continue;
    if (ag.ruta.length < 2) {
      ag.grupo.position.y = 0;
      const r = Math.sin(tiempo / 700 + ag.desfase) * 0.05;
      ag.piernaI.rotation.x = 0; ag.piernaD.rotation.x = 0;
      ag.brazoI.rotation.x = r; ag.brazoD.rotation.x = -r;
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
      if (ag.t >= tramo - 1e-6) { ag.ruta.shift(); ag.t = 0; }
    }
    if (ag.ruta.length >= 2) {
      ag.grupo.lookAt(ag.ruta[1]);
      const paso = Math.sin(tiempo / 110 + ag.desfase) * 0.7;
      ag.piernaI.rotation.x = paso; ag.piernaD.rotation.x = -paso;
      ag.brazoI.rotation.x = -paso * 0.8; ag.brazoD.rotation.x = paso * 0.8;
      ag.grupo.position.y = Math.abs(Math.sin(tiempo / 110 + ag.desfase)) * 0.06;
    } else {
      ag.grupo.position.y = 0;
      ag.piernaI.rotation.x = 0; ag.piernaD.rotation.x = 0;
      ag.brazoI.rotation.x = 0; ag.brazoD.rotation.x = 0;
    }
  }
}

// ---------- pulsos de eventos reales
const geometriaAnillo = new THREE.RingGeometry(2.6, 3.0, 40);
function actualizarPulsos(city, ahoraMs) {
  for (const b of city.buildings) {
    const e = edificios[b.id];
    if (!e) continue;
    e.anillos.clear();
    for (const p of b.pulses) {
      const nacimiento = Date.parse(p.at);
      if (!(ahoraMs - nacimiento >= 0 && ahoraMs - nacimiento < DURACION_PULSO_S * 1000)) continue;
      const anillo = new THREE.Mesh(geometriaAnillo, new THREE.MeshBasicMaterial({ color: COLOR_PULSO[p.type] ?? 0xffffff, transparent: true, opacity: 1, side: THREE.DoubleSide }));
      anillo.rotation.x = -Math.PI / 2;
      anillo.position.y = 0.12;
      anillo.userData.nacimiento = nacimiento;
      e.anillos.add(anillo);
    }
  }
}
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

// ---------- selección y cortes
let seleccion = null; // { kind: "building", id } | { kind: "agent", key }
let ultimo = null;
function resaltarSeleccion() {
  for (const id in edificios) {
    const sel = seleccion && seleccion.kind === "building" && seleccion.id === id;
    edificios[id].material.emissive = new THREE.Color(sel ? 0x334155 : 0x000000);
    edificios[id].material.opacity = sel ? 0.8 : 0.62;
  }
  for (const key in agentes) {
    const sel = Boolean(seleccion && seleccion.kind === "agent" && seleccion.key === key);
    agentes[key].seleccionAro.visible = sel;
    if (agentes[key].esSimulado) agentes[key].etiqueta.visible = sel;
  }
}
let interioresVisibles = true;
function aplicarInteriores() {
  for (const id in edificios) if (edificios[id].interior) edificios[id].interior.visible = interioresVisibles;
}
$("cortes").addEventListener("click", () => {
  interioresVisibles = !interioresVisibles;
  $("cortes").textContent = `Interiores: ${interioresVisibles ? "on" : "off"}`;
  aplicarInteriores();
});

const raycaster = new THREE.Raycaster();
const puntero = new THREE.Vector2();
renderer.domElement.addEventListener("click", (ev) => {
  const r = renderer.domElement.getBoundingClientRect();
  puntero.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(puntero, camara);
  const objetos = [];
  scene.traverse((o) => { if (o.visible && o.userData && o.userData.kind) objetos.push(o); });
  const hit = raycaster.intersectObjects(objetos, true)[0];
  let objeto = hit ? hit.object : null;
  while (objeto && !(objeto.userData && objeto.userData.kind)) objeto = objeto.parent;
  if (!objeto) return;
  seleccion = objeto.userData.kind === "building"
    ? { kind: "building", id: objeto.userData.id }
    : { kind: "agent", key: objeto.userData.key };
  pestana = seleccion.kind;
  aplicarPestana();
  resaltarSeleccion();
  pintarSeleccion();
});
$("p-cerrar").addEventListener("click", () => {
  seleccion = null;
  seguir = null;
  pestana = "city";
  aplicarPestana();
  resaltarSeleccion();
  pintarSeleccion();
});

// ---------- paneles
const fila = (k, v) => `<div class="fila"><span>${escapar(k)}</span><span>${escapar(v)}</span></div>`;

// Pestañas: qué bloques se ven en cada una. "all" = la tarjeta de selección, siempre visible.
let pestana = "city";
const VISIBLES = {
  city: ["all", "real", "sim", "roles", "feed", "legend"],
  agent: ["all"], building: ["all"],
  operations: ["all", "real", "roles", "feed"],
  simulation: ["all", "sim"],
};
function aplicarPestana() {
  for (const el of document.querySelectorAll("[data-tab]")) el.hidden = !(VISIBLES[pestana] || []).includes(el.dataset.tab);
  for (const b of document.querySelectorAll(".tab")) b.classList.toggle("on", b.dataset.tab === pestana);
}
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
  pestana = b.dataset.tab;
  if (pestana === "city") { seleccion = null; seguir = null; resaltarSeleccion(); }
  aplicarPestana();
  pintarSeleccion();
}));

// Seguimiento de agente y enfoque de edificio (acciones del panel y doble clic).
let seguir = null; // clave del agente que la cámara sigue
function enfocarEdificio(id) {
  const b = EDIFICIO_DE[id];
  if (!b) return;
  const centro = mundoDe(b);
  controles.target.copy(centro);
  camara.position.copy(centro).add(new THREE.Vector3(12, 12, 12));
  controles.update();
}
$("p-cuerpo").addEventListener("click", (ev) => {
  const accion = ev.target?.dataset?.accion;
  if (!accion || !seleccion) return;
  if (accion === "seguir" && seleccion.kind === "agent") seguir = seleccion.key;
  if (accion === "dejar") seguir = null;
  if (accion === "enfocar" && seleccion.kind === "building") enfocarEdificio(seleccion.id);
  pintarSeleccion();
});
renderer.domElement.addEventListener("dblclick", () => {
  if (seleccion && seleccion.kind === "building") enfocarEdificio(seleccion.id);
});

function pintarSeleccion() {
  if (!ultimo) return;
  if (!seleccion) return pintarResumen();
  if (seleccion.kind === "building") {
    const b = EDIFICIO_DE[seleccion.id];
    if (!b) return pintarResumen();
    const bloque = ultimo.buildings.find((x) => x.id === seleccion.id);
    const esSim = b.district === "simulation";
    const dentro = ultimo.agents.filter((a) => a.target === seleccion.id);
    const reales = dentro.filter((a) => a.kind !== "simulated");
    const sims = dentro.filter((a) => a.kind === "simulated");
    const pulsos = (bloque?.pulses || []).map((p) => `<li><b>${escapar(p.type)}</b> ${escapar(p.subject)} ${escapar(p.detail)}</li>`).join("")
      || "<li class='muted'>sin eventos reales recientes</li>";
    $("p-titulo").textContent = b.label;
    $("p-badge").className = `badge ${esSim ? "sim" : "real"}`;
    $("p-badge").textContent = esSim ? "SIMULACIÓN" : "REAL";
    $("p-cuerpo").innerHTML =
      `${fila("Distrito", esSim ? "Life Simulation" : "Operational Reality")}
       <button class="secundario" data-accion="enfocar" type="button" style="margin:6px 0">Enfocar edificio</button>
       ${fila("Agentes reales aquí", reales.length ? reales.map((a) => a.name).join(", ") : "ninguno")}
       ${fila("Simulados aquí", String(sims.length))}
       ${esSim ? `<p class="nota-sim">${escapar(SIM_NOTE)}</p>` : ""}
       <div class="grupo-titulo">Eventos reales en este edificio</div><ul class="feed" style="padding:0">${pulsos}</ul>`;
    return;
  }
  const a = ultimo.agents.find((x) => x.key === seleccion.key);
  if (!a) return pintarResumen();
  const esSim = a.kind === "simulated";
  $("p-titulo").textContent = a.name;
  $("p-badge").className = `badge ${esSim ? "sim" : "real"}`;
  $("p-badge").textContent = esSim ? "SIMULADO" : "REAL";
  $("p-cuerpo").innerHTML =
    `${fila("Estado", a.state)}
     ${fila("Dónde está", NOMBRE_EDIFICIO[a.target] || a.target)}
     ${fila("Motivo", a.reason)}
     <div style="display:flex;gap:6px;margin:6px 0">
       <button data-accion="${seguir === a.key ? "dejar" : "seguir"}" type="button">${seguir === a.key ? "Dejar de seguir" : "Seguir agente"}</button>
       <button data-accion="enfocar" type="button" disabled title="Enfoca el edificio donde está">Enfocar</button>
     </div>
     ${esSim ? `<p class="nota-sim">${escapar(SIM_NOTE)}. No es evidencia de trabajo.</p>`
       : `${fila("Tarea actual", a.currentTask || "NOT_SYNCED")}
          ${fila("Último commit", a.heartbeat || "NOT_SYNCED (no es heartbeat)")}
          ${fila("Último resultado", a.lastResult || "NOT_SYNCED")}
          ${fila("Último evento", a.lastEvent ? a.lastEvent.type + " · " + a.lastEvent.at : "ninguno en 2 h")}`}`;
}

function pintarResumen() {
  $("p-titulo").textContent = "Ciudad";
  $("p-badge").className = "badge mix";
  $("p-badge").textContent = "RESUMEN";
  const reales = ultimo.agents.filter((a) => a.kind !== "simulated");
  const sims = ultimo.agents.filter((a) => a.kind === "simulated");
  $("p-cuerpo").innerHTML =
    `${fila("Modo", ultimo.mode)}
     ${fila("Sincronización", ultimo.syncOk ? "OK" : "no verificada")}
     ${fila("Agentes reales", reales.length)}
     ${fila("Población simulada", sims.length)}
     ${fila("Demanda real", `${ultimo.demand?.abiertas ?? 0} abiertas · ${ultimo.demand?.actividad24h ?? 0} eventos 24 h`)}`;
}

function pintarRealidad() {
  const reales = ultimo.agents.filter((a) => a.kind !== "simulated");
  $("sec-real").innerHTML =
    `${fila("Sincronización", ultimo.syncOk ? "OK" : "no verificada")}
     ${fila("Agentes reales", reales.length)}
     ${reales.map((a) => fila(a.name, a.state)).join("")}
     <p class="muted" style="font-size:11px;margin:6px 0 0">Estados sólo de sync, eventos reales y documentos. Sin evidencia = NOT_SYNCED.</p>`;
}

function pintarSimulacion() {
  const sims = ultimo.agents.filter((a) => a.kind === "simulated" && a.stage !== "SIM_ROLE");
  const porEstado = {};
  for (const s of sims) porEstado[s.state] = (porEstado[s.state] || 0) + 1;
  const estados = Object.entries(porEstado).map(([k, v]) => `<span>${escapar(k)} ${v}</span>`).join("") || "<span>ninguno</span>";
  const roles = ultimo.agents.filter((a) => a.stage === "SIM_ROLE").map((s) => `<span>${escapar(s.name)}</span>`).join("") || "<span>ninguno</span>";
  $("sec-sim").innerHTML =
    `<p class="nota-sim">${escapar(SIM_NOTE)}. Crece sólo con demanda real: abiertas ${ultimo.demand?.abiertas ?? 0}, eventos 24 h ${ultimo.demand?.actividad24h ?? 0}.</p>
     ${fila("Población", sims.length)}
     <div class="grupo-titulo">Estados visuales</div><div class="chipline">${estados}</div>
     <div class="grupo-titulo">Roles simulados activos</div><div class="chipline">${roles}</div>`;
}

function pintarRoles() {
  const conectados = ultimo.agents.filter((a) => a.kind !== "simulated" && a.stage === "CORE")
    .map((a) => `<span>${escapar(a.name)} (${escapar(a.alias)})</span>`).join("") || "<span>ninguno</span>";
  const simulados = ultimo.agents.filter((a) => a.stage === "SIM_ROLE").map((a) => `<span>${escapar(a.name)}</span>`).join("") || "<span>ninguno</span>";
  const planeados = ultimo.planned || [];
  const grupos = CATEGORIAS.map((c) => {
    const lista = planeados.filter((p) => p.categoria === c);
    if (!lista.length) return "";
    return `<div class="grupo-titulo">${escapar(c)}</div>` + lista.map((p) => fila(p.name, p.state)).join("");
  }).join("");
  $("sec-roles").innerHTML =
    `<div class="grupo-titulo">Conectados a fuente real</div><div class="chipline">${conectados}</div>
     <div class="grupo-titulo">Simulados activos (sin fuente real)</div><div class="chipline">${simulados}</div>
     <div class="grupo-titulo">Planificados (inactivos)</div>${grupos || "<p class='muted'>ninguno</p>"}`;
}

function pintarFeed() {
  $("feed").innerHTML = ultimo.feed.map((e) =>
    `<li><b>${escapar(e.type)}</b> <span class="badge real" style="font-size:9px">REAL</span><br>${escapar(e.subject)} ${escapar(e.detail)}<br><time>${escapar(e.observed_at || e.ts || "")}</time></li>`
  ).join("") || "<li class='muted'>sin eventos</li>";
}

function pintarBanners() {
  $("banners").innerHTML = ultimo.banners.map((b) => `<div class="b">${escapar(b)}</div>`).join("");
  $("modo").textContent = `${ultimo.mode} MODE`;
  $("sync").textContent = ultimo.syncOk ? `sync OK · ${ultimo.snapshotAt}` : "sync no verificada";
}

// ---------- refresco (conservador: 30 s, sólo lectura)
async function refrescar() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const datos = await r.json();
    ultimo = deriveCity({ snapshot: datos.snapshot, society: datos.society, events: datos.events, now: new Date() });
    asignarDestinos(ultimo);
    actualizarPulsos(ultimo, Date.now());
    aplicarInteriores();
    pintarBanners();
    pintarRealidad();
    pintarSimulacion();
    pintarRoles();
    pintarFeed();
    pintarSeleccion();
    resaltarSeleccion();
    $("refresco").textContent = `actualizado ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    $("sync").textContent = "servidor no responde";
    $("banners").innerHTML = `<div class="b">SIN DATOS: ${escapar(e.message)}. Se conserva la última vista.</div>`;
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
  avanzarAgentes(dt, ahora);
  animarPulsos(Date.now());
  if (seguir && agentes[seguir] && agentes[seguir].grupo.visible) {
    const d = agentes[seguir].grupo.position.clone().sub(controles.target);
    controles.target.add(d);
    camara.position.add(d);
  }
  controles.update();
  renderer.render(scene, camara);
});

aplicarPestana();
refrescar();
setInterval(refrescar, REFRESCO_MS);
