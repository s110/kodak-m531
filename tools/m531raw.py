#!/usr/bin/env python3
"""RAW de la Kodak EasyShare M531 → DNG.

uso:
  m531raw.py info ARCHIVO [ARCHIVO2]              detecta formato y lo informa
  m531raw.py dng  ARCHIVO [ARCHIVO2] -o SALIDA.dng [--bits N --packing P --width W
                  --layout L --cfa RGGB --black N --white N]

El firmware guarda el RAW sin cabecera, en uno o dos archivos por disparo: 101O####.raw y
101b####.raw (cambia el '_' del nombre del JPG por 'O' o 'b'), probablemente los dos campos
de un CCD entrelazado. Tamaño = ceil(ancho*alto*bits/8) con
bits ∈ {8,10,12,16}. Como las dimensiones sólo existen en RAM durante la captura, todo se
detecta de los datos:

  * bits/empaquetado/ancho: para cada formato candidato se decodifica un tramo y se mide la
    autocorrelación de la secuencia de píxeles. El ancho real (o su doble) da un pico; el
    formato correcto da el pico más fuerte.
  * dos archivos: se prueban "intercalado de filas", "intercalado de pares" y "uno sobre otro";
    gana el que deja filas del mismo color (y, y+2) más parecidas.
  * CFA: la diagonal con medias y texturas más parecidas es la verde. R vs B no se puede saber
    sólo con estadística: se elige el más oscuro como R (típico con luz de día) y se puede
    forzar con --cfa. Ver tools/RAW_FALLAS.md.
"""
import argparse
import json
import os
import struct
import sys

import numpy as np

FORMATOS = [  # (nombre, bits)
    ('u8', 8), ('p10_msb', 10), ('p10_lsb', 10), ('p12_msb', 12), ('p12_lsb', 12),
    ('p14_msb', 14), ('p14_lsb', 14), ('u16_le', 16), ('u16_be', 16),
]
BITS = dict(FORMATOS)


# ---------------------------------------------------------------- desempaquetado
def desempaquetar(datos: bytes, packing: str, n: int | None = None) -> np.ndarray:
    """Devuelve uint16 con los primeros n píxeles (o todos los completos)."""
    b = BITS[packing]
    total = (len(datos) * 8) // b
    n = total if n is None else min(n, total)
    nbytes = (n * b + 7) // 8
    a = np.frombuffer(datos[:nbytes], dtype=np.uint8)
    if packing == 'u8':
        return a[:n].astype(np.uint16)
    if packing in ('u16_le', 'u16_be'):
        return np.frombuffer(datos[:n * 2], dtype='<u2' if packing == 'u16_le' else '>u2').astype(np.uint16)
    out = np.empty(n, dtype=np.uint16)
    orden = 'big' if packing.endswith('msb') else 'little'
    trozo = 1 << 20  # píxeles por bloque; múltiplo de 8 para no partir bytes
    pesos = (1 << np.arange(b - 1, -1, -1, dtype=np.uint32)) if orden == 'big' \
        else (1 << np.arange(b, dtype=np.uint32))
    for i in range(0, n, trozo):
        m = min(trozo, n - i)
        ini_bit = i * b
        bytes_ini = ini_bit // 8  # i*b es múltiplo de 8 porque trozo lo es
        bits = np.unpackbits(a[bytes_ini:bytes_ini + (m * b + 7) // 8], bitorder=orden)[:m * b]
        out[i:i + m] = (bits.reshape(m, b).astype(np.uint32) @ pesos).astype(np.uint16)
    return out


# ---------------------------------------------------------------- detección
def _autocorr(x: np.ndarray, lag_max: int):
    x = x.astype(np.float64)
    x -= x.mean()
    if not x.std():
        return None
    nfft = 1 << int(np.ceil(np.log2(len(x) + lag_max + 1)))
    f = np.fft.rfft(x, nfft)
    ac = np.fft.irfft(f * np.conj(f), nfft)[:lag_max + 1]
    return ac / ac[0]


def _prominencia(ac, l):
    """Cuánto sobresale ac en l (o l±1) sobre su entorno (±3..±12)."""
    if l - 12 < 0 or l + 13 > len(ac):
        return 0.0
    centro = ac[l - 1:l + 2].max()
    entorno = np.concatenate([ac[l - 12:l - 2], ac[l + 3:l + 13]])
    return float(centro - np.median(entorno))


def _ancho_desde_ac(ac, ancho_min, ancho_max):
    """Ancho de fila a partir de la autocorrelación, sin confundir colores del Bayer.

    En un mosaico completo, el desfase de una fila (W) compara filas de colores distintos y el
    de dos filas (2W) compara el mismo color. En un campo de un CCD entrelazado (sólo filas de un
    tipo), ya W compara el mismo color. Se busca el mayor pico en desfases pares de [min, 2·max]
    y se decide: si L/2 también es un pico marcado, el ancho es L/2 (mosaico completo); si no, L.
    """
    lags = np.arange(ancho_min - ancho_min % 2, min(2 * ancho_max, len(ac) - 13) + 1, 2)
    L = int(lags[np.argmax(ac[lags])])
    pico = float(ac[L])
    W = L
    if L // 2 >= ancho_min and _prominencia(ac, L // 2) >= 0.3 * max(_prominencia(ac, L), 1e-6):
        W = L // 2
    if W > ancho_max:
        W = L // 2  # nunca devolver un ancho fuera de rango
    return pico, W


def detectar_formato(datos: bytes, ancho_min=1500, ancho_max=7000, muestra=4_000_000):
    res = []
    for packing, b in FORMATOS:
        px = desempaquetar(datos, packing, muestra)
        if len(px) < 3 * 2 * ancho_max:
            continue
        # empezar lejos del borde superior (negro óptico, filas de basura)
        ini = len(px) // 4
        x = px[ini:].astype(np.float64)
        ac_bruta = _autocorr(x[:400_000], 4)
        # para el ancho: diferencia horizontal entre píxeles del mismo color. Quita los gradientes
        # amplios de la escena (que correlacionan a cualquier distancia) y deja los bordes, que sí
        # se alinean de una fila a la siguiente.
        ac = _autocorr(x[2:] - x[:-2], 2 * ancho_max + 16)
        if ac is None or ac_bruta is None:
            continue
        pico, ancho = _ancho_desde_ac(ac, ancho_min, ancho_max)
        vecino = float(ac_bruta[2])
        vals = px[ini:ini + 200_000]
        usado = int(vals.max()).bit_length()
        # el ancho correcto da pico vertical; el empaquetado correcto, además, vecinos del mismo
        # color (desfase 2) parecidos. Un empaquetado equivocado mezcla bits y rompe lo segundo.
        puntaje = pico * max(vecino, 0.0) ** 4
        # Un contenedor de 16 bits guarda datos de 12–14 bits: los dos bits altos quedan vacíos.
        # Si se llenan, lo más probable es que sean dos píxeles de 8 bits leídos como uno.
        if b == 16 and usado > 14:
            puntaje *= 0.05  # ningún sensor de 12–14 bits llena los 16: casi seguro son 8 bits
        if b == 16:
            # En datos reales de 12–14 bits el byte bajo es casi uniforme (media ≈ 127) y el alto es
            # chico. Si el byte "bajo" tiene media baja y el "alto" una media parecida, son dos
            # píxeles de 8 bits leídos como uno.
            q = len(datos) // 4
            crudo = np.frombuffer(datos[q:q + 800_000], dtype=np.uint8).astype(np.float64)
            alto_b, bajo_b = (crudo[1::2], crudo[0::2]) if packing == 'u16_le' else (crudo[0::2], crudo[1::2])
            if bajo_b.mean() < 80 and alto_b.mean() > 0.3 * bajo_b.mean():
                puntaje *= 0.05
        res.append(dict(packing=packing, bits=b, ancho=ancho, pico=round(pico, 4), vecino=round(vecino, 4),
                        puntaje=round(puntaje, 4), bits_usados=usado))
    res.sort(key=lambda r: -r['puntaje'])
    return res


# Confianza: puntaje alto, o puntaje moderado con clara ventaja sobre el segundo candidato.
# Medido: ruido 0,0; cuadro oscuro 0,004; plano con viñeteo 0,072 (ventaja 1,08×).
CONFIANZA_ALTA, CONFIANZA_MIN, VENTAJA_MIN = 0.15, 0.03, 1.5


def confiable(cands):
    if not cands:
        return False
    p1 = cands[0]['puntaje']
    p2 = cands[1]['puntaje'] if len(cands) > 1 else 0.0
    return p1 >= CONFIANZA_ALTA or (p1 >= CONFIANZA_MIN and p1 >= VENTAJA_MIN * max(p2, 1e-9))


def a_imagen(datos: bytes, packing: str, ancho: int) -> np.ndarray:
    px = desempaquetar(datos, packing)
    alto = len(px) // ancho
    return px[:alto * ancho].reshape(alto, ancho)


def _suavidad(img: np.ndarray) -> float:
    """Menor = mejor: diferencia media entre filas del mismo color (y, y+2)."""
    a = img[:-2:, :].astype(np.int32)
    b = img[2:, :].astype(np.int32)
    return float(np.mean(np.abs(a - b)))


def combinar(campos: list[np.ndarray], layout: str | None):
    if len(campos) == 1:
        return campos[0], 'unico'
    A, B = campos
    h = min(len(A), len(B))
    w = min(A.shape[1], B.shape[1])
    A, B = A[:h, :w], B[:h, :w]
    opciones = {}
    # intercalado de filas: A0 B0 A1 B1 ...
    f = np.empty((2 * h, w), dtype=A.dtype); f[0::2] = A; f[1::2] = B
    opciones['filas'] = f
    # intercalado de pares: A0 A1 B0 B1 A2 A3 ...
    if h % 2 == 0:
        p = np.empty((2 * h, w), dtype=A.dtype)
        p.reshape(h, 2, w)[0::2] = A.reshape(h // 2, 2, w)
        p.reshape(h, 2, w)[1::2] = B.reshape(h // 2, 2, w)
        opciones['pares'] = p
    # Si los dos archivos son casi la misma imagen, son campos entrelazados de una misma escena y
    # no mitades apiladas (que muestran contenido distinto).
    a_r = A[::16, ::16].astype(np.float64).ravel(); b_r = B[::16, ::16].astype(np.float64).ravel()
    parecidos = a_r.std() and b_r.std() and np.corrcoef(a_r, b_r)[0, 1] > 0.97
    if not parecidos or layout == 'apilado':
        opciones['apilado'] = np.vstack([A, B])
    if layout:
        if layout not in opciones:
            raise SystemExit(f'disposición {layout} imposible con campos de {h} filas')
        return opciones[layout], layout
    puntaje = {k: _suavidad(v) for k, v in opciones.items()}
    mejor = min(puntaje, key=puntaje.get)
    return opciones[mejor], mejor


def detectar_cfa(img: np.ndarray):
    h, w = img.shape
    y0, x0 = (h // 8) & ~1, (w // 8) & ~1  # origen par: la fase del patrón es la de la imagen
    c = img[y0: h - y0, x0: w - x0].astype(np.float64)
    c = c[: c.shape[0] // 2 * 2, : c.shape[1] // 2 * 2]
    p = {(y, x): c[y::2, x::2] for y in (0, 1) for x in (0, 1)}
    def parecido(a, b):  # menor = más parecidos (media y textura)
        return abs(a.mean() - b.mean()) / (a.mean() + b.mean() + 1e-9) + \
            np.mean(np.abs(a - b)) / (a.mean() + b.mean() + 1e-9)
    d_principal = parecido(p[0, 0], p[1, 1])
    d_secundaria = parecido(p[0, 1], p[1, 0])
    if d_principal < d_secundaria:  # verdes en (0,0) y (1,1)
        o1, o2 = p[0, 1].mean(), p[1, 0].mean()
        return ('GRBG' if o1 < o2 else 'GBRG'), dict(d_verde=d_principal, d_otra=d_secundaria)
    o1, o2 = p[0, 0].mean(), p[1, 1].mean()
    return ('RGGB' if o1 < o2 else 'BGGR'), dict(d_verde=d_secundaria, d_otra=d_principal)


def neutro_parche_blanco(img, cfa, negro, blanco, pct=98):
    """Balance por las zonas más claras sin saturar (2 % superior de luminancia). Más estable que el
    mundo gris en escenas con un color dominante, si hay algo blanco o gris claro en la foto."""
    v = img.astype(np.float64) - negro
    pos = {c: [(i // 2, i % 2) for i, ch in enumerate(cfa) if ch == c] for c in 'RGB'}
    ch = {c: np.mean([v[y::2, x::2] for y, x in pos[c]], axis=0) for c in 'RGB'}
    R, G, B = ch['R'], ch['G'], ch['B']
    tope = (blanco - negro) * 0.97
    ok = (R < tope) & (G < tope) & (B < tope) & (G > 0)
    L = R + G + B
    if ok.sum() < 1000:
        return None
    sel = ok & (L >= np.percentile(L[ok], pct))
    n = np.array([R[sel].mean(), G[sel].mean(), B[sel].mean()])
    return tuple(float(x) for x in np.clip(n / n[1], 0.05, 4.0))


def neutro_mundo_gris(img, cfa, negro, blanco):
    """AsShotNeutral por mundo gris: media de cada canal sin negro ni saturados, relativa a G."""
    pos = {c: [] for c in 'RGB'}
    for i, c in enumerate(cfa):
        pos[c].append((i // 2, i % 2))
    v = img.astype(np.float64) - negro
    tope = (blanco - negro) * 0.95
    medias = {}
    for c, ps in pos.items():
        x = np.concatenate([v[y::2, xx::2].ravel() for y, xx in ps])
        x = x[(x > 0) & (x < tope)]
        medias[c] = x.mean() if len(x) else 1.0
    return tuple(min(max(medias[c] / medias['G'], 0.05), 4.0) for c in 'RGB')


def neutro_creible(neutro):
    """¿Está el neutro cerca de los balances que la cámara elige de verdad (ver LOCUS_*)? Filtra los
    resultados del parche blanco cuando lo más claro de la escena tiene color propio."""
    if neutro is None or min(neutro) <= 0:
        return False
    x, y = np.log(neutro[0] / neutro[1]), np.log(neutro[2] / neutro[1])
    return bool(LOCUS_LN_R[0] <= x <= LOCUS_LN_R[1] and abs(y - (LOCUS_A + LOCUS_B * x)) <= LOCUS_TOL)


def awb_camara(ruta_raw):
    """Ganancias R, G, B (÷256) del AWB de la cámara, leídas del MakerNote del JPG hermano; None si no hay.
    En modo 0 coinciden con el ajuste RAW↔JPG. En modo 4 no sirven de balance: sin flash la cámara deja el
    valor por omisión (400, 256, 456) y con flash salen corridas (ver NOTAS.md). Sólo se informa."""
    d, n = os.path.split(ruta_raw)
    try:
        from PIL import Image
        mk = Image.open(os.path.join(d, n[:3] + '_' + n[4:8] + '.JPG')).getexif().get_ifd(0x8769).get(0x927c)
        if not mk or len(mk) < 0x21ac:
            return None
        g = struct.unpack_from('<3I', mk, 0x1318)
        if g != struct.unpack_from('<3I', mk, 0x21a0) or not (200 <= g[1] <= 512 and all(100 <= v <= 4096 for v in g)):
            return None
        return list(g)
    except Exception:
        return None


# ---------------------------------------------------------------- DNG
_CFA = {'RGGB': (0, 1, 1, 2), 'BGGR': (2, 1, 1, 0), 'GRBG': (1, 0, 2, 1), 'GBRG': (1, 2, 0, 1)}
# Matriz provisional XYZ(D65)→cámara: inversa de la CCM de luz de día de la C713 (misma
# familia Altek). Se reemplaza al calibrar con fotos reales de la M531.
_CCM_C713 = np.array([[150592, -88384, 3328], [-27776, 143360, -50048], [3008, -52352, 114880]]) / 65536
_SRGB_A_XYZ = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                        [0.0193339, 0.1191920, 0.9503041]])


def _matriz_color(ccm=None):
    cam_a_xyz = _SRGB_A_XYZ @ (_CCM_C713 if ccm is None else ccm)
    return np.linalg.inv(cam_a_xyz)


def neutro_desde_jpg(ruta_raw, img, cfa):
    """Balance de la cámara: ajusta RAW (lineal) ↔ JPG hermano (sRGB linealizado) y devuelve el
    AsShotNeutral (respuesta de la cámara al blanco). None si no hay JPG o no alinea."""
    d, n = os.path.split(ruta_raw)
    ruta = os.path.join(d, n[:3] + '_' + n[4:8] + '.JPG')
    if not os.path.exists(ruta) or img.shape != (3264, 4320):
        return None
    from PIL import Image
    pos = {c: [(i // 2, i % 2) for i, ch in enumerate(cfa) if ch == c] for c in 'RGB'}
    a = img.astype(np.float64) / 1023
    canal = {c: np.mean([a[y::2, x::2] for y, x in pos[c]], axis=0) for c in 'RGB'}
    raw = np.dstack([canal['R'], canal['G'], canal['B']])
    def bloque(x, k):
        h, w = x.shape[0] // k * k, x.shape[1] // k * k
        return x[:h, :w].reshape(h // k, k, w // k, k, -1).mean(axis=(1, 3))
    mejor = None
    for rot in (0, -90, 90):
        s = np.asarray(Image.open(ruta).convert('RGB').rotate(rot, expand=True)).astype(np.float64) / 255
        if s.shape[:2] != (3216, 4288):
            continue
        lin = np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)
        jj = bloque(lin, 2)
        rr = raw[12:12 + jj.shape[0], 8:8 + jj.shape[1]]
        A, B = bloque(rr, 8).reshape(-1, 3), bloque(jj, 8).reshape(-1, 3)
        ok = (A.max(1) < 0.95) & (B.max(1) < 0.95) & (A.min(1) > 0.002)
        if ok.sum() < 500:
            continue
        c = np.corrcoef(A[ok, 1], B[ok, 1])[0, 1]
        if mejor is None or c > mejor[0]:
            mejor = (c, A[ok], B[ok])
    if mejor is None or mejor[0] < 0.9:
        return None
    M = np.linalg.lstsq(mejor[1], mejor[2], rcond=None)[0].T
    neutro = np.linalg.solve(M, np.ones(3))
    if np.any(neutro <= 0):
        return None
    return tuple(float(x) for x in neutro / neutro[1])


def orientacion_jpg(ruta_raw):
    """Orientación EXIF del JPG hermano (101O1970.RAW → 101_1970.JPG), 1 si no hay."""
    d, n = os.path.split(ruta_raw)
    for cand in (n[:3] + '_' + n[4:8] + '.JPG', n[:3] + '_' + n[4:8] + '.jpg'):
        try:
            from PIL import Image
            return int(Image.open(os.path.join(d, cand)).getexif().get(0x0112, 1))
        except Exception:
            continue
    return 1


def escribir_dng(ruta, img: np.ndarray, cfa: str, negro: int, blanco: int, recorte=None,
                 neutro=(0.5, 1.0, 0.7), orientacion=1, ccm=None):
    h, w = img.shape
    datos = img.astype('<u2').tobytes()
    entradas = []  # (tag, tipo, cuenta, valor_bytes)
    def tag(t, tipo, valores):
        fmt = {1: 'B', 2: 's', 3: 'H', 4: 'I', 5: 'II', 10: 'ii', 12: 'd'}[tipo]
        if tipo == 2:
            vb = valores.encode() + b'\0'; n = len(vb)
        elif tipo in (5, 10):
            vb = b''.join(struct.pack('<' + fmt, *v) for v in valores); n = len(valores)
        else:
            vb = struct.pack('<%d%s' % (len(valores), fmt), *valores); n = len(valores)
        entradas.append((t, tipo, n, vb))
    def rac(x, d=10000):
        return (int(round(x * d)), d)
    cx, cy, cw, ch = recorte or (0, 0, w, h)
    m = _matriz_color(ccm)
    tag(254, 4, [0]); tag(256, 4, [w]); tag(257, 4, [h]); tag(258, 3, [16]); tag(259, 3, [1])
    tag(262, 3, [32803]); tag(271, 2, 'Kodak'); tag(272, 2, 'EasyShare M531')
    tag(273, 4, [0]); tag(274, 3, [orientacion]); tag(277, 3, [1]); tag(278, 4, [h]); tag(279, 4, [len(datos)])
    tag(284, 3, [1]); tag(305, 2, 'm531raw.py')
    tag(33421, 3, [2, 2]); tag(33422, 1, list(_CFA[cfa]))
    tag(50706, 1, [1, 4, 0, 0]); tag(50707, 1, [1, 1, 0, 0]); tag(50708, 2, 'Kodak EasyShare M531')
    tag(50710, 1, [0, 1, 2]); tag(50711, 3, [1])
    tag(50714, 4, [int(negro)]); tag(50717, 4, [int(blanco)])
    tag(50719, 4, [cx, cy]); tag(50720, 4, [cw, ch])
    tag(50721, 10, [rac(v) for v in m.flatten()])
    tag(50728, 5, [rac(v) for v in neutro])
    tag(50778, 3, [21])
    entradas.sort(key=lambda e: e[0])
    n = len(entradas)
    ifd_off = 8
    extra_off = ifd_off + 2 + 12 * n + 4
    extra = bytearray()
    cuerpo = bytearray()
    datos_off = None
    # primera pasada para ubicar datos tras los valores largos
    largos = sum((len(e[3]) + 1) & ~1 for e in entradas if len(e[3]) > 4)
    datos_off = extra_off + largos
    datos_off = (datos_off + 15) & ~15
    for t, tipo, cnt, vb in entradas:
        if t == 273:
            vb = struct.pack('<I', datos_off)
        if len(vb) <= 4:
            cuerpo += struct.pack('<HHI', t, tipo, cnt) + vb.ljust(4, b'\0')
        else:
            cuerpo += struct.pack('<HHII', t, tipo, cnt, extra_off + len(extra))
            extra += vb
            if len(extra) % 2:
                extra += b'\0'
    with open(ruta, 'wb') as f:
        f.write(b'II*\0' + struct.pack('<I', ifd_off))
        f.write(struct.pack('<H', n) + cuerpo + struct.pack('<I', 0))
        f.write(extra)
        f.write(b'\0' * (datos_off - (extra_off + len(extra))))
        f.write(datos)


# ---------------------------------------------------------------- flujo
# Formato medido en la cámara real (2026-11-11, fotos 1968/1969): 4320×3264, u16 little-endian,
# 12 bits útiles, patrón con verdes en (0,0)/(1,1). Si el tamaño coincide, se usa directamente.
PERFILES = {
    28_200_960: dict(packing='u16_le', ancho=4320),            # modo de captura 3 (rompe el JPEG)
    14_100_480: dict(packing='u8', ancho=4320, decodificar=True),  # modo normal: 8 bits comprimidos
    # modo 4: contenedor de 12 bits empaquetado (orden lsb medido), datos de 10 bits lineales con el negro
    # ya restado (máximo 1020 en las fotos 1972–1974). El JPG de este modo sale con el color corrido:
    # el balance no se toma de él, sino de la propia escena (parche blanco) con reserva a un neutro fijo.
    21_150_720: dict(bits=12, ancho=4320, blanco=1023, negro=0, balance_jpg=False, neutro='modo4',
                     decodificar10=True),
    17_625_600: dict(bits=10, ancho=4320),  # modo 2: 10 bits empaquetado
}
# Patrón medido: GBRG (verdes en (0,0)/(1,1), azul en (0,1), rojo en (1,0)). La heurística "R es el más
# oscuro" daba GRBG; el ajuste RAW↔JPG de las fotos 1970/1971 lo corrigió (matriz diagonal con GBRG).
CFA_M531 = 'GBRG'
# CCM_M531 (más abajo): cámara balanceada → sRGB lineal, filas suman 1. Ajustada con las cinco fotos de
# modo 0 (1970, 1971, 1978–1980) por tools/ajustar_ccm.py (Huber, curva de tono por foto); dejando una
# escena fuera da ΔE2000 medio 2,92 contra 3,32 de la anterior (1970/1971) y 3,35 de la C713; detalle en
# firmware/stock/ccm_ajustada_v2.json. Reproduce el color del JPG de la cámara (incluye su saturación),
# no una carta de color: sigue pendiente refinarla con una carta.
# Balance fijo para modos cuyo JPG no sirve de referencia: media de los ajustes RAW↔JPG de 1970 y 1971
# (interior, luz cálida). Provisional.
NEUTRO_M531 = (0.7056, 1.0, 0.5292)
# Modo 4, balance de reserva: pares con flash 1976↔1978 y 1977↔1979, tras decodificar con la curva de
# 10 bits. Se usa si el balance por foto (parche blanco) no da un resultado creíble, o con --balance fijo.
NEUTRO_M531_MODO4 = (0.62, 1.0, 0.60)
# Lugar de los balances que elige la propia cámara: ganancias R/G/B del AWB guardadas en el MakerNote de
# 67 JPG de modo 0 (fotos 1900–1971). En log caen sobre una recta: ln(nB) = LOCUS_A + LOCUS_B·ln(nR),
# rms 0,028; el extremo cálido se aparta hasta 0,12. Un neutro estimado se acepta sólo si queda cerca.
LOCUS_A, LOCUS_B = -0.9243, -0.8826
LOCUS_TOL = 0.20                    # distancia máxima en ln(nB) a la recta
LOCUS_LN_R = (-0.74, 0.33)          # rango de ln(nR) visto en la cámara (−0,64…0,23) con 0,1 de margen
CCM_M531 = np.array([[1.73412, -0.7057, -0.02842], [-0.27821, 1.68179, -0.40358], [-0.08057, -0.50968, 1.59025]])
# Tabla del firmware (0x429c4c y copia en 0x42a24c, idéntica a la de la C713): código de 8 bits del RAW
# → valor lineal de 10 bits. El negro ya viene restado (mínimo 0). Justo antes está la tabla inversa.
DECODE_M531 = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 77, 78, 79, 80, 81, 82, 83, 85, 86, 87, 88, 90, 91, 92, 94, 95, 96, 98, 99, 100, 102, 103, 105, 106, 108, 109, 111, 113, 114, 116, 118, 119, 121, 123, 125, 126, 128, 130, 132, 134, 136, 138, 140, 142, 144, 146, 148, 150, 152, 154, 157, 159, 161, 164, 166, 168, 171, 173, 176, 178, 181, 183, 186, 189, 191, 194, 197, 200, 203, 206, 209, 212, 215, 218, 221, 224, 227, 231, 234, 237, 241, 244, 248, 251, 255, 259, 262, 266, 270, 274, 278, 282, 286, 290, 294, 298, 303, 307, 312, 316, 321, 325, 330, 335, 339, 344, 349, 354, 360, 365, 370, 375, 381, 386, 392, 397, 403, 409, 415, 421, 427, 433, 439, 446, 452, 459, 465, 472, 479, 486, 493, 500, 507, 514, 522, 529, 537, 545, 553, 560, 569, 577, 585, 594, 602, 611, 620, 629, 638, 647, 656, 666, 675, 685, 695, 705, 715, 725, 736, 746, 757, 768, 779, 790, 802, 813, 825, 837, 849, 861, 874, 886, 899, 912, 925, 939, 952, 966, 980, 994, 1008, 1023], dtype=np.uint16)


def analizar(rutas, bits=None, packing=None, ancho=None, layout=None, cfa=None, invertir=False):
    datos = [open(r, 'rb').read() for r in rutas]
    perfil = PERFILES.get(len(datos[0])) if packing is None and ancho is None and len(datos) == 1 else None
    if perfil:
        ancho = perfil['ancho']
        packing = perfil.get('packing')
        if packing is None:  # perfil con bits conocidos pero orden de empaquetado por detectar
            cands = [c for c in detectar_formato(datos[0]) if c['bits'] == perfil['bits']]
            packing = cands[0]['packing'] if cands else f"p{perfil['bits']}_msb"
    decodificar = bool(perfil and perfil.get('decodificar'))
    perfil_info = perfil or {}
    if perfil and cfa is None:
        cfa = CFA_M531
    if invertir:
        datos = datos[::-1]
    if packing is None:
        cands = detectar_formato(datos[0])
        if bits:
            cands = [c for c in cands if c['bits'] == bits] or cands
        if not cands:
            raise SystemExit('sin formato posible: archivo demasiado pequeño, truncado o constante (todos los bytes iguales)')
        elegido = cands[0]
        if not confiable(cands) and ancho is None:
            raise SystemExit(f"detección poco fiable (puntajes {[c['puntaje'] for c in cands[:2]]}): escena sin "
                             'estructura (plano, oscuro, ruido). Pasar --packing y --width sacados de una toma con detalle.')
        packing = elegido['packing']
        ancho = ancho or elegido['ancho']
    else:
        cands = []
        if ancho is None:
            c = [c for c in detectar_formato(datos[0]) if c['packing'] == packing]
            if not c:
                raise SystemExit(f'no se pudo detectar el ancho para {packing}; pasar --width')
            ancho = c[0]['ancho']
    campos = [a_imagen(d, packing, ancho) for d in datos]
    if decodificar:
        campos = [DECODE_M531[c] for c in campos]
    if perfil and perfil.get('decodificar10'):
        # Modo 4: la misma curva de compresión que el modo de 8 bits, con 10 bits de precisión
        # (código10 ≈ 4·código8). Verificado con pares modo0/modo4 de la misma escena: tras decodificar,
        # la relación entre modos pasa de pendiente log-log 0,68 a 0,89 y queda casi constante.
        xs = np.arange(256) * 4.0
        campos = [np.round(np.interp(c, xs, DECODE_M531.astype(np.float64))).astype(np.uint16) for c in campos]
    img, layout_usado = combinar(campos, layout)
    if img.shape[0] % 2:
        img = img[:-1]
    cfa_det, cfa_info = detectar_cfa(img)
    info = dict(archivos=[os.path.basename(r) for r in rutas], tamanos=[len(d) for d in datos],
                packing=packing, bits=BITS[packing], ancho=int(ancho), alto=int(img.shape[0]),
                layout=layout_usado, orden_campos='invertido' if invertir else 'O, b',
                cfa=cfa or cfa_det, cfa_detectado=cfa_det,
                cfa_rb_provisional=cfa is None,  # R vs B sale de "el más oscuro es R"; confirmar con toma real
                cfa_metricas={k: round(v, 5) for k, v in cfa_info.items()},
                candidatos=cands[:5], decodificado=decodificar,
                perfil={k: v for k, v in perfil_info.items() if k in ('blanco', 'negro', 'balance_jpg', 'neutro')})
    return img, info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('accion', choices=['info', 'dng'])
    ap.add_argument('archivos', nargs='+')
    ap.add_argument('-o', '--salida')
    ap.add_argument('--bits', type=int, choices=sorted(set(BITS.values())))
    ap.add_argument('--packing', choices=[p for p, _ in FORMATOS])
    ap.add_argument('--width', type=int)
    ap.add_argument('--layout', choices=['filas', 'pares', 'apilado'])
    ap.add_argument('--cfa', choices=list(_CFA))
    ap.add_argument('--black', type=int)
    ap.add_argument('--white', type=int)
    ap.add_argument('--matriz', choices=['m531', 'c713'], default='m531',
                    help='m531 = ajustada con cinco fotos reales (tools/ajustar_ccm.py); c713 = la de la C713')
    ap.add_argument('--balance', choices=['auto', 'fijo'], default='auto',
                    help='modo 4: auto = por foto (parche blanco, con reserva al fijo); fijo = neutro de flash')
    ap.add_argument('--invertir-campos', action='store_true', help='el orden de los campos no se detecta; usar si los colores salen cambiados')
    a = ap.parse_args()
    if len(a.archivos) > 2:
        sys.exit('máximo dos archivos (los dos campos de un disparo)')
    img, info = analizar(a.archivos, a.bits, a.packing, a.width, a.layout, a.cfa, a.invertir_campos)
    # Negro provisional: percentil bajo de la escena. Sobreestima si la escena no tiene negros puros;
    # el valor real sale del negro óptico de una toma real (o --black).
    negro = a.black if a.black is not None else int(np.percentile(img, 0.05))
    pf = info.get('perfil') or {}
    if info.get('decodificado'):
        negro = a.black if a.black is not None else 0   # el firmware ya restó el negro
        blanco = a.white if a.white is not None else 1023
    elif 'blanco' in pf:
        negro = a.black if a.black is not None else pf.get('negro', 0)
        blanco = a.white if a.white is not None else pf['blanco']
    elif a.white is not None:
        blanco = a.white
    elif info['bits'] == 16:
        # contenedor de 16 bits: el sensor da 12–14; usar los bits realmente ocupados
        blanco = (1 << max(int(img.max()).bit_length(), 12)) - 1
    else:
        blanco = (1 << info['bits']) - 1
    if not 0 <= negro < blanco:
        sys.exit(f'niveles inválidos: negro {negro}, blanco {blanco}')
    info['niveles_provisionales'] = a.black is None or a.white is None
    info.update(negro=negro, blanco=blanco)
    if a.accion == 'info':
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return
    if not a.salida:
        sys.exit('falta -o SALIDA.dng')
    usar_jpg = info.get('decodificado') and pf.get('balance_jpg', True)
    neutro = neutro_desde_jpg(a.archivos[0], img, info['cfa']) if usar_jpg else None
    if neutro:
        info['balance'] = 'jpg'
    elif pf.get('neutro') == 'modo4':
        # Balance por foto: lo más claro de la escena, aceptado sólo si cae cerca de los balances que la
        # cámara elige. Error medido contra el AWB de la cámara en 10 fotos (modo 0 y pares de modo 4):
        # media 8 %, peor 18 %. El JPG rosado y su AWB no sirven de referencia en este modo.
        neutro = None if a.balance == 'fijo' else neutro_parche_blanco(img, info['cfa'], negro, blanco)
        if neutro_creible(neutro):
            info['balance'] = 'parche_blanco'
        else:
            info['parche_blanco_descartado'] = None if neutro is None else [round(x, 4) for x in neutro]
            neutro, info['balance'] = NEUTRO_M531_MODO4, 'fijo_modo4'
    elif pf.get('balance_jpg') is False:
        neutro = neutro_parche_blanco(img, info['cfa'], negro, blanco)
        info['balance'] = 'parche_blanco' if neutro else 'fijo_m531'
        neutro = neutro or NEUTRO_M531
    else:
        neutro, info['balance'] = neutro_mundo_gris(img, info['cfa'], negro, blanco), 'mundo_gris'
    info['neutro'] = [round(x, 4) for x in neutro]
    info['awb_camara'] = awb_camara(a.archivos[0])
    info['matriz'] = a.matriz
    info['orientacion'] = orientacion_jpg(a.archivos[0])
    escribir_dng(a.salida, img, info['cfa'], negro, blanco, neutro=neutro, orientacion=info['orientacion'],
                 ccm=CCM_M531 if a.matriz == 'm531' else None)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == '__main__':
    main()
