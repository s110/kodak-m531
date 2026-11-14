#!/usr/bin/env python3
"""Conversor RAW → DNG de la M531 con interfaz en el navegador (sólo local).

uso:  ./conversor          abre la página (si ya está abierto, sólo vuelve a mostrarla)
      ./conversor --destino DIR --origen DCIM --copias DIR --puerto N --no-abrir   (pruebas)

- Arrastrar RAW (con sus JPG, o una carpeta entera) a la página: cada RAW se convierte a DNG en
  <destino>/<fecha de hoy>/, con su JPG al lado, igual que ./importar.
- "Importar de la SD": corre ./importar (copia verificada con SHA-256 + DNG) y muestra lo nuevo.
- Cada foto: vista previa del DNG (render de macOS con sips), girar, abrir en Vista Previa/darktable.

Escucha sólo en 127.0.0.1 y cada llamada lleva un token aleatorio de la sesión (otra página web no
puede usarla). Se cierra sola tras 10 minutos sin la página abierta. Nunca escribe en la SD.
"""
import argparse
import concurrent.futures as cf
import contextlib
import datetime
import hashlib
import http.server
import io
import json
import multiprocessing
import os
import re
import secrets
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import m531raw  # noqa: E402
import importar_sd  # noqa: E402

ESTADO = os.path.expanduser('~/Library/Caches/m531_conversor.json')
RE_ARCHIVO = re.compile(r'(\d{3})([Ob_])(\d{4})\.(RAW|JPG)', re.I)
MAX_SUBIDA = 64 << 20
INACTIVO = 600                      # s sin peticiones → se cierra
_TAG_A_GIRO = {v: k for k, v in m531raw._ETIQUETA_GIRO.items()}


# ---------------------------------------------------------------- trabajo (en procesos aparte)
def convertir_uno(campos, dng, jpg, jpg_destino, balance, rotar):
    """Convierte un disparo. Escribe primero <dng>.parcial para que un fallo no deje un DNG a medias.
    Devuelve el resumen para la página."""
    giro_n = rotar
    try:
        info = m531raw.convertir(campos, dng + '.parcial', balance=balance, rotar=giro_n)
        os.replace(dng + '.parcial', dng)
    except BaseException as e:      # SystemExit con el motivo, o cualquier error de lectura
        with contextlib.suppress(FileNotFoundError):
            os.remove(dng + '.parcial')
        return dict(ok=False, error=str(e)[-300:] or e.__class__.__name__)
    con_jpg = False
    if jpg and os.path.getsize(jpg) > 10_000:
        try:
            from PIL import Image
            Image.open(jpg).load()                      # el JPG puede venir truncado (disparo encima)
            shutil.copy2(jpg, jpg_destino)
            m531raw.orientar(jpg_destino, info['giro'])
            con_jpg = True
        except Exception:
            pass
    return dict(ok=True, formato=importar_sd.descripcion(info), balance=info['balance'], giro=info['giro'],
                jpg=con_jpg)


def leer_giro(ruta):
    """Cuartos de vuelta a la izquierda que muestra hoy un DNG (lee su etiqueta Orientation)."""
    with open(ruta, 'rb') as f:
        cab = f.read(8)
        orden = {b'II': '<', b'MM': '>'}[cab[:2]]
        f.seek(struct.unpack(orden + 'I', cab[4:8])[0])
        n = struct.unpack(orden + 'H', f.read(2))[0]
        for _ in range(n):
            e = f.read(12)
            if struct.unpack(orden + 'H', e[:2])[0] == 0x0112:
                return _TAG_A_GIRO.get(struct.unpack(orden + 'H', e[8:10])[0], 0)
    return 0


# ---------------------------------------------------------------- servidor
class Conversor:
    def __init__(self, a):
        self.destino = os.path.realpath(os.path.expanduser(a.destino))
        self.origen = a.origen
        self.copias = a.copias
        self.token = secrets.token_urlsafe(24)
        self.entrada = tempfile.mkdtemp(prefix='m531_entrada_')
        self.cache = tempfile.mkdtemp(prefix='m531_vistas_')
        self.pool = cf.ProcessPoolExecutor(max_workers=min(4, os.cpu_count() or 2),
                                           mp_context=multiprocessing.get_context('spawn'))
        self.ultimo = time.monotonic()
        self.cerrojo = threading.Lock()
        self.imp = dict(corriendo=False, lineas=[], dngs=[], codigo=None)

    def fecha(self):
        return datetime.date.today().isoformat()

    def dentro(self, rel):
        """Ruta relativa al destino → absoluta, o None si se sale de él."""
        p = os.path.realpath(os.path.join(self.destino, rel))
        return p if os.path.commonpath([p, self.destino]) == self.destino and p != self.destino else None

    def ficha(self, dng, extra=None):
        rel = os.path.relpath(dng, self.destino)
        d = dict(dng=rel, nombre=os.path.basename(dng), v=int(os.path.getmtime(dng)), giro=leer_giro(dng),
                 jpg=os.path.exists(dng[:-4] + '.JPG'))
        d.update(extra or {})
        return d

    # --- acciones
    def subir(self, nombre, datos):
        m = RE_ARCHIVO.fullmatch(nombre)
        if not m:
            raise ValueError(f'{nombre}: no es un archivo de la M531 (101O####.RAW / 101_####.JPG)')
        if not datos:
            raise ValueError(f'{nombre}: archivo vacío')
        final = os.path.join(self.entrada, ''.join(m.groups()[:3]).upper() + '.' + m.group(4).upper())
        with open(final + '.tmp', 'wb') as f:
            f.write(datos)
        os.replace(final + '.tmp', final)
        return dict(ok=True)

    def convertir(self, nombre, balance, rotar):
        m = RE_ARCHIVO.fullmatch(nombre or '')
        if not m or m.group(2).upper() != 'O' or m.group(4).upper() != 'RAW':
            raise ValueError('falta el RAW 101O####.RAW')
        pre, _, num, _ = m.groups()
        campos = [os.path.join(self.entrada, f'{pre}O{num}.RAW')]
        if not os.path.exists(campos[0]):
            raise ValueError(f'{nombre}: no se subió')
        if os.path.exists(os.path.join(self.entrada, f'{pre}B{num}.RAW')):
            campos.append(os.path.join(self.entrada, f'{pre}B{num}.RAW'))
        salida = os.path.join(self.destino, self.fecha())
        os.makedirs(salida, exist_ok=True)
        dng = os.path.join(salida, f'{pre}_{num}.DNG')
        jpg = os.path.join(self.entrada, f'{pre}_{num}.JPG')
        r = self.pool.submit(convertir_uno, campos, dng, jpg if os.path.exists(jpg) else None,
                             dng[:-4] + '.JPG', balance, rotar).result()
        if not r.pop('ok'):
            return dict(ok=False, nombre=nombre, error=r['error'])
        return dict(ok=True, **self.ficha(dng, r))

    def girar(self, rel, sentido):
        dng = self.dentro(rel)
        if not dng or not dng.upper().endswith('.DNG') or not os.path.exists(dng):
            raise ValueError('DNG no encontrado')
        g = (leer_giro(dng) + (1 if sentido == 'izq' else -1)) % 4
        m531raw.orientar(dng, g)
        jpg = dng[:-4] + '.JPG'
        if os.path.exists(jpg):
            m531raw.orientar(jpg, g)
        os.utime(dng)                                   # cambia la versión de la vista previa
        return dict(ok=True, **self.ficha(dng))

    def vista(self, rel, que, tam=900):
        ruta = self.dentro(rel)
        if ruta and que == 'jpg':
            ruta = ruta[:-4] + '.JPG'
        if not ruta or not ruta.upper().endswith(('.DNG', '.JPG')) or not os.path.exists(ruta):
            return None
        st = os.stat(ruta)
        tam = 2400 if tam > 900 else 900
        clave = hashlib.sha1(f'{ruta}|{st.st_mtime_ns}|{st.st_size}|{tam}'.encode()).hexdigest()
        out = os.path.join(self.cache, clave + '.jpg')
        if not os.path.exists(out):
            p = subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '82', '-Z', str(tam),
                                ruta, '--out', out + '.tmp.jpg'], capture_output=True)
            if p.returncode or not os.path.exists(out + '.tmp.jpg'):
                return None
            if ruta.upper().endswith('.DNG'):
                # sips revela el DNG sin aplicar su etiqueta Orientation (Vista Previa y Quick Look sí):
                # se gira aquí para que la vista muestre lo mismo que abrirá el visor.
                g = leer_giro(ruta)
                if g:
                    from PIL import Image
                    Image.open(out + '.tmp.jpg').rotate(90 * g, expand=True).save(out + '.tmp.jpg', quality=85)
            os.replace(out + '.tmp.jpg', out)
        with open(out, 'rb') as f:
            return f.read()

    def abrir(self, que, rel):
        ruta = self.dentro(rel) if rel else os.path.join(self.destino, self.fecha())
        if not ruta or not os.path.exists(ruta):
            ruta = self.destino
        os.makedirs(ruta, exist_ok=True)
        cmd = {'finder': ['open', '-R', ruta] if os.path.isfile(ruta) else ['open', ruta],
               'vista': ['open', '-a', 'Preview', ruta],
               'darktable': ['open', '-a', 'darktable', ruta]}.get(que)
        if not cmd:
            raise ValueError('acción desconocida')
        p = subprocess.run(cmd, capture_output=True, text=True)
        return dict(ok=p.returncode == 0, error=p.stderr.strip())

    def sd(self):
        hay = os.path.isdir(self.origen)
        n = 0
        if hay:
            with contextlib.suppress(OSError):
                n = sum(1 for x in os.listdir(self.origen) if x.upper().endswith('.RAW') and not x.startswith('.'))
        return dict(sd=hay, sd_raw=n, destino=self.destino, fecha=self.fecha(), importando=self.imp['corriendo'])

    def importar(self, balance, rotar):
        with self.cerrojo:
            if self.imp['corriendo']:
                raise ValueError('ya hay una importación en curso')
            self.imp = dict(corriendo=True, lineas=[], dngs=[], codigo=None)
        antes = self._dngs()
        args = ['--origen', self.origen, '--destino', self.destino, '--balance', balance, '--rotar', rotar]
        if self.copias:
            args += ['--copias', self.copias]

        imp = self.imp

        class Lineas(io.TextIOBase):
            def write(self, s):
                imp['lineas'].extend(x for x in s.splitlines() if x.strip())
                return len(s)

        def correr():
            try:
                with contextlib.redirect_stdout(Lineas()):
                    imp['codigo'] = importar_sd.main(args)
            except BaseException as e:
                imp['lineas'].append(f'ERROR: {e}')
                imp['codigo'] = 1
            nuevos = sorted(set(self._dngs()) - set(antes))
            fichas, resumenes = [], {}
            for d in nuevos:
                carpeta = os.path.dirname(d)
                if carpeta not in resumenes:             # formato y balance que dejó ./importar
                    try:
                        resumenes[carpeta] = {x['raw'][:3] + '_' + x['raw'][4:8]: x
                                              for x in json.load(open(os.path.join(carpeta, 'resumen.json')))}
                    except Exception:
                        resumenes[carpeta] = {}
                r = resumenes[carpeta].get(os.path.basename(d)[:8], {})
                with contextlib.suppress(Exception):
                    fichas.append(self.ficha(d, {k: r[k] for k in ('formato', 'balance') if k in r}))
            imp['dngs'] = fichas
            imp['corriendo'] = False
        threading.Thread(target=correr, daemon=True).start()
        return dict(ok=True)

    def _dngs(self):
        out = []
        if os.path.isdir(self.destino):
            for d in os.listdir(self.destino):
                c = os.path.join(self.destino, d)
                if os.path.isdir(c):
                    out += [os.path.join(c, n) for n in os.listdir(c) if n.upper().endswith('.DNG')]
        return out

    def expulsar(self):
        vol = os.path.dirname(os.path.dirname(os.path.realpath(self.origen)))
        if not os.path.ismount(vol) or vol == '/':
            raise ValueError('la SD no está montada')
        p = subprocess.run(['diskutil', 'eject', vol], capture_output=True, text=True)
        return dict(ok=p.returncode == 0, error=(p.stderr or p.stdout).strip())


def manejador(c: Conversor, puerto_ref):
    html = open(os.path.join(AQUI, 'conversor_ui.html'), encoding='utf-8').read().replace('__TOKEN__', c.token)

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _host_ok(self):
            return self.headers.get('Host', '') in (f'127.0.0.1:{puerto_ref[0]}', f'localhost:{puerto_ref[0]}')

        def _enviar(self, codigo, cuerpo, tipo='application/json'):
            if isinstance(cuerpo, (dict, list)):
                cuerpo = json.dumps(cuerpo, ensure_ascii=False).encode()
            elif isinstance(cuerpo, str):
                cuerpo = cuerpo.encode()
            self.send_response(codigo)
            self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(len(cuerpo)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(cuerpo)

        def _autorizado(self, q):
            t = self.headers.get('X-Token') or q.get('t', [''])[0]
            return self._host_ok() and secrets.compare_digest(t, c.token)

        def do_GET(self):
            c.ultimo = time.monotonic()
            u = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not self._host_ok():
                return self._enviar(403, {'error': 'host'})
            if u.path == '/':
                return self._enviar(200, html, 'text/html; charset=utf-8')
            if not self._autorizado(q):
                return self._enviar(403, {'error': 'token'})
            if u.path == '/api/estado':
                return self._enviar(200, c.sd())
            if u.path == '/api/importar':
                return self._enviar(200, c.imp)
            if u.path == '/api/vista':
                datos = c.vista(q.get('dng', [''])[0], q.get('que', ['dng'])[0],
                                int(q.get('tam', ['900'])[0]) if q.get('tam', ['900'])[0].isdigit() else 900)
                return self._enviar(200, datos, 'image/jpeg') if datos else self._enviar(404, {'error': 'sin vista'})
            self._enviar(404, {'error': 'no existe'})

        def do_POST(self):
            c.ultimo = time.monotonic()
            u = urllib.parse.urlsplit(self.path)
            if not self._autorizado(urllib.parse.parse_qs(u.query)):
                return self._enviar(403, {'error': 'token'})
            largo = int(self.headers.get('Content-Length') or 0)
            if largo > MAX_SUBIDA:
                return self._enviar(413, {'error': 'archivo demasiado grande'})
            datos = self.rfile.read(largo)
            try:
                if u.path == '/api/subir':
                    r = c.subir(urllib.parse.unquote(self.headers.get('X-Nombre', '')), datos)
                else:
                    j = json.loads(datos or b'{}')
                    bal = j.get('balance', 'auto') if j.get('balance') in ('auto', 'camara') else 'auto'
                    rot = j.get('rotar', 'no') if j.get('rotar') in ('no', 'camara') else 'no'
                    r = {'/api/convertir': lambda: c.convertir(j.get('nombre'), bal, rot),
                         '/api/girar': lambda: c.girar(j.get('dng', ''), j.get('sentido')),
                         '/api/abrir': lambda: c.abrir(j.get('que'), j.get('dng')),
                         '/api/importar': lambda: c.importar(bal, rot),
                         '/api/expulsar': c.expulsar}.get(u.path)
                    if r is None:
                        return self._enviar(404, {'error': 'no existe'})
                    r = r()
                self._enviar(200, r)
            except ValueError as e:
                self._enviar(400, {'ok': False, 'error': str(e)})
            except Exception as e:
                self._enviar(500, {'ok': False, 'error': f'{e.__class__.__name__}: {e}'})
    return H


def ya_abierto():
    """URL del conversor que ya corre, o None."""
    try:
        e = json.load(open(ESTADO))
        r = urllib.request.Request(f"http://127.0.0.1:{e['puerto']}/api/estado", headers={'X-Token': e['token']})
        with urllib.request.urlopen(r, timeout=1.5) as resp:
            if resp.status == 200:
                return f"http://127.0.0.1:{e['puerto']}/"
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--destino', default=os.path.expanduser('~/Pictures/m531_dng'))
    ap.add_argument('--origen', default=importar_sd.ORIGEN, help='carpeta DCIM de la SD')
    ap.add_argument('--copias', help='dónde guarda ./importar las copias verificadas (por omisión dump/ de la repo)')
    ap.add_argument('--puerto', type=int, default=8531, help='0 = cualquiera libre')
    ap.add_argument('--no-abrir', action='store_true', help='no abrir el navegador (pruebas)')
    ap.add_argument('--estado', default=ESTADO, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    if a.estado == ESTADO and not a.no_abrir:
        url = ya_abierto()
        if url:
            subprocess.run(['open', url])
            return 0
    c = Conversor(a)
    puerto = [0]
    try:
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', a.puerto), manejador(c, puerto))
    except OSError:
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), manejador(c, puerto))
    puerto[0] = srv.server_address[1]
    os.makedirs(os.path.dirname(a.estado), exist_ok=True)
    fd = os.open(a.estado, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(dict(puerto=puerto[0], token=c.token, pid=os.getpid()), f)
    url = f'http://127.0.0.1:{puerto[0]}/'
    print(f'Conversor M531 en {url}  (Ctrl-C para cerrar)', flush=True)

    def vigilar():
        while True:
            time.sleep(15)
            if time.monotonic() - c.ultimo > INACTIVO and not c.imp['corriendo']:
                srv.shutdown()
                return
    threading.Thread(target=vigilar, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    if not a.no_abrir:
        subprocess.Popen(['open', url])
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        c.pool.shutdown(cancel_futures=True)
        shutil.rmtree(c.entrada, ignore_errors=True)
        shutil.rmtree(c.cache, ignore_errors=True)
        with contextlib.suppress(Exception):
            if json.load(open(a.estado)).get('pid') == os.getpid():
                os.remove(a.estado)
    return 0


if __name__ == '__main__':
    sys.exit(main())
