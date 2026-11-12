#!/usr/bin/env python3
"""Inspecciona, verifica y parchea imágenes de firmware KM531.FW (Altek "RHIR", Kodak M531).

uso:
  km531fw.py info IMAGEN                     cabecera, registros y verificación
  km531fw.py vs-ram IMAGEN                   compara secciones con lo verificado desde la RAM
  km531fw.py patch IMAGEN SALIDA PARCHE... [--particion=TAMAÑO]
                                             PARCHE = DIRECCION_RAM:HEXBYTES (p. ej. 0x2d6608:7fe0d801)

Formato (validador del propio firmware en 0x2bd46c, rutina de actualización 0x2bcdb8):
  0x000 "RHIR"; 0x006 u8 número de registros; 0x008 u32 palabra de modelo = 0x01121410
  0x00C u16,u16 versión MAIN; 0x010 registros de 16 B:
        u16 tipo (1 = verificado, 0 = no verificado, 2 = especial), u16 0,
        u16 sector inicial (512 B), u16 nº de sectores, u32 destino en RAM, u32 sum32
  El validador sólo exige: RHIR, modelo, tamaño ≤ partición y sum32 de los registros tipo 1.
  sum32 = suma de palabras de 32 bits little-endian (0x2e06e4).

Cómo puede fallar un parche (escrito antes del código; cada punto tiene su comprobación):
  1. Dirección fuera de las secciones del archivo → se rechaza.
  2. Parche que cruza el límite de una sección → se rechaza.
  3. Parche sobre la rutina de actualización, el menú oculto o la NAND Tool → se rechaza
     (son la vía de vuelta, ver REVERSIBILIDAD.md).
  4. Sumas no recalculadas → el firmware rechaza el archivo ("Firmware file is invalid").
  5. Registro tipo 2 tocado o "corregido" → nunca se modifica.
  6. Imagen base que no verifica → no se parchea.
  7. Imagen base que no es la de fábrica verificada → aviso (código distinto del de la RAM).
"""
import hashlib
import os
import struct
import sys

MODELO = 0x01121410
AQUI = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.join(os.path.dirname(AQUI), 'firmware', 'stock')
CODIGO_STOCK_SHA = '366cb4a4a4b74234e36f5aae3a155c03195c7bb1b82b9685f775131c32a35cbc'
ZONAS_INTOCABLES = sorted([
    (0x2bcdb8, 0x2bd800, 'rutina de actualización'),
    (0x2bd800, 0x2bf000, 'menú oculto / NAND Tool / scripts de arranque'),
    (0x2e06e4, 0x2e0708, 'sum32 usada por el validador'),
    # funciones de las que depende la vía de vuelta (llamadas desde 0x2bcdb8–0x2bd800)
    (0x4c1c0, 0x4c1f0, 'palabra de modelo y rutas del .FW'),
    (0x6584c, 0x658a0, 'tamaño de partición'),
    (0x657b8, 0x65800, 'NAND'),
    (0x1433c0, 0x143700, 'lectura de NAND'),
    (0x1436fc, 0x143800, 'lectura de NAND'),
    (0x143a90, 0x143b00, 'NAND'),
    (0x1447a0, 0x144b00, 'escritura de NAND'),
    (0x3019c8, 0x301a00, 'memcmp de verificación'),
    (0x7574c, 0x75780, 'pool de memoria del actualizador'),
    (0xe0c00, 0xe1000, 'acceso a archivos (FAT) del actualizador'),
    # revisión de Fable (2026-11-12): vía de vuelta completa
    (0x23bcf0, 0x23bd60, 'entrada al menú oculto'),
    (0x1f2c00, 0x1f2c90, 'pantalla UPDATE FIRMWARE'),
    (0x6615c, 0x66190, 'estado de teclas'),
    (0xe1f5c, 0xe1fc0, 'apertura de pantallas'),
    (0x24cc00, 0x24ce00, 'NAND Tool'),
    (0x2c0000, 0x2c3000, 'NAND Tool'),
    (0x1445d0, 0x144700, 'escritura de NAND (interna)'),
    (0x143eb8, 0x144080, 'NAND (interna)'),
    (0x14335c, 0x1433c0, 'NAND (interna)'),
    (0x12e2e4, 0x12ec00, 'tabla de particiones'),
    (0x2bd024, 0x2bd2bc, 'actualizador con contenedor 5-en-1'),
    (0x2bcf28, 0x2bd024, 'actualizador del boot'),
])
MARCADOR_5EN1 = b'INFO' + bytes.fromhex('55aaaa55')


def sum32(b: bytes) -> int:
    b = b + b'\0' * (-len(b) % 4)
    return sum(struct.unpack_from('<%dI' % (len(b) // 4), b)) & 0xFFFFFFFF


def registros(d: bytes):
    out = []
    for i in range(d[6]):
        t, z, st, n, dest, ck = struct.unpack_from('<HHHHII', d, 0x10 + 16 * i)
        out.append(dict(i=i, tipo=t, sector=st, n=n, off=st * 512, size=n * 512, dest=dest, sum=ck))
    return out


def validar_como_firmware(d: bytes, tam_particion=None):
    """Port del validador 0x2bd46c. Devuelve lista de problemas (vacía = el firmware lo acepta).

    Además marca el paquete 5-en-1: si el archivo contiene INFO+0x55aaaa55, el actualizador
    (0x2bd1e4–0x2bd236) llama a 0x2bd664, que escribe la partición 0. Nunca queremos eso."""
    p = []
    if MARCADOR_5EN1 in d:
        p.append('contiene el marcador 5-en-1 (INFO+0x55aaaa55): escribiría la partición 0')
    if tam_particion is not None and len(d) > tam_particion:
        p.append('archivo más grande que la partición')
    if d[:4] != b'RHIR':
        p.append('falta RHIR')
        return p
    if struct.unpack_from('<I', d, 8)[0] != MODELO:
        p.append('palabra de modelo distinta de 0x01121410')
    for r in registros(d):
        if r['tipo'] != 1:
            continue
        if r['off'] + r['size'] > len(d):
            p.append(f"registro {r['i']} se sale del archivo")
        elif sum32(d[r['off']:r['off'] + r['size']]) != r['sum']:
            p.append(f"registro {r['i']}: sum32 no coincide")
    return p


def verificar_estricto(d: bytes):
    """Además de lo que mira el firmware: sumas de tipo 0 (por si el arranque las revisa)."""
    p = validar_como_firmware(d)
    for r in registros(d):
        if r['tipo'] == 0 and r['off'] + r['size'] <= len(d):
            if sum32(d[r['off']:r['off'] + r['size']]) != r['sum']:
                p.append(f"registro {r['i']} (tipo 0): sum32 no coincide")
    return p


def recalcular(d: bytearray, indices):
    for r in registros(d):
        if r['i'] in indices and r['tipo'] in (0, 1):
            struct.pack_into('<I', d, 0x10 + 16 * r['i'] + 12, sum32(bytes(d[r['off']:r['off'] + r['size']])))


def ubicar(d: bytes, dir_ram: int, n: int):
    hits = [r for r in registros(d) if r['tipo'] in (0, 1) and r['dest'] <= dir_ram < r['dest'] + r['size']]
    if not hits:
        raise ValueError(f'{dir_ram:#x} no cae en ninguna sección del archivo')
    if len(hits) > 1:
        raise ValueError(f'{dir_ram:#x} cae en varias secciones ({[h["i"] for h in hits]}); '
                         'los idiomas comparten destino en RAM: parchear por desplazamiento de archivo')
    r = hits[0]
    if dir_ram + n > r['dest'] + r['size']:
        raise ValueError(f'el parche en {dir_ram:#x} cruza el final del registro {r["i"]}')
    return r, r['off'] + dir_ram - r['dest']


def parchear(d: bytes, parches, tam_particion=None):
    if validar_como_firmware(d, tam_particion):
        raise ValueError('la imagen base no verifica; no se parchea')
    out = bytearray(d)
    tocados = set()
    for dir_ram, datos in parches:
        for ini, fin, motivo in ZONAS_INTOCABLES:
            if dir_ram < fin and dir_ram + len(datos) > ini:
                raise ValueError(f'parche en {dir_ram:#x} toca la {motivo}')
        r, off = ubicar(out, dir_ram, len(datos))
        out[off:off + len(datos)] = datos
        tocados.add(r['i'])
    recalcular(out, tocados)
    if MARCADOR_5EN1 in out and MARCADOR_5EN1 not in d:
        raise ValueError('el parche introduce el marcador INFO+0x55aaaa55: el actualizador escribiría la partición 0')
    problemas = validar_como_firmware(bytes(out), tam_particion)
    if problemas:
        raise ValueError('la salida no verifica: ' + '; '.join(problemas))
    return bytes(out)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    acc, ruta = sys.argv[1], sys.argv[2]
    d = open(ruta, 'rb').read()
    if acc == 'info':
        print(f'{ruta}: {len(d)} B, sha256 {hashlib.sha256(d).hexdigest()}')
        print(f'  modelo {struct.unpack_from("<I", d, 8)[0]:#x}, MAIN {struct.unpack_from("<HH", d, 12)}')
        for r in registros(d):
            ok = '' if r['tipo'] == 2 else ('ok' if sum32(d[r['off']:r['off'] + r['size']]) == r['sum'] else 'MAL')
            print(f"  rec{r['i']} tipo {r['tipo']} archivo {r['off']:#x}+{r['size']:#x} → RAM {r['dest']:#x} sum {r['sum']:#010x} {ok}")
        p = verificar_estricto(d)
        print('  firmware lo acepta:', 'sí' if not validar_como_firmware(d) else 'NO')
        for x in p:
            print('   -', x)
        sys.exit(1 if p else 0)
    if acc == 'vs-ram':
        r0 = registros(d)[0]
        cod = d[r0['off']:r0['off'] + r0['size']]
        same = hashlib.sha256(cod).hexdigest() == CODIGO_STOCK_SHA
        print('código igual al verificado desde la RAM:', 'sí' if same else 'NO')
        sys.exit(0 if same else 1)
    if acc == 'patch':
        salida = sys.argv[3]
        parches, particion = [], None
        for s in sys.argv[4:]:
            if s.startswith('--particion='):
                particion = int(s.split('=')[1], 0)
                continue
            a, h = s.split(':')
            parches.append((int(a, 0), bytes.fromhex(h)))
        if particion is None:
            print('aviso: sin --particion=TAMAÑO (sale de D1 NANDPartition.txt); no se compara con la partición 6')
        out = parchear(d, parches, particion)
        if os.path.exists(salida):
            sys.exit(f'{salida} ya existe; no se sobrescribe')
        open(salida, 'wb').write(out)
        print(f'{salida}: sha256 {hashlib.sha256(out).hexdigest()}; el firmware lo acepta')


if __name__ == '__main__':
    main()
