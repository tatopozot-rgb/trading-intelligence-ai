// Escena three.js de Agent City 3D. Estado y vida en lib/model.mjs, lib/life.mjs y rutas en lib/paths.mjs (probados).
// Regla visual: REAL y SIMULADO siempre etiquetados; WORKING sólo viene de estado real.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { BUILDINGS, AGENTS, STATE_COLOR, SIM_NOTE, deriveCity, CATEGORIAS } from "/lib/model.mjs";
import { planRuta, posicionMundo, PUERTA_Z } from "/lib/paths.mjs";

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
const VELOCIDAD_PIE = 4.5;
const VELOCIDAD_BICI = 9;
const COLOR_SIM = 0xcbd5e1;
// Estados simulados en los que el avatar está dentro del edificio (entra por la puerta).
const DENTRO_SIM = ["SIM_SLEEPING", "SIM_STUDYING", "SIM_WORKING", "SIM_ON_DUTY", "SIM_MEETING", "SIM_MENTORING"];
const SENTADO_SIM = ["SIM_WORKING", "SIM_STUDYING", "SIM_MEETING", "SIM_MENTORING", "SIM_ON_DUTY"];
const LOD_MEDIO = 45;
const LOD_LEJOS = 85;

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

// Coordenadas de mundo a partir de lib/paths (misma geometría que las rutas probadas).
const v3 = (p) => new THREE.Vector3(p.x, 0, p.z);
const ids = (id) => EDIFICIO_DE[id] || EDIFICIO_DE.residential;
const puntoCalle = (id) => { const p = posicionMundo(ids(id)); return new THREE.Vector3(p.x, 0, p.z + 3.6); };

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

// Etiquetas de estado legibles: qué hace el agente, con icono y texto corto.
const ETIQUETA_ESTADO = {
  WORKING: ["🟢", "TRABAJANDO", "#86efac"], REVIEWING: ["🔵", "REVISANDO", "#93c5fd"], BLOCKED: ["🟠", "BLOQUEADO", "#fdba74"],
  STUDYING: ["📘", "ESTUDIANDO", "#fde68a"], TRAINING: ["📘", "ENTRENANDO", "#fde68a"], EXAMINING: ["📝", "EXAMEN", "#fde68a"],
  SLEEPING: ["💤", "DURMIENDO", "#a5b4fc"], SEEKING_WORK: ["🔎", "BUSCANDO TRABAJO", "#fdba74"], MEETING: ["👥", "EN REUNIÓN", "#67e8f9"],
  MENTORING: ["🧑‍🏫", "MENTORIZANDO", "#d8b4fe"], COMMUTING: ["🚲", "DE CAMINO", "#67e8f9"], RESTING: ["🌿", "DESCANSANDO", "#d9f99d"],
  LEISURE: ["🌳", "TIEMPO LIBRE", "#bbf7d0"], ON_DUTY: ["🟢", "EN SERVICIO", "#86efac"], IDLE: ["⚪", "EN ESPERA", "#cbd5e1"],
  NOT_SYNCED: ["❔", "SIN EVIDENCIA", "#cbd5e1"], STALE: ["⌛", "DATOS VIEJOS", "#d6d3d1"],
};
function etiquetaEstado(state) {
  const base = String(state || "").replace(/^SIM_/, "");
  return ETIQUETA_ESTADO[base] || ["•", base, "#e5e7eb"];
}
// Tarjeta compacta de 3 líneas: estado · nombre · tarea. Reemplaza las etiquetas gigantes de una línea.
function crearTarjeta(a) {
  const [icono, texto, color] = etiquetaEstado(a.state);
  const c = document.createElement("canvas");
  c.width = 420; c.height = 116;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(11,18,32,0.86)";
  g.beginPath(); g.roundRect(3, 3, c.width - 6, c.height - 6, 14); g.fill();
  g.fillStyle = color; g.font = "bold 26px system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(`${icono} ${texto}`, c.width / 2, 28);
  g.fillStyle = a.kind === "simulated" ? "#fde68a" : "#f8fafc"; g.font = "bold 24px system-ui, sans-serif";
  g.fillText(a.kind === "simulated" ? `${a.name} · SIM` : a.name, c.width / 2, 60);
  const tarea = a.kind === "simulated" ? (a.reason || "") : (a.currentTask || "NOT_SYNCED");
  g.fillStyle = "#cbd5e1"; g.font = "20px system-ui, sans-serif";
  const corta = tarea.length > 34 ? tarea.slice(0, 33) + "…" : tarea;
  g.fillText(corta, c.width / 2, 92);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  sp.scale.set(3.6, 0.99, 1);
  return sp;
}

// ---------- interiores y puertas
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
  // Puerta: hueco oscuro en la fachada, en la misma línea que la ruta (PUERTA_Z).
  if (TIENE_INTERIOR.has(b.id)) {
    const puerta = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.8, 0.12), new THREE.MeshStandardMaterial({ color: 0x111827 }));
    puerta.position.set(0, 0.9, PUERTA_Z);
    grupo.add(puerta);
  }
  const p = posicionMundo(b);
  grupo.position.set(p.x, 0, p.z);
  const etiqueta = crearEtiqueta(b.label, 600, 80, "#f8fafc", 36);
  etiqueta.position.set(0, alto + 1.4, 0);
  grupo.add(etiqueta);
  const anillos = new THREE.Group();
  grupo.add(anillos);
  if (b.id === "residential") {
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

// ---------- avatares humanoides (con niveles de detalle)
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
  const etiqueta = crearTarjeta({ name: nombre, kind: esSimulado ? "simulated" : "real", state: "IDLE", reason: "", currentTask: null });
  etiqueta.position.y = 2.9;
  const grupoBici = new THREE.Group();
  const ruedaM = new THREE.MeshStandardMaterial({ color: 0x111827 });
  for (const x of [-0.45, 0.45]) {
    const rueda = new THREE.Mesh(new THREE.TorusGeometry(0.32, 0.05, 6, 14), ruedaM);
    rueda.rotation.y = Math.PI / 2; rueda.position.set(x, 0.36, 0);
    grupoBici.add(rueda);
  }
  const cuadro = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.06, 0.06), new THREE.MeshStandardMaterial({ color: 0xf97316 }));
  cuadro.position.set(0, 0.6, 0);
  grupoBici.add(cuadro);
  grupoBici.visible = false;
  const elementos = [torso, cabeza, cabello, brazoI, brazoD, piernaI, piernaD, aro, seleccionAro, etiqueta, grupoBici];
  if (key === "sim-supervisor") {
    // Presencia visual del supervisor: portapapeles de backlog en el brazo izquierdo.
    const tabla = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.36, 0.04), new THREE.MeshStandardMaterial({ color: 0xf8fafc }));
    tabla.position.set(0.1, -0.52, 0.2);
    brazoD.add(tabla);
    elementos.push(tabla);
  }
  grupo.add(...elementos);
  grupo.userData = { kind: "agent", key };
  for (const m of [torso, cabeza, cabello, subI, subD, malI, malD]) m.userData = grupo.userData;
  scene.add(grupo);
  agentes[key] = { grupo, aro, seleccionAro, etiqueta, piernaI, piernaD, brazoI, brazoD, torso, cabeza, cabello, grupoBici,
    ruta: [], destino: null, destinoClave: null, desfase: Math.random() * 6, esSimulado, enEdificio: null,
    velocidad: VELOCIDAD_PIE, lod: 0, estado: null, transporte: "caminar", sentado: false, acostado: false };
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

// Rutas: cada cambio de destino recalcula la ruta desde la posición actual (calle → puerta → interior o salida inversa).
function asignarDestinos(city) {
  sincronizarAvatares(city);
  const porEdificio = {};
  for (const a of city.agents) (porEdificio[a.target] ||= []).push(a.key);
  for (const a of city.agents) {
    const ag = agentes[a.key];
    if (!ag) continue;
    const grupo = porEdificio[a.target];
    const slot = grupo.indexOf(a.key);
    const adentro = a.kind === "simulated" && DENTRO_SIM.includes(a.state) && EDIFICIO_DE[a.target]?.id && TIENE_INTERIOR.has(a.target);
    const offset = (slot - (grupo.length - 1) / 2) * 1.2;
    const clave = `${a.target}|${adentro}|${slot}|${a.state}`;
    ag.estado = a.state;
    ag.transporte = a.transporte || "caminar";
    ag.velocidad = ag.transporte === "bici" ? VELOCIDAD_BICI : VELOCIDAD_PIE;
    ag.sentado = adentro && SENTADO_SIM.includes(a.state);
    ag.acostado = adentro && a.state === "SIM_SLEEPING";
    ag.colorEstado = STATE_COLOR[a.state] ?? 0x6b7280;
    ag.aro.material.color.setHex(ag.colorEstado);
    ag.modelo = a;
    if (ag.destinoClave !== clave) {
      const b = EDIFICIO_DE[a.target];
      const actual = ag.grupo.position.lengthSq() === 0
        ? (a.kind === "simulated" && a.home ? puntoCalle(a.home) : puntoCalle(a.target))
        : ag.grupo.position.clone();
      const origen = ag.enEdificio ? EDIFICIO_DE[ag.enEdificio] : null;
      const plan = planRuta({ desde: { x: actual.x, z: actual.z }, origen, destino: b, adentro });
      const puntos = plan.puntos.map(v3);
      // El último punto se desplaza por slot para que los avatares del mismo edificio no se solapen.
      const fin = puntos[puntos.length - 1];
      fin.x += offset;
      ag.ruta = puntos;
      ag.t = 0;
      ag.destinoClave = clave;
      ag.destinoAdentro = adentro;
      ag.destinoEdificio = a.target;
    }
    const clave2 = `${a.state}|${a.currentTask || a.reason || ""}`;
    if (ag.claveTarjeta !== clave2) {
      const nueva = crearTarjeta(a);
      ag.etiqueta.material.map.dispose();
      ag.etiqueta.material.map = nueva.material.map;
      ag.etiqueta.material.needsUpdate = true;
      nueva.material.dispose();
      ag.claveTarjeta = clave2;
    }
  }
}

// Movimiento: pies o bicicleta según el trayecto; sentado o tumbado al trabajar o dormir dentro.
function avanzarAgentes(dt, tiempo, camaraPos) {
  for (const key in agentes) {
    const ag = agentes[key];
    if (!ag.grupo.visible) continue;
    const distancia = camaraPos.distanceTo(ag.grupo.position);
    ag.lod = distancia > LOD_LEJOS ? 2 : distancia > LOD_MEDIO ? 1 : 0;
    const activo = ag.estado !== null && !["SIM_SLEEPING", "SIM_LEISURE", "SIM_RESTING", "SIM_TRAVEL", "IDLE"].includes(ag.estado);
    ag.etiqueta.visible = ag.seleccionAro.visible || (ag.esSimulado ? distancia < 32 && activo : ag.lod < 2);
    if (ag.ruta.length >= 2) {
      let restante = ag.velocidad * dt;
      while (restante > 0 && ag.ruta.length >= 2) {
        const a = ag.ruta[0], b = ag.ruta[1];
        const tramo = a.distanceTo(b);
        const hueco = tramo - (ag.t || 0);
        const usado = Math.min(restante, hueco);
        ag.t = (ag.t || 0) + usado;
        restante -= usado;
        ag.grupo.position.lerpVectors(a, b, tramo === 0 ? 1 : ag.t / tramo);
        if (ag.t >= tramo - 1e-6) { ag.ruta.shift(); ag.t = 0; }
      }
      if (ag.ruta.length < 2) {
        // Llegó: si el destino está dentro, queda dentro; si no, queda en la calle.
        ag.enEdificio = ag.destinoAdentro ? ag.destinoEdificio : null;
      }
    }
    const moviendose = ag.ruta.length >= 2;
    ag.grupoBici.visible = moviendose && ag.transporte === "bici" && ag.lod === 0;
    if (moviendose) {
      ag.grupo.lookAt(ag.ruta[1]);
      const paso = Math.sin(tiempo / (ag.transporte === "bici" ? 60 : 110) + ag.desfase) * 0.7;
      ag.piernaI.rotation.x = paso; ag.piernaD.rotation.x = -paso;
      ag.brazoI.rotation.x = -paso * 0.8; ag.brazoD.rotation.x = paso * 0.8;
      ag.grupo.position.y = ag.transporte === "bici" ? 0.3 : Math.abs(Math.sin(tiempo / 110 + ag.desfase)) * 0.06;
      ag.grupo.rotation.x = 0;
    } else {
      ag.grupo.position.y = 0;
      ag.grupo.rotation.x = 0;
      const r = Math.sin(tiempo / 700 + ag.desfase) * 0.05;
      if (ag.acostado) {
        ag.grupo.rotation.x = -Math.PI / 2 + 0.05;
        ag.grupo.position.y = 0.4;
        ag.piernaI.rotation.x = 0; ag.piernaD.rotation.x = 0;
        ag.brazoI.rotation.x = 0; ag.brazoD.rotation.x = 0;
      } else if (ag.sentado) {
        ag.piernaI.rotation.x = -1.4; ag.piernaD.rotation.x = -1.4;
        ag.brazoI.rotation.x = -0.6 + r; ag.brazoD.rotation.x = -0.6 - r;
      } else {
        ag.piernaI.rotation.x = 0; ag.piernaD.rotation.x = 0;
        ag.brazoI.rotation.x = r; ag.brazoD.rotation.x = -r;
      }
    }
    // LOD lejano: sin brazos, piernas ni cabello (silueta)
    const detalle = ag.lod === 0;
    ag.brazoI.visible = detalle; ag.brazoD.visible = detalle;
    ag.piernaI.visible = detalle; ag.piernaD.visible = detalle;
    ag.cabello.visible = ag.lod < 2;
    ag.aro.visible = ag.lod < 2;
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

// ---------- selección, cortes, seguimiento
let seleccion = null; // { kind: "building", id } | { kind: "agent", key }
let ultimo = null;
let seguir = null;
function resaltarSeleccion() {
  for (const id in edificios) {
    const sel = seleccion && seleccion.kind === "building" && seleccion.id === id;
    edificios[id].material.emissive = new THREE.Color(sel ? 0x334155 : 0x000000);
    edificios[id].material.opacity = sel ? 0.8 : 0.62;
  }
  for (const key in agentes) {
    const sel = Boolean(seleccion && seleccion.kind === "agent" && seleccion.key === key);
    agentes[key].seleccionAro.visible = sel;
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

function enfocarEdificio(id) {
  const b = ids(id);
  const p = posicionMundo(b);
  const centro = new THREE.Vector3(p.x, 0, p.z);
  controles.target.copy(centro);
  camara.position.copy(centro).add(new THREE.Vector3(12, 12, 12));
  controles.update();
}

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
renderer.domElement.addEventListener("dblclick", () => {
  if (seleccion && seleccion.kind === "building") enfocarEdificio(seleccion.id);
});

// ---------- paneles
const fila = (k, v) => `<div class="fila"><span>${escapar(k)}</span><span>${escapar(v)}</span></div>`;
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
$("p-cuerpo").addEventListener("click", (ev) => {
  const accion = ev.target?.dataset?.accion;
  if (!accion || !seleccion) return;
  if (accion === "seguir" && seleccion.kind === "agent") seguir = seleccion.key;
  if (accion === "dejar") seguir = null;
  if (accion === "enfocar" && seleccion.kind === "building") enfocarEdificio(seleccion.id);
  pintarSeleccion();
});
$("p-cerrar").addEventListener("click", () => {
  seleccion = null; seguir = null; pestana = "city";
  aplicarPestana(); resaltarSeleccion(); pintarSeleccion();
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
       ${fila("Agentes reales aquí", reales.length ? reales.map((a) => a.name).join(", ") : "ninguno")}
       ${fila("Simulados aquí", String(sims.length))}
       <button class="secundario" data-accion="enfocar" type="button" style="margin:6px 0">Enfocar edificio</button>
       ${esSim ? `<p class="nota-sim">${escapar(SIM_NOTE)}</p>` : ""}
       <div class="grupo-titulo">Eventos reales en este edificio</div><ul class="feed" style="padding:0">${pulsos}</ul>`;
    return;
  }
  const a = ultimo.agents.find((x) => x.key === seleccion.key);
  if (!a) return pintarResumen();
  const esSim = a.kind === "simulated";
  const siguiendo = seguir === a.key;
  $("p-titulo").textContent = a.name;
  $("p-badge").className = `badge ${esSim ? "sim" : "real"}`;
  $("p-badge").textContent = esSim ? "SIMULADO" : "REAL";
  $("p-cuerpo").innerHTML =
    `${fila("Rol", a.alias || "—")}
     ${fila("Estado", a.state)}
     ${fila("Edificio", NOMBRE_EDIFICIO[a.target] || a.target)}
     ${fila("Destino", NOMBRE_EDIFICIO[a.target] || a.target)}
     ${fila("Siguiente acción", a.reason)}
     ${esSim ? `${fila("Nivel", a.nivel || "—")}${fila("XP", a.xp ?? 0)}${fila("Habilidades", (a.skills || []).join(", ") || "—")}
       ${fila("Transporte", a.transporte || "caminar")}
       <p class="nota-sim">${escapar(SIM_NOTE)}. No es evidencia de trabajo.</p>`
       : `${fila("Tarea actual", a.currentTask || "NOT_SYNCED")}
          ${fila("Último commit", a.heartbeat || "NOT_SYNCED (no es heartbeat)")}
          ${fila("Último resultado", a.lastResult || "NOT_SYNCED")}
          ${fila("Último evento", a.lastEvent ? a.lastEvent.type + " · " + a.lastEvent.at : "ninguno en 2 h")}`}
     <div style="display:flex;gap:6px;margin:8px 0">
       <button data-accion="${siguiendo ? "dejar" : "seguir"}" type="button">${siguiendo ? "Dejar de seguir" : "Seguir agente"}</button>
       <button data-accion="enfocar" type="button" title="Enfoca el edificio donde está">Enfocar</button>
     </div>`;
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
  const aprendices = ultimo.agents.filter((a) => a.stage === "TRAINEE").length;
  const trabajadores = ultimo.agents.filter((a) => a.tipo === "worker").length;
  $("sec-sim").innerHTML =
    `<p class="nota-sim">${escapar(SIM_NOTE)}. Crece sólo con demanda real: abiertas ${ultimo.demand?.abiertas ?? 0}, eventos 24 h ${ultimo.demand?.actividad24h ?? 0}.</p>
     ${fila("Población", sims.length)}
     ${fila("Aprendices (sim)", aprendices)}
     ${fila("Puestos ocupados (sim)", trabajadores)}
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
  avanzarAgentes(dt, ahora, camara.position);
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
