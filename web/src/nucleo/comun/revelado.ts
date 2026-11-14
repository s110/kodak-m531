// Revelado rápido para la vista previa: el navegador no sabe abrir un DNG, así que se revela aquí.
// Media resolución (una celda de 2×2 del mosaico = un píxel), el mismo balance y la misma matriz que
// lleva el DNG, gamma sRGB y la orientación aplicada. No es el revelado final: sin interpolación ni
// curva de tono. Sin DOM.
import type { Matriz3, Vec3 } from './num.js';
import type { Cfa, Giro } from './dng.js';

/** Lo que hace falta para revelar un mosaico: lo mismo que lleva el DNG. */
export interface ParamsRevelado {
  readonly ancho: number;
  readonly alto: number;
  readonly cfa: Cfa;
  readonly negro: number;
  readonly blanco: number;
  readonly neutro: Vec3;
  /** cámara balanceada → sRGB lineal */
  readonly ccm: Matriz3;
}
export interface Vista {
  readonly rgba: Uint8ClampedArray<ArrayBuffer>;
  readonly ancho: number;
  readonly alto: number;
}
type Color = 'R' | 'G' | 'B';

/**
 * pix: Uint16Array del mosaico. p = { ancho, alto, cfa, negro, blanco, neutro, ccm } con ccm = cámara
 * balanceada → sRGB lineal. paso = celdas promediadas por lado (1 = media resolución); giro = cuartos
 * de vuelta a la izquierda. Devuelve { rgba: Uint8ClampedArray, ancho, alto }.
 */
export function revelar(pix: Uint16Array, p: ParamsRevelado, { paso = 1, giro = 0 }: { paso?: number; giro?: Giro } = {}): Vista {
  const w = p.ancho, ow = Math.floor(w / 2 / paso), oh = Math.floor(p.alto / 2 / paso);
  const pos: Record<Color, number[]> = { R: [], G: [], B: [] };
  [...p.cfa].forEach((c, i) => pos[c as Color].push((i >> 1) * w + (i & 1)));
  // un patrón Bayer tiene un R, un B y dos G
  const dr = pos.R[0]!, db = pos.B[0]!, dg1 = pos.G[0]!, dg2 = pos.G[1]!;
  const maxN = Math.max(...p.neutro);
  const escala = 1 / ((p.blanco - p.negro) * paso * paso);
  const gan = p.neutro.map(v => escala / (v / maxN));     // con el neutro a máximo 1, lo saturado queda blanco
  const [[m00, m01, m02], [m10, m11, m12], [m20, m21, m22]] = p.ccm;
  const gamma = new Uint8Array(4097);
  for (let i = 0; i <= 4096; i++) {
    const v = i / 4096;
    gamma[i] = Math.round(255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055));
  }
  const g = ((giro % 4) + 4) % 4;
  const W = g % 2 ? oh : ow, H = g % 2 ? ow : oh;
  const rgba = new Uint8ClampedArray(W * H * 4);
  const negro = p.negro;
  for (let y = 0; y < oh; y++) {
    for (let x = 0; x < ow; x++) {
      let r = 0, v = 0, b = 0;
      for (let cy = 0; cy < paso; cy++) {
        const o = 2 * (y * paso + cy) * w + 2 * x * paso;
        for (let cx = 0; cx < paso; cx++) {
          const q = o + 2 * cx;
          r += Math.max(pix[q + dr] - negro, 0);
          v += (Math.max(pix[q + dg1] - negro, 0) + Math.max(pix[q + dg2] - negro, 0)) / 2;
          b += Math.max(pix[q + db] - negro, 0);
        }
      }
      r = Math.min(r * gan[0], 1); v = Math.min(v * gan[1], 1); b = Math.min(b * gan[2], 1);
      const R = m00 * r + m01 * v + m02 * b, G = m10 * r + m11 * v + m12 * b, B = m20 * r + m21 * v + m22 * b;
      const X = g === 0 ? x : g === 1 ? y : g === 2 ? ow - 1 - x : oh - 1 - y;
      const Y = g === 0 ? y : g === 1 ? ow - 1 - x : g === 2 ? oh - 1 - y : x;
      const k = (Y * W + X) * 4;
      rgba[k] = gamma[R <= 0 ? 0 : R >= 1 ? 4096 : (R * 4096 + 0.5) | 0];
      rgba[k + 1] = gamma[G <= 0 ? 0 : G >= 1 ? 4096 : (G * 4096 + 0.5) | 0];
      rgba[k + 2] = gamma[B <= 0 ? 0 : B >= 1 ? 4096 : (B * 4096 + 0.5) | 0];
      rgba[k + 3] = 255;
    }
  }
  return { rgba, ancho: W, alto: H };
}
