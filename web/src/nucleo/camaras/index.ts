// Registro de cámaras. Cada perfil dice qué archivos son suyos (agrupar) y cómo se convierten.
// Para sumar una cámara: un módulo que cumpla PerfilCamara (perfil.ts) y una línea aquí.
import m531 from './m531.js';
import type { ArchivoNombrado, DisparoDeCamara, PerfilCamara } from './perfil.js';

export const CAMARAS: readonly PerfilCamara[] = [m531];
const porId = new Map(CAMARAS.map(c => [c.id, c]));

export function camara(id: string): PerfilCamara {
  const c = porId.get(id);
  if (!c) throw new Error(`cámara desconocida: ${id}`);
  return c;
}

/**
 * Reparte una tanda de archivos entre los perfiles, en orden: cada uno aparta los disparos que
 * reconoce y el resto sigue al siguiente. `ignorados` no cuenta los archivos ocultos.
 */
export function repartir<A extends ArchivoNombrado>(archivos: readonly A[]): { disparos: DisparoDeCamara<A>[]; ignorados: number } {
  let resto = archivos.filter(f => !f.name.startsWith('.'));
  const disparos: DisparoDeCamara<A>[] = [];
  for (const c of CAMARAS) {
    const usados = new Set<A>();
    for (const d of c.agrupar(resto)) {
      disparos.push({ ...d, camara: c.id, clave: `${c.id}:${d.clave}` });
      d.campos.forEach(f => usados.add(f));
      if (d.jpg) usados.add(d.jpg);
    }
    resto = resto.filter(f => !usados.has(f));
  }
  return { disparos, ignorados: resto.length };
}
