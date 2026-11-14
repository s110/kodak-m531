// Decodificador de JPEG base (Huffman, 8 bits) y lectura de EXIF, sin DOM.
//
// Para qué uno propio: el balance de las fotos con JPG de referencia sale de sus píxeles, y los
// decodificadores de los navegadores no dan todos los mismos. Este sigue paso a paso lo que hace
// libjpeg (la que usa PIL en la versión de escritorio): IDCT entera "islow", ensanchado "fancy" del
// croma y la conversión YCbCr → RGB con sus tablas de 16 bits. Da los mismos píxeles en cualquier
// navegador y en Node.
//
// Alcance: un solo barrido intercalado, 1 o 3 componentes, croma a 1×1 con luma a 1×1, 2×1 o 2×2.
// Otra cosa (progresivo, CMYK…) lanza NO_ADMITIDO.

export const TRUNCADO = 'JPG truncado';
export const NO_ADMITIDO = 'JPG de un tipo no admitido';

const ZIGZAG = new Uint8Array([0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20,
  13, 6, 7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46,
  53, 60, 61, 54, 47, 55, 62, 63]);

/**
 * Recorre los segmentos hasta el inicio del barrido, con las mismas exigencias que Image.open de PIL:
 * lanza si falta la firma o si un segmento de la cabecera está cortado. Devuelve tamaño, tablas,
 * EXIF (segmento APP1 sin el prefijo "Exif\0\0") y dónde empiezan los datos comprimidos.
 */
export function cabeceraJpeg(b) {
  if (!b || b.length < 3 || b[0] !== 0xff || b[1] !== 0xd8 || b[2] !== 0xff) throw new Error('no es un JPEG');
  const r = { ancho: 0, alto: 0, exif: null, cuant: [], huff: {}, dri: 0, comps: null, sof: 0, barrido: null, posDatos: 0 };
  let p = 3, s = 0xff;
  const leer = () => { if (p >= b.length) throw new Error(TRUNCADO); return b[p++]; };
  for (;;) {
    if (s !== 0xff) { s = leer(); continue; }
    const m = leer();
    if (m >= 0xc0 && m <= 0xfe) {
      if (!(m >= 0xd0 && m <= 0xd9)) {
        if (p + 2 > b.length) throw new Error(TRUNCADO);
        const n = ((b[p] << 8) | b[p + 1]) - 2;
        p += 2;
        if (n < 0 || p + n > b.length) throw new Error(TRUNCADO);
        const seg = b.subarray(p, p + n);
        p += n;
        if (m === 0xe1 && !r.exif && n >= 6 && seg[0] === 0x45 && seg[1] === 0x78 && seg[2] === 0x69 && seg[3] === 0x66 && seg[4] === 0) {
          r.exif = seg.subarray(6);
        } else if ((m >= 0xc0 && m <= 0xc3) || (m >= 0xc5 && m <= 0xc7) || (m >= 0xc9 && m <= 0xcb) || (m >= 0xcd && m <= 0xcf)) {
          r.sof = m;
          r.precision = seg[0];
          r.alto = (seg[1] << 8) | seg[2];
          r.ancho = (seg[3] << 8) | seg[4];
          r.comps = [];
          for (let i = 0; i < seg[5]; i++) {
            r.comps.push({ id: seg[6 + 3 * i], h: seg[7 + 3 * i] >> 4, v: seg[7 + 3 * i] & 15, tq: seg[8 + 3 * i] });
          }
        } else if (m === 0xdb) {
          let q = 0;
          while (q < n) {
            const pq = seg[q] >> 4, tq = seg[q] & 15;
            q++;
            const t = new Int32Array(64);
            for (let i = 0; i < 64; i++) {
              t[ZIGZAG[i]] = pq ? (seg[q] << 8) | seg[q + 1] : seg[q];
              q += pq ? 2 : 1;
            }
            r.cuant[tq] = t;
          }
        } else if (m === 0xc4) {
          let q = 0;
          while (q + 17 <= n) {
            const clase = seg[q] >> 4, id = seg[q] & 15;
            const cuentas = seg.subarray(q + 1, q + 17);
            let total = 0;
            for (let i = 0; i < 16; i++) total += cuentas[i];
            r.huff[clase * 4 + id] = tablaHuffman(cuentas, seg.subarray(q + 17, q + 17 + total));
            q += 17 + total;
          }
        } else if (m === 0xdd) {
          r.dri = (seg[0] << 8) | seg[1];
        } else if (m === 0xda) {
          r.barrido = [];
          for (let i = 0; i < seg[0]; i++) r.barrido.push({ id: seg[1 + 2 * i], td: seg[2 + 2 * i] >> 4, ta: seg[2 + 2 * i] & 15 });
          r.posDatos = p;
          break;
        }
      }
      s = leer();
    } else if (m === 0xff) {
      s = 0xff;
    } else if (m === 0) {
      s = leer();
    } else {
      throw new Error('JPEG sin marcador');
    }
  }
  if (!r.comps) throw new Error('JPEG sin SOF');
  return r;
}

function tablaHuffman(cuentas, simbolos) {
  // rapida[prefijo de 9 bits] = (largo << 8) | símbolo, o 0 si el código es más largo
  const rapida = new Uint16Array(512);
  const maxcod = new Int32Array(18).fill(-1), valptr = new Int32Array(17), mincod = new Int32Array(17);
  let cod = 0, k = 0;
  for (let l = 1; l <= 16; l++) {
    valptr[l] = k; mincod[l] = cod;
    for (let i = 0; i < cuentas[l - 1]; i++, k++, cod++) {
      if (l <= 9) {
        const ini = cod << (9 - l);
        for (let j = 0; j < (1 << (9 - l)); j++) rapida[ini + j] = (l << 8) | simbolos[k];
      }
    }
    maxcod[l] = cuentas[l - 1] ? cod - 1 : -1;
    cod <<= 1;
  }
  maxcod[17] = 0x7fffffff;
  return { rapida, maxcod, valptr, mincod, simbolos: Uint8Array.from(simbolos) };
}

// IDCT entera lenta de libjpeg (jidctint.c): 13 bits de constante, 2 de precisión intermedia.
const F_0_298631336 = 2446, F_0_390180644 = 3196, F_0_541196100 = 4433, F_0_765366865 = 6270, F_0_899976223 = 7373,
  F_1_175875602 = 9633, F_1_501321110 = 12299, F_1_847759065 = 15137, F_1_961570560 = 16069, F_2_053119869 = 16819,
  F_2_562915447 = 20995, F_3_072711026 = 25172;
const _ws = new Int32Array(64);

function idct(coef, q, sal, base, ancho) {
  const ws = _ws;
  for (let c = 0; c < 8; c++) {
    if (coef[c + 8] === 0 && coef[c + 16] === 0 && coef[c + 24] === 0 && coef[c + 32] === 0 && coef[c + 40] === 0 &&
        coef[c + 48] === 0 && coef[c + 56] === 0) {
      const dc = (coef[c] * q[c]) << 2;
      ws[c] = ws[c + 8] = ws[c + 16] = ws[c + 24] = ws[c + 32] = ws[c + 40] = ws[c + 48] = ws[c + 56] = dc;
      continue;
    }
    let z2 = coef[c + 16] * q[c + 16], z3 = coef[c + 48] * q[c + 48];
    let z1 = (z2 + z3) * F_0_541196100;
    let tmp2 = z1 + z3 * -F_1_847759065;
    let tmp3 = z1 + z2 * F_0_765366865;
    z2 = coef[c] * q[c]; z3 = coef[c + 32] * q[c + 32];
    let tmp0 = (z2 + z3) << 13, tmp1 = (z2 - z3) << 13;
    const tmp10 = tmp0 + tmp3, tmp13 = tmp0 - tmp3, tmp11 = tmp1 + tmp2, tmp12 = tmp1 - tmp2;
    tmp0 = coef[c + 56] * q[c + 56]; tmp1 = coef[c + 40] * q[c + 40];
    tmp2 = coef[c + 24] * q[c + 24]; tmp3 = coef[c + 8] * q[c + 8];
    z1 = tmp0 + tmp3; z2 = tmp1 + tmp2; z3 = tmp0 + tmp2;
    let z4 = tmp1 + tmp3;
    const z5 = (z3 + z4) * F_1_175875602;
    tmp0 *= F_0_298631336; tmp1 *= F_2_053119869; tmp2 *= F_3_072711026; tmp3 *= F_1_501321110;
    z1 *= -F_0_899976223; z2 *= -F_2_562915447; z3 *= -F_1_961570560; z4 *= -F_0_390180644;
    z3 += z5; z4 += z5;
    tmp0 += z1 + z3; tmp1 += z2 + z4; tmp2 += z2 + z3; tmp3 += z1 + z4;
    ws[c] = (tmp10 + tmp3 + 1024) >> 11; ws[c + 56] = (tmp10 - tmp3 + 1024) >> 11;
    ws[c + 8] = (tmp11 + tmp2 + 1024) >> 11; ws[c + 48] = (tmp11 - tmp2 + 1024) >> 11;
    ws[c + 16] = (tmp12 + tmp1 + 1024) >> 11; ws[c + 40] = (tmp12 - tmp1 + 1024) >> 11;
    ws[c + 24] = (tmp13 + tmp0 + 1024) >> 11; ws[c + 32] = (tmp13 - tmp0 + 1024) >> 11;
  }
  for (let f = 0; f < 8; f++) {
    const w = f * 8, o = base + f * ancho;
    if (ws[w + 1] === 0 && ws[w + 2] === 0 && ws[w + 3] === 0 && ws[w + 4] === 0 && ws[w + 5] === 0 && ws[w + 6] === 0 &&
        ws[w + 7] === 0) {
      let v = ((ws[w] + 16) >> 5) + 128;
      v = v < 0 ? 0 : v > 255 ? 255 : v;
      sal[o] = sal[o + 1] = sal[o + 2] = sal[o + 3] = sal[o + 4] = sal[o + 5] = sal[o + 6] = sal[o + 7] = v;
      continue;
    }
    let z2 = ws[w + 2], z3 = ws[w + 6];
    let z1 = (z2 + z3) * F_0_541196100;
    let tmp2 = z1 + z3 * -F_1_847759065;
    let tmp3 = z1 + z2 * F_0_765366865;
    let tmp0 = (ws[w] + ws[w + 4]) << 13, tmp1 = (ws[w] - ws[w + 4]) << 13;
    const tmp10 = tmp0 + tmp3, tmp13 = tmp0 - tmp3, tmp11 = tmp1 + tmp2, tmp12 = tmp1 - tmp2;
    tmp0 = ws[w + 7]; tmp1 = ws[w + 5]; tmp2 = ws[w + 3]; tmp3 = ws[w + 1];
    z1 = tmp0 + tmp3; z2 = tmp1 + tmp2; z3 = tmp0 + tmp2;
    let z4 = tmp1 + tmp3;
    const z5 = (z3 + z4) * F_1_175875602;
    tmp0 *= F_0_298631336; tmp1 *= F_2_053119869; tmp2 *= F_3_072711026; tmp3 *= F_1_501321110;
    z1 *= -F_0_899976223; z2 *= -F_2_562915447; z3 *= -F_1_961570560; z4 *= -F_0_390180644;
    z3 += z5; z4 += z5;
    tmp0 += z1 + z3; tmp1 += z2 + z4; tmp2 += z2 + z3; tmp3 += z1 + z4;
    // Uint8ClampedArray no sirve aquí: libjpeg recorta con una tabla que da la vuelta en 10 bits,
    // pero con coeficientes válidos el valor ya cae en −128…383 y recortar a 0…255 es lo mismo.
    let v;
    v = ((tmp10 + tmp3 + 131072) >> 18) + 128; sal[o] = v < 0 ? 0 : v > 255 ? 255 : v;
    v = ((tmp10 - tmp3 + 131072) >> 18) + 128; sal[o + 7] = v < 0 ? 0 : v > 255 ? 255 : v;
    v = ((tmp11 + tmp2 + 131072) >> 18) + 128; sal[o + 1] = v < 0 ? 0 : v > 255 ? 255 : v;
    v = ((tmp11 - tmp2 + 131072) >> 18) + 128; sal[o + 6] = v < 0 ? 0 : v > 255 ? 255 : v;
    v = ((tmp12 + tmp1 + 131072) >> 18) + 128; sal[o + 2] = v < 0 ? 0 : v > 255 ? 255 : v;
    v = ((tmp12 - tmp1 + 131072) >> 18) + 128; sal[o + 5] = v < 0 ? 0 : v > 255 ? 255 : v;
    v = ((tmp13 + tmp0 + 131072) >> 18) + 128; sal[o + 3] = v < 0 ? 0 : v > 255 ? 255 : v;
    v = ((tmp13 - tmp0 + 131072) >> 18) + 128; sal[o + 4] = v < 0 ? 0 : v > 255 ? 255 : v;
  }
}

/**
 * Decodifica el JPEG entero. Con soloValidar no calcula píxeles: sólo recorre los datos comprimidos y
 * lanza TRUNCADO si se acaban antes de la última fila (lo mismo que hace fallar Image.load de PIL).
 * Devuelve { ancho, alto, rgb } con rgb = Uint8Array de alto·ancho·3.
 */
export function decodificarJpeg(b, { soloValidar = false } = {}) {
  const c = cabeceraJpeg(b);
  const nc = c.comps.length;
  if ((c.sof !== 0xc0 && c.sof !== 0xc1) || c.precision !== 8 || (nc !== 1 && nc !== 3) || c.barrido.length !== nc) {
    throw new Error(NO_ADMITIDO);
  }
  const hmax = Math.max(...c.comps.map(x => x.h)), vmax = Math.max(...c.comps.map(x => x.v));
  if (nc === 3 && (c.comps[1].h !== 1 || c.comps[1].v !== 1 || c.comps[2].h !== 1 || c.comps[2].v !== 1 ||
      !((hmax === 1 && vmax === 1) || (hmax === 2 && vmax === 1) || (hmax === 2 && vmax === 2)))) throw new Error(NO_ADMITIDO);
  if (nc === 1) { c.comps[0].h = 1; c.comps[0].v = 1; }
  const H = nc === 1 ? 1 : hmax, V = nc === 1 ? 1 : vmax;
  const mcuX = Math.ceil(c.ancho / (8 * H)), mcuY = Math.ceil(c.alto / (8 * V));
  const comps = c.comps.map((x, i) => {
    const s = c.barrido.find(y => y.id === x.id) || c.barrido[i];
    const dc = c.huff[s.td], ac = c.huff[4 + s.ta], q = c.cuant[x.tq];
    if (!dc || !ac || !q) throw new Error(NO_ADMITIDO);
    const ancho = mcuX * x.h * 8, alto = mcuY * x.v * 8;
    return { h: x.h, v: x.v, dc, ac, q, ancho, alto, pred: 0, plano: soloValidar ? null : new Uint8Array(ancho * alto) };
  });

  // ---- lector de bits, con las reglas de libjpeg: FF00 es un FF de datos; un marcador corta los
  // datos (siguen ceros); si el archivo se acaba sin marcador, pedir un bit más es TRUNCADO.
  let p = c.posDatos, buf = 0, cnt = 0, falsos = 0, marcador = 0;
  const fin = b.length;
  const llenar = () => {
    while (cnt <= 24) {
      let x = 0;
      if (marcador) { /* ceros */ } else if (p >= fin) { falsos += 8; } else {
        x = b[p];
        if (x === 0xff) {
          let q = p + 1;
          while (q < fin && b[q] === 0xff) q++;
          if (q >= fin) { p = fin; x = 0; falsos += 8; }
          else if (b[q] === 0) { p = q + 1; }
          else { marcador = b[q]; p = q + 1; x = 0; }
        } else p++;
      }
      buf |= x << (24 - cnt);
      cnt += 8;
    }
  };
  const gastar = n => {
    buf <<= n; cnt -= n;
    if (cnt < falsos) throw new Error(TRUNCADO);
  };
  const simbolo = t => {
    if (cnt < 16) llenar();
    const e = t.rapida[buf >>> 23];
    if (e) { gastar(e >> 8); return e & 255; }
    let l = 10, cod = buf >>> 22;
    while (cod > t.maxcod[l]) { l++; cod = buf >>> (32 - l); if (l > 16) { gastar(16); return 0; } }
    gastar(l);
    return t.simbolos[t.valptr[l] + cod - t.mincod[l]];
  };
  const recibir = s => {
    if (cnt < s) llenar();
    const v = buf >>> (32 - s);
    gastar(s);
    return v < (1 << (s - 1)) ? v - (1 << s) + 1 : v;
  };
  const coef = new Int32Array(64);
  const bloque = (co, bx, by) => {
    coef.fill(0);
    const t = simbolo(co.dc);
    if (t) co.pred += recibir(t);
    coef[0] = co.pred;
    for (let k = 1; k < 64;) {
      const rs = simbolo(co.ac), r = rs >> 4, s = rs & 15;
      if (!s) { if (r !== 15) break; k += 16; continue; }
      k += r;
      const v = recibir(s);
      if (k < 64) coef[ZIGZAG[k]] = v;
      k++;
    }
    if (!soloValidar) idct(coef, co.q, co.plano, by * 8 * co.ancho + bx * 8, co.ancho);
  };
  const total = mcuX * mcuY;
  let hastaReinicio = c.dri;
  for (let m = 0; m < total; m++) {
    if (c.dri && hastaReinicio === 0) {
      buf = 0; cnt = 0; falsos = 0;
      if (!marcador) {                              // buscar el siguiente marcador
        for (;;) {
          while (p < fin && b[p] !== 0xff) p++;
          while (p < fin && b[p] === 0xff) p++;
          if (p >= fin) throw new Error(TRUNCADO);
          if (b[p] !== 0) { marcador = b[p++]; break; }
          p++;
        }
      }
      if (marcador >= 0xd0 && marcador <= 0xd7) marcador = 0;
      for (const co of comps) co.pred = 0;
      hastaReinicio = c.dri;
    }
    const mx = m % mcuX, my = (m / mcuX) | 0;
    for (const co of comps) {
      for (let v = 0; v < co.v; v++) for (let h = 0; h < co.h; h++) bloque(co, mx * co.h + h, my * co.v + v);
    }
    hastaReinicio--;
  }
  if (soloValidar) return { ancho: c.ancho, alto: c.alto, rgb: null };
  return { ancho: c.ancho, alto: c.alto, rgb: aRgb(c, comps, H, V) };
}

function aRgb(c, comps, H, V) {
  const W = c.ancho, A = c.alto;
  const rgb = new Uint8Array(W * A * 3);
  const Y = comps[0];
  if (comps.length === 1) {
    for (let y = 0; y < A; y++) for (let x = 0; x < W; x++) {
      const v = Y.plano[y * Y.ancho + x], o = (y * W + x) * 3;
      rgb[o] = rgb[o + 1] = rgb[o + 2] = v;
    }
    return rgb;
  }
  // tablas de jdcolor.c (16 bits de escala)
  const crR = new Int32Array(256), cbB = new Int32Array(256), crG = new Int32Array(256), cbG = new Int32Array(256);
  for (let i = 0; i < 256; i++) {
    const x = i - 128;
    crR[i] = (91881 * x + 32768) >> 16;
    cbB[i] = (116130 * x + 32768) >> 16;
    crG[i] = -46802 * x;
    cbG[i] = -22554 * x + 32768;
  }
  const dw = Math.ceil(W / H), dh = Math.ceil(A / V);     // tamaño real del croma
  const filaCb = new Uint8Array(dw * 2 + 2), filaCr = new Uint8Array(dw * 2 + 2);
  // ensanchado "fancy" de jdsample.c para una fila de salida
  const ensanchar = (pl, anchoPl, fy, v, sal) => {
    if (H === 1) { for (let x = 0; x < dw; x++) sal[x] = pl[fy * anchoPl + x]; return; }
    if (V === 1) {                                         // h2v1: 3/4 del cercano + 1/4 del lejano
      const o = fy * anchoPl;
      if (dw === 1) { sal[0] = sal[1] = pl[o]; return; }
      sal[0] = pl[o]; sal[1] = (pl[o] * 3 + pl[o + 1] + 2) >> 2;
      for (let x = 1; x < dw - 1; x++) {
        const t = pl[o + x] * 3;
        sal[2 * x] = (t + pl[o + x - 1] + 1) >> 2;
        sal[2 * x + 1] = (t + pl[o + x + 1] + 2) >> 2;
      }
      sal[2 * dw - 2] = (pl[o + dw - 1] * 3 + pl[o + dw - 2] + 1) >> 2; sal[2 * dw - 1] = pl[o + dw - 1];
      return;
    }
    // h2v2: filtro triangular en las dos direcciones; arriba y abajo se repite la fila del borde
    const o0 = fy * anchoPl;
    const fv = v === 0 ? Math.max(fy - 1, 0) : Math.min(fy + 1, dh - 1);
    const o1 = fv * anchoPl;
    if (dw === 1) { const s = pl[o0] * 3 + pl[o1]; sal[0] = (s * 4 + 8) >> 4; sal[1] = (s * 4 + 7) >> 4; return; }
    let este = pl[o0] * 3 + pl[o1], sig = pl[o0 + 1] * 3 + pl[o1 + 1], ant;
    sal[0] = (este * 4 + 8) >> 4; sal[1] = (este * 3 + sig + 7) >> 4;
    ant = este; este = sig;
    for (let x = 2; x < dw; x++) {
      sig = pl[o0 + x] * 3 + pl[o1 + x];
      sal[2 * x - 2] = (este * 3 + ant + 8) >> 4; sal[2 * x - 1] = (este * 3 + sig + 7) >> 4;
      ant = este; este = sig;
    }
    sal[2 * dw - 2] = (este * 3 + ant + 8) >> 4; sal[2 * dw - 1] = (este * 4 + 7) >> 4;
  };
  const Cb = comps[1], Cr = comps[2];
  for (let y = 0; y < A; y++) {
    const fy = (y / V) | 0, v = y % V;
    ensanchar(Cb.plano, Cb.ancho, fy, v, filaCb);
    ensanchar(Cr.plano, Cr.ancho, fy, v, filaCr);
    const oy = y * Y.ancho;
    let o = y * W * 3;
    for (let x = 0; x < W; x++, o += 3) {
      const l = Y.plano[oy + x], cb = filaCb[x], cr = filaCr[x];
      let r = l + crR[cr], g = l + ((cbG[cb] + crG[cr]) >> 16), bl = l + cbB[cb];
      rgb[o] = r < 0 ? 0 : r > 255 ? 255 : r;
      rgb[o + 1] = g < 0 ? 0 : g > 255 ? 255 : g;
      rgb[o + 2] = bl < 0 ? 0 : bl > 255 ? 255 : bl;
    }
  }
  return rgb;
}

/** MakerNote (0x927c) del IFD EXIF, como lo da PIL: getexif().get_ifd(0x8769).get(0x927c). */
export function makerNote(exif) {
  if (!exif || exif.length < 8) return null;
  const le = exif[0] === 0x49 && exif[1] === 0x49;
  if (!le && !(exif[0] === 0x4d && exif[1] === 0x4d)) return null;
  const dv = new DataView(exif.buffer, exif.byteOffset, exif.byteLength);
  const buscar = (ifd, etiqueta) => {
    if (ifd + 2 > exif.length) return null;
    const n = dv.getUint16(ifd, le);
    for (let i = 0; i < n; i++) {
      const e = ifd + 2 + 12 * i;
      if (e + 12 > exif.length) return null;
      if (dv.getUint16(e, le) === etiqueta) return { tipo: dv.getUint16(e + 2, le), n: dv.getUint32(e + 4, le), pos: e + 8 };
    }
    return null;
  };
  const sub = buscar(dv.getUint32(4, le), 0x8769);
  if (!sub) return null;
  const mk = buscar(dv.getUint32(sub.pos, le), 0x927c);
  if (!mk) return null;
  const ini = mk.n <= 4 ? mk.pos : dv.getUint32(mk.pos, le);
  if (ini + mk.n > exif.length) return null;
  return exif.subarray(ini, ini + mk.n);
}
