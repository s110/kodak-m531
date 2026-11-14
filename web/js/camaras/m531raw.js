// RAW de la Kodak EasyShare M531 → mosaico + datos del DNG. Port fiel de tools/m531raw.py: mismas
// funciones, mismos nombres y mismo orden de operaciones, para que el DNG salga idéntico al de Python.
// Sin DOM: corre en Node (tools/e2e_web.py lo compara con Python) y en el Worker de la página.
//
// Dónde puede diferir de numpy y cómo se evita:
//   * sumas y medias: los datos son enteros (o medios), así que las sumas son exactas en float64 en
//     cualquier orden; las medias salen idénticas.
//   * percentiles: misma fórmula que numpy ('linear', con su _lerp).
//   * autocorrelación: FFT propia; difiere de numpy en ~1e-13, muy por debajo del margen de las
//     decisiones (pico más alto, prominencia ≥ 30 %).
//   * JPG: decodificador propio que da los mismos píxeles que libjpeg/PIL (comun/jpeg.js).
import { autocorrelacion, correlacion, diag3, inv3, minimosCuadrados3, mul3, mulVec3, percentilHistograma,
  percentilOrdenado, redondear, redondearPar } from '../comun/num.js';
import { cabeceraJpeg, decodificarJpeg, makerNote } from '../comun/jpeg.js';
import { ETIQUETA_GIRO, ponerOrientacion } from '../comun/dng.js';

export const FORMATOS = [['u8', 8], ['p10_msb', 10], ['p10_lsb', 10], ['p12_msb', 12], ['p12_lsb', 12],
  ['p14_msb', 14], ['p14_lsb', 14], ['u16_le', 16], ['u16_be', 16]];
const BITS = Object.fromEntries(FORMATOS);

/** Error con el motivo para el usuario (el SystemExit de Python). */
export class Motivo extends Error {}

// ---------------------------------------------------------------- desempaquetado
/** Uint16Array con los primeros n píxeles (o todos los completos). */
export function desempaquetar(datos, packing, n = null) {
  const b = BITS[packing];
  const total = Math.floor(datos.length * 8 / b);
  n = n === null ? total : Math.min(n, total);
  const out = new Uint16Array(n);
  if (packing === 'u8') {
    for (let i = 0; i < n; i++) out[i] = datos[i];
  } else if (packing === 'u16_le') {
    for (let i = 0; i < n; i++) out[i] = datos[2 * i] | (datos[2 * i + 1] << 8);
  } else if (packing === 'u16_be') {
    for (let i = 0; i < n; i++) out[i] = (datos[2 * i] << 8) | datos[2 * i + 1];
  } else if (packing.endsWith('msb')) {
    let acc = 0, nb = 0, p = 0;
    for (let i = 0; i < n; i++) {
      while (nb < b) { acc = (acc << 8) | datos[p++]; nb += 8; }
      nb -= b;
      out[i] = acc >>> nb;
      acc &= (1 << nb) - 1;
    }
  } else {
    const mascara = (1 << b) - 1;
    let acc = 0, nb = 0, p = 0;
    for (let i = 0; i < n; i++) {
      while (nb < b) { acc |= datos[p++] << nb; nb += 8; }
      out[i] = acc & mascara;
      acc >>>= b; nb -= b;
    }
  }
  return out;
}

// ---------------------------------------------------------------- detección
function _autocorr(x, lagMax) {
  // x: Float64Array propio (se modifica). null si es constante.
  const n = x.length;
  let s = 0, igual = true;
  for (let i = 0; i < n; i++) { s += x[i]; if (x[i] !== x[0]) igual = false; }
  if (igual) return null;
  const m = s / n;
  for (let i = 0; i < n; i++) x[i] -= m;
  return autocorrelacion(x, lagMax);
}

function _prominencia(ac, l) {
  if (l - 12 < 0 || l + 13 > ac.length) return 0.0;
  const centro = Math.max(ac[l - 1], ac[l], ac[l + 1]);
  const entorno = [...ac.subarray(l - 12, l - 2), ...ac.subarray(l + 3, l + 13)].sort((a, b) => a - b);
  return centro - (entorno[9] + entorno[10]) / 2;
}

function _ancho_desde_ac(ac, anchoMin, anchoMax) {
  let L = -1, mejor = -Infinity;
  for (let l = anchoMin - anchoMin % 2; l <= Math.min(2 * anchoMax, ac.length - 13); l += 2) {
    if (ac[l] > mejor) { mejor = ac[l]; L = l; }
  }
  const pico = ac[L];
  let W = L;
  if ((L >> 1) >= anchoMin && _prominencia(ac, L >> 1) >= 0.3 * Math.max(_prominencia(ac, L), 1e-6)) W = L >> 1;
  if (W > anchoMax) W = L >> 1;
  return [pico, W];
}

/** Candidatos de formato, del mejor al peor. `solo` limita los empaquetados a probar (cada candidato
 *  se puntúa por separado, así que probar menos no cambia el puntaje de los que quedan). */
export function detectar_formato(datos, { anchoMin = 1500, anchoMax = 7000, muestra = 4_000_000, solo = null } = {}) {
  const res = [];
  for (const [packing, b] of FORMATOS) {
    if (solo && !solo(packing, b)) continue;
    const px = desempaquetar(datos, packing, muestra);
    if (px.length < 3 * 2 * anchoMax) continue;
    const ini = px.length >> 2;
    const nx = px.length - ini;
    const bruta = new Float64Array(Math.min(400_000, nx));
    for (let i = 0; i < bruta.length; i++) bruta[i] = px[ini + i];
    const acBruta = _autocorr(bruta, 4);
    const dif = new Float64Array(nx - 2);
    for (let i = 0; i < nx - 2; i++) dif[i] = px[ini + i + 2] - px[ini + i];
    const ac = _autocorr(dif, 2 * anchoMax + 16);
    if (ac === null || acBruta === null) continue;
    const [pico, ancho] = _ancho_desde_ac(ac, anchoMin, anchoMax);
    const vecino = acBruta[2];
    let maximo = 0;
    for (let i = ini; i < Math.min(ini + 200_000, px.length); i++) if (px[i] > maximo) maximo = px[i];
    const usado = 32 - Math.clz32(maximo);
    let puntaje = pico * Math.max(vecino, 0.0) ** 4;
    if (b === 16 && usado > 14) puntaje *= 0.05;
    if (b === 16) {
      const q = datos.length >> 2;
      const crudo = datos.subarray(q, q + 800_000);
      let s0 = 0, s1 = 0, n0 = 0, n1 = 0;
      for (let i = 0; i < crudo.length; i++) { if (i & 1) { s1 += crudo[i]; n1++; } else { s0 += crudo[i]; n0++; } }
      const [alto, bajo] = packing === 'u16_le' ? [s1 / n1, s0 / n0] : [s0 / n0, s1 / n1];
      if (bajo < 80 && alto > 0.3 * bajo) puntaje *= 0.05;
    }
    res.push({ packing, bits: b, ancho, pico: redondear(pico, 4), vecino: redondear(vecino, 4),
      puntaje: redondear(puntaje, 4), bits_usados: usado });
  }
  res.sort((x, y) => y.puntaje - x.puntaje);
  return res;
}

const CONFIANZA_ALTA = 0.15, CONFIANZA_MIN = 0.03, VENTAJA_MIN = 1.5;
export function confiable(cands) {
  if (!cands.length) return false;
  const p1 = cands[0].puntaje, p2 = cands.length > 1 ? cands[1].puntaje : 0.0;
  return p1 >= CONFIANZA_ALTA || (p1 >= CONFIANZA_MIN && p1 >= VENTAJA_MIN * Math.max(p2, 1e-9));
}

/** Imagen = { d: Uint16Array, h, w } (fila a fila). */
function a_imagen(datos, packing, ancho) {
  const px = desempaquetar(datos, packing);
  const alto = Math.floor(px.length / ancho);
  return { d: px.subarray(0, alto * ancho), h: alto, w: ancho };
}

function _suavidad(img) {
  const { d, h, w } = img;
  let s = 0;
  for (let i = 0, n = (h - 2) * w; i < n; i++) s += Math.abs(d[i] - d[i + 2 * w]);
  return s / ((h - 2) * w);
}

function combinar(campos, layout) {
  if (campos.length === 1) return [campos[0], 'unico'];
  const h = Math.min(campos[0].h, campos[1].h), w = Math.min(campos[0].w, campos[1].w);
  const fila = (c, y) => c.d.subarray(y * c.w, y * c.w + w);
  const [A, B] = campos;
  const opciones = {};
  const f = { d: new Uint16Array(2 * h * w), h: 2 * h, w };
  for (let y = 0; y < h; y++) { f.d.set(fila(A, y), 2 * y * w); f.d.set(fila(B, y), (2 * y + 1) * w); }
  opciones.filas = f;
  if (h % 2 === 0) {
    const p = { d: new Uint16Array(2 * h * w), h: 2 * h, w };
    for (let y = 0; y < h; y++) {
      const par = y >> 1, k = y & 1;
      p.d.set(fila(A, y), (4 * par + k) * w); p.d.set(fila(B, y), (4 * par + 2 + k) * w);
    }
    opciones.pares = p;
  }
  const ar = [], br = [];
  for (let y = 0; y < h; y += 16) for (let x = 0; x < w; x += 16) { ar.push(A.d[y * A.w + x]); br.push(B.d[y * B.w + x]); }
  const constante = v => v.every(x => x === v[0]);
  const parecidos = !constante(ar) && !constante(br) && correlacion(ar, br) > 0.97;
  if (!parecidos || layout === 'apilado') {
    const a = { d: new Uint16Array(2 * h * w), h: 2 * h, w };
    for (let y = 0; y < h; y++) { a.d.set(fila(A, y), y * w); a.d.set(fila(B, y), (h + y) * w); }
    opciones.apilado = a;
  }
  if (layout) {
    if (!(layout in opciones)) throw new Motivo(`disposición ${layout} imposible con campos de ${h} filas`);
    return [opciones[layout], layout];
  }
  let mejor = null, min = Infinity;
  for (const k of Object.keys(opciones)) {
    const s = _suavidad(opciones[k]);
    if (s < min) { min = s; mejor = k; }
  }
  return [opciones[mejor], mejor];
}

function detectar_cfa(img) {
  const { d, h, w } = img;
  const y0 = (h >> 3) & ~1, x0 = (w >> 3) & ~1;
  const ch = ((h - 2 * y0) >> 1) * 2, cw = ((w - 2 * x0) >> 1) * 2;
  const n = (ch / 2) * (cw / 2);
  const suma = [0, 0, 0, 0];
  let dPrin = 0, dSec = 0;
  for (let y = 0; y < ch; y += 2) {
    const o = (y0 + y) * w + x0;
    for (let x = 0; x < cw; x += 2) {
      const p00 = d[o + x], p01 = d[o + x + 1], p10 = d[o + w + x], p11 = d[o + w + x + 1];
      suma[0] += p00; suma[1] += p01; suma[2] += p10; suma[3] += p11;
      dPrin += Math.abs(p00 - p11); dSec += Math.abs(p01 - p10);
    }
  }
  const m = suma.map(s => s / n);
  const parecido = (ma, mb, dif) => Math.abs(ma - mb) / (ma + mb + 1e-9) + (dif / n) / (ma + mb + 1e-9);
  const d_principal = parecido(m[0], m[3], dPrin), d_secundaria = parecido(m[1], m[2], dSec);
  if (d_principal < d_secundaria) {
    return [m[1] < m[2] ? 'GRBG' : 'GBRG', { d_verde: d_principal, d_otra: d_secundaria }];
  }
  return [m[0] < m[3] ? 'RGGB' : 'BGGR', { d_verde: d_secundaria, d_otra: d_principal }];
}

/** Posiciones (y, x) de cada color en la celda de 2×2. */
function posiciones(cfa) {
  const pos = { R: [], G: [], B: [] };
  [...cfa].forEach((c, i) => pos[c].push([i >> 1, i & 1]));
  return pos;
}

function fraccion_quemada(img, negro, blanco) {
  const { d, w } = img, h2 = img.h >> 1, w2 = w >> 1;
  const tope = negro + (blanco - negro) * 0.97;
  let n = 0;
  for (let y = 0; y < h2; y++) {
    const o = 2 * y * w;
    for (let x = 0; x < w2; x++) {
      const i = o + 2 * x;
      if (Math.max(d[i], d[i + 1], d[i + w], d[i + w + 1]) >= tope) n++;
    }
  }
  return n / (h2 * w2);
}

/** Balance por foto: lo claro y menos cálido de la escena (ver el original en Python). */
function neutro_claros_frios(img, cfa, negro, blanco, claros = 85, frio = [70, 95]) {
  const { d, w } = img;
  const bh = img.h >> 4, bw = w >> 4;               // bloques de 8×8 celdas = 16×16 píxeles
  const pos = posiciones(cfa);
  const [ry, rx] = pos.R[0], [by, bx] = pos.B[0], [g1y, g1x] = pos.G[0], [g2y, g2x] = pos.G[1];
  const tope = (blanco - negro) * 0.97;
  const R = [], G = [], B = [];
  for (let j = 0; j < bh; j++) {
    for (let i = 0; i < bw; i++) {
      let sr = 0, sg = 0, sb = 0, quemado = false;
      for (let cy = 0; cy < 8; cy++) {
        const o = (16 * j + 2 * cy) * w + 16 * i;
        for (let cx = 0; cx < 8; cx++) {
          const p = o + 2 * cx;
          const r = d[p + ry * w + rx] - negro, b = d[p + by * w + bx] - negro;
          const g = ((d[p + g1y * w + g1x] - negro) + (d[p + g2y * w + g2x] - negro)) / 2;
          if (r >= tope || g >= tope || b >= tope) quemado = true;
          sr += r; sg += g; sb += b;
        }
      }
      if (!quemado && sr > 0 && sg > 0 && sb > 0) { R.push(sr / 64); G.push(sg / 64); B.push(sb / 64); }
    }
  }
  if (R.length < 1000) return null;
  const L = R.map((r, k) => r + G[k] + B[k]);
  const pL = percentilOrdenado(Float64Array.from(L).sort(), claros);
  const sel = [];
  for (let k = 0; k < L.length; k++) if (L[k] >= pL) sel.push(k);
  const t = sel.map(k => Math.log(B[k] / R[k]));
  const orden = Float64Array.from(t).sort();
  const lo = percentilOrdenado(orden, frio[0]), hi = percentilOrdenado(orden, frio[1]);
  let sr = 0, sg = 0, sb = 0, n = 0;
  sel.forEach((k, j) => { if (t[j] >= lo && t[j] <= hi) { sr += R[k]; sg += G[k]; sb += B[k]; n++; } });
  const m = [sr / n, sg / n, sb / n];
  return m.map(x => Math.min(Math.max(x / m[1], 0.05), 4.0));
}

function neutro_mundo_gris(img, cfa, negro, blanco) {
  const { d, h, w } = img;
  const tope = (blanco - negro) * 0.95;
  const suma = { R: 0, G: 0, B: 0 }, cuenta = { R: 0, G: 0, B: 0 };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const v = d[y * w + x] - negro;
      if (v > 0 && v < tope) { const c = cfa[(y & 1) * 2 + (x & 1)]; suma[c] += v; cuenta[c]++; }
    }
  }
  const media = c => (cuenta[c] ? suma[c] / cuenta[c] : 1.0);
  return ['R', 'G', 'B'].map(c => Math.min(Math.max(media(c) / media('G'), 0.05), 4.0));
}

function neutro_creible(neutro) {
  if (!neutro || Math.min(...neutro) <= 0) return false;
  const x = Math.log(neutro[0] / neutro[1]), y = Math.log(neutro[2] / neutro[1]);
  return LOCUS_LN_R[0] <= x && x <= LOCUS_LN_R[1] && Math.abs(y - (LOCUS_A + LOCUS_B * x)) <= LOCUS_TOL;
}

/** Ganancias R, G, B (÷256) del AWB de la cámara, del MakerNote del JPG hermano; null si no hay. */
export function awb_camara(jpg) {
  try {
    const mk = makerNote(cabeceraJpeg(jpg).exif);
    if (!mk || mk.length < 0x21ac) return null;
    const dv = new DataView(mk.buffer, mk.byteOffset, mk.byteLength);
    const g = [0, 4, 8].map(o => dv.getUint32(0x1318 + o, true));
    const g2 = [0, 4, 8].map(o => dv.getUint32(0x21a0 + o, true));
    if (g.some((v, i) => v !== g2[i]) || !(200 <= g[1] && g[1] <= 512 && g.every(v => 100 <= v && v <= 4096))) return null;
    return g;
  } catch (_) {
    return null;
  }
}

// ---------------------------------------------------------------- matrices del DNG
const _CCM_C713 = [[150592, -88384, 3328], [-27776, 143360, -50048], [3008, -52352, 114880]].map(f => f.map(v => v / 65536));
const _SRGB_A_XYZ = [[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]];
const _XYZ_D65 = mulVec3(_SRGB_A_XYZ, [1, 1, 1]);
const _XYZ_D50 = [0.9642, 1.0, 0.8249];
const _XYZ_A = [1.0985, 1.0, 0.3558];
const _BRADFORD = [[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]];
const NEUTRO_M531_D65 = [256 / 451, 1.0, 256 / 417];
const NEUTRO_M531_A = [1.0, 248 / 263, 248 / 828];

function _adaptacion(origen, destino) {
  const d = mulVec3(_BRADFORD, destino), o = mulVec3(_BRADFORD, origen);
  return mul3(mul3(inv3(_BRADFORD), diag3(d.map((v, i) => v / o[i]))), _BRADFORD);
}

/** ColorMatrix1 (iluminante A), ColorMatrix2 (D65) y ForwardMatrix del DNG. */
export function matrices_dng(ccm = null) {
  const bal_a_xyz65 = mul3(_SRGB_A_XYZ, ccm || _CCM_C713);
  const xyz65_a_bal = inv3(bal_a_xyz65);
  const cm_a = mul3(mul3(diag3(NEUTRO_M531_A), xyz65_a_bal), _adaptacion(_XYZ_A, _XYZ_D65));
  const cm_d65 = mul3(diag3(NEUTRO_M531_D65), xyz65_a_bal);
  const fm = mul3(_adaptacion(_XYZ_D65, _XYZ_D50), bal_a_xyz65);
  return [cm_a, cm_d65, fm];
}

/** Balance de la cámara: ajusta RAW (lineal) ↔ JPG hermano (sRGB linealizado). null si no alinea. */
function neutro_desde_jpg(jpg, img, cfa) {
  if (!jpg || img.h !== 3264 || img.w !== 4320) return null;
  let J;
  try {                                               // la cámara puede dejar el JPG vacío o truncado
    J = decodificarJpeg(jpg);
  } catch (_) {
    return null;
  }
  const lut = new Float64Array(256);
  for (let i = 0; i < 256; i++) { const s = i / 255; lut[i] = s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; }
  // RAW a media resolución, recortado a la zona del JPG y promediado en bloques de 8×8 celdas
  const { d, w } = img;
  const pos = posiciones(cfa);
  const [ry, rx] = pos.R[0], [by, bx] = pos.B[0], [g1y, g1x] = pos.G[0], [g2y, g2x] = pos.G[1];
  const BH = 201, BW = 268;                           // (3216/2)/8 × (4288/2)/8
  const A = new Float64Array(BH * BW * 3);
  for (let j = 0; j < BH; j++) for (let i = 0; i < BW; i++) {
    let sr = 0, sg = 0, sb = 0;
    for (let cy = 0; cy < 8; cy++) {
      const o = 2 * (12 + 8 * j + cy) * w + 2 * (8 + 8 * i);
      for (let cx = 0; cx < 8; cx++) {
        const p = o + 2 * cx;
        sr += d[p + ry * w + rx] / 1023; sb += d[p + by * w + bx] / 1023;
        sg += (d[p + g1y * w + g1x] / 1023 + d[p + g2y * w + g2x] / 1023) / 2;
      }
    }
    const k = (j * BW + i) * 3;
    A[k] = sr / 64; A[k + 1] = sg / 64; A[k + 2] = sb / 64;
  }
  let mejor = null;
  for (const rot of [0, -90, 90]) {
    // el JPG girado debe medir 3216 filas × 4288 columnas
    if (rot === 0 ? !(J.alto === 3216 && J.ancho === 4288) : !(J.ancho === 3216 && J.alto === 4288)) continue;
    // jj = medias de 2×2 del JPG lineal (ya girado); B = medias de 8×8 de jj
    const jw = J.ancho >> 1, jh = J.alto >> 1;
    const jj = new Float64Array(jw * jh * 3);
    for (let y = 0; y < jh; y++) for (let x = 0; x < jw; x++) {
      const o0 = (2 * y * J.ancho + 2 * x) * 3, o1 = o0 + J.ancho * 3, k = (y * jw + x) * 3;
      for (let c = 0; c < 3; c++) jj[k + c] = (lut[J.rgb[o0 + c]] + lut[J.rgb[o0 + 3 + c]] + lut[J.rgb[o1 + c]] + lut[J.rgb[o1 + 3 + c]]) / 4;
    }
    // (X, Y) de la imagen girada → (x, y) de jj. −90 = a la derecha (ROTATE_270 de PIL), 90 = a la izquierda.
    const origen = rot === 0 ? (X, Y) => Y * jw + X : rot === -90 ? (X, Y) => (jh - 1 - X) * jw + Y : (X, Y) => X * jw + (jw - 1 - Y);
    const B = new Float64Array(BH * BW * 3);
    for (let j = 0; j < BH; j++) for (let i = 0; i < BW; i++) {
      let s0 = 0, s1 = 0, s2 = 0;
      for (let cy = 0; cy < 8; cy++) for (let cx = 0; cx < 8; cx++) {
        const k = origen(8 * i + cx, 8 * j + cy) * 3;
        s0 += jj[k]; s1 += jj[k + 1]; s2 += jj[k + 2];
      }
      const k = (j * BW + i) * 3;
      B[k] = s0 / 64; B[k + 1] = s1 / 64; B[k + 2] = s2 / 64;
    }
    const ok = [];
    for (let k = 0; k < BH * BW; k++) {
      const a0 = A[3 * k], a1 = A[3 * k + 1], a2 = A[3 * k + 2];
      if (Math.max(a0, a1, a2) < 0.95 && Math.max(B[3 * k], B[3 * k + 1], B[3 * k + 2]) < 0.95 && Math.min(a0, a1, a2) > 0.002) ok.push(k);
    }
    if (ok.length < 500) continue;
    const Aok = new Float64Array(ok.length * 3), Bok = new Float64Array(ok.length * 3);
    ok.forEach((k, n) => { for (let c = 0; c < 3; c++) { Aok[3 * n + c] = A[3 * k + c]; Bok[3 * n + c] = B[3 * k + c]; } });
    const c = correlacion(ok.map(k => A[3 * k + 1]), ok.map(k => B[3 * k + 1]));
    if (mejor === null || c > mejor[0]) mejor = [c, Aok, Bok, ok.length];
  }
  if (mejor === null || mejor[0] < 0.9) return null;
  const X = minimosCuadrados3(mejor[1], mejor[2], mejor[3]);      // B ≈ A·X; M = Xᵀ
  const M = [0, 1, 2].map(i => [0, 1, 2].map(j => X[j][i]));
  const neutro = mulVec3(inv3(M), [1, 1, 1]);
  if (neutro.some(v => !(v > 0))) return null;
  return neutro.map(v => v / neutro[1]);
}

// ---------------------------------------------------------------- giro
export const GIROS = { no: 0, izq: 1, 180: 2, der: 3 };

/** Cuartos de vuelta a la izquierda que la cámara ya aplicó a los píxeles del JPG: 1 si está en vertical. */
export function giro_jpg(jpg) {
  try {
    const c = cabeceraJpeg(jpg);
    return c.alto > c.ancho ? 1 : 0;
  } catch (_) {
    return 0;
  }
}

function giro_pedido(rotar, jpg) {
  if (rotar === 'camara') return jpg ? giro_jpg(jpg) : 0;
  return GIROS[rotar];
}

/** Deja el JPG de la cámara mostrándose con `giro` cuartos a la izquierda respecto del sensor
 *  (descuenta el giro que la cámara ya aplicó a los píxeles). Cambia dos bytes, en el sitio. */
export function orientar_jpg(jpg, giro) {
  return ponerOrientacion(jpg, ETIQUETA_GIRO[(((giro - giro_jpg(jpg)) % 4) + 4) % 4]);
}

// ---------------------------------------------------------------- flujo
const PERFILES = {
  28_200_960: { packing: 'u16_le', ancho: 4320 },
  14_100_480: { packing: 'u8', ancho: 4320, decodificar: true },
  21_150_720: { bits: 12, ancho: 4320, blanco: 1023, negro: 0, balance_jpg: false, neutro: 'modo4', decodificar10: true },
  17_625_600: { bits: 10, ancho: 4320 },
};
export const TAMANOS_PERFIL = Object.keys(PERFILES).map(Number);
const CFA_M531 = 'GBRG';
const MAX_CODIGO_MODO4 = 1020;
const BLANCO_M4_LINEAL = 3950;
const NEUTRO_M531 = [0.7056, 1.0, 0.5292];
const NEUTRO_M531_MODO4 = [0.62, 1.0, 0.60];
const QUEMADO_MAX = 0.02;
const AWB_OMISION = [400, 256, 456];
const LOCUS_A = -0.9243, LOCUS_B = -0.8826;
const LOCUS_TOL = 0.20;
const LOCUS_LN_R = [-0.74, 0.33];
export const CCM_M531 = [[1.73412, -0.7057, -0.02842], [-0.27821, 1.68179, -0.40358], [-0.08057, -0.50968, 1.59025]];
const DECODE_M531 = Uint16Array.from([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 77, 78, 79, 80, 81, 82, 83, 85, 86, 87, 88, 90, 91, 92, 94, 95, 96, 98, 99, 100, 102, 103, 105, 106, 108, 109, 111, 113, 114, 116, 118, 119, 121, 123, 125, 126, 128, 130, 132, 134, 136, 138, 140, 142, 144, 146, 148, 150, 152, 154, 157, 159, 161, 164, 166, 168, 171, 173, 176, 178, 181, 183, 186, 189, 191, 194, 197, 200, 203, 206, 209, 212, 215, 218, 221, 224, 227, 231, 234, 237, 241, 244, 248, 251, 255, 259, 262, 266, 270, 274, 278, 282, 286, 290, 294, 298, 303, 307, 312, 316, 321, 325, 330, 335, 339, 344, 349, 354, 360, 365, 370, 375, 381, 386, 392, 397, 403, 409, 415, 421, 427, 433, 439, 446, 452, 459, 465, 472, 479, 486, 493, 500, 507, 514, 522, 529, 537, 545, 553, 560, 569, 577, 585, 594, 602, 611, 620, 629, 638, 647, 656, 666, 675, 685, 695, 705, 715, 725, 736, 746, 757, 768, 779, 790, 802, 813, 825, 837, 849, 861, 874, 886, 899, 912, 925, 939, 952, 966, 980, 994, 1008, 1023]);

function maximo(a) {
  let m = 0;
  for (let i = 0; i < a.length; i++) if (a[i] > m) m = a[i];
  return m;
}

/** campos: [Uint8Array] (uno o dos archivos de un disparo). Devuelve [img, info]. */
export function analizar(campos, { bits = null, packing = null, ancho = null, layout = null, cfa = null, invertir = false,
  nombres = null } = {}) {
  let datos = campos;
  const perfil = (packing === null && ancho === null && datos.length === 1 && PERFILES[datos[0].length]) || null;
  if (perfil) {
    ancho = perfil.ancho;
    packing = perfil.packing ?? null;
    if (packing === null) {     // perfil con bits conocidos pero orden de empaquetado por detectar
      const c = detectar_formato(datos[0], { solo: (_, b) => b === perfil.bits });
      packing = c.length ? c[0].packing : `p${perfil.bits}_msb`;
    }
  }
  const decodificar = Boolean(perfil && perfil.decodificar);
  let perfil_info = perfil || {};
  if (perfil && cfa === null) cfa = CFA_M531;
  if (invertir) datos = [...datos].reverse();
  let cands;
  if (packing === null) {
    cands = detectar_formato(datos[0]);
    if (bits) { const f = cands.filter(c => c.bits === bits); if (f.length) cands = f; }
    if (!cands.length) throw new Motivo('sin formato posible: archivo demasiado pequeño, truncado o constante (todos los bytes iguales)');
    const elegido = cands[0];
    if (!confiable(cands) && ancho === null) {
      throw new Motivo(`detección poco fiable (puntajes [${cands.slice(0, 2).map(c => c.puntaje).join(', ')}]): escena sin ` +
        'estructura (plano, oscuro, ruido). Pasar --packing y --width sacados de una toma con detalle.');
    }
    packing = elegido.packing;
    ancho = ancho || elegido.ancho;
  } else {
    cands = [];
    if (ancho === null) {
      const c = detectar_formato(datos[0], { solo: p => p === packing });
      if (!c.length) throw new Motivo(`no se pudo detectar el ancho para ${packing}; pasar --width`);
      ancho = c[0].ancho;
    }
  }
  let imgs = datos.map(d => a_imagen(d, packing, ancho));
  if (decodificar) for (const c of imgs) { const d = c.d; for (let i = 0; i < d.length; i++) d[i] = DECODE_M531[d[i]]; }
  const max_crudo = Math.max(...imgs.map(c => maximo(c.d)));
  const lineal12 = Boolean(perfil && perfil.decodificar10 && max_crudo > MAX_CODIGO_MODO4);
  if (lineal12) {
    perfil_info = { ...perfil, blanco: BLANCO_M4_LINEAL, negro: 0 };
  } else if (perfil && perfil.decodificar10) {
    // np.round(np.interp(c, arange(256)*4, DECODE)): tabla de 4096 entradas, redondeo al par
    const t = new Uint16Array(4096);
    for (let c = 0; c < 4096; c++) {
      if (c >= 1020) { t[c] = DECODE_M531[255]; continue; }
      const j = c >> 2, pend = (DECODE_M531[j + 1] - DECODE_M531[j]) / 4;
      t[c] = redondearPar(pend * (c - 4 * j) + DECODE_M531[j]);
    }
    for (const c of imgs) { const d = c.d; for (let i = 0; i < d.length; i++) d[i] = t[d[i]]; }
  }
  let [img, layout_usado] = combinar(imgs, layout);
  if (img.h % 2) img = { d: img.d.subarray(0, (img.h - 1) * img.w), h: img.h - 1, w: img.w };
  const [cfa_det, cfa_info] = detectar_cfa(img);
  const perfilPub = {};
  for (const k of ['blanco', 'negro', 'balance_jpg', 'neutro']) if (k in perfil_info) perfilPub[k] = perfil_info[k];
  const info = {
    archivos: nombres, tamanos: datos.map(d => d.length), packing, bits: BITS[packing], ancho, alto: img.h,
    layout: layout_usado, orden_campos: invertir ? 'invertido' : 'O, b', cfa: cfa || cfa_det, cfa_detectado: cfa_det,
    cfa_rb_provisional: cfa === null,
    cfa_metricas: { d_verde: redondear(cfa_info.d_verde, 5), d_otra: redondear(cfa_info.d_otra, 5) },
    candidatos: cands.slice(0, 5), decodificado: decodificar, max_crudo,
    modo4: lineal12 ? 'lineal12' : (perfil_info.decodificar10 ? 'curva10' : null),
    perfil_camara: Boolean(perfil), perfil: perfilPub,
  };
  return [img, info];
}

/** AsShotNeutral de la foto y de dónde salió (info.balance). Mismo orden que en Python. */
function elegir_balance(jpg, img, info, negro, blanco, balance = 'auto') {
  const pf = info.perfil || {};
  const cfa = info.cfa;
  const awb = jpg ? awb_camara(jpg) : null;
  info.awb_camara = awb;
  const n_awb = awb ? [awb[1] / awb[0], 1.0, awb[1] / awb[2]] : null;
  const awb_util = Boolean(awb && !awb.every((v, i) => v === AWB_OMISION[i]) && neutro_creible(n_awb));
  const modo4 = pf.neutro === 'modo4';
  const de_camara = Boolean(info.perfil_camara);
  if (balance === 'fijo') {
    info.balance = modo4 ? 'fijo_modo4' : 'fijo_m531';
    return modo4 ? NEUTRO_M531_MODO4 : NEUTRO_M531;
  }
  if (balance === 'camara' && awb && neutro_creible(n_awb)) {
    info.balance = 'awb_camara';
    return n_awb;
  }
  if (info.decodificado && (pf.balance_jpg ?? true)) {
    const neutro = neutro_desde_jpg(jpg, img, cfa);
    if (neutro) { info.balance = 'jpg'; return neutro; }
  }
  if (!de_camara) {
    info.balance = 'mundo_gris';
    return neutro_mundo_gris(img, cfa, negro, blanco);
  }
  const neutro = neutro_claros_frios(img, cfa, negro, blanco);
  info.quemado = redondear(fraccion_quemada(img, negro, blanco), 4);
  const descartado = () => (neutro === null ? null : neutro.map(x => redondear(x, 4)));
  if (info.modo4 === 'lineal12' && info.quemado > QUEMADO_MAX && awb_util) {
    info.parche_blanco_descartado = descartado();
    info.balance = 'awb_camara';
    return n_awb;
  }
  if (neutro_creible(neutro)) { info.balance = 'parche_blanco'; return neutro; }
  info.parche_blanco_descartado = descartado();
  if (awb_util) { info.balance = 'awb_camara'; return n_awb; }
  if (modo4) { info.balance = 'fijo_modo4'; return NEUTRO_M531_MODO4; }
  info.balance = 'mundo_gris';
  return neutro_mundo_gris(img, cfa, negro, blanco);
}

/**
 * Analiza uno o dos archivos RAW de un disparo y deja todo lo que hace falta para el DNG.
 * jpg = bytes del JPG hermano (o null). Devuelve { img: {d, h, w}, info, neutro }.
 * Lanza Motivo con el texto para el usuario si el archivo no se puede leer.
 */
export function convertir(campos, jpg, { balance = 'auto', rotar = 'no', black = null, white = null, ...resto } = {}) {
  if (jpg && !jpg.length) jpg = null;
  const [img, info] = analizar(campos, resto);
  const pf = info.perfil || {};
  let negro, blanco;
  if (info.decodificado) {
    negro = black ?? 0;                               // el firmware ya restó el negro
    blanco = white ?? 1023;
  } else if ('blanco' in pf) {
    negro = black ?? (pf.negro ?? 0);
    blanco = white ?? pf.blanco;
  } else {
    if (black !== null) negro = black;
    else {                                            // negro provisional: percentil bajo de la escena
      const cuenta = new Uint32Array(65536);
      for (let i = 0; i < img.d.length; i++) cuenta[img.d[i]]++;
      negro = Math.trunc(percentilHistograma(cuenta, img.d.length, 0.05));
    }
    if (white !== null) blanco = white;
    else if (info.bits === 16) blanco = 2 ** Math.max(32 - Math.clz32(maximo(img.d)), 12) - 1;
    else blanco = 2 ** info.bits - 1;
  }
  if (!(0 <= negro && negro < blanco)) throw new Motivo(`niveles inválidos: negro ${negro}, blanco ${blanco}`);
  info.niveles_provisionales = black === null || white === null;
  info.negro = negro; info.blanco = blanco;
  const neutro = elegir_balance(jpg, img, info, negro, blanco, balance);
  info.neutro = neutro.map(x => redondear(x, 4));
  info.matriz = 'm531';
  info.giro = giro_pedido(rotar, jpg);
  info.orientacion = ETIQUETA_GIRO[info.giro];
  return { img, info, neutro };
}
