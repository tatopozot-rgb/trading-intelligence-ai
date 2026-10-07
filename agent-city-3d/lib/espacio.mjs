// Diseño espacial de edificios: plantas, camas y estaciones de trabajo. Puro y determinista: mismo
// input, misma asignación siempre. La escena sólo coloca lo que este módulo decide.

export const ALTURA_PLANTA = 3.3; // separación vertical entre plantas, en unidades de mundo

// Edificios con dos plantas: los más altos (variedad visual de skyline) más los 5 edificios de
// trabajo reales (lib/life.mjs EDIFICIOS_TRABAJO), que necesitan la 2ª planta para tener capacidad
// real: con el tope de población (POBLACION_MAX=40 en life.mjs), el edificio de trabajo con más
// gente recibe 8 trabajadores (verificado con residentes(1000)); 2 plantas x 4 puestos = 8 cubre
// ese máximo exacto, así nadie comparte escritorio nunca, igual que las casas con litera.
export const EDIFICIOS_DOS_PLANTAS = new Set([
  "risk_tower", "command_center", "trading_floor",
  "quant_lab", "qa_facility", "engineering_lab", "market_intel",
]);
export function plantasDe(idEdificio) {
  return EDIFICIOS_DOS_PLANTAS.has(idEdificio) ? 2 : 1;
}

// Estaciones de trabajo (escritorio/pupitre) por planta: 4 puestos fijos por planta (ver comentario
// de EDIFICIOS_DOS_PLANTAS para el porqué de 4 x 2 plantas = 8). Exportadas para que la escena dibuje
// el mueble en el mismo punto exacto que decide la asignación.
export const ESTACIONES_BASE = [[-0.6, -0.6], [0.6, -0.6], [-0.6, 0.6], [0.6, 0.6]];
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

// Camas por casa: 4 posiciones de suelo; cada una además tiene litera (nivel 0 = abajo, 1 = arriba),
// así que una casa aloja 8 personas con una cama real y propia cada una, no sólo 4. Con más gente que
// literas, recién ahí se reparte por turno (ver asignarEspacios / tests).
export const CAMAS_BASE = [[-1.05, -1.05], [1.05, -1.05], [-1.05, 1.05], [1.05, 1.05]];
export const ALTURA_LITERA = 0.95; // separación vertical entre la cama de abajo y la de arriba
export const NIVELES_LITERA = 2;
export function camaPara(indiceEnCasa) {
  const nivel = Math.floor(indiceEnCasa / CAMAS_BASE.length) % NIVELES_LITERA;
  const [x, z] = CAMAS_BASE[indiceEnCasa % CAMAS_BASE.length];
  return [x, z, nivel];
}
export const CAPACIDAD_CASA = CAMAS_BASE.length * NIVELES_LITERA;

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
    return [r.id, { cama: { x: cama[0], z: cama[1], planta: 0, nivel: cama[2] }, estacion }];
  }));
}
