// Worker: aquí corre todo lo pesado (leer los archivos, convertir, revelar la vista previa, CRC del
// .zip) para que la página no se trabe. Los archivos se leen del disco del usuario y no salen de aquí.
import { camara } from './camaras/index.js';
import { revelar } from './comun/revelado.js';
import { crc32 } from './comun/zip.js';

const bytes = async f => new Uint8Array(await f.arrayBuffer());

const TAREAS = {
  /** Convierte un disparo. Devuelve el DNG en dos partes (cabecera + píxeles) y la miniatura. */
  async convertir(m) {
    const t0 = performance.now();
    const perfil = camara(m.camara);
    const campos = await Promise.all(m.campos.map(bytes));
    const jpg = m.jpg && m.jpg.size ? await bytes(m.jpg) : null;
    const c = perfil.convertir(campos, jpg, { ...m.opciones, nombres: m.campos.map(f => f.name) });
    const pix = new Uint16Array(c.pixeles.buffer, c.pixeles.byteOffset, c.pixeles.byteLength / 2);
    const v = revelar(pix, c.revelado, { paso: m.pasoVista, giro: 0 });
    const pixeles = c.pixeles.byteLength === c.pixeles.buffer.byteLength ? c.pixeles.buffer : c.pixeles.slice().buffer;
    const r = { cabecera: c.cabecera, pixeles, jpg: c.jpg, formato: c.formato, balance: c.balance, giro: c.giro,
      revelado: c.revelado, vista: { rgba: v.rgba.buffer, ancho: v.ancho, alto: v.alto }, ms: Math.round(performance.now() - t0) };
    return [r, [pixeles, v.rgba.buffer]];
  },
  /** Revela un DNG ya hecho (para el visor). m.pixeles es un Blob con el mosaico. */
  async revelar(m) {
    const pix = new Uint16Array(await m.pixeles.arrayBuffer());
    const v = revelar(pix, m.revelado, { paso: m.paso, giro: m.giro });
    return [{ rgba: v.rgba.buffer, ancho: v.ancho, alto: v.alto }, [v.rgba.buffer]];
  },
  /** CRC-32 de un archivo dado por partes (Uint8Array o Blob), leyendo los Blob por tramos. */
  async crc(m) {
    let c = 0;
    for (const p of m.partes) {
      if (p instanceof Blob) {
        for (let i = 0; i < p.size; i += 8 << 20) c = crc32(await bytes(p.slice(i, i + (8 << 20))), c);
      } else c = crc32(p, c);
    }
    return [{ crc: c }, []];
  },
};

self.onmessage = async e => {
  const m = e.data;
  try {
    const [r, transferir] = await TAREAS[m.que](m);
    self.postMessage({ id: m.id, ok: true, ...r }, transferir);
  } catch (err) {
    self.postMessage({ id: m.id, ok: false, error: String(err && err.message ? err.message : err).slice(-300) });
  }
};
