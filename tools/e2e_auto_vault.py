#!/usr/bin/env python3
"""Prueba E2E de los DNG automáticos tras el respaldo de sdvault, con launchd de verdad (otro label,
vault y sello temporales; el agente real y el PhotoVault real no se tocan).

Cómo puede fallar (escrito antes de la prueba):
  1. El agente no despierta cuando sdvault toca su sello (WatchPaths mal puesto), o despierta y no ve el vault.
  2. Al instalar reconvierte todo lo viejo del vault en vez de marcarlo como visto.
  3. Toma por fotos de la M531 archivos de otras cámaras (DCIM/100CANON) o temporales de sdvault a medio copiar.
  4. Un RAW sin JPG o con el JPG truncado no se convierte, o el JPG roto se copia.
  5. Repetir (otro respaldo sin fotos nuevas) reconvierte o vuelve a avisar.
  6. Pisa un DNG que ya existía (hecho por ./importar el mismo día).
  7. Dos corridas a la vez (respaldos seguidos) convierten dos veces o dejan .parcial.
  8. Escribe algo dentro del vault.
  9. --quitar deja el agente cargado o el plist en su sitio.
Artefacto: work/e2e_auto_vault/reporte.json (comprobaciones, registro del agente, árbol de salida con SHA-256).
uso: .venv/bin/python tools/e2e_auto_vault.py
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import rawpy

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
D13 = os.path.join(RAIZ, 'dump', '2026-11-13')
OUT = os.path.join(RAIZ, 'work', 'e2e_auto_vault')
PY = sys.executable
LABEL = 'me.sebastian.m531-dng-e2e'
CHECKS = []


def chequear(cond, msg):
    CHECKS.append(dict(ok=bool(cond), msg=msg))
    print(('ok    ' if cond else 'FALLA ') + msg, flush=True)


def huella(carpeta):
    h = {}
    for d, _, fs in os.walk(carpeta):
        for f in fs:
            p = os.path.join(d, f)
            h[os.path.relpath(p, carpeta)] = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    return h


def como_sdvault(origen, destino, recorte=None):
    """Copia como sdvault: a .sdvault-tmp-* y renombra al final."""
    tmp = os.path.join(os.path.dirname(destino), '.sdvault-tmp-' + os.path.basename(destino) + '-1')
    datos = open(origen, 'rb').read()
    open(tmp, 'wb').write(datos[:recorte] if recorte else datos)
    os.replace(tmp, destino)


def esperar_linea(log, n_lineas, texto, s=90):
    t = time.time()
    while time.time() - t < s:
        if os.path.exists(log):
            lineas = open(log).read().splitlines()[n_lineas:]
            if any(texto in x for x in lineas):
                return lineas
        time.sleep(0.5)
    return None


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    tmp = tempfile.mkdtemp(prefix='e2e_auto_')
    vault, destino = os.path.join(tmp, 'PhotoVault'), os.path.join(tmp, 'm531_dng')
    estado, sello, log = os.path.join(tmp, 'estado', 'vistos.json'), os.path.join(tmp, 'sdvault', 'last-ok'), os.path.join(tmp, 'agente.log')
    m531 = os.path.join(vault, 'NO-NAME-e2e00001', 'DCIM', '101KM531')
    canon = os.path.join(vault, 'CANON_DC-e2e00002', 'DCIM', '100CANON')
    for d in (m531, canon, os.path.dirname(sello)):
        os.makedirs(d)
    open(sello, 'w').write('x\n')
    como_sdvault(os.path.join(D13, '101O2030.RAW'), os.path.join(m531, '101O2030.RAW'))
    como_sdvault(os.path.join(D13, '101_2030.JPG'), os.path.join(m531, '101_2030.JPG'))
    shutil.copy(os.path.join(D13, '101O2031.RAW'), os.path.join(canon, '101O9999.RAW'))
    hoy = os.path.join(destino, datetime.date.today().isoformat())
    informe = {}
    try:
        # instalar: marca la base
        p = subprocess.run([PY, os.path.join(AQUI, 'instalar_auto.py'), '--label', LABEL, '--sello', sello, '--vault', vault,
                            '--destino', destino, '--estado', estado, '--log', log, '--sin-aviso'], capture_output=True, text=True)
        informe['instalar'] = p.stdout + p.stderr
        chequear(p.returncode == 0, f'instala y carga el agente ({p.stderr.strip()})')
        chequear(subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/{LABEL}'], capture_output=True).returncode == 0,
                 'launchd lo tiene cargado')
        chequear(json.load(open(estado)) and not os.path.exists(destino), 'la base marca lo viejo como visto y no convierte nada')

        # un respaldo de sdvault con fotos nuevas + un temporal a medio copiar
        como_sdvault(os.path.join(D13, '101O2036.RAW'), os.path.join(m531, '101O2036.RAW'))
        como_sdvault(os.path.join(D13, '101_2036.JPG'), os.path.join(m531, '101_2036.JPG'))
        como_sdvault(os.path.join(D13, '101O2032.RAW'), os.path.join(m531, '101O2032.RAW'))
        como_sdvault(os.path.join(D13, '101_2032.JPG'), os.path.join(m531, '101_2032.JPG'), recorte=30_000)
        como_sdvault(os.path.join(D13, '101O2029.RAW'), os.path.join(m531, '101O2029.RAW'))
        open(os.path.join(m531, '.sdvault-tmp-101O2034.RAW-7'), 'wb').write(open(os.path.join(D13, '101O2034.RAW'), 'rb').read()[:5_000_000])
        os.makedirs(hoy)
        open(os.path.join(hoy, '101_2029.DNG'), 'wb').write(b'hecho antes por ./importar')
        antes_vault = huella(vault)
        n0 = 0
        open(sello, 'w').write('2026-11-14T00:00:00Z\n')     # sdvault cierra una corrida limpia
        lineas = esperar_linea(log, n0, 'DNG nuevos')
        chequear(lineas is not None, 'launchd despierta el agente al tocar el sello')
        informe['registro_1'] = lineas
        dngs = sorted(f for f in os.listdir(hoy) if f.endswith('.DNG'))
        chequear(dngs == ['101_2029.DNG', '101_2032.DNG', '101_2036.DNG'], f'DNG del día: {dngs}')
        chequear(open(os.path.join(hoy, '101_2029.DNG'), 'rb').read() == b'hecho antes por ./importar', 'no pisa un DNG que ya existía')
        chequear(not os.path.exists(os.path.join(hoy, '101_2030.DNG')), 'lo viejo (base) no se convierte')
        chequear(not any('9999' in f or '2034' in f for f in os.listdir(hoy)), 'ignora otra cámara y el temporal de sdvault')
        chequear(os.path.exists(os.path.join(hoy, '101_2036.JPG')) and not os.path.exists(os.path.join(hoy, '101_2032.JPG')),
                 'JPG entero al lado; el truncado no se copia')
        for n in ('101_2032.DNG', '101_2036.DNG'):
            with rawpy.imread(os.path.join(hoy, n)) as r:
                chequear(r.raw_image.shape == (3264, 4320), f'{n}: LibRaw lee el mosaico')
        chequear(lineas and any('1 ya existían' in x for x in lineas), 'el registro cuenta el DNG que ya existía')

        # otro respaldo sin nada nuevo: silencio
        n1 = len(open(log).read().splitlines())
        time.sleep(11)                                    # ThrottleInterval
        open(sello, 'w').write('2026-11-14T00:30:00Z\n')
        time.sleep(8)
        chequear(len(open(log).read().splitlines()) == n1, 'un respaldo sin fotos nuevas no hace nada ni escribe')

        # dos corridas a la vez
        como_sdvault(os.path.join(D13, '101O2037.RAW'), os.path.join(m531, '101O2037.RAW'))
        como_sdvault(os.path.join(D13, '101_2037.JPG'), os.path.join(m531, '101_2037.JPG'))
        antes_vault = huella(vault)
        cmd = [PY, os.path.join(AQUI, 'auto_vault.py'), '--vault', vault, '--destino', destino, '--estado', estado, '--sin-aviso']
        ps = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for _ in range(2)]
        salidas = [x.communicate(timeout=120)[0] for x in ps]
        informe['dos_a_la_vez'] = salidas
        chequear(sum('101O2037.RAW →' in s for s in salidas) == 1, 'dos corridas a la vez convierten una sola vez')
        chequear(not [f for f in os.listdir(hoy) if 'parcial' in f], 'sin .parcial')
        chequear(huella(vault) == antes_vault, 'el vault quedó idéntico (SHA-256)')
        informe['salida'] = huella(destino)
    finally:
        p = subprocess.run([PY, os.path.join(AQUI, 'instalar_auto.py'), '--quitar', '--label', LABEL], capture_output=True, text=True)
        chequear(p.returncode == 0 and not os.path.exists(os.path.expanduser(f'~/Library/LaunchAgents/{LABEL}.plist'))
                 and subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/{LABEL}'], capture_output=True).returncode != 0,
                 '--quitar descarga el agente y borra el plist')
        informe['log'] = open(log).read() if os.path.exists(log) else ''
        shutil.rmtree(tmp, ignore_errors=True)
    informe['checks'] = CHECKS
    fallas = [c['msg'] for c in CHECKS if not c['ok']]
    json.dump(informe, open(os.path.join(OUT, 'reporte.json'), 'w'), indent=1, ensure_ascii=False)
    print(f"\n{len(CHECKS) - len(fallas)}/{len(CHECKS)} comprobaciones · artefacto en {OUT}/reporte.json")
    return 1 if fallas else 0


if __name__ == '__main__':
    sys.exit(main())
