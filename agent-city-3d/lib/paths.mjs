// Planificación de rutas en el plano (x, z): calle → puerta → interior, y salida inversa.
// Puro: sin three.js. La escena sólo interpola los puntos. Sin teletransporte salvo fallback documentado.

export const ESPACIO = 9;      // separación de la cuadrícula (igual que la escena)
export const CALLE_Z = 3.6;    // acera frente a la fachada
export const PUERTA_Z = 2.15;  // línea de la puerta (cara frontal del edificio)
export const CENTRO_Z = 0;     // interior: centro del edificio

// b: { pos:[i,j], world?:[x,z] }
export function posicionMundo(b) {
  return b.world ? { x: b.world[0], z: b.world[1] } : { x: b.pos[0] * ESPACIO, z: b.pos[1] * ESPACIO };
}
export const calle = (b) => { const p = posicionMundo(b); return { x: p.x, z: p.z + CALLE_Z }; };
export const puerta = (b) => { const p = posicionMundo(b); return { x: p.x, z: p.z + PUERTA_Z }; };
export const interior = (b) => { const p = posicionMundo(b); return { x: p.x, z: p.z + CENTRO_Z }; };

// Camino por la calle: primero recorre x a la altura actual, luego llega a la acera del destino (ángulo recto).
function camino(desde, b) {
  const c = calle(b);
  return [{ x: c.x, z: desde.z }, c];
}

// Planifica la ruta completa. opciones: { desde:{x,z}|null, origen:b|null (edificio donde está, si está dentro),
// destino:b, adentro:boolean }. Devuelve { puntos:[{x,z}], fallback:boolean }.
export function planRuta({ desde, origen = null, destino, adentro }) {
  // Fallback documentado: sin posición conocida, aparece en la acera del destino (no hay origen que recorrer).
  if (!desde) {
    const c = calle(destino);
    return { puntos: adentro ? [c, puerta(destino), interior(destino)] : [c], fallback: true };
  }
  const puntos = [{ x: desde.x, z: desde.z }];
  if (origen && origen.id === destino.id) {
    // Ya está en ese edificio: sólo entra al interior o sale por la puerta, sin dar la vuelta.
    if (adentro) return { puntos: [...puntos, interior(destino)], fallback: false };
    return { puntos: [...puntos, puerta(destino), calle(destino)], fallback: false };
  }
  if (origen) {
    // Sale por la puerta del edificio donde está, y sigue por la calle hasta el destino.
    puntos.push(puerta(origen), calle(origen));
    puntos.push(...camino(calle(origen), destino));
  } else {
    puntos.push(...camino(puntos[0], destino));
  }
  if (adentro) puntos.push(puerta(destino), interior(destino));
  return { puntos, fallback: false };
}

// Longitud total de la ruta (para elegir transporte y medir coste).
export function longitudRuta(puntos) {
  let total = 0;
  for (let i = 1; i < puntos.length; i++) {
    total += Math.hypot(puntos[i].x - puntos[i - 1].x, puntos[i].z - puntos[i - 1].z);
  }
  return total;
}
