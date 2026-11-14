// Contrato de un perfil de cámara. Sumar una cámara es escribir un módulo que cumpla `PerfilCamara` y
// añadirlo a CAMARAS en index.ts: el compilador comprueba el resto. Sin DOM.
import type { Bytes, Giro } from '../comun/dng.js';
import type { ParamsRevelado } from '../comun/revelado.js';

export type Balance = 'auto' | 'camara';
export type Rotar = 'no' | 'camara';
/** Los dos ajustes de la página. Un objeto de éstos no se modifica: se sustituye por otro. */
export interface Opciones {
  readonly balance: Balance;
  readonly rotar: Rotar;
}
export const BALANCES: readonly Balance[] = ['auto', 'camara'];
export const ROTARES: readonly Rotar[] = ['no', 'camara'];

/** Lo único que un perfil mira de un archivo para agruparlo: su nombre. */
export interface ArchivoNombrado {
  readonly name: string;
}

/** Los archivos de una foto, tal como los aparta el perfil. `A` es File en la página y una ruta en Node. */
export interface Disparo<A extends ArchivoNombrado = ArchivoNombrado> {
  /** Identidad de la foto dentro de la cámara: soltarla otra vez reconvierte la misma tarjeta. */
  readonly clave: string;
  readonly titulo: string;
  /** Nombre de salida sin extensión. Debe ser único entre todas las cámaras (es el nombre en el .zip). */
  readonly salida: string;
  /** Uno o más archivos RAW, el principal primero. */
  readonly campos: readonly A[];
  readonly jpg: A | null;
}
/** Un disparo ya asignado a su cámara; `clave` lleva delante el id del perfil. */
export interface DisparoDeCamara<A extends ArchivoNombrado = ArchivoNombrado> extends Disparo<A> {
  readonly camara: string;
}

export interface OpcionesDeConversion extends Partial<Opciones> {
  /** Nombres de los archivos RAW, sólo para informar. */
  readonly nombres?: readonly string[] | null;
}

/** Resultado de convertir un disparo. El DNG es cabecera + pixeles. `I` son los datos de análisis del perfil. */
export interface Conversion<I = unknown> {
  readonly cabecera: Bytes;
  /** Mosaico de 16 bits little-endian, fila a fila. */
  readonly pixeles: Bytes;
  /** Copia del JPG con la misma orientación que el DNG; null si falta o está roto. */
  readonly jpg: Bytes | null;
  readonly info: I;
  /** Descripción del formato del RAW, para la tarjeta. */
  readonly formato: string;
  /** De dónde salió el balance de blancos. */
  readonly balance: string;
  readonly giro: Giro;
  readonly revelado: ParamsRevelado;
}

export interface PerfilCamara<I = unknown> {
  readonly id: string;
  readonly nombre: string;
  readonly corto: string;
  /** Texto para la zona de soltar: qué archivos espera. */
  readonly ayuda: string;
  /** De una lista de archivos aparta los disparos de esta cámara; lo que no usa queda para otros perfiles. */
  agrupar<A extends ArchivoNombrado>(archivos: readonly A[]): Disparo<A>[];
  /** Convierte un disparo a partir del contenido de sus archivos. Lanza Error con el motivo si no se puede. */
  convertir(campos: readonly Uint8Array[], jpg: Uint8Array | null, opciones?: OpcionesDeConversion): Conversion<I>;
  /** Gira el JPG de la cámara (sólo su etiqueta EXIF, en el sitio) para que se vea como el DNG. */
  orientarJpg(jpg: Uint8Array, giro: Giro): boolean;
  /** ¿Es un rechazo con motivo para el usuario (y no un fallo del programa)? */
  esMotivo(e: unknown): boolean;
}
