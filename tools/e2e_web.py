#!/usr/bin/env python3
"""Prueba E2E del conversor web (web/, la página estática "Reveal"): los mismos módulos de la página
contra tools/m531raw.py sobre fotos reales de dump/, y la página de verdad en Chrome sin ventana.

Cómo puede fallar (escrito antes del código de web/):
  1. El port a JavaScript decodifica distinto: otro orden de bits al desempaquetar 12 bits, otra curva
     (np.interp + redondeo al par del modo 4 de fábrica), o confunde M4L (12 bits lineales) con P9.
  2. La FFT propia difiere de numpy en el redondeo y cambia una decisión: p12_msb contra p12_lsb, el
     ancho de fila o si la detección es fiable (archivo de tamaño desconocido, dos campos O + B).
  3. Un percentil, una media o un umbral salen distintos (np.percentile, suma por pares de numpy) y el
     AsShotNeutral del DNG cambia, o se elige otra fuente de balance que Python.
  4. El JPG se decodifica distinto que con PIL/libjpeg (IDCT, ensanchado del croma, YCbCr → RGB) y el
     balance sacado del JPG (modo 0) se corre; o el MakerNote se lee mal y Balance = Cámara no aplica.
  5. Un JPG truncado, vacío o de 224 B: Python lo ignora y no lo copia; la web lo copia, o revienta.
  6. El DNG no es el mismo archivo: una etiqueta TIFF distinta (racionales de las matrices, redondeo),
     otro relleno, o píxeles en otro orden de bytes. O LibRaw no lo abre.
  7. Girar: la etiqueta Orientation queda distinta que con m531raw.orientar, el JPG no descuenta el giro
     que la cámara ya aplicó, o la miniatura gira hacia el otro lado.
  8. La página: no empareja O/B/JPG de una carpeta DCIM, convierte archivos ajenos, se traba mientras
     convierte, no recuerda Balance/Giro, o el visor no alterna DNG/JPG con espacio ni cierra con Esc.
  9. El .zip: CRC o desplazamientos malos, DNG distinto del que se ve, JPG roto dentro, o un lote
     grande que pasa de 4 GB en vez de repartirse en varios .zip.
 10. Privacidad: la página pide algo fuera de sus propios archivos (CDN, analítica, subida), o la
     política CSP de web/_headers le impide funcionar. O web/ lleva rutas personales o fotos.
 11. La vista previa propia no corresponde al DNG (otro balance, otra orientación, colores cambiados).
 12. En pantalla de teléfono la página se desborda; en modo oscuro queda ilegible.

Qué se compara y con qué tolerancia:
  * píxeles del DNG: idénticos bit a bit. Etiquetas TIFF: idénticas todas. La única que podría diferir
    legítimamente es AsShotNeutral (50728) cuando el balance sale del JPG o de una estimación en coma
    flotante; se admite hasta 2e-6 (dos unidades del último dígito del racional) y se informa lo medido.
  * neutro en precisión completa (antes de redondear al racional): se informa la diferencia máxima.
Artefacto: work/e2e_web/reporte.json, hoja.jpg (vista previa de la página junto al revelado de LibRaw del
mismo DNG) y capturas de la página (escritorio, visor, teléfono en modo oscuro).
uso: .venv/bin/python tools/e2e_web.py
Necesita node, Google Chrome y playwright en el entorno (uv pip install --python .venv/bin/python playwright;
usa el Chrome instalado, no descarga navegadores).
"""
import base64
import hashlib
import http.server
import io
import json
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import numpy as np
import rawpy
from PIL import Image, ImageDraw

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DUMP = os.path.join(RAIZ, 'dump')
WEB = os.path.join(RAIZ, 'web')
OUT = os.path.join(RAIZ, 'work', 'e2e_web')
NODE = shutil.which('node') or '/opt/homebrew/bin/node'
sys.path.insert(0, AQUI)
import m531raw  # noqa: E402
import conversor_ui  # noqa: E402

FALLAS = []
HECHAS = [0]
TOL_NEUTRO = 2e-6


def chequear(cond, msg):
    HECHAS[0] += 1
    print(('ok    ' if cond else 'FALLA ') + msg, flush=True)
    if not cond:
        FALLAS.append(msg)
    return bool(cond)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def etiquetas(b):
    """IFD de un DNG → {etiqueta: (tipo, cuenta, bytes del valor)} y el desplazamiento de los píxeles."""
    n = struct.unpack_from('<H', b, 8)[0]
    tam = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 10: 8}
    out = {}
    for i in range(n):
        t, tipo, cnt = struct.unpack_from('<HHI', b, 10 + 12 * i)
        largo = tam[tipo] * cnt
        pos = 10 + 12 * i + 8 if largo <= 4 else struct.unpack_from('<I', b, 10 + 12 * i + 8)[0]
        out[t] = (tipo, cnt, b[pos:pos + largo])
    return out, struct.unpack('<I', out[273][2])[0]


def racionales(v):
    return [a / b for a, b in struct.iter_unpack('<II', v)]


# ---------------------------------------------------------------- casos (fotos reales de dump/)
def d13(n):
    return os.path.join(DUMP, '2026-11-13', n)


def partir_campos(origen, destino_o, destino_b, ancho_bytes):
    """Dos campos entrelazados a partir de un RAW real: filas pares → O, impares → B."""
    a = np.fromfile(origen, dtype=np.uint8).reshape(-1, ancho_bytes)
    a[0::2].tofile(destino_o)
    a[1::2].tofile(destino_b)


def preparar_casos(tmp):
    """Cada caso es una carpeta con los archivos tal como llegarían de la tarjeta."""
    casos = []

    def caso(nombre, archivos, balance='auto', rotar='no', giros=(), espera=None):
        c = os.path.join(tmp, 'casos', nombre)
        os.makedirs(c)
        for destino, origen in archivos.items():
            if callable(origen):
                origen(os.path.join(c, destino))
            else:
                shutil.copy(origen, os.path.join(c, destino))
        casos.append(dict(nombre=nombre, carpeta=c, balance=balance, rotar=rotar, giros=list(giros), espera=espera or {}))

    def cortado(origen, n):
        return lambda dst: open(dst, 'wb').write(open(origen, 'rb').read()[:n])

    def fraccion(origen, f):
        return lambda dst: open(dst, 'wb').write(open(origen, 'rb').read()[:int(os.path.getsize(origen) * f)])

    r10, r8, r3, r1 = (os.path.join(DUMP, x) for x in ('raw10', 'raw8', 'raw3', 'raw1'))
    caso('m4l_con_jpg', {'101O2037.RAW': d13('101O2037.RAW'), '101_2037.JPG': d13('101_2037.JPG')}, rotar='camara', giros=['izq'],
         espera=dict(balance='parche_blanco', modo4='lineal12', jpg=True))
    caso('m4l_sin_jpg', {'101O2029.RAW': d13('101O2029.RAW')}, rotar='camara', espera=dict(balance='parche_blanco', jpg=False))
    caso('m4l_jpg_cortado_en_cabecera', {'101O2032.RAW': d13('101O2032.RAW'), '101_2032.JPG': cortado(d13('101_2032.JPG'), 30_000)},
         rotar='camara', espera=dict(jpg=False, awb_camara=None))
    caso('m4l_jpg_cortado_en_datos', {'101O2031.RAW': d13('101O2031.RAW'), '101_2031.JPG': fraccion(d13('101_2031.JPG'), 0.6)},
         rotar='camara', espera=dict(jpg=False, giro=1))
    caso('m4l_balance_camara', {'101O2037.RAW': d13('101O2037.RAW'), '101_2037.JPG': d13('101_2037.JPG')}, balance='camara',
         espera=dict(balance='awb_camara', jpg=True))
    caso('m4l_quemado_usa_awb', {'101O2030.RAW': d13('101O2030.RAW'), '101_2030.JPG': d13('101_2030.JPG')},
         espera=dict(balance='awb_camara'))
    caso('m4l_parche_no_creible', {'101O2022.RAW': d13('101O2022.RAW'), '101_2022.JPG': d13('101_2022.JPG')}, rotar='camara',
         espera=dict(balance='fijo_modo4'))
    caso('p8_balance_del_jpg', {'101O1988.RAW': os.path.join(r10, '101O1988.RAW'), '101_1988.JPG': os.path.join(r10, '101_1988.JPG')},
         rotar='camara', giros=['der', 'der', 'der'], espera=dict(balance='jpg', jpg=True, giro=2))
    caso('p8_balance_del_jpg_2', {'101O1989.RAW': os.path.join(r10, '101O1989.RAW'), '101_1989.JPG': os.path.join(r10, '101_1989.JPG')},
         espera=dict(balance='jpg'))
    caso('p8_balance_camara', {'101O1989.RAW': os.path.join(r10, '101O1989.RAW'), '101_1989.JPG': os.path.join(r10, '101_1989.JPG')},
         balance='camara', espera=dict(balance='awb_camara'))
    caso('p8_jpg_vacio', {'101O1987.RAW': os.path.join(r8, '101O1987.RAW'), '101_1987.JPG': os.path.join(r8, '101_1987.JPG')},
         rotar='camara', espera=dict(balance='parche_blanco', jpg=False))
    caso('p9_curva_10_bits', {'101O1972.RAW': os.path.join(r3, '101O1972.RAW'), '101_1972.JPG': os.path.join(r3, '101_1972.JPG')},
         espera=dict(modo4='curva10'))
    caso('modo3_16_bits_jpg_de_224_B', {'101O1968.RAW': os.path.join(r1, '101O1968.RAW'), '101_1968.JPG': os.path.join(r1, '101_1968.JPG')},
         rotar='camara', espera=dict(packing='u16_le', jpg=False))
    # dump/ no tiene ningún disparo en dos archivos (O + B): se arma uno partiendo en campos un RAW real.
    caso('dos_campos_O_y_B', {'101O1989.RAW': lambda dst: partir_campos(os.path.join(r10, '101O1989.RAW'), dst,
                                                                         dst.replace('O1989', 'B1989'), 4320)},
         espera=dict(layout='filas', packing='u8', ancho=4320, alto=3264))
    # tamaño que no es de ningún modo conocido (M4L sin sus dos últimas filas): todo se detecta de los datos
    caso('tamano_desconocido', {'101O2029.RAW': cortado(d13('101O2029.RAW'), 21_150_720 - 2 * 6480)},
         espera=dict(packing='p12_lsb', ancho=4320, alto=3262))
    caso('archivo_constante', {'101O0001.RAW': lambda dst: open(dst, 'wb').write(bytes(3_000_000))}, espera=dict(error='sin formato posible'))
    rng = np.random.default_rng(531)
    caso('ruido_sin_estructura', {'101O0002.RAW': lambda dst: open(dst, 'wb').write(rng.integers(0, 256, 3_000_000, dtype=np.uint8).tobytes())},
         espera=dict(error='detección poco fiable'))
    return casos


def referencia_python(c, salida):
    """Lo que hace la versión de escritorio con esa carpeta: conversor_ui.convertir_uno (DNG + JPG) y los
    datos completos de m531raw.convertir. Devuelve dict(ok, info, neutro, jpg, giro, ms)."""
    nombres = sorted(os.listdir(c['carpeta']))
    o = [n for n in nombres if n[3] == 'O'][0]
    campos = [os.path.join(c['carpeta'], o)]
    b = os.path.join(c['carpeta'], o[:3] + 'B' + o[4:])
    if os.path.exists(b):
        campos.append(b)
    base = o[:3] + '_' + o[4:8]
    jpg = os.path.join(c['carpeta'], base + '.JPG')
    dng = os.path.join(salida, base + '.DNG')
    capturado = {}
    original = m531raw.escribir_dng

    def espia(ruta, img, cfa, negro, blanco, **kw):
        capturado['neutro'] = [float(x) for x in kw['neutro']]
        return original(ruta, img, cfa, negro, blanco, **kw)
    m531raw.escribir_dng = espia
    try:
        t0 = time.time()
        try:
            info = m531raw.convertir(campos, os.path.join(salida, 'info.dng'), balance=c['balance'], rotar=c['rotar'])
        except SystemExit as e:
            return dict(ok=False, error=str(e), base=base)
        ms = round((time.time() - t0) * 1000)
    finally:
        m531raw.escribir_dng = original
    os.remove(os.path.join(salida, 'info.dng'))
    r = conversor_ui.convertir_uno(campos, dng, jpg if os.path.exists(jpg) and os.path.getsize(jpg) else None, dng[:-4] + '.JPG',
                                   c['balance'], c['rotar'])
    assert r['ok'], r
    giro = r['giro']
    for s in c['giros']:                                   # como conversor_ui.Conversor.girar
        giro = (giro + (1 if s == 'izq' else -1)) % 4
        m531raw.orientar(dng, giro)
        if r['jpg']:
            m531raw.orientar(dng[:-4] + '.JPG', giro)
    return dict(ok=True, info=info, neutro=capturado['neutro'], jpg=r['jpg'], giro=giro, ms=ms, base=base, formato=r['formato'])


def correr_node(trabajos, tmp):
    ruta = os.path.join(tmp, f'trabajos_{len(os.listdir(tmp))}.json')
    json.dump(trabajos, open(ruta, 'w'))
    p = subprocess.run([NODE, os.path.join(AQUI, 'e2e_web_nodo.mjs'), ruta], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return {j['id']: j for j in map(json.loads, p.stdout.splitlines())}


CAMPOS_INFO = ('packing', 'bits', 'ancho', 'alto', 'layout', 'cfa', 'cfa_detectado', 'cfa_rb_provisional', 'cfa_metricas', 'decodificado',
               'max_crudo', 'modo4', 'perfil_camara', 'perfil', 'negro', 'blanco', 'balance', 'neutro', 'giro', 'orientacion', 'awb_camara',
               'quemado', 'parche_blanco_descartado', 'tamanos', 'archivos')


def parte_equivalencia(tmp, informe):
    print('\n== 1. Los módulos de la página (en Node) contra m531raw.py, sobre RAW reales ==')
    casos = preparar_casos(tmp)
    trabajos = []
    for c in casos:
        c['js'] = os.path.join(tmp, 'js', c['nombre'])
        c['py'] = os.path.join(tmp, 'py', c['nombre'])
        os.makedirs(c['js'])
        os.makedirs(c['py'])
        trabajos.append(dict(id=c['nombre'], que='convertir', carpeta=c['carpeta'], salida=c['js'], balance=c['balance'], rotar=c['rotar'],
                             giros=c['giros'], vista=4))
    t0 = time.time()
    res = correr_node(trabajos, tmp)
    informe['node_segundos_total'] = round(time.time() - t0, 1)
    informe['casos'] = {}
    peor_neutro = 0.0
    for c in casos:
        n = c['nombre']
        ref = referencia_python(c, c['py'])
        j = res[n]
        d = informe['casos'][n] = dict(balance_pedido=c['balance'], rotar=c['rotar'], giros=c['giros'])
        if 'excepcion' in j or len(j['fotos']) != 1:
            chequear(False, f'{n}: Node devolvió una foto ({j.get("excepcion", j)})')
            continue
        f = j['fotos'][0]
        if not ref['ok']:
            d.update(error_python=ref['error'], error_js=f.get('error'))
            chequear(not f['ok'] and f.get('motivo') and f['error'].split(' (')[0] == ref['error'].split(' (')[0]
                     and c['espera']['error'] in f['error'], f'{n}: los dos rechazan el archivo con el mismo motivo ({f.get("error", "")[:60]!r})')
            chequear(not os.listdir(c['js']), f'{n}: no queda ningún archivo a medias')
            continue
        if not chequear(f['ok'], f'{n}: JavaScript convierte ({f.get("error", "")})'):
            continue
        a = open(os.path.join(c['py'], ref['base'] + '.DNG'), 'rb').read()
        b = open(os.path.join(c['js'], ref['base'] + '.DNG'), 'rb').read()
        ta, pa = etiquetas(a)
        tb, pb = etiquetas(b)
        distintas = sorted(t for t in set(ta) | set(tb) if ta.get(t) != tb.get(t))
        na, nb = racionales(ta[50728][2]), racionales(tb[50728][2])
        dif_tag = max(abs(x - y) for x, y in zip(na, nb))
        dif_full = max(abs(x - y) for x, y in zip(ref['neutro'], f['neutro']))
        peor_neutro = max(peor_neutro, dif_full)
        dif_info = [k for k in CAMPOS_INFO if ref['info'].get(k) != f['info'].get(k)]
        d.update(formato=f['formato'], balance=f['balance'], neutro_js=f['neutro'], neutro_python=ref['neutro'],
                 dif_neutro_precision_completa=dif_full, dif_neutro_etiqueta=dif_tag, etiquetas_distintas=distintas,
                 dng_identico=a == b, sha256_dng=sha(b), ms_python=ref['ms'], ms_node=f['ms'], giro=f['giro'], jpg=f['jpg'])
        chequear(a[pa:] == b[pb:] and pa == pb, f'{n}: píxeles del DNG idénticos bit a bit ({len(b) - pb} B)')
        chequear(not [t for t in distintas if t != 50728] and len(ta) == len(tb), f'{n}: las {len(tb)} etiquetas TIFF iguales una a una (distintas: {distintas})')
        chequear(dif_tag <= TOL_NEUTRO, f'{n}: AsShotNeutral {[round(x, 6) for x in nb]} dentro de {TOL_NEUTRO} (dif. etiqueta {dif_tag:.1e}, '
                 f'precisión completa {dif_full:.1e})')
        chequear(a == b, f'{n}: el DNG entero es el mismo archivo que el de Python (SHA-256 {sha(b)[:12]})')
        chequear(not dif_info, f'{n}: mismos datos de análisis: {f["formato"]}, balance {f["balance"]} (distintos: {dif_info})')
        cj, cp = f['info']['candidatos'], ref['info']['candidatos']
        if cp:
            dp = max(abs(x['puntaje'] - y['puntaje']) for x, y in zip(cj, cp))
            d.update(candidatos_js=cj[:2], candidatos_python=cp[:2])
            chequear([(x['packing'], x['ancho'], x['bits_usados']) for x in cj] == [(x['packing'], x['ancho'], x['bits_usados']) for x in cp]
                     and dp <= 1e-4, f'{n}: la detección por FFT da los mismos candidatos y anchos (puntajes a {dp:.0e})')
        else:
            chequear(cj == [], f'{n}: formato por tamaño de archivo, sin lista de candidatos')
        chequear(f['jpg'] == ref['jpg'] and f['giro'] == ref['giro'] and f['formato'] == ref['formato'],
                 f'{n}: JPG al lado = {f["jpg"]}, giro {f["giro"]}, igual que conversor_ui.convertir_uno')
        jp, jj = (os.path.join(x, ref['base'] + '.JPG') for x in (c['py'], c['js']))
        if ref['jpg']:
            chequear(os.path.exists(jj) and open(jp, 'rb').read() == open(jj, 'rb').read(),
                     f'{n}: el JPG de salida es idéntico al de Python (orientación EXIF {Image.open(jj).getexif().get(0x112)})')
        else:
            chequear(not os.path.exists(jj), f'{n}: el JPG ausente o roto no se copia')
        for k, v in c['espera'].items():
            real = f.get(k, f['info'].get(k)) if k in ('jpg', 'giro') else f['info'].get(k)
            chequear(real == v, f'{n}: {k} = {real!r} (el caso que se quería cubrir: {v!r})')
        with rawpy.imread(os.path.join(c['js'], ref['base'] + '.DNG')) as rp:
            forma, wb, flip = rp.raw_image.shape, list(rp.camera_whitebalance)[:3], rp.sizes.flip
        chequear(forma == (f['info']['alto'], f['info']['ancho']) and flip == {0: 0, 1: 5, 2: 3, 3: 6}[f['giro']],
                 f'{n}: LibRaw abre el DNG de JavaScript: mosaico {forma}, giro {flip}, balance {[round(x, 3) for x in wb]}')
        c['ok'] = True
        c['base'] = ref['base']
        c['vista'] = f.get('vista')
    informe['peor_dif_neutro_precision_completa'] = peor_neutro
    chequear(len({informe['casos'][n].get('balance') for n in informe['casos']} - {None}) >= 5,
             'los casos cubren las cinco fuentes de balance (jpg, parche_blanco, awb_camara, fijo_modo4, mundo_gris)')

    # ---- JPG: píxeles del decodificador propio contra PIL
    jpgs = dict(p8=os.path.join(DUMP, 'raw10', '101_1988.JPG'), danado_por_disparo_encima=d13('101_2032.JPG'), m4l=d13('101_2037.JPG'))
    r = correr_node([dict(id=k, que='jpeg', jpg=v, salida=os.path.join(tmp, k + '.rgb')) for k, v in jpgs.items()], tmp)
    informe['jpeg_contra_pil'] = {}
    for k, v in jpgs.items():
        pil = np.asarray(Image.open(v).convert('RGB')).astype(np.int16)
        js = np.fromfile(os.path.join(tmp, k + '.rgb'), dtype=np.uint8).reshape(pil.shape).astype(np.int16)
        dmax, dist = int(np.abs(pil - js).max()), int((pil != js).sum())
        informe['jpeg_contra_pil'][k] = dict(dif_max=dmax, valores_distintos=dist, de=int(pil.size))
        chequear(dist == 0, f'JPG {k}: el decodificador propio da los mismos píxeles que PIL ({dist} distintos de {pil.size}, máx. {dmax})')

    # ---- .zip: el mismo escritor que usa la página, con un tope pequeño para forzar el reparto
    listos = [c for c in casos if c.get('ok')]
    archivos = sorted(os.path.join(c['js'], x) for c in listos[:4] for x in os.listdir(c['js']) if x.endswith(('.DNG', '.JPG')))
    # nombres repetidos entre casos no caben en un mismo zip: una copia con el nombre del caso delante
    zdir = os.path.join(tmp, 'zip')
    os.makedirs(zdir)
    planos = []
    for i, a in enumerate(archivos):
        dst = os.path.join(zdir, os.path.basename(os.path.dirname(a))[:3] + os.path.basename(a))
        shutil.copy(a, dst)
        planos.append(dst)
    planos += [os.path.join(zdir, 'ñandú á.DNG')]
    shutil.copy(planos[0], planos[-1])
    limite = 60_000_000                                   # dos DNG de 28 MB por .zip
    r = correr_node([dict(id='reparto', que='zip', archivos=planos, limite=limite, salida=os.path.join(zdir, 'r')),
                     dict(id='uno', que='zip', archivos=planos[:3], salida=os.path.join(zdir, 'u'))], tmp)
    zips = r['reparto']['zips']
    todo = {}
    bien = True
    for z in zips:
        with zipfile.ZipFile(z['ruta']) as zf:
            bien &= zf.testzip() is None and os.path.getsize(z['ruta']) <= limite
            for i in zf.infolist():
                bien &= i.compress_type == zipfile.ZIP_STORED and i.date_time == (2026, 11, 14, 12, 30, 40)
                todo[i.filename] = sha(zf.read(i))
    chequear(len(zips) > 1 and bien, f'.zip: {len(planos)} archivos ({sum(map(os.path.getsize, planos)) >> 20} MB) con tope de {limite >> 20} MB salen en '
             f'{len(zips)} .zip válidos (CRC, sin comprimir, fecha), ninguno pasa del tope')
    chequear(todo == {os.path.basename(p): sha(open(p, 'rb').read()) for p in planos}, '.zip: cada archivo sale una vez y con su contenido exacto (también el nombre con ñ y tilde)')
    juntos = all(len({os.path.basename(z['ruta']) for z in zips if any(x[:-4] == b for x in z['nombres'])}) == 1
                 for b in {os.path.basename(p)[:-4] for p in planos})
    chequear(juntos, '.zip: el DNG y su JPG van siempre en el mismo .zip')
    with zipfile.ZipFile(r['uno']['zips'][0]['ruta']) as zf:
        chequear(len(r['uno']['zips']) == 1 and zf.testzip() is None and len(zf.namelist()) == 3, '.zip: con el tope normal (1,9 GB) un lote chico es un solo .zip')
    p = subprocess.run(['unzip', '-tq', zips[0]['ruta']], capture_output=True, text=True)
    chequear(p.returncode == 0, f'.zip: unzip del sistema también lo da por bueno ({p.stdout.strip()[:60]})')
    informe['zip'] = dict(tope=limite, zips=[dict(nombres=z['nombres'], bytes=os.path.getsize(z['ruta'])) for z in zips])
    return casos


# ---------------------------------------------------------------- 2. la página en Chrome
def cabeceras_de_pages():
    """Las cabeceras de web/_headers (formato de Cloudflare Pages) para la regla /*."""
    cab, dentro = [], False
    for linea in open(os.path.join(WEB, '_headers'), encoding='utf-8'):
        if not linea.strip():
            continue
        if not linea[0].isspace():
            dentro = linea.strip() == '/*'
        elif dentro:
            k, v = linea.strip().split(':', 1)
            cab.append((k.strip(), v.strip()))
    return cab


def servidor():
    pedidos = []
    extra = cabeceras_de_pages()

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=WEB, **kw)

        def log_message(self, fmt, *a):
            pedidos.append((self.command, self.path, a[1] if len(a) > 1 else ''))

        def do_POST(self):
            pedidos.append(('POST', self.path, ''))
            self.send_error(405)
        do_PUT = do_POST

        def end_headers(self):
            for k, v in extra:
                self.send_header(k, v)
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()
    H.extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{'.js': 'text/javascript', '.webmanifest': 'application/manifest+json'})
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, pedidos, dict(extra)


# showDirectoryPicker abre un diálogo del sistema que no se puede manejar sin ventana: en la prueba
# devuelve una carpeta del sistema de archivos privado del navegador (OPFS). El código que escribe los
# archivos (getFileHandle → createWritable → write → close) es el de la página, sin tocar.
SHIM_CARPETA = """
window.showDirectoryPicker = async () => (await navigator.storage.getDirectory()).getDirectoryHandle('elegida', { create: true });
window.__latido = { max: 0, t: performance.now(), n: 0 };
setInterval(() => { const a = performance.now(); window.__latido.max = Math.max(window.__latido.max, a - window.__latido.t); window.__latido.t = a; window.__latido.n++; }, 20);
"""
LEER_CARPETA = """async () => {
  const dir = await (await navigator.storage.getDirectory()).getDirectoryHandle('elegida');
  const out = {};
  for await (const [nombre, h] of dir.entries()) {
    const b = await (await h.getFile()).arrayBuffer();
    const d = new Uint8Array(await crypto.subtle.digest('SHA-256', b));
    out[nombre] = [...d].map(x => x.toString(16).padStart(2, '0')).join('');
  }
  return out;
}"""


def armar_sd(tmp):
    """Una SD de mentira: DCIM/101KM531 con RAW, campo B, JPG (uno roto) y archivos que no son de la cámara."""
    sd = os.path.join(tmp, 'SD')
    dcim = os.path.join(sd, 'DCIM', '101KM531')
    os.makedirs(dcim)
    os.makedirs(os.path.join(sd, 'Batch'))
    r10 = os.path.join(DUMP, 'raw10')
    for n in ('101O2037.RAW', '101_2037.JPG', '101O2029.RAW', '101O2030.RAW', '101_2030.JPG', '101O2032.RAW'):
        shutil.copy(d13(n), dcim)
    open(os.path.join(dcim, '101_2032.JPG'), 'wb').write(open(d13('101_2032.JPG'), 'rb').read()[:400_000])   # disparo encima: JPG cortado
    shutil.copy(os.path.join(r10, '101O1988.RAW'), dcim)
    shutil.copy(os.path.join(r10, '101_1988.JPG'), dcim)
    partir_campos(os.path.join(r10, '101O1989.RAW'), os.path.join(dcim, '101o1989.raw'), os.path.join(dcim, '101b1989.raw'), 4320)
    # lo que no es de la M531: se ignora
    shutil.copy(d13('101_1140.JPG'), os.path.join(dcim, 'IMG_0001.JPG'))        # JPG de otra cámara
    shutil.copy(d13('101_1141.JPG'), os.path.join(dcim, '101_1141.JPG'))        # JPG de la M531 sin RAW
    open(os.path.join(dcim, 'DSC00001.ARW'), 'wb').write(os.urandom(50_000))
    open(os.path.join(dcim, '.DS_Store'), 'wb').write(b'x' * 100)
    open(os.path.join(sd, 'Batch', 'M4L.LOG'), 'w').write('ok\n')
    return sd, dcim


def referencia_sd(dcim, tmp, rotar, giros):
    """Lo que deja la versión de escritorio (conversor_ui.convertir_uno) con esa SD, ya girado."""
    ref = os.path.join(tmp, 'ref_sd')
    os.makedirs(ref)
    entrada = os.path.join(tmp, 'ref_entrada')              # nombres en mayúsculas, como hace conversor_ui.subir
    os.makedirs(entrada)
    for n in os.listdir(dcim):
        if conversor_ui.RE_ARCHIVO.fullmatch(n):
            shutil.copy(os.path.join(dcim, n), os.path.join(entrada, n.upper()))
    out = {}
    for n in sorted(os.listdir(entrada)):
        if n[3] != 'O':
            continue
        base = n[:3] + '_' + n[4:8]
        campos = [os.path.join(entrada, n)] + [p for p in [os.path.join(entrada, n[:3] + 'B' + n[4:])] if os.path.exists(p)]
        jpg = os.path.join(entrada, base + '.JPG')
        dng = os.path.join(ref, base + '.DNG')
        t0 = time.time()
        r = conversor_ui.convertir_uno(campos, dng, jpg if os.path.exists(jpg) else None, dng[:-4] + '.JPG', 'auto', rotar)
        r['ms'] = round((time.time() - t0) * 1000)
        g = r['giro']
        for s in giros.get(base, []):
            g = (g + (1 if s == 'izq' else -1)) % 4
            m531raw.orientar(dng, g)
            if r['jpg']:
                m531raw.orientar(dng[:-4] + '.JPG', g)
        r['giro'] = g
        out[base] = r
    return ref, out


def revelado_libraw(dng, lado):
    """El mismo DNG revelado por LibRaw, sin brillo automático y con el balance del archivo."""
    with rawpy.imread(dng) as rp:
        rgb = rp.postprocess(half_size=True, use_camera_wb=True, no_auto_bright=True, output_bps=8, gamma=(2.4, 12.92))
    im = Image.fromarray(rgb)
    im.thumbnail((lado, lado))
    return im


def esperar(pag, expresion, timeout=30_000):
    """Espera a que la expresión sea cierta en la página. (wait_for_function de Playwright evalúa texto
    dentro de la página y la CSP de web/_headers lo prohíbe; evaluate va por DevTools y no.)"""
    fin = time.time() + timeout / 1000
    while time.time() < fin:
        if pag.evaluate(expresion):
            return
        time.sleep(0.1)
    raise TimeoutError(f'no se cumplió en {timeout} ms: {expresion[:80]}')


def parte_navegador(tmp, informe):
    print('\n== 2. La página en Chrome sin ventana ==')
    from playwright.sync_api import sync_playwright
    srv, pedidos, cab = servidor()
    origen = f'http://127.0.0.1:{srv.server_address[1]}'
    sd, dcim = armar_sd(tmp)
    giros = {'101_2037': ['izq'], '101_2029': ['der']}
    ref, esperado = referencia_sd(dcim, tmp, 'camara', giros)
    nav = informe['navegador'] = {}
    urls, consola = [], []
    with sync_playwright() as pw:
        chrome = pw.chromium.launch(channel='chrome', headless=True)
        nav['chrome'] = chrome.version
        ctx = chrome.new_context(accept_downloads=True, viewport=dict(width=1280, height=900))
        ctx.add_init_script(SHIM_CARPETA)
        ctx.on('request', lambda r: urls.append((r.method, r.url, r.resource_type)))
        pag = ctx.new_page()
        pag.on('console', lambda m: consola.append(f'{m.type}: {m.text}') if m.type in ('error', 'warning') else None)
        pag.on('pageerror', lambda e: consola.append(f'excepción: {e}'))
        pag.goto(origen + '/')
        chequear(pag.title().startswith('Reveal') and pag.inner_text('h1').startswith('Reveal'), f'la página carga y se llama Reveal ({pag.title()!r})')
        chequear("default-src 'none'" in cab.get('Content-Security-Policy', '') and "connect-src 'none'" in cab['Content-Security-Policy'],
                 'se sirve con la CSP de web/_headers (nada externo, sin conexiones)')

        # opciones: se recuerdan al recargar
        pag.click('.seg[data-opc="rotar"] button[data-v="camara"]')
        pag.reload()
        chequear(pag.get_attribute('.seg[data-opc="rotar"] button[data-v="camara"]', 'aria-pressed') == 'true'
                 and pag.get_attribute('.seg[data-opc="balance"] button[data-v="auto"]', 'aria-pressed') == 'true',
                 'Giro = "Como el JPG" se recuerda al recargar; Balance sigue en Auto')

        # archivos ajenos: aviso y ninguna tarjeta
        pag.set_input_files('#elegir', [os.path.join(dcim, 'IMG_0001.JPG'), os.path.join(dcim, 'DSC00001.ARW')])
        pag.wait_for_selector('#aviso.on')
        chequear('Ningún RAW conocido' in pag.inner_text('#aviso') and pag.locator('.foto').count() == 0,
                 f'archivos de otra cámara: aviso y ninguna tarjeta ({pag.inner_text("#aviso")[:50]!r})')

        # la carpeta de la SD entera, por el selector de carpetas
        pag.evaluate('window.__latido.max = 0')
        t0 = time.time()
        pag.set_input_files('#elegir-carpeta', sd)
        esperar(pag, 'document.querySelectorAll(".foto").length === 6')
        esperar(pag, '[...document.querySelectorAll(".foto")].every(f => ["lista", "error"].includes(f.dataset.estado))', timeout=180_000)
        nav['segundos_6_fotos'] = round(time.time() - t0, 1)
        latido = pag.evaluate('window.__latido.max')
        nav['pausa_maxima_de_la_pagina_ms'] = round(latido)
        chequear(latido < 400, f'la página no se traba mientras convierte (pausa máxima del hilo principal {latido:.0f} ms)')
        tarjetas = pag.evaluate('''() => Object.fromEntries([...document.querySelectorAll(".foto")].map(f => [f.querySelector(".nom").textContent,
            { estado: f.dataset.estado, ms: +f.dataset.ms, giro: +f.dataset.giro, camara: f.querySelector(".cam").textContent, meta: f.querySelector(".m").textContent }]))''')
        nav['tarjetas'] = tarjetas
        chequear(sorted(tarjetas) == sorted(esperado) and all(t['estado'] == 'lista' for t in tarjetas.values()),
                 f'una tarjeta por disparo, todas convertidas; los 4 archivos ajenos y el JPG suelto no cuentan ({sorted(tarjetas)})')
        chequear(all(t['camara'] == 'Kodak M531' for t in tarjetas.values()), 'cada tarjeta dice de qué cámara es (Kodak M531)')
        for b, e in sorted(esperado.items()):
            meta = f"{e['formato']} · balance {e['balance'].replace('_', ' ')} · {'con JPG' if e['jpg'] else 'sin JPG'}"
            chequear(tarjetas[b]['meta'] == meta, f'{b}: la tarjeta dice lo mismo que la de escritorio ({meta})')
        chequear(tarjetas['101_1989']['meta'].startswith('u8 4320x3264'), 'los campos 101o1989.raw + 101b1989.raw (minúsculas) se emparejan en una foto')
        chequear('3 DNG' not in pag.inner_text('#cuenta') and '6 DNG listos' in pag.inner_text('#cuenta'), f'resumen: {pag.inner_text("#cuenta")!r}')
        pag.screenshot(path=os.path.join(OUT, 'pagina.png'))

        # girar: ↺ en 2037 (venía vertical como el JPG), ↻ en 2029
        def tarjeta(b):
            return pag.locator('.foto', has=pag.locator('.nom', has_text=b))
        antes = tarjeta('101_2037').locator('canvas').evaluate('c => [c.width, c.height]')
        tarjeta('101_2037').locator('button[data-a="izq"]').click()
        tarjeta('101_2029').locator('button[data-a="der"]').click()
        desp = tarjeta('101_2037').locator('canvas').evaluate('c => [c.width, c.height]')
        chequear(antes == [408, 540] and desp == [540, 408] and tarjeta('101_2037').get_attribute('data-giro') == '2'
                 and tarjeta('101_2029').get_attribute('data-giro') == '3', f'girar cambia la miniatura {antes} → {desp} y el giro (2037: 2, 2029: 3)')

        # visor: clic amplía, espacio alterna DNG/JPG, Esc cierra
        tarjeta('101_1988').locator('.marco').click()
        esperar(pag, 'document.querySelector("#visor").dataset.revelado')
        dims = pag.evaluate('(() => { const c = document.querySelector("#visor canvas"); return [c.width, c.height, getComputedStyle(c).display]; })()')
        chequear(dims[:2] == [1632, 2160] and dims[2] != 'none', f'visor: el DNG se revela a media resolución y de pie como el JPG {dims[:2]}')
        pag.screenshot(path=os.path.join(OUT, 'visor_dng.png'))
        pag.keyboard.press('Space')
        esperar(pag, '(() => { const i = document.querySelector("#visor img"); return !i.hidden && i.complete && i.naturalWidth > 0; })()')
        j = pag.evaluate('(() => { const i = document.querySelector("#visor img"), c = document.querySelector("#visor canvas"); return [i.naturalWidth, i.naturalHeight, c.hidden, document.querySelector(".pie-visor").textContent]; })()')
        chequear(j[:3] == [3216, 4288, True] and 'JPG de la cámara' in j[3], f'visor: espacio cambia al JPG de la cámara {j[:2]}')
        pag.keyboard.press('Space')
        chequear(pag.evaluate('document.querySelector("#visor").dataset.que') == 'dng' and pag.evaluate('document.querySelector("#visor img").hidden'),
                 'visor: espacio otra vez vuelve al DNG')
        pag.keyboard.press('Escape')
        chequear(not pag.evaluate('document.querySelector("#visor").classList.contains("on")'), 'visor: Esc cierra')
        tarjeta('101_2029').locator('.marco').click()
        pag.keyboard.press('Space')
        chequear(pag.evaluate('document.querySelector("#visor").dataset.que') == 'dng', 'visor: una foto sin JPG no cambia con espacio')
        pag.keyboard.press('Escape')

        # vistas previas de la página (para la hoja y para compararlas con LibRaw)
        vistas = {b: Image.open(io.BytesIO(base64.b64decode(tarjeta(b).locator('canvas').evaluate('c => c.toDataURL("image/png")').split(',')[1]))).convert('RGB')
                  for b in sorted(esperado)}

        # descargar todo
        with pag.expect_download(timeout=120_000) as dl:
            pag.click('#zip')
        zruta = os.path.join(tmp, 'todo.zip')
        dl.value.save_as(zruta)
        chequear(re.fullmatch(r'reveal_\d{4}-\d\d-\d\d\.zip', dl.value.suggested_filename) is not None, f'"Descargar todo" baja {dl.value.suggested_filename}')
        zdir = os.path.join(tmp, 'unzip')
        with zipfile.ZipFile(zruta) as zf:
            malo = zf.testzip()
            zf.extractall(zdir)
        quiero = sorted(b + '.DNG' for b in esperado) + sorted(b + '.JPG' for b, e in esperado.items() if e['jpg'])
        chequear(malo is None and sorted(os.listdir(zdir)) == sorted(quiero), f'el .zip es válido y trae {len(quiero)} archivos: 6 DNG y sólo los JPG sanos '
                 f'({sorted(x for x in os.listdir(zdir) if x.endswith("JPG"))})')
        nav['zip_bytes'] = os.path.getsize(zruta)
        etq = {0: 1, 1: 8, 2: 3, 3: 6}
        for b, e in sorted(esperado.items()):
            p = os.path.join(zdir, b + '.DNG')
            if not os.path.exists(p):
                chequear(False, f'{b}.DNG falta en el .zip')
                continue
            datos = open(p, 'rb').read()
            with rawpy.imread(p) as rp:
                forma = rp.raw_image.shape
            orient = struct.unpack('<H', etiquetas(datos)[0][274][2])[0]
            chequear(forma == (3264, 4320) and orient == etq[e['giro']], f'{b}.DNG del navegador: LibRaw lee {forma}, Orientation {orient} (giro {e["giro"]})')
            chequear(datos == open(os.path.join(ref, b + '.DNG'), 'rb').read(), f'{b}.DNG del navegador es byte a byte el de la versión de escritorio')
            if e['jpg']:
                jz = open(os.path.join(zdir, b + '.JPG'), 'rb').read()
                im = Image.open(io.BytesIO(jz))
                im.load()
                chequear(jz == open(os.path.join(ref, b + '.JPG'), 'rb').read() and im.getexif().get(0x112) == etq[(e['giro'] - 1) % 4],
                         f'{b}.JPG: mismo archivo que en escritorio, sin recomprimir, EXIF Orientation {im.getexif().get(0x112)} (se ve igual que el DNG)')
        orig = open(d13('101_2037.JPG'), 'rb').read()
        girado = open(os.path.join(zdir, '101_2037.JPG'), 'rb').read() if os.path.exists(os.path.join(zdir, '101_2037.JPG')) else b''
        chequear(len(orig) == len(girado) and sum(x != y for x, y in zip(orig, girado)) == 1, 'girar el JPG cambia un solo byte del original (la etiqueta), sin pérdida')

        # descarga de una sola foto
        with pag.expect_download() as d1:
            tarjeta('101_2029').locator('button[data-a="bajar"]').click()
        p1 = os.path.join(tmp, 'una.dng')
        d1.value.save_as(p1)
        chequear(d1.value.suggested_filename == '101_2029.DNG' and open(p1, 'rb').read() == open(os.path.join(ref, '101_2029.DNG'), 'rb').read(),
                 'el botón de cada tarjeta baja su DNG, idéntico al de escritorio')

        # guardar en carpeta (File System Access)
        chequear(pag.is_visible('#guardar'), '"Guardar en carpeta" aparece en Chrome (tiene showDirectoryPicker)')
        pag.click('#guardar')
        esperar(pag, 'document.querySelector("#aviso").textContent.includes("guardados")', timeout=120_000)
        guardado = pag.evaluate(LEER_CARPETA)
        chequear(guardado == {n: sha(open(os.path.join(zdir, n), 'rb').read()) for n in os.listdir(zdir)},
                 f'"Guardar en carpeta" escribe los mismos {len(guardado)} archivos que el .zip (SHA-256 leído de la carpeta)')

        # soltar la carpeta (arrastrar y soltar de verdad, por el protocolo de DevTools) reconvierte en sus tarjetas
        try:
            pag.click('.seg[data-opc="balance"] button[data-v="camara"]')
            cdp = ctx.new_cdp_session(pag)
            datos = dict(items=[], files=[os.path.join(sd, 'DCIM')], dragOperationsMask=1)
            for tipo in ('dragEnter', 'dragOver', 'drop'):
                cdp.send('Input.dispatchDragEvent', dict(type=tipo, x=640, y=300, data=datos))
            esperar(pag, '[...document.querySelectorAll(".foto")].some(f => f.dataset.estado !== "lista")', timeout=10_000)
            esperar(pag, '[...document.querySelectorAll(".foto")].every(f => f.dataset.estado === "lista")', timeout=180_000)
            bal = pag.evaluate('Object.fromEntries([...document.querySelectorAll(".foto")].map(f => [f.querySelector(".nom").textContent, f.dataset.balance]))')
            nav['balance_camara_al_soltar'] = bal
            chequear(len(bal) == 6 and bal['101_2037'] == 'awb_camara' and bal['101_2029'] == 'parche_blanco',
                     f'soltar la carpeta DCIM con Balance = Cámara reconvierte las 6 en sus tarjetas: {bal["101_2037"]} con JPG, {bal["101_2029"]} sin JPG')
        except Exception as e:
            chequear(False, f'soltar la carpeta sobre la página ({str(e)[:120]})')
        pag.click('.seg[data-opc="balance"] button[data-v="auto"]')
        ctx.close()

        # teléfono, modo oscuro
        movil = chrome.new_context(viewport=dict(width=390, height=844), device_scale_factor=2, color_scheme='dark', is_mobile=True, has_touch=True)
        movil.on('request', lambda r: urls.append((r.method, r.url, r.resource_type)))
        pm = movil.new_page()
        pm.on('console', lambda m: consola.append(f'móvil {m.type}: {m.text}') if m.type in ('error', 'warning') else None)
        pm.goto(origen + '/')
        pm.set_input_files('#elegir', [os.path.join(dcim, n) for n in ('101O2037.RAW', '101_2037.JPG', '101O1988.RAW', '101_1988.JPG')])
        esperar(pm, 'document.querySelectorAll(".foto[data-estado=lista]").length === 2', timeout=120_000)
        m = pm.evaluate('''() => ({ ancho: document.documentElement.scrollWidth, vista: innerWidth, fondo: getComputedStyle(document.body).backgroundColor,
            texto: getComputedStyle(document.body).color, boton: Math.min(...[...document.querySelectorAll(".ic")].map(b => b.getBoundingClientRect().width)),
            tarjeta: document.querySelector(".foto").getBoundingClientRect().width })''')
        nav['telefono'] = m
        pm.screenshot(path=os.path.join(OUT, 'telefono_oscuro.png'), full_page=True)
        chequear(m['ancho'] <= m['vista'] and m['tarjeta'] > 340 and m['boton'] >= 40, f'a 390 px no hay desborde horizontal, tarjeta a todo el ancho, botones de {m["boton"]:.0f} px')
        chequear(m['fondo'] == 'rgb(22, 21, 19)' and m['texto'] == 'rgb(236, 232, 225)', f'modo oscuro: fondo {m["fondo"]}, texto {m["texto"]}')
        movil.close()
        chrome.close()
    srv.shutdown()

    # ---- red: sólo sus propios archivos
    ajenas = [u for u in urls if not u[1].startswith((origen + '/', 'blob:' + origen))]
    propios = {'/' + os.path.relpath(os.path.join(d, f), WEB) for d, _, fs in os.walk(WEB) for f in fs} | {'/'}
    raros = [p for p in pedidos if p[0] != 'GET' or p[1].split('?')[0] not in propios or str(p[2]) not in ('200', '304')]
    nav['pedidos_al_servidor'] = sorted({p[1] for p in pedidos})
    nav['consola'] = consola
    chequear(not ajenas, f'la página no pidió nada fuera de su origen en {len(urls)} peticiones ({ajenas[:3]})')
    chequear(not raros and len(pedidos) > 10, f'el servidor sólo vio GET de archivos de web/ ({len({p[1] for p in pedidos})} distintos, ningún envío de datos; raros: {raros[:3]})')
    chequear(not consola, f'sin errores ni avisos en la consola (la CSP no bloquea nada): {consola[:3]}')
    informe['navegador']['ms_por_raw_navegador'] = {b: t['ms'] for b, t in tarjetas.items()}
    informe['navegador']['ms_por_raw_python'] = {b: e['ms'] for b, e in esperado.items()}

    # ---- vista previa de la página contra el revelado de LibRaw del mismo DNG; hoja de contactos
    lado = 300
    hoja = Image.new('RGB', (len(vistas) * (lado + 10) + 10, 2 * (lado + 24) + 10), (32, 32, 32))
    dib = ImageDraw.Draw(hoja)
    nav['vista_previa_contra_libraw'] = {}
    for i, (b, v) in enumerate(sorted(vistas.items())):
        lr = revelado_libraw(os.path.join(ref, b + '.DNG'), lado)
        # la miniatura se capturó tras girar en la página; la referencia de LibRaw ya trae ese giro (etiqueta del DNG)
        v2 = v.copy()
        v2.thumbnail((lado, lado))
        misma_forma = abs(v2.width - lr.width) <= 2 and abs(v2.height - lr.height) <= 2
        a = np.asarray(v2.resize(lr.size), np.float64)
        r = np.asarray(lr, np.float64)
        dif = float(np.abs(a - r).mean())
        dif180 = float(np.abs(a[::-1, ::-1] - r).mean())
        corr = float(np.corrcoef(a.mean(2).ravel(), r.mean(2).ravel())[0, 1])
        tinte = [float(x) for x in (a.reshape(-1, 3).mean(0) / a.mean() - r.reshape(-1, 3).mean(0) / r.mean())]
        nav['vista_previa_contra_libraw'][b] = dict(dif_media_0_255=round(dif, 1), dif_media_girada_180=round(dif180, 1), correlacion=round(corr, 4),
                                                    tinte_rgb=[round(x, 3) for x in tinte])
        chequear(misma_forma and corr > 0.97 and dif < dif180 and max(map(abs, tinte)) < 0.06,
                 f'{b}: la vista previa es el mismo DNG que revela LibRaw (correlación {corr:.3f}, dif. media {dif:.1f}/255, tinte máx. {max(map(abs, tinte)):.3f}, mismo lado arriba)')
        x = 10 + i * (lado + 10)
        hoja.paste(v2, (x + (lado - v2.width) // 2, 24 + (lado - v2.height) // 2))
        hoja.paste(lr, (x + (lado - lr.width) // 2, lado + 48 + (lado - lr.height) // 2))
        dib.text((x, 6), f'{b}  Reveal (JS)', fill=(230, 230, 230))
        dib.text((x, lado + 30), f'{b}  LibRaw', fill=(230, 230, 230))
    hoja.save(os.path.join(OUT, 'hoja.jpg'), quality=88)


def parte_paquete(informe):
    print('\n== 3. Lo que se publica (web/) ==')
    archivos = sorted(os.path.relpath(os.path.join(d, f), WEB) for d, _, fs in os.walk(WEB) for f in fs)
    tam = {a: os.path.getsize(os.path.join(WEB, a)) for a in archivos}
    informe['paquete'] = dict(archivos=tam, bytes=sum(tam.values()))
    texto = {a: open(os.path.join(WEB, a), encoding='utf-8').read() for a in archivos}
    personal = [(a, m.group(0)) for a, t in texto.items() for m in re.finditer(r'/Volumes|/Users/|sebasti[aá]n|l[oó]pez|PhotoVault|dump/', t, re.I)]
    chequear(not personal, f'web/ no lleva rutas personales, nombres ni referencias a dump/ ({personal[:3]})')
    externos = [(a, m.group(0)) for a, t in texto.items() for m in re.finditer(r'https?://(?!www\.w3\.org/2000/svg)[^\s"\'<>)]+', t)]
    chequear(not externos, f'ningún archivo de web/ apunta a otro servidor ({externos[:3]})')
    chequear(not [a for a in archivos if a.lower().endswith(('.jpg', '.jpeg', '.png', '.raw', '.dng', '.bin'))] and 'package.json' not in archivos,
             f'sin fotos, binarios ni dependencias: {len(archivos)} archivos de texto, {sum(tam.values()) / 1024:.0f} KB')
    usa_red = [(a, m.group(0)) for a, t in texto.items() if a.endswith('.js')
               for m in re.finditer(r'\bfetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|EventSource|importScripts', t)]
    chequear(not usa_red, f'el código no usa fetch, XHR, WebSocket ni sendBeacon ({usa_red[:3]})')
    dom = [(a, m.group(0)) for a, t in texto.items() if a.startswith(('js/comun/', 'js/camaras/'))
           for m in re.finditer(r'\b(document|window|navigator|localStorage)\b\.', t)]
    chequear(not dom, f'los módulos de conversión (js/comun, js/camaras) no tocan el DOM: son los mismos en Node y en el Worker ({dom[:3]})')


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    tmp = tempfile.mkdtemp(prefix='e2e_web_')
    informe = dict(node=subprocess.run([NODE, '--version'], capture_output=True, text=True).stdout.strip(), tolerancia_neutro=TOL_NEUTRO)
    try:
        casos = parte_equivalencia(tmp, informe)
        parte_navegador(tmp, informe)
        parte_paquete(informe)
        ok = [c for c in casos if c.get('ok')]
        informe['resumen_tiempos_ms'] = dict(
            python_por_raw=round(float(np.mean([informe['casos'][c['nombre']]['ms_python'] for c in ok]))),
            node_por_raw=round(float(np.mean([informe['casos'][c['nombre']]['ms_node'] for c in ok]))),
            navegador_por_raw=round(float(np.mean(list(informe['navegador']['ms_por_raw_navegador'].values())))),
            python_mismas_fotos_que_el_navegador=round(float(np.mean(list(informe['navegador']['ms_por_raw_python'].values())))))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        informe['fallas'] = FALLAS
        informe['comprobaciones'] = HECHAS[0]
        json.dump(informe, open(os.path.join(OUT, 'reporte.json'), 'w'), indent=1, ensure_ascii=False)
    print(f"\n{HECHAS[0] - len(FALLAS)} de {HECHAS[0]} comprobaciones bien · {'TODO BIEN' if not FALLAS else f'{len(FALLAS)} FALLAS'} · artefacto en {OUT}/")
    return 1 if FALLAS else 0


if __name__ == '__main__':
    sys.exit(main())
