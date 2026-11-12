#!/usr/bin/env python3
"""Verifica los volcados de la NAND Tool de la M531 cuando vuelven de la cámara. Sólo lee.

uso: python3 -I tools/verificar_volcados.py CARPETA [--copia OTRA_CARPETA] [--e1-anterior ARCHIVO]
                                            [--json SALIDA.json] [--escribir-sumas]

CARPETA = copia en el Mac de lo que la NAND Tool dejó en la raíz de la SD. Comprueba, con lo que se
sabe por el código y la RAM (NOTAS.md, "NAND Tool: manejadores de Dump"):
  * que estén los 11 archivos de las opciones A1, B3, C1, D1, E1, F1, G1, I4, I5 y que no haya
    ninguno de los que nunca van a la SD;
  * tamaños contra la tabla de particiones (bloques de 16 KiB) y contenido no vacío;
  * SHA-256 de cada archivo (y, con --copia, que la segunda copia sea idéntica);
  * MainCode.dmp: cabecera RHIR igual a la leída en la RAM, modelo, registros dentro del archivo,
    sum32 de los tipos 1 (lo que exigen el boot y el actualizador) y 0, y bytes de código, gráficos
    y rec3 iguales a los reconstruidos desde la RAM;
  * BootCode.dmp: cabecera de 16 B y sum32 del cuerpo = 0xbbb66ba4, bytes iguales al boot residente
    en RAM, en cualquiera de las disposiciones posibles (con cabecera, sin ella o desplazado);
  * NANDPartition.txt contra la tabla de la RAM; NANDP1.dmp con P1IDSTR;
  * con --e1-anterior, qué bytes de CameraParam.dmp cambiaron.
Niveles: ERROR (no flashear con esto), AVISO (hay que mirarlo), OK. Sale con 1 si hay algún ERROR.
Las formas de fallar están en tools/NAND_FALLAS.md (escritas antes que este código).
"""
import argparse
import hashlib
import json
import os
import re
import struct
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import km531fw as fw  # noqa: E402

STOCK = os.path.join(os.path.dirname(AQUI), 'firmware', 'stock')
BLOQUE = 32 * 512  # 32 sectores por bloque (byte +3 de la geometría, RAM 0x4da320)
# Tabla de particiones leída en la RAM (0x4da228 +0xc4 inicios, +0xd2 tamaños, en bloques).
PARTICIONES = {0: (695, 15), 1: (0, 10), 2: (10, 10), 3: (20, 1), 4: (21, 1), 5: (22, 173), 6: (195, 500)}
# Archivo -> partición, según el manejador 0x2c0510 (índice de partición -> nombre) y el despachador
# 0x24cb44. None = no es una partición entera (0x2c0620, 0x2c0738, 0x2c09e4, 0x2c1908).
ARCHIVOS = {
    'Calibration.dmp': ('A1', 1), 'Calibration_2.dmp': ('A1', 2), 'MainCode.dmp': ('B3', 6),
    'BootCode.dmp': ('C1', 0), 'NANDPartition.txt': ('D1', None), 'CameraParam.dmp': ('E1', 3),
    'CameraParam_2.dmp': ('E1', 4), 'NANDReserved.dmp': ('F1', 5), 'NANDP1.dmp': ('G1', None),
    'BFNSetting.txt': ('I4', None), 'BootNANDBase.dmp': ('I5', None),
}
PROHIBIDOS = [r'ALLOW_ERASE_BOOT$', r'ALLOW_ROLLBACK_OLD_PARTITION$', r'TBIB_.*\.BIN$', r'TBM_.*\.BIN$',
              r'KM531\.FW$', r'NANDUtility\.txt$', r'BootNANDBase\.bin$', r'IMAGE\.ISO$']
BOOT_CABECERA = struct.pack('<4I', 0x800000, 0x2cff0, 0xbbb66ba4, 0x800030)
BOOT_TAM, BOOT_SUMA = 0x2cff0, 0xbbb66ba4
BOOT_SHA = 'feedac93f52f253c538773423783507ae402ab7958c0716f8b14f4048242129e'  # cuerpo, RAM 0x800000
# NANDPartition.txt: "%-40s0x%04X\r\n" con estas etiquetas (0x2c0738); valores de la tabla en RAM.
TABLA_TXT = [('uwReg_Configuration', 0x0), ('uwReg_AutoRefresh', 0x0), ('uwReg_Control', 0x0),
             ('uwSize_BootCode', 0xf), ('uwSize_Calibration', 0xa), ('uwSize_CameraPara', 0x1),
             ('uwSize_Reserved', 0xad), ('uwSize_HexMain', 0x1f4), ('uwProductID', 0x1224),
             ('uwPartition_Ver', 0x10)]
SECCIONES_RAM = {0: 'rec0_code_0x48000.bin', 2: 'rec2_gfx_0x528000.bin', 3: 'rec3_0x5ae000.bin'}


class Informe:
    def __init__(self):
        self.lineas, self.datos = [], {}

    def _a(self, nivel, archivo, texto):
        self.lineas.append((nivel, archivo, texto))

    def ok(self, a, t):
        self._a('OK', a, t)

    def aviso(self, a, t):
        self._a('AVISO', a, t)

    def error(self, a, t):
        self._a('ERROR', a, t)

    def hay_error(self):
        return any(n == 'ERROR' for n, _, _ in self.lineas)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def listar(carpeta):
    """nombre canónico -> ruta real, sin distinguir mayúsculas (FAT)."""
    reales = {f.lower(): os.path.join(carpeta, f) for f in os.listdir(carpeta)
              if os.path.isfile(os.path.join(carpeta, f)) and not f.startswith('.')}
    return {n: reales.get(n.lower()) for n in ARCHIVOS}, reales


def revisar_presencia(carpeta, inf):
    rutas, reales = listar(carpeta)
    for n, (opcion, _) in ARCHIVOS.items():
        if rutas[n] is None:
            inf.error(n, f'falta (opción {opcion})')
    for real in sorted(reales):
        for patron in PROHIBIDOS:
            if re.match(patron, real, re.I):
                inf.error(os.path.basename(reales[real]), 'archivo que nunca debe estar en la SD de la cámara')
    return rutas


def revisar_tamanos(rutas, inf):
    datos = {}
    for n, ruta in rutas.items():
        if ruta is None:
            continue
        b = open(ruta, 'rb').read()
        datos[n] = b
        inf.datos[n] = {'bytes': len(b), 'sha256': sha(b)}
        if not b:
            inf.error(n, 'archivo vacío')
            continue
        if n.endswith('.dmp') and len(set(b)) == 1:
            inf.error(n, f'todo el contenido es 0x{b[0]:02X}: lectura fallida o partición borrada')
        part = ARCHIVOS[n][1]
        if part is not None:
            tope = PARTICIONES[part][1] * BLOQUE
            if len(b) > tope:
                inf.error(n, f'{len(b):#x} B, mayor que la partición {part} ({tope:#x} B)')
            elif len(b) % 512:
                inf.error(n, f'{len(b):#x} B, no es múltiplo de 512: escritura cortada')
            elif len(b) == tope:
                inf.ok(n, f'{len(b):#x} B = partición {part} completa')
            else:
                inf.aviso(n, f'{len(b):#x} B, menos que la partición {part} ({tope:#x} B): '
                             'el largo real del volcado no estaba medido; revisar que no esté truncado')
    return datos


def revisar_main(b, inf):
    n = 'MainCode.dmp'
    if b[:4] != b'RHIR':
        inf.error(n, 'no empieza por RHIR')
        return
    cab = open(os.path.join(STOCK, 'header_first_0xa0.bin'), 'rb').read()
    if b[:len(cab)] == cab:
        inf.ok(n, 'cabecera RHIR idéntica a la leída en la RAM (0xA0 B)')
    else:
        dif = [i for i in range(min(len(cab), len(b))) if b[i] != cab[i]]
        inf.error(n, f'la cabecera difiere de la leída en la RAM en {len(dif)} bytes (primero en {dif[0]:#x})')
    if struct.unpack_from('<I', b, 8)[0] != fw.MODELO:
        inf.error(n, f'palabra de modelo {struct.unpack_from("<I", b, 8)[0]:#x}, se esperaba {fw.MODELO:#x}')
    regs = fw.registros(b)
    fin_datos = 0
    for r in regs:
        if r['tipo'] == 2:
            inf.ok(n, f"registro {r['i']} tipo 2 (sector {r['sector']}, fuera del archivo): no se toca")
            continue
        if r['tipo'] not in (0, 1):
            inf.aviso(n, f"registro {r['i']} de tipo desconocido {r['tipo']}")
            continue
        fin = r['off'] + r['size']
        fin_datos = max(fin_datos, fin)
        if fin > len(b):
            inf.error(n, f"registro {r['i']} (tipo {r['tipo']}) termina en {fin:#x}, fuera del archivo ({len(b):#x} B)")
            continue
        suma = fw.sum32(b[r['off']:fin])
        if suma != r['sum']:
            texto = f"registro {r['i']} tipo {r['tipo']}: sum32 {suma:08x}, la cabecera dice {r['sum']:08x}"
            # el boot (0x800ee0) y el actualizador (0x2bd46c) sólo exigen los de tipo 1
            inf.error(n, texto + (' (el boot lo rechazaría)' if r['tipo'] == 1 else ' (el boot no lo revisa)'))
        else:
            inf.ok(n, f"registro {r['i']} tipo {r['tipo']}: sum32 {suma:08x} correcta")
        if r['i'] in SECCIONES_RAM:
            ref = open(os.path.join(STOCK, SECCIONES_RAM[r['i']]), 'rb').read()
            if b[r['off']:fin] == ref:
                inf.ok(n, f"registro {r['i']}: bytes idénticos a {SECCIONES_RAM[r['i']]}")
            else:
                inf.error(n, f"registro {r['i']}: difiere de {SECCIONES_RAM[r['i']]} (reconstruido desde la RAM)")
    cola = b[fin_datos:]
    if cola and set(cola) - {0xff}:
        inf.aviso(n, f'{len(cola):#x} B tras el último registro ({fin_datos:#x}) con datos distintos de 0xFF: '
                     'guardar el archivo tal cual y revisar qué son')
    if b[0x1f0:0x1f4] == b'KHIR':
        s = fw.sum32(b[:0x1f0])
        a, c = struct.unpack_from('<II', b, 0x1f4)
        if (a, c) == (s, s ^ 0xffffffff):
            inf.ok(n, 'cola KHIR con sum32 de la cabecera y su complemento (formato de la C713)')
        else:
            inf.aviso(n, f'cola KHIR presente con valores {a:08x}/{c:08x}; sum32 de la cabecera = {s:08x}')
    else:
        inf.aviso(n, f'sin "KHIR" en 0x1F0 (hay {b[0x1f0:0x1f4].hex()}); ni el boot ni el actualizador lo leen')
    problemas = fw.validar_como_firmware(b[:fin_datos] if fin_datos <= len(b) else b, PARTICIONES[6][1] * BLOQUE)
    if problemas:
        inf.error(n, 'el validador del firmware lo rechaza: ' + '; '.join(problemas))
    elif fin_datos > len(b):
        inf.error(n, f'incompleto: los registros llegan a {fin_datos:#x} y el archivo tiene {len(b):#x} B; '
                     'no sirve para reconstruir KM531.FW')
    else:
        inf.ok(n, f'el validador del firmware (0x2bd46c) acepta los primeros {fin_datos:#x} B: '
                  'con ellos se reconstruye KM531.FW')
    inf.datos[n]['fin_datos'] = fin_datos


def revisar_boot(b, inf):
    n = 'BootCode.dmp'
    ruta_ram = os.path.join(STOCK, 'boot_hdr16_0x800000.bin')
    cuerpo_ram = open(ruta_ram, 'rb').read()[16:] if os.path.exists(ruta_ram) else None
    candidatos = []
    pos = b.find(BOOT_CABECERA)
    while pos >= 0:
        candidatos.append(('con cabecera de 16 B en %#x' % pos, pos + 16))
        pos = b.find(BOOT_CABECERA, pos + 1)
    candidatos.append(('sin cabecera, desde 0', 0))
    if cuerpo_ram:
        p = b.find(cuerpo_ram[:64])
        if p >= 0 and all(p != c[1] for c in candidatos):
            candidatos.append(('cuerpo hallado en %#x sin cabecera delante' % p, p))
    for nombre, ini in candidatos:
        cuerpo = b[ini:ini + BOOT_TAM]
        if len(cuerpo) == BOOT_TAM and fw.sum32(cuerpo) == BOOT_SUMA:
            inf.ok(n, f'disposición: {nombre}; sum32 del cuerpo = {BOOT_SUMA:08x}')
            if sha(cuerpo) == BOOT_SHA:
                inf.ok(n, 'cuerpo idéntico byte a byte al boot residente en RAM (0x800000)')
            else:
                inf.error(n, 'la suma coincide y los bytes difieren del boot residente en RAM')
            if cuerpo[0x568:0x570] != fw.MARCADOR_5EN1:
                inf.aviso(n, 'sin el marcador INFO+0x55aaaa55 en 0x568 del cuerpo')
            inf.datos[n]['cuerpo_en'] = ini
            return
    if not b.count(BOOT_CABECERA):
        inf.error(n, 'no aparece la cabecera (0x800000, 0x2cff0, 0xbbb66ba4, 0x800030) y el contenido desde 0 '
                     'no suma 0xbbb66ba4')
    else:
        inf.error(n, 'cabecera presente y la sum32 del cuerpo no da 0xbbb66ba4: boot distinto o dañado')


def revisar_tabla(b, datos, inf):
    n = 'NANDPartition.txt'
    try:
        texto = b.decode('ascii')
    except UnicodeDecodeError:
        inf.error(n, 'no es texto ASCII')
        return
    leido = dict(re.findall(r'^(\w+)\s+0x([0-9A-Fa-f]{4})\s*$', texto, re.M))
    for etiqueta, esperado in TABLA_TXT:
        if etiqueta not in leido:
            inf.error(n, f'falta la línea {etiqueta}')
        elif int(leido[etiqueta], 16) != esperado:
            nivel = inf.error if etiqueta.startswith('uwSize') else inf.aviso
            nivel(n, f'{etiqueta} = 0x{leido[etiqueta]}, en la tabla de la RAM es {esperado:#06x}')
    if all(e in leido and int(leido[e], 16) == v for e, v in TABLA_TXT):
        inf.ok(n, 'las 10 líneas coinciden con la tabla de la RAM; partición 6 = 0x1F4 bloques = 0x7d0000 B '
                  '(valor para km531fw.py patch --particion)')
    for etiqueta, archivo in (('uwSize_BootCode', 'BootCode.dmp'), ('uwSize_HexMain', 'MainCode.dmp'),
                              ('uwSize_Reserved', 'NANDReserved.dmp'), ('uwSize_Calibration', 'Calibration.dmp'),
                              ('uwSize_CameraPara', 'CameraParam.dmp')):
        if etiqueta in leido and archivo in datos and len(datos[archivo]) > int(leido[etiqueta], 16) * BLOQUE:
            inf.error(archivo, f'más grande que lo que declara {etiqueta} en NANDPartition.txt')


def revisar_resto(datos, inf):
    p1 = datos.get('NANDP1.dmp')
    if p1 is not None:
        pos = p1.find(b'P1IDSTR')
        if pos < 0:
            inf.error('NANDP1.dmp', 'no contiene P1IDSTR')
        else:
            inf.ok('NANDP1.dmp', f'P1IDSTR en {pos:#x}')
            if len(p1) >= pos + 0xe0:
                ini = struct.unpack_from('<7H', p1, pos + 0xc4)
                tam = struct.unpack_from('<7H', p1, pos + 0xd2)
                esperado = [PARTICIONES[i] for i in range(7)]
                if list(zip(ini, tam)) == esperado and p1[pos + 0xb4:pos + 0xc4] == BOOT_CABECERA:
                    inf.ok('NANDP1.dmp', 'inicios, tamaños y cabecera del boot iguales a la tabla de la RAM')
                else:
                    inf.aviso('NANDP1.dmp', 'los campos en +0xb4…+0xde no coinciden con la estructura de la RAM '
                                            '(no se sabe si en la NAND tiene la misma disposición): revisar a mano')
    for a, c in (('Calibration.dmp', 'Calibration_2.dmp'), ('CameraParam.dmp', 'CameraParam_2.dmp')):
        if a in datos and c in datos:
            if datos[a] == datos[c]:
                inf.ok(a, f'idéntico a {c}')
            else:
                dif = sum(x != y for x, y in zip(datos[a], datos[c])) + abs(len(datos[a]) - len(datos[c]))
                inf.aviso(a, f'difiere de {c} en {dif} bytes (no se sabe si las dos copias deben ser iguales)')
    b = datos.get('BFNSetting.txt')
    if b is not None and not re.search(rb'0x[0-9A-Fa-f]+', b):
        inf.aviso('BFNSetting.txt', 'no se reconoce ningún valor hexadecimal')


def comparar_copia(carpeta, otra, inf):
    rutas, _ = listar(otra)
    for n in ARCHIVOS:
        if n not in inf.datos:
            continue
        if rutas[n] is None:
            inf.error(n, f'falta en la segunda copia ({otra})')
        elif sha(open(rutas[n], 'rb').read()) != inf.datos[n]['sha256']:
            inf.error(n, 'la segunda copia tiene otro SHA-256')
        else:
            inf.ok(n, 'segunda copia idéntica')


def comparar_e1(actual, ruta_anterior, inf):
    antes = open(ruta_anterior, 'rb').read()
    if antes == actual:
        inf.ok('CameraParam.dmp', f'idéntico al volcado anterior ({ruta_anterior})')
        return
    dif = [i for i in range(min(len(antes), len(actual))) if antes[i] != actual[i]]
    tramos, ini = [], None
    for i in dif:
        if ini is None:
            ini = fin = i
        elif i == fin + 1:
            fin = i
        else:
            tramos.append((ini, fin))
            ini = fin = i
    if ini is not None:
        tramos.append((ini, fin))
    inf.aviso('CameraParam.dmp', f'{len(dif)} bytes distintos del volcado anterior (largos {len(antes)}/{len(actual)}): '
              + ', '.join(f'{a:#x}–{b:#x}' for a, b in tramos[:24]) + (' …' if len(tramos) > 24 else ''))
    inf.datos['CameraParam.dmp']['tramos_cambiados'] = tramos


def verificar(carpeta, copia=None, e1_anterior=None):
    inf = Informe()
    rutas = revisar_presencia(carpeta, inf)
    datos = revisar_tamanos(rutas, inf)
    if 'MainCode.dmp' in datos and datos['MainCode.dmp']:
        revisar_main(datos['MainCode.dmp'], inf)
    if 'BootCode.dmp' in datos and datos['BootCode.dmp']:
        revisar_boot(datos['BootCode.dmp'], inf)
    if 'NANDPartition.txt' in datos and datos['NANDPartition.txt']:
        revisar_tabla(datos['NANDPartition.txt'], datos, inf)
    revisar_resto(datos, inf)
    if copia:
        comparar_copia(carpeta, copia, inf)
    if e1_anterior and 'CameraParam.dmp' in datos:
        comparar_e1(datos['CameraParam.dmp'], e1_anterior, inf)
    return inf


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('carpeta')
    ap.add_argument('--copia', help='segunda copia de los volcados: deben tener los mismos SHA-256')
    ap.add_argument('--e1-anterior', help='CameraParam.dmp de una sesión anterior, para ver qué cambió')
    ap.add_argument('--json', help='escribe el informe completo en este archivo')
    ap.add_argument('--escribir-sumas', action='store_true', help='escribe SHA256SUMS en la carpeta')
    a = ap.parse_args()
    inf = verificar(a.carpeta, a.copia, a.e1_anterior)
    for nivel, archivo, texto in inf.lineas:
        print(f'{nivel:5} {archivo}: {texto}')
    errores = sum(n == 'ERROR' for n, _, _ in inf.lineas)
    avisos = sum(n == 'AVISO' for n, _, _ in inf.lineas)
    print(f'\n{errores} error(es), {avisos} aviso(s)')
    if a.escribir_sumas:
        rutas, _ = listar(a.carpeta)
        with open(os.path.join(a.carpeta, 'SHA256SUMS'), 'w') as f:
            for n in ARCHIVOS:
                if n in inf.datos:
                    f.write(f"{inf.datos[n]['sha256']}  {os.path.basename(rutas[n])}\n")
    if a.json:
        json.dump({'carpeta': os.path.abspath(a.carpeta), 'archivos': inf.datos,
                   'lineas': [dict(nivel=n, archivo=f, texto=t) for n, f, t in inf.lineas],
                   'errores': errores, 'avisos': avisos}, open(a.json, 'w'), indent=1, ensure_ascii=False)
    sys.exit(1 if errores else 0)


if __name__ == '__main__':
    main()
