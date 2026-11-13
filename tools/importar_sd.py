#!/usr/bin/env python3
"""Importa las fotos de la SD de la M531: copia verificada + DNG listos para abrir.

uso:  ./importar                       (con la SD montada; equivale a .venv/bin/python tools/importar_sd.py)
      ./importar --verticales 2031,2034-2036      esas fotos se tomaron con la cámara en vertical
      ./importar --origen CARPETA --copias DIR --destino DIR --fecha AAAA-MM-DD

Qué hace, en orden:
  1. Lee "/Volumes/NO NAME/DCIM/101KM531" (RAW y JPG) y los .LOG de la carpeta Batch de la SD.
  2. Copia lo que no estaba ya importado a <copias>/<fecha>/ y verifica cada copia con SHA-256
     (lo leído de la SD contra lo releído del disco). Deja SHA256SUMS en la carpeta.
  3. Convierte cada RAW a DNG en <destino>/<fecha>/, con su JPG al lado.
  4. Imprime un resumen. Código de salida 1 si algo falló.

Por omisión: copias en dump/ de la repo, destino ~/Pictures/m531_dng, fecha de hoy (el reloj de la
cámara no es fiable). La SD sólo se lee: todos sus archivos se abren en modo lectura y el programa se
niega a copiar dentro de ella.

"Ya importado" = mismo contenido (SHA-256) que algún archivo de cualquier carpeta de <copias> con
SHA256SUMS, incluidas las dump/rawNN anteriores. Para no releer la tarjeta entera en cada importación,
<copias>/importados.json recuerda nombre, tamaño y fecha de lo ya visto.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import m531raw  # noqa: E402

ORIGEN = '/Volumes/NO NAME/DCIM/101KM531'
TROZO = 4 << 20
RE_FOTO = re.compile(r'(\d{3})([Ob_])(\d{4})\.(RAW|JPG)$', re.I)
FORMATOS = {28_200_960: 'modo 3, 16 bits', 14_100_480: 'modo 0 (P8), 8 bits con curva', 17_625_600: 'modo 2, 10 bits'}


def sha_archivo(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for b in iter(lambda: f.read(TROZO), b''):
            h.update(b)
    return h.hexdigest()


def copiar_verificado(origen, destino):
    """Copia origen → destino y devuelve el SHA-256. Lee el origen una sola vez (sólo lectura), escribe
    a un archivo .parcial, lo relee del disco y compara; sólo entonces le da el nombre final."""
    parcial = destino + '.parcial'
    h = hashlib.sha256()
    with open(origen, 'rb') as f, open(parcial, 'wb') as g:
        for b in iter(lambda: f.read(TROZO), b''):
            h.update(b)
            g.write(b)
        g.flush()
        os.fsync(g.fileno())
    if sha_archivo(parcial) != h.hexdigest():
        os.remove(parcial)
        raise IOError('la copia no coincide con lo leído de la SD (SHA-256 distinto)')
    st = os.stat(origen)
    os.utime(parcial, ns=(st.st_atime_ns, st.st_mtime_ns))
    os.replace(parcial, destino)
    return h.hexdigest()


def hashes_conocidos(copias):
    """SHA-256 de todo lo que ya está en <copias>/*/SHA256SUMS → carpeta donde está."""
    vistos = {}
    if not os.path.isdir(copias):
        return vistos
    for d in sorted(os.listdir(copias)):
        sums = os.path.join(copias, d, 'SHA256SUMS')
        if not os.path.isfile(sums):
            continue
        for linea in open(sums, encoding='utf-8', errors='replace'):
            p = linea.split(None, 1)
            if len(p) == 2 and len(p[0]) == 64 and os.path.exists(os.path.join(copias, d, p[1].strip().lstrip('*'))):
                vistos.setdefault(p[0].lower(), d)
    return vistos


def leer_sums(carpeta):
    r = {}
    sums = os.path.join(carpeta, 'SHA256SUMS')
    if os.path.isfile(sums):
        for linea in open(sums, encoding='utf-8', errors='replace'):
            p = linea.split(None, 1)
            if len(p) == 2:
                r[p[1].strip()] = p[0].lower()
    return r


def lista_numeros(texto):
    """'2031,2034-2036' → {2031, 2034, 2035, 2036}"""
    nums = set()
    for parte in filter(None, (texto or '').replace(' ', '').split(',')):
        a, _, b = parte.partition('-')
        if not a.isdigit() or (b and not b.isdigit()):
            raise SystemExit(f'--verticales: no entiendo "{parte}" (ejemplo: 2031,2034-2036)')
        nums.update(range(int(a), int(b or a) + 1))
    return nums


def descripcion(info):
    if info.get('modo4') == 'lineal12':
        return 'M4L, 12 bits lineales'
    if info.get('modo4') == 'curva10':
        return 'modo 4 (P9), 10 bits con curva'
    return FORMATOS.get(info['tamanos'][0], f"{info['packing']} {info['ancho']}x{info['alto']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--origen', default=ORIGEN, help='carpeta DCIM de la SD (por omisión %(default)s)')
    ap.add_argument('--batch', help='carpeta de los .LOG (por omisión Batch/ en la raíz de la SD)')
    ap.add_argument('--copias', default=os.path.join(RAIZ, 'dump'), help='dónde guardar las copias verificadas')
    ap.add_argument('--destino', default=os.path.expanduser('~/Pictures/m531_dng'), help='dónde dejar DNG y JPG')
    ap.add_argument('--fecha', default=datetime.date.today().isoformat(), help='nombre de la carpeta del día')
    ap.add_argument('--rotar', choices=list(m531raw.GIROS) + ['camara'], default='no',
                    help='giro de todas las fotos: no = apaisadas como el sensor (por omisión), izq = vertical '
                         'como gira la cámara, der, 180, camara = lo que hizo la cámara con cada JPG')
    ap.add_argument('--verticales', default='', help='números de foto tomadas en vertical (giro izq), p. ej. 2031,2034-2036')
    ap.add_argument('--balance', choices=['auto', 'camara', 'fijo'], default='auto')
    ap.add_argument('--abrir', action='store_true', help='abrir la carpeta de DNG en darktable al terminar')
    a = ap.parse_args(argv)
    verticales = lista_numeros(a.verticales)

    origen = os.path.realpath(a.origen)
    if not os.path.isdir(origen):
        print(f'No encuentro la SD: {a.origen} no existe. ¿Está montada? (con otra ruta: --origen CARPETA)')
        return 2
    raiz_sd = os.path.dirname(os.path.dirname(origen))
    batch = os.path.realpath(a.batch) if a.batch else os.path.join(raiz_sd, 'Batch')
    copias, destino = os.path.realpath(a.copias), os.path.realpath(a.destino)
    volumen = raiz_sd if os.path.ismount(raiz_sd) else origen
    for d in (copias, destino):                          # nunca escribir en la tarjeta
        if os.path.commonpath([d, volumen]) == volumen or os.path.commonpath([d, origen]) == origen:
            print(f'{d} está dentro de la SD: no se escribe en la tarjeta.')
            return 2

    # ---- qué hay en la SD
    entradas = []                                        # (ruta, nombre, tipo)
    for n in sorted(os.listdir(origen)):
        if n.startswith('.') or not RE_FOTO.fullmatch(n):
            continue
        entradas.append((os.path.join(origen, n), n, 'RAW' if n.upper().endswith('.RAW') else 'JPG'))
    if os.path.isdir(batch):
        for n in sorted(os.listdir(batch)):
            if not n.startswith('.') and n.upper().endswith('.LOG'):
                entradas.append((os.path.join(batch, n), n, 'LOG'))
    cuenta = {t: sum(1 for e in entradas if e[2] == t) for t in ('RAW', 'JPG', 'LOG')}
    print(f"SD: {a.origen}: {cuenta['RAW']} RAW, {cuenta['JPG']} JPG, {cuenta['LOG']} LOG")

    # ---- qué es nuevo
    os.makedirs(copias, exist_ok=True)
    ruta_indice = os.path.join(copias, 'importados.json')
    try:
        indice = json.load(open(ruta_indice))
    except Exception:
        indice = {}
    conocidos = hashes_conocidos(copias)
    nuevos, ya, errores = [], 0, []
    for ruta, nombre, tipo in entradas:
        st = os.stat(ruta)
        clave = f'{nombre}|{st.st_size}|{st.st_mtime_ns}'
        if tipo != 'LOG' and clave in indice and indice[clave] in conocidos:
            ya += 1
            continue
        try:
            sha = sha_archivo(ruta)
        except OSError as e:
            errores.append(f'{nombre}: no se pudo leer de la SD ({e})')
            continue
        if sha in conocidos:
            ya += 1
            indice[clave] = sha
            continue
        nuevos.append((ruta, nombre, tipo, sha, clave))

    # ---- carpeta del día: si un nombre ya existe allí con otro contenido, se usa <fecha>_2, _3…
    def carpeta_libre():
        k = 1
        while True:
            c = os.path.join(copias, a.fecha if k == 1 else f'{a.fecha}_{k}')
            sums = leer_sums(c)
            if not any(os.path.exists(os.path.join(c, n)) and sums.get(n) != sha for _, n, t, sha, _ in nuevos if t != 'LOG'):
                return c
            k += 1
    carpeta = carpeta_libre()
    sufijo = os.path.basename(carpeta)
    copiados, total_bytes = [], 0
    if nuevos:
        os.makedirs(carpeta, exist_ok=True)
        sums = leer_sums(carpeta)
        for ruta, nombre, tipo, sha, clave in nuevos:
            final = nombre
            if tipo == 'LOG' and os.path.exists(os.path.join(carpeta, nombre)):
                # el mismo script deja un log nuevo en cada sesión: se guardan los dos
                base, ext = os.path.splitext(nombre)
                k = 2
                while os.path.exists(os.path.join(carpeta, f'{base}_{k}{ext}')):
                    k += 1
                final = f'{base}_{k}{ext}'
            try:
                if os.path.exists(os.path.join(carpeta, final)) and sums.get(final) == sha:
                    pass                                   # quedó copiado en una pasada anterior que se cortó
                else:
                    sha_copia = copiar_verificado(ruta, os.path.join(carpeta, final))
                    if sha_copia != sha:
                        os.remove(os.path.join(carpeta, final))
                        raise IOError('el archivo cambió entre dos lecturas de la SD')
            except OSError as e:
                errores.append(f'{nombre}: {e}')
                continue
            sums[final] = sha
            indice[clave] = sha
            conocidos[sha] = sufijo
            copiados.append((final, tipo))
            total_bytes += os.path.getsize(os.path.join(carpeta, final))
            with open(os.path.join(carpeta, 'SHA256SUMS'), 'w', encoding='utf-8') as f:
                f.writelines(f'{h}  {n}\n' for n, h in sorted(sums.items()))
    json.dump(indice, open(ruta_indice, 'w'), indent=0, sort_keys=True)
    print(f"Copiados {len(copiados)} archivos ({total_bytes / 1e6:.1f} MB) a {carpeta}, verificados con SHA-256; "
          f"{ya} ya estaban importados." if copiados else f'Nada nuevo que copiar; {ya} archivos ya estaban importados.')

    # ---- DNG: cada RAW de la carpeta del día que aún no lo tiene
    salida = os.path.join(destino, sufijo)
    hechos, filas = 0, []
    if os.path.isdir(carpeta):
        ruta_resumen = os.path.join(salida, 'resumen.json')
        try:
            resumen = {x['raw']: x for x in json.load(open(ruta_resumen))}
        except Exception:
            resumen = {}
        for n in sorted(os.listdir(carpeta)):
            mm = RE_FOTO.fullmatch(n)
            if not mm:
                continue
            pre, letra, num, ext = mm.groups()
            os.makedirs(salida, exist_ok=True)
            giro_n = 'izq' if int(num) in verticales else a.rotar
            jpg_copia = os.path.join(salida, f'{pre}_{num}.JPG')
            if ext.upper() == 'JPG':
                # el JPG va al lado del DNG, con la misma orientación; uno de 0 bytes (cuelgue) no se lleva
                if os.path.getsize(os.path.join(carpeta, n)) > 10_000 and not os.path.exists(jpg_copia):
                    shutil.copy2(os.path.join(carpeta, n), jpg_copia)
                    giro = m531raw.giro_jpg(jpg_copia) if giro_n == 'camara' else m531raw.GIROS[giro_n]
                    m531raw.orientar(jpg_copia, giro)
                continue
            if letra != 'O':
                continue                                   # el campo 'b' acompaña a su 'O'
            dng = os.path.join(salida, f'{pre}_{num}.DNG')
            if os.path.exists(dng):
                continue
            campos = [os.path.join(carpeta, n)]
            segundo = os.path.join(carpeta, f'{pre}b{num}.{ext}')
            if os.path.exists(segundo):
                campos.append(segundo)
            jpg = m531raw._jpg_hermano(campos[0])
            con_jpg = bool(jpg and os.path.getsize(jpg) > 10_000)
            try:
                info = m531raw.convertir(campos, dng + '.parcial', balance=a.balance, rotar=giro_n)
                os.replace(dng + '.parcial', dng)
            except (SystemExit, Exception) as e:          # un RAW ilegible no detiene a los demás
                if os.path.exists(dng + '.parcial'):
                    os.remove(dng + '.parcial')
                errores.append(f'{n}: no se pudo convertir ({e})')
                resumen[n] = dict(raw=n, estado='error', error=str(e)[-300:])
                continue
            hechos += 1
            resumen[n] = dict(raw=n, estado='ok', formato=descripcion(info), balance=info['balance'], neutro=info['neutro'],
                              blanco=info['blanco'], giro=giro_n, jpg=con_jpg)
            filas.append(f"  {num}  {descripcion(info):<31} balance {info['balance']:<13} "
                         f"{'vertical' if info['giro'] % 2 else 'apaisada'}  {'con JPG' if con_jpg else 'sin JPG'}")
        if resumen:
            json.dump(sorted(resumen.values(), key=lambda x: x['raw']), open(ruta_resumen, 'w'), indent=1, ensure_ascii=False)
    print(f'DNG nuevos: {hechos} en {salida}' if hechos else 'DNG nuevos: 0')
    for f in filas:
        print(f)
    if errores:
        print(f'ERRORES ({len(errores)}):')
        for e in errores:
            print('  ' + e)
    if a.abrir and hechos:
        subprocess.run(['open', '-a', 'darktable', salida])
    return 1 if errores else 0


if __name__ == '__main__':
    sys.exit(main())
