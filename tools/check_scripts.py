#!/usr/bin/env python3
"""Verifica los scripts .srt antes de copiarlos a la SD de la M531.

uso: python3 -I tools/check_scripts.py CARPETA_BATCH

Falla (código 1) si un script:
  * nombra cualquier identificador que no sea palabra clave, variable asignada con LET o función
    de la lista permitida (con o sin paréntesis: `FOREIGN UpdateFW 1` también se detecta);
  * usa una palabra clave (SYSTEM/FOREIGN/DEBUGGING) que no corresponde a la tabla de la función;
  * usa Run_SpecifyFunc sin 9 enteros literales, con un destino distinto de peek32/poke32/flush,
    con nargs distinto del de ese destino o con outpos ≠ 0;
  * escribe con poke32 dentro de una zona intocable o fuera de la SDRAM;
  * salta con GOTO/GOSUB a una línea que no existe;
  * no tiene número de línea, repite números, los desordena o no termina en END;
  * BatchScripts.txt nombra un script inexistente, le pone extensión o usa un nombre que otras
    pantallas del firmware lanzan solas (Reset, ISO_Calibration, BatTestCIPA, BatTestPreview, Preview).
"""
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from km531fw import ZONAS_INTOCABLES  # noqa: E402

PERMITIDAS = {
    'ScreenString', 'ScreenInt32', 'ScreenFloat32', 'ScreenInt32_Hex', 'delay_us', 'ClearOSD',
    'SaveCFAonTake', 'SaveCFAonIRP', 'Take12BitCCDRaw', 'EnableS1ImgSaving',
    'Run_SpecifyFunc', 'GetSystemDateTime', 'DebugMsgLog', 'MemRead',
}
PEEK32, POKE32, FLUSH = 0x198bbc, 0x2e8a84, 0x24e140
NARGS = {PEEK32: 1, POKE32: 2, FLUSH: 2}
ZONAS_PROHIBIDAS = ZONAS_INTOCABLES + [(0x0, 0x48000, 'vectores y pilas')]
RAM_MAX = 0x4000000
CLAVES = {'REM', 'LET', 'END', 'IF', 'THEN', 'ELSE', 'GOTO', 'GOSUB', 'RETURN', 'SYSTEM', 'FOREIGN',
          'DEBUGGING', 'LOG_PRINT', 'SCREEN_PRINT', 'QUIT', 'TRUE', 'FALSE'}
RESERVADOS = {'reset', 'iso_calibration', 'battestcipa', 'battestpreview', 'preview'}
_mapa = json.load(open(os.path.join(os.path.dirname(AQUI), 'docs_script_manejadores.json')))
TABLA = {}
for e in _mapa:
    TABLA.setdefault(e['nombre'], set()).add(e['palabra_clave'])


def revisar_srt(ruta):
    errores = []
    lineas = open(ruta, 'rb').read().decode('ascii').splitlines()
    numeros, saltos, variables, cuerpos = [], [], set(), []
    for n, l in enumerate(lineas, 1):
        if not l.strip():
            continue
        m = re.match(r'\s*(\d+)\s+(.*)$', l)
        if not m:
            errores.append(f'{ruta}:{n}: sin número de línea')
            continue
        num, cuerpo = int(m.group(1)), m.group(2)
        if num in numeros:
            errores.append(f'{ruta}:{n}: número de línea repetido {num}')
        if numeros and num < numeros[-1]:
            errores.append(f'{ruta}:{n}: números de línea fuera de orden')
        numeros.append(num)
        if cuerpo.startswith('REM'):
            continue
        s = re.sub(r'"[^"]*"', '""', cuerpo)
        cuerpos.append((n, s))
        mv = re.match(r'LET\s+([A-Za-z_]\w*)\s*=', s)
        if mv:
            variables.add(mv.group(1))
        saltos += [(n, int(x)) for x in re.findall(r'\b(?:GOTO|GOSUB)\s+(\d+)', s)]
    for n, s in cuerpos:
        for kw, f in re.findall(r'\b(SYSTEM|FOREIGN|DEBUGGING)\s+([A-Za-z_]\w*)', s):
            if f not in PERMITIDAS:
                errores.append(f'{ruta}:{n}: función no permitida {f}')
            elif kw not in TABLA.get(f, set()):
                errores.append(f'{ruta}:{n}: {f} no es de la tabla {kw} (es {sorted(TABLA.get(f, []))})')
        for ident in re.findall(r'\b[A-Za-z_]\w*\b', s):
            if ident not in CLAVES and ident not in variables and ident not in PERMITIDAS:
                errores.append(f'{ruta}:{n}: identificador desconocido o no permitido {ident}')
        if 'Run_SpecifyFunc' in s and not re.search(r'Run_SpecifyFunc\s*\(', s):
            errores.append(f'{ruta}:{n}: Run_SpecifyFunc sin paréntesis')
        for args in re.findall(r'Run_SpecifyFunc\s*\(([^)]*)\)', s):
            partes = [p.strip() for p in args.split(',')]
            if len(partes) != 9 or not all(re.fullmatch(r'-?\d+', p) for p in partes):
                errores.append(f'{ruta}:{n}: Run_SpecifyFunc necesita 9 enteros literales')
                continue
            v = [int(p) for p in partes]
            f, nargs, outpos, dest = v[0], v[1], v[2], v[3]
            if f not in NARGS:
                errores.append(f'{ruta}:{n}: Run_SpecifyFunc a {f:#x}, sólo peek32/poke32/flush')
                continue
            if nargs != NARGS[f] or outpos != 0:
                errores.append(f'{ruta}:{n}: nargs/outpos inválidos para {f:#x} ({nargs}, {outpos})')
            if f == FLUSH and not (0 < v[4] <= 0x10000):
                errores.append(f'{ruta}:{n}: flush con longitud {v[4]} fuera de rango')
            if not 0 <= dest < RAM_MAX or dest % 4:
                errores.append(f'{ruta}:{n}: dirección {dest:#x} fuera de RAM o desalineada')
            if f == POKE32:
                for ini, fin, motivo in ZONAS_PROHIBIDAS:
                    if ini <= dest < fin:
                        errores.append(f'{ruta}:{n}: poke32 en {dest:#x} ({motivo})')
    for n, destino in saltos:
        if destino not in numeros:
            errores.append(f'{ruta}:{n}: salto a la línea {destino}, que no existe')
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
        if f.startswith('._'):
            errores.append(f'{f}: archivo de metadatos de macOS; copiar con cp -X o dot_clean')
        elif f.lower().endswith('.srt'):
            if f[:-4].lower() in RESERVADOS:
                errores.append(f'{f}: nombre que otra pantalla del firmware ejecuta sola')
            errores += revisar_srt(os.path.join(carpeta, f))
    for e in errores:
        print('ERROR', e)
    print('OK' if not errores else f'{len(errores)} error(es)')
    sys.exit(1 if errores else 0)


if __name__ == '__main__':
    main()
