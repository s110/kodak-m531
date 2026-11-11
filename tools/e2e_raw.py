#!/usr/bin/env python3
"""Prueba E2E del conversor m531raw.py.

Fabrica, a partir de una foto real, RAWs "como los de la M531" de tamaño no estándar en varios
formatos, partidos en dos campos, y los pasa por la CLI sin pistas. Exige:
  * detección correcta de empaquetado, ancho, disposición de campos y patrón CFA;
  * que LibRaw (rawpy) abra el DNG y su raw_image sea idéntico, píxel a píxel, al mosaico original;
  * que LibRaw revele el DNG a RGB sin error.
Deja un artefacto verificable en work/e2e_raw/: reporte JSON con hashes y vistas previas PNG.

uso: .venv/bin/python tools/e2e_raw.py [FOTO.jpg]
"""
import hashlib
import json
import os
import subprocess
import sys
import time

import numpy as np
import rawpy
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SALIDA = os.path.join(RAIZ, 'work', 'e2e_raw')
FOTO = sys.argv[1] if len(sys.argv) > 1 else \
    '/Volumes/Datos/proyectos/sx40-chdk-max/testdata/raw/128___10/IMG_2830.JPG'
W, H = 4416, 3312          # no estándar a propósito; el firmware no los conoce
CFA_FASE = {'RGGB': (0, 0), 'GRBG': (0, 1), 'GBRG': (1, 0), 'BGGR': (1, 1)}  # posición de R

CASOS = [
    # nombre, packing, bits, cfa, layout de campos, dos archivos
    ('12b_msb_filas_GRBG', 'p12_msb', 12, 'GRBG', 'filas', True),
    ('10b_lsb_pares_RGGB', 'p10_lsb', 10, 'RGGB', 'pares', True),
    ('14b_msb_apilado_BGGR', 'p14_msb', 14, 'BGGR', 'apilado', True),
    ('16b_le_unico_GBRG', 'u16_le', 16, 'GBRG', None, False),  # datos de 14 bits en contenedor de 16
    ('8b_unico_RGGB', 'u8', 8, 'RGGB', None, False),
]


def mosaico(foto, cfa, bits, rng):
    img = Image.open(foto).convert('RGB').resize((W, H), Image.LANCZOS)
    s = np.asarray(img).astype(np.float64) / 255
    lin = np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)
    # respuesta de cámara típica con luz de día: R el canal más oscuro, G el más alto
    cam = lin * np.array([0.45, 1.0, 0.70])
    ry, rx = CFA_FASE[cfa]
    m = np.empty((H, W))
    m[:] = cam[..., 1]
    m[ry::2, rx::2] = cam[ry::2, rx::2, 0]
    m[1 - ry::2, 1 - rx::2] = cam[1 - ry::2, 1 - rx::2, 2]
    maxv = (1 << min(bits, 14)) - 1  # el sensor da como mucho 14 bits; el modo 16 es contenedor
    negro = round(maxv * 0.015)
    v = negro + m * (maxv - negro) * 0.9 + rng.normal(0, maxv * 0.002, m.shape)
    return np.clip(np.round(v), 0, maxv).astype(np.uint16), negro


def empaquetar(px, packing, bits):
    px = px.ravel()
    if packing == 'u8':
        return px.astype(np.uint8).tobytes()
    if packing == 'u16_le':
        return px.astype('<u2').tobytes()
    orden = 'big' if packing.endswith('msb') else 'little'
    rng = np.arange(bits - 1, -1, -1) if orden == 'big' else np.arange(bits)
    bitsarr = ((px[:, None] >> rng) & 1).astype(np.uint8).ravel()
    return np.packbits(bitsarr, bitorder=orden).tobytes()


def partir(m, layout):
    if layout == 'filas':
        return [m[0::2], m[1::2]]
    if layout == 'pares':
        q = m.reshape(H // 2, 2, W)
        return [q[0::2].reshape(-1, W), q[1::2].reshape(-1, W)]
    return [m[:H // 2], m[H // 2:]]


def main():
    os.makedirs(SALIDA, exist_ok=True)
    rng = np.random.default_rng(531)
    reporte = dict(foto=FOTO, foto_sha256=hashlib.sha256(open(FOTO, 'rb').read()).hexdigest(),
                   dimensiones=[W, H], fecha=time.strftime('%Y-%m-%dT%H:%M:%S'), casos=[])
    fallos = 0
    for nombre, packing, bits, cfa, layout, dos in CASOS:
        m, negro = mosaico(FOTO, cfa, bits, rng)
        partes = partir(m, layout) if dos else [m]
        rutas = []
        for i, p in enumerate(partes):
            r = os.path.join(SALIDA, f"{nombre}_{'Ob'[i]}.raw")
            open(r, 'wb').write(empaquetar(p, packing, bits))
            rutas.append(r)
        dng = os.path.join(SALIDA, f'{nombre}.dng')
        t0 = time.time()
        proc = subprocess.run([sys.executable, os.path.join(AQUI, 'm531raw.py'), 'dng', *rutas, '-o', dng],
                              capture_output=True, text=True)
        dt = time.time() - t0
        caso = dict(nombre=nombre, esperado=dict(packing=packing, ancho=W, alto=H, layout=layout or 'unico', cfa=cfa))
        if proc.returncode:
            caso.update(ok=False, error=proc.stderr[-800:]); fallos += 1
            reporte['casos'].append(caso); print('FALLO', nombre, proc.stderr[-300:]); continue
        info = json.loads(proc.stdout)
        det = dict(packing=info['packing'], ancho=info['ancho'], alto=info['alto'], layout=info['layout'], cfa=info['cfa'])
        with rawpy.imread(dng) as rp:
            leido = rp.raw_image.copy()
            patron = ''.join('RGBG'[c] for c in rp.raw_pattern.ravel())
            rgb = rp.postprocess(use_camera_wb=True, output_bps=8, half_size=True)
        identico = leido.shape == m.shape and bool(np.array_equal(leido, m))
        Image.fromarray(rgb).resize((rgb.shape[1] // 3, rgb.shape[0] // 3)).save(dng[:-4] + '_preview.png')
        ok = det == caso['esperado'] and identico
        fallos += not ok
        caso.update(ok=ok, detectado=det, libraw_identico=identico, libraw_patron=patron,
                    negro_esperado=negro, negro_detectado=info['negro'], segundos=round(dt, 1),
                    dng_sha256=hashlib.sha256(open(dng, 'rb').read()).hexdigest(),
                    candidatos=info['candidatos'][:3])
        reporte['casos'].append(caso)
        print(('OK   ' if ok else 'FALLO'), nombre, det, 'libraw idéntico' if identico else 'libraw DISTINTO', f'{dt:.1f}s')
        for r in rutas:
            os.remove(r)  # los .raw pesan ~25 MB cada uno; el DNG y el reporte quedan
    reporte['resultado'] = 'OK' if not fallos else f'{fallos} fallo(s)'
    json.dump(reporte, open(os.path.join(SALIDA, 'reporte.json'), 'w'), indent=2, ensure_ascii=False)
    print('reporte:', os.path.join(SALIDA, 'reporte.json'), '→', reporte['resultado'])
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    main()
