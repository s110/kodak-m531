#!/usr/bin/env python3
"""Prueba E2E del conversor con interfaz (tools/conversor_ui.py), por HTTP como lo usa la página,
con fotos reales de dump/.

Cómo puede fallar (escrito antes de la prueba):
  1. Otra web o un Host falso (DNS rebinding) llama a la API: debe responder 403 sin token o con Host ajeno.
  2. /api/vista o /api/girar leen o tocan archivos fuera del destino (../, rutas absolutas).
  3. Un nombre que no es de la M531, o un archivo vacío (JPG de 0 B tras un cuelgue), se acepta o tumba al resto.
  4. Varias conversiones a la vez (la página manda 3) se pisan, o una falla deja un .parcial o un DNG a medias.
  5. Un RAW sin JPG, o con el JPG truncado (disparo encima), no se convierte, o el JPG roto se copia al destino.
  6. Formatos distintos (M4L de 12 bits, P8 de 8 bits) se convierten con el formato equivocado.
  7. Girar cambia sólo el DNG y deja el JPG con otra orientación, o la vista previa no cambia.
  8. "Importar de la SD" escribe en la SD, no devuelve los DNG nuevos, o reconvierte lo ya importado.
  9. La vista previa no corresponde a lo que macOS muestra del DNG.
Artefacto: work/e2e_conversor/reporte.json y hoja.jpg (las vistas previas que sirvió la página).
uso: .venv/bin/python tools/e2e_conversor.py
"""
import concurrent.futures as cf
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import numpy as np
import rawpy
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DUMP = os.path.join(RAIZ, 'dump')
OUT = os.path.join(RAIZ, 'work', 'e2e_conversor')

FALLAS = []


def chequear(cond, msg):
    print(('ok    ' if cond else 'FALLA ') + msg, flush=True)
    if not cond:
        FALLAS.append(msg)


def huella(carpeta):
    h = {}
    for d, _, fs in os.walk(carpeta):
        for f in fs:
            p = os.path.join(d, f)
            st = os.stat(p)
            h[os.path.relpath(p, carpeta)] = (st.st_size, st.st_mtime_ns, hashlib.sha256(open(p, 'rb').read()).hexdigest())
    return h


class Cliente:
    def __init__(self, puerto, token):
        self.base, self.token = f'http://127.0.0.1:{puerto}', token

    def pedir(self, ruta, cuerpo=None, token=True, host=None, cab=None):
        h = dict(cab or {})
        if token:
            h['X-Token'] = self.token
        if host:
            h['Host'] = host
        datos = None
        if cuerpo is not None:
            datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
        r = urllib.request.Request(self.base + ruta, data=datos, headers=h, method='POST' if datos is not None else 'GET')
        try:
            with urllib.request.urlopen(r, timeout=120) as resp:
                cuerpo = resp.read()
                return resp.status, (json.loads(cuerpo) if resp.headers.get_content_type() == 'application/json' else cuerpo)
        except urllib.error.HTTPError as e:
            b = e.read()
            try:
                return e.code, json.loads(b)
            except Exception:
                return e.code, b

    def subir(self, nombre, datos):
        return self.pedir('/api/subir', datos, cab={'X-Nombre': urllib.request.quote(nombre)})


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    tmp = tempfile.mkdtemp(prefix='e2e_conv_')
    destino, copias = os.path.join(tmp, 'dng'), os.path.join(tmp, 'copias')
    sd = os.path.join(tmp, 'SD')
    dcim = os.path.join(sd, 'DCIM', '101KM531')
    os.makedirs(dcim)
    os.makedirs(os.path.join(sd, 'Batch'))
    d13 = os.path.join(DUMP, '2026-11-13')
    for n in ('101O2030.RAW', '101_2030.JPG', '101O2031.RAW', '101_2031.JPG'):
        shutil.copy2(os.path.join(d13, n), dcim)
    for d, _, fs in os.walk(sd):                       # la SD de mentira, sólo lectura
        for f in fs:
            os.chmod(os.path.join(d, f), 0o444)
    antes_sd = huella(sd)
    estado = os.path.join(tmp, 'estado.json')

    srv = subprocess.Popen([sys.executable, os.path.join(AQUI, 'conversor_ui.py'), '--puerto', '0', '--no-abrir',
                            '--destino', destino, '--origen', dcim, '--copias', copias, '--estado', estado],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    informe = {}
    try:
        for _ in range(100):
            if os.path.exists(estado) and os.path.getsize(estado):
                break
            time.sleep(0.1)
        e = json.load(open(estado))
        c = Cliente(e['puerto'], e['token'])
        chequear(oct(os.stat(estado).st_mode & 0o777) == '0o600', 'el archivo con el token sólo lo lee el usuario')

        # 1. seguridad
        st, pag = c.pedir('/', token=False)
        chequear(st == 200 and e['token'].encode() in pag, 'la página se sirve con el token de la sesión')
        chequear(c.pedir('/', token=False, host='evil.example:80')[0] == 403, 'Host ajeno (DNS rebinding) → 403')
        chequear(c.pedir('/api/estado', token=False)[0] == 403, 'API sin token → 403')
        chequear(c.pedir('/api/convertir', {'nombre': '101O2037.RAW'}, token=False)[0] == 403, 'POST sin token → 403')
        chequear(c.pedir('/api/estado', host=f'evil.example:{e["puerto"]}')[0] == 403, 'token correcto con Host ajeno → 403')
        st, est = c.pedir('/api/estado')
        chequear(st == 200 and est['sd'] and est['sd_raw'] == 2, f'estado ve la SD con 2 RAW ({est})')

        # 3. nombres y vacíos
        st, r = c.subir('../../evil.RAW', b'x' * 100)
        chequear(st == 400, f'nombre ajeno a la M531 → 400 ({r})')
        st, r = c.subir('101_2029.JPG', b'')
        chequear(st == 400, 'JPG vacío → 400 (la página sigue con el RAW)')

        # subidas: M4L con JPG (2037), M4L sin JPG (2029), M4L con JPG truncado (2032), P8 con JPG (raw10/1988)
        casos = {
            '101O2037.RAW': (os.path.join(d13, '101O2037.RAW'), os.path.join(d13, '101_2037.JPG'), None),
            '101O2029.RAW': (os.path.join(d13, '101O2029.RAW'), None, None),
            '101O2032.RAW': (os.path.join(d13, '101O2032.RAW'), os.path.join(d13, '101_2032.JPG'), 30_000),
            '101O1988.RAW': (os.path.join(DUMP, 'raw10', '101O1988.RAW'), os.path.join(DUMP, 'raw10', '101_1988.JPG'), None),
        }
        for n, (raw, jpg, corte) in casos.items():
            if jpg and os.path.exists(jpg):
                datos = open(jpg, 'rb').read()
                chequear(c.subir(os.path.basename(jpg), datos[:corte] if corte else datos)[0] == 200, f'sube {os.path.basename(jpg)}')
            chequear(c.subir(n, open(raw, 'rb').read())[0] == 200, f'sube {n}')
        chequear(c.pedir('/api/convertir', {'nombre': '101O7777.RAW'})[0] == 400, 'convertir un RAW no subido → 400')

        # 4. tres a la vez, como la página
        t0 = time.time()
        with cf.ThreadPoolExecutor(3) as ex:
            res = dict(zip(casos, ex.map(lambda n: c.pedir('/api/convertir', {'nombre': n, 'balance': 'auto', 'rotar': 'no'}), casos)))
        informe['segundos_4_conversiones'] = round(time.time() - t0, 1)
        dia = os.listdir(destino)
        chequear(len(dia) == 1, f'una carpeta del día en el destino ({dia})')
        salida = os.path.join(destino, dia[0])
        chequear(not [f for f in os.listdir(salida) if f.endswith('.parcial')], 'sin .parcial en el destino')
        esperado = {'101O2037.RAW': ('M4L', True), '101O2029.RAW': ('M4L', False), '101O2032.RAW': ('M4L', False),
                    '101O1988.RAW': ('modo 0', True)}
        for n, (st, r) in res.items():
            fmt, con_jpg = esperado[n]
            chequear(st == 200 and r.get('ok'), f'{n} convertido ({r.get("error", "")})')
            if not r.get('ok'):
                continue
            chequear(r['formato'].startswith(fmt), f'{n}: formato {r["formato"]!r} empieza por {fmt!r}')
            chequear(r['jpg'] == con_jpg and os.path.exists(os.path.join(salida, r['nombre'][:-4] + '.JPG')) == con_jpg,
                     f'{n}: JPG al lado = {con_jpg} (truncado o ausente no se copia)')
            with rawpy.imread(os.path.join(salida, r['nombre'])) as rp:
                tam = rp.raw_image.shape
            chequear(tam in ((3264, 4320), (2448, 5760), (3264, 4320)), f'{n}: LibRaw lee el mosaico del DNG {tam}')
            informe[n] = r

        # 2. rutas fuera del destino
        for mala in ('../estado.json', '/etc/hosts', '../../' + os.path.relpath('/etc/hosts', '/')):
            chequear(c.pedir('/api/vista?dng=' + urllib.request.quote(mala))[0] == 404, f'vista fuera del destino ({mala}) → 404')
            chequear(c.pedir('/api/girar', {'dng': mala, 'sentido': 'izq'})[0] == 400, f'girar fuera del destino ({mala}) → 400')

        # 7 y 9. girar y vistas previas
        r37 = informe['101O2037.RAW']
        st, img = c.pedir('/api/vista?que=dng&dng=' + urllib.request.quote(r37['dng']))
        v0 = Image.open(io.BytesIO(img))
        chequear(st == 200 and v0.width > v0.height, f'vista previa del DNG apaisada {v0.size}')
        sips = os.path.join(tmp, 'sips.jpg')
        subprocess.run(['sips', '-s', 'format', 'jpeg', '-Z', '900', os.path.join(destino, r37['dng']), '--out', sips], capture_output=True)
        chequear(Image.open(sips).size == v0.size, 'la vista previa es el render de macOS del DNG')
        st, g = c.pedir('/api/girar', {'dng': r37['dng'], 'sentido': 'izq'})
        chequear(st == 200 and g['giro'] == 1, f'girar a la izquierda → giro 1 ({g.get("giro")})')
        st, img = c.pedir('/api/vista?que=dng&dng=' + urllib.request.quote(r37['dng']))
        v1 = Image.open(io.BytesIO(img))
        chequear(v1.size == (v0.height, v0.width), f'la vista previa gira con el DNG {v1.size}')
        ql = os.path.join(tmp, 'ql')
        os.makedirs(ql)
        subprocess.run(['qlmanage', '-t', '-s', '400', '-o', ql, os.path.join(destino, r37['dng'])], capture_output=True)
        q = Image.open(os.path.join(ql, os.path.basename(r37['dng']) + '.png'))
        chequear(q.height > q.width, f'Quick Look (verdad independiente) también lo muestra vertical {q.size}')
        # mismo lado hacia arriba: la vista y Quick Look, reducidas, se parecen más entre sí que a la vista girada al revés
        a = v1.convert('L').resize((60, 80))
        b = q.convert('L').resize((60, 80))
        c180 = a.rotate(180)
        dif = lambda x, y: int(np.abs(np.asarray(x, np.int32) - np.asarray(y, np.int32)).sum())
        chequear(dif(a, b) < dif(c180, b), 'la vista girada coincide con Quick Look y no con el giro contrario')
        st, img = c.pedir('/api/vista?que=jpg&dng=' + urllib.request.quote(r37['dng']))
        vj = Image.open(io.BytesIO(img))
        chequear(vj.height > vj.width, f'el JPG de al lado gira igual {vj.size}')
        for _ in range(2):
            c.pedir('/api/girar', {'dng': r37['dng'], 'sentido': 'der'})
        st, g = c.pedir('/api/girar', {'dng': r37['dng'], 'sentido': 'der'})
        chequear(g['giro'] == 2, f'izq + 3 der = 180° ({g["giro"]})')
        vistas = [Image.open(io.BytesIO(c.pedir('/api/vista?que=dng&dng=' + urllib.request.quote(informe[n]['dng']))[1]))
                  for n in casos if n in informe]

        # 8. importar de la SD
        st, r = c.pedir('/api/importar', {'balance': 'auto', 'rotar': 'no'})
        chequear(st == 200 and r['ok'], 'arranca la importación')
        chequear(c.pedir('/api/importar', {'balance': 'auto'})[0] == 400, 'una segunda importación a la vez → 400')
        for _ in range(600):
            st, imp = c.pedir('/api/importar')
            if not imp['corriendo']:
                break
            time.sleep(0.2)
        nombres = sorted(d['nombre'] for d in imp['dngs'])
        chequear(imp['codigo'] == 0 and nombres == ['101_2030.DNG', '101_2031.DNG'], f'importación: {nombres}, código {imp["codigo"]}')
        chequear(any('verificados con SHA-256' in x for x in imp['lineas']), 'el registro de ./importar llega a la página')
        chequear(all(d.get('formato', '').startswith('M4L') and d.get('balance') for d in imp['dngs']),
                 'las fotos importadas traen formato y balance para la tarjeta')
        st, img = c.pedir('/api/vista?que=dng&tam=2400&dng=' + urllib.request.quote(imp['dngs'][0]['dng']))
        chequear(st == 200 and max(Image.open(io.BytesIO(img)).size) == 2400, 'vista grande para el visor (2400 px)')
        st, r = c.pedir('/api/importar', {'balance': 'auto'})
        while c.pedir('/api/importar')[1]['corriendo']:
            time.sleep(0.2)
        imp2 = c.pedir('/api/importar')[1]
        chequear(imp2['dngs'] == [] and imp2['codigo'] == 0, 'repetir la importación no reconvierte nada')
        chequear(huella(sd) == antes_sd, 'la SD quedó idéntica (nombres, tamaños, fechas, SHA-256)')
        informe['importacion'] = imp['lineas']
        st, est = c.pedir('/api/estado')
        chequear(est['importando'] is False, 'estado: importación terminada')

        # artefacto: hoja con las vistas previas servidas
        vistas += [Image.open(io.BytesIO(c.pedir('/api/vista?que=dng&dng=' + urllib.request.quote(d['dng']))[1])) for d in imp['dngs']]
        hoja = Image.new('RGB', (3 * 320, ((len(vistas) + 2) // 3) * 320), 'white')
        for i, v in enumerate(vistas):
            v = v.convert('RGB')
            v.thumbnail((310, 310))
            hoja.paste(v, ((i % 3) * 320 + 5, (i // 3) * 320 + 5))
        hoja.save(os.path.join(OUT, 'hoja.jpg'), quality=85)
    finally:
        srv.terminate()
        try:
            salida_srv = srv.communicate(timeout=10)[0]
        except subprocess.TimeoutExpired:
            srv.kill()
            salida_srv = ''
        informe['servidor'] = salida_srv
        chequear(not os.path.exists(estado), 'al cerrar borra el archivo con el token')
        for d, _, fs in os.walk(sd):
            for f in fs:
                os.chmod(os.path.join(d, f), 0o644)
        shutil.rmtree(tmp, ignore_errors=True)
    informe['fallas'] = FALLAS
    json.dump(informe, open(os.path.join(OUT, 'reporte.json'), 'w'), indent=1, ensure_ascii=False)
    print(f"\n{'TODO BIEN' if not FALLAS else f'{len(FALLAS)} FALLAS'} · artefacto en {OUT}/")
    return 1 if FALLAS else 0


if __name__ == '__main__':
    sys.exit(main())
