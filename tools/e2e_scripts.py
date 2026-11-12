#!/usr/bin/env python3
"""Prueba E2E de tools/check_scripts.py con los kits reales y con el script que colgó la cámara.

Cómo puede fallar el verificador (escrito antes del código; cada punto es un caso de abajo):

  F1. Deja pasar una llamada SIN asignar a una función que devuelve valor. El intérprete la rechaza
      en 0x199488: sin variable y tipo de retorno 0 (entero) o 1 (FLOAT32) →
      "Error: function returns a FLOAT32 or integer." y la CPU se detiene. Ocurrió en la cámara el
      2026-11-12 con `460 FOREIGN Run_SpecifyFunc(3050116, 2, 0, 1785216, 4472856, 0, 0, 0, 0)`
      (dump/raw9/EET.srt y EET.LOG). El verificador de entonces dio OK.
  F2. Deja pasar la falla inversa: llamada asignada a una función void. Misma rutina: con variable
      y tipo de retorno 6 → "Error: function returns no value." y la CPU se detiene.
  F3. Aplica la regla sólo a Run_SpecifyFunc o sólo a FOREIGN: la comprobación del firmware es por
      firma, igual en las tres tablas (SYSTEM 0x4871f4, FOREIGN 0x486334, DEBUGGING 0x487404).
  F4. Saca los tipos de retorno de un catálogo (docs_script_manejadores.json) que no coincide con
      las tablas de firmas del firmware.
  F5. Al endurecer la regla rechaza los scripts que sí corrieron en la cámara (P0, P6, P8, P9, EE0)
      o el resto de los kits.
  F6. Deja pasar una variable asignada dos veces en el mismo script. Por código es válido
      (0x198f78, rama "encontrada" en 0x198ff0), pero nunca corrió en la cámara: el contexto se crea
      y se destruye por script (0x1078d8 → 0x198cd0 / 0x198d9c), así que ningún script ejecutado
      reasignó una variable.
  F7. Deja pasar nombres de variable de más de una letra (válidos por 0x29bce8, nunca ejecutados).
  F8. Informa el error en otra línea o en otro archivo: quien corrige no encuentra la causa.
  F9. La corrección de EET (EET + EETV) no pasa, o el juego que va a la SD no es el del repo.
  F10. Un script que parchea la RAM (M3V, M4L, M2V) lleva un número decimal mal convertido: la guardia
      no coincide con los bytes de fábrica (en la cámara: script que termina sin hacer nada, viaje
      perdido), la escritura cambia bytes que no son los previstos, o el byte nuevo de una tabla de
      saltos no cae en la instrucción buscada (en la cámara: salto a mitad de otra instrucción). El
      verificador no puede verlo: sólo conoce direcciones permitidas, no su contenido. Se coteja con
      firmware/stock/rec0_code_0x48000.bin, no con los números del propio script.
  F11. Una escritura sin guardia previa o sin relectura posterior del mismo valor, o con anchos
      mezclados (guardia de 32 bits y escritura de 16).
  F12. La lista BatchScripts_<nombre>.txt de un script experimental nombra otra cosa, o ese juego,
      armado solo como iría a la SD, no pasa el verificador.

Corre la CLI de verdad sobre carpetas armadas en work/e2e_scripts/. Artefacto:
work/e2e_scripts/reporte.json (veredicto por caso, salida de la CLI y SHA-256 de cada script).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
OUT = os.path.join(RAIZ, 'work', 'e2e_scripts')
KIT = os.path.join(RAIZ, 'sd_kit')
RAM = os.path.join(RAIZ, 'dump', 'ram_snapshot.bin')
COLGADO = os.path.join(RAIZ, 'dump', 'raw9')
STOCK = os.path.join(RAIZ, 'firmware', 'stock', 'rec0_code_0x48000.bin')
STOCK_BASE = 0x48000
PEEK = {0x198bbc: 4, 0x736e6: 2}   # peek32, peek16
POKE = {0x2e8a84: 4, 0x13f09a: 2}  # poke32, poke16
# Tablas de saltos modo -> formato del IRP: destino = tabla + 2·byte. Instrucción que debe haber en
# el destino para cada formato (leída en el desensamblado): foto 0x128344 `mov_s r0,N` (0xd800 + N);
# vista en vivo 0x1286dc, formato 0 = `st_s r14,[r13,0x2c]` (0xa5cb, con r14 = 0 desde 0x128558).
SALTO_FOTO, SALTO_VISTA = 0x128344, 0x1286dc
# Por script: {dirección del byte que cambia: (qué es, comprobación del byte nuevo)}.
PARCHES = {
    'M3V': {0x128347: ('tabla', SALTO_FOTO, 0xd802), 0x1286df: ('tabla', SALTO_VISTA, 0xa5cb)},
    'M2V': {0x1286de: ('tabla', SALTO_VISTA, 0xa5cb)},
    # 0x122780 `or_s r0,r0,r1` (0x7825) -> `mov_s r0,r1` (0x7028): cambian sus dos bytes
    'M4L': {0x1286e0: ('tabla', SALTO_VISTA, 0xa5cb), 0x122780: ('codigo', 0x7825, 0x7028),
            0x122781: ('codigo', 0x7825, 0x7028)},
    # M4R = M4L sin tocar la tabla; M4N = M4R sin SaveCFAonTake (diagnóstico de la revisión)
    'M4R': {0x122780: ('codigo', 0x7825, 0x7028), 0x122781: ('codigo', 0x7825, 0x7028)},
    'M4N': {0x122780: ('codigo', 0x7825, 0x7028), 0x122781: ('codigo', 0x7825, 0x7028)},
}
TABLAS = {'FOREIGN': 0x486334, 'SYSTEM': 0x4871f4, 'DEBUGGING': 0x487404}
TIPOS = {0: 'int', 1: 'float', 2: 'str', 6: 'void'}
LINEA_COLGADA = '460 FOREIGN Run_SpecifyFunc(3050116, 2, 0, 1785216, 4472856, 0, 0, 0, 0)'

casos = []


def cli(carpeta):
    r = subprocess.run([sys.executable, '-I', os.path.join(AQUI, 'check_scripts.py'), carpeta],
                       capture_output=True, text=True)
    return r.returncode, r.stdout


def carpeta(nombre, archivos, lista):
    """archivos: {nombre.srt: bytes}; lista: nombres para BatchScripts.txt."""
    d = os.path.join(OUT, nombre)
    os.makedirs(d)
    for f, b in archivos.items():
        open(os.path.join(d, f), 'wb').write(b)
    open(os.path.join(d, 'BatchScripts.txt'), 'wb').write(''.join(x + '\r\n' for x in lista).encode())
    return d


def leer(*ruta):
    return open(os.path.join(KIT, *ruta), 'rb').read()


def anotar(nombre, falla, ok, detalle, salida=''):
    casos.append({'caso': nombre, 'falla': falla, 'ok': bool(ok), 'detalle': detalle, 'salida': salida})
    print(('ok   ' if ok else 'FALLA'), nombre, '-', detalle)


def debe_pasar(nombre, falla, d):
    rc, out = cli(d)
    anotar(nombre, falla, rc == 0 and out.strip().endswith('OK'), f'rc={rc}', out)


def debe_fallar(nombre, falla, d, esperados):
    """esperados: lista de (archivo, línea de archivo, fragmento del mensaje). Exige exactamente
    esos errores, ni uno más: un error de más indicaría que el caso falla por otro motivo."""
    rc, out = cli(d)
    errores = [l for l in out.splitlines() if l.startswith('ERROR')]
    faltan = [e for e in esperados
              if not any(f'{os.sep}{e[0]}:{e[1]}: ' in l and e[2] in l for l in errores)]
    ok = rc == 1 and not faltan and len(errores) == len(esperados)
    anotar(nombre, falla, ok, f'rc={rc}, {len(errores)} error(es), esperados {len(esperados)}, faltan {faltan}', out)


def mutar(b, viejo, nuevo):
    viejo, nuevo = viejo.encode(), nuevo.encode()
    if b.count(viejo) != 1:
        raise SystemExit(f'la línea a mutar no aparece una sola vez: {viejo!r}')
    return b.replace(viejo, nuevo)


def linea_de(b, texto):
    """Número de línea de archivo (base 1) de la línea que contiene `texto`."""
    hits = [n for n, l in enumerate(b.decode('ascii').splitlines(), 1) if texto in l]
    if len(hits) != 1:
        raise SystemExit(f'{texto!r} aparece {len(hits)} veces')
    return hits[0]


def firmas_del_firmware():
    """Lee las tres tablas de firmas de la RAM: [ret][nombre\\0][args…][0x07] sin relleno."""
    ram = open(RAM, 'rb').read()
    cat = json.load(open(os.path.join(RAIZ, 'docs_script_manejadores.json')))
    out = {}
    for kw, base in TABLAS.items():
        p = base
        for _ in range(sum(1 for e in cat if e['palabra_clave'] == kw)):
            ret = ram[p]
            fin = ram.index(b'\0', p + 1)
            nombre = ram[p + 1:fin].decode('ascii')
            p = ram.index(b'\x07', fin + 1) + 1
            out[(kw, nombre)] = TIPOS.get(ret, f'tipo{ret}')
    return cat, out


def revisar_parches(nombre, crudo=None):
    """F10 + F11 sobre un script de sd_kit/fase1/Batch (o sobre `crudo`). Devuelve (ok, detalle)."""
    fw = open(STOCK, 'rb').read()

    def de_fabrica(dir_ram, n):
        return int.from_bytes(fw[dir_ram - STOCK_BASE:dir_ram - STOCK_BASE + n], 'little')

    texto = (crudo or leer('fase1', 'Batch', nombre + '.srt')).decode('ascii')
    lineas = [l.split(' ', 1)[1] for l in texto.splitlines() if re.match(r'\d+ ', l)]
    llamada = re.compile(r'FOREIGN ([a-z]) = Run_SpecifyFunc\((\d+), (\d+), 0, (\d+), (\d+), 0, 0, 0, 0\)$')
    lecturas, condiciones, escrituras, problemas = {}, {}, [], []
    for n, l in enumerate(lineas):
        m = llamada.match(l)
        if m and int(m.group(2)) in PEEK:
            lecturas[m.group(1)] = (n, int(m.group(4)), PEEK[int(m.group(2))])
        elif m and int(m.group(2)) in POKE:
            escrituras.append((n, int(m.group(4)), POKE[int(m.group(2))], int(m.group(5))))
        mi = re.match(r'IF ([a-z]) == (\d+) THEN \d+$', l)
        if mi:
            condiciones[mi.group(1)] = (n, int(mi.group(2)))
    tocados = {}
    for n, direccion, ancho, valor in escrituras:
        antes = [(lecturas[v][0], condiciones[v][1]) for v in condiciones
                 if v in lecturas and lecturas[v][1:] == (direccion, ancho) and condiciones[v][0] < n]
        despues = [condiciones[v][1] for v in condiciones
                   if v in lecturas and lecturas[v][1:] == (direccion, ancho) and lecturas[v][0] > n]
        if not antes:
            problemas.append(f'{direccion:#x}: escritura sin guardia previa del mismo ancho')
            continue
        guardia = max(antes)[1]
        if guardia != de_fabrica(direccion, ancho):
            problemas.append(f'{direccion:#x}: la guardia {guardia:#x} no es el valor de fábrica '
                             f'{de_fabrica(direccion, ancho):#x}')
        if despues != [valor]:
            problemas.append(f'{direccion:#x}: se escribe {valor:#x} y la relectura espera {despues}')
        for i in range(ancho):
            viejo, nuevo = guardia >> 8 * i & 0xff, valor >> 8 * i & 0xff
            if viejo != nuevo:
                tocados[direccion + i] = nuevo
    previstos = PARCHES[nombre]
    if set(tocados) != set(previstos):
        problemas.append(f'bytes cambiados {sorted(map(hex, tocados))}, previstos {sorted(map(hex, previstos))}')
    for direccion, nuevo in tocados.items():
        if direccion not in previstos:
            continue
        clase, x, y = previstos[direccion]
        if clase == 'tabla':  # el byte nuevo, como desplazamiento, debe caer en la instrucción y
            if de_fabrica(x + 2 * nuevo, 2) != y:
                problemas.append(f'{direccion:#x}: el byte {nuevo:#x} salta a {x + 2 * nuevo:#x}, donde no está {y:#x}')
        else:                 # la palabra de 16 bits pasa de x a y
            base = direccion & ~1
            ahora = de_fabrica(base, 2)
            for d, b in tocados.items():
                if d & ~1 == base:
                    ahora = ahora & ~(0xff << 8 * (d - base)) | b << 8 * (d - base)
            if de_fabrica(base, 2) != x or ahora != y:
                problemas.append(f'{base:#x}: se esperaba {x:#x} -> {y:#x}, sale {de_fabrica(base, 2):#x} -> {ahora:#x}')
    return not problemas and bool(escrituras), \
        f'{len(escrituras)} escritura(s), bytes cambiados {sorted(map(hex, tocados))}; problemas: {problemas}'


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    p8, p0 = leer('fase1', 'Batch', 'P8.srt'), leer('fase1', 'Batch', 'P0.srt')
    memrwt = leer('fase2', 'Batch', 'MEMRWT.srt')

    # F4: el catálogo de retornos contra el firmware
    cat, fwf = firmas_del_firmware()
    distintos = [(e['palabra_clave'], e['nombre']) for e in cat
                 if fwf.get((e['palabra_clave'], e['nombre'])) != e['firma'].split()[0]]
    anotar('catalogo_vs_firmware', 'F4',
           not distintos and len(fwf) == len(cat) and fwf[('FOREIGN', 'Run_SpecifyFunc')] == 'int'
           and fwf[('FOREIGN', 'SaveCFAonTake')] == 'void' and fwf[('SYSTEM', 'MemRead')] == 'int',
           f'{len(fwf)} firmas leídas de la RAM, {len(cat)} en el catálogo, distintas: {distintos}')

    # F5: los kits tal como están en el repo
    for fase in ('fase1', 'fase2', 'fase3'):
        debe_pasar(f'kit_{fase}', 'F5', os.path.join(KIT, fase, 'Batch'))

    # F9: el juego exacto que va a la SD (P8 + EET + EETV)
    lista = open(os.path.join(KIT, 'fase3', 'Batch', 'BatchScripts_EET.txt')).read().split()
    sd = carpeta('sd_eet', {n + '.srt': leer('fase3', 'Batch', n + '.srt') for n in lista}, lista)
    debe_pasar('sd_eet', 'F9', sd)
    anotar('sd_eet_lista', 'F9', lista == ['P8', 'EET', 'EETV'], f'BatchScripts_EET.txt = {lista}')
    eet, eetv = leer('fase3', 'Batch', 'EET.srt').decode(), leer('fase3', 'Batch', 'EETV.srt').decode()
    cuerpo = eet + eetv
    guardias = re.findall(r'= Run_SpecifyFunc\(1674172, 1, 0, (\d+), 0, 0, 0, 0, 0\)\r\n\d+ IF', eet)
    pokes = re.findall(r'= Run_SpecifyFunc\(3050116, 2, 0, (\d+), 4472856, 0, 0, 0, 0\)', eet)
    relee = re.findall(r'= Run_SpecifyFunc\(1674172, 1, 0, (\d+), 0, 0, 0, 0, 0\)\r\n\d+ LOG_PRINT VERIFY', eetv)
    primera_escritura = eet.index('Run_SpecifyFunc(3050116')
    ultima_guardia = max(m.start() for m in re.finditer(r'\d+ IF ', eet))
    anotar('sd_eet_estructura', 'F9',
           len(guardias) == 11 and guardias == pokes == relee and ultima_guardia < primera_escritura
           and 'FOREIGN Run_SpecifyFunc' not in cuerpo,
           f'{len(guardias)} guardias, {len(pokes)} escrituras, {len(relee)} relecturas, mismas direcciones en el '
           f'mismo orden: {guardias == pokes == relee}; todas las guardias antes de la primera escritura: '
           f'{ultima_guardia < primera_escritura}')

    # F10 + F11 + F12: scripts experimentales de modo RAW (cada uno va SOLO a la SD)
    for nombre in sorted(PARCHES):
        ok, detalle = revisar_parches(nombre)
        anotar(f'parches_{nombre}', 'F10 F11', ok, detalle)
        lista = open(os.path.join(KIT, 'fase1', 'Batch', f'BatchScripts_{nombre}.txt')).read().split()
        anotar(f'sd_{nombre}_lista', 'F12', lista == [nombre], f'BatchScripts_{nombre}.txt = {lista}')
        debe_pasar(f'sd_{nombre}', 'F12',
                   carpeta(f'sd_{nombre}', {nombre + '.srt': leer('fase1', 'Batch', nombre + '.srt')}, lista))

    # F10: el control detecta un decimal mal convertido (guardia de M4L con un dígito cambiado)
    ok, detalle = revisar_parches('M4L', mutar(leer('fase1', 'Batch', 'M4L.srt'), 'IF b == 30757', 'IF b == 30767'))
    anotar('parches_M4L_guardia_mutada', 'F10', not ok and 'no es el valor de fábrica' in detalle, detalle)

    # F1 + F8: el script que colgó la cámara, tal cual quedó respaldado
    colgado = open(os.path.join(COLGADO, 'EET.srt'), 'rb').read()
    log = open(os.path.join(COLGADO, 'EET.LOG'), 'rb').read().decode('ascii')
    reportada = re.search(r'^(\d+ FOREIGN [^\r\n]*)', log, re.M).group(1)
    sin_asignar = [n for n, l in enumerate(colgado.decode('ascii').splitlines(), 1)
                   if re.match(r'\d+ FOREIGN Run_SpecifyFunc\(', l)]
    d = carpeta('colgado_raw9', {'P8.srt': p8, 'EET.srt': colgado}, ['P8', 'EET'])
    debe_fallar('colgado_raw9', 'F1 F8', d, [('EET.srt', n, 'devuelve un valor') for n in sin_asignar])
    anotar('colgado_raw9_linea_de_la_camara', 'F1 F8',
           reportada == LINEA_COLGADA and len(sin_asignar) == 11
           and linea_de(colgado, LINEA_COLGADA) == sin_asignar[0]
           and 'function returns a FLOAT32 or integer' in log,
           f'la cámara se detuvo en {reportada!r}; el verificador marca {len(sin_asignar)} líneas, la primera es esa')

    # F1: la misma línea, sola, dentro de un script que sí corrió (P8)
    malo = mutar(p8, '40 FOREIGN SaveCFAonTake(1)', LINEA_COLGADA.replace('460 ', '40 '))
    d = carpeta('linea_exacta_en_p8', {'P8.srt': malo}, ['P8'])
    debe_fallar('linea_exacta_en_p8', 'F1', d, [('P8.srt', 4, 'devuelve un valor')])

    # F1: lectura (peek32) sin asignar
    malo = mutar(p0, 'FOREIGN a = Run_SpecifyFunc(1674172', 'FOREIGN Run_SpecifyFunc(1674172')
    malo = mutar(malo, '30 LOG_PRINT VERIFY a\r\n', '')
    d = carpeta('peek_sin_asignar', {'P0.srt': malo}, ['P0'])
    debe_fallar('peek_sin_asignar', 'F1', d, [('P0.srt', 2, 'devuelve un valor')])

    # F2: función void asignada
    malo = mutar(p8, '40 FOREIGN SaveCFAonTake(1)', '40 FOREIGN v = SaveCFAonTake(1)')
    d = carpeta('void_asignada', {'P8.srt': malo}, ['P8'])
    debe_fallar('void_asignada', 'F2', d, [('P8.srt', 4, 'no devuelve valor')])

    # F3: tabla SYSTEM, en los dos sentidos
    malo = mutar(memrwt, '20 SYSTEM a = MemRead(2975248)\r\n30 LOG_PRINT VERIFY a\r\n', '20 SYSTEM MemRead(2975248)\r\n')
    d = carpeta('system_sin_asignar', {'MEMRWT.srt': malo}, ['MEMRWT'])
    debe_fallar('system_sin_asignar', 'F3', d, [('MEMRWT.srt', 2, 'devuelve un valor')])
    malo = mutar(memrwt, '20 SYSTEM a = MemRead(2975248)', '20 SYSTEM a = delay_us(1000)')
    d = carpeta('system_void_asignada', {'MEMRWT.srt': malo}, ['MEMRWT'])
    debe_fallar('system_void_asignada', 'F3', d, [('MEMRWT.srt', 2, 'no devuelve valor')])

    # F6: variable asignada dos veces en el mismo script
    malo = mutar(p8, '50 FOREIGN b = Run_SpecifyFunc', '50 FOREIGN a = Run_SpecifyFunc')
    malo = mutar(malo, '60 LOG_PRINT VERIFY b', '60 LOG_PRINT VERIFY a')
    d = carpeta('variable_reasignada', {'P8.srt': malo}, ['P8'])
    debe_fallar('variable_reasignada', 'F6', d, [('P8.srt', 5, 'ya tiene valor')])

    # F7: nombre de variable de dos letras (la forma del EET anterior al cuelgue)
    malo = mutar(p0, 'FOREIGN a = Run_SpecifyFunc', 'FOREIGN ga = Run_SpecifyFunc')
    malo = mutar(malo, 'LOG_PRINT VERIFY a', 'LOG_PRINT VERIFY ga')
    d = carpeta('variable_dos_letras', {'P0.srt': malo}, ['P0'])
    debe_fallar('variable_dos_letras', 'F7', d, [('P0.srt', 2, 'una sola letra')])

    hashes = {}
    for raiz, _, fs in os.walk(KIT):
        for f in sorted(fs):
            if f.lower().endswith('.srt') or f.startswith('BatchScripts'):
                ruta = os.path.join(raiz, f)
                hashes[os.path.relpath(ruta, RAIZ)] = hashlib.sha256(open(ruta, 'rb').read()).hexdigest()
    malos = [c['caso'] for c in casos if not c['ok']]
    json.dump({'casos': casos, 'fallidos': malos, 'sha256': hashes},
              open(os.path.join(OUT, 'reporte.json'), 'w'), indent=1, ensure_ascii=False)
    print(f'{len(casos) - len(malos)}/{len(casos)} casos; reporte en {os.path.join(OUT, "reporte.json")}')
    sys.exit(1 if malos else 0)


if __name__ == '__main__':
    main()
