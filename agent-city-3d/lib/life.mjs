// Capa de vida simulada (Life Simulation). Puro: sin red, sin escritura.
// TODO lo que sale de aquí es simulación visual inspirada en la operación. Nunca es evidencia operativa.
// Cada residente lleva kind="simulated" y se etiqueta así en la UI.

export const SIM_NOTE = "SIMULACIÓN — no es actividad real";
export const POBLACION_BASE = 6;
export const POBLACION_MAX = 40;

// Roles simulados activos (decorativos, coherentes con el edificio que ocupan).
export const ROLES_SIMULADOS = [
  { id: "sim-supervisor", name: "Supervisor (sim)", role: "supervisor", home: "command_center", kind: "simulated" },
  { id: "sim-recruiter", name: "Recruiter / Creator (sim)", role: "recruiter", home: "foundry", kind: "simulated" },
  { id: "sim-trainer", name: "Trainer (sim)", role: "trainer", home: "academy", kind: "simulated" },
  { id: "sim-auditor", name: "Auditor / Filter (sim)", role: "auditor", home: "hall", kind: "simulated" },
];

const NOMBRES = ["Ana", "Bruno", "Clara", "Diego", "Elena", "Felix", "Gala", "Hugo", "Iris", "Jonás", "Kira", "Lucas",
  "Mara", "Nico", "Olivia", "Pablo", "Quinn", "Rosa", "Samir", "Tara", "Uma", "Víctor", "Wren", "Yara", "Zoe", "Abel",
  "Bianca", "Cruz", "Dara", "Esteban", "Fiona", "Gabriel", "Helena", "Ivo", "Jade", "Kai", "Lola", "Milo", "Nora", "Otto", "Paz"];

// Población que crece sólo con demanda real (tareas abiertas y actividad reciente), con tope.
export function poblacionObjetivo(demanda) {
  const d = Math.max(0, Math.floor(demanda || 0));
  return Math.min(POBLACION_MAX, POBLACION_BASE + Math.ceil(d * 1.5));
}

// Residentes deterministas (mismo índice → mismo residente) para que la ciudad no cambie de cara al refrescar.
export function residentes(demanda) {
  const n = poblacionObjetivo(demanda);
  const lista = [];
  for (let i = 0; i < n; i++) {
    const tipo = i % 3 === 0 ? "trainee" : i % 3 === 1 ? "worker" : "resident";
    lista.push({
      id: `sim-${String(i + 1).padStart(2, "0")}`,
      name: NOMBRES[i % NOMBRES.length],
      kind: "simulated",
      tipo,
      home: `house_${"abcd"[i % 4]}`,
      workplace: tipo === "trainee" ? "academy" : tipo === "worker" ? (["quant_lab", "qa_facility", "engineering_lab", "risk_tower"][i % 4]) : null,
      skills: tipo === "trainee" ? ["curso"] : [],
      xp: 0,
      stage: tipo === "trainee" ? "TRAINEE" : "CITIZEN",
    });
  }
  return lista;
}

// Actividad según la hora local. Función pura: (residente, hora 0-23) → {actividad, destino, etiqueta}.
export function actividadPara(r, hora) {
  if (hora >= 22 || hora < 6) return { actividad: "SLEEPING", destino: r.home, etiqueta: "dormir en casa" };
  if (hora >= 6 && hora < 8) return { actividad: "TRAVEL", destino: r.home, etiqueta: "de camino al día" };
  if (hora >= 8 && hora < 12) {
    if (r.tipo === "trainee") return { actividad: "STUDYING", destino: "academy", etiqueta: "estudiar en la academia" };
    if (r.tipo === "worker") return { actividad: "WORKING", destino: r.workplace, etiqueta: `trabajar en ${r.workplace} (simulado)` };
    return { actividad: "LEISURE", destino: "park", etiqueta: "paseo por el parque" };
  }
  if (hora >= 12 && hora < 13) return { actividad: "BREAK", destino: "park", etiqueta: "descanso" };
  if (hora >= 13 && hora < 17) {
    if (r.tipo === "trainee") return { actividad: "STUDYING", destino: "university", etiqueta: "clase en la universidad" };
    if (r.tipo === "worker") return { actividad: "WORKING", destino: r.workplace, etiqueta: `trabajar en ${r.workplace} (simulado)` };
    return { actividad: "LEISURE", destino: "residential", etiqueta: "tiempo libre en el barrio" };
  }
  return { actividad: "LEISURE", destino: r.home, etiqueta: "tiempo en casa" };
}

// Ocioso útil: nunca se queda quieto. Sin tarea real, la simulación lo manda a casa, academia o parque.
export function standbyPara(r) {
  if (r.tipo === "trainee") return { actividad: "STUDYING", destino: "academy", etiqueta: "estudio libre (standby)" };
  return { actividad: "LEISURE", destino: "park", etiqueta: "standby visual" };
}

// Progreso de un trainee simulado. Graduación sólo con examen aprobado (simulado, con puntuación reproducible).
export function progresarTrainee(r, horasEstudio) {
  const xp = r.xp + Math.max(0, horasEstudio) * 10;
  if (xp < 100) return { ...r, xp, stage: "TRAINEE", examen: null };
  const puntuacion = 60 + (Number(r.id.replace(/\D/g, "")) * 17) % 40; // 60–99, determinista por id
  const aprobado = puntuacion >= 80;
  return { ...r, xp, stage: aprobado ? "GRADUATED_SIM" : "TRAINEE",
    examen: { curriculum: "curso simulado", score: puntuacion, min_score: 80, passed: aprobado, simulated: true } };
}

// Mapa de edificio → punto de entrada visual (la vida simulada entra por el interior).
export const INTERIOR_OK = ["house_a", "house_b", "house_c", "house_d", "academy", "university", "quant_lab",
  "qa_facility", "engineering_lab", "risk_tower", "park", "residential", "command_center", "foundry", "hall"];
