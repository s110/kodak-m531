// Aritmética que tiene que dar lo mismo que numpy/Python: redondeo al par, percentil lineal,
// autocorrelación por FFT y álgebra de 3×3. Sin DOM: corre igual en Node y en un Worker.

/** round() de Python para enteros: mitad al par. */
export function redondearPar(x) {
  const f = Math.floor(x), d = x - f;
  if (d < 0.5) return f;
  if (d > 0.5) return f + 1;
  return f % 2 === 0 ? f : f + 1;
}

/** round(x, n) de Python (para informar; un empate exacto en decimal no ocurre con datos reales). */
export function redondear(x, n) {
  return Number(x.toFixed(n));
}

/** _lerp de numpy (percentil 'linear'). */
function lerp(a, b, t) {
  const d = b - a;
  return t >= 0.5 ? b - d * (1 - t) : a + d * t;
}

/** np.percentile(v, q) con método lineal; `orden` es v ya ordenado ascendente (Float64Array). */
export function percentilOrdenado(orden, q) {
  const n = orden.length;
  const vi = (n - 1) * (q / 100);
  const i = Math.floor(vi);
  const sig = Math.min(i + 1, n - 1);
  return lerp(orden[i], orden[sig], vi - i);
}

/** np.percentile sobre un histograma de enteros (cuenta[v] = veces que aparece v). */
export function percentilHistograma(cuenta, total, q) {
  const vi = (total - 1) * (q / 100);
  const i = Math.floor(vi), sig = Math.min(i + 1, total - 1);
  let a = -1, b = -1, acum = 0;
  for (let v = 0; v < cuenta.length; v++) {
    acum += cuenta[v];
    if (a < 0 && acum > i) a = v;
    if (acum > sig) { b = v; break; }
  }
  return lerp(a, b, vi - i);
}

// ---------------------------------------------------------------- FFT
const _tablas = new Map();
function tabla(n) {
  let t = _tablas.get(n);
  if (!t) {
    const cos = new Float64Array(n / 2), sen = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) {
      const a = -2 * Math.PI * i / n;
      cos[i] = Math.cos(a); sen[i] = Math.sin(a);
    }
    const inv = new Uint32Array(n);
    const bits = Math.log2(n);
    for (let i = 0; i < n; i++) {
      let r = 0;
      for (let b = 0; b < bits; b++) r |= ((i >>> b) & 1) << (bits - 1 - b);
      inv[i] = r >>> 0;
    }
    t = { cos, sen, inv };
    _tablas.set(n, t);
  }
  return t;
}

/** FFT compleja en el sitio, base 2 (n potencia de 2). */
export function fft(re, im) {
  const n = re.length, { cos, sen, inv } = tabla(n);
  for (let i = 0; i < n; i++) {
    const j = inv[i];
    if (j > i) {
      let t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }
  for (let tam = 2; tam <= n; tam <<= 1) {
    const mitad = tam >> 1, paso = n / tam;
    for (let i = 0; i < n; i += tam) {
      for (let j = i, k = 0; j < i + mitad; j++, k += paso) {
        const c = cos[k], s = sen[k];
        const xr = re[j + mitad] * c - im[j + mitad] * s;
        const xi = re[j + mitad] * s + im[j + mitad] * c;
        re[j + mitad] = re[j] - xr; im[j + mitad] = im[j] - xi;
        re[j] += xr; im[j] += xi;
      }
    }
  }
}

/**
 * Autocorrelación normalizada de x (ya sin media) para los desfases 0..lagMax: lo que da
 * irfft(|rfft(x)|²)[:lagMax+1] / ac[0] en numpy. Con pocos desfases se suma directo; con muchos se
 * parte x en bloques de 65.536 muestras y se acumula conj(F(a))·F(b) con FFT de 131.072 (a = el bloque, b = el bloque
 * más los lagMax valores siguientes): mismo resultado matemático que una sola FFT de 4 M de puntos,
 * con 2 MB de memoria en vez de 100. La diferencia con numpy es de redondeo (~1e-13).
 */
export function autocorrelacion(x, lagMax) {
  const n = x.length;
  const ac = new Float64Array(lagMax + 1);
  if (lagMax <= 16) {
    for (let k = 0; k <= lagMax; k++) {
      let s = 0;
      for (let i = 0; i + k < n; i++) s += x[i] * x[i + k];
      ac[k] = s;
    }
  } else {
    const B = 65536;
    let nfft = 2 * B;
    while (nfft < B + lagMax + 1) nfft *= 2;
    // Una sola FFT por bloque: z = a + i·b. Como a y b son reales, sus transformadas se separan con
    // A[k] = (Z[k] + conj(Z[n−k]))/2 y B[k] = (Z[k] − conj(Z[n−k]))/(2i).
    const zr = new Float64Array(nfft), zi = new Float64Array(nfft);
    const sr = new Float64Array(nfft), si = new Float64Array(nfft);
    for (let ini = 0; ini < n; ini += B) {
      const finA = Math.min(ini + B, n), finB = Math.min(ini + B + lagMax, n);
      zr.fill(0); zi.fill(0);
      zr.set(x.subarray(ini, finA));
      zi.set(x.subarray(ini, finB));
      fft(zr, zi);
      for (let i = 0; i < nfft; i++) {
        const j = (nfft - i) & (nfft - 1);
        const ar = (zr[i] + zr[j]) / 2, ai = (zi[i] - zi[j]) / 2;
        const br = (zi[i] + zi[j]) / 2, bi = (zr[j] - zr[i]) / 2;
        sr[i] += ar * br + ai * bi;                 // conj(A)·B
        si[i] += ar * bi - ai * br;
      }
    }
    // inversa = conjugar, FFT directa, conjugar (y dividir por nfft, que se va al normalizar)
    for (let i = 0; i < nfft; i++) si[i] = -si[i];
    fft(sr, si);
    for (let k = 0; k <= lagMax; k++) ac[k] = sr[k];
  }
  const a0 = ac[0];
  for (let k = 0; k <= lagMax; k++) ac[k] /= a0;
  return ac;
}

// ---------------------------------------------------------------- 3×3
export function mul3(a, b) {
  const r = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) r[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j];
  return r;
}
export function mulVec3(a, v) {
  return a.map(f => f[0] * v[0] + f[1] * v[1] + f[2] * v[2]);
}
export function diag3(v) {
  return [[v[0], 0, 0], [0, v[1], 0], [0, 0, v[2]]];
}
export function inv3(m) {
  const [[a, b, c], [d, e, f], [g, h, i]] = m;
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  return [[A / det, -(b * i - c * h) / det, (b * f - c * e) / det],
          [B / det, (a * i - c * g) / det, -(a * f - c * d) / det],
          [C / det, -(a * h - b * g) / det, (a * e - b * d) / det]];
}

/** Mínimos cuadrados A·X ≈ B (A y B de n×3, por filas en Float64Array): devuelve X de 3×3.
 *  QR por Gram-Schmidt modificado, para no elevar al cuadrado el número de condición. */
export function minimosCuadrados3(A, B, n) {
  const q = [new Float64Array(n), new Float64Array(n), new Float64Array(n)];
  for (let i = 0; i < n; i++) { q[0][i] = A[3 * i]; q[1][i] = A[3 * i + 1]; q[2][i] = A[3 * i + 2]; }
  const R = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let j = 0; j < 3; j++) {
    for (let k = 0; k < j; k++) {
      let p = 0;
      for (let i = 0; i < n; i++) p += q[k][i] * q[j][i];
      R[k][j] = p;
      for (let i = 0; i < n; i++) q[j][i] -= p * q[k][i];
    }
    let s = 0;
    for (let i = 0; i < n; i++) s += q[j][i] * q[j][i];
    R[j][j] = Math.sqrt(s);
    for (let i = 0; i < n; i++) q[j][i] /= R[j][j];
  }
  const X = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let c = 0; c < 3; c++) {
    const y = [0, 0, 0];
    for (let j = 0; j < 3; j++) {
      let p = 0;
      for (let i = 0; i < n; i++) p += q[j][i] * B[3 * i + c];
      y[j] = p;
    }
    for (let j = 2; j >= 0; j--) {
      let v = y[j];
      for (let k = j + 1; k < 3; k++) v -= R[j][k] * X[k][c];
      X[j][c] = v / R[j][j];
    }
  }
  return X;
}

/** np.corrcoef(a, b)[0, 1]. */
export function correlacion(a, b) {
  const n = a.length;
  let ma = 0, mb = 0;
  for (let i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
  ma /= n; mb /= n;
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < n; i++) {
    const x = a[i] - ma, y = b[i] - mb;
    sab += x * y; saa += x * x; sbb += y * y;
  }
  return sab / Math.sqrt(saa * sbb);
}
