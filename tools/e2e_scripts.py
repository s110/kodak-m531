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
  F13. ORI (sensor de orientación) apunta a otra dirección que la que consulta el firmware, o esa
      dirección ya no es la compuerta: `0xf02a0` devuelve 0 (cámara horizontal) sin leer el sensor
      cuando el byte `[0x3da998]` o el byte `[0x3da998 + 1]` vale 0. La dirección se coteja con el
      literal de `0xf032c` y la compuerta con las instrucciones de `0xf02b6–0xf02c5` del firmware
      de fábrica, no con los números del script.
  F14. ORI escribe sin haber leído, escribe con un valor inicial que no previó (en la cámara: pisa
      un estado desconocido), cambia el byte bajo (bandera "sensor alimentado", que comparte la
      palabra de 16 bits), deja el byte alto distinto de 0, o no relee y registra. Se ejecuta el
      script entero en un intérprete mínimo sobre una memoria simulada, con los dos estados que el
      firmware puede dejar (0x0101, 0x0100) y con seis que no debería tocar.
  F15. El juego de prueba de ORI (P8 + EET + EETV + ORI, y M4L + ORI) no pasa el verificador, su
      lista nombra otra cosa, o las dos copias de ORI.srt (fase1 y fase3) difieren.
  F16. M4Q (revisión tras el disparo en modo 4) cambia instrucciones que no son las que arman la
      llamada al conversor RAW → imagen de revisión. Se coteja con el firmware de fábrica, no con
      los números del script: `0x148b78` pone r15 = 0 y r16 = r15 al entrar; en `0x148ed6` guarda
      el puntero del recorte en `[sp+0x10]` y en `0x148ed8` pasa r16 (0 = RAW de 8 bits) como
      formato; `0x148ee8` es `bl 0x25239c` y es la ÚNICA referencia a `0x25239c` en todo el código
      (barrido de `bl`, `b` y punteros, posición par por posición par); `0x25239c` lee esos argumentos en `[sp+140]`, `[sp+144]`
      y `[sp+148]` tras bajar la pila 0x4c + 0x38. Los valores nuevos deben ser exactamente
      `st_s r15,[sp,0x10]` (recorte nulo) y `mov_s r0,4` (12 bits empaquetados).
  F17. M4Q escribe con el modo de captura distinto de 4, con una de las dos palabras distinta de
      la de fábrica (en la cámara: firmware distinto del volcado, o script ya aplicado), deja
      aplicada sólo la segunda palabra (formato 4 con el recorte de fábrica: en ráfaga el ancho
      4300 px no da bytes múltiplos de 4 y `0xf65f4` sale por un camino de error que nunca corrió),
      no relee, o cambia otros bytes. Se ejecuta entero sobre el firmware de fábrica como memoria,
      en cinco estados iniciales, y un control con el valor escrito cambiado.
  F18. El juego M4L + M4Q, armado como va a la SD, no pasa el verificador, la lista nombra otra
      cosa o está en otro orden (M4Q antes de M4L encuentra el modo 0 y termina sin escribir).
  F19. M4W (color de la revisión en modo 4 lineal) cambia una palabra que no es la de las banderas
      de la tabla de módulos de la revisión, o esa palabra la lee alguien más. Se coteja con el
      firmware de fábrica: el literal de `0x1b03bc` vale `0x00380300`; lo carga sólo `0x1b02fa`
      (`ld_s r1,[pcl,0xc4]`, dentro de `0x1b02e0`); `0x1b02e0` tiene una sola llamada (`0x1229e8`,
      dentro de `0x122944`) y `0x122944` otra sola (`0x148c52`, dentro de `0x148b78`); la bandera
      que decide la tabla de linealización es el bit 19 (`btst_s r0,0x13` en `0x147824`, con
      `0x18fcf8` + `0x18fcc0` si está y `0x18fcdc` si no). El valor nuevo sólo apaga ese bit.
  F20. M4W escribe sin M4L aplicado (RAW con curva: la revisión necesita la linealización), sin
      M4Q aplicado (la revisión lee 8 bits), con el literal distinto del de fábrica, no relee, o
      cambia otros bytes. Se ejecuta entero sobre el firmware de fábrica con M4L y M4Q encima, en
      cinco estados, y un control con el valor escrito cambiado.
  F21. El juego M4L + M4Q + M4W, armado como va a la SD, no pasa el verificador o está en otro orden.

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
# M4Q: llamada de la revisión al conversor RAW -> YUV (0x148b78 -> 0x25239c), leída en el
# desensamblado. Palabras de 16 bits (LE) del firmware de fábrica que sostienen el parche.
M4Q_MODO = 0x3d97a8
M4Q_RECORTE, M4Q_FORMATO, M4Q_LLAMADA, M4Q_CONVERSOR = 0x148ed6, 0x148ed8, 0x148ee8, 0x25239c
M4Q_FABRICA = {
    0x148b8e: 0xdf00,                    # mov_s r15,0
    0x148b94: 0x771a,                    # mov_s r16,r15
    # los tres resultados que pasan por r15 salen a 0x148f3c si no son 0: en 0x148ed6 r15 vale 0
    0x148c56: 0x270a, 0x148c58: 0x9000,  # mov.f r15,r0
    0x148ce4: 0x270a, 0x148ce6: 0x9000,
    0x148df2: 0x270a, 0x148df4: 0x9000,
    M4Q_RECORTE: 0xc044,                 # st_s r0,[sp,0x10]  (puntero del recorte)
    M4Q_FORMATO: 0x700a,                 # mov_s r0,r16       (formato del RAW = 0)
    0x148eda: 0x8621,                    # ld_s r1,[r14,0x4]  (RAW = ctx+4)
    0x148edc: 0x135a, 0x148ede: 0xb602,  # ld.as r2,[fp,-166] (ancho)
    0x148ee0: 0x260a, 0x148ee2: 0x0640,  # mov r6,r25
    0x148ee4: 0x274a, 0x148ee6: 0x0040,  # mov r7,1
    0x2523a2: 0xc1b3,                    # sub_s sp,sp,0x4c (tras guardar 0x38 B)
    0x2523a4: 0x705a,                    # mov_s r18,r0     (formato)
    0x2523c0: 0x148c, 0x2523c2: 0x3080,  # ldb r0,[sp,140]  (escala)
    0x2523d2: 0x1490, 0x2523d4: 0x3101,  # ldh r1,[sp,144]  (zoom)
    0x2523e2: 0x1494, 0x2523e4: 0x3000,  # ld r0,[sp,148]   (recorte)
}
# El barrido decodifica cada posición par: 0x2b1b7e es la segunda mitad de `b.d 0x2b219a`
# (0x061f 0x0020 en 0x2b1b7c, instrucción de 4 bytes) y leída como comienzo de instrucción da un
# salto a 0x25239c. No es una referencia.
M4Q_MITAD_DE_INSTRUCCION = {0x2b1b7e: (0x2b1b7c, 0x061f, 0x0020)}
M4Q_NUEVO = {M4Q_RECORTE: 0xc744,        # st_s r15,[sp,0x10]
             M4Q_FORMATO: 0xd804}        # mov_s r0,0x4
PARCHES_ENCADENADOS = {'M4Q': {0x148ed7: ('codigo', 0xc044, 0xc744), 0x148ed8: ('codigo', 0x700a, 0xd804),
                               0x148ed9: ('codigo', 0x700a, 0xd804)}}
# M4W: banderas de la tabla de módulos de la revisión (0x1b02e0, literal de 0x1b03bc). Bit 19 =
# cargar y habilitar la tabla de linealización (inversa de la curva del RAW de 8 bits).
M4W_LITERAL, M4W_CARGA, M4W_BIT = 0x1b03bc, 0x1b02fa, 19
M4W_M4L, M4W_M4L_VALOR = 0x122780, 0x7028          # instrucción que M4L deja (RAW lineal)
M4W_FABRICA = {
    M4W_LITERAL: 0x0300, M4W_LITERAL + 2: 0x0038,   # 0x00380300
    M4W_CARGA: 0xd131,                               # ld_s r1,[pcl,0xc4]
    0x147824: 0xb8f3,                                # btst_s r0,0x13
    0x147826: 0xf209,                                # beq_s 0x147836 (sin bandera: 0x18fcdc)
}
M4W_LLAMADAS = {0x1b02e0: 0x1229e8, 0x122944: 0x148c52,          # constructor de la tabla: una llamada cada uno
                0x18fcf8: 0x147828, 0x18fcc0: 0x147830, 0x18fcdc: 0x147836}
PARCHES_ENCADENADOS['M4W'] = {0x1b03be: ('codigo', 0x0038, 0x0030)}
TABLAS = {'FOREIGN': 0x486334, 'SYSTEM': 0x4871f4, 'DEBUGGING': 0x487404}
TIPOS = {0: 'int', 1: 'float', 2: 'str', 6: 'void'}
# ORI: compuerta del sensor de orientación, leída en el desensamblado de 0xf02a0. El literal de
# 0xf032c es la base (r15); la función devuelve 0 si [r15+0] == 0 o si [r15+1] == 0, antes de
# esperar y de leer el puerto 0x0ff04034. Palabras de 16 bits (LE) de 0xf02b6 a 0xf02c5:
# `ldb_s r0,[r15,0]; cmp_s r0,0; beq 0xf036a; ldb_s r0,[r15,1]; cmp_s r0,0; beq 0xf036a`,
# y en 0xf036a `mov_s r0,0`.
ORI_LITERAL, ORI_COMPUERTA, ORI_SALIDA = 0xf032c, 0xf02b6, 0xf036a
ORI_CODIGO = [0x8f00, 0xe080, 0x00b2, 0x0001, 0x8f01, 0xe080, 0x00aa, 0x0001]
ORI_ESTADOS = (0x0101, 0x0100)                                   # los que el firmware puede dejar
ORI_AJENOS = (0x0001, 0x0000, 0x0201, 0x0102, 0xffff, 0x0180)    # ya aplicado, o desconocidos
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
    previstos = {**PARCHES, **PARCHES_ENCADENADOS}[nombre]
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


def simular(crudo, memoria, pasos=1000):
    """Ejecuta un script del subconjunto verificado sobre `memoria` ({dirección: byte}). Sólo conoce
    peek/poke por Run_SpecifyFunc, LOG_PRINT VERIFY, `IF v == N THEN línea`, REM y END; cualquier otra
    sentencia, una lectura fuera de la memoria dada o una variable sin valor es un error (no se salta
    nada en silencio). Devuelve (log, operaciones) con operaciones = [('r'|'w', dirección, ancho, valor)]."""
    prog = []
    for l in crudo.decode('ascii').splitlines():
        m = re.match(r'(\d+) (.*)$', l)
        if m:
            prog.append((int(m.group(1)), m.group(2).strip()))
    lineas = [n for n, _ in prog]
    llamada = re.compile(r'FOREIGN ([a-z]) = Run_SpecifyFunc\((\d+), (\d+), 0, (\d+), (\d+), 0, 0, 0, 0\)$')
    var, log, ops, i = {}, [], [], 0
    for _ in range(pasos):
        if i >= len(prog):
            raise ValueError('el programa se acaba sin END')
        cuerpo = prog[i][1]
        i += 1
        if re.match(r'REM( |$)', cuerpo):
            continue
        if cuerpo == 'END':
            return log, ops
        m = llamada.match(cuerpo)
        if m:
            f, direccion, valor = int(m.group(2)), int(m.group(4)), int(m.group(5))
            if f in PEEK:
                var[m.group(1)] = int.from_bytes(bytes(memoria[direccion + k] for k in range(PEEK[f])), 'little')
                ops.append(('r', direccion, PEEK[f], var[m.group(1)]))
            elif f in POKE:
                for k in range(POKE[f]):
                    memoria[direccion + k]  # KeyError si escribe fuera de la memoria modelada
                    memoria[direccion + k] = valor >> 8 * k & 0xff
                var[m.group(1)] = 0
                ops.append(('w', direccion, POKE[f], valor))
            else:
                raise ValueError(f'función {f:#x} fuera del intérprete de prueba')
            continue
        m = re.match(r'LOG_PRINT VERIFY ([a-z])$', cuerpo)
        if m:
            log.append(var[m.group(1)])
            continue
        m = re.match(r'IF ([a-z]) == (\d+) THEN (\d+)$', cuerpo)
        if m:
            if var[m.group(1)] == int(m.group(2)):
                i = lineas.index(int(m.group(3)))
            continue
        raise ValueError(f'sentencia fuera del intérprete de prueba: {cuerpo!r}')
    raise ValueError('el programa no termina')


def revisar_ori(crudo, direccion):
    """F14 sobre ORI: lo corre con cada estado inicial de la palabra [direccion]. (ok, detalle)."""
    problemas = []
    for inicial in ORI_ESTADOS + ORI_AJENOS:
        mem = {direccion: inicial & 0xff, direccion + 1: inicial >> 8}
        try:
            log, ops = simular(crudo, mem)
        except (KeyError, ValueError) as e:
            problemas.append(f'{inicial:#06x}: {type(e).__name__} {e}')
            continue
        final = mem[direccion] | mem[direccion + 1] << 8
        escrituras = [o for o in ops if o[0] == 'w']
        if inicial in ORI_ESTADOS:
            esperado = inicial & 0xff  # byte bajo intacto, byte alto (compuerta) en 0
            if final != esperado or log != [inicial, esperado] or len(escrituras) != 1 \
                    or ops[0] != ('r', direccion, 2, inicial) or ops[-1] != ('r', direccion, 2, esperado):
                problemas.append(f'{inicial:#06x}: final {final:#06x}, log {log}, operaciones {ops}')
        elif escrituras or final != inicial or log != [inicial]:
            problemas.append(f'{inicial:#06x}: no debía escribir; final {final:#06x}, log {log}, operaciones {ops}')
    return not problemas, f'{len(ORI_ESTADOS)} estados con escritura y {len(ORI_AJENOS)} sin ella; problemas: {problemas}'


class MemoriaDeFabrica(dict):
    """Memoria para `simular`: el firmware de fábrica, más lo que se le ponga o se escriba encima."""

    def __init__(self, extra):
        super().__init__(extra)
        self.fw = open(STOCK, 'rb').read()

    def __missing__(self, direccion):
        if not STOCK_BASE <= direccion < STOCK_BASE + len(self.fw):
            raise KeyError(direccion)
        return self.fw[direccion - STOCK_BASE]

    def cambiados(self):
        return {d: v for d, v in self.items()
                if not STOCK_BASE <= d < STOCK_BASE + len(self.fw) or self.fw[d - STOCK_BASE] != v}


def referencias_a(destino):
    """Todas las formas de llegar a `destino` en el código de fábrica: `bl`/`blcc`, `b`/`bcc` y
    punteros de 32 bits. Se decodifica cada posición par (los falsos positivos sólo suman)."""
    fw = open(STOCK, 'rb').read()
    fin = min(len(fw), 0x3a0000 - STOCK_BASE) - 4
    refs = []
    for off in range(0, fin, 2):
        h0, h1 = fw[off] | fw[off + 1] << 8, fw[off + 2] | fw[off + 3] << 8
        pc = STOCK_BASE + off
        if pc % 4 == 0 and fw[off:off + 4] == destino.to_bytes(4, 'little'):  # literales y tablas: alineados a 4
            refs.append(('puntero', pc))
        w = h0 << 16 | h1
        mayor, s9, s10, t4 = w >> 27, w >> 18 & 0x1ff, w >> 6 & 0x3ff, w & 0xf
        if mayor == 1 and not w >> 16 & 1:        # bl (bit 17 = 1, 25 bits) o blcc (21 bits), en palabras
            d = (t4 << 19 | s10 << 9 | s9) if w >> 17 & 1 else (s10 << 9 | s9)
            bits = 23 if w >> 17 & 1 else 19
            d = (d - (1 << bits) if d >> bits - 1 else d) << 2
            if (pc & ~3) + d == destino:
                refs.append(('bl', pc))
        elif mayor == 0:                          # b (bit 16 = 1, 25 bits) o bcc (21 bits), en medias palabras
            s10b = w >> 17 & 0x3ff
            d = (t4 << 20 | s10 << 10 | s10b) if w >> 16 & 1 else (s10 << 10 | s10b)
            bits = 24 if w >> 16 & 1 else 20
            d = (d - (1 << bits) if d >> bits - 1 else d) << 1
            if (pc & ~3) + d == destino:
                refs.append(('b', pc))
    return refs


def revisar_m4q(crudo):
    """F17: M4Q entero sobre el firmware de fábrica como memoria, en cinco estados. (ok, detalle)."""
    def palabra(v):
        return {0: v & 0xff, 1: v >> 8}
    a, b = M4Q_FABRICA[M4Q_RECORTE], M4Q_FABRICA[M4Q_FORMATO]
    na, nb = M4Q_NUEVO[M4Q_RECORTE], M4Q_NUEVO[M4Q_FORMATO]
    estados = {  # nombre: (modo, palabra del recorte, palabra del formato, log esperado, escribe)
        'modo 4, de fábrica': (4, a, b, [4, a, b, na, nb], True),
        'modo 0': (0, a, b, [0], False),
        'modo 4, recorte ajeno': (4, 0xc045, b, [4, 0xc045], False),
        'modo 4, formato ajeno': (4, a, 0x7008, [4, a, 0x7008], False),
        'modo 4, ya aplicado': (4, na, nb, [4, na], False),
    }
    problemas = []
    for nombre, (modo, pa, pb, log_esperado, escribe) in estados.items():
        mem = MemoriaDeFabrica({M4Q_MODO + k: modo >> 8 * k & 0xff for k in range(4)})
        mem.update({M4Q_RECORTE + k: v for k, v in palabra(pa).items()})
        mem.update({M4Q_FORMATO + k: v for k, v in palabra(pb).items()})
        try:
            log, ops = simular(crudo, mem)
        except (KeyError, ValueError) as e:
            problemas.append(f'{nombre}: {type(e).__name__} {e}')
            continue
        escrituras = [o for o in ops if o[0] == 'w']
        final = [mem[x] | mem[x + 1] << 8 for x in (M4Q_RECORTE, M4Q_FORMATO)]
        codigo = {d: v for d, v in mem.cambiados().items() if not M4Q_MODO <= d < M4Q_MODO + 4}
        if escribe:
            # orden: primero el recorte nulo (inocuo con formato 0), después el formato
            bien = escrituras == [('w', M4Q_RECORTE, 2, na), ('w', M4Q_FORMATO, 2, nb)] and final == [na, nb] \
                and sorted(codigo) == sorted(PARCHES_ENCADENADOS['M4Q']) \
                and ops.index(('r', M4Q_FORMATO, 2, pb)) < ops.index(escrituras[0])
        else:
            bien = not escrituras and final == [pa, pb]
        if not bien or log != log_esperado:
            problemas.append(f'{nombre}: log {log}, escrituras {escrituras}, final {[hex(x) for x in final]}, '
                             f'bytes de código distintos {sorted(map(hex, codigo))}')
    return not problemas, f'{len(estados)} estados; problemas: {problemas}'


def revisar_m4w(crudo):
    """F20: M4W entero sobre el firmware de fábrica con M4L y M4Q encima, en cinco estados."""
    def palabra(d, v):
        return {d: v & 0xff, d + 1: v >> 8}
    lit = M4W_LITERAL + 2
    q, viejo, nuevo = M4Q_NUEVO[M4Q_FORMATO], 0x0038, 0x0030
    estados = {  # nombre: (palabra de M4L, palabra de M4Q, mitad alta del literal, log, escribe)
        'M4L y M4Q aplicados': (M4W_M4L_VALOR, q, viejo, [M4W_M4L_VALOR, q, viejo, nuevo], True),
        'sin M4L': (0x7825, q, viejo, [0x7825], False),
        'sin M4Q': (M4W_M4L_VALOR, M4Q_FABRICA[M4Q_FORMATO], viejo, [M4W_M4L_VALOR, M4Q_FABRICA[M4Q_FORMATO]], False),
        'literal ajeno': (M4W_M4L_VALOR, q, 0x0078, [M4W_M4L_VALOR, q, 0x0078], False),
        'ya aplicado': (M4W_M4L_VALOR, q, nuevo, [M4W_M4L_VALOR, q, nuevo], False),
    }
    problemas = []
    for nombre, (l, f, h, log_esperado, escribe) in estados.items():
        previo = {**palabra(M4W_M4L, l), **palabra(M4Q_FORMATO, f), **palabra(lit, h)}
        mem = MemoriaDeFabrica(previo)
        try:
            log, ops = simular(crudo, mem)
        except (KeyError, ValueError) as e:
            problemas.append(f'{nombre}: {type(e).__name__} {e}')
            continue
        escrituras = [o for o in ops if o[0] == 'w']
        tocados = {d for d in mem if mem[d] != previo.get(d, mem.fw[d - STOCK_BASE])}
        bien = (escrituras == [('w', lit, 2, nuevo)] and tocados == {lit} and ops[-1] == ('r', lit, 2, nuevo)) \
            if escribe else (not escrituras and not tocados)
        if not bien or log != log_esperado:
            problemas.append(f'{nombre}: log {log}, escrituras {escrituras}, bytes tocados {sorted(map(hex, tocados))}')
    return not problemas, f'{len(estados)} estados; problemas: {problemas}'


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

    # F13: ORI contra el firmware de fábrica y la RAM volcada
    fw, ram = open(STOCK, 'rb').read(), open(RAM, 'rb').read()

    def palabra(dir_ram, n=2):
        return int.from_bytes(fw[dir_ram - STOCK_BASE:dir_ram - STOCK_BASE + n], 'little')

    ori = leer('fase3', 'Batch', 'ORI.srt')
    base = palabra(ORI_LITERAL, 4)
    usadas = {int(x) for x in re.findall(r'Run_SpecifyFunc\(\d+, \d+, 0, (\d+),', ori.decode('ascii'))}
    codigo = [palabra(ORI_COMPUERTA + 2 * k) for k in range(len(ORI_CODIGO))]
    # destino de cada `beq` (0xf02ba y 0xf02c2): (pc & ~3) + desplazamiento, que en estas dos
    # instrucciones es su primera palabra; los dos deben caer en `mov_s r0,0`
    saltos = [((ORI_COMPUERTA + 4 + 8 * k) & ~3) + codigo[2 + 4 * k] for k in range(2)]
    en_ram = int.from_bytes(ram[base:base + 2], 'little')
    anotar('ori_direccion_y_compuerta', 'F13',
           usadas == {base} and codigo == ORI_CODIGO and saltos == [ORI_SALIDA] * 2
           and palabra(ORI_SALIDA) == 0xd800 and en_ram in ORI_ESTADOS
           and fw.count((base + 1).to_bytes(4, 'little')) == 1,
           f'ORI usa {sorted(map(hex, usadas))}, literal de {ORI_LITERAL:#x} = {base:#x}; compuerta '
           f'{[hex(c) for c in codigo]}, saltos a {[hex(x) for x in saltos]}, allí {palabra(ORI_SALIDA):#x}; '
           f'la RAM volcada tiene {en_ram:#06x}; literales a {base + 1:#x} en el código: '
           f'{fw.count((base + 1).to_bytes(4, "little"))}')

    # F14: ORI ejecutado sobre memoria simulada, y dos controles de que la prueba ve los errores
    ok, detalle = revisar_ori(ori, base)
    anotar('ori_ejecutado', 'F14', ok, detalle)
    ok, detalle = revisar_ori(mutar(ori, '4041112, 1, 0, 0, 0, 0)', '4041112, 257, 0, 0, 0, 0)'), base)
    anotar('ori_byte_alto_sin_apagar', 'F14', not ok and '0x0101: final 0x0101' in detalle, detalle)
    ok, detalle = revisar_ori(mutar(ori, '60 END\r\n', '60 REM\r\n'), base)
    anotar('ori_sin_corte_por_valor_ajeno', 'F14', not ok and 'no debía escribir' in detalle, detalle)

    # F15: los dos juegos de prueba de ORI, armados como irían a la SD
    anotar('ori_copias_iguales', 'F15', ori == leer('fase1', 'Batch', 'ORI.srt'), 'fase1/ORI.srt == fase3/ORI.srt')
    for fase, archivo, esperada in (('fase3', 'BatchScripts_ORI.txt', ['P8', 'EET', 'EETV', 'ORI']),
                                    ('fase1', 'BatchScripts_ORIM4L.txt', ['M4L', 'ORI'])):
        lista = open(os.path.join(KIT, fase, 'Batch', archivo)).read().split()
        anotar(f'sd_ori_{fase}_lista', 'F15', lista == esperada, f'{archivo} = {lista}')
        debe_pasar(f'sd_ori_{fase}', 'F15',
                   carpeta(f'sd_ori_{fase}', {n + '.srt': leer(fase, 'Batch', n + '.srt') for n in lista}, lista))

    # F16: M4Q contra el firmware de fábrica
    m4q = leer('fase1', 'Batch', 'M4Q.srt')
    fwb = open(STOCK, 'rb').read()
    leidas = {d: int.from_bytes(fwb[d - STOCK_BASE:d - STOCK_BASE + 2], 'little') for d in M4Q_FABRICA}
    def medias(d, n=2):
        return tuple(int.from_bytes(fwb[d - STOCK_BASE + 2 * k:d - STOCK_BASE + 2 * k + 2], 'little') for k in range(n))
    refs = [(t, d) for t, d in referencias_a(M4Q_CONVERSOR)
            if not (d in M4Q_MITAD_DE_INSTRUCCION and t == 'b'
                    and medias(M4Q_MITAD_DE_INSTRUCCION[d][0]) == M4Q_MITAD_DE_INSTRUCCION[d][1:])]
    control = referencias_a(0x1653e0)  # función vecina con llamadas conocidas: el barrido las ve
    anotar('m4q_sitio_en_firmware', 'F16',
           leidas == M4Q_FABRICA and refs == [('bl', M4Q_LLAMADA)]
           and ('bl', 0x148f20) in control and M4Q_LLAMADA - M4Q_FORMATO == 0x10,
           f'palabras distintas de las leídas: {[hex(d) for d in leidas if leidas[d] != M4Q_FABRICA[d]]}; '
           f'referencias a {M4Q_CONVERSOR:#x}: {[(t, hex(d)) for t, d in refs]}; control 0x1653e0: '
           f'{len(control)} referencias, incluye bl 0x148f20: {("bl", 0x148f20) in control}')
    ok, detalle = revisar_parches('M4Q')
    anotar('parches_M4Q', 'F10 F11 F16', ok, detalle)

    # F17: M4Q ejecutado sobre el firmware de fábrica, y un control de que la prueba ve un valor malo
    ok, detalle = revisar_m4q(m4q)
    anotar('m4q_simulado', 'F17', ok, detalle)
    ok, detalle = revisar_m4q(mutar(m4q, f', {M4Q_NUEVO[M4Q_FORMATO]}, 0, 0, 0, 0)', ', 55301, 0, 0, 0, 0)'))
    anotar('m4q_control_valor_cambiado', 'F17', not ok and 'modo 4, de fábrica' in detalle, detalle)

    # F18: el juego M4L + M4Q, armado como va a la SD
    lista = open(os.path.join(KIT, 'fase1', 'Batch', 'BatchScripts_M4LQ.txt')).read().split()
    m4l = leer('fase1', 'Batch', 'M4L.srt').decode('ascii')
    anotar('sd_m4lq_lista', 'F18',
           lista == ['M4L', 'M4Q'] and re.search(r'= Run_SpecifyFunc\(450736, 1, 0, 4, 0, 0, 0, 0, 0\)\r\n', m4l),
           f'BatchScripts_M4LQ.txt = {lista}; M4L deja el modo 4 antes de que corra M4Q')
    debe_pasar('sd_m4lq', 'F18',
               carpeta('sd_m4lq', {n + '.srt': leer('fase1', 'Batch', n + '.srt') for n in lista}, lista))

    # F19: M4W contra el firmware de fábrica
    m4w = leer('fase1', 'Batch', 'M4W.srt')
    leidas = {d: medias(d, 1)[0] for d in M4W_FABRICA}
    carga = (M4W_CARGA & ~3) + (leidas[M4W_CARGA] & 0xff) * 4          # ld_s b,[pcl,u8·4]
    otras = [STOCK_BASE + o for o in range(0, 0x3a0000 - STOCK_BASE, 2)  # cualquier ld_s rX,[pcl,…] al literal
             if fwb[o + 1] >> 3 == 0x1a and ((STOCK_BASE + o) & ~3) + fwb[o] * 4 == M4W_LITERAL]
    llamadas = {f: [d for _, d in referencias_a(f)] for f in M4W_LLAMADAS}
    literal = leidas[M4W_LITERAL] | leidas[M4W_LITERAL + 2] << 16
    anotar('m4w_sitio_en_firmware', 'F19',
           leidas == M4W_FABRICA and carga == M4W_LITERAL and otras == [M4W_CARGA]
           and llamadas == {f: [d] for f, d in M4W_LLAMADAS.items()}
           and literal ^ (0x0030 << 16 | leidas[M4W_LITERAL]) == 1 << M4W_BIT
           and leidas[0x147824] & 0x1f == M4W_BIT,
           f'literal {literal:#x}; carga desde {M4W_CARGA:#x} apunta a {carga:#x}; ld_s al literal: '
           f'{[hex(x) for x in otras]}; llamadas: { {hex(f): [hex(x) for x in v] for f, v in llamadas.items()} }')
    ok, detalle = revisar_parches('M4W')
    anotar('parches_M4W', 'F10 F11 F19', ok, detalle)

    # F20: M4W ejecutado, y control
    ok, detalle = revisar_m4w(m4w)
    anotar('m4w_simulado', 'F20', ok, detalle)
    ok, detalle = revisar_m4w(mutar(m4w, ', 48, 0, 0, 0, 0)', ', 49, 0, 0, 0, 0)'))
    anotar('m4w_control_valor_cambiado', 'F20', not ok and 'M4L y M4Q aplicados' in detalle, detalle)

    # F21: el juego M4L + M4Q + M4W
    lista = open(os.path.join(KIT, 'fase1', 'Batch', 'BatchScripts_M4LQW.txt')).read().split()
    anotar('sd_m4lqw_lista', 'F21', lista == ['M4L', 'M4Q', 'M4W'], f'BatchScripts_M4LQW.txt = {lista}')
    debe_pasar('sd_m4lqw', 'F21',
               carpeta('sd_m4lqw', {n + '.srt': leer('fase1', 'Batch', n + '.srt') for n in lista}, lista))

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
