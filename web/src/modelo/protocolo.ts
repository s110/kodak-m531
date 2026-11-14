// Mensajes entre la página y el Worker. Sin DOM: los archivos se describen por lo que se usa de ellos,
// así que valen los File y Blob del navegador y los objetos equivalentes de la prueba en Node.
//
// Cada petición lleva un `id` que la respuesta repite. Es la ficha de generación de la cola: una
// respuesta cuyo id no es el del trabajo en curso de ese Worker se descarta (ver pagina/cola.ts).
import type { Bytes, Giro } from '../nucleo/comun/dng.js';
import type { ParamsRevelado } from '../nucleo/comun/revelado.js';
import type { Opciones } from '../nucleo/camaras/perfil.js';

export interface BlobLegible {
  readonly size: number;
  arrayBuffer(): Promise<ArrayBuffer>;
  slice(inicio: number, fin: number): BlobLegible;
}
export interface ArchivoLegible extends BlobLegible {
  readonly name: string;
}

/** Vista previa ya revelada: RGBA de 8 bits, fila a fila. */
export interface VistaRgba {
  readonly rgba: ArrayBuffer;
  readonly ancho: number;
  readonly alto: number;
}

export interface TareaConvertir {
  readonly que: 'convertir';
  readonly camara: string;
  readonly campos: readonly ArchivoLegible[];
  readonly jpg: ArchivoLegible | null;
  readonly opciones: Opciones;
  /** Celdas del mosaico promediadas por lado en la miniatura. */
  readonly pasoVista: number;
}
export interface TareaRevelar {
  readonly que: 'revelar';
  readonly pixeles: BlobLegible;
  readonly revelado: ParamsRevelado;
  readonly giro: Giro;
  readonly paso: number;
}
export interface TareaCrc {
  readonly que: 'crc';
  readonly partes: readonly (Uint8Array | BlobLegible)[];
}
export type Tarea = TareaConvertir | TareaRevelar | TareaCrc;
export type Que = Tarea['que'];

/** Lo que devuelve cada tarea. */
export interface Datos {
  convertir: {
    readonly cabecera: Bytes;
    readonly pixeles: ArrayBuffer;
    readonly jpg: Bytes | null;
    readonly formato: string;
    readonly balance: string;
    readonly giro: Giro;
    readonly revelado: ParamsRevelado;
    readonly vista: VistaRgba;
    readonly ms: number;
  };
  revelar: VistaRgba;
  crc: { readonly crc: number };
}

export type Peticion = Tarea & { readonly id: number };
export type Respuesta =
  | { readonly id: number; readonly ok: true; readonly datos: Datos[Que] }
  | { readonly id: number; readonly ok: false; readonly error: string };

/** Texto de un error para enseñarlo: el final del mensaje, que es donde está el motivo. */
export function textoDeError(e: unknown): string {
  return String(e instanceof Error && e.message ? e.message : e).slice(-300);
}
