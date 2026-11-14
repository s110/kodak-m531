#!/usr/bin/env python3
"""DNG automáticos tras cada respaldo de sdvault (PhotoVault).

sdvault copia la SD al vault y, al terminar una corrida limpia, toca ~/.local/state/sdvault/last-ok. Un
agente de launchd (me.sebastian.m531-dng, ver tools/instalar_auto.sh) vigila ese archivo y corre esto:

  1. Busca en <vault>/*/DCIM/*KM531/ los RAW de la M531 (101O####.RAW) que todavía no se vieron.
     sdvault escribe a .sdvault-tmp-* y renombra al final, así que un 101O####.RAW ya está completo.
  2. Convierte cada uno a DNG en <destino>/<fecha de hoy>/ con su JPG al lado (como ./importar y el
     conversor), 3 a la vez. Si ese DNG ya existe (p. ej. lo hizo ./importar), no lo pisa.
  3. Avisa con una notificación de macOS y deja registro en ~/Library/Logs/m531_dng.log.

El vault sólo se lee. "Visto" = ruta en el vault + tamaño + fecha, guardado en el estado; --base marca
todo lo que ya hay como visto sin convertir (lo que se hace al instalar, para no reconvertir lo viejo).

uso: .venv/bin/python tools/auto_vault.py [--base] [--vault DIR] [--destino DIR] [--estado ARCHIVO] [--sin-aviso]
"""
import argparse
import concurrent.futures as cf
import datetime
import fcntl
import json
import multiprocessing
import os
import re
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from conversor_ui import convertir_uno  # noqa: E402

RE_RAW = re.compile(r'(\d{3})O(\d{4})\.RAW', re.I)
RE_CARPETA = re.compile(r'\d{3}KM531', re.I)


def registrar(msg):
    print(f'{datetime.datetime.now().isoformat(timespec="seconds")} {msg}', flush=True)


def raws_del_vault(vault):
    """(clave, ruta) de cada RAW de la M531 en el vault. Sólo tarjetas con una carpeta DCIM/1xxKM531."""
    out = []
    for tarjeta in sorted(os.listdir(vault)):
        dcim = os.path.join(vault, tarjeta, 'DCIM')
        if tarjeta.startswith('.') or not os.path.isdir(dcim):
            continue
        for carpeta in sorted(os.listdir(dcim)):
            c = os.path.join(dcim, carpeta)
            if not RE_CARPETA.fullmatch(carpeta) or not os.path.isdir(c):
                continue
            for n in sorted(os.listdir(c)):
                if RE_RAW.fullmatch(n):
                    p = os.path.join(c, n)
                    st = os.stat(p)
                    out.append((f'{os.path.relpath(p, vault)}|{st.st_size}|{int(st.st_mtime)}', p))
    return out


def avisar(texto):
    script = f'display notification {json.dumps(texto)} with title "Kodak M531"'
    subprocess.run(['osascript', '-e', script], capture_output=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--vault', default='/Volumes/Datos/PhotoVault')
    ap.add_argument('--destino', default=os.path.expanduser('~/Pictures/m531_dng'))
    ap.add_argument('--estado', default=os.path.expanduser('~/.local/state/m531_dng/vistos.json'))
    ap.add_argument('--base', action='store_true', help='marcar todo lo que hay como visto, sin convertir')
    ap.add_argument('--balance', choices=['auto', 'camara'], default='auto')
    ap.add_argument('--sin-aviso', action='store_true', help='sin notificación de macOS (pruebas)')
    a = ap.parse_args(argv)

    if not os.path.isdir(a.vault):
        return 0                                         # disco desmontado: nada que hacer
    os.makedirs(os.path.dirname(a.estado), exist_ok=True)
    cerrojo = open(a.estado + '.lock', 'w')
    try:
        fcntl.flock(cerrojo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        registrar('otra corrida en curso; ésta no hace nada')
        return 0
    try:
        vistos = set(json.load(open(a.estado)))
    except Exception:
        vistos = set()

    def guardar():
        with open(a.estado + '.tmp', 'w') as f:
            json.dump(sorted(vistos), f, indent=0)
        os.replace(a.estado + '.tmp', a.estado)

    todos = raws_del_vault(a.vault)
    nuevos = [(k, p) for k, p in todos if k not in vistos]
    if a.base:
        vistos.update(k for k, _ in todos)
        guardar()
        registrar(f'base: {len(todos)} RAW del vault marcados como vistos')
        return 0
    if not nuevos:
        return 0

    salida = os.path.join(a.destino, datetime.date.today().isoformat())
    os.makedirs(salida, exist_ok=True)
    trabajos, errores, hechos, saltados = {}, [], [], 0
    t0 = time.time()
    with cf.ProcessPoolExecutor(3, mp_context=multiprocessing.get_context('spawn')) as ex:
        for k, p in nuevos:
            pre, num = RE_RAW.fullmatch(os.path.basename(p)).groups()
            d = os.path.dirname(p)
            dng = os.path.join(salida, f'{pre}_{num}.DNG')
            if os.path.exists(dng):
                saltados += 1
                vistos.add(k)
                continue
            campos = [p] + [os.path.join(d, n) for n in os.listdir(d) if n.upper() == f'{pre}B{num}.RAW']
            jpg = next((os.path.join(d, n) for n in os.listdir(d) if n.upper() == f'{pre}_{num}.JPG'), None)
            trabajos[ex.submit(convertir_uno, campos, dng, jpg, dng[:-4] + '.JPG', a.balance, 'no')] = (k, p, dng)
        for fut in cf.as_completed(trabajos):
            k, p, dng = trabajos[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = dict(ok=False, error=f'{e.__class__.__name__}: {e}')
            if r['ok']:
                hechos.append(os.path.basename(dng))
                vistos.add(k)
                registrar(f'{os.path.basename(p)} → {dng} ({r["formato"]}, balance {r["balance"]}, '
                          f'{"con" if r["jpg"] else "sin"} JPG)')
            else:
                errores.append(f'{os.path.basename(p)}: {r["error"]}')
                registrar(f'ERROR {os.path.basename(p)}: {r["error"]}')
                vistos.add(k)                            # un RAW ilegible no se reintenta en cada respaldo
            guardar()
    guardar()
    registrar(f'{len(hechos)} DNG nuevos en {salida} ({time.time() - t0:.1f} s), {saltados} ya existían, '
              f'{len(errores)} con error')
    if not a.sin_aviso and (hechos or errores):
        avisar(f'{len(hechos)} DNG nuevos en m531_dng/{os.path.basename(salida)}'
               + (f' · {len(errores)} con error (ver ~/Library/Logs/m531_dng.log)' if errores else ''))
    return 1 if errores else 0


if __name__ == '__main__':
    sys.exit(main())
