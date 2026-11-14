#!/usr/bin/env python3
"""Instala (o quita) el agente de launchd que hace los DNG tras cada respaldo de sdvault.

uso:  .venv/bin/python tools/instalar_auto.py            instala y carga me.sebastian.m531-dng
      .venv/bin/python tools/instalar_auto.py --quitar   lo descarga y borra el plist

Al instalar por primera vez marca como vistos los RAW que ya están en el vault (no reconvierte lo viejo;
para eso está el conversor: arrastrar la carpeta). El agente corre cuando sdvault toca su sello
~/.local/state/sdvault/last-ok, es decir, al final de cada respaldo limpio.
Las demás opciones existen para la prueba E2E (otro label, vault, sello y destino).
"""
import argparse
import os
import plistlib
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
PY = os.path.join(RAIZ, '.venv', 'bin', 'python')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--quitar', action='store_true')
    ap.add_argument('--label', default='me.sebastian.m531-dng')
    ap.add_argument('--sello', default=os.path.expanduser('~/.local/state/sdvault/last-ok'))
    ap.add_argument('--vault', default='/Volumes/Datos/PhotoVault')
    ap.add_argument('--destino', default='/Volumes/Datos/personal/Fotos/m531_dng')
    ap.add_argument('--estado', default=os.path.expanduser('~/.local/state/m531_dng/vistos.json'))
    ap.add_argument('--log', default=os.path.expanduser('~/Library/Logs/m531_dng.log'))
    ap.add_argument('--sin-aviso', action='store_true')
    a = ap.parse_args(argv)

    plist = os.path.expanduser(f'~/Library/LaunchAgents/{a.label}.plist')
    dominio = f'gui/{os.getuid()}'
    subprocess.run(['launchctl', 'bootout', f'{dominio}/{a.label}'], capture_output=True)
    if a.quitar:
        if os.path.exists(plist):
            os.remove(plist)
        print(f'{a.label} quitado')
        return 0

    args = [PY, os.path.join(AQUI, 'auto_vault.py'), '--vault', a.vault, '--destino', a.destino, '--estado', a.estado]
    if a.sin_aviso:
        args.append('--sin-aviso')
    if not os.path.exists(a.estado):
        p = subprocess.run(args + ['--base'], capture_output=True, text=True)
        if p.returncode:
            sys.exit(f'no se pudo marcar la base: {p.stderr or p.stdout}')
        print(p.stdout.strip())
    os.makedirs(os.path.dirname(a.log), exist_ok=True)
    with open(plist, 'wb') as f:
        plistlib.dump({
            'Label': a.label,
            'ProgramArguments': args,
            'WatchPaths': [a.sello],                     # sdvault lo toca al cerrar una corrida limpia
            'ThrottleInterval': 10,
            'ProcessType': 'Background',
            'LowPriorityIO': True,
            'Nice': 5,
            'StandardOutPath': a.log,
            'StandardErrorPath': a.log,
        }, f)
    p = subprocess.run(['launchctl', 'bootstrap', dominio, plist], capture_output=True, text=True)
    if p.returncode:
        sys.exit(f'launchctl bootstrap falló: {p.stderr.strip()}')
    print(f'{a.label} cargado: vigila {a.sello}; DNG en {a.destino}/<fecha>; registro en {a.log}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
