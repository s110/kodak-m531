#!/usr/bin/env python3
"""Mide el balance de blancos por foto de m531raw.py contra verdades independientes (fotos de dump/).

uso: .venv/bin/python tools/medir_balance.py        → tabla y work/balance/reporte.json

Verdad de cada foto:
  * M4L 2015–2021: el mouse blanco, medido en el propio RAW (mediana de R/G y B/G de sus píxeles sin saturar);
  * P9 1975–1977, 1981, 1982: el AWB de la cámara en la foto de modo 0 de la misma escena;
  * modo 0: el AWB de la cámara guardado en el JPG.
Error = máximo de |ln(estimado / verdad)| en R y B. Compara el estimador (lo claro y menos cálido), las
ganancias de la cámara (AWB, preset o flash) y lo que elige `elegir_balance`.
"""
import json
import os
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import m531raw as m  # noqa: E402

# parche del mouse en fracciones del cuadro del RAW (x0, x1, y0, y1)
MOUSE = {'raw19/101O2015': (0.74, 0.90, 0.33, 0.38), 'raw19/101O2016': (0.55, 0.65, 0.70, 0.90),
         'raw19/101O2017': (0.74, 0.84, 0.50, 0.72), 'raw19/101O2018': (0.60, 0.78, 0.36, 0.42),
         'raw20/101O2019': (0.75, 0.95, 0.38, 0.55), 'raw20/101O2020': (0.62, 0.82, 0.33, 0.40),
         'raw20/101O2021': (0.62, 0.82, 0.36, 0.42)}
PARES = {'raw6/101O1981': 'raw5/101O1980', 'raw4/101O1975': 'raw5/101O1980', 'raw6/101O1982': 'raw5/101O1978',
         'raw4/101O1976': 'raw5/101O1978', 'raw4/101O1977': 'raw5/101O1979'}
MODO0 = ['raw5/101O1978', 'raw5/101O1979', 'raw5/101O1980', 'raw8/101O1983', 'raw8/101O1984', 'raw8/101O1985',
         'raw8/101O1986', 'raw10/101O1988', 'raw10/101O1989', 'raw17/101O2010', 'raw17/101O2011']


def ruta(k):
    return os.path.join(RAIZ, 'dump', k + '.RAW')


def n_awb(k):
    a = m.awb_camara(ruta(k))
    return (a[1] / a[0], 1.0, a[1] / a[2]) if a else None


def err(n, t):
    return None if n is None else round(float(max(abs(np.log(n[0] / t[0])), abs(np.log(n[2] / t[2])))), 3)


def main():
    todas = list(MOUSE) + list(PARES) + MODO0
    if not all(os.path.exists(ruta(k)) for k in todas + list(PARES.values())):
        sys.exit('faltan fotos de dump/')
    filas = []
    for k in todas:
        img, info = m.analizar([ruta(k)])
        blanco = m.BLANCO_M4_LINEAL if info['modo4'] == 'lineal12' else 1023
        if k in MOUSE:
            v = img.astype(np.float64)
            R, G, B = v[1::2, 0::2], (v[0::2, 0::2] + v[1::2, 1::2]) / 2, v[0::2, 1::2]
            p = MOUSE[k]
            h, w = G.shape
            z = (slice(int(p[2] * h), int(p[3] * h)), slice(int(p[0] * w), int(p[1] * w)))
            ok = (R[z] < blanco * .95) & (G[z] < blanco * .95) & (B[z] < blanco * .95)
            verdad, clase = (float(np.median(R[z][ok] / G[z][ok])), 1.0, float(np.median(B[z][ok] / G[z][ok]))), 'M4L'
        elif k in PARES:
            verdad, clase = n_awb(PARES[k]), 'P9'
        else:
            verdad, clase = n_awb(k), 'modo 0'
        info.update(negro=0, blanco=blanco)
        if clase == 'modo 0':
            info['perfil'] = dict(balance_jpg=False)        # sin mirar el JPG: se mide el estimador
        elegido = m.elegir_balance(ruta(k) if clase != 'modo 0' else ruta(k) + '.sin_jpg', img, info, 0, blanco)
        fila = dict(foto=k[-4:], clase=clase, quemado=round(m.fraccion_quemada(img, 0, blanco), 3),
                    verdad=[round(x, 3) for x in verdad], escena=err(m.neutro_claros_frios(img, 'GBRG', 0, blanco), verdad),
                    camara=err(n_awb(k), verdad) if clase == 'M4L' else None, elegido=err(elegido, verdad), regla=info['balance'])
        filas.append(fila)
        print(fila)
    res = {}
    for clase in ('M4L', 'P9', 'modo 0', 'todas'):
        e = [f['elegido'] for f in filas if clase in (f['clase'], 'todas')]
        s = [f['escena'] for f in filas if clase in (f['clase'], 'todas') and f['quemado'] <= m.QUEMADO_MAX]
        res[clase] = dict(fotos=len(e), elegido_media=round(float(np.mean(e)), 3), elegido_peor=max(e),
                          escena_sin_quemado_media=round(float(np.mean(s)), 3), escena_sin_quemado_peor=max(s))
        print(clase, res[clase])
    os.makedirs(os.path.join(RAIZ, 'work', 'balance'), exist_ok=True)
    json.dump(dict(fotos=filas, resumen=res), open(os.path.join(RAIZ, 'work', 'balance', 'reporte.json'), 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
