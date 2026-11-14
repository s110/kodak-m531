#!/usr/bin/env node
// Lado Node de tools/e2e_web.py: corre los mismos módulos que carga la página (web/js) sobre
// archivos del disco y deja los resultados para que Python los compare. No es una prueba por sí solo.
// uso: node tools/e2e_web_nodo.mjs TRABAJOS.json   (lista de trabajos; imprime una línea JSON por trabajo)
import fs from 'node:fs';
import path from 'node:path';
import { camara, repartir } from '../web/js/camaras/index.js';
import { archivosDeFoto, girarFoto } from '../web/js/comun/foto.js';
import { decodificarJpeg } from '../web/js/comun/jpeg.js';
import { revelar } from '../web/js/comun/revelado.js';
import { armarZip, crc32, repartirZips } from '../web/js/comun/zip.js';

const leer = r => new Uint8Array(fs.readFileSync(r));
const unir = partes => Buffer.concat(partes.map(p => Buffer.from(p.buffer, p.byteOffset, p.byteLength)));

function convertir(t) {
  // t = { carpeta, salida, balance, rotar, giros: ['izq', …], vista: paso | 0 }
  const archivos = fs.readdirSync(t.carpeta).sort().map(name => ({ name, ruta: path.join(t.carpeta, name) }));
  const { disparos, ignorados } = repartir(archivos);
  const res = { ignorados, fotos: [] };
  for (const d of disparos) {
    const perfil = camara(d.camara);
    const r = { camara: d.camara, titulo: d.titulo, campos: d.campos.map(f => f.name), jpg_entrada: d.jpg ? d.jpg.name : null };
    const t0 = performance.now();
    try {
      const c = perfil.convertir(d.campos.map(f => leer(f.ruta)), d.jpg ? leer(d.jpg.ruta) : null,
        { balance: t.balance, rotar: t.rotar, nombres: d.campos.map(f => f.name) });
      r.ms = Math.round(performance.now() - t0);
      const foto = { salida: d.salida, cabecera: c.cabecera, pixeles: c.pixeles, jpg: c.jpg, giro: c.giro };
      for (const s of t.giros || []) girarFoto(foto, s, perfil.orientarJpg);
      for (const a of archivosDeFoto(foto)) fs.writeFileSync(path.join(t.salida, a.nombre), unir(a.partes));
      Object.assign(r, { ok: true, info: c.info, formato: c.formato, balance: c.balance, giro: foto.giro, jpg: Boolean(c.jpg),
        neutro: c.revelado.neutro });
      if (t.vista) {
        const pix = new Uint16Array(c.pixeles.buffer, c.pixeles.byteOffset, c.pixeles.byteLength / 2);
        const t1 = performance.now();
        const v = revelar(pix, c.revelado, { paso: t.vista, giro: foto.giro });
        r.vista = { ancho: v.ancho, alto: v.alto, ms: Math.round(performance.now() - t1), archivo: `${d.salida}.rgba` };
        fs.writeFileSync(path.join(t.salida, r.vista.archivo), v.rgba);
      }
    } catch (e) {
      Object.assign(r, { ok: false, error: e.message, motivo: perfil.esMotivo(e) });
    }
    res.fotos.push(r);
  }
  return res;
}

function jpeg(t) {
  const r = decodificarJpeg(leer(t.jpg));
  fs.writeFileSync(t.salida, r.rgb);
  return { ancho: r.ancho, alto: r.alto };
}

function zip(t) {
  // t = { archivos: [rutas], limite, salida (prefijo) }: como la página, DNG y JPG de una foto van juntos
  const entradas = t.archivos.map(r => {
    const datos = leer(r);
    return { nombre: path.basename(r), datos, tam: datos.length, crc: crc32(datos), junto: path.basename(r).slice(0, -4) };
  });
  const grupos = repartirZips(entradas, t.limite);
  return { zips: grupos.map((g, i) => {
    const ruta = `${t.salida}${i + 1}.zip`;
    fs.writeFileSync(ruta, unir(armarZip(g, new Date(2026, 10, 14, 12, 30, 40))));
    return { ruta, nombres: g.map(e => e.nombre) };
  }) };
}

const trabajos = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
for (const t of trabajos) {
  let r;
  try {
    r = { convertir, jpeg, zip }[t.que](t);
  } catch (e) {
    r = { excepcion: e.stack };
  }
  console.log(JSON.stringify({ id: t.id, ...r }));
}
