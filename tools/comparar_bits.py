#!/usr/bin/env python3
"""¿Sirven los 12 bits lineales (M4L) frente al RAW de 8 bits con curva (P8, modo 0)? Medición con fotos reales.

uso: .venv/bin/python tools/comparar_bits.py

Lee los RAW de dump/ (fuera del repo) y deja en work/bits12/:
  reporte.json    todas las cifras
  sombras_*.png   recortes de sombras subidas +2/+3 EV, con y sin reducción de ruido
  balance_*.png   recortes con un balance de blancos extremo
  niveles.png     niveles por paso y escalón de P8 contra el ruido

Unidades: DN12 = cuentas del RAW lineal de 12 bits (M4L). El RAW de P8 decodificado está en cuentas de
10 bits; 1 cuenta = 4 DN12 (lo confirma la curva de ruido: misma varianza a la misma señal e ISO).

"P8 simulado" = el mosaico de una foto M4L pasado por la cuantización de P8 (÷4, código de 8 bits más
cercano en la tabla del firmware, decodificado, ×4). Misma escena, misma exposición y mismo ruido: lo
único que cambia es la profundidad de bits. Supone que la cámara codifica al código más cercano.
"""
import json
import os
import sys
from statistics import NormalDist

import numpy as np
from PIL import Image, ImageDraw

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import m531raw as m  # noqa: E402

SALIDA = os.path.join(RAIZ, 'work', 'bits12')
DUMP = os.path.join(RAIZ, 'dump')
P8 = ['raw8/101O1983', 'raw8/101O1984', 'raw8/101O1985', 'raw8/101O1986', 'raw10/101O1988', 'raw10/101O1989',
      'raw17/101O2010', 'raw17/101O2011']
M4L = ['raw13/101O1994', 'raw13/101O1995', 'raw18/101O2012', 'raw18/101O2013', 'raw18/101O2014', 'raw19/101O2015',
       'raw19/101O2016', 'raw19/101O2017', 'raw19/101O2018', 'raw20/101O2019', 'raw20/101O2020', 'raw20/101O2021']
TOPE = 4092            # 1023 × 4: fin de la escala de P8 en DN12
DEC12 = m.DECODE_M531.astype(np.float64) * 4      # código de 8 bits → DN12
_N = NormalDist()


def ruta(k):
    return os.path.join(DUMP, k + '.RAW')


def exif(k):
    r = ruta(k)
    j = os.path.join(os.path.dirname(r), os.path.basename(r)[:3] + '_' + os.path.basename(r)[4:8] + '.JPG')
    try:
        e = Image.open(j).getexif().get_ifd(0x8769)
        return dict(iso=int(e.get(0x8827)), flash=int(e.get(0x9209)) & 1, t=float(e.get(0x829a)))
    except Exception:
        return dict(iso=None, flash=None, t=None)


def cargar(k):
    """Mosaico en DN12 (float) y si es M4L."""
    img, info = m.analizar([ruta(k)])
    lineal = info['modo4'] == 'lineal12'
    return img.astype(np.float64) * (1 if lineal else 4), lineal


def codificar_p8(dn12):
    """DN12 → DN12 tras pasar por el código de 8 bits de P8 (código más cercano)."""
    x = np.clip(np.round(dn12 / 4), 0, 1023).astype(np.int64)
    d = m.DECODE_M531.astype(np.int64)
    cod = np.abs(np.arange(1024)[:, None] - d[None, :]).argmin(1)
    return DEC12[cod[x]]


def bloques(x, k):
    h, w = x.shape[0] // k * k, x.shape[1] // k * k
    return x[:h, :w].reshape(h // k, k, w // k, k)


def curva_ruido(v):
    """Curva de transferencia de fotones con los dos verdes de cada celda (su diferencia quita la escena).
    Devuelve K (DN12 por DN12 de señal), y pares (señal, sigma) por tramo."""
    g1, g2 = v[0::2, 0::2], v[1::2, 1::2]
    var = bloques(g1 - g2, 16).var((1, 3)) / 2
    mu = bloques((g1 + g2) / 2, 16).mean((1, 3))
    xs, ys = [], []
    for a, b in zip(np.linspace(40, 1600, 27)[:-1], np.linspace(40, 1600, 27)[1:]):
        q = (mu >= a) & (mu < b)
        if q.sum() > 50:
            xs.append(float(np.median(mu[q]))); ys.append(float(np.median(var[q])))
    K, a0 = (np.polyfit(xs, ys, 1) if len(xs) > 5 else (np.nan, np.nan))
    tramos = {}
    for a, b in [(10, 20), (20, 40), (40, 80), (80, 160), (160, 320), (320, 640), (640, 1280), (1280, 2560), (2560, 3800)]:
        q = (mu >= a) & (mu < b)
        if q.sum() > 30:
            tramos[f'{a}-{b}'] = round(float(np.sqrt(np.median(var[q]))), 1)
    return float(K), float(a0), tramos


def ruido_lectura(v, q):
    """Ruido en negro, en DN12. El firmware resta el negro y recorta en 0, así que en las zonas más oscuras
    sólo se ve la mitad positiva de la distribución. Por bloque de un canal: el cero recoge todo lo que cae
    bajo medio escalón (q/2; q = 1 en M4L, 4 en P8), así que con la fracción de ceros p0,
    (media − q/2)/sigma = −Φ⁻¹(p0), y la media de los valores positivos da sigma (normal truncada).
    Se usan los bloques con 35–65 % de ceros (casi sin fotones) y se devuelve la mediana. Comprobado con P8
    simulado desde M4L: sin el medio escalón el mismo ruido de 7,9 se leía como 11."""
    sig = []
    for y, x in ((0, 0), (1, 1), (1, 0), (0, 1)):
        b = bloques(v[y::2, x::2], 32).transpose(0, 2, 1, 3).reshape(-1, 1024)
        p0 = (b <= 0).mean(1)
        for fila, p in zip(b[(p0 > 0.35) & (p0 < 0.65)], p0[(p0 > 0.35) & (p0 < 0.65)]):
            z = -_N.inv_cdf(float(p))
            pos = fila[fila > 0]
            sig.append((pos.mean() - q / 2) / (z + _N.pdf(z) / _N.cdf(z)))
    return (float(np.median(sig)), len(sig)) if len(sig) >= 8 else (None, len(sig))


def recorte_alto(v, lineal):
    """Dónde satura: máximo, y nivel de la meseta más poblada del 1,5 % superior de la escala."""
    mx = float(v.max())
    h = np.bincount(v[v >= 3800].astype(np.int64), minlength=4097)
    meseta = int(h.argmax()) if h.sum() > 2000 else None
    return dict(maximo=mx, meseta=meseta, pixeles_sobre_3800=int(h.sum()))


def tabla_niveles(modelos):
    """Por paso bajo el tope: niveles distintos en P8 y en 12 bits, escalón de P8 y su peso frente al ruido."""
    filas = []
    niveles = np.unique(DEC12)
    for paso in range(12):
        hi, lo = TOPE / 2 ** paso, TOPE / 2 ** (paso + 1)
        en = niveles[(niveles > lo) & (niveles <= hi)]
        centro = (hi * lo) ** 0.5
        esc = float(np.median(np.diff(niveles)[(niveles[1:] > lo) & (niveles[1:] <= hi)])) if len(en) else None
        fila = dict(paso=f'-{paso} a -{paso + 1} EV', desde=round(lo, 1), hasta=round(hi, 1), niveles_p8=int(len(en)),
                    niveles_12b=int(np.floor(hi) - np.floor(lo)), escalon_p8_dn12=esc)
        for iso, (K, sr) in modelos.items():
            s = (sr ** 2 + K * centro) ** 0.5
            fila[f'sigma_iso{iso}'] = round(s, 1)
            if esc:
                fila[f'escalon_sobre_sigma_iso{iso}'] = round(esc / s, 2)
                fila[f'ruido_extra_p8_pct_iso{iso}'] = round(((1 + esc ** 2 / 12 / s ** 2) ** 0.5 - 1) * 100, 2)
        filas.append(fila)
    return filas


# ------------------------------------------------------------------ revelado para los recortes
def media_res(v):
    """Mosaico GBRG → RGB lineal a media resolución (sin interpolar)."""
    return np.dstack([v[1::2, 0::2], (v[0::2, 0::2] + v[1::2, 1::2]) / 2, v[0::2, 1::2]])


def suavizar(a, r=4):
    """Media móvil (2r+1)², por canal: una reducción de ruido fuerte y sin trucos."""
    k = 2 * r + 1
    p = np.pad(a, ((r + 1, r), (r + 1, r), (0, 0)), mode='edge').cumsum(0).cumsum(1)
    return (p[k:, k:] - p[:-k, k:] - p[k:, :-k] + p[:-k, :-k]) / k ** 2


def revelar(rgb, neutro, ev=0.0, blanco=3950.0):
    x = rgb / np.asarray(neutro) / blanco * 2 ** ev
    x = np.clip(x @ m.CCM_M531.T, 0, 1)
    s = np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)
    return (s * 255 + 0.5).astype(np.uint8)


def hoja(titulo, columnas, zoom=2):
    """columnas: [(rótulo, imagen uint8)]. Devuelve una PIL con los recortes lado a lado."""
    h, w = columnas[0][1].shape[:2]
    lienzo = Image.new('RGB', (len(columnas) * (w * zoom + 6) + 6, h * zoom + 44), (24, 24, 24))
    d = ImageDraw.Draw(lienzo)
    d.text((6, 4), titulo, fill=(255, 255, 255))
    for i, (rot, im) in enumerate(columnas):
        x = 6 + i * (w * zoom + 6)
        lienzo.paste(Image.fromarray(im).resize((w * zoom, h * zoom), Image.NEAREST), (x, 40))
        d.text((x, 22), rot, fill=(255, 220, 120))
    return lienzo


def zona_oscura(rgb, alto=200, ancho=300):
    """Ventana con menos señal que no esté pegada a 0: la más oscura con mediana de G ≥ 12 DN12."""
    g = rgb[..., 1]
    mejor = None
    for y in range(0, g.shape[0] - alto, 50):
        for x in range(0, g.shape[1] - ancho, 50):
            med = np.median(g[y:y + alto:4, x:x + ancho:4])
            if med >= 12 and (mejor is None or med < mejor[0]):
                mejor = (float(med), y, x)
    return mejor


def comparar_escena(k, neutro, reporte):
    """M4L contra su versión P8 simulada: error por paso, sesgo tras promediar y recortes."""
    v, _ = cargar(k)
    sim = codificar_p8(v)
    num = k[-4:]
    filas = []
    dif = sim - v
    for paso in range(11):
        hi, lo = TOPE / 2 ** paso, TOPE / 2 ** (paso + 1)
        q = (v > lo) & (v <= hi)
        if q.sum() < 5000:
            continue
        # sesgo tras promediar 16×16 del mismo canal: lo que queda de la cuantización cuando el ruido ya no tapa
        filas.append(dict(paso=f'-{paso} a -{paso + 1} EV', pixeles=int(q.sum()),
                          error_rms_dn12=round(float(np.sqrt((dif[q] ** 2).mean())), 2),
                          sesgo_medio_dn12=round(float(dif[q].mean()), 3)))
    g_v = bloques((v[0::2, 0::2] + v[1::2, 1::2]) / 2, 16).mean((1, 3))
    g_s = bloques((sim[0::2, 0::2] + sim[1::2, 1::2]) / 2, 16).mean((1, 3))
    sesgo = {}
    for a, b in [(8, 32), (32, 128), (128, 512), (512, 2048), (2048, 3900)]:
        q = (g_v >= a) & (g_v < b)
        if q.sum() > 50:
            sesgo[f'{a}-{b}'] = dict(bloques=int(q.sum()), rms_dn12=round(float(np.sqrt(((g_s - g_v)[q] ** 2).mean())), 3),
                                     rms_relativo_pct=round(float(np.sqrt((((g_s - g_v) / g_v)[q] ** 2).mean())) * 100, 3))
    a, b = media_res(v), media_res(sim)
    med, y, x = zona_oscura(a)
    rec = (slice(y, y + 200), slice(x, x + 300))
    ev = min(5.0, float(np.log2(0.18 * 3950 / max(med, 1))))     # lleva la sombra a gris medio
    cols = [(f'M4L +{e:.1f} EV', revelar(a[rec], neutro, e)) for e in (2.0, 3.0)] + \
           [(f'P8 simulado +{e:.1f} EV', revelar(b[rec], neutro, e)) for e in (2.0, 3.0)]
    hoja(f'{num}: sombra (G mediana {med:.0f} DN12) subida', cols).save(os.path.join(SALIDA, f'sombras_{num}.png'))
    sa, sb = suavizar(a), suavizar(b)
    cols = [(f'M4L +{ev:.1f} EV', revelar(a[rec], neutro, ev)), (f'P8 sim. +{ev:.1f} EV', revelar(b[rec], neutro, ev)),
            ('M4L suavizado 9x9', revelar(sa[rec], neutro, ev)), ('P8 sim. suavizado 9x9', revelar(sb[rec], neutro, ev))]
    hoja(f'{num}: la misma sombra a gris medio (+{ev:.1f} EV), con y sin reducción de ruido', cols).save(
        os.path.join(SALIDA, f'sombras_nr_{num}.png'))
    # balance extremo: como si la luz fuera mucho más cálida (azul ×2,5 más y rojo ×0,6) sobre la foto entera
    ext = (neutro[0] / 0.6, 1.0, neutro[2] / 2.5)
    yy, xx = a.shape[0] // 2 - 250, a.shape[1] // 2 - 375
    cen = (slice(yy, yy + 500), slice(xx, xx + 750))
    cols = [('M4L', revelar(sa[cen], ext, 1.0)), ('P8 simulado', revelar(sb[cen], ext, 1.0))]
    hoja(f'{num}: balance extremo (B x2,5, R x0,6), +1 EV, suavizado 9x9', cols, zoom=1).save(
        os.path.join(SALIDA, f'balance_{num}.png'))
    # ¿se ve alguna diferencia en 8 bits de salida? Fracción de píxeles que cambian más de 2/255 tras suavizar
    d8 = np.abs(revelar(sa, neutro, ev).astype(int) - revelar(sb, neutro, ev).astype(int)).max(-1)
    d8x = np.abs(revelar(sa, ext, 1.0).astype(int) - revelar(sb, ext, 1.0).astype(int)).max(-1)
    reporte[num] = dict(error_por_paso=filas, sesgo_tras_promediar_16x16=sesgo, zona_oscura=dict(y=y, x=x, mediana_g=med, ev=round(ev, 2)),
                        salida_8bit_suavizada=dict(sombras_dif_media=round(float(d8.mean()), 3), sombras_dif_p99=int(np.percentile(d8, 99)),
                                                   sombras_dif_max=int(d8.max()), balance_extremo_dif_media=round(float(d8x.mean()), 3),
                                                   balance_extremo_dif_p99=int(np.percentile(d8x, 99)), balance_extremo_dif_max=int(d8x.max())))


def margen_sobre_jpg(k):
    """Cuánto queda en el RAW por encima de donde el JPG de la cámara ya está en blanco (EV), y qué parte de
    lo que el JPG quema sigue sin saturar en el RAW."""
    r = ruta(k)
    j = os.path.join(os.path.dirname(r), os.path.basename(r)[:3] + '_' + os.path.basename(r)[4:8] + '.JPG')
    v, lineal = cargar(k)
    blanco = 3950 if lineal else TOPE * 0.97
    rgb = media_res(v)[12:-12, 8:-8]
    jpg = np.asarray(Image.open(j).convert('RGB'))
    if jpg.shape[0] > jpg.shape[1]:
        jpg = np.rot90(jpg, -1)          # la cámara guarda el JPG girado 90° a la izquierda
    jm = bloques(jpg.max(-1).astype(np.float64), 2).min((1, 3))          # las 4 muestras del JPG quemadas
    quemado = jm >= 254
    if quemado.mean() < 0.0005:
        return None
    rmax = rgb.max(-1)
    recuperable = quemado & (rmax < blanco)
    borde = (bloques(jpg.max(-1).astype(np.float64), 2).mean((1, 3)) >= 250) & ~quemado & (rmax < blanco)
    return dict(jpg_quemado_pct=round(float(quemado.mean()) * 100, 2),
                de_eso_sin_saturar_en_raw_pct=round(float(recuperable.sum() / quemado.sum()) * 100, 1),
                raw_donde_el_jpg_llega_a_blanco_dn12=round(float(np.median(rmax[borde])), 0) if borde.sum() > 200 else None,
                margen_ev=round(float(np.log2(blanco / np.median(rmax[borde]))), 2) if borde.sum() > 200 else None)


def grafico_niveles(filas, destino):
    """Gráfico simple (PIL): escalón de P8 y sigma por paso, en escala logarítmica."""
    W, H, m0 = 900, 420, 60
    im = Image.new('RGB', (W, H), (255, 255, 255)); d = ImageDraw.Draw(im)
    def y(val):
        return H - m0 - (np.log2(max(val, 0.5)) + 1) / 8 * (H - 2 * m0)
    n = len(filas)
    for e in range(-1, 8):
        d.line([(m0, y(2.0 ** e)), (W - 20, y(2.0 ** e))], fill=(225, 225, 225)); d.text((8, y(2.0 ** e) - 6), f'{2.0 ** e:g}', fill=(0, 0, 0))
    series = [('escalon_p8_dn12', (200, 30, 30), 'escalón de P8'), ('sigma_iso64', (30, 90, 200), 'ruido ISO 64'),
              ('sigma_iso160', (30, 160, 90), 'ruido ISO 160')]
    for clave, color, _ in series:
        pts = [(m0 + (i + 0.5) * (W - m0 - 20) / n, y(f[clave])) for i, f in enumerate(filas) if f.get(clave)]
        d.line(pts, fill=color, width=3)
        for p in pts:
            d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=color)
    d.line([(m0, y(1)), (W - 20, y(1))], fill=(120, 120, 120), width=2)
    for i, f in enumerate(filas):
        d.text((m0 + (i + 0.5) * (W - m0 - 20) / n - 8, H - m0 + 6), f"-{i}", fill=(0, 0, 0))
    d.text((m0, H - 24), 'paso bajo el tope del RAW (EV). Eje vertical: DN12. Línea gris: escalón de 12 bits (1 DN12).', fill=(0, 0, 0))
    for i, (_, color, nombre) in enumerate(series):
        d.text((m0 + 10 + i * 170, 10), nombre, fill=color)
    im.save(destino)


def main():
    faltan = [k for k in P8 + M4L if not os.path.exists(ruta(k))]
    if faltan:
        sys.exit(f'faltan fotos de dump/: {faltan[:3]}…')
    os.makedirs(SALIDA, exist_ok=True)
    rep = dict(unidades='DN12 = cuentas del RAW lineal de 12 bits; P8 decodificado × 4', archivos={})
    por_iso = {}
    for k in P8 + M4L:
        v, lineal = cargar(k)
        e = exif(k)
        K, a0, tramos = curva_ruido(v)
        sr, n = ruido_lectura(v, 1 if lineal else 4)
        fila = dict(modo='M4L' if lineal else 'P8', **e, K=round(K, 3), sigma_por_tramo=tramos,
                    ruido_negro_dn12=None if sr is None else round(sr, 2), bloques_negros=n,
                    ceros_pct=round(float((v <= 0).mean()) * 100, 2), **recorte_alto(v, lineal))
        if not lineal:
            crudo = np.frombuffer(open(ruta(k), 'rb').read(), dtype=np.uint8)
            fila['codigos_usados'] = int(len(np.unique(crudo)))
        else:
            fila['valores_distintos'] = int(len(np.unique(v)))
            fila['margen_sobre_jpg'] = margen_sobre_jpg(k)
        rep['archivos'][k[-4:]] = fila
        # el flash no cambia el ruido, pero las tomas con mucho quemado (2013, 2017–2019) tuercen el ajuste de K
        if sr is not None and e['iso'] in (64, 160) and 0.5 < K / (e['iso'] / 64) < 1.6:
            por_iso.setdefault((fila['modo'], e['iso']), []).append((K, sr))
        print(k[-4:], fila['modo'], f"ISO {e['iso']}", f"K={K:.2f}", f"negro σ={sr and round(sr, 1)} ({n} bloques)",
              f"máx {fila['maximo']:.0f} meseta {fila['meseta']}", f"ceros {fila['ceros_pct']} %")
    rep['modelo_ruido'] = {f'{modo}_iso{iso}': dict(K=round(float(np.median([x[0] for x in v])), 3),
                                                   ruido_negro_dn12=round(float(np.median([x[1] for x in v])), 2), fotos=len(v))
                           for (modo, iso), v in sorted(por_iso.items())}
    modelos = {iso: (rep['modelo_ruido'][f'M4L_iso{iso}']['K'], rep['modelo_ruido'][f'M4L_iso{iso}']['ruido_negro_dn12'])
               for iso in (64, 160) if f'M4L_iso{iso}' in rep['modelo_ruido']}
    rep['niveles_por_paso'] = tabla_niveles(modelos)
    rep['rango_dinamico'] = {}
    for iso, (K, sr) in modelos.items():
        q = 4.0   # escalón de P8 en sombras
        sr_p8 = (sr ** 2 + q ** 2 / 12) ** 0.5
        sr_12 = (sr ** 2 + 1 / 12) ** 0.5
        rep['rango_dinamico'][f'iso{iso}'] = dict(
            tope_dn12=3950, ruido_negro_dn12=sr,
            snr1_m4l_ev=round(float(np.log2(3950 / sr_12)), 2), snr1_p8_ev=round(float(np.log2(3950 / sr_p8)), 2),
            diferencia_ev=round(float(np.log2(sr_p8 / sr_12)), 3),
            bits_bajo_el_ruido_en_12b=round(float(np.log2(sr)), 1))
    grafico_niveles(rep['niveles_por_paso'], os.path.join(SALIDA, 'niveles.png'))
    rep['m4l_contra_p8_simulado'] = {}
    # 1995: ISO 64, sin flash. 2020: ISO 160, tungsteno (el balance ya pide azul × 3,2). 2016: ISO 64, flash, sombras hondas.
    for k, neutro in (('raw13/101O1995', (0.62, 1.0, 0.60)), ('raw20/101O2020', (1.02, 1.0, 0.357)),
                      ('raw19/101O2016', (0.675, 1.0, 0.573))):
        comparar_escena(k, neutro, rep['m4l_contra_p8_simulado'])
        print('recortes', k[-4:], rep['m4l_contra_p8_simulado'][k[-4:]]['salida_8bit_suavizada'])
    # P8 real contra M4L real, misma luz e ISO (1986 y 2020: tungsteno, ISO 160, sin flash): sombra a gris medio
    cols = []
    for k, neutro in (('raw8/101O1986', (1.03, 1.0, 0.348)), ('raw20/101O2020', (1.02, 1.0, 0.357))):
        v, lineal = cargar(k)
        a = media_res(v)
        med, y, x = zona_oscura(a)
        ev = float(np.log2(0.18 * 3950 / med))
        rec = (slice(y, y + 200), slice(x, x + 300))
        cols += [(f"{'M4L' if lineal else 'P8'} {k[-4:]} +{ev:.1f} EV", revelar(a[rec], neutro, ev)),
                 (f"{'M4L' if lineal else 'P8'} {k[-4:]} suavizado", revelar(suavizar(a)[rec], neutro, ev))]
    hoja('P8 real (1986) y M4L real (2020), ISO 160, tungsteno: sombra a gris medio', cols).save(os.path.join(SALIDA, 'sombras_reales_p8_m4l.png'))
    json.dump(rep, open(os.path.join(SALIDA, 'reporte.json'), 'w'), indent=1, ensure_ascii=False)
    print('modelo de ruido:', rep['modelo_ruido'])
    print('rango dinámico:', rep['rango_dinamico'])
    print('reporte:', os.path.join(SALIDA, 'reporte.json'))


if __name__ == '__main__':
    main()
