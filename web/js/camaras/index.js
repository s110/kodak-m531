// Registro de cámaras. Cada perfil dice qué archivos son suyos (agrupar) y cómo se convierten.
// Para sumar una cámara: un módulo como m531.js y una línea aquí.
import m531 from './m531.js';

export const CAMARAS = [m531];
const porId = new Map(CAMARAS.map(c => [c.id, c]));

export function camara(id) {
  return porId.get(id);
}

/**
 * Reparte una tanda de archivos entre los perfiles, en orden: cada uno aparta los disparos que
 * reconoce y el resto sigue al siguiente. Devuelve { disparos: [{ camara, clave, titulo, salida,
 * campos, jpg }], ignorados } (ignorados no cuenta los archivos ocultos).
 */
export function repartir(archivos) {
  let resto = archivos.filter(f => !f.name.startsWith('.'));
  const disparos = [];
  for (const c of CAMARAS) {
    const usados = new Set();
    for (const d of c.agrupar(resto)) {
      disparos.push({ ...d, camara: c.id, clave: `${c.id}:${d.clave}` });
      d.campos.forEach(f => usados.add(f));
      if (d.jpg) usados.add(d.jpg);
    }
    resto = resto.filter(f => !usados.has(f));
  }
  return { disparos, ignorados: resto.length };
}
