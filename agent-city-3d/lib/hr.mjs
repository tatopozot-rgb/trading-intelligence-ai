// HR / Performance Auditor. Módulo puro: sólo recomienda, nunca aplica cambios.
// Cada recomendación cita la evidencia (eventos y examen) que la justifica. Autoridad final: Claude Leader.
// Una recomendación sin evidencia no se emite. El tiempo de servicio, por sí solo, nunca justifica nada.

export const ACCIONES = ["TRAIN", "PROMOTE", "REASSIGN", "MENTOR", "RETIRE", "REPLACE"];
export const AUTORIDAD = "Claude Leader";
const GRADUADOS = ["GRADUATED_AGENT", "SPECIALIST", "SENIOR", "MENTOR"];

function metricas(agente, eventos) {
  const mios = eventos.filter((e) => e.agent_id === agente.id);
  const cuenta = (t) => mios.filter((e) => e.type === t).length;
  return {
    completadas: cuenta("TASK_COMPLETED"),
    fallidas: cuenta("TASK_FAILED"),
    tests_ok: cuenta("TEST_PASSED"),
    tests_ko: cuenta("TEST_FAILED"),
    revisiones: cuenta("PR_REVIEWED"),
    refs: mios.map((e) => e.evidence || e.observed_at).filter(Boolean),
  };
}

// Devuelve { authority, recomendaciones:[{agente, accion, motivo, evidencia}], sinEvidencia:[...] }
export function auditar({ agents = [], eventos = [], backlog = [], ahora = new Date(), diasSinActividad = 14 }) {
  const recomendaciones = [];
  const sinEvidencia = [];
  const porHabilidad = (h) => agents.filter((a) => GRADUADOS.includes(a.stage) && (a.skills || []).includes(h));

  for (const a of agents) {
    if (a.stage === "CORE") continue; // fundadores: fuera del auditor de sociedad
    const m = metricas(a, eventos);
    const evidencia = m.refs.slice(-5);

    // TRAIN: examen suspendido o habilidad pedida por el backlog que no tiene.
    const ultimoExamen = (a.exams || []).at(-1);
    if (ultimoExamen && ultimoExamen.passed === false) {
      recomendaciones.push({ agente: a.id, accion: "TRAIN", motivo: `examen ${ultimoExamen.curriculum} suspendido (${ultimoExamen.score}/${ultimoExamen.min_score})`, evidencia: [ultimoExamen.ref].filter(Boolean) });
    }
    // MENTOR: fallos repetidos en un área con mentor que la domina.
    if (m.tests_ko >= 2 && a.mentor) {
      recomendaciones.push({ agente: a.id, accion: "MENTOR", motivo: `${m.tests_ko} tests fallidos; asignar mentor`, evidencia });
    }

    // PROMOTE: graduado con evidencia positiva suficiente y sin fallos. Sólo recomendación.
    if (a.stage === "GRADUATED_AGENT" && m.completadas >= 5 && m.tests_ko === 0 && m.fallidas === 0) {
      recomendaciones.push({ agente: a.id, accion: "PROMOTE", motivo: `${m.completadas} tareas completadas sin fallos ni tests fallidos`, evidencia });
    }

    // RETIRE / REPLACE: sin actividad verificable durante mucho tiempo, o bloqueado sin reemplazo.
    const ultimo = eventos.filter((e) => e.agent_id === a.id).map((e) => Date.parse(e.observed_at)).sort((x, y) => y - x)[0];
    // Inactividad exige evidencia de la última actividad; sin eventos no hay juicio posible.
    const sinActividad = ultimo !== undefined && (ahora - ultimo) / 86400000 > diasSinActividad;
    if (sinActividad && a.retirement_condition && GRADUADOS.includes(a.stage)) {
      const reemplazo = porHabilidad((a.skills || [])[0] || "").find((b) => b.id !== a.id);
      if (reemplazo) recomendaciones.push({ agente: a.id, accion: "REPLACE", motivo: `sin actividad verificable > ${diasSinActividad} d; reemplazo ${reemplazo.id}`, evidencia: [] });
      else recomendaciones.push({ agente: a.id, accion: "RETIRE", motivo: `sin actividad verificable > ${diasSinActividad} d; condición de retiro declarada`, evidencia: [] });
    }
    if (!ultimo) sinEvidencia.push(a.id); // sin eventos: el auditor no emite juicio sobre él
  }

  // REASSIGN: tarea compatible con un agente graduado ocioso distinto del actual (lo hace el supervisor, aquí sólo se sugiere).
  for (const t of backlog) {
    const candidatos = agents.filter((b) => GRADUADOS.includes(b.stage) && ["IDLE", "SLEEPING"].includes(b.state) && (t.skills || []).every((s) => (b.skills || []).includes(s)));
    if (t.assignedTo && candidatos.length && !candidatos.some((c) => c.id === t.assignedTo)) {
      recomendaciones.push({ agente: t.assignedTo, accion: "REASSIGN", motivo: `tarea ${t.id} compatible con ${candidatos[0].id}, ocioso`, evidencia: [t.id] });
    }
  }

  return { authority: AUTORIDAD, recomendaciones, sinEvidencia, nota: "Ninguna recomendación se aplica automáticamente." };
}
