// Ciclo de vida de la vida SIMULADA. Puro: sin red, sin trading, sin escritura (salvo saveLife/loadLife a su propio archivo).
// NUNCA lee ni escribe órdenes, posiciones, riesgo ni datos financieros. Todo es gamificación.

export const ETAPAS = ["CHILD", "STUDENT", "YOUNG_ADULT", "ADULT", "SENIOR", "RETIRED"];
export const EDAD_RETIRO = 65;
// Años simulados por día real de offline: agregación, no tick a tick.
export const DIAS_SIM_POR_HORA_REAL = 1;      // 1 hora de cierre = 1 día simulado
export const MAX_DIAS_SIM_OFFLINE = 365 * 2;  // tope por sesión offline (no millones de ticks)

// Etapa vital según edad simulada (años).
export function etapaPorEdad(edad) {
  if (edad < 6) return "CHILD";
  if (edad < 18) return "STUDENT";
  if (edad < 30) return "YOUNG_ADULT";
  if (edad < 80) return edad < EDAD_RETIRO ? "ADULT" : "SENIOR";
  return "RETIRED";
}

// Avance de un habitante en `dias` simulados. Agregado: pocas transiciones, ningún bucle día a día.
// person: { id, nombre, edad (años), etapa, hogar, estudios:{curso,xp,graduado}, empleo:{estado}, relaciones:[] }
export function avanzarPersona(p, dias) {
  const d = Math.max(0, Math.floor(dias || 0));
  if (d === 0) return { ...p };
  const edad = p.edad + d / 365;
  let q = { ...p, edad, etapa: etapaPorEdad(edad) };
  // Estudios: los aprendices acumulan XP agregada; graduación sólo con examen aprobado (simulado).
  if (q.etapa === "STUDENT" || q.etapa === "YOUNG_ADULT") {
    if (q.estudios && !q.estudios.graduado && q.estudios.enCurso) {
      const xp = (q.estudios.xp || 0) + d * 0.5;
      q = { ...q, estudios: { ...q.estudios, xp } };
      if (xp >= 100) {
        const puntuacion = 60 + (hashNumero(q.id) * 17) % 40;
        const aprobado = puntuacion >= 80;
        q = { ...q, estudios: { ...q.estudios, graduado: aprobado, enCurso: !aprobado,
          examen: { curso: "curso simulado", puntuacion, aprobado, simulado: true } } };
        if (aprobado) q = { ...q, empleo: { estado: "SEEKING_WORK" } }; // graduado → busca trabajo simulado
      }
    }
  }
  // Retiro: deja de trabajar, conserva casa, vida social y parque.
  if (q.edad >= EDAD_RETIRO) q = { ...q, empleo: { estado: "RETIRED" } }; // deja de trabajar; sigue viviendo en su hogar
  return q;
}

// Número determinista a partir del id (para exámenes y eventos reproducibles).
export function hashNumero(id) {
  let h = 0;
  for (const c of String(id)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h;
}

// Nacimiento dentro de un hogar: sólo pareja adulta, con probabilidad determinista por hogar y año.
export function posibleNacimiento(hogar, anio) {
  const adultos = hogar.miembros.filter((m) => ["YOUNG_ADULT", "ADULT"].includes(m.etapa));
  if (adultos.length < 2) return null;
  if (hogar.miembros.filter((m) => m.etapa === "CHILD").length >= 3) return null;
  if (hashNumero(hogar.id + anio) % 5 !== 0) return null; // ~1 de cada 5 años como máximo
  return { id: `${hogar.id}-h${anio}`, nombre: "Hijo/a", edad: 0, etapa: "CHILD", hogar: hogar.id, estudios: null, empleo: null, relaciones: [] };
}

// Progresión offline agregada: convierte tiempo real transcurrido en días simulados acotados.
export function progresoOffline({ ultimoTs, ahoraTs }) {
  if (!ultimoTs) return { diasSim: 0, motivo: "primera ejecución: sin progresión" };
  const horas = (ahoraTs - ultimoTs) / 3600000;
  if (!(horas > 0)) return { diasSim: 0, motivo: "sin tiempo transcurrido" };
  const diasSim = Math.min(MAX_DIAS_SIM_OFFLINE, Math.floor(horas * DIAS_SIM_POR_HORA_REAL));
  return { diasSim, motivo: horas > MAX_DIAS_SIM_OFFLINE / DIAS_SIM_POR_HORA_REAL ? "tope de progresión offline aplicado" : "progresión agregada" };
}

// Aplica la progresión offline completa a una población.
export function aplicarOffline(poblacion, { ultimoTs, ahoraTs }) {
  const { diasSim, motivo } = progresoOffline({ ultimoTs, ahoraTs });
  return { poblacion: poblacion.map((p) => avanzarPersona(p, diasSim)), diasSim, motivo };
}

// Persona inicial a partir de un residente de la capa de vida: edad determinista por id, sin datos financieros.
export function personaInicial(r) {
  const edad = 6 + (hashNumero(r.id) % 55);
  const etapa = etapaPorEdad(edad);
  return {
    id: r.id, nombre: r.name, edad, etapa, hogar: r.home,
    estudios: etapa === "STUDENT" || etapa === "YOUNG_ADULT" ? { curso: "curso simulado", xp: 0, graduado: false, enCurso: true } : null,
    empleo: r.tipo === "worker" ? { estado: "WORKING" } : null,
    relaciones: [],
  };
}

// Perfil visual por etapa: tamaño y velocidad del avatar. Puro; la escena sólo lo aplica.
export const PERFIL_ETAPA = {
  CHILD: { escala: 0.62, velocidad: 0.9 },
  STUDENT: { escala: 0.82, velocidad: 1 },
  YOUNG_ADULT: { escala: 1, velocidad: 1 },
  ADULT: { escala: 1, velocidad: 1 },
  SENIOR: { escala: 0.97, velocidad: 0.8 },
  RETIRED: { escala: 0.95, velocidad: 0.65 },
};
export function perfilEtapa(etapa) {
  return PERFIL_ETAPA[etapa] || { escala: 1, velocidad: 1 };
}

// Rutina de jubilado: ya no trabaja; vive, pasea y socializa. Nunca desaparece.
export function actividadJubilado(hora) {
  if (hora >= 22 || hora < 7) return { actividad: "SLEEPING", destino: "home", etiqueta: "descanso (jubilado)" };
  if (hora < 11) return { actividad: "LEISURE", destino: "home", etiqueta: "mañana tranquila en casa" };
  if (hora < 16) return { actividad: "LEISURE", destino: "park", etiqueta: "parque y socializar (jubilado)" };
  if (hora < 20) return { actividad: "LEISURE", destino: "residential", etiqueta: "paseo por el barrio" };
  return { actividad: "LEISURE", destino: "home", etiqueta: "tarde en casa" };
}

// Marca el instante de graduación (sólo transición false→true) para mostrar un evento visual SIM.
// No decide nada por sí sola: la recibe ya calculada aplicarOffline y la usa life-store al guardar.
export function marcarGraduaciones(antes, despues, ahoraIso) {
  const yaGraduado = new Set(antes.filter((p) => p.estudios?.graduado).map((p) => p.id));
  return despues.map((p) => (p.estudios?.graduado && !yaGraduado.has(p.id) ? { ...p, graduadoEn: ahoraIso } : p));
}
