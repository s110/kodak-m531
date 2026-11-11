#!/usr/bin/env python3
"""Verifica los scripts .srt antes de copiarlos a la SD de la M531.

uso: python3 -I tools/check_scripts.py CARPETA_BATCH

Falla (código 1) si un script:
  * llama a una función que no está en la lista permitida (ver REVERSIBILIDAD.md);
  * usa Run_SpecifyFunc con un destino que no sea peek32 o poke32;
  * escribe con poke32 dentro de la rutina de actualización, la NAND Tool o fuera de la SDRAM;
  * no tiene número de línea, repite números o no termina en END;
  * BatchScripts.txt nombra un script que no existe (o le pone extensión).
"""
import os
import re
import sys

PERMITIDAS = {
    'ScreenString', 'ScreenInt32', 'ScreenFloat32', 'ScreenInt32_Hex', 'delay_us', 'ClearOSD',
    'SaveCFAonTake', 'SaveCFAonIRP', 'Take12BitCCDRaw', 'EnableS1ImgSaving',
    'Run_SpecifyFunc', 'GetSystemDateTime', 'DebugMsgLog',
}
PEEK32, POKE32 = 0x198bbc, 0x2e8a84
ZONAS_PROHIBIDAS = [  # (inicio, fin, motivo)
    (0x2bcdb8, 0x2bd800, 'rutina de actualización de firmware'),
    (0x2bd800, 0x2bf000, 'menú oculto / NAND Tool / scripts de arranque'),
    (0x0, 0x48000, 'vectores y pilas'),
]
RAM_MAX = 0x4000000
CLAVES = {'REM', 'LET', 'END', 'IF', 'THEN', 'ELSE', 'GOTO', 'GOSUB', 'RETURN', 'SYSTEM', 'FOREIGN',
          'DEBUGGING', 'LOG_PRINT', 'SCREEN_PRINT', 'QUIT', 'TRUE', 'FALSE'}


def revisar_srt(ruta):
    errores = []
    lineas = open(ruta, 'rb').read().decode('ascii').splitlines()
    vistos = []
    for n, l in enumerate(lineas, 1):
        if not l.strip():
            continue
        m = re.match(r'\s*(\d+)\s+(.*)$', l)
        if not m:
            errores.append(f'{ruta}:{n}: sin número de línea')
            continue
        num, cuerpo = int(m.group(1)), m.group(2)
        if num in vistos:
            errores.append(f'{ruta}:{n}: número de línea repetido {num}')
        if vistos and num < vistos[-1]:
            errores.append(f'{ruta}:{n}: números de línea fuera de orden')
        vistos.append(num)
        if cuerpo.startswith('REM'):
            continue
        sin_texto = re.sub(r'"[^"]*"', '""', cuerpo)
        for f in re.findall(r'([A-Za-z_]\w*)\s*\(', sin_texto):
            if f not in PERMITIDAS:
                errores.append(f'{ruta}:{n}: función no permitida {f}')
        for args in re.findall(r'Run_SpecifyFunc\s*\(([^)]*)\)', sin_texto):
            v = [int(x, 0) for x in re.findall(r'-?(?:0x[0-9a-fA-F]+|\d+)', args)]
            if len(v) != 9:
                errores.append(f'{ruta}:{n}: Run_SpecifyFunc necesita 9 argumentos')
                continue
            if v[0] not in (PEEK32, POKE32):
                errores.append(f'{ruta}:{n}: Run_SpecifyFunc a {v[0]:#x}, sólo se permite peek32/poke32')
            dest = v[3]
            if not 0 <= dest < RAM_MAX or dest % 4:
                errores.append(f'{ruta}:{n}: dirección {dest:#x} fuera de RAM o desalineada')
            if v[0] == POKE32:
                for ini, fin, motivo in ZONAS_PROHIBIDAS:
                    if ini <= dest < fin:
                        errores.append(f'{ruta}:{n}: poke32 en {dest:#x} ({motivo})')
    if not any(re.match(r'\s*\d+\s+END\s*$', l) for l in lineas):
        errores.append(f'{ruta}: no termina en END')
    return errores


def main():
    carpeta = sys.argv[1]
    errores = []
    lista = os.path.join(carpeta, 'BatchScripts.txt')
    if os.path.exists(lista):
        for nombre in open(lista).read().split():
            if nombre.lower().endswith('.srt'):
                errores.append(f'BatchScripts.txt: "{nombre}" lleva extensión; el firmware agrega .srt')
            elif not os.path.exists(os.path.join(carpeta, nombre + '.srt')):
                errores.append(f'BatchScripts.txt: falta {nombre}.srt')
    for f in sorted(os.listdir(carpeta)):
        if f.lower().endswith('.srt'):
            errores += revisar_srt(os.path.join(carpeta, f))
    for e in errores:
        print('ERROR', e)
    print('OK' if not errores else f'{len(errores)} error(es)')
    sys.exit(1 if errores else 0)


if __name__ == '__main__':
    main()
