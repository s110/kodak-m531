#!/usr/bin/env python3
"""Verifica los scripts .srt antes de copiarlos a la SD de la M531 (parser estricto, lista blanca).

uso: python3 -I tools/check_scripts.py CARPETA_BATCH

Regla general: todo lo que no esté explícitamente permitido es un error. En concreto falla si:
  * un identificador no es palabra clave, variable creada con LET o función permitida
    (se extraen sin límites de palabra: `1UpdateFW` también se detecta);
  * una función de cualquiera de las tablas del firmware aparece fuera de una llamada válida
    `PALABRA_CLAVE Nombre(args)` (sin paréntesis, con coma en medio, etc.);
  * la palabra clave no corresponde a la tabla de la función;
  * los argumentos no cumplen el esquema de esa función (sólo enteros literales en rango, cadenas
    sin barra invertida o, donde se admite, una variable). Run_SpecifyFunc: 9 enteros literales SIN
    signo, destino peek32/poke32/peek16/poke16/flush/modo, nargs exacto, outpos 0 y destino fuera de
    zonas intocables;
  * un IF no tiene exactamente la forma `IF var == ENTERO_SIN_SIGNO THEN línea`. El evaluador
    (0x1991f4) parte la condición en el primer operador de su tabla y exige que cada lado sea un
    símbolo simple: dígitos, TRUE/FALSE, cadena o variable (0x1990d0). `v == -5` deja "-5" como
    símbolo desconocido y detiene la CPU. Las palabras con el bit 31 se comparan y escriben por
    mitades de 16 bits (peek16/poke16);
  * aparece una sentencia que nunca corrió en la cámara: GOTO, GOSUB, RETURN, ELSE, LET;
  * una llamada no respeta el tipo de retorno de la firma (0x199488, igual en las tres tablas): sin
    asignar a una función que devuelve entero o FLOAT32 ("function returns a FLOAT32 or integer"),
    o asignada a una función void ("function returns no value"). Las dos detienen la CPU; la primera
    colgó la cámara el 2026-11-12 con `FOREIGN Run_SpecifyFunc(...)`. Los tipos salen de las firmas
    del firmware (docs_script_manejadores.json; tools/e2e_scripts.py las coteja con la RAM);
  * una variable no es una sola letra minúscula o recibe valor dos veces en el mismo script: las dos
    cosas son válidas por código (0x29bce8, 0x198ff0) y ninguna corrió en la cámara. Las variables
    no pasan de un script a otro (el contexto se crea y se destruye por script, 0x1078d8);
  * una línea no termina en CRLF (todos los scripts que corrieron en la cámara lo usan);
  * un LET crea una variable con nombre de función o palabra clave;
  * hay números con ceros a la izquierda, comillas desparejas o barras invertidas en cadenas;
  * GOTO/GOSUB/THEN saltan a algo que no es una línea existente;
  * no hay número de línea, se repiten o desordenan, o la última línea no es END;
  * BatchScripts.txt falta, está vacío, nombra algo que no es un nombre simple, nombra un script
    inexistente o uno que otras pantallas del firmware ejecutan solas.
"""
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from km531fw import ZONAS_INTOCABLES  # noqa: E402

PEEK32, POKE32, FLUSH = 0x198bbc, 0x2e8a84, 0x24e140
# Mitades de 16 bits, para palabras con el bit 31 (no hay literal decimal sin signo que las exprese):
# 0x736e6 = `j_s.d [blink]; ldw_s r0,[r0,0]` (sin extensión de signo); 0x13f09a = `j_s.d [blink];
# stw_s r1,[r0,0]`. Leídas en el desensamblado; ninguna corrió todavía en la cámara.
PEEK16, POKE16 = 0x736e6, 0x13f09a
SETMODO = 0x6e0b0  # escribe el modo de captura (palabra 0x3d97a8, sólo RAM); valores válidos 0–4
NARGS = {PEEK32: 1, POKE32: 2, FLUSH: 2, SETMODO: 1, PEEK16: 1, POKE16: 2}
ALINEACION = {PEEK32: 4, POKE32: 4, FLUSH: 4, PEEK16: 2, POKE16: 2}
ANCHO = {POKE32: 4, POKE16: 2}
NO_VERIFICADAS = ('GOTO', 'GOSUB', 'RETURN', 'ELSE', 'LET')
INT_MAX = 0x7fffffff
ZONAS_PROHIBIDAS = ZONAS_INTOCABLES + [(0x0, 0x48000, 'vectores y pilas')]
RAM_MAX = 0x4000000
CLAVES = {'REM', 'LET', 'END', 'IF', 'THEN', 'ELSE', 'GOTO', 'GOSUB', 'RETURN', 'SYSTEM', 'FOREIGN',
          'DEBUGGING', 'TRUE', 'FALSE', 'LOG_PRINT', 'VERIFY', 'IGNORE'}  # LOG_PRINT VERIFY|IGNORE <expresión>
RESERVADOS = {'reset', 'iso_calibration', 'battestcipa', 'battestpreview', 'preview'}

# esquema de argumentos: lista de ('int', min, max) | ('str',) | ('val',) = entero literal o variable
X, Y = ('int', 0, 479), ('int', 0, 239)
ESQUEMAS = {
    'ScreenString': [X, Y, ('str',)],
    'ScreenInt32': [X, Y, ('val',)],
    'ScreenInt32_Hex': [X, Y, ('val',)],
    'delay_us': [('int', 0, 10_000_000)],
    'ClearOSD': [],
    'GetSystemDateTime': [],
    'SaveCFAonTake': [('int', 0, 1)],
    'SaveCFAonIRP': [('int', 0, 1)],
    'Take12BitCCDRaw': [('int', 0, 1)],
    'EnableS1ImgSaving': [('int', 0, 1)],
    'DebugMsgLog': [('int', 0, 1)],
    'MemRead': [('int', 0x48000, RAM_MAX - 4)],
    'Run_SpecifyFunc': None,  # validación propia
}
PERMITIDAS = set(ESQUEMAS)
_mapa = json.load(open(os.path.join(os.path.dirname(AQUI), 'docs_script_manejadores.json')))
TABLA, RETORNO = {}, {}
for e in _mapa:
    TABLA.setdefault(e['nombre'], set()).add(e['palabra_clave'])
    RETORNO[(e['palabra_clave'], e['nombre'])] = e['firma'].split()[0]  # 'void' | 'int' (byte 6 | 0 de la firma)
ENTERO = re.compile(r'-?(0|[1-9]\d*)$')
SIN_SIGNO = re.compile(r'(0|[1-9]\d*)$')
IF_VERIFICADO = re.compile(r'IF ([A-Za-z][A-Za-z0-9]*) == (0|[1-9]\d*) THEN ([1-9]\d*)$')
# Forma verificada (0x10710c): `PALABRA_CLAVE [var =] Funcion(args)`. `LET x = PALABRA_CLAVE f()` NO existe:
# el evaluador de LET (0x1993b8) sólo acepta operandos simples y cualquier error detiene la CPU (0x4b4e0).
LLAMADA = re.compile(r'\b(SYSTEM|FOREIGN|DEBUGGING) (?:([A-Za-z][A-Za-z0-9]*) = )?([A-Za-z_]\w*)\(([^()]*)\)')


def _args(texto):
    texto = texto.strip()
    return [] if not texto else [a.strip() for a in texto.split(',')]


def _validar_llamada(kw, var, f, args, variables, err):
    if f not in PERMITIDAS:
        err(f'función no permitida {f}')
        return
    if kw not in TABLA.get(f, set()):
        err(f'{f} no es de la tabla {kw} (es {sorted(TABLA.get(f, []))})')
    else:
        # 0x199488: sin variable y retorno 0/1 -> error; con variable y retorno 6 -> error. Lista
        # blanca: sólo las dos combinaciones que el firmware acepta y que corrieron en la cámara.
        ret = RETORNO[(kw, f)]
        if not var and ret != 'void':
            err(f'{f} devuelve un valor ({ret}): la llamada sin asignar detiene la CPU; usar "{kw} v = {f}(...)"')
        elif var and ret != 'int':
            err(f'{f} no devuelve valor ({ret}): la llamada asignada detiene la CPU; usar "{kw} {f}(...)"')
    if f == 'Run_SpecifyFunc':
        if len(args) != 9 or not all(SIN_SIGNO.match(a) for a in args):
            err('Run_SpecifyFunc necesita 9 enteros literales sin signo')
            return
        v = [int(a) for a in args]
        if any(x > INT_MAX for x in v):
            err('Run_SpecifyFunc: literal mayor que 2147483647 (para el bit 31, usar poke16 por mitades)')
            return
        fn, nargs, outpos, dest = v[0], v[1], v[2], v[3]
        if fn not in NARGS:
            err(f'Run_SpecifyFunc a {fn:#x}, sólo peek32/poke32/peek16/poke16/flush/modo')
            return
        if nargs != NARGS[fn] or outpos != 0:
            err(f'nargs/outpos inválidos para {fn:#x} ({nargs}, {outpos})')
        if any(x != 0 for x in v[3 + NARGS[fn]:]):
            err('argumentos sobrantes de Run_SpecifyFunc distintos de 0')
        if fn == FLUSH and not (0 < v[4] <= 0x10000):
            err(f'flush con longitud {v[4]} fuera de rango')
        if fn == SETMODO:
            if not 0 <= dest <= 4:
                err(f'modo de captura {dest} fuera de 0–4')
            return
        if not 0 <= dest < RAM_MAX or dest % ALINEACION[fn]:
            err(f'dirección {dest:#x} fuera de RAM o desalineada')
        if fn == POKE16 and v[4] > 0xffff:
            err(f'poke16 con valor {v[4]} fuera de 16 bits')
        if fn in ANCHO:
            for ini, fin, motivo in ZONAS_PROHIBIDAS:
                if dest < fin and dest + ANCHO[fn] > ini:
                    err(f'escritura en {dest:#x} ({motivo})')
        return
    esquema = ESQUEMAS[f]
    if len(args) != len(esquema):
        err(f'{f} espera {len(esquema)} argumento(s), tiene {len(args)}')
        return
    for a, e in zip(args, esquema):
        if e[0] == 'str':
            if not re.fullmatch(r'"[^"\\]*"', a):
                err(f'{f}: se esperaba una cadena simple, no {a}')
        elif e[0] == 'val' and a in variables:
            continue
        elif not ENTERO.match(a):
            err(f'{f}: se esperaba un entero literal, no {a}')
        elif e[0] == 'int' and not e[1] <= int(a) <= e[2]:
            err(f'{f}: {a} fuera de rango [{e[1]}, {e[2]}]')


def revisar_srt(ruta):
    errores = []
    crudo = open(ruta, 'rb').read()
    try:
        lineas = crudo.decode('ascii').splitlines()
    except UnicodeDecodeError:
        return [f'{ruta}: contiene caracteres no ASCII']
    if crudo.count(b'\n') != crudo.count(b'\r\n') or crudo.count(b'\r') != crudo.count(b'\r\n') \
            or not crudo.endswith(b'\r\n'):
        errores.append(f'{ruta}: todas las líneas deben terminar en CRLF')
    numeros, saltos, variables, cuerpos = [], [], set(), []
    # 0x10776c: las líneas numeradas se GUARDAN como programa; sólo una línea "RUN" sin número las
    # ejecuta; "QUIT" termina el archivo; cualquier otra línea sin número (salvo REM) aborta.
    inmediatas = [l.strip() for l in lineas if l.strip() and not re.match(r'\d', l.strip())]
    if 'RUN' not in inmediatas:
        errores.append(f'{ruta}: falta la línea "RUN" sin número: sin ella el programa se carga y no se ejecuta')
    for x in inmediatas:
        if x not in ('RUN', 'QUIT') and not re.match(r'REM( |$)', x):
            errores.append(f'{ruta}: línea sin número no admitida: {x!r}')
    numeradas = [l for l in lineas if l.strip() and re.match(r'\d', l.strip())]
    for n, l in enumerate(lineas, 1):
        if not l.strip() or not re.match(r'\d', l.strip()):
            continue
        m = re.match(r'(\d+) (.*)$', l)
        if not m or (len(m.group(1)) > 1 and m.group(1).startswith('0')):
            errores.append(f'{ruta}:{n}: línea sin número válido')
            continue
        num, cuerpo = int(m.group(1)), m.group(2).strip()
        if num in numeros:
            errores.append(f'{ruta}:{n}: número de línea repetido {num}')
        if numeros and num < numeros[-1]:
            errores.append(f'{ruta}:{n}: números de línea fuera de orden')
        numeros.append(num)
        if re.match(r'REM( |$)', cuerpo):
            continue
        cuerpos.append((n, cuerpo))
    for n, cuerpo in cuerpos:
        mv = re.match(r'LET ([A-Za-z][A-Za-z0-9]*) = ', cuerpo) or \
            re.match(r'(?:SYSTEM|FOREIGN|DEBUGGING) ([A-Za-z][A-Za-z0-9]*) = ', cuerpo)
        if mv:
            nombre = mv.group(1)
            if nombre in TABLA or nombre in CLAVES or nombre in PERMITIDAS:
                errores.append(f'{ruta}:{n}: LET no puede crear la variable {nombre}')
            else:
                if not re.fullmatch(r'[a-z]', nombre):
                    errores.append(f'{ruta}:{n}: la variable {nombre} debe ser una sola letra minúscula '
                                   '(lo único que corrió en la cámara)')
                if nombre in variables:
                    errores.append(f'{ruta}:{n}: la variable {nombre} ya tiene valor: reasignar no está '
                                   'verificado en la cámara; usar otra letra o partir el script')
                variables.add(nombre)
    for n, cuerpo in cuerpos:
        def err(msg, n=n):
            errores.append(f'{ruta}:{n}: {msg}')
        if cuerpo.count('"') % 2:
            err('comillas desparejas')
            continue
        if re.search(r'"[^"]*\\[^"]*"', cuerpo):
            err('barra invertida dentro de una cadena')
        sin_texto = re.sub(r'"[^"]*"', '""', cuerpo)
        if re.search(r'(?<![\w.])0\d', sin_texto):
            err('número con ceros a la izquierda')
        if re.match(r'LET ', sin_texto) and re.search(r'\b(SYSTEM|FOREIGN|DEBUGGING)\b', sin_texto):
            err('LET con llamada no existe: usar "FOREIGN var = Funcion(...)"')
        llamadas = LLAMADA.findall(sin_texto)
        for kw, var, f, args in llamadas:
            _validar_llamada(kw, var, f, _args(args), variables, err)
        mlp = re.match(r'LOG_PRINT (\S+) (.*)$', sin_texto)
        if sin_texto.startswith('LOG_PRINT') and (not mlp or mlp.group(1) not in ('VERIFY', 'IGNORE', '0', '1')
                                                  or not re.fullmatch(r'[A-Za-z0-9_]+', mlp.group(2))):
            err('LOG_PRINT debe ser "LOG_PRINT VERIFY|IGNORE|0|1 <variable o número>" sin espacios en la expresión')
        if re.search(r'\bTHEN\s+(GOTO|GOSUB)\b', sin_texto):
            err('"THEN GOTO n" no existe: tras THEN va sólo el número de línea ("THEN n")')
        if re.search(r'\b(IF|THEN)\b', sin_texto):
            mi = IF_VERIFICADO.match(sin_texto)
            if not mi or int(mi.group(2)) > INT_MAX:
                err('IF debe ser exactamente "IF var == ENTERO_SIN_SIGNO THEN línea" (un literal negativo detiene la CPU)')
        for palabra in NO_VERIFICADAS:
            if re.search(rf'\b{palabra}\b', sin_texto):
                err(f'{palabra} no está verificado en la cámara: usar sólo "IF var == N THEN línea" y END')
        resto = LLAMADA.sub(' ', sin_texto)
        resto = re.sub(r'^LOG_PRINT (VERIFY|IGNORE)', 'LOG_PRINT', resto)
        for ident in re.findall(r'[A-Za-z_]\w*', resto):
            if ident in TABLA or ident in PERMITIDAS:
                err(f'{ident} fuera de una llamada válida "PALABRA_CLAVE {ident}(...)"')
            elif ident in ('SYSTEM', 'FOREIGN', 'DEBUGGING'):
                err(f'{ident} sin una llamada válida a continuación')
            elif ident not in CLAVES and ident not in variables:
                err(f'identificador desconocido {ident}')
        for kw, destino in re.findall(r'\b(GOTO|GOSUB|THEN)\b[\s,]*([^\s,]*)', resto):
            if kw == 'THEN' and destino in ('GOTO', 'GOSUB'):
                continue
            if kw == 'THEN' and not destino:
                err('THEN sin destino')
            elif kw == 'THEN' and not destino.isdigit():
                continue  # THEN seguido de sentencia (llamada) ya validada arriba
            elif not destino.isdigit():
                err(f'{kw} a algo que no es un número de línea: {destino!r}')
            else:
                saltos.append((n, int(destino)))
    for n, destino in saltos:
        if destino not in numeros:
            errores.append(f'{ruta}:{n}: salto a la línea {destino}, que no existe')
    if not numeradas or not re.fullmatch(r'\d+ END\s*', numeradas[-1]):
        errores.append(f'{ruta}: la última línea numerada debe ser END')
    return errores


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    carpeta = sys.argv[1]
    errores = []
    lista = os.path.join(carpeta, 'BatchScripts.txt')
    nombres = open(lista).read().split() if os.path.exists(lista) else []
    if nombres:
        b = open(lista, 'rb').read()
        if b.count(b'\n') != b.count(b'\r\n') or not b.endswith(b'\r\n'):
            errores.append('BatchScripts.txt: todas las líneas deben terminar en CRLF')
    if not nombres:
        errores.append('BatchScripts.txt falta o está vacío')
    for nombre in nombres:
        if not re.fullmatch(r'[A-Za-z0-9_]{1,8}', nombre):
            errores.append(f'BatchScripts.txt: "{nombre}" no es un nombre simple (sin extensión, sin carpetas, ≤ 8)')
        elif nombre.lower() in RESERVADOS:
            errores.append(f'BatchScripts.txt: {nombre} es un nombre que otra pantalla ejecuta sola')
        elif not os.path.exists(os.path.join(carpeta, nombre + '.srt')):
            errores.append(f'BatchScripts.txt: falta {nombre}.srt')
    for f in sorted(os.listdir(carpeta)):
        if f.startswith('._'):
            errores.append(f'{f}: archivo de metadatos de macOS; copiar con cp -X o dot_clean')
        elif f.lower().endswith('.srt'):
            if f[:-4].lower() in RESERVADOS:
                errores.append(f'{f}: nombre que otra pantalla del firmware ejecuta sola')
            errores += revisar_srt(os.path.join(carpeta, f))
        elif os.path.isdir(os.path.join(carpeta, f)):
            errores.append(f'{f}/: no se admiten subcarpetas en Batch')
    for e in errores:
        print('ERROR', e)
    print('OK' if not errores else f'{len(errores)} error(es)')
    sys.exit(1 if errores else 0)


if __name__ == '__main__':
    main()
