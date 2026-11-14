// Lo que hace el Worker con cada petición. Sin DOM ni API de Worker: obrero/obrero.ts sólo recibe el
// mensaje y devuelve lo que salga de aquí, y la prueba E2E llama a estas mismas funciones desde Node.
import { camara } from '../nucleo/camaras/index.js';
import { revelar } from '../nucleo/comun/revelado.js';
import { crc32 } from '../nucleo/comun/zip.js';
import type { BlobLegible, Datos, Que, Tarea, TareaConvertir, TareaCrc, TareaRevelar } from './protocolo.js';

/** Resultado de una tarea y los búferes que se transfieren (sin copiar) con él. */
export interface Hecho<K extends Que = Que> {
  readonly datos: Datos[K];
  readonly transferir: ArrayBuffer[];
}

const TRAMO_CRC = 8 << 20;
const bytes = async (f: BlobLegible) => new Uint8Array(await f.arrayBuffer());

/** Convierte un disparo: el DNG en dos partes (cabecera + píxeles) y la miniatura. */
async function convertir(m: TareaConvertir): Promise<Hecho<'convertir'>> {
  const t0 = performance.now();
  const perfil = camara(m.camara);
  const campos = await Promise.all(m.campos.map(bytes));
  const jpg = m.jpg && m.jpg.size ? await bytes(m.jpg) : null;
  const c = perfil.convertir(campos, jpg, { ...m.opciones, nombres: m.campos.map(f => f.name) });
  const pix = new Uint16Array(c.pixeles.buffer, c.pixeles.byteOffset, c.pixeles.byteLength / 2);
  const v = revelar(pix, c.revelado, { paso: m.pasoVista, giro: 0 });
  // Se transfiere el búfer entero: si los píxeles son sólo una parte de él, se copian a uno propio.
  const pixeles = c.pixeles.byteLength === c.pixeles.buffer.byteLength ? c.pixeles.buffer : c.pixeles.slice().buffer;
  return {
    datos: { cabecera: c.cabecera, pixeles, jpg: c.jpg, formato: c.formato, balance: c.balance, giro: c.giro, revelado: c.revelado,
      vista: { rgba: v.rgba.buffer, ancho: v.ancho, alto: v.alto }, ms: Math.round(performance.now() - t0) },
    transferir: [pixeles, v.rgba.buffer],
  };
}

/** Revela un DNG ya hecho (para el visor). */
async function revelarVista(m: TareaRevelar): Promise<Hecho<'revelar'>> {
  const pix = new Uint16Array(await m.pixeles.arrayBuffer());
  const v = revelar(pix, m.revelado, { paso: m.paso, giro: m.giro });
  return { datos: { rgba: v.rgba.buffer, ancho: v.ancho, alto: v.alto }, transferir: [v.rgba.buffer] };
}

/** CRC-32 de un archivo dado por partes, leyendo los Blob por tramos. */
async function crc(m: TareaCrc): Promise<Hecho<'crc'>> {
  let c = 0;
  for (const p of m.partes) {
    if (p instanceof Uint8Array) c = crc32(p, c);
    else for (let i = 0; i < p.size; i += TRAMO_CRC) c = crc32(await bytes(p.slice(i, i + TRAMO_CRC)), c);
  }
  return { datos: { crc: c }, transferir: [] };
}

export function ejecutar(t: Tarea): Promise<Hecho> {
  switch (t.que) {
    case 'convertir': return convertir(t);
    case 'revelar': return revelarVista(t);
    case 'crc': return crc(t);
    default: return nunca(t);
  }
}

/** Para el `default` de un switch que ya cubre todos los casos: si falta uno, no compila. */
export function nunca(x: never): never {
  throw new Error(`caso sin cubrir: ${JSON.stringify(x)}`);
}
