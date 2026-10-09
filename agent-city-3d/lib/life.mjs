// Capa de vida simulada (Life Simulation). Puro: sin red, sin escritura.
// TODO lo que sale de aquí es simulación visual inspirada en la operación. Nunca es evidencia operativa.
// Cada residente lleva kind="simulated". La población y los puestos crecen sólo con demanda real.

export const SIM_NOTE = "SIMULACIÓN — no es actividad real";
export const POBLACION_BASE = 6;
export const POBLACION_MAX = 40;
export const APRENDICES_MAX = 4;
const EDIFICIOS_TRABAJO = ["quant_lab", "qa_facility", "engineering_lab", "risk_tower", "market_intel"];
const DISTANCIA_BICI = 2; // trayecto largo: se usa bicicleta SIM

// Roles simulados activos (decorativos y coherentes con su rutina).
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

// Puestos y aprendices según demanda: sin demanda no hay aprendices ni puestos (no se inventa trabajo).
export function reparto(demanda) {
  const d = Math.max(0, Math.floor(demanda || 0));
  const n = poblacionObjetivo(d);
  const aprendices = d > 0 ? Math.min(APRENDICES_MAX, Math.ceil(d / 3)) : 0;
  const puestos = Math.min(n - aprendices, d);
  return { n, aprendices, puestos };
}

// Residentes deterministas (mismo índice, mismo residente) para que la ciudad no cambie al refrescar.
export function residentes(demanda) {
  const { n, aprendices, puestos } = reparto(demanda);
  const lista = [];
  for (let i = 0; i < n; i++) {
    const tipo = i < aprendices ? "trainee" : i < aprendices + puestos ? "worker" : "resident";
    lista.push({
      id: `sim-${String(i + 1).padStart(2, "0")}`,
      name: NOMBRES[i % NOMBRES.length],
      kind: "simulated",
      tipo,
      home: `house_${"abcde"[i % 5]}`, // 5 casas x 8 camas (litera) = POBLACION_MAX exacto, sin repetir cama
      workplace: tipo === "worker" ? EDIFICIOS_TRABAJO[i % EDIFICIOS_TRABAJO.length] : null,
      conPuesto: tipo === "worker",
      skills: tipo === "trainee" ? ["curso"] : tipo === "worker" ? ["operación"] : [],
      xp: 0,
      stage: tipo === "trainee" ? "TRAINEE" : "CITIZEN",
    });
  }
  return lista;
}

// Actividad según la hora local. Función pura: (residente, hora 0-23) → {actividad, destino, etiqueta, transporte}.
// Los nombres de actividad son internos; el modelo los muestra con prefijo SIM_.
export function actividadPara(r, hora) {
  const fin = (actividad, destino, etiqueta, transporte = "caminar") => ({ actividad, destino, etiqueta, transporte });
  if (hora >= 22 || hora < 6) return fin("SLEEPING", r.home, "dormir en casa");
  if (hora < 8) {
    if (r.tipo === "worker") return fin("COMMUTING", r.workplace, `camino al trabajo en ${r.workplace} (sim)`, "bici");
    return fin("TRAVEL", r.home, "de camino al día");
  }
  if (hora < 12) {
    if (r.tipo === "trainee") return fin("STUDYING", "academy", "estudiar en la academia");
    if (r.tipo === "worker") {
      if (hora === 10) return fin("MEETING", "command_center", "reunión de equipo (sim)");
      if (r.conPuesto) return fin("WORKING", r.workplace, `trabajar en ${r.workplace} (sim)`);
      return fin("SEEKING_WORK", "command_center", "buscar trabajo en el tablón (sim)");
    }
    return fin("LEISURE", "park", "paseo por el parque");
  }
  if (hora < 13) return fin("RESTING", "park", "descanso (sim)");
  if (hora < 17) {
    if (r.tipo === "trainee") return fin("STUDYING", "university", "clase en la universidad");
    if (r.tipo === "worker") {
      if (r.conPuesto) return fin("WORKING", r.workplace, `trabajar en ${r.workplace} (sim)`);
      return fin("STUDYING", "academy", "formación mientras no hay trabajo (sim)");
    }
    return fin("LEISURE", "residential", "tiempo libre en el barrio");
  }
  if (r.tipo === "worker") return fin("RESTING", r.home, "volver a casa (sim)", "bici");
  return fin("LEISURE", r.home, "tiempo en casa");
}

// Rutina de los roles simulados (supervisor, creator, trainer, auditor). Siempre tiene destino.
export function actividadRol(rol, hora) {
  const fin = (actividad, destino, etiqueta) => ({ actividad, destino, etiqueta, transporte: "caminar" });
  switch (rol.role) {
    case "supervisor":
      if (hora === 10) return fin("MEETING", "command_center", "reunión de coordinación (sim)");
      if (hora >= 13 && hora < 17) return fin("ON_DUTY", "foundry", "revisar capacidad en la Foundry (sim)");
      return fin("ON_DUTY", "command_center", "supervisar backlog (sim)");
    case "trainer":
      if (hora >= 9 && hora < 17) return fin("MENTORING", "academy", "mentoría de aprendices (sim)");
      return fin("RESTING", "academy", "fuera de turno (sim)");
    case "recruiter":
      return fin("ON_DUTY", "foundry", "crear propuestas de trainees (sim)");
    default:
      return fin("ON_DUTY", "hall", "auditoría de graduaciones (sim)");
  }
}

// Ocioso útil: nunca se queda quieto. Sin tarea real, la simulación lo manda a casa, academia o parque.
export function standbyPara(r) {
  if (r.tipo === "trainee") return { actividad: "STUDYING", destino: "academy", etiqueta: "estudio libre (standby)", transporte: "caminar" };
  return { actividad: "LEISURE", destino: "park", etiqueta: "standby visual", transporte: "caminar" };
}

export { DISTANCIA_BICI };

// Progreso de un trainee simulado. Graduación sólo con examen aprobado (simulado, puntuación reproducible).
export function progresarTrainee(r, horasEstudio) {
  const xp = r.xp + Math.max(0, horasEstudio) * 10;
  if (xp < 100) return { ...r, xp, stage: "TRAINEE", examen: null };
  const puntuacion = 60 + (Number(r.id.replace(/\D/g, "")) * 17) % 40; // 60–99, determinista por id
  const aprobado = puntuacion >= 80;
  return { ...r, xp, stage: aprobado ? "GRADUATED_SIM" : "TRAINEE",
    examen: { curriculum: "curso simulado", score: puntuacion, min_score: 80, passed: aprobado, simulated: true } };
}

// Reloj visual de la simulación: acelerado a propósito para que la ciudad se vea viva en minutos reales.
// Sólo decide la rutina horaria (trabajar/estudiar/pasear); la edad y el envejecimiento usan tiempo real (lifecycle.mjs).
export const SEGUNDOS_POR_DIA_VISUAL = 150; // 1 día simulado visual = 150 s reales (~6.25 s por hora)
export function horaVisual(ahoraMs) {
  const seg = (ahoraMs / 1000) % SEGUNDOS_POR_DIA_VISUAL;
  return Math.floor((seg / SEGUNDOS_POR_DIA_VISUAL) * 24);
}
