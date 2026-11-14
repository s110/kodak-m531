// Escritor de ZIP sin compresión ("store"). Los DNG no se comprimen casi nada y así el .zip se arma
// pegando los archivos tal cual, sin copiarlos en memoria. Sin DOM.
//
// Sin ZIP64: cada archivo y cada desplazamiento deben caber en 32 bits y un .zip lleva como mucho
// 65.535 archivos. Para no rozar esos topes (ni el de 4 GB por archivo de las tarjetas FAT32, ni los
// de memoria de los navegadores) una descarga grande se reparte en varios .zip de hasta LIMITE_ZIP.

export const LIMITE_ZIP = 1900 * 1024 * 1024;
const MAX_ENTRADAS = 65535;
const MAX_32 = 0xffffffff;

const TABLA = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

/** CRC-32 (el de ZIP). Se puede encadenar: crc32(b2, crc32(b1)). */
export function crc32(bytes, crc = 0) {
  let c = ~crc;
  for (let i = 0; i < bytes.length; i++) c = TABLA[(c ^ bytes[i]) & 255] ^ (c >>> 8);
  return ~c >>> 0;
}

function tamEntrada(e) {
  return 30 + 46 + 2 * new TextEncoder().encode(e.nombre).length + e.tam;
}

/**
 * Reparte las entradas ({ nombre, tam, … }) en grupos, cada uno para un .zip de hasta `limite` bytes,
 * sin separar las que comparten `junto` (el DNG y su JPG van en el mismo .zip).
 */
export function repartirZips(entradas, limite = LIMITE_ZIP) {
  limite = Math.min(limite, MAX_32 - 22);
  const lotes = [];
  for (const e of entradas) {                       // lotes indivisibles, en orden
    if (e.tam > MAX_32 - 200) throw new Error(`${e.nombre}: demasiado grande para un .zip (4 GB)`);
    const u = lotes[lotes.length - 1];
    if (u && e.junto !== undefined && u[0].junto === e.junto) u.push(e); else lotes.push([e]);
  }
  const grupos = [];
  let actual = [], tam = 22;
  for (const lote of lotes) {
    const t = lote.reduce((s, e) => s + tamEntrada(e), 0);
    if (actual.length && (tam + t > limite || actual.length + lote.length > MAX_ENTRADAS)) {
      grupos.push(actual); actual = []; tam = 22;
    }
    actual.push(...lote); tam += t;
  }
  if (actual.length) grupos.push(actual);
  return grupos;
}

/**
 * Partes de un .zip, en orden, para pasárselas a new Blob(partes) (o concatenarlas): cabeceras como
 * Uint8Array y, entre ellas, e.datos tal cual. entradas = [{ nombre, datos, tam, crc }].
 */
export function armarZip(entradas, fecha = new Date()) {
  if (entradas.length > MAX_ENTRADAS) throw new Error('demasiados archivos para un .zip');
  const txt = new TextEncoder();
  const hora = (fecha.getHours() << 11) | (fecha.getMinutes() << 5) | (fecha.getSeconds() >> 1);
  const dia = ((Math.max(fecha.getFullYear(), 1980) - 1980) << 9) | ((fecha.getMonth() + 1) << 5) | fecha.getDate();
  const partes = [], central = [];
  let pos = 0;
  for (const e of entradas) {
    const nombre = txt.encode(e.nombre);
    const loc = new Uint8Array(30 + nombre.length), dv = new DataView(loc.buffer);
    dv.setUint32(0, 0x04034b50, true); dv.setUint16(4, 20, true);
    dv.setUint16(6, 0x0800, true);                     // nombres en UTF-8
    dv.setUint16(8, 0, true); dv.setUint16(10, hora, true); dv.setUint16(12, dia, true);
    dv.setUint32(14, e.crc, true); dv.setUint32(18, e.tam, true); dv.setUint32(22, e.tam, true);
    dv.setUint16(26, nombre.length, true);
    loc.set(nombre, 30);
    const cen = new Uint8Array(46 + nombre.length), dc = new DataView(cen.buffer);
    dc.setUint32(0, 0x02014b50, true); dc.setUint16(4, 20, true); dc.setUint16(6, 20, true);
    dc.setUint16(8, 0x0800, true); dc.setUint16(12, hora, true); dc.setUint16(14, dia, true);
    dc.setUint32(16, e.crc, true); dc.setUint32(20, e.tam, true); dc.setUint32(24, e.tam, true);
    dc.setUint16(28, nombre.length, true); dc.setUint32(42, pos, true);
    cen.set(nombre, 46);
    partes.push(loc, e.datos);
    central.push(cen);
    pos += loc.length + e.tam;
    if (pos > MAX_32) throw new Error('el .zip pasa de 4 GB');
  }
  const tamCentral = central.reduce((s, c) => s + c.length, 0);
  if (pos + tamCentral > MAX_32) throw new Error('el .zip pasa de 4 GB');
  const fin = new Uint8Array(22), df = new DataView(fin.buffer);
  df.setUint32(0, 0x06054b50, true); df.setUint16(8, entradas.length, true); df.setUint16(10, entradas.length, true);
  df.setUint32(12, tamCentral, true); df.setUint32(16, pos, true);
  partes.push(...central, fin);
  return partes;
}
