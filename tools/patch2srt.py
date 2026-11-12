#!/usr/bin/env python3
"""Convierte parches de código en un script .srt de nivel 2 (sólo RAM; se pierde al apagar).

uso: python3 -I tools/patch2srt.py NOMBRE DIR_RAM:HEX [DIR_RAM:HEX ...] > Batch/NOMBRE.srt

Para cada palabra de 32 bits afectada, el script:
  1. lee la palabra con peek32 y la compara con la del firmware de fábrica verificado; si alguna
     no coincide (otra versión de firmware o parche ya aplicado), no escribe nada y avisa. La
     guardia es cerrada ante fallos: si el IF no se cumple o no se interpreta, salta al aviso;
  2. escribe todas las palabras con poke32;
  3. vacía la caché de datos de cada palabra escrita (dcache_flush_range 0x24e140, 4 bytes) para
     que el núcleo lea el código nuevo desde la memoria. No hay forma de invalidar una posible caché
     de instrucciones: parchear sólo código que no se ejecutó en esta sesión (ver NOTAS.md);
  4. relee cada palabra y la anota en el .LOG (LOG_PRINT VERIFY); si la guardia falla, sólo anota
     la lectura original y no escribe nada.
Es exactamente el mismo cambio de bytes que km531fw.py aplicaría al .FW: así se prueba antes de
flashear. La sintaxis de IF/GOTO y los números negativos se confirman con la sonda P5 del kit.
"""
import os
import struct
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
CODIGO = os.path.join(os.path.dirname(AQUI), 'firmware', 'stock', 'rec0_code_0x48000.bin')
BASE = 0x48000
PEEK32, POKE32, FLUSH = 0x198bbc, 0x2e8a84, 0x24e140
sys.path.insert(0, AQUI)
from km531fw import ZONAS_INTOCABLES  # noqa: E402


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def palabras(parches):
    cod = open(CODIGO, 'rb').read()
    orig, nuevo = {}, {}
    for dir_ram, datos in parches:
        for ini, fin, motivo in ZONAS_INTOCABLES:
            if dir_ram < fin and dir_ram + len(datos) > ini:
                raise SystemExit(f'parche en {dir_ram:#x} toca la {motivo}')
        if not (BASE <= dir_ram and dir_ram + len(datos) <= BASE + len(cod)):
            raise SystemExit(f'{dir_ram:#x} fuera de la sección de código')
        for k, b in enumerate(datos):
            a = dir_ram + k
            w = a & ~3
            if w not in orig:
                orig[w] = struct.unpack_from('<I', cod, w - BASE)[0]
                nuevo[w] = bytearray(cod[w - BASE:w - BASE + 4])
            nuevo[w][a - w] = b
    return [(w, orig[w], struct.unpack('<I', bytes(nuevo[w]))[0]) for w in sorted(orig)]


def generar(nombre, parches):
    ws = palabras(parches)
    L, n = [], 10
    def linea():
        nonlocal n
        n += 10
        return n - 10
    def add(s):
        L.append(f'{linea()} {s}')
    add(f'REM {nombre}: parche en RAM de {len(ws)} palabra(s); se pierde al apagar')
    # Guardia cerrada ante fallos: cada IF salta hacia adelante sólo si la palabra es la de fábrica;
    # si el IF no se cumple, o el intérprete lo ignora, la línea siguiente va al aviso y no escribe.
    for i, (w, o, _) in enumerate(ws):
        add(f'FOREIGN v{i} = Run_SpecifyFunc({PEEK32}, 1, 0, {w}, 0, 0, 0, 0, 0)')
        sigue = n + 20
        add(f'IF v{i} == {s32(o)} THEN {sigue}')
        add('GOTO 9000')
    for i, (w, _, nv) in enumerate(ws):
        add(f'FOREIGN r{i} = Run_SpecifyFunc({POKE32}, 2, 0, {w}, {s32(nv)}, 0, 0, 0, 0)')
        add(f'FOREIGN f{i} = Run_SpecifyFunc({FLUSH}, 2, 0, {w}, 4, 0, 0, 0, 0)')
    # la pantalla no muestra lo que dibujan los scripts al arrancar: el resultado va al .LOG
    for i, (w, _, _) in enumerate(ws):
        add(f'FOREIGN c{i} = Run_SpecifyFunc({PEEK32}, 1, 0, {w}, 0, 0, 0, 0, 0)')
        add(f'LOG_PRINT VERIFY c{i}')
    add('END')
    L.append('9000 LOG_PRINT VERIFY v0')  # guardia fallida: sólo queda la lectura original
    L.append('9010 END')
    L.append('RUN')  # sin RUN el programa sólo se carga (0x10776c)
    return '\r\n'.join(L) + '\r\n'


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    ps = []
    for s in sys.argv[2:]:
        a, h = s.split(':')
        ps.append((int(a, 0), bytes.fromhex(h)))
    sys.stdout.write(generar(sys.argv[1], ps))
