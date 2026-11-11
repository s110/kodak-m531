#!/usr/bin/env python3
"""Prueba E2E de km531fw.py con la cabecera y el código reales de la M531.

Arma una imagen de prueba (NO es para flashear: la sección de datos sale de la RAM, mutada) con la
cabecera real y las secciones verificadas, y exige:
  1. la imagen base verifica con el port del validador del firmware;
  2. el parche que restaura MemRead/MemWrite (stubs vacíos en producción) se aplica por la CLI,
     recalcula la suma y el resultado verifica; el código cambia sólo en esos 8 bytes;
  3. la CLI rechaza: parche sobre la rutina de actualización, parche que cruza el final de una
     sección, dirección fuera del archivo, base corrupta, y sobrescribir una salida existente;
  4. un byte corrupto sin recalcular suma hace que el validador rechace la imagen.
Artefacto: work/e2e_fw/reporte.json con hashes.
"""
import hashlib
import json
import os
import struct
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import km531fw as fw  # noqa: E402

OUT = os.path.join(RAIZ, 'work', 'e2e_fw')
RAM = os.path.join(RAIZ, 'dump', 'ram_snapshot.bin')


def imagen_de_prueba():
    r = open(RAM, 'rb').read()
    cab = bytearray(open(os.path.join(RAIZ, 'firmware', 'stock', 'header_first_0xa0.bin'), 'rb').read())
    cab += b'\0' * (0x200 - len(cab))
    regs = fw.registros(bytes(cab))
    fin = max(x['off'] + x['size'] for x in regs if x['tipo'] in (0, 1))
    img = bytearray(fin)
    img[:0x200] = cab
    codigo = open(os.path.join(RAIZ, 'firmware', 'stock', 'rec0_code_0x48000.bin'), 'rb').read()
    for x in regs:
        if x['tipo'] not in (0, 1):
            continue
        datos = codigo if x['i'] == 0 else r[x['dest']:x['dest'] + x['size']]
        img[x['off']:x['off'] + x['size']] = datos
    fw.recalcular(img, {1, 4, 5, 6})  # datos e idiomas salen de la RAM: sumas propias de la prueba
    return bytes(img)


def cli(*args):
    return subprocess.run([sys.executable, os.path.join(AQUI, 'km531fw.py'), *args], capture_output=True, text=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    rep = dict(casos=[])
    def caso(nombre, ok, **extra):
        rep['casos'].append(dict(nombre=nombre, ok=bool(ok), **extra)); print('OK   ' if ok else 'FALLO', nombre)

    base = imagen_de_prueba()
    rb = os.path.join(OUT, 'BASE_NO_FLASHEAR.FW')
    open(rb, 'wb').write(base)
    caso('base verifica', not fw.validar_como_firmware(base), sha256=hashlib.sha256(base).hexdigest())
    caso('código igual al verificado desde la RAM', cli('vs-ram', rb).returncode == 0)

    salida = os.path.join(OUT, 'MEMRW_NO_FLASHEAR.FW')
    if os.path.exists(salida):
        os.remove(salida)
    p = cli('patch', rb, salida, '0x2d6608:e07f0080', '0x2d660c:e07f20a0')
    nuevo = open(salida, 'rb').read() if os.path.exists(salida) else b''
    difs = [i for i in range(len(base)) if nuevo and base[i] != nuevo[i]]
    r0 = fw.registros(base)[0]
    cambios_codigo = [i for i in difs if r0['off'] <= i < r0['off'] + r0['size']]
    cambios_cab = [i for i in difs if i < 0x200]
    ini_parche = r0['off'] + 0x2d6608 - r0['dest']
    caso('parche MemRead/MemWrite aplicado y verifica', p.returncode == 0 and nuevo and not fw.validar_como_firmware(nuevo)
         and cambios_codigo and all(ini_parche <= i < ini_parche + 8 for i in cambios_codigo)
         and all(0x10 + 12 <= i < 0x10 + 16 for i in cambios_cab),
         bytes_codigo=len(cambios_codigo), bytes_cabecera=len(cambios_cab),
         sha256=hashlib.sha256(nuevo).hexdigest() if nuevo else None, salida_cli=p.stdout.strip())
    off = r0['off'] + 0x2d6608 - r0['dest']
    caso('bytes del parche en su lugar', nuevo[off:off + 8] == bytes.fromhex('e07f0080e07f20a0'))

    rechazos = {
        'parche sobre la rutina de actualización': ('0x2bce00:00000000',),
        'parche que cruza el final de la sección de código': (f"{r0['dest'] + r0['size'] - 2:#x}:00000000",),
        'dirección fuera del archivo': ('0x3000000:00',),
    }
    for nombre, parches in rechazos.items():
        s = os.path.join(OUT, 'NO_DEBE_EXISTIR.FW')
        q = cli('patch', rb, s, *parches)
        caso('rechaza ' + nombre, q.returncode != 0 and not os.path.exists(s), error=q.stderr.strip()[-160:])
    q = cli('patch', rb, salida, '0x2d6610:e07f')
    caso('no sobrescribe una salida existente', q.returncode != 0)

    corrupta = bytearray(base); corrupta[r0['off'] + 0x1000] ^= 0xFF
    rc = os.path.join(OUT, 'CORRUPTA.FW'); open(rc, 'wb').write(corrupta)
    caso('validador rechaza un byte corrupto', bool(fw.validar_como_firmware(bytes(corrupta))))
    q = cli('patch', rc, os.path.join(OUT, 'NO_DEBE_EXISTIR2.FW'), '0x2d6608:e07f0080')
    caso('no parchea una base corrupta', q.returncode != 0)
    os.remove(rc)

    rep['resultado'] = 'OK' if all(c['ok'] for c in rep['casos']) else 'FALLO'
    json.dump(rep, open(os.path.join(OUT, 'reporte.json'), 'w'), indent=2, ensure_ascii=False)
    print('reporte:', os.path.join(OUT, 'reporte.json'), '→', rep['resultado'])
    sys.exit(0 if rep['resultado'] == 'OK' else 1)


if __name__ == '__main__':
    main()
