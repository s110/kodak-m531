#!/usr/bin/env python3
"""Prueba E2E del conversor web (web/, la página estática "Reveal"): el JavaScript que se publica contra
tools/m531raw.py sobre fotos reales de dump/, y la página de verdad en Chrome sin ventana, con las
intercalaciones difíciles (cambiar ajustes, volver a soltar, girar o exportar a mitad de un lote).

Cómo puede fallar (escrito antes del código; las máquinas de estado están en docs/ESTADOS_WEB.md):

  Conversión (el oráculo es conversor_ui.convertir_uno, la versión de escritorio)
   1. El port decodifica distinto que Python: orden de bits, curva del modo 4, M4L confundido con P9, FFT
      que cambia una decisión (empaquetado, ancho, detección fiable), percentil o umbral del balance.
   2. El JPG se decodifica distinto que libjpeg y el balance que sale de él se corre; o el JPG truncado,
      vacío o de 224 B se copia (Python no lo copia).
   3. Compilar a TypeScript cambió algo: lo que se publica ya no es lo que se probó.
   4. Un caso de prueba ya no pasa por el camino que decía cubrir (otra fuente de balance, otro formato).

  Página: intercalaciones
   5. Cambiar Balance o Giro con un lote en marcha cambia fotos que ya estaban pedidas.
   6. Soltar otra vez las mismas fotos a mitad del lote: tarjetas duplicadas, un resultado viejo que llega
      tarde pisa al nuevo, el resumen cuenta trabajos en vez de fotos, o las conversiones viejas que
      estaban en cola se ejecutan igual (el doble de espera).
   7. Girar, ampliar o descargar una tarjeta que todavía convierte hace algo (o revienta).
   8. Abrir el visor a mitad de un lote: el revelado espera detrás de todas las conversiones.
   9. Soltar otra vez la foto que se está viendo: el visor se queda con una foto que ya no existe, la tecla
      espacio revienta, la URL del JPG se queda viva, o el visor se reabre solo al terminar.
  10. "Descargar todo" a mitad del lote exporta un lote incompleto.
  11. Girar o soltar durante una exportación: el .zip sale con CRC malo, con el DNG y el JPG girados
      distinto, o con fotos que no estaban al hacer clic; el botón se rehabilita y se exporta dos veces.
  12. "Guardar en carpeta" guarda lo que haya cuando se cierra el selector, no lo que había al hacer clic.
  13. Un Worker muere con una foto: esa tarjeta se queda "convirtiendo" para siempre, o se pierden otras.
  14. Girar varias veces hasta volver no deja los bytes originales; o girar no hace nada.
  15. El resumen, los botones o el visor dicen algo que no corresponde a las tarjetas en algún instante.

  Página: lo demás
  16. No empareja O/B/JPG de una carpeta DCIM o convierte archivos ajenos; no recuerda los ajustes.
  17. Se traba mientras convierte. La vista previa no corresponde al DNG (balance, giro, colores).
  18. El .zip, la descarga por foto o la carpeta no traen los mismos bytes que la versión de escritorio.
  19. Pide algo fuera de sus propios archivos, o la CSP de _headers le impide funcionar.
  20. En pantalla de teléfono se desborda; en modo oscuro queda ilegible.
  21. Lo que se publica lleva rutas personales, fotos, node_modules o fuentes sin compilar.

Cada comprobación es un comportamiento que puede fallar por su cuenta. Lo que sólo sirve para entender un
fallo (etiquetas TIFF, píxeles, neutro, datos del análisis) va al reporte como diagnóstico, sin contar.
No se usa LibRaw para "abrir" cada DNG: un DNG idéntico byte a byte al de Python ya lo abre LibRaw
(tools/e2e_raw.py lo comprueba sobre el de Python). LibRaw queda sólo donde dice algo nuevo: comparar la
vista previa de la página, que no existe en Python, con un revelado independiente del mismo DNG.

Artefacto: work/e2e_web/reporte.json, hoja.jpg (vista previa de la página junto al revelado de LibRaw) y
capturas. Con --mutaciones además rompe el código a propósito, de una forma por vez, y anota qué
comprobaciones se pusieron en rojo (work/e2e_web/mutaciones.json; el reporte lo incluye).
uso: .venv/bin/python tools/e2e_web.py [--mutaciones]
Necesita node (con `npm install` hecho en web/), Google Chrome y playwright en el entorno.
"""
import base64
import concurrent.futures as cf
import hashlib
import http.server
import io
import json
import multiprocessing
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
PUBLICO = os.path.join(WEB, 'public')
OUT = os.path.join(RAIZ, 'work', 'e2e_web')
NODE = shutil.which('node') or '/opt/homebrew/bin/node'
NPM = shutil.which('npm') or '/opt/homebrew/bin/npm'
sys.path.insert(0, AQUI)
import m531raw  # noqa: E402
import conversor_ui  # noqa: E402

HECHAS = {}      # id → dict(ok, texto): un comportamiento, una entrada
DIAGNOSTICOS = {}


def chequear(ident, cond, msg, diagnostico=None):
    assert ident not in HECHAS, f'comprobación repetida: {ident}'
    HECHAS[ident] = dict(ok=bool(cond), texto=msg)
    print(('ok    ' if cond else 'FALLA ') + msg, flush=True)
    if not cond and diagnostico is not None:
        DIAGNOSTICOS[ident] = diagnostico
        print('      diagnóstico: ' + json.dumps(diagnostico, ensure_ascii=False, default=str)[:700], flush=True)
    return bool(cond)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def huellas(carpeta, solo=None):
    """{nombre: SHA-256} de los DNG y JPG de una carpeta."""
    if not os.path.isdir(carpeta):
        return {}
    return {n: sha(open(os.path.join(carpeta, n), 'rb').read()) for n in sorted(os.listdir(carpeta))
            if n.endswith(('.DNG', '.JPG')) and (solo is None or n[:8] in solo)}


def diferencias(real, esperado):
    """Qué nombres sobran, faltan o difieren entre dos {nombre: sha}."""
    return dict(sobran=sorted(set(real) - set(esperado)), faltan=sorted(set(esperado) - set(real)),
                distintos=sorted(n for n in set(real) & set(esperado) if real[n] != esperado[n]))


# ---------------------------------------------------------------- diagnóstico de un DNG distinto
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


CAMPOS_INFO = ('packing', 'bits', 'ancho', 'alto', 'layout', 'cfa', 'cfa_detectado', 'cfa_metricas', 'decodificado', 'max_crudo', 'modo4',
               'perfil_camara', 'perfil', 'negro', 'blanco', 'balance', 'neutro', 'giro', 'orientacion', 'awb_camara', 'quemado',
               'parche_blanco_descartado', 'tamanos')


def diagnostico_dng(c, a, b, f):
    """Por qué el DNG de JavaScript (b) no es el de Python (a): etiquetas, píxeles, neutro y análisis."""
    d = {}
    try:
        ta, pa = etiquetas(a)
        tb, pb = etiquetas(b)
        d['etiquetas_distintas'] = sorted(t for t in set(ta) | set(tb) if ta.get(t) != tb.get(t))
        d['pixeles_identicos'] = pa == pb and a[pa:] == b[pb:]
        d['pixeles_distintos_en_los_primeros_2_MB'] = int(sum(x != y for x, y in zip(a[pa:pa + 2_000_000], b[pb:pb + 2_000_000])))
        d['neutro_python'], d['neutro_js'] = ([x / y for x, y in struct.iter_unpack('<II', t[50728][2])] for t in (ta, tb))
        nombres = sorted(os.listdir(c['carpeta']))
        o = [n for n in nombres if n[3] == 'O'][0]
        campos = [os.path.join(c['carpeta'], x) for x in (o, o[:3] + 'B' + o[4:]) if os.path.exists(os.path.join(c['carpeta'], x))]
        tmp = tempfile.mkdtemp()
        info = m531raw.convertir(campos, os.path.join(tmp, 'x.dng'), balance=c['balance'], rotar=c['rotar'])
        shutil.rmtree(tmp)
        d['analisis_distinto'] = {k: [info.get(k), f['info'].get(k)] for k in CAMPOS_INFO if info.get(k) != f['info'].get(k)}
    except Exception as e:
        d['error_al_diagnosticar'] = repr(e)
    return d


# ---------------------------------------------------------------- casos (fotos reales de dump/)
def d13(n):
    return os.path.join(DUMP, '2026-11-13', n)


def partir_campos(origen, destino_o, destino_b, ancho_bytes):
    """Dos campos entrelazados a partir de un RAW real: filas pares → O, impares → B."""
    a = np.fromfile(origen, dtype=np.uint8).reshape(-1, ancho_bytes)
    a[0::2].tofile(destino_o)
    a[1::2].tofile(destino_b)


def preparar_casos(tmp):
    """Cada caso es una carpeta con los archivos tal como llegarían de la tarjeta. `camino` dice qué
    rama del conversor quiere cubrir el caso; se comprueba aparte de la igualdad con Python."""
    casos = []

    def caso(nombre, archivos, balance='auto', rotar='no', giros=(), camino=None):
        c = os.path.join(tmp, 'casos', nombre)
        os.makedirs(c)
        for destino, origen in archivos.items():
            if callable(origen):
                origen(os.path.join(c, destino))
            else:
                shutil.copy(origen, os.path.join(c, destino))
        casos.append(dict(nombre=nombre, carpeta=c, balance=balance, rotar=rotar, giros=list(giros), camino=camino or {}))

    def cortado(origen, n):
        return lambda dst: open(dst, 'wb').write(open(origen, 'rb').read()[:n])

    def fraccion(origen, f):
        return lambda dst: open(dst, 'wb').write(open(origen, 'rb').read()[:int(os.path.getsize(origen) * f)])

    r10, r8, r3, r1 = (os.path.join(DUMP, x) for x in ('raw10', 'raw8', 'raw3', 'raw1'))
    caso('m4l_con_jpg', {'101O2037.RAW': d13('101O2037.RAW'), '101_2037.JPG': d13('101_2037.JPG')}, rotar='camara', giros=['izq'],
         camino=dict(balance='parche_blanco', modo4='lineal12', jpg=True))
    caso('m4l_sin_jpg', {'101O2029.RAW': d13('101O2029.RAW')}, rotar='camara', camino=dict(balance='parche_blanco', jpg=False))
    caso('m4l_jpg_cortado_en_cabecera', {'101O2032.RAW': d13('101O2032.RAW'), '101_2032.JPG': cortado(d13('101_2032.JPG'), 30_000)},
         rotar='camara', camino=dict(jpg=False, awb_camara=None))
    caso('m4l_jpg_cortado_en_datos', {'101O2031.RAW': d13('101O2031.RAW'), '101_2031.JPG': fraccion(d13('101_2031.JPG'), 0.6)},
         rotar='camara', camino=dict(jpg=False, giro=1))
    caso('m4l_balance_camara', {'101O2037.RAW': d13('101O2037.RAW'), '101_2037.JPG': d13('101_2037.JPG')}, balance='camara',
         camino=dict(balance='awb_camara', jpg=True))
    caso('m4l_quemado_usa_awb', {'101O2030.RAW': d13('101O2030.RAW'), '101_2030.JPG': d13('101_2030.JPG')},
         camino=dict(balance='awb_camara', modo4='lineal12'))
    caso('m4l_parche_no_creible', {'101O2022.RAW': d13('101O2022.RAW'), '101_2022.JPG': d13('101_2022.JPG')}, rotar='camara',
         camino=dict(balance='fijo_modo4'))
    caso('p8_balance_del_jpg', {'101O1988.RAW': os.path.join(r10, '101O1988.RAW'), '101_1988.JPG': os.path.join(r10, '101_1988.JPG')},
         rotar='camara', giros=['der', 'der', 'der'], camino=dict(balance='jpg', jpg=True, giro=2, decodificado=True))
    caso('p8_balance_del_jpg_2', {'101O1989.RAW': os.path.join(r10, '101O1989.RAW'), '101_1989.JPG': os.path.join(r10, '101_1989.JPG')},
         camino=dict(balance='jpg'))
    caso('p8_balance_camara', {'101O1989.RAW': os.path.join(r10, '101O1989.RAW'), '101_1989.JPG': os.path.join(r10, '101_1989.JPG')},
         balance='camara', camino=dict(balance='awb_camara', decodificado=True))
    caso('p8_jpg_vacio', {'101O1987.RAW': os.path.join(r8, '101O1987.RAW'), '101_1987.JPG': os.path.join(r8, '101_1987.JPG')},
         rotar='camara', camino=dict(balance='parche_blanco', jpg=False, decodificado=True))
    caso('p9_curva_10_bits', {'101O1972.RAW': os.path.join(r3, '101O1972.RAW'), '101_1972.JPG': os.path.join(r3, '101_1972.JPG')},
         camino=dict(modo4='curva10'))
    caso('modo3_16_bits_jpg_de_224_B', {'101O1968.RAW': os.path.join(r1, '101O1968.RAW'), '101_1968.JPG': os.path.join(r1, '101_1968.JPG')},
         rotar='camara', camino=dict(packing='u16_le', jpg=False))
    # dump/ no tiene ningún disparo en dos archivos (O + B): se arma uno partiendo en campos un RAW real.
    caso('dos_campos_O_y_B', {'101O1989.RAW': lambda dst: partir_campos(os.path.join(r10, '101O1989.RAW'), dst,
                                                                         dst.replace('O1989', 'B1989'), 4320)},
         camino=dict(layout='filas', packing='u8', ancho=4320, alto=3264, perfil_camara=False))
    # tamaño que no es de ningún modo conocido (M4L sin sus dos últimas filas): todo se detecta de los datos
    caso('tamano_desconocido', {'101O2029.RAW': cortado(d13('101O2029.RAW'), 21_150_720 - 2 * 6480)},
         camino=dict(packing='p12_lsb', ancho=4320, alto=3262, perfil_camara=False))
    caso('archivo_constante', {'101O0001.RAW': lambda dst: open(dst, 'wb').write(bytes(3_000_000))}, camino=dict(error='sin formato posible'))
    rng = np.random.default_rng(531)
    caso('ruido_sin_estructura', {'101O0002.RAW': lambda dst: open(dst, 'wb').write(rng.integers(0, 256, 3_000_000, dtype=np.uint8).tobytes())},
         camino=dict(error='detección poco fiable'))
    return casos


def escritorio(carpeta, salida, balance, rotar):
    """Lo que hace la versión de escritorio con una carpeta: conversor_ui.convertir_uno por cada disparo.
    Los nombres se pasan a mayúsculas como hace conversor_ui.subir. Devuelve {base: resultado}."""
    os.makedirs(salida, exist_ok=True)
    entrada = tempfile.mkdtemp(prefix='e2e_web_ref_')
    for n in os.listdir(carpeta):
        if conversor_ui.RE_ARCHIVO.fullmatch(n):
            os.symlink(os.path.join(carpeta, n), os.path.join(entrada, n.upper()))
    out = {}
    for n in sorted(os.listdir(entrada)):
        if n[3] != 'O' or not n.endswith('.RAW'):
            continue
        base = n[:3] + '_' + n[4:8]
        campos = [os.path.join(entrada, n)] + [p for p in [os.path.join(entrada, n[:3] + 'B' + n[4:])] if os.path.exists(p)]
        jpg = os.path.join(entrada, base + '.JPG')
        dng = os.path.join(salida, base + '.DNG')
        t0 = time.time()
        r = conversor_ui.convertir_uno(campos, dng, jpg if os.path.exists(jpg) and os.path.getsize(jpg) else None, dng[:-4] + '.JPG',
                                       balance, rotar)
        r['ms'] = round((time.time() - t0) * 1000)
        out[base] = r
    shutil.rmtree(entrada)
    return out


def girar_referencia(carpeta, base, giro_inicial, sentidos):
    """Gira el DNG (y su JPG) de la referencia como conversor_ui.Conversor.girar. Devuelve el giro final."""
    g = giro_inicial
    dng = os.path.join(carpeta, base + '.DNG')
    for s in sentidos:
        g = (g + (1 if s == 'izq' else -1)) % 4
        m531raw.orientar(dng, g)
        if os.path.exists(dng[:-4] + '.JPG'):
            m531raw.orientar(dng[:-4] + '.JPG', g)
    return g


def en_paralelo(trabajos):
    """[(carpeta, salida, balance, rotar)] → [resultado de escritorio(...)], en procesos aparte."""
    with cf.ProcessPoolExecutor(min(4, len(trabajos)), mp_context=multiprocessing.get_context('spawn')) as ex:
        return list(ex.map(escritorio, *zip(*trabajos)))


def correr_node(trabajos, tmp):
    ruta = os.path.join(tmp, f'trabajos_{len(os.listdir(tmp))}.json')
    json.dump(trabajos, open(ruta, 'w'))
    p = subprocess.run([NODE, os.path.join(AQUI, 'e2e_web_nodo.mjs'), ruta], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return {j['id']: j for j in map(json.loads, p.stdout.splitlines())}


def compilar():
    """npm run build: tsc en modo estricto, de web/src a web/public/js. Devuelve (bien, salida)."""
    p = subprocess.run([NPM, 'run', '--silent', 'build'], cwd=WEB, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def parte_equivalencia(tmp, informe):
    print('\n== 1. El JavaScript publicado (en Node) contra la versión de escritorio, sobre RAW reales ==')
    casos = preparar_casos(tmp)
    for c in casos:
        c['js'] = os.path.join(tmp, 'js', c['nombre'])
        c['py'] = os.path.join(tmp, 'py', c['nombre'])
        os.makedirs(c['js'])
    t0 = time.time()
    res = correr_node([dict(id=c['nombre'], que='convertir', carpeta=c['carpeta'], salida=c['js'], balance=c['balance'], rotar=c['rotar'],
                            giros=c['giros']) for c in casos], tmp)
    informe['node_segundos_total'] = round(time.time() - t0, 1)
    refs = en_paralelo([(c['carpeta'], c['py'], c['balance'], c['rotar']) for c in casos])
    informe['casos'] = {}
    for c, ref in zip(casos, refs):
        n = c['nombre']
        (base, r), = ref.items()
        j = res[n]
        f = j['fotos'][0] if 'fotos' in j and len(j['fotos']) == 1 else None
        d = informe['casos'][n] = dict(balance_pedido=c['balance'], rotar=c['rotar'], giros=c['giros'])
        if f is None:
            chequear(f'igual/{n}', False, f'{n}: Node devuelve una foto', j)
            continue
        if 'error' in c['camino']:
            d.update(error_python=r.get('error'), error_js=f.get('error'))
            chequear(f'igual/{n}', not r['ok'] and not f['ok'] and f.get('motivo') and f['error'].split(' (')[0] == r['error'].split(' (')[0]
                     and not huellas(c['js']), f'{n}: JavaScript rechaza el archivo con el mismo motivo que Python y no deja nada escrito',
                     dict(python=r, js=f))
            chequear(f'camino/{n}', c['camino']['error'] in str(r.get('error')), f'{n}: el rechazo es el que el caso quería cubrir ({c["camino"]["error"]!r})', r)
            continue
        if r['ok']:
            girar_referencia(c['py'], base, r['giro'], c['giros'])
        hp, hj = huellas(c['py']), huellas(c['js'])
        d.update(sha256=hj, ms_python=r.get('ms'), ms_node=f.get('ms'), formato=f.get('formato'), balance=f.get('balance'))
        diag = dict(python=r, js=f.get('error'))
        if hp != hj and f.get('ok') and r['ok']:
            diag = dict(archivos=diferencias(hj, hp), **diagnostico_dng(c, open(os.path.join(c['py'], base + '.DNG'), 'rb').read(),
                                                                         open(os.path.join(c['js'], base + '.DNG'), 'rb').read(), f))
        chequear(f'igual/{n}', r['ok'] and f.get('ok') and hp == hj and len(hp) >= 1,
                 f'{n}: lo que sale ({", ".join(hp)}) es byte a byte lo de la versión de escritorio', diag)
        if f.get('ok'):
            real = {k: (f.get(k) if k in ('jpg', 'giro') else f['info'].get(k)) for k in c['camino']}
            chequear(f'camino/{n}', real == c['camino'], f'{n}: pasa por el camino que quería cubrir ({c["camino"]})', real)

    # ---- JPG: píxeles del decodificador propio contra PIL. No lo implica la igualdad de los DNG: el
    # balance que sale del JPG se redondea a 1e-6, así que un decodificador casi igual podría pasar allí.
    jpgs = dict(p8=os.path.join(DUMP, 'raw10', '101_1988.JPG'), danado_por_disparo_encima=d13('101_2032.JPG'), m4l=d13('101_2037.JPG'))
    correr_node([dict(id=k, que='jpeg', jpg=v, salida=os.path.join(tmp, k + '.rgb')) for k, v in jpgs.items()], tmp)
    informe['jpeg_contra_pil'] = {}
    for k, v in jpgs.items():
        pil = np.asarray(Image.open(v).convert('RGB')).astype(np.int16)
        js = np.fromfile(os.path.join(tmp, k + '.rgb'), dtype=np.uint8).reshape(pil.shape).astype(np.int16)
        informe['jpeg_contra_pil'][k] = dict(dif_max=int(np.abs(pil - js).max()), valores_distintos=int((pil != js).sum()), de=int(pil.size))
    chequear('jpeg', all(x['valores_distintos'] == 0 for x in informe['jpeg_contra_pil'].values()),
             f'el decodificador de JPG propio da los mismos píxeles que PIL/libjpeg en {len(jpgs)} JPG de la cámara (uno dañado)', informe['jpeg_contra_pil'])

    # ---- .zip: el mismo escritor que usa la página, con un tope pequeño para forzar el reparto
    listos = [c for c in casos if huellas(c['js'])]
    zdir = os.path.join(tmp, 'zip')
    os.makedirs(zdir)
    planos = []
    for c in listos[:4]:                                  # nombres repetidos entre casos: el del caso delante
        for x in huellas(c['js']):
            planos.append(os.path.join(zdir, c['nombre'][:3] + c['nombre'][-3:] + x))
            shutil.copy(os.path.join(c['js'], x), planos[-1])
    planos.append(os.path.join(zdir, 'ñandú á.DNG'))
    shutil.copy(planos[0], planos[-1])
    limite = 60_000_000                                   # dos DNG de 28 MB por .zip
    zips = correr_node([dict(id='reparto', que='zip', archivos=planos, limite=limite, salida=os.path.join(zdir, 'r'))], tmp)['reparto']['zips']
    todo, bien, veces = {}, [], {}
    for z in zips:
        with zipfile.ZipFile(z['ruta']) as zf:
            bien.append(zf.testzip() is None and os.path.getsize(z['ruta']) <= limite
                        and subprocess.run(['unzip', '-tq', z['ruta']], capture_output=True).returncode == 0)
            for i in zf.infolist():
                veces[i.filename] = veces.get(i.filename, 0) + 1
                todo[i.filename] = sha(zf.read(i))
    juntos = all(len({z['ruta'] for z in zips if any(x[:-4] == b for x in z['nombres'])}) == 1 for b in {os.path.basename(p)[:-4] for p in planos})
    informe['zip'] = dict(tope=limite, zips=[dict(nombres=z['nombres'], bytes=os.path.getsize(z['ruta'])) for z in zips])
    chequear('zip/reparto', len(zips) > 1 and all(bien) and juntos and set(veces.values()) == {1}
             and todo == {os.path.basename(p): sha(open(p, 'rb').read()) for p in planos},
             f'.zip repartido: {len(planos)} archivos con tope de {limite >> 20} MB salen en {len(zips)} .zip que zipfile y unzip dan por buenos, ninguno '
             'pasa del tope, cada archivo sale una vez e íntegro (también el de nombre con ñ) y el DNG va con su JPG',
             dict(validos=bien, juntos=juntos, veces=veces))


# ---------------------------------------------------------------- 2. la página en Chrome
def cabeceras_de_pages():
    """Las cabeceras de _headers (formato de Cloudflare Pages) para la regla /*."""
    cab, dentro = [], False
    for linea in open(os.path.join(PUBLICO, '_headers'), encoding='utf-8'):
        if not linea.strip():
            continue
        if not linea[0].isspace():
            dentro = linea.strip() == '/*'
        elif dentro:
            k, v = linea.strip().split(':', 1)
            cab.append((k.strip(), v.strip()))
    return cab


# Worker de prueba: envuelve al de verdad (que carga con ?real) para retrasar respuestas o hacerlo morir
# con una foto concreta. Sólo cambia cuándo llegan las cosas, que es lo que la prueba necesita gobernar.
OBRERO_DE_PRUEBA = """import './obrero.js?real';
const REGLAS = __REGLAS__;
const real = self.onmessage, enviar = self.postMessage.bind(self), retrasos = new Map();
const regla = m => REGLAS.find(r => r.que === m.que && (!r.nombre || (m.campos || []).some(f => f.name === r.nombre))
  && (!r.balance || (m.opciones && m.opciones.balance === r.balance)));
self.onmessage = e => {
  const r = regla(e.data);
  if (r && r.accion === 'reventar') { setTimeout(() => { throw new Error('obrero reventado por la prueba'); }); return; }
  if (r && r.accion === 'retrasar') retrasos.set(e.data.id, r.ms);
  return real.call(self, e);
};
self.postMessage = (msg, t) => {
  const ms = retrasos.get(msg.id);
  if (ms) setTimeout(() => enviar(msg, t), ms); else enviar(msg, t);
};
"""


class Servidor:
    """Sirve web/public con las cabeceras de _headers. `reglas` cambia el Worker por el de prueba."""

    def __init__(self):
        self.pedidos = []
        self.reglas = None
        extra = cabeceras_de_pages()
        yo = self

        class H(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=PUBLICO, **kw)

            def log_message(self, fmt, *a):
                yo.pedidos.append((self.command, self.path, a[1] if len(a) > 1 else ''))

            def do_GET(self):
                if self.path == '/js/obrero/obrero.js' and yo.reglas is not None:
                    cuerpo = OBRERO_DE_PRUEBA.replace('__REGLAS__', json.dumps(yo.reglas)).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/javascript')
                    self.send_header('Content-Length', str(len(cuerpo)))
                    self.end_headers()
                    self.wfile.write(cuerpo)
                    return
                super().do_GET()

            def do_POST(self):
                yo.pedidos.append(('POST', self.path, ''))
                self.send_error(405)
            do_PUT = do_POST

            def end_headers(self):
                for k, v in extra:
                    self.send_header(k, v)
                self.send_header('Cache-Control', 'no-store')
                super().end_headers()
        H.extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{'.js': 'text/javascript', '.webmanifest': 'application/manifest+json'})
        self.srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.origen = f'http://127.0.0.1:{self.srv.server_address[1]}'


# Instrumentos de la prueba dentro de la página (se inyectan por DevTools; no son código de la página):
#  * un observador que, cada vez que el DOM cambia, comprueba los invariantes de docs/ESTADOS_WEB.md
#    contra lo que se ve y apunta la línea de tiempo de cada tarjeta;
#  * espías de Worker (qué se le envía y cuándo responde) y de URL.createObjectURL / revokeObjectURL;
#  * showDirectoryPicker abre un diálogo del sistema que no se puede manejar sin ventana: aquí devuelve una
#    carpeta del sistema de archivos privado del navegador (OPFS) y puede retenerse hasta que la prueba
#    quiera. El código que escribe los archivos es el de la página, sin tocar.
INSTRUMENTOS = r"""
(() => {
  const P = window.__prueba = { violaciones: [], observaciones: 0, linea: [], enviados: [], recibidos: [], urls: { vivas: {}, historia: [] },
    previo: {}, latido: 0, carpeta: { retener: false, soltar: null, n: 0 } };
  let t = performance.now();
  setInterval(() => { const a = performance.now(); P.latido = Math.max(P.latido, a - t); t = a; }, 20);

  window.showDirectoryPicker = async () => {
    if (P.carpeta.retener) await new Promise(r => { P.carpeta.soltar = r; });
    return (await navigator.storage.getDirectory()).getDirectoryHandle('elegida_' + (++P.carpeta.n), { create: true });
  };

  const W = window.Worker;
  window.Worker = class extends W {
    constructor(...a) {
      super(...a);
      this.addEventListener('message', e => P.recibidos.push({ t: performance.now(), id: e.data.id, ok: e.data.ok }));
    }
    postMessage(m, tr) {
      P.enviados.push({ t: performance.now(), id: m.id, que: m.que, nombres: (m.campos || []).map(f => f.name), balance: m.opciones && m.opciones.balance });
      return super.postMessage(m, tr);
    }
  };
  const crear = URL.createObjectURL, revocar = URL.revokeObjectURL;
  URL.createObjectURL = b => { const u = crear.call(URL, b); P.urls.vivas[u] = b.type; P.urls.historia.push(Object.keys(P.urls.vivas).length); return u; };
  URL.revokeObjectURL = u => { delete P.urls.vivas[u]; P.urls.historia.push(Object.keys(P.urls.vivas).length); return revocar.call(URL, u); };

  const LEGAL = { cola: ['convirtiendo'], convirtiendo: ['lista', 'error'], lista: ['lista'], error: [] };
  const falla = (inv, detalle) => { if (P.violaciones.length < 40) P.violaciones.push({ inv, t: Math.round(performance.now()), detalle }); };
  P.foto = () => [...document.querySelectorAll('.foto')].map(f => ({ nom: f.querySelector('.nom').textContent, estado: f.dataset.estado,
    epoca: +f.dataset.epoca, giro: f.dataset.giro, balance: f.dataset.balance, botones: [...f.querySelectorAll('.ic')].map(b => !b.disabled) }));
  P.tarjeta = nom => [...document.querySelectorAll('.foto')].find(f => f.querySelector('.nom').textContent === nom);
  P.ahora = () => {
    const fotos = P.foto(), n = e => fotos.filter(f => e.includes(f.estado)).length;
    return { fotos, cola: n(['cola']), convirtiendo: n(['convirtiendo']), listas: n(['lista']), pend: n(['cola', 'convirtiendo']), errores: n(['error']),
      de: nom => fotos.find(f => f.nom === nom) || {}, tarjeta: P.tarjeta, exportando: document.querySelector('#resumen').dataset.exportando || '' };
  };
  const revisar = () => {
    const cuenta = document.querySelector('#cuenta'), zip = document.querySelector('#zip'), guardar = document.querySelector('#guardar');
    if (!cuenta || !zip || !guardar) return;
    P.observaciones++;
    const c = P.ahora(), { fotos, pend, listas, errores, exportando } = c;
    const texto = [pend ? `convirtiendo ${pend}…` : '', listas ? `${listas} DNG ${listas === 1 ? 'listo' : 'listos'}` : '', errores ? `${errores} con error` : '']
      .filter(Boolean).join(' · ');
    if (cuenta.textContent !== texto) falla('resumen', { dice: cuenta.textContent, tarjetas: texto });
    const puede = pend === 0 && listas > 0 && exportando === '';
    if (zip.disabled === puede || guardar.disabled === puede) falla('exportar', { zip: !zip.disabled, guardar: !guardar.disabled, pend, listas, exportando });
    if ((zip.textContent === 'Preparando…') !== (exportando === 'zip') || (guardar.textContent === 'Guardando…') !== (exportando === 'carpeta')) {
      falla('rotulo', { zip: zip.textContent, guardar: guardar.textContent, exportando });
    }
    const visor = document.querySelector('#visor.on');
    if (visor && !fotos.some(f => f.nom === visor.dataset.foto && f.estado === 'lista')) falla('visor', { foto: visor.dataset.foto });
    for (const f of fotos) {
      if (f.botones.some(b => b !== (f.estado === 'lista'))) falla('botones', f);
      const a = P.previo[f.nom];
      if (a && a.estado === f.estado && a.epoca === f.epoca) continue;
      // Una foto recién soltada puede verse ya 'convirtiendo': si hay un Worker libre empieza en el mismo instante.
      const recien = ['cola', 'convirtiendo'].includes(f.estado);
      if (!a ? !(recien && f.epoca === 1)
        : f.epoca === a.epoca ? !LEGAL[a.estado].includes(f.estado) : !(f.epoca === a.epoca + 1 && recien)) falla('transicion', { de: a || null, a: f });
      P.previo[f.nom] = { estado: f.estado, epoca: f.epoca };
      P.linea.push({ t: performance.now(), nom: f.nom, estado: f.estado, epoca: f.epoca, pend, listas });
    }
  };
  new MutationObserver(revisar).observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
})();
"""
INVARIANTES = dict(
    resumen='el resumen dice exactamente lo que hay en las tarjetas (fotos, no trabajos)',
    exportar='"Descargar todo" y "Guardar en carpeta" están habilitados sólo sin fotos pendientes, con alguna lista y sin exportación en marcha',
    rotulo='el rótulo "Preparando…" / "Guardando…" aparece sólo mientras dura esa exportación',
    visor='el visor abierto enseña siempre una foto que está lista',
    botones='los botones de una tarjeta están habilitados sólo cuando la foto está lista',
    transicion='cada tarjeta sigue la tabla: cola → convirtiendo → lista | error, y sólo vuelve a empezar con una época más')
LEER_CARPETA = """async n => {
  const dir = await (await navigator.storage.getDirectory()).getDirectoryHandle('elegida_' + n);
  const out = {};
  for await (const [nombre, h] of dir.entries()) {
    const d = new Uint8Array(await crypto.subtle.digest('SHA-256', await (await h.getFile()).arrayBuffer()));
    out[nombre] = [...d].map(x => x.toString(16).padStart(2, '0')).join('');
  }
  return out;
}"""
SD_FOTOS = ('101_1988', '101_1989', '101_2022', '101_2029', '101_2030', '101_2031', '101_2032', '101_2037')
TODO_QUIETO = '(() => { const c = window.__prueba.ahora(); return c.fotos.length > 0 && c.pend === 0; })()'
JPG_A_LA_VISTA = '(() => { const i = document.querySelector("#visor img"); return !i.hidden && i.complete && i.naturalWidth > 0; })()'
VISOR_ABIERTO = 'document.querySelector("#visor").classList.contains("on")'


def armar_sd(tmp):
    """Una SD de mentira: DCIM/101KM531 con 8 disparos (RAW, un campo B, JPG, uno cortado) y archivos ajenos."""
    sd = os.path.join(tmp, 'SD')
    dcim = os.path.join(sd, 'DCIM', '101KM531')
    os.makedirs(dcim)
    os.makedirs(os.path.join(sd, 'Batch'))
    r10 = os.path.join(DUMP, 'raw10')
    for n in ('101O2037.RAW', '101_2037.JPG', '101O2029.RAW', '101O2030.RAW', '101_2030.JPG', '101O2032.RAW', '101O2022.RAW', '101_2022.JPG',
              '101O2031.RAW', '101_2031.JPG'):
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


def revelado_libraw(dng, lado):
    """El mismo DNG revelado por LibRaw, sin brillo automático y con el balance del archivo."""
    with rawpy.imread(dng) as rp:
        rgb = rp.postprocess(half_size=True, use_camera_wb=True, no_auto_bright=True, output_bps=8, gamma=(2.4, 12.92))
    im = Image.fromarray(rgb)
    im.thumbnail((lado, lado))
    return im


def esperar(pag, expresion, timeout=30_000, arg=None):
    """Espera a que la expresión dé algo cierto en la página y lo devuelve. (wait_for_function de
    Playwright evalúa texto dentro de la página y la CSP lo prohíbe; evaluate va por DevTools y no.)"""
    fin = time.time() + timeout / 1000
    while time.time() < fin:
        r = pag.evaluate(expresion, arg) if arg is not None else pag.evaluate(expresion)
        if r:
            return r
        time.sleep(0.03)
    raise TimeoutError(f'no se cumplió en {timeout} ms: {expresion[:90]}')


class Pagina:
    """Una página nueva (contexto limpio) con los instrumentos puestos, y lo que la prueba hace con ella."""

    def __init__(self, banco, nombre, reglas=None, **contexto):
        self.banco, self.nombre = banco, nombre
        banco.servidor.reglas = reglas
        self.ctx = banco.chrome.new_context(accept_downloads=True, **(contexto or dict(viewport=dict(width=1280, height=900))))
        self.ctx.add_init_script(INSTRUMENTOS)
        self.ctx.on('request', lambda r: banco.urls.append((r.method, r.url)))
        self.pag = self.ctx.new_page()
        self.pag.on('console', lambda m: banco.consola.append(f'{nombre} {m.type}: {m.text}') if m.type in ('error', 'warning') else None)
        self.pag.on('pageerror', lambda e: banco.consola.append(f'{nombre} excepción: {e}'))
        self.descargas = []
        banco.abiertas.append(self)
        self.pag.on('download', lambda d: self.descargas.append(d))
        self.pag.goto(banco.servidor.origen + '/')

    def ev(self, expresion, arg=None):
        return self.pag.evaluate(expresion, arg) if arg is not None else self.pag.evaluate(expresion)

    def cuando(self, condicion, accion='', timeout=30_000):
        """Hace `accion` en la página sólo si las tarjetas están como dice `condicion`, las dos cosas en
        el mismo instante (una sola tarea de JavaScript; `c` es window.__prueba.ahora()): así la
        intercalación que se quiere probar es la que de verdad ocurrió. Devuelve cómo estaban las
        tarjetas y lo que devolvió la acción, o None si la condición no llegó a darse."""
        js = ('(() => { const c = window.__prueba.ahora(); if (!(%s)) return null; const r = (() => { %s })(); '
              'return { fotos: c.fotos, t: performance.now(), r: r === undefined ? null : r }; })()') % (condicion, accion)
        try:
            return esperar(self.pag, js, timeout)
        except TimeoutError:
            return None

    def fotos(self):
        return {f['nom']: f for f in self.ev('window.__prueba.foto()')}

    def quieta(self, timeout=120_000):
        esperar(self.pag, TODO_QUIETO, timeout)

    def opcion(self, clave, valor):
        self.pag.click(f'.seg[data-opc="{clave}"] button[data-v="{valor}"]')

    def soltar_arrastrando(self, ruta):
        """Arrastrar y soltar de verdad (protocolo de DevTools) una carpeta o archivo sobre la página."""
        cdp = self.ctx.new_cdp_session(self.pag)
        datos = dict(items=[], files=[ruta], dragOperationsMask=1)
        for tipo in ('dragEnter', 'dragOver', 'drop'):
            cdp.send('Input.dispatchDragEvent', dict(type=tipo, x=640, y=300, data=datos))

    def tarjeta(self, base):
        return self.pag.locator('.foto', has=self.pag.locator('.nom', has_text=base))

    def descargar(self, accion, cuantas=1, timeout=120_000):
        """Lo que baja al hacer `accion`: {nombre sugerido: bytes}."""
        antes = len(self.descargas)
        accion()
        fin = time.time() + timeout / 1000
        while len(self.descargas) < antes + cuantas and time.time() < fin:
            self.pag.wait_for_timeout(50)
        out = {}
        for d in self.descargas[antes:]:
            ruta = os.path.join(self.banco.tmp, f'descarga_{time.time_ns()}')
            d.save_as(ruta)
            out[d.suggested_filename] = open(ruta, 'rb').read()
            os.remove(ruta)
        return out

    def zip(self, accion=None):
        """Hace clic en "Descargar todo" (o `accion`) y devuelve ({nombre: sha}, problema o None)."""
        bajado = self.descargar(accion or (lambda: self.pag.click('#zip', timeout=5000)))
        if len(bajado) != 1:
            return {}, f'bajaron {len(bajado)} archivos'
        (nombre, datos), = bajado.items()
        if not re.fullmatch(r'reveal_\d{4}-\d\d-\d\d\.zip', nombre):
            return {}, f'nombre inesperado: {nombre}'
        try:
            with zipfile.ZipFile(io.BytesIO(datos)) as zf:
                malo = zf.testzip()
                if malo:
                    return {i.filename: '' for i in zf.infolist()}, f'CRC que no corresponde: {malo}'
                return {i.filename: sha(zf.read(i)) for i in zf.infolist()}, None
        except Exception as e:
            return {}, f'.zip ilegible: {e!r}'

    def cerrar(self):
        """Recoge lo que vieron los instrumentos y cierra."""
        p = self.ev('({ violaciones: window.__prueba.violaciones, observaciones: window.__prueba.observaciones })')
        self.banco.observaciones += p['observaciones']
        for v in p['violaciones']:
            self.banco.violaciones.append(dict(v, pagina=self.nombre))
        self.banco.abiertas.remove(self)
        self.ctx.close()


class Banco:
    """Lo común a todos los escenarios: Chrome, servidor, la SD de mentira y las referencias de escritorio."""

    def __init__(self, tmp, pw):
        self.tmp = tmp
        self.servidor = Servidor()
        self.chrome = pw.chromium.launch(channel='chrome', headless=True)
        self.urls, self.consola, self.violaciones, self.observaciones, self.abiertas = [], [], [], 0, []
        self.sd, self.dcim = armar_sd(tmp)
        self.ref = {b: os.path.join(tmp, 'ref_' + b) for b in ('auto', 'camara')}
        res = en_paralelo([(self.dcim, self.ref[b], b, 'camara') for b in self.ref])   # Giro = "Como el JPG" en todos los escenarios
        self.meta = dict(zip(self.ref, res))
        self.huellas = {b: huellas(self.ref[b]) for b in self.ref}

    def esperado(self, balance='auto', giros=None, solo=None, otros=None):
        """{nombre: sha} que debe salir de la página: la referencia de escritorio con `balance`, girando
        las fotos de `giros` ({base: [sentidos]}); `otros` = {base: balance} para fotos con otro balance."""
        tmp = tempfile.mkdtemp(prefix='e2e_web_esp_')
        for base in (solo or SD_FOTOS):
            bal = (otros or {}).get(base, balance)
            for ext in ('.DNG', '.JPG'):
                if os.path.exists(os.path.join(self.ref[bal], base + ext)):
                    shutil.copy(os.path.join(self.ref[bal], base + ext), tmp)
            if giros and base in giros:
                girar_referencia(tmp, base, self.meta[bal][base]['giro'], giros[base])
        out = huellas(tmp)
        shutil.rmtree(tmp)
        return out

    def archivos_de(self, base):
        return [os.path.join(self.dcim, n) for n in os.listdir(self.dcim) if re.fullmatch(base[:3] + '[ob_]' + base[4:] + r'\.(raw|jpg)', n, re.I)]

    def cerrar(self):
        self.chrome.close()
        self.servidor.srv.shutdown()


def escenario_base(b, informe):
    """Recorrido normal con el Worker de verdad: carpeta de la SD, visor, las tres salidas y giros."""
    nav = informe['navegador']
    p = Pagina(b, 'base')
    pag = p.pag
    nav['chrome'] = b.chrome.version
    p.opcion('rotar', 'camara')
    pag.reload()
    chequear('ajustes/recordados', pag.get_attribute('.seg[data-opc="rotar"] button[data-v="camara"]', 'aria-pressed') == 'true'
             and pag.get_attribute('.seg[data-opc="balance"] button[data-v="auto"]', 'aria-pressed') == 'true',
             'Giro = "Como el JPG" se recuerda al recargar y Balance, que no se tocó, sigue en Auto')

    pag.set_input_files('#elegir', [os.path.join(b.dcim, 'IMG_0001.JPG'), os.path.join(b.dcim, 'DSC00001.ARW')])
    pag.wait_for_selector('#aviso.on')
    chequear('entrada/ajenos', 'Ningún RAW conocido' in pag.inner_text('#aviso') and pag.locator('.foto').count() == 0,
             f'archivos de otra cámara: aviso y ninguna tarjeta ({pag.inner_text("#aviso")[:50]!r})')

    t0 = time.time()
    pag.set_input_files('#elegir-carpeta', b.sd)
    p.quieta()
    nav['segundos_8_fotos'] = round(time.time() - t0, 1)
    latido = p.ev('window.__prueba.latido')
    nav['pausa_maxima_de_la_pagina_ms'] = round(latido)
    fotos = p.fotos()
    chequear('entrada/sd', sorted(fotos) == sorted(SD_FOTOS) and all(f['estado'] == 'lista' for f in fotos.values()),
             f'la carpeta de la SD da una tarjeta por disparo y todas se convierten; los archivos ajenos y el JPG suelto no cuentan ({len(fotos)} tarjetas)', fotos)
    chequear('pagina/no_se_traba', latido < 400, f'la página no se traba mientras convierte 8 fotos (pausa máxima del hilo principal {latido:.0f} ms)')
    metas = pag.evaluate('Object.fromEntries([...document.querySelectorAll(".foto")].map(f => [f.querySelector(".nom").textContent, [f.querySelector(".m").textContent, +f.dataset.ms]]))')
    quiero = {k: f"{e['formato']} · balance {e['balance'].replace('_', ' ')} · {'con JPG' if e['jpg'] else 'sin JPG'}" for k, e in b.meta['auto'].items()}
    chequear('tarjeta/descripcion', {k: v[0] for k, v in metas.items()} == quiero, 'cada tarjeta describe formato, balance y JPG con el mismo texto que la versión de escritorio',
             dict(pagina=metas, escritorio=quiero))
    nav['ms_por_raw_navegador'] = {k: v[1] for k, v in metas.items()}
    nav['ms_por_raw_python'] = {k: e['ms'] for k, e in b.meta['auto'].items()}
    pag.screenshot(path=os.path.join(OUT, 'pagina.png'))
    vistas = {k: Image.open(io.BytesIO(base64.b64decode(p.tarjeta(k).locator('canvas').evaluate('c => c.toDataURL("image/png")').split(',')[1]))).convert('RGB')
              for k in SD_FOTOS}

    # visor: la tabla abrir → (espacio) JPG → (espacio) DNG → (Esc) cerrado; sin JPG, espacio no cambia
    p.tarjeta('101_1988').locator('.marco').click()
    esperar(pag, 'document.querySelector("#visor").dataset.revelado')
    dims = pag.evaluate('(() => { const c = document.querySelector("#visor canvas"); return [c.width, c.height, getComputedStyle(c).display !== "none"]; })()')
    chequear('visor/revelado', dims == [1632, 2160, True], f'visor: el DNG se revela a media resolución y de pie, como el JPG de esa foto ({dims[:2]})')
    pag.screenshot(path=os.path.join(OUT, 'visor_dng.png'))
    pasos = []
    pag.keyboard.press('Space')
    esperar(pag, JPG_A_LA_VISTA)
    pasos.append(pag.evaluate('(() => { const i = document.querySelector("#visor img"), v = document.querySelector("#visor"); return [v.dataset.que, i.naturalWidth, i.naturalHeight, document.querySelector("#visor canvas").hidden]; })()'))
    pag.keyboard.press('Space')
    pasos.append(pag.evaluate('[document.querySelector("#visor").dataset.que, document.querySelector("#visor img").hidden]'))
    pag.keyboard.press('Escape')
    pasos.append(pag.evaluate(VISOR_ABIERTO))
    p.tarjeta('101_2029').locator('.marco').click()
    pag.keyboard.press('Space')
    pasos.append(pag.evaluate(f'[{VISOR_ABIERTO}, document.querySelector("#visor").dataset.que]'))
    pag.keyboard.press('Escape')
    chequear('visor/tabla', pasos == [['jpg', 3216, 4288, True], ['dng', True], False, [True, 'dng']],
             'visor: espacio pasa al JPG de la cámara y vuelve al DNG, Esc cierra, y una foto sin JPG no cambia con espacio', pasos)

    # las tres salidas, contra los bytes de la versión de escritorio
    real, problema = p.zip()
    chequear('salida/zip', problema is None and real == b.huellas['auto'], f'"Descargar todo": un .zip válido con los {len(b.huellas["auto"])} archivos de la versión de '
             'escritorio, byte a byte (8 DNG y sólo los JPG sanos)', dict(problema=problema, **diferencias(real, b.huellas['auto'])))
    una = {n: sha(d) for n, d in p.descargar(lambda: p.tarjeta('101_2037').locator('button[data-a="bajar"]').click(), 2).items()}
    chequear('salida/una_foto', una == b.esperado(solo=['101_2037']), 'el botón de una tarjeta baja su DNG y su JPG, idénticos a los de escritorio', una)
    pag.click('#guardar')
    esperar(pag, 'document.querySelector("#aviso").textContent.includes("guardados")', timeout=120_000)
    guardado = pag.evaluate(LEER_CARPETA, 1)
    chequear('salida/carpeta', guardado == b.huellas['auto'], f'"Guardar en carpeta" escribe los mismos {len(guardado)} archivos (SHA-256 leído de la carpeta)',
             diferencias(guardado, b.huellas['auto']))

    # giros: los que vuelven al punto de partida y los que no
    giros = {'101_2037': ['izq'] * 4, '101_2029': ['der', 'izq'], '101_2030': ['izq', 'izq', 'der', 'der'], '101_1988': ['izq'], '101_2031': ['der'] * 3,
             '101_2032': ['der', 'der']}
    for base, sentidos in giros.items():
        for s in sentidos:
            p.tarjeta(base).locator(f'button[data-a="{s}"]').click()
    esperar(pag, 'document.querySelector("#resumen").dataset.exportando === ""')
    real, problema = p.zip()
    vuelven, netos = ['101_2037', '101_2029', '101_2030'], ['101_1988', '101_2031', '101_2032']
    en = lambda bases: {n: h for n, h in real.items() if n[:8] in bases}                       # noqa: E731
    chequear('giros/vuelven', problema is None and en(vuelven) == b.esperado(solo=vuelven), 'girar hasta volver (4 a la izquierda; derecha e izquierda; 2 y 2) deja '
             'el DNG y el JPG con los bytes originales', dict(problema=problema, **diferencias(en(vuelven), b.esperado(solo=vuelven))))
    quiero = b.esperado(solo=netos, giros={k: giros[k] for k in netos})
    chequear('giros/netos', problema is None and en(netos) == quiero and not set(quiero.values()) & set(b.esperado(solo=netos).values()),
             'un giro neto (1 a la izquierda, 3 a la derecha, 2 a la derecha) deja DNG y JPG como los gira la versión de escritorio',
             dict(problema=problema, **diferencias(en(netos), quiero)))
    p.cerrar()
    return vistas


BOTON_BALANCE = 'document.querySelector(\'.seg[data-opc="balance"] button[data-v="%s"]\').click();'


def escenario_ajustes_y_resoltar(b, informe):
    """Cambiar Balance con el lote en marcha, y volver a soltar la carpeta a mitad del lote.
    El Worker de prueba retiene 9 s la respuesta de 1988 con Balance = Auto: es el resultado viejo que
    llegará cuando esa foto ya se haya reconvertido con otro balance."""
    p = Pagina(b, 'resoltar', reglas=[dict(que='convertir', nombre='101O1988.RAW', balance='auto', accion='retrasar', ms=9000),
                                      dict(que='convertir', accion='retrasar', ms=350)])
    pag, d = p.pag, {}
    p.opcion('rotar', 'camara')
    # A. lote con Balance = Cámara; con fotos todavía en cola se pasa a Auto
    p.opcion('balance', 'camara')
    pag.set_input_files('#elegir-carpeta', b.sd)
    a = p.cuando('c.cola >= 3 && c.convirtiendo >= 1', BOTON_BALANCE % 'auto')
    p.quieta()
    real, problema = p.zip()
    enviados_en_a = len(p.ev('window.__prueba.enviados'))
    d['A'] = dict(al_cambiar=a and [f['estado'] for f in a['fotos']], problema=problema, **diferencias(real, b.huellas['camara']))
    chequear('ajustes/en_vuelo', a is not None and problema is None and real == b.huellas['camara']
             and pag.get_attribute('.seg[data-opc="balance"] button[data-v="auto"]', 'aria-pressed') == 'true',
             'cambiar Balance con el lote en marcha (3 o más fotos aún en cola) no toca lo ya soltado: las 8 salen con el Balance del momento de soltarlas', d['A'])

    # B. se suelta otra vez (ahora en Auto) y, con 1988 convirtiendo y otras en cola, se pasa a Cámara y
    #    se suelta la carpeta una tercera vez, arrastrándola
    pag.set_input_files('#elegir-carpeta', b.sd)
    antes = p.cuando('c.de("101_1988").estado === "convirtiendo" && c.de("101_1988").epoca === 2 && c.cola >= 3', BOTON_BALANCE % 'camara')
    p.soltar_arrastrando(os.path.join(b.sd, 'DCIM'))
    try:
        esperar(pag, '(() => { const f = window.__prueba.foto(); return f.length === 8 && f.every(x => x.epoca === 3 && x.estado === "lista"); })()', 60_000)
    except TimeoutError:
        pass
    fotos = p.fotos()
    otras = [x for x in SD_FOTOS if x != '101_1988']
    real, problema = p.zip() if all(f['estado'] == 'lista' for f in fotos.values()) else ({}, 'quedan tarjetas sin terminar')
    en = lambda bases: {n: h for n, h in real.items() if n[:8] in bases}                       # noqa: E731
    d['B'] = dict(antes=antes and [f['estado'] for f in antes['fotos']], tarjetas={k: [f['estado'], f['epoca']] for k, f in fotos.items()}, problema=problema,
                  **diferencias(en(otras), b.esperado('camara', solo=otras)))
    chequear('resoltar/tarjetas', antes is not None and sorted(fotos) == sorted(SD_FOTOS) and all(f['epoca'] == 3 and f['estado'] == 'lista' for f in fotos.values())
             and problema is None and en(otras) == b.esperado('camara', solo=otras),
             'volver a soltar la carpeta a mitad del lote (arrastrándola) reconvierte en las mismas 8 tarjetas, sin duplicar, con el Balance nuevo', d['B'])

    # lo que se le mandó a los Workers: las conversiones del lote reemplazado que estaban en cola no se envían
    # (en orden de envío: el lote B se pidió con Auto y el que lo reemplaza, con Cámara)
    conv = [x for x in p.ev('window.__prueba.enviados')[enviados_en_a:] if x['que'] == 'convertir']
    primera_nueva = next((i for i, x in enumerate(conv) if x['balance'] == 'camara'), len(conv))
    lote2, tras = conv[:primera_nueva], conv[primera_nueva:]
    d['envios'] = dict(lote_reemplazado_enviadas=len(lote2), tras_resoltar_auto=sum(x['balance'] == 'auto' for x in tras),
                       tras_resoltar_camara=sum(x['balance'] == 'camara' for x in tras))
    chequear('resoltar/cola_cancelada', 1 <= len(lote2) < 8 and all(x['balance'] == 'auto' for x in lote2) and d['envios']['tras_resoltar_auto'] == 0 and d['envios']['tras_resoltar_camara'] == 8,
             f'las conversiones del lote reemplazado que seguían en cola no llegan a ejecutarse: de sus 8 se enviaron {len(lote2)}, y tras volver a soltar '
             'sólo se envían las 8 nuevas', d['envios'])

    # el resultado viejo de 1988 (Auto, retenido 9 s) llega cuando su tarjeta ya está lista con Cámara
    viejo = next((x for x in lote2 if '101O1988.RAW' in x['nombres']), None)
    llego = None
    if viejo:
        try:
            llego = esperar(pag, 'id => window.__prueba.recibidos.find(x => x.id === id)', 20_000, viejo['id'])
        except TimeoutError:
            pass
    pag.wait_for_timeout(300)
    lista3 = next((x['t'] for x in p.ev('window.__prueba.linea') if x['nom'] == '101_1988' and x['epoca'] == 3 and x['estado'] == 'lista'), None)
    f88 = p.fotos().get('101_1988', {})
    una = {}
    if f88.get('estado') == 'lista':
        una = {n: sha(x) for n, x in p.descargar(lambda: p.tarjeta('101_1988').locator('button[data-a="bajar"]').click(), 2).items()}
    d['viejo'] = dict(llego=llego, lista_epoca_3=lista3, tarjeta=f88, **diferencias(una, b.esperado('camara', solo=['101_1988'])))
    chequear('resoltar/resultado_viejo', bool(llego and llego['ok'] and lista3 and llego['t'] > lista3) and f88.get('epoca') == 3
             and una == b.esperado('camara', solo=['101_1988']) and una != b.esperado('auto', solo=['101_1988']),
             'un resultado del lote viejo que llega tarde (1988 con Balance = Auto, después de que su tarjeta ya se reconvirtió) no pisa al nuevo', d['viejo'])
    informe['navegador']['resoltar'] = d
    p.cerrar()


def escenario_tarjeta_sin_terminar_y_visor(b, informe):
    """Girar, ampliar y descargar una tarjeta que aún convierte; el visor a mitad del lote; y soltar
    otra vez la foto que se está viendo."""
    p = Pagina(b, 'visor', reglas=[dict(que='convertir', accion='retrasar', ms=600)])
    pag, d = p.pag, {}
    p.opcion('rotar', 'camara')
    pag.set_input_files('#elegir-carpeta', b.sd)
    # 2037 es la última de la cola. Se le hace de todo mientras espera y mientras convierte; los botones
    # están deshabilitados, así que también se prueba saltándose eso (lo que haría un atajo de teclado).
    todo = """const t = c.tarjeta('101_2037'); t.querySelector('.marco').click();
      for (const x of t.querySelectorAll('.ic')) { x.click(); x.disabled = false; x.click(); x.disabled = true; }
      document.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));
      return { visor: %s, giro: t.dataset.giro || null, estado: t.dataset.estado };""" % VISOR_ABIERTO
    en_cola = p.cuando('c.de("101_2037").estado === "cola" && c.listas >= 1', todo)
    # visor a mitad del lote: se abre una foto lista con 3 o más en cola
    abierto = p.cuando('c.listas >= 1 && c.cola >= 3', 'const f = c.fotos.find(x => x.estado === "lista"); c.tarjeta(f.nom).querySelector(".marco").click(); return f.nom;')
    revelado = None
    try:
        revelado = esperar(pag, '(() => { const c = window.__prueba.ahora(); return document.querySelector("#visor").dataset.revelado ? { cola: c.cola, pend: c.pend } : null; })()', 60_000)
    except TimeoutError:
        pass
    pag.keyboard.press('Escape')
    convirtiendo = p.cuando('c.de("101_2037").estado === "convirtiendo"', todo)
    p.quieta()
    antes = len(p.descargas)
    una = {n: sha(x) for n, x in p.descargar(lambda: p.tarjeta('101_2037').locator('button[data-a="bajar"]').click(), 2).items()}
    d['sin_terminar'] = dict(en_cola=en_cola and en_cola['r'], convirtiendo=convirtiendo and convirtiendo['r'], descargas_antes_de_terminar=antes,
                             **diferencias(una, b.esperado(solo=['101_2037'])))
    chequear('tarjeta/sin_terminar', bool(en_cola and convirtiendo) and all(x['r'] == dict(visor=False, giro=None, estado=e) for x, e in ((en_cola, 'cola'), (convirtiendo, 'convirtiendo')))
             and antes == 0 and una == b.esperado(solo=['101_2037']),
             'girar, ampliar o descargar una tarjeta en cola o convirtiendo no hace nada (ni saltándose el botón deshabilitado): no baja nada y, al terminar, la foto '
             'sale sin girar', d['sin_terminar'])
    d['prioridad'] = dict(abierto=abierto and dict(foto=abierto['r'], estados=[f['estado'] for f in abierto['fotos']]), revelado=revelado)
    chequear('visor/a_mitad_del_lote', bool(abierto and revelado and revelado['cola'] >= 1),
             f'el visor no espera al lote: abierto con 3 o más fotos en cola, su revelado llega cuando aún hay {revelado and revelado["cola"]} sin empezar '
             f'({revelado and revelado["pend"]} por terminar)', d['prioridad'])

    # la foto que se está viendo (en JPG) se suelta otra vez
    urls = []
    habia = len(p.ev('Object.keys(window.__prueba.urls.vivas)'))                                # las de la descarga de antes viven un minuto
    vivas = lambda: len(p.ev('Object.keys(window.__prueba.urls.vivas)')) - habia                # noqa: E731
    desde = len(p.ev('window.__prueba.urls.historia'))
    p.tarjeta('101_1988').locator('.marco').click()
    pag.keyboard.press('Space')
    urls.append(['jpg', vivas()])
    pag.keyboard.press('Space')
    urls.append(['dng', vivas()])
    pag.keyboard.press('Space')
    esperar(pag, JPG_A_LA_VISTA)
    urls.append(['jpg', vivas()])
    pag.set_input_files('#elegir', b.archivos_de('101_1988'))
    esperar(pag, 'window.__prueba.foto().find(f => f.nom === "101_1988").epoca === 2')
    al_soltar = [pag.evaluate(VISOR_ABIERTO), vivas()]
    pag.keyboard.press('Space')
    p.quieta()
    pag.wait_for_timeout(300)
    al_terminar = pag.evaluate(VISOR_ABIERTO)
    pag.keyboard.press('Escape')
    p.tarjeta('101_1988').locator('.marco').click()
    try:
        reabre = bool(esperar(pag, 'document.querySelector("#visor").dataset.revelado', 20_000))
    except TimeoutError:
        reabre = False
    pag.keyboard.press('Escape')
    d['reemplazo'] = dict(urls=urls, al_soltar=al_soltar, al_terminar=al_terminar, reabre=reabre, max_urls_vivas=max(p.ev('window.__prueba.urls.historia')[desde:] or [habia]) - habia)
    chequear('visor/foto_reemplazada', urls == [['jpg', 1], ['dng', 0], ['jpg', 1]] and al_soltar == [False, 0] and al_terminar is False and reabre
             and d['reemplazo']['max_urls_vivas'] == 1,
             'soltar otra vez la foto que se está viendo cierra el visor y revoca la URL de su JPG (viva sólo mientras se ve el JPG, nunca más de una); espacio no '
             'revienta, el visor no se reabre solo al terminar y se puede volver a abrir', d['reemplazo'])
    informe['navegador']['visor'] = d
    p.cerrar()


def escenario_exportar(b, informe):
    """"Descargar todo" a mitad del lote, y girar o soltar mientras una exportación está en marcha.
    El Worker de prueba retrasa cada CRC para que la preparación del .zip dure varios segundos."""
    p = Pagina(b, 'exportar', reglas=[dict(que='crc', accion='retrasar', ms=350), dict(que='convertir', accion='retrasar', ms=500)])
    pag, d = p.pag, {}
    p.opcion('rotar', 'camara')
    pag.set_input_files('#elegir-carpeta', b.sd)
    # a mitad del lote: el botón está deshabilitado; se le hace clic igual, y también saltándose eso
    forzar = """const z = document.querySelector('#zip'), estaba = z.disabled; z.click(); z.disabled = false; z.click(); z.disabled = estaba;
      return { deshabilitado: estaba, exportando: document.querySelector('#resumen').dataset.exportando, aviso: document.querySelector('#aviso').textContent };"""
    medio = p.cuando('c.listas >= 2 && c.pend >= 2', forzar)
    p.quieta()
    pag.wait_for_timeout(1500)
    d['a_mitad'] = dict(medio=medio and medio['r'], estados=medio and [f['estado'] for f in medio['fotos']], descargas=len(p.descargas))
    chequear('exportar/a_mitad_del_lote', bool(medio) and medio['r']['deshabilitado'] and medio['r']['exportando'] == '' and 'Espera' in medio['r']['aviso'] and len(p.descargas) == 0,
             '"Descargar todo" a mitad del lote no exporta nada: el botón está deshabilitado y, aun saltándoselo, la página responde "Espera a que terminen…"', d['a_mitad'])
    esperar(pag, 'document.querySelector("#resumen").dataset.exportando === ""', 120_000)
    antes_de = len(p.descargas)
    d['durante'] = dict(giro=False, exportando_al_soltar=None)

    # exportación en marcha: se giran la primera y la última foto del .zip y se suelta otra vez una tercera con otro Balance
    def durante_la_exportacion():
        pag.click('#zip', timeout=5000)
        d['durante'].update(giro=bool(p.cuando('c.exportando === "zip"', "for (const n of ['101_1988', '101_2037']) c.tarjeta(n).querySelector('button[data-a=\"izq\"]').click();"
                                               + BOTON_BALANCE % 'camara', 5000)))
        pag.set_input_files('#elegir', b.archivos_de('101_2030'))
        d['durante']['exportando_al_soltar'] = pag.evaluate('document.querySelector("#resumen").dataset.exportando')
    real, problema = ({}, 'ya había bajado algo') if antes_de else p.zip(durante_la_exportacion)
    d['durante'].update(problema=problema, **diferencias(real, b.huellas['auto']))
    chequear('exportar/instantanea', d['durante']['giro'] and d['durante']['exportando_al_soltar'] == 'zip' and problema is None and real == b.huellas['auto'],
             'el .zip lleva lo que había al hacer clic: girar dos fotos y volver a soltar otra mientras se prepara no lo cambia (CRC buenos, DNG y JPG con el mismo giro)', d['durante'])
    esperar(pag, 'document.querySelector("#resumen").dataset.exportando === ""', 60_000)
    p.quieta()
    cambios = dict(giros={'101_1988': ['izq'], '101_2037': ['izq']}, otros={'101_2030': 'camara'})
    real, problema = p.zip()
    chequear('exportar/siguiente', problema is None and real == b.esperado(**cambios), 'lo hecho durante la exportación no se pierde: el siguiente .zip trae las dos fotos giradas '
             'y la reconvertida con el Balance nuevo', dict(problema=problema, **diferencias(real, b.esperado(**cambios))))

    # carpeta: se hace clic, y con el selector de carpeta aún abierto se gira una foto
    pag.evaluate('window.__prueba.carpeta.retener = true')
    pag.click('#guardar', timeout=5000)
    esperar(pag, 'window.__prueba.carpeta.soltar !== null')
    p.tarjeta('101_2029').locator('button[data-a="der"]').click()
    pag.evaluate('window.__prueba.carpeta.soltar()')
    esperar(pag, 'document.querySelector("#aviso").textContent.includes("guardados")', timeout=120_000)
    guardado = pag.evaluate(LEER_CARPETA, 1)
    chequear('exportar/carpeta_instantanea', guardado == b.esperado(**cambios) and p.fotos()['101_2029']['giro'] == '3',
             '"Guardar en carpeta" guarda lo que había al hacer clic, aunque se gire una foto con el selector de carpeta abierto', diferencias(guardado, b.esperado(**cambios)))
    informe['navegador']['exportar'] = d
    p.cerrar()


def escenario_obrero_que_revienta(b, informe):
    """Un Worker que muere con una foto (2030) y un RAW ilegible (bytes constantes), con otras en marcha."""
    malo = os.path.join(b.tmp, '101O0001.RAW')
    open(malo, 'wb').write(bytes(3_000_000))
    p = Pagina(b, 'obrero', reglas=[dict(que='convertir', nombre='101O2030.RAW', accion='reventar')])
    pag = p.pag
    p.opcion('rotar', 'camara')
    pag.set_input_files('#elegir', [os.path.join(b.dcim, n) for n in sorted(os.listdir(b.dcim)) if conversor_ui.RE_ARCHIVO.fullmatch(n)] + [malo])
    try:
        p.quieta(45_000)
    except TimeoutError:
        pass
    fotos = p.fotos()
    errores = pag.evaluate('Object.fromEntries([...document.querySelectorAll(".foto[data-estado=error]")].map(f => [f.querySelector(".nom").textContent, f.querySelector(".m").textContent]))')
    sanas = [x for x in SD_FOTOS if x != '101_2030']
    chequear('error/raw_ilegible', fotos.get('101_0001', {}).get('estado') == 'error' and 'sin formato posible' in errores.get('101_0001', ''),
             'un RAW ilegible deja su tarjeta en error con el motivo de la versión de escritorio ("sin formato posible…")', errores)
    real, problema = ({}, 'quedan tarjetas sin terminar') if any(f['estado'] in ('cola', 'convirtiendo') for f in fotos.values()) else p.zip()
    d = dict(estados={k: f['estado'] for k, f in fotos.items()}, errores=errores, problema=problema, **diferencias(real, b.esperado(solo=sanas)))
    chequear('error/obrero_muere', fotos.get('101_2030', {}).get('estado') == 'error' and 'reventado' in errores.get('101_2030', '') and problema is None
             and real == b.esperado(solo=sanas),
             'un Worker que muere con una foto deja esa tarjeta en error con su motivo, y las otras 7 se convierten igual: el .zip trae sólo esas, idénticas a las de escritorio', d)
    # el grupo de Workers sigue entero: otra foto se convierte después
    pag.set_input_files('#elegir', b.archivos_de('101_2037'))
    try:
        esperar(pag, '(() => { const f = window.__prueba.foto().find(x => x.nom === "101_2037"); return f.epoca === 2 && f.estado === "lista"; })()', 30_000)
        sigue = True
    except TimeoutError:
        sigue = False
    chequear('error/grupo_repuesto', sigue, 'después de la muerte de un Worker la página sigue convirtiendo (el Worker se repone)')
    informe['navegador']['obrero'] = d
    p.cerrar()


def luminancia(css):
    r, g, bl = (int(x) / 255 for x in re.findall(r'\d+', css)[:3])
    return sum(k * (v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4) for k, v in zip((0.2126, 0.7152, 0.0722), (r, g, bl)))


def escenario_telefono(b, informe):
    p = Pagina(b, 'teléfono', viewport=dict(width=390, height=844), device_scale_factor=2, color_scheme='dark', is_mobile=True, has_touch=True)
    pm = p.pag
    pm.set_input_files('#elegir', b.archivos_de('101_2037') + b.archivos_de('101_1988'))
    p.quieta()
    m = pm.evaluate('''() => ({ ancho: document.documentElement.scrollWidth, vista: innerWidth, fondo: getComputedStyle(document.body).backgroundColor,
        texto: getComputedStyle(document.body).color, tenue: getComputedStyle(document.querySelector(".pie .m")).color,
        panel: getComputedStyle(document.querySelector(".foto")).backgroundColor,
        boton: Math.min(...[...document.querySelectorAll(".ic")].map(b => b.getBoundingClientRect().width)),
        tarjeta: document.querySelector(".foto").getBoundingClientRect().width })''')
    contraste = lambda a, c: (max(luminancia(a), luminancia(c)) + 0.05) / (min(luminancia(a), luminancia(c)) + 0.05)   # noqa: E731
    m['contraste_texto'], m['contraste_tenue'] = round(contraste(m['texto'], m['fondo']), 1), round(contraste(m['tenue'], m['panel']), 1)
    informe['navegador']['telefono'] = m
    pm.screenshot(path=os.path.join(OUT, 'telefono_oscuro.png'), full_page=True)
    chequear('telefono/sin_desborde', m['ancho'] <= m['vista'] and m['tarjeta'] > 340 and m['boton'] >= 40,
             f'a 390 px de ancho no hay desborde horizontal, la tarjeta ocupa el ancho y los botones miden {m["boton"]:.0f} px', m)
    chequear('telefono/modo_oscuro', luminancia(m['fondo']) < 0.05 and m['contraste_texto'] >= 7 and m['contraste_tenue'] >= 4.5,
             f'modo oscuro legible: fondo oscuro, contraste del texto {m["contraste_texto"]}:1 y del texto secundario {m["contraste_tenue"]}:1', m)
    p.cerrar()


ESCENARIOS = dict(resoltar=escenario_ajustes_y_resoltar, visor=escenario_tarjeta_sin_terminar_y_visor, exportar=escenario_exportar,
                  obrero=escenario_obrero_que_revienta)


def parte_navegador(tmp, informe, solo=None):
    print('\n== 2. La página en Chrome sin ventana ==')
    from playwright.sync_api import sync_playwright
    nav = informe['navegador'] = {}
    vistas = {}
    with sync_playwright() as pw:
        b = Banco(tmp, pw)
        if not solo:
            vistas = escenario_base(b, informe)
        print('\n== 3. Intercalaciones (docs/ESTADOS_WEB.md) ==')
        for nombre, f in ESCENARIOS.items():
            if not solo or nombre in solo:
                try:
                    f(b, informe)
                except Exception as e:                    # el escenario se interrumpe: cuenta como falla y sigue el resto
                    chequear(f'interrumpido/{nombre}', False, f'el escenario «{nombre}» se interrumpe: {e!r}'[:300])
                    for p in list(b.abiertas):
                        p.cerrar()
        if not solo:
            escenario_telefono(b, informe)
        b.cerrar()

    # ---- invariantes, observados en cada cambio del DOM de todos los escenarios
    nav['observaciones_de_invariantes'] = b.observaciones
    nav['violaciones'] = b.violaciones
    for inv, texto in INVARIANTES.items():
        v = [x for x in b.violaciones if x['inv'] == inv]
        chequear(f'invariante/{inv}', not v and b.observaciones > (0 if solo else 100), f'en {b.observaciones} cambios observados, {texto}', v[:3])
    if solo:
        return

    # ---- red y consola
    origen = b.servidor.origen
    ajenas = [u for u in b.urls if not u[1].startswith((origen + '/', 'blob:' + origen))]
    propios = {'/' + os.path.relpath(os.path.join(d, f), PUBLICO) for d, _, fs in os.walk(PUBLICO) for f in fs} | {'/'}
    raros = [x for x in b.servidor.pedidos if x[0] != 'GET' or x[1].split('?')[0] not in propios or str(x[2]) not in ('200', '304')]
    nav['pedidos_al_servidor'] = sorted({x[1] for x in b.servidor.pedidos})
    consola = [c for c in b.consola if 'reventado por la prueba' not in c]
    nav['consola'] = b.consola
    chequear('red/solo_lo_suyo', not ajenas and not raros and len(b.servidor.pedidos) > 10,
             f'en {len(b.urls)} peticiones la página no pidió nada fuera de su origen y el servidor sólo vio GET de los archivos publicados', dict(ajenas=ajenas[:3], raros=raros[:3]))
    chequear('consola/limpia', not consola, 'sin errores, avisos ni excepciones en la consola en ningún escenario (la CSP no bloquea nada)', consola[:5])

    # ---- vista previa de la página contra el revelado de LibRaw del mismo DNG; hoja de contactos
    lado = 300
    hoja = Image.new('RGB', (len(vistas) * (lado + 10) + 10, 2 * (lado + 24) + 10), (32, 32, 32))
    dib = ImageDraw.Draw(hoja)
    medidas = nav['vista_previa_contra_libraw'] = {}
    for i, (base, v) in enumerate(sorted(vistas.items())):
        lr = revelado_libraw(os.path.join(b.ref['auto'], base + '.DNG'), lado)
        v2 = v.copy()
        v2.thumbnail((lado, lado))
        a = np.asarray(v2.resize(lr.size), np.float64)
        r = np.asarray(lr, np.float64)
        tinte = a.reshape(-1, 3).mean(0) / a.mean() - r.reshape(-1, 3).mean(0) / r.mean()
        medidas[base] = dict(misma_forma=abs(v2.width - lr.width) <= 2 and abs(v2.height - lr.height) <= 2,
                             correlacion=round(float(np.corrcoef(a.mean(2).ravel(), r.mean(2).ravel())[0, 1]), 4),
                             dif_media=round(float(np.abs(a - r).mean()), 1), dif_media_girada_180=round(float(np.abs(a[::-1, ::-1] - r).mean()), 1),
                             tinte_max=round(float(np.abs(tinte).max()), 3))
        x = 10 + i * (lado + 10)
        hoja.paste(v2, (x + (lado - v2.width) // 2, 24 + (lado - v2.height) // 2))
        hoja.paste(lr, (x + (lado - lr.width) // 2, lado + 48 + (lado - lr.height) // 2))
        dib.text((x, 6), f'{base}  Reveal', fill=(230, 230, 230))
        dib.text((x, lado + 30), f'{base}  LibRaw', fill=(230, 230, 230))
    hoja.save(os.path.join(OUT, 'hoja.jpg'), quality=88)
    # 2022 queda fuera del juicio (está en la hoja y en el reporte): tiene un canal quemado en media imagen, y cómo se pinta
    # lo quemado es propio de cada revelador (LibRaw lo deja verdoso, la vista previa lo lleva a amarillo).
    juzgadas = {k: m for k, m in medidas.items() if k != '101_2022'}
    peor = min(m['correlacion'] for m in juzgadas.values())
    chequear('vista_previa', all(m['misma_forma'] and m['correlacion'] > 0.97 and m['dif_media'] < m['dif_media_girada_180'] and m['tinte_max'] < 0.06 for m in juzgadas.values())
             and medidas['101_2022']['misma_forma'],
             f'la vista previa de {len(juzgadas)} fotos corresponde al revelado de LibRaw del mismo DNG: misma forma y lado arriba, sin tinte (peor correlación {peor})', medidas)


def parte_paquete(informe):
    print('\n== 4. Lo que se publica (web/public) ==')
    archivos = sorted(os.path.relpath(os.path.join(d, f), PUBLICO) for d, _, fs in os.walk(PUBLICO) for f in fs)
    tam = {a: os.path.getsize(os.path.join(PUBLICO, a)) for a in archivos}
    informe['paquete'] = dict(carpeta='web/public', archivos=tam, bytes=sum(tam.values()))
    texto = {a: open(os.path.join(PUBLICO, a), encoding='utf-8', errors='replace').read() for a in archivos}
    personal = [(a, m.group(0)) for a, t in texto.items() for m in re.finditer(r'/Volumes|/Users/|sebasti[aá]n|l[oó]pez|PhotoVault|dump/', t, re.I)]
    externos = [(a, m.group(0)) for a, t in texto.items() for m in re.finditer(r'https?://(?!www\.w3\.org/2000/svg)[^\s"\'<>)]+', t)]
    fuentes = sorted(os.path.relpath(os.path.join(d, f), os.path.join(WEB, 'src'))[:-3] for d, _, fs in os.walk(os.path.join(WEB, 'src')) for f in fs
                     if f.endswith('.ts') and not f.endswith('.d.ts'))
    sobra = [a for a in archivos if not (a in ('_headers', 'index.html', 'favicon.svg', 'manifest.webmanifest', 'css/estilo.css')
                                         or (a.startswith('js/') and a.endswith('.js') and a[3:-3] in fuentes))]
    falta = [f for f in fuentes if f'js/{f}.js' not in archivos]
    chequear('paquete/contenido', not personal and not externos and not sobra and not falta,
             f'web/public lleva sólo la página y el JavaScript compilado de web/src ({len(archivos)} archivos, {sum(tam.values()) / 1024:.0f} KB): sin rutas ni nombres '
             'personales, sin fotos, sin node_modules ni fuentes, sin enlaces a otros servidores', dict(personal=personal[:3], externos=externos[:3], sobra=sobra, falta=falta))
    usa_red = [(a, m.group(0)) for a, t in texto.items() if a.endswith('.js')
               for m in re.finditer(r'\bfetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|EventSource|importScripts|\beval\s*\(|new Function', t)]
    chequear('paquete/sin_red', not usa_red, 'el código publicado no usa fetch, XHR, WebSocket, sendBeacon ni eval, tampoco en los caminos que la prueba no recorre', usa_red[:3])


# ---------------------------------------------------------------- mutaciones
# Cada una reintroduce un defecto concreto en web/src (casi todos son el comportamiento del código de
# antes), compila y corre el escenario que debe notarlo. `rojas` son las comprobaciones que tienen que
# fallar; lo que siguió en verde se anota también, para ver qué distingue cada comprobación.
CANCELAR = "    conversiones.get(d.clave)?.cancelar();            // la conversión anterior de esta foto ya no interesa\n"
MUTACIONES = [
    dict(nombre='un resultado viejo pisa al nuevo y la cola vieja se ejecuta', escenario='resoltar', rojas=['resoltar/cola_cancelada', 'resoltar/resultado_viejo'],
         cambios=[('pagina/app.ts', CANCELAR, ''),
                  ('modelo/estado.ts', "return e.epoca === t.epoca && enCurso(t.estado) ? { ...t, estado: { tipo: 'lista', foto: e.foto } } : t;",
                   "return { ...t, estado: { tipo: 'lista', foto: e.foto } };")]),
    dict(nombre='soltar otra vez no cancela la conversión anterior (la época sigue protegiendo)', escenario='resoltar', rojas=['resoltar/cola_cancelada'],
         cambios=[('pagina/app.ts', CANCELAR, '')]),
    dict(nombre='girar modifica la foto en el sitio en vez de dar otra', escenario='exportar', rojas=['exportar/instantanea'],
         cambios=[('nucleo/comun/foto.ts', 'const cabecera = foto.cabecera.slice();', 'const cabecera = foto.cabecera;'),
                  ('nucleo/comun/foto.ts', 'const jpg = foto.jpg ? foto.jpg.slice() : null;', 'const jpg = foto.jpg;')]),
    dict(nombre='exportar no mira si quedan fotos por convertir', escenario='exportar', rojas=['exportar/a_mitad_del_lote', 'invariante/exportar'],
         cambios=[('modelo/estado.ts', "  if (r.pendientes > 0) return `Espera", "  if (r.pendientes < 0) return `Espera"),
                  ('modelo/estado.ts', "return x.tipo === 'reposo' && r.pendientes === 0 && r.listas > 0;", "return x.tipo === 'reposo' && r.listas > 0;")]),
    dict(nombre='la muerte de un Worker no falla su trabajo', escenario='obrero', rojas=['error/obrero_muere'],
         cambios=[('pagina/cola.ts', "      if (o.trabajo) this.resolver(o.trabajo, { tipo: 'error', mensaje });\n", '      void mensaje;\n')]),
    dict(nombre='el visor no se entera de que su foto se reemplazó', escenario='visor', rojas=['visor/foto_reemplazada'],
         cambios=[('modelo/estado.ts', "return v.tipo === 'abierto' && !fotoDe(tarjetas.get(v.clave)) ? { tipo: 'cerrado' } : v;", 'return v;')]),
    dict(nombre='el revelado del visor hace cola detrás del lote', escenario='visor', rojas=['visor/a_mitad_del_lote'],
         cambios=[('pagina/cola.ts', "if (trabajo.prioridad === 'primero') {", "if (trabajo.prioridad === 'primero' && this.maximo < 0) {")]),
]


def parte_mutaciones(tmp):
    print('\n== Mutaciones: ¿las comprobaciones se ponen en rojo cuando el código se rompe? ==')
    evidencia = []
    src = os.path.join(WEB, 'src')
    for m in MUTACIONES:
        originales = {}
        try:
            for archivo, viejo, nuevo in m['cambios']:
                ruta = os.path.join(src, archivo)
                texto = open(ruta, encoding='utf-8').read()
                originales.setdefault(ruta, texto)
                assert texto.count(viejo) == 1, f'la mutación ya no aplica: {archivo}: {viejo[:60]!r}'
                open(ruta, 'w', encoding='utf-8').write(texto.replace(viejo, nuevo))
            bien, salida = compilar()
            assert bien, f'la mutación no compila: {salida[-400:]}'
            HECHAS.clear()
            DIAGNOSTICOS.clear()
            print(f'\n-- mutación: {m["nombre"]}')
            mtmp = tempfile.mkdtemp(prefix='mut_', dir=tmp)
            parte_navegador(mtmp, dict(), solo=[m['escenario']])
            shutil.rmtree(mtmp, ignore_errors=True)
            rojas = sorted(k for k, v in HECHAS.items() if not v['ok'])
            evidencia.append(dict(mutacion=m['nombre'], cambios=[dict(archivo=a, antes=v.strip(), despues=n.strip()) for a, v, n in m['cambios']], escenario=m['escenario'],
                                  debian_fallar=m['rojas'], fallaron=rojas, siguieron_verdes=sorted(k for k, v in HECHAS.items() if v['ok']),
                                  detectada=all(r in rojas for r in m['rojas'])))
        finally:
            for ruta, texto in originales.items():
                open(ruta, 'w', encoding='utf-8').write(texto)
    bien, salida = compilar()
    assert bien, salida
    HECHAS.clear()
    DIAGNOSTICOS.clear()
    return evidencia


def main():
    mutar = '--mutaciones' in sys.argv[1:]
    solo = [a[7:] for a in sys.argv[1:] if a.startswith('--solo=')]       # para depurar un escenario: --solo=exportar
    ruta_mut = os.path.join(OUT, 'mutaciones.json')
    previas = json.load(open(ruta_mut)) if os.path.exists(ruta_mut) else None
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    tmp = tempfile.mkdtemp(prefix='e2e_web_')
    informe = dict(node=subprocess.run([NODE, '--version'], capture_output=True, text=True).stdout.strip())
    fallas = []
    try:
        if mutar:
            previas = dict(fecha=time.strftime('%Y-%m-%d %H:%M'), mutaciones=parte_mutaciones(tmp))
        if previas:
            json.dump(previas, open(ruta_mut, 'w'), indent=1, ensure_ascii=False)
        print('\n== 0. Compilar (npm run build: tsc estricto, web/src → web/public/js) ==')
        bien, salida = compilar()
        informe['typescript'] = subprocess.run([os.path.join(WEB, 'node_modules', '.bin', 'tsc'), '--version'], capture_output=True, text=True).stdout.strip()
        if chequear('compila', bien, f'web/src compila en modo estricto sin errores ({informe["typescript"]}); de ahí sale lo que se prueba y lo que se publica', salida[-1500:]):
            if solo:
                parte_navegador(tmp, informe, solo=solo)
            else:
                parte_equivalencia(tmp, informe)
                parte_navegador(tmp, informe)
                parte_paquete(informe)
                ok = [c for c in informe['casos'].values() if c.get('ms_node')]
                informe['resumen_tiempos_ms'] = dict(
                    python_por_raw=round(float(np.mean([c['ms_python'] for c in ok]))), node_por_raw=round(float(np.mean([c['ms_node'] for c in ok]))),
                    navegador_por_raw=round(float(np.mean(list(informe['navegador']['ms_por_raw_navegador'].values())))),
                    python_mismas_fotos_que_el_navegador=round(float(np.mean(list(informe['navegador']['ms_por_raw_python'].values())))))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        fallas = [k for k, v in HECHAS.items() if not v['ok']]
        informe.update(comportamientos=len(HECHAS), fallas=fallas, comprobaciones=HECHAS, diagnosticos=DIAGNOSTICOS, mutaciones=previas)
        json.dump(informe, open(os.path.join(OUT, 'reporte.json'), 'w'), indent=1, ensure_ascii=False, default=str)
    if previas:
        det = [m for m in previas['mutaciones'] if m['detectada']]
        print(f"\nmutaciones ({previas['fecha']}): {len(det)} de {len(previas['mutaciones'])} detectadas")
        for m in previas['mutaciones']:
            print(f"  {'detectada   ' if m['detectada'] else 'NO DETECTADA'} {m['mutacion']} → en rojo: {', '.join(m['fallaron']) or 'nada'}")
        if mutar and len(det) != len(previas['mutaciones']):
            fallas = fallas + ['mutaciones sin detectar']
    bien = len(HECHAS) - sum(not v['ok'] for v in HECHAS.values())
    print(f"\n{bien} de {len(HECHAS)} comportamientos distintos verificados · "
          f"{'TODO BIEN' if not fallas else f'{len(fallas)} FALLAS: ' + ', '.join(fallas)} · artefacto en {OUT}/")
    return 1 if fallas else 0


if __name__ == '__main__':
    sys.exit(main())
