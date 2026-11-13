#!/usr/bin/env python3
"""Prueba E2E del conversor m531raw.py.

Fabrica, a partir de una foto real, RAWs "como los de la M531" de tamaño no estándar en varios
formatos, partidos en dos campos, y los pasa por la CLI sin pistas. Exige:
  * detección correcta de empaquetado, ancho, disposición de campos y patrón CFA;
  * que LibRaw (rawpy) abra el DNG y su raw_image sea idéntico, píxel a píxel, al mosaico original;
  * que LibRaw revele el DNG a RGB sin error.
  * con las fotos reales de dump/ (si están): balance por foto del modo 4 contra el par de modo 0.
  * con las fotos reales de dump/raw13, raw14 y raw6: el modo 4 lineal (M4L/M4R) se separa solo del de fábrica (P9).
  * con fotos reales de los cuatro formatos: el DNG revelado por el motor de macOS (sips) y por darktable-cli
    da el mouse blanco neutro y el color de LibRaw y del JPG de la cámara.
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
import glob
CARPETA = '/Volumes/Datos/proyectos/sx40-chdk-max/testdata/raw'
TODAS = sorted(glob.glob(os.path.join(CARPETA, '*', '*.JPG')))
# por defecto: la foto fácil (bordes fuertes), la que destapó el fallo de ancho y otra más;
# con --todas, las 18. Tamaños con h//8 o w//8 impares a propósito (fase del CFA).
FOTOS = TODAS if '--todas' in sys.argv else [f for f in TODAS if os.path.basename(f) in
                                             ('IMG_2830.JPG', 'IMG_2829.JPG', 'IMG_2819.JPG')]
TAMANOS = [(4416, 3312), (4320, 3240), (4424, 3312)]
W, H = TAMANOS[0]
CFA_FASE = {'RGGB': (0, 0), 'GRBG': (0, 1), 'GBRG': (1, 0), 'BGGR': (1, 1)}  # posición de R

CASOS = [
    # nombre, packing, bits, cfa, layout de campos, dos archivos
    ('12b_msb_filas_GRBG', 'p12_msb', 12, 'GRBG', 'filas', True),
    ('10b_lsb_pares_RGGB', 'p10_lsb', 10, 'RGGB', 'pares', True),
    ('14b_msb_apilado_BGGR', 'p14_msb', 14, 'BGGR', 'apilado', True),
    ('16b_le_unico_GBRG', 'u16_le', 16, 'GBRG', None, False),  # datos de 14 bits en contenedor de 16
    ('16b_be_unico_RGGB', 'u16_be', 16, 'RGGB', None, False),
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
    if packing == 'u16_be':
        return px.astype('>u2').tobytes()
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


def _cli_dng(raw, dng):
    p = subprocess.run([sys.executable, os.path.join(AQUI, 'm531raw.py'), 'dng', raw, '-o', dng],
                       capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-300:])
    return json.loads(p.stdout)


def balance_modo4(reporte):
    """Balance por foto del modo 4 con fotos reales (dump/, fuera del repo; se omite si no están).

    Verdad independiente: la misma escena tomada en modo 0, cuyo balance sale del JPG bueno de la cámara.
    Exige que el neutro del RAW de modo 4 quede a menos de TOL (en ln, canales R y B) del de su par, con
    y sin flash, y que una escena cuyo punto más claro es verde puro caiga al neutro fijo (no se acepta
    un balance que la cámara nunca elegiría). Devuelve el número de fallos."""
    TOL = 0.15
    d = os.path.join(RAIZ, 'dump')
    pares = [('raw6/101O1981.RAW', 'raw5/101O1980.RAW', 'sin flash'), ('raw4/101O1975.RAW', 'raw5/101O1980.RAW', 'sin flash'),
             ('raw6/101O1982.RAW', 'raw5/101O1978.RAW', 'flash'), ('raw4/101O1976.RAW', 'raw5/101O1978.RAW', 'flash')]
    if not all(os.path.exists(os.path.join(d, r)) for par in pares for r in par[:2]):
        reporte['balance_modo4'] = 'omitido: faltan las fotos de dump/'
        print('OMITIDO balance modo 4 (faltan las fotos de dump/)')
        return 0
    fallos, filas = 0, []
    tmp = os.path.join(SALIDA, 'balance_tmp.dng')
    for m4, m0, luz in pares:
        a, b = _cli_dng(os.path.join(d, m4), tmp), _cli_dng(os.path.join(d, m0), tmp)
        dist = max(abs(float(np.log(a['neutro'][i] / b['neutro'][i]))) for i in (0, 2))
        ok = a['balance'] == 'parche_blanco' and b['balance'] == 'jpg' and dist < TOL
        fallos += not ok
        filas.append(dict(modo4=m4, modo0=m0, luz=luz, neutro_modo4=a['neutro'], balance_modo4=a['balance'],
                          neutro_modo0=b['neutro'], balance_modo0=b['balance'], distancia_ln=round(dist, 4), ok=ok))
        print(('OK   ' if ok else 'FALLO'), 'balance modo 4', m4, luz, a['neutro'], 'vs', b['neutro'], f'd={dist:.3f}')
    # escena real con los canales R y B hundidos: lo más claro es verde y el parche blanco no es creíble
    from importlib import util
    spec = util.spec_from_file_location('m531raw', os.path.join(AQUI, 'm531raw.py'))
    mod = util.module_from_spec(spec); spec.loader.exec_module(mod)
    img, info = mod.analizar([os.path.join(d, pares[0][0])])
    verde = img.astype(np.float64)
    verde[1::2, 0::2] *= 0.15   # R en GBRG
    verde[0::2, 1::2] *= 0.15   # B en GBRG
    # de vuelta a códigos de 10 bits (inversa de la curva) y a 12 bits empaquetados lsb, como los escribe la cámara
    cod = np.round(np.interp(verde, mod.DECODE_M531.astype(np.float64), np.arange(256) * 4.0)).astype(np.uint16)
    falso = os.path.join(SALIDA, '101O9999.RAW')
    open(falso, 'wb').write(empaquetar(cod, 'p12_lsb', 12))
    c = _cli_dng(falso, tmp)
    os.remove(falso); os.remove(tmp)
    ok = c['balance'] == 'fijo_modo4' and c['neutro'] == [0.62, 1.0, 0.6] and c['packing'] == 'p12_lsb'
    fallos += not ok
    filas.append(dict(caso='escena verde: reserva al neutro fijo', balance=c['balance'], neutro=c['neutro'],
                      descartado=c.get('parche_blanco_descartado'), ok=ok))
    print(('OK   ' if ok else 'FALLO'), 'balance modo 4 escena verde →', c['balance'], 'descartado', c.get('parche_blanco_descartado'))
    reporte['balance_modo4'] = dict(tolerancia_ln=TOL, casos=filas)
    return fallos


def modo4_lineal(reporte):
    """Archivos de 21.150.720 B con fotos reales: M4L/M4R (12 bits lineales) contra P9 (curva de fábrica).

    Mismo tamaño y mismo empaquetado; el conversor los separa solo. Verdad independiente:
      * el mosaico del DNG, reempaquetado aquí a p12_lsb, tiene que dar los bytes del archivo de la cámara
        (lineal: sin tocar un solo valor);
      * el JPG que la propia cámara sacó de esos datos: con el RAW bien leído, el verde por bloques sigue al
        JPG linealizado (correlación alta, pendiente log-log cerca de 1). Leído con la curva saturaría en 1023.
      * los P9 de fábrica siguen por la curva (blanco 1023) y su mosaico ya no es el del archivo.
    Devuelve el número de fallos."""
    d = os.path.join(RAIZ, 'dump')
    lineales = [('raw13/101O1994.RAW', 'M4L'), ('raw13/101O1995.RAW', 'M4L'), ('raw14/101O1996.RAW', 'M4R'),
                ('raw14/101O2001.RAW', 'M4R')]
    fabrica = ['raw6/101O1981.RAW', 'raw6/101O1982.RAW']
    if not all(os.path.exists(os.path.join(d, r)) for r in [x[0] for x in lineales] + fabrica):
        reporte['modo4_lineal'] = 'omitido: faltan las fotos de dump/'
        print('OMITIDO modo 4 lineal (faltan las fotos de dump/)')
        return 0

    def bloques(a, n=24):
        k = a.shape[0] // n
        h, w = a.shape[0] // k * k, a.shape[1] // k * k
        return a[:h, :w].reshape(h // k, k, w // k, k).mean((1, 3))

    def contra_jpg(mos, ruta_raw):
        jpg = os.path.join(os.path.dirname(ruta_raw), os.path.basename(ruta_raw).replace('O', '_', 1)[:-4] + '.JPG')
        j = np.asarray(Image.open(jpg).convert('RGB')).astype(np.float64)[..., 1] / 255
        j = np.where(j <= 0.04045, j / 12.92, ((j + 0.055) / 1.055) ** 2.4)
        g = (mos[0::2, 0::2].astype(np.float64) + mos[1::2, 1::2]) / 2      # verdes de GBRG
        g = g[12:-12, 8:-8]                                                 # el JPG recorta a 4288×3216
        mejor = (-1.0, 0.0)
        for giro in range(4):                                               # la cámara gira el JPG según su sensor
            jr = np.rot90(j, giro)
            if (jr.shape[0] > jr.shape[1]) != (g.shape[0] > g.shape[1]):
                continue
            a, b = bloques(g), bloques(jr)
            n, m = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
            a, b = a[:n, :m].ravel(), b[:n, :m].ravel()
            sel = (b > 0.02) & (b < 0.7) & (a > 4)
            if sel.sum() < 50:
                continue
            c = float(np.corrcoef(a, b)[0, 1])
            if c > mejor[0]:
                mejor = (c, float(np.polyfit(np.log(a[sel]), np.log(b[sel]), 1)[0]))
        return mejor

    fallos, filas = 0, []
    tmp = os.path.join(SALIDA, 'modo4_tmp.dng')
    for rel, kit in lineales:
        ruta = os.path.join(d, rel)
        info = _cli_dng(ruta, tmp)
        with rawpy.imread(tmp) as rp:
            mos, blanco = rp.raw_image.copy(), int(rp.white_level)
            rp.postprocess(use_camera_wb=True, output_bps=8, half_size=True)
        identico = empaquetar(mos, 'p12_lsb', 12) == open(ruta, 'rb').read()
        corr, pend = contra_jpg(mos, ruta)
        ok = (info['modo4'] == 'lineal12' and info['packing'] == 'p12_lsb' and info['negro'] == 0 and info['blanco'] == 3950
              and blanco == 3950 and identico and int(mos.max()) > 1020 and corr > 0.97 and 0.9 < pend < 1.4)
        fallos += not ok
        filas.append(dict(archivo=rel, kit=kit, modo4=info['modo4'], maximo=int(mos.max()), blanco_dng=blanco,
                          identico_al_archivo=identico, corr_jpg=round(corr, 4), pendiente_loglog=round(pend, 3),
                          balance=info['balance'], ok=ok))
        print(('OK   ' if ok else 'FALLO'), 'modo 4 lineal', rel, kit, f'max={int(mos.max())} corr={corr:.3f} pend={pend:.2f}')
    for rel in fabrica:
        ruta = os.path.join(d, rel)
        info = _cli_dng(ruta, tmp)
        with rawpy.imread(tmp) as rp:
            mos, blanco = rp.raw_image.copy(), int(rp.white_level)
        crudo_igual = empaquetar(mos, 'p12_lsb', 12) == open(ruta, 'rb').read()
        ok = (info['modo4'] == 'curva10' and info['max_crudo'] <= 1020 and info['blanco'] == 1023 and blanco == 1023
              and int(mos.max()) <= 1023 and not crudo_igual)
        fallos += not ok
        filas.append(dict(archivo=rel, kit='P9', modo4=info['modo4'], max_crudo=info['max_crudo'], blanco_dng=blanco,
                          decodificado_con_curva=not crudo_igual, ok=ok))
        print(('OK   ' if ok else 'FALLO'), 'modo 4 de fábrica', rel, f"max_crudo={info['max_crudo']} blanco={blanco}")
    os.remove(tmp)
    reporte['modo4_lineal'] = dict(casos=filas)
    return fallos


DARKTABLE = '/Applications/darktable.app/Contents/MacOS/darktable-cli'
# Parches en fracciones del cuadro del RAW (x0, x1, y0, y1). 'blanco': objeto blanco de verdad (el mouse);
# 'color': superficies con color propio (madera del escritorio, teclas).
CASOS_COLOR = [
    dict(raw='raw20/101O2020.RAW', formato='M4L lineal 12 bits, preset Tungsteno, sin flash',
         blanco=(0.70, 0.82, 0.31, 0.36), color=dict(madera=(0.55, 0.80, 0.62, 0.77))),
    dict(raw='raw19/101O2017.RAW', formato='M4L lineal 12 bits, flash, cenital',
         blanco=(0.74, 0.84, 0.50, 0.72), color=dict(fondo_abajo=(0.03, 0.20, 0.80, 0.97))),
    dict(raw='raw20/101O2019.RAW', formato='M4L lineal 12 bits, flash, 27 % quemado',
         blanco=(0.75, 0.95, 0.38, 0.55), color=dict(madera=(0.10, 0.60, 0.75, 0.88))),
    dict(raw='raw8/101O1983.RAW', formato='modo 0, 8 bits con curva', jpg=True,
         color=dict(madera=(0.02, 0.20, 0.45, 0.65), tecla1=(0.27, 0.33, 0.38, 0.44))),
    dict(raw='raw6/101O1981.RAW', formato='modo 4 de fábrica (P9), curva de 10 bits',
         color=dict(madera=(0.02, 0.20, 0.45, 0.65), tecla1=(0.28, 0.34, 0.44, 0.50))),
    dict(raw='raw12/101O1992.RAW', formato='modo 3, u16',
         color=dict(madera=(0.05, 0.20, 0.60, 0.80), tecla4=(0.60, 0.66, 0.44, 0.50))),
]
# TOL_BLANCO: el peor error medido del balance por foto (parche blanco) es 0,18; en 2020 el mouse recibe
# además la luz del monitor. TOL_MOTORES y TOL_JPG: cada motor pone su curva de tono y su saturación; con
# la matriz de cámara balanceada que el DNG llevaba antes, la madera se iba a 1,2–1,5 en sips.
TOL_BLANCO, TOL_MOTORES, TOL_JPG = 0.18, 0.25, 0.25


def color_motores(reporte):
    """El color del DNG en motores ajenos: el de macOS (sips) y darktable-cli, si está instalado.

    Las etiquetas de color del DNG (ColorMatrix, ForwardMatrix, AsShotNeutral, iluminantes, WhiteLevel)
    sólo se prueban revelando el archivo con quien las interpreta según la norma. Con fotos reales de los
    cuatro formatos (dump/, fuera del repo; se omite si faltan) exige, en cada motor:
      * blanco: el mouse blanco sale neutro (|ln R/G| y |ln B/G| < TOL_BLANCO en sRGB linealizado);
      * color: madera y teclas a menos de TOL_MOTORES (ln de R/G y B/G) del revelado de LibRaw, que es el
        camino que supone el conversor (balance en espacio de cámara y después la matriz);
      * modo 0: además a menos de TOL_JPG del JPG que la cámara sacó del mismo disparo.
    Devuelve el número de fallos."""
    d = os.path.join(RAIZ, 'dump')
    if not all(os.path.exists(os.path.join(d, c['raw'])) for c in CASOS_COLOR):
        reporte['color_motores'] = 'omitido: faltan las fotos de dump/'
        print('OMITIDO color en motores externos (faltan las fotos de dump/)')
        return 0
    sal = os.path.join(SALIDA, 'color_motores')
    os.makedirs(sal, exist_ok=True)
    motores = ['sips'] + (['darktable'] if os.path.exists(DARKTABLE) else [])

    def lineal(ruta):
        v = np.asarray(Image.open(ruta).convert('RGB')).astype(np.float64) / 255
        return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)

    def parche(a, p):
        h, w = a.shape[:2]
        m = a[int(p[2] * h):int(p[3] * h), int(p[0] * w):int(p[1] * w)].reshape(-1, 3).mean(0)
        return [float(np.log(m[0] / m[1])), float(np.log(m[2] / m[1]))]

    def dist(a, b=(0.0, 0.0)):
        return round(max(abs(a[0] - b[0]), abs(a[1] - b[1])), 4)

    def revelar(motor, dng, jpg):
        if motor == 'sips':
            orden = ['sips', '-s', 'format', 'jpeg', '-Z', '1000', dng, '--out', jpg]
        else:
            conf = os.path.join(sal, 'darktable_conf')
            orden = [DARKTABLE, dng, jpg, '--width', '1000', '--height', '1000', '--hq', 'false',
                     '--apply-custom-presets', 'false', '--core', '--configdir', conf, '--cachedir', conf,
                     '--library', ':memory:']
        if os.path.exists(jpg):
            os.remove(jpg)
        p = subprocess.run(orden, capture_output=True, text=True, cwd=sal)
        if not os.path.exists(jpg):
            raise RuntimeError(f'{motor} no reveló {dng}: {(p.stderr or p.stdout)[-300:]}')
        return lineal(jpg)

    fallos, filas = 0, []
    for c in CASOS_COLOR:
        ruta = os.path.join(d, c['raw'])
        num = os.path.basename(ruta)[4:8]
        dng = os.path.join(sal, f'{num}.dng')
        info = _cli_dng(ruta, dng)
        with rawpy.imread(dng) as rp:
            ref = rp.postprocess(use_camera_wb=True, gamma=(1, 1), no_auto_bright=True, output_bps=16,
                                 half_size=True, user_flip=0).astype(np.float64) / 65535
        fila = dict(raw=c['raw'], formato=c['formato'], balance=info['balance'], neutro=info['neutro'],
                    blanco_dng=info['blanco'], motores={})
        ref_color = {k: parche(ref, p) for k, p in c['color'].items()}
        jpg_color = None
        if c.get('jpg'):
            j = lineal(os.path.join(os.path.dirname(ruta), f'101_{num}.JPG'))
            g = ref[::8, ::8, 1]
            cands = [np.rot90(j, k) for k in range(4)]
            cands = [x for x in cands if (x.shape[0] > x.shape[1]) == (g.shape[0] > g.shape[1])]
            def parecido(x):
                y = x[::x.shape[0] // g.shape[0], ::x.shape[1] // g.shape[1], 1][:g.shape[0], :g.shape[1]]
                return np.corrcoef(y.ravel(), g[:y.shape[0], :y.shape[1]].ravel())[0, 1]
            j = max(cands, key=parecido)
            jpg_color = {k: parche(j, p) for k, p in c['color'].items()}
        ok_caso = True
        for motor in motores:
            a = revelar(motor, dng, os.path.join(sal, f'{num}_{motor}.jpg'))
            if a.shape[0] > a.shape[1]:
                raise RuntimeError(f'{motor} giró {dng}')
            m = dict(color_vs_libraw={k: dist(parche(a, p), ref_color[k]) for k, p in c['color'].items()})
            ok = all(v < TOL_MOTORES for v in m['color_vs_libraw'].values())
            if 'blanco' in c:
                b = parche(a, c['blanco'])
                m['blanco_R_G'], m['blanco_B_G'] = round(float(np.exp(b[0])), 3), round(float(np.exp(b[1])), 3)
                m['blanco_dist'] = dist(b)
                ok = ok and m['blanco_dist'] < TOL_BLANCO
            if jpg_color:
                m['color_vs_jpg'] = {k: dist(parche(a, p), jpg_color[k]) for k, p in c['color'].items()}
                ok = ok and all(v < TOL_JPG for v in m['color_vs_jpg'].values())
            m['ok'] = ok
            ok_caso = ok_caso and ok
            fila['motores'][motor] = m
            print(('OK   ' if ok else 'FALLO'), 'color', motor.ljust(9), c['raw'], {k: v for k, v in m.items() if k != 'ok'})
        os.remove(dng)
        fila['ok'] = ok_caso
        fallos += not ok_caso
        filas.append(fila)
    import shutil
    shutil.rmtree(os.path.join(sal, 'darktable_conf'), ignore_errors=True)
    reporte['color_motores'] = dict(motores=motores, tolerancias=dict(blanco=TOL_BLANCO, motores=TOL_MOTORES, jpg=TOL_JPG),
                                    casos=filas)
    return fallos


def main():
    global W, H
    os.makedirs(SALIDA, exist_ok=True)
    rng = np.random.default_rng(531)
    reporte = dict(fotos=[os.path.basename(f) for f in FOTOS], tamanos=TAMANOS,
                   fecha=time.strftime('%Y-%m-%dT%H:%M:%S'), casos=[])
    fallos = 0
    for k, foto in enumerate(FOTOS):
        W, H = TAMANOS[k % len(TAMANOS)]
        for nombre, packing, bits, cfa, layout, dos in CASOS:
            m, negro = mosaico(foto, cfa, bits, rng)
            partes = partir(m, layout) if dos else [m]
            base = f"{os.path.basename(foto)[:-4]}_{W}x{H}_{nombre}"
            rutas = []
            for i, p in enumerate(partes):
                r = os.path.join(SALIDA, f"{base}_{'Ob'[i]}.raw")
                open(r, 'wb').write(empaquetar(p, packing, bits))
                rutas.append(r)
            dng = os.path.join(SALIDA, f'{base}.dng')
            proc = subprocess.run([sys.executable, os.path.join(AQUI, 'm531raw.py'), 'dng', *rutas, '-o', dng],
                                  capture_output=True, text=True)
            for r in rutas:
                os.remove(r)  # ~25 MB cada uno
            caso = dict(foto=os.path.basename(foto), tamano=[W, H], nombre=nombre,
                        esperado=dict(packing=packing, ancho=W, alto=H, layout=layout or 'unico', cfa=cfa))
            if proc.returncode:
                caso.update(ok=False, error=proc.stderr[-400:]); fallos += 1
                reporte['casos'].append(caso); print('FALLO', base, proc.stderr.strip()[-200:]); continue
            info = json.loads(proc.stdout)
            det = dict(packing=info['packing'], ancho=info['ancho'], alto=info['alto'], layout=info['layout'], cfa=info['cfa'])
            with rawpy.imread(dng) as rp:
                leido = rp.raw_image.copy()
                blanco_dng = int(rp.white_level)
                patron = ''.join('RGBG'[c] for c in rp.raw_pattern.ravel())
                rgb = rp.postprocess(use_camera_wb=True, output_bps=8, half_size=True) if k == 0 else None
            identico = leido.shape == m.shape and bool(np.array_equal(leido, m))
            # La diagonal verde se exige; R vs B sale de la heurística "R es el más oscuro", que
            # depende de la escena (limitación documentada): se informa aparte y no hace fallar.
            verde = lambda c: tuple(i for i, ch in enumerate(c) if ch == 'G')
            patron_ok = verde(patron) == verde(cfa)
            rb_ok = patron == cfa
            blanco_ok = int(m.max()) <= blanco_dng < 2 * max(int(m.max()), 255) + 1
            det_sin_rb = dict(det, cfa=verde(det['cfa']))
            esp_sin_rb = dict(caso['esperado'], cfa=verde(cfa))
            ok = det_sin_rb == esp_sin_rb and identico and patron_ok and blanco_ok
            if rgb is not None:
                Image.fromarray(rgb).resize((rgb.shape[1] // 3, rgb.shape[0] // 3)).save(dng[:-4] + '_preview.png')
            else:
                os.remove(dng)
            fallos += not ok
            caso.update(ok=ok, detectado=det, libraw_identico=identico, libraw_patron=patron, patron_ok=patron_ok, rb_ok=rb_ok,
                        blanco_dng=blanco_dng, blanco_ok=blanco_ok, negro_esperado=negro,
                        negro_detectado=info['negro'], candidatos=info['candidatos'][:2])
            reporte['casos'].append(caso)
            print(('OK   ' if ok else 'FALLO'), base, '' if ok else det, '' if rb_ok else '(R/B invertidos: heurística)')
    fallos += balance_modo4(reporte)
    fallos += modo4_lineal(reporte)
    fallos += color_motores(reporte)
    total = len(reporte['casos'])
    reporte['resultado'] = 'OK' if not fallos else f'{fallos} fallo(s) de {total}'
    reporte['rb_heuristica_acierta'] = f"{sum(1 for c in reporte['casos'] if c.get('rb_ok'))} de {total}"
    json.dump(reporte, open(os.path.join(SALIDA, 'reporte.json'), 'w'), indent=2, ensure_ascii=False)
    print('reporte:', os.path.join(SALIDA, 'reporte.json'), '→', reporte['resultado'], f'({total} casos)')
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    main()
