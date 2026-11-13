#!/usr/bin/env python3
"""Prueba E2E de ./importar (tools/importar_sd.py) sobre una SD de mentira hecha con fotos reales de dump/.

Cómo puede fallar la importación (escrito antes del código):
  1. La SD no está montada → mensaje claro, código 2, nada creado.
  2. El destino cae dentro de la SD → se niega (código 2).
  3. Se escribe algo en la SD (un índice, un temporal, una fecha de acceso cambiada a mano).
  4. Una copia sale distinta del original y queda con el nombre final.
  5. Un archivo ya importado en otra sesión (otra carpeta, incluso una dump/rawNN vieja) se duplica.
  6. Un archivo nuevo con el nombre de uno ya importado (otro contenido) se salta o pisa al anterior.
  7. Un RAW sin JPG (modo 3) o con el JPG de 0 bytes (cuelgue) no se convierte.
  8. Un RAW ilegible (truncado) o un archivo que la SD no deja leer detiene a los demás, o pasa sin aviso.
  9. Basura de macOS en la tarjeta (._archivo, .DS_Store) o scripts .srt se toman por fotos o logs.
 10. El DNG no lleva los datos del RAW, o DNG y JPG quedan con orientaciones distintas.
 11. Repetir la importación recopia o reconvierte.
 12. Un .LOG con el mismo nombre y otro contenido (otra sesión) pisa al anterior.

La SD de mentira se deja sin permiso de escritura durante la prueba y se compara entera (nombres, tamaños,
fechas y SHA-256) antes y después. Las verdades son independientes del importador: SHA-256 de los
originales de dump/, `shasum -c`, los bytes del RAW contra el mosaico que LibRaw lee del DNG, y el JPG de
la cámara contra el revelado del DNG.

Artefacto: work/e2e_importar/reporte.json y hoja.png (los DNG revelados como los muestra un visor).
uso: .venv/bin/python tools/e2e_importar.py
"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time

import numpy as np
import rawpy
from PIL import Image, ImageOps

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DUMP = os.path.join(RAIZ, 'dump')
SALIDA = os.path.join(RAIZ, 'work', 'e2e_importar')
FECHA = '2031-02-03'
DARKTABLE = '/Applications/darktable.app/Contents/MacOS/darktable-cli'
# (archivo de dump/, qué es)
FOTOS = ['raw20/101O2020.RAW', 'raw20/101_2020.JPG',      # M4L, se importa como vertical
         'raw20/101O2019.RAW', 'raw20/101_2019.JPG',      # M4L con flash y 29 % quemado
         'raw8/101O1986.RAW', 'raw8/101_1986.JPG',        # modo 0 (P8)
         'raw12/101O1992.RAW',                            # modo 3, sin JPG
         'raw8/101O1987.RAW', 'raw8/101_1987.JPG',        # modo 0 con el JPG de 0 bytes
         'raw6/101O1981.RAW', 'raw6/101_1981.JPG']        # P9, ya importada en una carpeta vieja
LOGS = ['raw20/M4L.LOG', 'raw20/M4Q.LOG', 'raw20/M4W.LOG']
SEGUNDA = ['raw20/101O2021.RAW', 'raw20/101_2021.JPG']   # llegan en la tercera pasada


def sha(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def foto_sd(sd):
    """Estado completo de la SD: ruta → (tamaño, mtime, modo, sha)."""
    r = {}
    for d, dirs, fs in os.walk(sd):
        st = os.stat(d)
        r[os.path.relpath(d, sd) + '/'] = (st.st_mtime_ns, stat.S_IMODE(st.st_mode))
        for f in fs:
            p = os.path.join(d, f)
            st = os.stat(p)
            legible = stat.S_IMODE(st.st_mode) & 0o400
            r[os.path.relpath(p, sd)] = (st.st_size, st.st_mtime_ns, stat.S_IMODE(st.st_mode), sha(p) if legible else None)
    return r


def proteger(sd, activar):
    for d, dirs, fs in os.walk(sd, topdown=False):
        for f in fs:
            p = os.path.join(d, f)
            if stat.S_IMODE(os.stat(p).st_mode) != 0:            # el ilegible se queda ilegible
                os.chmod(p, 0o444 if activar else 0o644)
        mt = os.stat(d).st_mtime_ns
        os.chmod(d, 0o555 if activar else 0o755)
        os.utime(d, ns=(mt, mt))


def importar(sd, copias, fotos, *extra, origen=None):
    p = subprocess.run([os.path.join(RAIZ, 'importar'), '--origen', origen or os.path.join(sd, 'DCIM', '101KM531'),
                        '--copias', copias, '--destino', fotos, '--fecha', FECHA, *extra], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def arbol(d):
    return {os.path.relpath(os.path.join(a, f), d): (os.path.getsize(os.path.join(a, f)), os.stat(os.path.join(a, f)).st_mtime_ns)
            for a, _, fs in os.walk(d) for f in fs} if os.path.isdir(d) else {}


def mostrado(ruta, lado=400):
    """Verde de la imagen tal como la enseña un visor (con la etiqueta de orientación aplicada)."""
    if ruta.upper().endswith('.DNG'):
        with rawpy.imread(ruta) as rp:
            a = rp.postprocess(use_camera_wb=True, half_size=True, output_bps=8)   # LibRaw aplica Orientation
        im = Image.fromarray(a)
    else:
        im = ImageOps.exif_transpose(Image.open(ruta).convert('RGB'))
    return im


def parecido(a, b):
    if (a.size[0] > a.size[1]) != (b.size[0] > b.size[1]):
        return -1.0
    x = np.asarray(a.convert('L').resize((96, 96))).astype(float).ravel()
    y = np.asarray(b.convert('L').resize((96, 96))).astype(float).ravel()
    return float(np.corrcoef(x, y)[0, 1])


def main():
    faltan = [f for f in FOTOS + LOGS + SEGUNDA + ['raw19/101O2017.RAW'] if not os.path.exists(os.path.join(DUMP, f))]
    if faltan:
        print('OMITIDO: faltan fotos de dump/:', faltan[:3])
        return 0
    if os.path.isdir(SALIDA):
        for d, _, _ in os.walk(SALIDA):
            os.chmod(d, 0o755)
        shutil.rmtree(SALIDA)
    sd, copias, fotos = (os.path.join(SALIDA, x) for x in ('SD', 'copias', 'fotos'))
    dcim, batch = os.path.join(sd, 'DCIM', '101KM531'), os.path.join(sd, 'Batch')
    os.makedirs(dcim); os.makedirs(batch)
    for f in FOTOS:
        shutil.copy2(os.path.join(DUMP, f), dcim)
    for f in LOGS:
        shutil.copy2(os.path.join(DUMP, f), batch)
    open(os.path.join(batch, 'M4L.srt'), 'w').write('no es un log\n')
    open(os.path.join(dcim, '._101O2020.RAW'), 'wb').write(b'\0' * 4096)          # basura de macOS
    open(os.path.join(dcim, '.DS_Store'), 'wb').write(b'\0' * 100)
    open(os.path.join(dcim, '101O9999.RAW'), 'wb').write(open(os.path.join(DUMP, 'raw20/101O2020.RAW'), 'rb').read(1_000_001))  # truncado
    shutil.copy2(os.path.join(DUMP, 'raw20/101_2021.JPG'), os.path.join(dcim, '101_8888.JPG'))
    os.chmod(os.path.join(dcim, '101_8888.JPG'), 0)                                # la SD no lo deja leer
    # importación vieja, hecha a mano: carpeta con SHA256SUMS como las dump/rawNN
    vieja = os.path.join(copias, 'raw6')
    os.makedirs(vieja)
    with open(os.path.join(vieja, 'SHA256SUMS'), 'w') as f:
        for n in ('101O1981.RAW', '101_1981.JPG'):
            shutil.copy2(os.path.join(DUMP, 'raw6', n), vieja)
            f.write(f"{sha(os.path.join(vieja, n))}  {n}\n")

    rep = dict(fecha=time.strftime('%Y-%m-%dT%H:%M:%S'), pasos=[])
    fallos = []

    def exigir(nombre, cond, detalle=''):
        rep['pasos'].append(dict(caso=nombre, ok=bool(cond), detalle=str(detalle)[:300]))
        print(('OK   ' if cond else 'FALLO'), nombre, '' if cond else detalle)
        if not cond:
            fallos.append(nombre)

    # ---- sin SD y con destino dentro de la SD
    c, out = importar(sd, copias, fotos, origen=os.path.join(SALIDA, 'no_existe', 'DCIM', '101KM531'))
    exigir('sin SD: código 2 y nada creado', c == 2 and not os.path.exists(fotos) and os.listdir(copias) == ['raw6'], out)
    c, out = importar(sd, os.path.join(dcim, 'copias'), fotos)
    exigir('destino dentro de la SD: se niega', c == 2 and not os.path.exists(os.path.join(dcim, 'copias')), out)

    proteger(sd, True)
    antes = foto_sd(sd)

    # ---- primera pasada
    c, out = importar(sd, copias, fotos, '--verticales', '2020')
    rep['salida_primera_pasada'] = out
    dia, pics = os.path.join(copias, FECHA), os.path.join(fotos, FECHA)
    exigir('primera pasada: código 1 por el RAW truncado y el archivo ilegible, y los nombra',
           c == 1 and '101O9999.RAW' in out and '101_8888.JPG' in out, out[-600:])
    esperados = [os.path.basename(f) for f in FOTOS if '1981' not in f] + [os.path.basename(f) for f in LOGS] + ['101O9999.RAW']
    presentes = sorted(f for f in os.listdir(dia) if f != 'SHA256SUMS') if os.path.isdir(dia) else []
    exigir('copias: están las nuevas y sólo ésas (ni la ya importada, ni basura de macOS, ni .srt, ni la ilegible)',
           presentes == sorted(esperados), presentes)
    iguales = all(sha(os.path.join(dia, os.path.basename(f))) == sha(os.path.join(DUMP, f)) for f in FOTOS + LOGS if '1981' not in f)
    exigir('copias: SHA-256 igual al del original de dump/', iguales)
    chk = subprocess.run(['shasum', '-a', '256', '-c', 'SHA256SUMS'], cwd=dia, capture_output=True, text=True)
    exigir('copias: SHA256SUMS completo y aprobado por shasum -c',
           chk.returncode == 0 and chk.stdout.count(': OK') == len(esperados), chk.stdout + chk.stderr)
    exigir('copias: sin temporales', not [f for f in os.listdir(dia) if f.endswith('.parcial')])
    exigir('copias: conservan la fecha del archivo de la SD',
           os.stat(os.path.join(dia, '101O2019.RAW')).st_mtime_ns == os.stat(os.path.join(dcim, '101O2019.RAW')).st_mtime_ns)
    dngs = sorted(f for f in os.listdir(pics) if f.endswith('.DNG')) if os.path.isdir(pics) else []
    exigir('DNG: uno por RAW legible, incluidos el de modo 3 sin JPG y el del JPG vacío; ninguno de la ya importada ni del truncado',
           dngs == ['101_1986.DNG', '101_1987.DNG', '101_1992.DNG', '101_2019.DNG', '101_2020.DNG'], dngs)
    jpgs = sorted(f for f in os.listdir(pics) if f.endswith('.JPG')) if os.path.isdir(pics) else []
    exigir('JPG al lado del DNG, sin el de 0 bytes', jpgs == ['101_1986.JPG', '101_2019.JPG', '101_2020.JPG'], jpgs)
    if len(dngs) == 5:
        # los datos del DNG son los del RAW: M4L (12 bits empaquetados) y modo 3 (u16) byte a byte
        with rawpy.imread(os.path.join(pics, '101_2019.DNG')) as rp:
            m = rp.raw_image.copy().ravel()
        bits = ((m[:, None] >> np.arange(12)) & 1).astype(np.uint8).ravel()
        exigir('DNG M4L: su mosaico reempaquetado da los bytes del RAW de la cámara',
               np.packbits(bits, bitorder='little').tobytes() == open(os.path.join(DUMP, 'raw20/101O2019.RAW'), 'rb').read())
        with rawpy.imread(os.path.join(pics, '101_1992.DNG')) as rp:
            m3 = rp.raw_image.copy()
        exigir('DNG modo 3: mosaico idéntico al RAW', m3.astype('<u2').tobytes() == open(os.path.join(DUMP, 'raw12/101O1992.RAW'), 'rb').read())
        res = {x['raw']: x for x in json.load(open(os.path.join(pics, 'resumen.json')))}
        exigir('resumen: balance de cada formato (cámara con flash quemado, escena en M4L y modo 3, JPG en modo 0)',
               (res['101O2019.RAW']['balance'], res['101O2020.RAW']['balance'], res['101O1986.RAW']['balance'],
                res['101O1992.RAW']['balance'], res['101O9999.RAW']['estado'], res['101O1992.RAW']['jpg'])
               == ('awb_camara', 'parche_blanco', 'jpg', 'parche_blanco', 'error', False), res)
        # orientación: como lo enseña un visor
        vistas = {n: mostrado(os.path.join(pics, n)) for n in dngs + jpgs}
        exigir('orientación: todo apaisado salvo la 2020 (--verticales), DNG y JPG',
               all((v.size[1] > v.size[0]) == ('2020' in n) for n, v in vistas.items()), {n: v.size for n, v in vistas.items()})
        pares = {n: round(parecido(vistas[f'101_{n}.DNG'], vistas[f'101_{n}.JPG']), 3) for n in ('1986', '2019', '2020')}
        rep['parecido_dng_jpg'] = pares
        exigir('orientación: el DNG mostrado coincide con el JPG mostrado (ni girado ni cabeza abajo)',
               all(v > 0.8 for v in pares.values()), pares)
        # los motores que usa el usuario: el de macOS (Vista Previa, sips) y darktable, sobre la vertical y una apaisada
        motores = {}
        for num in ('2020', '2019'):
            dng = os.path.join(pics, f'101_{num}.DNG')
            sal = os.path.join(SALIDA, f'{num}_sips.jpg')
            subprocess.run(['sips', '-s', 'format', 'jpeg', '-Z', '600', dng, '--out', sal], capture_output=True)
            # sips no gira los píxeles: pasa la orientación al JPG que escribe, como etiqueta
            motores[f'sips_{num}'] = round(parecido(mostrado(sal), vistas[f'101_{num}.JPG']), 3) if os.path.exists(sal) else -2
            subprocess.run(['qlmanage', '-t', '-s', '600', '-o', SALIDA, dng], capture_output=True)      # Finder y Vista Previa
            sal = os.path.join(SALIDA, f'101_{num}.DNG.png')
            motores[f'quicklook_{num}'] = round(parecido(Image.open(sal).convert('RGB'), vistas[f'101_{num}.JPG']), 3) if os.path.exists(sal) else -2
            if os.path.exists(DARKTABLE):
                sal, conf = os.path.join(SALIDA, f'{num}_darktable.jpg'), os.path.join(SALIDA, 'darktable_conf')
                subprocess.run([DARKTABLE, dng, sal, '--width', '600', '--height', '600', '--hq', 'false', '--apply-custom-presets', 'false',
                                '--core', '--configdir', conf, '--cachedir', conf, '--library', ':memory:'], capture_output=True, cwd=SALIDA)
                motores[f'darktable_{num}'] = round(parecido(Image.open(sal).convert('RGB'), vistas[f'101_{num}.JPG']), 3) if os.path.exists(sal) else -2
                shutil.rmtree(conf, ignore_errors=True)
        rep['parecido_motores_jpg'] = motores
        exigir('orientación: el motor de macOS y darktable enseñan el DNG como el JPG (vertical la 2020, apaisada la 2019)',
               all(v > 0.8 for v in motores.values()), motores)
        a = open(os.path.join(pics, '101_2019.JPG'), 'rb').read(); b = open(os.path.join(dia, '101_2019.JPG'), 'rb').read()
        dif = sum(x != y for x, y in zip(a, b)) if len(a) == len(b) else -1
        exigir('JPG al lado del DNG: mismo archivo salvo la etiqueta de orientación (1 o 2 bytes)', 1 <= dif <= 2, dif)
        hoja = Image.new('RGB', (5 * 260, 2 * 260), (30, 30, 30))
        for i, n in enumerate(dngs):
            for j, v in enumerate((vistas[n], vistas.get(n[:-3] + 'JPG'))):
                if v is not None:
                    t = v.copy(); t.thumbnail((250, 250)); hoja.paste(t, (i * 260 + 5, j * 260 + 5))
        hoja.save(os.path.join(SALIDA, 'hoja.png'))

    # ---- segunda pasada: nada nuevo
    a1, p1 = arbol(dia), {k: v for k, v in arbol(pics).items() if k != 'resumen.json'}
    c, out = importar(sd, copias, fotos, '--verticales', '2020')
    rep['salida_segunda_pasada'] = out
    exigir('segunda pasada: no recopia ni reconvierte',
           arbol(dia) == a1 and {k: v for k, v in arbol(pics).items() if k != 'resumen.json'} == p1 and 'Nada nuevo' in out, out[-400:])
    exigir('SD intacta tras dos pasadas (nombres, tamaños, fechas, permisos y SHA-256)', foto_sd(sd) == antes)

    # ---- tercera pasada: fotos nuevas, un nombre repetido con otro contenido y un log distinto
    proteger(sd, False)
    for f in SEGUNDA:
        shutil.copy2(os.path.join(DUMP, f), dcim)
    os.remove(os.path.join(dcim, '101O2019.RAW'))
    shutil.copy2(os.path.join(DUMP, 'raw19/101O2017.RAW'), os.path.join(dcim, '101O2019.RAW'))   # mismo nombre, otra foto
    open(os.path.join(batch, 'M4L.LOG'), 'a').write('VERIFY: otra sesion\r\n')
    os.remove(os.path.join(dcim, '101O9999.RAW')); os.chmod(os.path.join(dcim, '101_8888.JPG'), 0o644); os.remove(os.path.join(dcim, '101_8888.JPG'))
    sha_log = sha(os.path.join(batch, 'M4L.LOG'))
    proteger(sd, True)
    antes = foto_sd(sd)
    c, out = importar(sd, copias, fotos)
    rep['salida_tercera_pasada'] = out
    dia2, pics2 = os.path.join(copias, FECHA + '_2'), os.path.join(fotos, FECHA + '_2')
    exigir('tercera pasada: sin errores', c == 0, out[-600:])
    en2 = sorted(f for f in os.listdir(dia2) if f != 'SHA256SUMS') if os.path.isdir(dia2) else []
    exigir('nombre repetido con otro contenido: va a una carpeta nueva junto con lo nuevo; no pisa ni se salta',
           en2 == ['101O2019.RAW', '101O2021.RAW', '101_2021.JPG', 'M4L.LOG']
           and sha(os.path.join(dia2, '101O2019.RAW')) == sha(os.path.join(DUMP, 'raw19/101O2017.RAW'))
           and sha(os.path.join(dia, '101O2019.RAW')) == sha(os.path.join(DUMP, 'raw20/101O2019.RAW')), en2)
    exigir('log con el mismo nombre y otro contenido: se guardan los dos',
           os.path.isdir(dia2) and sha(os.path.join(dia2, 'M4L.LOG')) == sha_log
           and sha(os.path.join(dia, 'M4L.LOG')) == sha(os.path.join(DUMP, 'raw20/M4L.LOG')))
    d2 = sorted(os.listdir(pics2)) if os.path.isdir(pics2) else []
    exigir('tercera pasada: DNG de lo nuevo, apaisados', d2 == ['101_2019.DNG', '101_2021.DNG', '101_2021.JPG', 'resumen.json']
           and all(mostrado(os.path.join(pics2, n)).size[0] > mostrado(os.path.join(pics2, n)).size[1] for n in d2 if n != 'resumen.json'), d2)
    exigir('SD intacta tras la tercera pasada', foto_sd(sd) == antes)
    exigir('en toda la prueba no apareció nada en la SD fuera de lo que puso la prueba',
           sorted(os.listdir(sd)) == ['Batch', 'DCIM'] and not [f for f in os.listdir(dcim) if 'parcial' in f or f.endswith('.json')])

    proteger(sd, False)
    rep['arbol_final'] = {k: v[0] for k, v in sorted({**arbol(copias), **{'fotos/' + k: v for k, v in arbol(fotos).items()}}.items())}
    rep['sha256_copias'] = {os.path.join(os.path.basename(d), n): h for d in (dia, dia2) if os.path.isdir(d)
                            for h, n in (l.split() for l in open(os.path.join(d, 'SHA256SUMS')))}
    rep['resultado'] = 'OK' if not fallos else f'{len(fallos)} fallo(s): {fallos}'
    for d in (sd, copias, fotos):                      # ~450 MB de copias: el artefacto es el reporte y la hoja
        shutil.rmtree(d, ignore_errors=True)
    json.dump(rep, open(os.path.join(SALIDA, 'reporte.json'), 'w'), indent=1, ensure_ascii=False)
    print('reporte:', os.path.join(SALIDA, 'reporte.json'), '→', rep['resultado'])
    return 1 if fallos else 0


if __name__ == '__main__':
    sys.exit(main())
