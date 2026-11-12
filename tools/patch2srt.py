#!/usr/bin/env python3
"""Convierte parches de código en un script .srt de nivel 2 (sólo RAM; se pierde al apagar).

uso: python3 -I tools/patch2srt.py NOMBRE DIR_RAM:HEX [DIR_RAM:HEX ...] > Batch/NOMBRE.srt

Trabaja por mitades de 16 bits de cada palabra afectada, porque el intérprete no admite literales
negativos como operando de `==` (detiene la CPU) y una palabra con el bit 31 no tiene literal decimal
sin signo. Sólo usa la sintaxis del kit: `FOREIGN v = Run_SpecifyFunc(...)` con 9 enteros sin signo,
`IF v == N THEN línea`, `LOG_PRINT VERIFY v`, `END` y `RUN`. Sin GOTO, sin LET, variables de una letra.
El script:
  1. lee cada mitad con peek16 y la compara con la del firmware de fábrica verificado. Guardia
     cerrada ante fallos: si una mitad no coincide (otra versión de firmware o parche ya aplicado),
     la línea siguiente anota esa lectura en el .LOG y termina con END, antes de cualquier escritura;
  2. escribe con poke16 sólo las mitades que cambian (la mitad baja antes que la alta);
  3. vacía la caché de datos de cada palabra escrita (dcache_flush_range 0x24e140, 4 bytes) para
     que el núcleo lea el código nuevo desde la memoria. No hay forma de invalidar una posible caché
     de instrucciones: parchear sólo código que no se ejecutó en esta sesión (ver NOTAS.md);
  4. relee cada mitad escrita y la anota en el .LOG (LOG_PRINT VERIFY).
Es exactamente el mismo cambio de bytes que km531fw.py aplicaría al .FW: así se prueba antes de
flashear. peek16, poke16 y el vaciado de caché todavía no corrieron en la cámara: probar primero un
script mínimo.
"""
import os
import struct
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
CODIGO = os.path.join(os.path.dirname(AQUI), 'firmware', 'stock', 'rec0_code_0x48000.bin')
BASE = 0x48000
PEEK16, POKE16, FLUSH = 0x736e6, 0x13f09a, 0x24e140
sys.path.insert(0, AQUI)
from km531fw import ZONAS_INTOCABLES  # noqa: E402


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
    mitades = []  # (dirección, valor de fábrica, valor nuevo)
    for w, o, nv in ws:
        mitades += [(w, o & 0xffff, nv & 0xffff), (w + 2, o >> 16, nv >> 16)]
    cambian = [m for m in mitades if m[1] != m[2]]
    if not cambian:
        raise SystemExit('el parche no cambia nada respecto del firmware de fábrica')
    tocadas = sorted({a & ~3 for a, _, _ in cambian})
    if len(mitades) + 2 * len(cambian) + len(tocadas) > 26:
        raise SystemExit('parche demasiado grande para variables de una letra: partirlo en varios scripts')
    letras = iter('abcdefghijklmnopqrstuvwxyz')
    L, n = [], 10
    def add(s):
        nonlocal n
        L.append(f'{n} {s}')
        n += 10
    def llamada(var, f, nargs, a1, a2=0):
        add(f'FOREIGN {var} = Run_SpecifyFunc({f}, {nargs}, 0, {a1}, {a2}, 0, 0, 0, 0)')
    add(f'REM {nombre}: parche en RAM de {len(cambian)} mitad(es) de 16 bits; se pierde al apagar')
    # Guardia cerrada ante fallos: el IF salta sobre "anotar y terminar" sólo si la mitad es la de
    # fábrica. Todas las guardias van antes de la primera escritura.
    for a, o, _ in mitades:
        v = next(letras)
        llamada(v, PEEK16, 1, a)
        add(f'IF {v} == {o} THEN {n + 30}')
        add(f'LOG_PRINT VERIFY {v}')
        add('END')
    for a, _, nv in cambian:
        llamada(next(letras), POKE16, 2, a, nv)
    for w in tocadas:
        llamada(next(letras), FLUSH, 2, w, 4)
    # la pantalla no muestra lo que dibujan los scripts al arrancar: el resultado va al .LOG
    for a, _, _ in cambian:
        v = next(letras)
        llamada(v, PEEK16, 1, a)
        add(f'LOG_PRINT VERIFY {v}')
    add('END')
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
