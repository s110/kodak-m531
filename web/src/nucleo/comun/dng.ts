// Escritor de DNG (TIFF con un IFD, mosaico de 16 bits sin comprimir) y etiqueta de orientación.
// Genérico: la cámara pone marca, modelo, patrón, niveles, neutro y matrices. Sin DOM.
import { redondearPar } from './num.js';
import type { Matriz3, Vec3 } from './num.js';

export type Cfa = 'RGGB' | 'BGGR' | 'GRBG' | 'GBRG';
/** Cuartos de vuelta a la izquierda respecto del sensor. */
export type Giro = 0 | 1 | 2 | 3;
/** Bytes con memoria propia (no compartida): se pueden transferir a otro hilo. */
export type Bytes = Uint8Array<ArrayBuffer>;

export interface ParamsDng {
  readonly ancho: number;
  readonly alto: number;
  readonly cfa: Cfa;
  readonly negro: number;
  readonly blanco: number;
  readonly neutro: Vec3;
  /** Valor de la etiqueta Orientation (1, 8, 3 o 6). */
  readonly orientacion: number;
  readonly marca: string;
  readonly modelo: string;
  readonly modeloUnico: string;
  readonly software: string;
  readonly cm1: Matriz3;
  readonly cm2: Matriz3;
  readonly fm: Matriz3;
  readonly iluminante1: number;
  readonly iluminante2: number;
  /** [x, y, ancho, alto] del recorte por omisión; sin él, la imagen entera. */
  readonly recorte?: readonly [number, number, number, number];
}
type Racional = [number, number];

const CFA: Readonly<Record<Cfa, readonly number[]>> = { RGGB: [0, 1, 1, 2], BGGR: [2, 1, 1, 0], GRBG: [1, 0, 2, 1], GBRG: [1, 2, 0, 1] };
/** Cuartos de vuelta a la izquierda respecto del sensor → etiqueta Orientation (TIFF/EXIF). */
export const ETIQUETA_GIRO: Readonly<Record<Giro, number>> = { 0: 1, 1: 8, 2: 3, 3: 6 };
const GIRO_DE_ETIQUETA: Readonly<Record<number, Giro>> = { 1: 0, 8: 1, 3: 2, 6: 3 };
/** Tipos de dato TIFF que se usan: BYTE, ASCII, SHORT, LONG, RATIONAL y SRATIONAL → bytes por valor. */
type TipoTiff = 1 | 2 | 3 | 4 | 5 | 10;
const TAM: Readonly<Record<TipoTiff, number>> = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 10: 8 };

function racional(x: number, d = 10000): Racional {
  return [redondearPar(x * d), d];
}

/**
 * Cabecera de un DNG: todo el archivo menos los píxeles, que van justo después, tal cual
 * (uint16 little-endian, fila a fila). El archivo es cabecera + píxeles.
 *
 * p = { ancho, alto, cfa, negro, blanco, neutro[3], orientacion, marca, modelo, modeloUnico, software,
 *       cm1, cm2, fm (3×3), iluminante1, iluminante2, recorte? }
 */
export function cabeceraDng(p: ParamsDng): Bytes {
  const { ancho: w, alto: h } = p;
  const nDatos = w * h * 2;
  const entradas: { t: number; tipo: TipoTiff; n: number; vb: Uint8Array }[] = [];
  const txt = new TextEncoder();
  // El tipo de `valores` va con `tipo`: texto para ASCII, pares para los racionales, números para el resto.
  function tag(t: number, tipo: 2, valores: string): void;
  function tag(t: number, tipo: 5 | 10, valores: readonly Racional[]): void;
  function tag(t: number, tipo: 1 | 3 | 4, valores: readonly number[]): void;
  function tag(t: number, tipo: TipoTiff, valores: string | readonly number[] | readonly Racional[]): void {
    let vb: Uint8Array, n: number;
    if (tipo === 2) {
      const s = txt.encode(valores as string);
      vb = new Uint8Array(s.length + 1); vb.set(s); n = vb.length;
    } else {
      n = valores.length;
      vb = new Uint8Array(n * TAM[tipo]);
      const dv = new DataView(vb.buffer);
      if (tipo === 5 || tipo === 10) {
        (valores as readonly Racional[]).forEach((v, i) => {
          if (tipo === 5) { dv.setUint32(8 * i, v[0], true); dv.setUint32(8 * i + 4, v[1], true); }
          else { dv.setInt32(8 * i, v[0], true); dv.setInt32(8 * i + 4, v[1], true); }
        });
      } else {
        (valores as readonly number[]).forEach((v, i) => {
          if (tipo === 1) dv.setUint8(i, v);
          else if (tipo === 3) dv.setUint16(2 * i, v, true);
          else dv.setUint32(4 * i, v, true);
        });
      }
    }
    entradas.push({ t, tipo, n, vb });
  }
  const [cx, cy, cw, ch] = p.recorte || [0, 0, w, h];
  const maxN = Math.max(...p.neutro);
  const neutro = p.neutro.map(v => v / maxN);              // AsShotNeutral: máximo 1
  const plano = (m: Matriz3): Racional[] => m.flat().map(v => racional(v));
  tag(254, 4, [0]); tag(256, 4, [w]); tag(257, 4, [h]); tag(258, 3, [16]); tag(259, 3, [1]);
  tag(262, 3, [32803]); tag(271, 2, p.marca); tag(272, 2, p.modelo);
  tag(273, 4, [0]); tag(274, 3, [p.orientacion]); tag(277, 3, [1]); tag(278, 4, [h]); tag(279, 4, [nDatos]);
  tag(284, 3, [1]); tag(305, 2, p.software);
  tag(33421, 3, [2, 2]); tag(33422, 1, CFA[p.cfa]);
  tag(50706, 1, [1, 4, 0, 0]); tag(50707, 1, [1, 1, 0, 0]); tag(50708, 2, p.modeloUnico);
  tag(50710, 1, [0, 1, 2]); tag(50711, 3, [1]);
  tag(50714, 4, [p.negro]); tag(50717, 4, [p.blanco]);
  tag(50719, 4, [cx, cy]); tag(50720, 4, [cw, ch]);
  tag(50721, 10, plano(p.cm1)); tag(50722, 10, plano(p.cm2));
  tag(50728, 5, neutro.map(v => racional(v, 1000000)));
  tag(50778, 3, [p.iluminante1]); tag(50779, 3, [p.iluminante2]);
  tag(50964, 10, plano(p.fm)); tag(50965, 10, plano(p.fm));
  entradas.sort((a, b) => a.t - b.t);
  const n = entradas.length;
  const ifdOff = 8;
  const extraOff = ifdOff + 2 + 12 * n + 4;
  let largos = 0;
  for (const e of entradas) if (e.vb.length > 4) largos += (e.vb.length + 1) & ~1;
  const datosOff = (extraOff + largos + 15) & ~15;
  const cab = new Uint8Array(datosOff);
  const dv = new DataView(cab.buffer);
  cab.set([0x49, 0x49, 0x2a, 0]); dv.setUint32(4, ifdOff, true);
  dv.setUint16(ifdOff, n, true);
  let pos = ifdOff + 2, extra = extraOff;
  for (const e of entradas) {
    dv.setUint16(pos, e.t, true); dv.setUint16(pos + 2, e.tipo, true); dv.setUint32(pos + 4, e.n, true);
    if (e.t === 273) dv.setUint32(pos + 8, datosOff, true);
    else if (e.vb.length <= 4) cab.set(e.vb, pos + 8);
    else {
      dv.setUint32(pos + 8, extra, true);
      cab.set(e.vb, extra);
      extra += (e.vb.length + 1) & ~1;
    }
    pos += 12;
  }
  return cab;
}

/** Los píxeles (Uint16Array) como bytes little-endian, sin copiar si la máquina ya lo es. */
export function bytesPixeles(img: Uint16Array<ArrayBuffer>): Bytes {
  const u8 = new Uint8Array(img.buffer, img.byteOffset, img.byteLength);
  if (new Uint8Array(new Uint16Array([1]).buffer)[0] === 1) return u8;
  const out = new Uint8Array(img.byteLength);
  for (let i = 0; i < img.length; i++) { out[2 * i] = img[i] & 255; out[2 * i + 1] = img[i] >> 8; }
  return out;
}

/**
 * Posición de los dos bytes de la etiqueta Orientation (0x0112) en un DNG/TIFF o en el EXIF de un JPG,
 * y el orden de bytes; null si el archivo no la trae. Mismo recorrido que poner_orientacion de Python.
 */
function buscarOrientacion(b: Uint8Array): { pos: number; le: boolean } | null {
  let base = 0;
  if (b.length < 4) return null;
  if (b[0] === 0xff && b[1] === 0xd8) {                 // JPEG: buscar el segmento APP1 "Exif"
    let p = 2;
    for (;;) {
      if (p + 10 > b.length || b[p] !== 0xff || b[p + 1] === 0xda) return null;
      if (b[p + 1] === 0xe1 && b[p + 4] === 0x45 && b[p + 5] === 0x78 && b[p + 6] === 0x69 && b[p + 7] === 0x66 &&
          b[p + 8] === 0 && b[p + 9] === 0) { base = p + 10; break; }
      p += 2 + ((b[p + 2] << 8) | b[p + 3]);
    }
  }
  if (base + 8 > b.length) return null;
  const le = b[base] === 0x49 && b[base + 1] === 0x49;
  if (!le && !(b[base] === 0x4d && b[base + 1] === 0x4d)) return null;
  const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const ifd = dv.getUint32(base + 4, le);
  if (base + ifd + 2 > b.length) return null;
  const n = dv.getUint16(base + ifd, le);
  for (let i = 0; i < n; i++) {
    const pos = base + ifd + 2 + 12 * i;
    if (pos + 12 > b.length) return null;
    if (dv.getUint16(pos, le) === 0x0112) return { pos: pos + 8, le };
  }
  return null;
}

/** Escribe la etiqueta Orientation en el sitio (dos bytes). false si el archivo no la trae. */
export function ponerOrientacion(bytes: Uint8Array, valor: number): boolean {
  const o = buscarOrientacion(bytes);
  if (!o) return false;
  new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).setUint16(o.pos, valor, o.le);
  return true;
}

/** Cuartos de vuelta a la izquierda que pide hoy la etiqueta Orientation (0 si no la hay). */
export function leerGiro(bytes: Uint8Array): Giro {
  const o = buscarOrientacion(bytes);
  if (!o) return 0;
  return GIRO_DE_ETIQUETA[new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint16(o.pos, o.le)] ?? 0;
}
