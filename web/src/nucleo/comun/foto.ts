// Una foto ya convertida y lo que se le puede hacer sin reconvertir.
// Sin DOM: la página y la prueba E2E (en Node) usan estas mismas funciones.
//
// Una Foto no se modifica nunca: girar devuelve otra. Así, quien tenga una en la mano (una descarga o
// una exportación a medias) sigue viendo el DNG y el JPG con la misma orientación aunque la tarjeta
// gire mientras tanto.
import { ETIQUETA_GIRO, ponerOrientacion } from './dng.js';
import type { Bytes, Giro } from './dng.js';

/** El mosaico, que no cabe cómodo en memoria muchas veces: bytes (Node) o un Blob (página). */
export type Pixeles = Uint8Array | { readonly size: number };

export interface Foto<P extends Pixeles = Pixeles> {
  /** Nombre de salida sin extensión. */
  readonly salida: string;
  /** El DNG entero menos los píxeles; el archivo es cabecera + pixeles. */
  readonly cabecera: Bytes;
  readonly pixeles: P;
  /** Copia del JPG de la cámara con la misma orientación que el DNG, o null. */
  readonly jpg: Bytes | null;
  readonly giro: Giro;
}
export type Sentido = 'izq' | 'der';
/** Pone la orientación en el JPG de esa cámara (en el sitio). Es `orientarJpg` del perfil. */
export type OrientarJpg = (jpg: Uint8Array, giro: Giro) => boolean;

export interface ArchivoDeFoto<P extends Pixeles> {
  readonly nombre: string;
  /** Para `new Blob(partes)` o para concatenar. */
  readonly partes: (Bytes | P)[];
  readonly tam: number;
}

/**
 * La foto girada un cuarto de vuelta. Sólo cambia la etiqueta Orientation de la cabecera del DNG y la
 * del EXIF del JPG (dos bytes cada una, sin recomprimir), en copias: la foto original queda intacta.
 */
export function girarFoto<F extends Foto>(foto: F, sentido: Sentido, orientarJpg: OrientarJpg): F {
  const giro = ((foto.giro + (sentido === 'izq' ? 1 : 3)) % 4) as Giro;
  const cabecera = foto.cabecera.slice();
  ponerOrientacion(cabecera, ETIQUETA_GIRO[giro]);
  const jpg = foto.jpg ? foto.jpg.slice() : null;
  if (jpg) orientarJpg(jpg, giro);
  return { ...foto, cabecera, jpg, giro };
}

function tamPixeles(p: Pixeles): number {
  return 'size' in p ? p.size : p.length;
}

/** Archivos que salen de una foto: el DNG y, si lo hay, su JPG. */
export function archivosDeFoto<P extends Pixeles>(foto: Foto<P>): ArchivoDeFoto<P>[] {
  const out: ArchivoDeFoto<P>[] = [{ nombre: `${foto.salida}.DNG`, partes: [foto.cabecera, foto.pixeles],
    tam: foto.cabecera.length + tamPixeles(foto.pixeles) }];
  if (foto.jpg) out.push({ nombre: `${foto.salida}.JPG`, partes: [foto.jpg], tam: foto.jpg.length });
  return out;
}
