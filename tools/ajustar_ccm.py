#!/usr/bin/env python3
"""Ajuste y validación de la matriz de color de la M531 con pares RAW/JPG reales (dump/, fuera del repo).

uso:  ajustar_ccm.py [-o firmware/stock/ccm_ajustada_v2.json]

Datos: fotos de modo 0 (RAW de 8 bits decodificado + JPG normal del mismo disparo): 1970, 1971, 1978,
1979, 1980. Los RAW de modo 4 no entran: su JPG sale rosado y su par de modo 0 es otro disparo a pulso
(no alinea píxel a píxel).

Modelo por foto:  JPG_lineal = T( M · (RAW / neutro_AWB) )
  * neutro_AWB: ganancias del AWB de la cámara en el MakerNote (independientes del ajuste);
  * M: 3×3, filas que suman 1 (el neutro se queda neutro);
  * T: curva de tono monótona por foto, común a los tres canales (exposición + curva del JPG). Es un
    parámetro de estorbo: se estima igual para cada matriz candidata, también en la foto retenida.
Ajuste: bloques de 32×32 px del JPG, sin bloques saturados ni oscuros; mínimos cuadrados con pesos de
Huber, alternando M y T. Sin regularización: un ridge hacia la identidad se probó y empeora (ver RIDGE).

Validación: se retiene una escena entera (no un archivo: 1978, 1979 y 1980 son el mismo macropad) y se
mide ΔE2000 entre el JPG de la cámara y la predicción, para la matriz actual, la de la C713 y la nueva.
Todo es determinista: sin azar, mismos números en cada corrida.
"""
import argparse
import json
import os
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import m531raw as mr  # noqa: E402

FOTOS = [  # (carpeta, número, escena, luz)
    ('raw2', 1970, 'interior_1970', 'ambiente'), ('raw2', 1971, 'interior_1971', 'ambiente'),
    ('raw5', 1978, 'macropad', 'flash'), ('raw5', 1979, 'macropad', 'flash'),
    ('raw5', 1980, 'macropad', 'ambiente'),
]
CCM_ANTERIOR = np.array([[1.43013, -0.34631, -0.08382], [-0.2075, 1.54443, -0.33693],
                         [0.22245, -1.20159, 1.97913]])  # ajuste de 1970/1971 (commit 72f9da3)
RIDGE = 0.0   # tirar hacia la identidad empeora la foto retenida (0,005 → 3,21; 0,02 → 3,51; 0,1 → 4,24 de ΔE00)


# ---------------------------------------------------------------- color
def _lin_a_lab(rgb):
    xyz = np.clip(rgb, 0, None) @ mr._SRGB_A_XYZ.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def delta_e2000(l1, l2):
    L1, a1, b1 = l1.T
    L2, a2, b2 = l2.T
    C = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    G = 0.5 * (1 - np.sqrt(C ** 7 / (C ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1, C2 = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1, h2 = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dL, dC = L2 - L1, C2 - C1
    dh = h2 - h1
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1 * C2 == 0, 0, dh)
    dH = 2 * np.sqrt(C1 * C2) * np.sin(np.radians(dh) / 2)
    Lm, Cm = (L1 + L2) / 2, (C1 + C2) / 2
    hs = h1 + h2
    hm = np.where(np.abs(h1 - h2) > 180, np.where(hs < 360, hs + 360, hs - 360), hs) / 2
    hm = np.where(C1 * C2 == 0, hs, hm)
    T = (1 - 0.17 * np.cos(np.radians(hm - 30)) + 0.24 * np.cos(np.radians(2 * hm))
         + 0.32 * np.cos(np.radians(3 * hm + 6)) - 0.20 * np.cos(np.radians(4 * hm - 63)))
    SL = 1 + 0.015 * (Lm - 50) ** 2 / np.sqrt(20 + (Lm - 50) ** 2)
    SC, SH = 1 + 0.045 * Cm, 1 + 0.015 * Cm * T
    RC = 2 * np.sqrt(Cm ** 7 / (Cm ** 7 + 25.0 ** 7))
    RT = -np.sin(np.radians(60 * np.exp(-((hm - 275) / 25) ** 2))) * RC
    return np.sqrt((dL / SL) ** 2 + (dC / SC) ** 2 + (dH / SH) ** 2 + RT * (dC / SC) * (dH / SH))


# ---------------------------------------------------------------- datos
def cargar(carpeta, num):
    """Bloques alineados (cámara balanceada, JPG lineal) de una foto de modo 0."""
    from PIL import Image
    raw = os.path.join(RAIZ, 'dump', carpeta, f'101O{num}.RAW')
    jpg = os.path.join(RAIZ, 'dump', carpeta, f'101_{num}.JPG')
    img, info = mr.analizar([raw])
    assert info['decodificado'] and info['cfa'] == 'GBRG', info
    g = mr.awb_camara(raw)
    assert g, f'sin AWB en el MakerNote de {jpg}'
    neutro = np.array([g[1] / g[0], 1.0, g[1] / g[2]])
    pos = {c: [(i // 2, i % 2) for i, ch in enumerate(info['cfa']) if ch == c] for c in 'RGB'}
    a = img.astype(np.float64) / 1023
    cam = np.dstack([np.mean([a[y::2, x::2] for y, x in pos[c]], axis=0) for c in 'RGB'])

    def bloque(x, k):
        h, w = x.shape[0] // k * k, x.shape[1] // k * k
        return x[:h, :w].reshape(h // k, k, w // k, k, -1).mean(axis=(1, 3))
    mejor = None
    for rot in (-90, 90, 0):
        s = np.asarray(Image.open(jpg).convert('RGB').rotate(rot, expand=True)).astype(np.float64) / 255
        if s.shape[:2] != (3216, 4288):
            continue
        lin = np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)
        jj = bloque(lin, 2)
        rr = cam[12:12 + jj.shape[0], 8:8 + jj.shape[1]]
        A, B = bloque(rr, 8).reshape(-1, 3), bloque(jj, 8).reshape(-1, 3)
        # desviación dentro del bloque: descarta bordes (desalineación subpíxel, nitidez del JPG)
        sd = np.sqrt(np.maximum(bloque(jj ** 2, 8).reshape(-1, 3) - B ** 2, 0)).max(1)
        c = np.corrcoef(A[:, 1], B[:, 1])[0, 1]
        if mejor is None or c > mejor[0]:
            mejor = (c, A, B, sd, rot)
    c, A, B, sd, rot = mejor
    assert c > 0.9, f'{num}: el JPG no alinea con el RAW (corr {c:.3f})'
    ok = (A.max(1) < 0.90) & (B.max(1) < 0.90) & (A.min(1) > 0.004) & (B.min(1) > 0.002)
    ok &= sd < np.percentile(sd[ok], 80)
    return dict(num=num, cam=A[ok] / neutro, jpg=B[ok], neutro=neutro, corr=float(c), rot=rot,
                bloques=int(ok.sum()))


# ---------------------------------------------------------------- modelo
def curva_tono(pred, obj, nodos=48):
    """T monótona: mediana del JPG lineal por cuantil de la predicción (los 3 canales juntos)."""
    p, o = pred.ravel(), obj.ravel()
    orden = np.argsort(p, kind='stable')
    p, o = p[orden], o[orden]
    cortes = np.linspace(0, len(p), nodos + 1).astype(int)
    xs = np.array([np.median(p[a:b]) for a, b in zip(cortes[:-1], cortes[1:])])
    ys = np.maximum.accumulate([np.median(o[a:b]) for a, b in zip(cortes[:-1], cortes[1:])])
    xs = xs + np.arange(nodos) * 1e-12   # estrictamente creciente
    ys = ys + np.arange(nodos) * 1e-9
    return xs, ys


def aplicar(M, foto):
    """Predicción del JPG lineal de una foto con la matriz M (T estimada en la propia foto)."""
    pred = foto['cam'] @ M.T
    xs, ys = curva_tono(pred, foto['jpg'])
    return np.interp(pred, xs, ys), (xs, ys)


def ajustar(fotos, M0, iteraciones=12):
    M = M0.copy()
    for _ in range(iteraciones):
        X, Y, W = [], [], []
        for f in fotos:
            pred = f['cam'] @ M.T
            xs, ys = curva_tono(pred, f['jpg'])
            # objetivo en luz de escena: T⁻¹(JPG); peso = pendiente local de T⁻¹ acotada (las sombras
            # y las altas luces comprimidas pesan menos) y cada foto pesa lo mismo
            obj = np.interp(f['jpg'], ys, xs)
            X.append(f['cam']); Y.append(obj)
            W.append(np.full(len(obj), 1.0 / len(obj)))
        X, Y, W = np.vstack(X), np.vstack(Y), np.concatenate(W)
        Mn = np.empty((3, 3))
        for i in range(3):
            j = [k for k in range(3) if k != i]
            # fila i = e_i + a·(c_j0 − c_i) + b·(c_j1 − c_i): suma 1 por construcción
            D = np.stack([X[:, j[0]] - X[:, i], X[:, j[1]] - X[:, i]], 1)
            t = Y[:, i] - X[:, i]
            w = W.copy()
            for _ in range(8):  # Huber
                A = D * w[:, None]
                ab = np.linalg.solve(D.T @ A + RIDGE * W.sum() * np.mean(X ** 2) * np.eye(2), A.T @ t)
                r = t - D @ ab
                s = 1.4826 * np.median(np.abs(r)) + 1e-9
                w = W * np.minimum(1.0, 1.345 * s / np.maximum(np.abs(r), 1e-12))
            Mn[i, i] = 1 - ab.sum()
            Mn[i, j] = ab
        if np.abs(Mn - M).max() < 1e-5:
            M = Mn
            break
        M = Mn
    return M


def error(M, foto):
    pred, _ = aplicar(M, foto)
    a, b = _lin_a_lab(pred), _lin_a_lab(foto['jpg'])
    de = delta_e2000(a, b)
    dab = np.hypot(a[:, 1] - b[:, 1], a[:, 2] - b[:, 2])
    return dict(de2000_media=round(float(de.mean()), 3), de2000_mediana=round(float(np.median(de)), 3),
                de2000_p90=round(float(np.percentile(de, 90)), 3), croma_ab_media=round(float(dab.mean()), 3))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-o', '--salida', default=os.path.join(RAIZ, 'firmware', 'stock', 'ccm_ajustada_v2.json'))
    a = ap.parse_args()
    falta = [n for c, n, _, _ in FOTOS if not os.path.exists(os.path.join(RAIZ, 'dump', c, f'101O{n}.RAW'))]
    if falta:
        sys.exit(f'faltan las fotos de dump/: {falta}')
    fotos = []
    for carpeta, num, escena, luz in FOTOS:
        f = cargar(carpeta, num)
        f.update(escena=escena, luz=luz)
        fotos.append(f)
        print(f"{num} {escena:14s} {luz:8s} bloques {f['bloques']:6d} corr {f['corr']:.3f} rot {f['rot']:4d} "
              f"neutro AWB {np.round(f['neutro'], 3).tolist()}")
    fijas = {'m531_anterior': CCM_ANTERIOR, 'c713': mr._CCM_C713, 'identidad': np.eye(3)}
    escenas = sorted({f['escena'] for f in fotos})
    filas, pliegues = [], {}
    for esc in escenas:
        entreno = [f for f in fotos if f['escena'] != esc]
        M = ajustar(entreno, np.eye(3))
        pliegues[esc] = dict(entreno=[f['num'] for f in entreno], ccm=np.round(M, 5).tolist())
        for f in (x for x in fotos if x['escena'] == esc):
            for nombre, Mc in list(fijas.items()) + [('nueva_retenida', M)]:
                filas.append(dict(foto=f['num'], escena=esc, luz=f['luz'], matriz=nombre, **error(Mc, f)))
    # Aviso: 'm531_anterior' se ajustó con 1970 y 1971, así que en esas dos fotos NO está retenida
    # (ventaja para la anterior). Sólo en la escena macropad las tres matrices son ajenas a los datos.
    print(f"\n{'foto':5s} {'escena':14s} {'luz':8s} {'matriz':15s} ΔE00 media  mediana    p90   Δab media")
    for r in filas:
        print(f"{r['foto']:<5d} {r['escena']:14s} {r['luz']:8s} {r['matriz']:15s} {r['de2000_media']:10.2f} "
              f"{r['de2000_mediana']:8.2f} {r['de2000_p90']:6.2f} {r['croma_ab_media']:11.2f}")
    resumen = {}
    for nombre in list(fijas) + ['nueva_retenida']:
        rs = [r for r in filas if r['matriz'] == nombre]
        mac = [r for r in rs if r['escena'] == 'macropad']
        resumen[nombre] = dict(
            de2000_media_todas=round(float(np.mean([r['de2000_media'] for r in rs])), 3),
            de2000_peor_foto=max(r['de2000_media'] for r in rs),
            de2000_media_macropad=round(float(np.mean([r['de2000_media'] for r in mac])), 3),
            fotos_mejor_o_igual_que_anterior=sum(
                r['de2000_media'] <= next(x['de2000_media'] for x in filas
                                          if x['foto'] == r['foto'] and x['matriz'] == 'm531_anterior') for r in rs))
    print('\nresumen (media de las medias por foto retenida):')
    for k, v in resumen.items():
        print(f'  {k:15s} {v}')
    final = ajustar(fotos, np.eye(3))
    n, v = resumen['nueva_retenida'], resumen['m531_anterior']
    adoptar = bool(n['de2000_media_todas'] < v['de2000_media_todas']
                   and n['de2000_media_macropad'] < v['de2000_media_macropad']
                   and n['de2000_peor_foto'] <= v['de2000_peor_foto'])
    print('\nmatriz final (las 5 fotos):')
    print(np.round(final, 5))
    print('filas suman', np.round(final.sum(1), 6), '| condición', round(float(np.linalg.cond(final)), 2),
          '(anterior', round(float(np.linalg.cond(CCM_ANTERIOR)), 2), ')')
    print('ADOPTAR' if adoptar else 'NO ADOPTAR', '(criterio: mejor media retenida, mejor en la escena ajena a '
          'ambas y peor foto no peor)')
    json.dump(dict(
        descripcion='CCM M531: cámara balanceada (AWB del MakerNote) → sRGB lineal, filas suman 1',
        metodo='bloques 32 px, Huber + ridge %g, curva de tono por foto; validación dejando una escena fuera' % RIDGE,
        metrica='ΔE2000 (D65) contra el JPG de la cámara, tras curva de tono por foto; croma_ab = distancia en a*b*',
        fotos=[dict(num=f['num'], escena=f['escena'], luz=f['luz'], bloques=f['bloques'],
                    neutro_awb=np.round(f['neutro'], 4).tolist()) for f in fotos],
        retenidas=filas, pliegues=pliegues, resumen=resumen, adoptada=adoptar,
        ccm=np.round(final, 5).tolist(), ccm_anterior=CCM_ANTERIOR.tolist(),
        aviso='la matriz anterior se ajustó con 1970/1971: en esas dos fotos no está retenida',
    ), open(a.salida, 'w'), indent=1, ensure_ascii=False)
    print('escrito', os.path.relpath(a.salida, RAIZ))


if __name__ == '__main__':
    main()
