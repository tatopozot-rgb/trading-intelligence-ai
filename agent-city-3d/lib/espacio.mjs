// Diseño espacial de edificios: plantas, camas y estaciones de trabajo. Puro y determinista: mismo
// input, misma asignación siempre. La escena sólo coloca lo que este módulo decide.

export const ALTURA_PLANTA = 3.3; // separación vertical entre plantas, en unidades de mundo

// Edificios con dos plantas: los más altos, donde "subir" tiene sentido visual.
export const EDIFICIOS_DOS_PLANTAS = new Set(["risk_tower", "command_center", "trading_floor"]);
export function plantasDe(idEdificio) {
  return EDIFICIOS_DOS_PLANTAS.has(idEdificio) ? 2 : 1;
}

// Estaciones de trabajo (escritorio/pupitre) por planta: 2 puestos fijos por planta (no una sala
// vacía de 4 para 3 personas). Con sólo 2 por planta, el 3er compañero ya sube al piso de arriba.
// Exportadas para que la escena dibuje el mueble en el mismo punto exacto que decide la asignación.
export const ESTACIONES_BASE = [[-0.6, -0.6], [0.6, 0.6]];
export function estacionesDe(idEdificio) {
  const plantas = plantasDe(idEdificio);
  const lista = [];
  for (let planta = 0; planta < plantas; planta++) {
    for (const [x, z] of ESTACIONES_BASE) lista.push({ x, z, planta });
  }
  return lista;
}
// Asigna una estación estable a partir del índice de la persona dentro de ESE edificio (no global).
export function estacionPara(idEdificio, indiceEnEdificio) {
  const estaciones = estacionesDe(idEdificio);
  return estaciones[indiceEnEdificio % estaciones.length];
}

// Camas por casa: 4 posiciones fijas; cada habitante de la casa recibe la suya por índice estable.
export const CAMAS_BASE = [[-1.05, -1.05], [1.05, -1.05], [-1.05, 1.05], [1.05, 1.05]];
export function camaPara(indiceEnCasa) {
  return CAMAS_BASE[indiceEnCasa % CAMAS_BASE.length];
}
export const CAPACIDAD_CASA = CAMAS_BASE.length;

// Agrupa una lista de residentes por una clave (hogar o lugar de trabajo) y devuelve, para cada
// residente, su índice estable dentro de ese grupo (orden por id, siempre igual para la misma lista).
export function indicesPorGrupo(residentes, claveDeGrupo) {
  const grupos = new Map();
  const indices = new Map();
  for (const r of [...residentes].sort((a, b) => (a.id < b.id ? -1 : 1))) {
    const clave = claveDeGrupo(r);
    if (!clave) continue;
    const n = grupos.get(clave) || 0;
    indices.set(r.id, n);
    grupos.set(clave, n + 1);
  }
  return indices;
}

// Punto de llegada completo (planta + posición relativa al centro del edificio) para dormir o trabajar.
export function asignarEspacios(residentes) {
  const indiceEnCasa = indicesPorGrupo(residentes, (r) => r.home);
  const indiceEnTrabajo = indicesPorGrupo(residentes.filter((r) => r.workplace), (r) => r.workplace);
  return Object.fromEntries(residentes.map((r) => {
    const cama = camaPara(indiceEnCasa.get(r.id) || 0);
    const estacion = r.workplace ? estacionPara(r.workplace, indiceEnTrabajo.get(r.id) || 0) : null;
    return [r.id, { cama: { x: cama[0], z: cama[1], planta: 0 }, estacion }];
  }));
}
