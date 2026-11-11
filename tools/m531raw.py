#!/usr/bin/env python3
"""RAW de la Kodak EasyShare M531 → DNG.

uso:
  m531raw.py info ARCHIVO [ARCHIVO2]              detecta formato y lo informa
  m531raw.py dng  ARCHIVO [ARCHIVO2] -o SALIDA.dng [--bits N --packing P --width W
                  --layout L --cfa RGGB --black N --white N]

El firmware guarda el RAW sin cabecera, en uno o dos archivos por disparo: 101O####.raw y
101b####.raw (cambia el '_' del nombre del JPG por 'O' o 'b'), probablemente los dos campos
de un CCD entrelazado. Tamaño = ceil(ancho*alto*bits/8) con
bits ∈ {8,10,12,16}. Como las dimensiones sólo existen en RAM durante la captura, todo se
detecta de los datos:

  * bits/empaquetado/ancho: para cada formato candidato se decodifica un tramo y se mide la
    autocorrelación de la secuencia de píxeles. El ancho real (o su doble) da un pico; el
    formato correcto da el pico más fuerte.
  * dos archivos: se prueban "intercalado de filas", "intercalado de pares" y "uno sobre otro";
    gana el que deja filas del mismo color (y, y+2) más parecidas.
  * CFA: la diagonal con medias y texturas más parecidas es la verde. R vs B no se puede saber
    sólo con estadística: se elige el más oscuro como R (típico con luz de día) y se puede
    forzar con --cfa. Ver tools/RAW_FALLAS.md.
"""
import argparse
import json
import os
import struct
import sys

import numpy as np

FORMATOS = [  # (nombre, bits)
    ('u8', 8), ('p10_msb', 10), ('p10_lsb', 10), ('p12_msb', 12), ('p12_lsb', 12),
    ('p14_msb', 14), ('p14_lsb', 14), ('u16_le', 16), ('u16_be', 16),
]
BITS = dict(FORMATOS)


# ---------------------------------------------------------------- desempaquetado
def desempaquetar(datos: bytes, packing: str, n: int | None = None) -> np.ndarray:
    """Devuelve uint16 con los primeros n píxeles (o todos los completos)."""
    b = BITS[packing]
    total = (len(datos) * 8) // b
    n = total if n is None else min(n, total)
    nbytes = (n * b + 7) // 8
    a = np.frombuffer(datos[:nbytes], dtype=np.uint8)
    if packing == 'u8':
        return a[:n].astype(np.uint16)
    if packing in ('u16_le', 'u16_be'):
        return np.frombuffer(datos[:n * 2], dtype='<u2' if packing == 'u16_le' else '>u2').astype(np.uint16)
    out = np.empty(n, dtype=np.uint16)
    orden = 'big' if packing.endswith('msb') else 'little'
    trozo = 1 << 20  # píxeles por bloque; múltiplo de 8 para no partir bytes
    pesos = (1 << np.arange(b - 1, -1, -1, dtype=np.uint32)) if orden == 'big' \
        else (1 << np.arange(b, dtype=np.uint32))
    for i in range(0, n, trozo):
        m = min(trozo, n - i)
        ini_bit = i * b
        bytes_ini = ini_bit // 8  # i*b es múltiplo de 8 porque trozo lo es
        bits = np.unpackbits(a[bytes_ini:bytes_ini + (m * b + 7) // 8], bitorder=orden)[:m * b]
        out[i:i + m] = (bits.reshape(m, b).astype(np.uint32) @ pesos).astype(np.uint16)
    return out


# ---------------------------------------------------------------- detección
def _autocorr_pico(x: np.ndarray, lag_min: int, lag_max: int):
    x = x.astype(np.float64)
    x -= x.mean()
    if not x.std():
        return 0.0, 0, 0.0
    nfft = 1 << int(np.ceil(np.log2(2 * len(x))))
    f = np.fft.rfft(x, nfft)
    ac = np.fft.irfft(f * np.conj(f), nfft)[:lag_max + 1]
    ac /= ac[0]
    seg = ac[lag_min:lag_max + 1]
    k = int(np.argmax(seg))
    pico = float(seg[k])
    lag = lag_min + k
    # preferir el menor múltiplo: si lag/2 o lag/3 tienen un pico casi igual, el ancho es ese
    for div in (3, 2):
        l2 = lag // div
        if l2 >= lag_min and lag % div == 0:
            vec = ac[max(l2 - 1, 0):l2 + 2]
            if vec.max() >= 0.9 * pico:
                lag = l2 - 1 + int(np.argmax(vec))
    return pico, lag, float(ac[2])


def detectar_formato(datos: bytes, ancho_min=1500, ancho_max=7000, muestra=3_000_000):
    res = []
    for packing, b in FORMATOS:
        px = desempaquetar(datos, packing, muestra)
        if len(px) < 3 * ancho_max:
            continue
        # empezar lejos del borde superior (negro óptico, filas de basura)
        ini = len(px) // 4
        pico, lag, vecino = _autocorr_pico(px[ini:], ancho_min, ancho_max)
        # castigo a formatos que dejan bits altos vacíos o saturan raro
        vals = px[ini:ini + 200_000]
        usado = int(vals.max()).bit_length()
        # el ancho correcto da pico vertical; el empaquetado correcto, además, vecinos del mismo
        # color (desfase 2) parecidos. Un empaquetado equivocado mezcla bits y rompe lo segundo.
        puntaje = pico * max(vecino, 0.0)
        # Un contenedor de 16 bits guarda datos de 12–14 bits: los dos bits altos quedan vacíos.
        # Si se llenan, lo más probable es que sean dos píxeles de 8 bits leídos como uno.
        if b == 16 and usado > 14:
            puntaje *= 0.5
        res.append(dict(packing=packing, bits=b, ancho=lag, pico=round(pico, 4), vecino=round(vecino, 4),
                        puntaje=round(puntaje, 4), bits_usados=usado))
    res.sort(key=lambda r: -r['puntaje'])
    return res


def a_imagen(datos: bytes, packing: str, ancho: int) -> np.ndarray:
    px = desempaquetar(datos, packing)
    alto = len(px) // ancho
    return px[:alto * ancho].reshape(alto, ancho)


def _suavidad(img: np.ndarray) -> float:
    a = img[:-2:, :].astype(np.int32)
    b = img[2:, :].astype(np.int32)
    return float(np.mean(np.abs(a - b)))


def combinar(campos: list[np.ndarray], layout: str | None):
    if len(campos) == 1:
        return campos[0], 'unico'
    A, B = campos
    h = min(len(A), len(B))
    w = min(A.shape[1], B.shape[1])
    A, B = A[:h, :w], B[:h, :w]
    opciones = {}
    # intercalado de filas: A0 B0 A1 B1 ...
    f = np.empty((2 * h, w), dtype=A.dtype); f[0::2] = A; f[1::2] = B
    opciones['filas'] = f
    # intercalado de pares: A0 A1 B0 B1 A2 A3 ...
    if h % 2 == 0:
        p = np.empty((2 * h, w), dtype=A.dtype)
        p.reshape(h, 2, w)[0::2] = A.reshape(h // 2, 2, w)
        p.reshape(h, 2, w)[1::2] = B.reshape(h // 2, 2, w)
        opciones['pares'] = p
    opciones['apilado'] = np.vstack([A, B])
    if layout:
        return opciones[layout], layout
    puntaje = {k: _suavidad(v) for k, v in opciones.items()}
    mejor = min(puntaje, key=puntaje.get)
    return opciones[mejor], mejor


def detectar_cfa(img: np.ndarray):
    h, w = img.shape
    c = img[h // 8: h - h // 8, w // 8: w - w // 8].astype(np.float64)
    c = c[: c.shape[0] // 2 * 2, : c.shape[1] // 2 * 2]
    p = {(y, x): c[y::2, x::2] for y in (0, 1) for x in (0, 1)}
    def parecido(a, b):  # menor = más parecidos (media y textura)
        return abs(a.mean() - b.mean()) / (a.mean() + b.mean() + 1e-9) + \
            np.mean(np.abs(a - b)) / (a.mean() + b.mean() + 1e-9)
    d_principal = parecido(p[0, 0], p[1, 1])
    d_secundaria = parecido(p[0, 1], p[1, 0])
    if d_principal < d_secundaria:  # verdes en (0,0) y (1,1)
        o1, o2 = p[0, 1].mean(), p[1, 0].mean()
        return ('GRBG' if o1 < o2 else 'GBRG'), dict(d_verde=d_principal, d_otra=d_secundaria)
    o1, o2 = p[0, 0].mean(), p[1, 1].mean()
    return ('RGGB' if o1 < o2 else 'BGGR'), dict(d_verde=d_secundaria, d_otra=d_principal)


def neutro_mundo_gris(img, cfa, negro, blanco):
    """AsShotNeutral por mundo gris: media de cada canal sin negro ni saturados, relativa a G."""
    pos = {c: [] for c in 'RGB'}
    for i, c in enumerate(cfa):
        pos[c].append((i // 2, i % 2))
    v = img.astype(np.float64) - negro
    tope = (blanco - negro) * 0.95
    medias = {}
    for c, ps in pos.items():
        x = np.concatenate([v[y::2, xx::2].ravel() for y, xx in ps])
        x = x[(x > 0) & (x < tope)]
        medias[c] = x.mean() if len(x) else 1.0
    return tuple(min(max(medias[c] / medias['G'], 0.05), 4.0) for c in 'RGB')


# ---------------------------------------------------------------- DNG
_CFA = {'RGGB': (0, 1, 1, 2), 'BGGR': (2, 1, 1, 0), 'GRBG': (1, 0, 2, 1), 'GBRG': (1, 2, 0, 1)}
# Matriz provisional XYZ(D65)→cámara: inversa de la CCM de luz de día de la C713 (misma
# familia Altek). Se reemplaza al calibrar con fotos reales de la M531.
_CCM_C713 = np.array([[150592, -88384, 3328], [-27776, 143360, -50048], [3008, -52352, 114880]]) / 65536
_SRGB_A_XYZ = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                        [0.0193339, 0.1191920, 0.9503041]])


def _matriz_color():
    cam_a_xyz = _SRGB_A_XYZ @ _CCM_C713
    return np.linalg.inv(cam_a_xyz)


def escribir_dng(ruta, img: np.ndarray, cfa: str, negro: int, blanco: int, recorte=None,
                 neutro=(0.5, 1.0, 0.7)):
    h, w = img.shape
    datos = img.astype('<u2').tobytes()
    entradas = []  # (tag, tipo, cuenta, valor_bytes)
    def tag(t, tipo, valores):
        fmt = {1: 'B', 2: 's', 3: 'H', 4: 'I', 5: 'II', 10: 'ii', 12: 'd'}[tipo]
        if tipo == 2:
            vb = valores.encode() + b'\0'; n = len(vb)
        elif tipo in (5, 10):
            vb = b''.join(struct.pack('<' + fmt, *v) for v in valores); n = len(valores)
        else:
            vb = struct.pack('<%d%s' % (len(valores), fmt), *valores); n = len(valores)
        entradas.append((t, tipo, n, vb))
    def rac(x, d=10000):
        return (int(round(x * d)), d)
    cx, cy, cw, ch = recorte or (0, 0, w, h)
    m = _matriz_color()
    tag(254, 4, [0]); tag(256, 4, [w]); tag(257, 4, [h]); tag(258, 3, [16]); tag(259, 3, [1])
    tag(262, 3, [32803]); tag(271, 2, 'Kodak'); tag(272, 2, 'EasyShare M531')
    tag(273, 4, [0]); tag(274, 3, [1]); tag(277, 3, [1]); tag(278, 4, [h]); tag(279, 4, [len(datos)])
    tag(284, 3, [1]); tag(305, 2, 'm531raw.py')
    tag(33421, 3, [2, 2]); tag(33422, 1, list(_CFA[cfa]))
    tag(50706, 1, [1, 4, 0, 0]); tag(50707, 1, [1, 1, 0, 0]); tag(50708, 2, 'Kodak EasyShare M531')
    tag(50710, 1, [0, 1, 2]); tag(50711, 3, [1])
    tag(50714, 4, [int(negro)]); tag(50717, 4, [int(blanco)])
    tag(50719, 4, [cx, cy]); tag(50720, 4, [cw, ch])
    tag(50721, 10, [rac(v) for v in m.flatten()])
    tag(50728, 5, [rac(v) for v in neutro])
    tag(50778, 3, [21])
    entradas.sort(key=lambda e: e[0])
    n = len(entradas)
    ifd_off = 8
    extra_off = ifd_off + 2 + 12 * n + 4
    extra = bytearray()
    cuerpo = bytearray()
    datos_off = None
    # primera pasada para ubicar datos tras los valores largos
    largos = sum((len(e[3]) + 1) & ~1 for e in entradas if len(e[3]) > 4)
    datos_off = extra_off + largos
    datos_off = (datos_off + 15) & ~15
    for t, tipo, cnt, vb in entradas:
        if t == 273:
            vb = struct.pack('<I', datos_off)
        if len(vb) <= 4:
            cuerpo += struct.pack('<HHI', t, tipo, cnt) + vb.ljust(4, b'\0')
        else:
            cuerpo += struct.pack('<HHII', t, tipo, cnt, extra_off + len(extra))
            extra += vb
            if len(extra) % 2:
                extra += b'\0'
    with open(ruta, 'wb') as f:
        f.write(b'II*\0' + struct.pack('<I', ifd_off))
        f.write(struct.pack('<H', n) + cuerpo + struct.pack('<I', 0))
        f.write(extra)
        f.write(b'\0' * (datos_off - (extra_off + len(extra))))
        f.write(datos)


# ---------------------------------------------------------------- flujo
def analizar(rutas, bits=None, packing=None, ancho=None, layout=None, cfa=None):
    datos = [open(r, 'rb').read() for r in rutas]
    if packing is None:
        cands = detectar_formato(datos[0])
        if bits:
            cands = [c for c in cands if c['bits'] == bits] or cands
        if not cands:
            raise SystemExit('archivo demasiado pequeño o truncado: ningún formato da 3 filas de 7000 píxeles')
        elegido = cands[0]
        packing = elegido['packing']
        ancho = ancho or elegido['ancho']
    else:
        cands = []
        if ancho is None:
            c = [c for c in detectar_formato(datos[0]) if c['packing'] == packing]
            if not c:
                raise SystemExit(f'no se pudo detectar el ancho para {packing}; pasar --width')
            ancho = c[0]['ancho']
    campos = [a_imagen(d, packing, ancho) for d in datos]
    img, layout_usado = combinar(campos, layout)
    if img.shape[0] % 2:
        img = img[:-1]
    cfa_det, cfa_info = detectar_cfa(img)
    info = dict(archivos=[os.path.basename(r) for r in rutas], tamanos=[len(d) for d in datos],
                packing=packing, bits=BITS[packing], ancho=int(ancho), alto=int(img.shape[0]),
                layout=layout_usado, cfa=cfa or cfa_det, cfa_detectado=cfa_det,
                cfa_metricas={k: round(v, 5) for k, v in cfa_info.items()},
                candidatos=cands[:5])
    return img, info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('accion', choices=['info', 'dng'])
    ap.add_argument('archivos', nargs='+')
    ap.add_argument('-o', '--salida')
    ap.add_argument('--bits', type=int)
    ap.add_argument('--packing', choices=[p for p, _ in FORMATOS])
    ap.add_argument('--width', type=int)
    ap.add_argument('--layout', choices=['filas', 'pares', 'apilado'])
    ap.add_argument('--cfa', choices=list(_CFA))
    ap.add_argument('--black', type=int)
    ap.add_argument('--white', type=int)
    a = ap.parse_args()
    if len(a.archivos) > 2:
        sys.exit('máximo dos archivos (los dos campos de un disparo)')
    img, info = analizar(a.archivos, a.bits, a.packing, a.width, a.layout, a.cfa)
    # Negro provisional: percentil bajo de la escena. Sobreestima si la escena no tiene negros puros;
    # el valor real sale del negro óptico de una toma real (o --black).
    negro = a.black if a.black is not None else int(np.percentile(img, 0.05))
    if a.white is not None:
        blanco = a.white
    elif info['bits'] == 16:
        # contenedor de 16 bits: el sensor da 12–14; usar los bits realmente ocupados
        blanco = (1 << max(int(img.max()).bit_length(), 12)) - 1
    else:
        blanco = (1 << info['bits']) - 1
    info['niveles_provisionales'] = a.black is None or a.white is None
    info.update(negro=negro, blanco=blanco)
    if a.accion == 'info':
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return
    if not a.salida:
        sys.exit('falta -o SALIDA.dng')
    neutro = neutro_mundo_gris(img, info['cfa'], negro, blanco)
    info['neutro'] = [round(x, 4) for x in neutro]
    escribir_dng(a.salida, img, info['cfa'], negro, blanco, neutro=neutro)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == '__main__':
    main()
