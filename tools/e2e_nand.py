#!/usr/bin/env python3
"""Prueba E2E de tools/verificar_volcados.py con piezas reales de la M531.

Arma en work/e2e_nand/ un juego de volcados como los dejaría la NAND Tool, en la disposición más
incómoda admitida: nombres en mayúsculas (FAT), particiones completas con relleno 0xFF, boot con su
cabecera de 16 B. Piezas reales: cabecera RHIR, código, gráficos y rec3 de firmware/stock; boot y
tabla de particiones de dump/ram_snapshot.bin. Piezas de relleno (no existen fuera de la cámara):
sección de datos e idiomas (bytes deterministas con la última palabra ajustada a la sum32 de la
cabecera), calibración, parámetros, reserva y BFN.

Exige, corriendo la CLI de verdad:
  1. el juego sano sale sin errores y reconoce cabecera, código y boot como idénticos a la RAM;
  2. cada daño de tools/NAND_FALLAS.md produce un ERROR en el archivo correcto: bit cambiado en el
     código, en un gráfico (tipo 0), truncado, modelo cambiado, boot con un bit cambiado, boot sin
     cabecera y dañado, tabla con otro tamaño de partición 6, archivo prohibido, calibración
     borrada, archivo ausente y segunda copia alterada;
  3. un boot sano sin cabecera se acepta (disposición alternativa), y un CameraParam distinto del
     anterior se informa con el tramo exacto que cambió.
Artefacto: work/e2e_nand/reporte.json (veredicto por caso y SHA-256 del juego sano).
"""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import km531fw as fw  # noqa: E402
import verificar_volcados as vv  # noqa: E402

OUT = os.path.join(RAIZ, 'work', 'e2e_nand')
RAM = os.path.join(RAIZ, 'dump', 'ram_snapshot.bin')
STOCK = os.path.join(RAIZ, 'firmware', 'stock')


def relleno(n, semilla):
    out, h = bytearray(), hashlib.sha256(semilla.encode()).digest()
    while len(out) < n:
        out += h
        h = hashlib.sha256(h).digest()
    return bytes(out[:n])


def con_suma(n, suma, semilla):
    """n bytes deterministas cuya sum32 es `suma` (se ajusta la última palabra)."""
    b = bytearray(relleno(n, semilla))
    b[-4:] = b'\0\0\0\0'
    struct.pack_into('<I', b, n - 4, (suma - fw.sum32(bytes(b))) & 0xffffffff)
    return bytes(b)


def juego_sano():
    ram = open(RAM, 'rb').read()
    cab = open(os.path.join(STOCK, 'header_first_0xa0.bin'), 'rb').read()
    cab += b'\0' * (0x200 - len(cab))
    main = bytearray(b'\xff' * (vv.PARTICIONES[6][1] * vv.BLOQUE))
    main[:0x200] = cab
    for r in fw.registros(cab):
        if r['tipo'] not in (0, 1):
            continue
        if r['i'] in vv.SECCIONES_RAM:
            pieza = open(os.path.join(STOCK, vv.SECCIONES_RAM[r['i']]), 'rb').read()
            assert len(pieza) == r['size'], r
        else:
            pieza = con_suma(r['size'], r['sum'], f"registro {r['i']}")
        main[r['off']:r['off'] + r['size']] = pieza
    boot = vv.BOOT_CABECERA + ram[0x800000:0x800000 + vv.BOOT_TAM]
    boot += b'\xff' * (vv.PARTICIONES[0][1] * vv.BLOQUE - len(boot))
    tabla = ''.join('%-40s0x%04X\r\n' % (e, v) for e, v in vv.TABLA_TXT).encode()
    p1 = ram[0x4da228:0x4da228 + 0x100] + b'\xff' * 0x3f00
    cal = relleno(vv.PARTICIONES[1][1] * vv.BLOQUE, 'calibración')
    par = relleno(vv.PARTICIONES[3][1] * vv.BLOQUE, 'parámetros')
    return {
        'CALIBRATION.DMP': cal, 'CALIBRATION_2.DMP': cal, 'MAINCODE.DMP': bytes(main), 'BOOTCODE.DMP': boot,
        'NANDPARTITION.TXT': tabla, 'CAMERAPARAM.DMP': par, 'CAMERAPARAM_2.DMP': par,
        'NANDRESERVED.DMP': relleno(vv.PARTICIONES[5][1] * vv.BLOQUE, 'reserva'), 'NANDP1.DMP': p1,
        'BFNSETTING.TXT': b'uwBFN_Version                           0x0001\r\n',
        'BOOTNANDBASE.DMP': relleno(0x4000, 'bfn'),
    }


def escribir(nombre, archivos):
    carpeta = os.path.join(OUT, nombre)
    shutil.rmtree(carpeta, ignore_errors=True)
    os.makedirs(carpeta)
    for n, b in archivos.items():
        open(os.path.join(carpeta, n), 'wb').write(b)
    return carpeta


def correr(carpeta, *extra):
    salida = carpeta + '.json'
    p = subprocess.run([sys.executable, '-I', os.path.join(AQUI, 'verificar_volcados.py'), carpeta,
                        '--json', salida, *extra], capture_output=True, text=True)
    return p.returncode, json.load(open(salida))


def cambiar_bit(b, pos):
    b = bytearray(b)
    b[pos] ^= 0x10
    return bytes(b)


def main():
    os.makedirs(OUT, exist_ok=True)
    sano = juego_sano()
    regs = fw.registros(sano['MAINCODE.DMP'])
    casos, fallas = [], []

    def caso(nombre, archivos, espera, extra=()):
        """espera: lista de (archivo canónico, fragmento de texto) que deben aparecer como ERROR;
        lista vacía = no debe haber ningún ERROR."""
        codigo, rep = correr(escribir(nombre, archivos), *extra)
        errores = [(x['archivo'], x['texto']) for x in rep['lineas'] if x['nivel'] == 'ERROR']
        if espera:
            bien = codigo == 1 and all(any(a == ea and frag in t for a, t in errores) for ea, frag in espera)
            # un daño no debe condenar archivos ajenos
            ajenos = [a for a, _ in errores if a not in {e[0] for e in espera}]
            bien = bien and not ajenos
        else:
            bien = codigo == 0 and not errores
        casos.append(dict(caso=nombre, codigo=codigo, errores=errores, esperado=espera, ok=bien))
        if not bien:
            fallas.append(nombre)
        print(('OK   ' if bien else 'FALLA'), nombre, '' if bien else errores)
        return rep

    rep = caso('sano', sano, [])
    textos = [x['texto'] for x in rep['lineas'] if x['nivel'] == 'OK']
    for frag in ('cabecera RHIR idéntica', 'registro 0: bytes idénticos', 'boot residente en RAM',
                 'con cabecera de 16 B en 0x0', 'las 10 líneas coinciden', 'tabla de la RAM'):
        if not any(frag in t for t in textos):
            fallas.append(f'sano: falta el reconocimiento "{frag}"')
    r0, r2 = regs[0], regs[2]
    m = sano['MAINCODE.DMP']
    caso('bit_en_codigo', {**sano, 'MAINCODE.DMP': cambiar_bit(m, r0['off'] + 0x123457)},
         [('MainCode.dmp', 'registro 0 tipo 1: sum32'), ('MainCode.dmp', 'registro 0: difiere'),
          ('MainCode.dmp', 'el validador del firmware lo rechaza')])
    caso('bit_en_grafico', {**sano, 'MAINCODE.DMP': cambiar_bit(m, r2['off'] + 0x1000)},
         [('MainCode.dmp', 'registro 2 tipo 0: sum32'), ('MainCode.dmp', 'el boot no lo revisa')])
    # dos bits que se compensan en la suma: sólo la comparación de bytes lo ve
    doble = bytearray(m)
    a, c = r0['off'] + 0x2000, r0['off'] + 0x3000
    va, vc = struct.unpack_from('<I', doble, a)[0], struct.unpack_from('<I', doble, c)[0]
    struct.pack_into('<I', doble, a, (va + 1) & 0xffffffff)
    struct.pack_into('<I', doble, c, (vc - 1) & 0xffffffff)
    caso('codigo_misma_suma', {**sano, 'MAINCODE.DMP': bytes(doble)}, [('MainCode.dmp', 'registro 0: difiere')])
    caso('truncado', {**sano, 'MAINCODE.DMP': m[:regs[5]['off'] + 0x1200]},
         [('MainCode.dmp', 'fuera del archivo')])
    otro_modelo = bytearray(m)
    struct.pack_into('<I', otro_modelo, 8, 0x01121310)
    caso('otro_modelo', {**sano, 'MAINCODE.DMP': bytes(otro_modelo)},
         [('MainCode.dmp', 'palabra de modelo'), ('MainCode.dmp', 'la cabecera difiere')])
    b = sano['BOOTCODE.DMP']
    caso('boot_bit', {**sano, 'BOOTCODE.DMP': cambiar_bit(b, 16 + 0x1100)}, [('BootCode.dmp', 'sum32 del cuerpo')])
    caso('boot_sin_cabecera_sano', {**sano, 'BOOTCODE.DMP': b[16:] + b'\xff' * 16}, [])
    caso('boot_sin_cabecera_danado', {**sano, 'BOOTCODE.DMP': cambiar_bit(b[16:] + b'\xff' * 16, 0x800)},
         [('BootCode.dmp', 'no aparece la cabecera')])
    caso('tabla_otro_tamano', {**sano, 'NANDPARTITION.TXT': sano['NANDPARTITION.TXT'].replace(b'0x01F4', b'0x01E0')},
         [('NANDPartition.txt', 'uwSize_HexMain'), ('MainCode.dmp', 'más grande que lo que declara')])
    caso('archivo_prohibido', {**sano, 'TBM_HD14P.BIN': b'RHIR', 'ALLOW_ERASE_BOOT': b''},
         [('TBM_HD14P.BIN', 'nunca debe estar'), ('ALLOW_ERASE_BOOT', 'nunca debe estar')])
    caso('calibracion_borrada', {**sano, 'CALIBRATION.DMP': b'\xff' * len(sano['CALIBRATION.DMP'])},
         [('Calibration.dmp', 'todo el contenido es 0xFF')])
    caso('falta_reserva', {k: v for k, v in sano.items() if k != 'NANDRESERVED.DMP'},
         [('NANDReserved.dmp', 'falta')])
    caso('p1_sin_marca', {**sano, 'NANDP1.DMP': relleno(0x4000, 'no es P1')}, [('NANDP1.dmp', 'P1IDSTR')])
    copia = escribir('copia_alterada', {**sano, 'CAMERAPARAM.DMP': cambiar_bit(sano['CAMERAPARAM.DMP'], 77)})
    caso('segunda_copia', sano, [('CameraParam.dmp', 'otro SHA-256')], extra=('--copia', copia))
    anterior = os.path.join(OUT, 'e1_anterior.dmp')
    viejo = bytearray(sano['CAMERAPARAM.DMP'])
    viejo[0x120:0x124] = b'\0\0\0\0'
    open(anterior, 'wb').write(viejo)
    rep = caso('e1_cambiado', sano, [], extra=('--e1-anterior', anterior))
    tramos = rep['archivos']['CameraParam.dmp'].get('tramos_cambiados')
    esperados = [i for i in range(0x120, 0x124) if sano['CAMERAPARAM.DMP'][i] != 0]
    if not tramos or tramos[0][0] != esperados[0] or tramos[-1][1] != esperados[-1]:
        fallas.append(f'e1_cambiado: tramos {tramos}, se esperaba {esperados[0]:#x}–{esperados[-1]:#x}')

    reporte = dict(casos=casos, fallas=fallas,
                   sha256_juego_sano={k: hashlib.sha256(v).hexdigest() for k, v in sorted(sano.items())})
    json.dump(reporte, open(os.path.join(OUT, 'reporte.json'), 'w'), indent=1, ensure_ascii=False)
    print(f'\n{len(casos)} casos, {len(fallas)} falla(s); artefacto: work/e2e_nand/reporte.json')
    for f in fallas:
        print('  FALLA', f)
    sys.exit(1 if fallas else 0)


if __name__ == '__main__':
    main()
