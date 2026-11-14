// Página de Reveal: recibe archivos, los reparte entre las cámaras conocidas, los convierte en
// Workers y enseña cada foto. Todo ocurre en el navegador: no hay servidor al que subir nada.
import { camara, CAMARAS, repartir } from './camaras/index.js';
import { archivosDeFoto, girarFoto } from './comun/foto.js';
import { armarZip, repartirZips } from './comun/zip.js';

const $ = s => document.querySelector(s);
const opc = { balance: 'auto', rotar: 'no' };
const fotos = new Map();            // clave → { el, disparo, datos (foto convertida) | null }
let pendientes = 0, fallos = 0;
const PASO_MINIATURA = 4;           // 4320×3264 → 540×408

const ICON = {
  izq: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v6h6"/></svg>',
  der: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/></svg>',
  bajar: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11"/><path d="M7 11l5 5 5-5"/><path d="M5 20h14"/></svg>',
};

function aviso(t) {
  const a = $('#aviso');
  a.textContent = t; a.classList.add('on');
  clearTimeout(aviso.t); aviso.t = setTimeout(() => a.classList.remove('on'), 3200);
}

// ---------------------------------------------------------------- Workers
// Hasta tres conversiones a la vez; cada una ocupa unos 150 MB mientras dura, así que en equipos con
// poca memoria (o teléfonos) se queda en una o dos.
const N_OBREROS = Math.max(1, Math.min(3, (navigator.hardwareConcurrency || 2) - 1, navigator.deviceMemory && navigator.deviceMemory <= 4 ? 1 : 3));
const obreros = [], libres = [], cola = [], esperando = new Map();
let serie = 0;
function atender() {
  while (cola.length && (libres.length || obreros.length < N_OBREROS)) {
    let w = libres.pop();
    if (!w) {
      w = new Worker(new URL('./obrero.js', import.meta.url), { type: 'module' });
      w.onmessage = e => {
        const p = esperando.get(e.data.id);
        esperando.delete(e.data.id);
        libres.push(w);
        p.resolve(e.data);
        atender();
      };
      w.onerror = e => {            // el Worker murió (sin memoria, por ejemplo): falla su tarea y se repone
        e.preventDefault();
        for (const [id, p] of esperando) if (p.w === w) { esperando.delete(id); p.resolve({ ok: false, error: e.message || 'el conversor se quedó sin memoria' }); }
        obreros.splice(obreros.indexOf(w), 1);
        w.terminate();
        atender();
      };
      obreros.push(w);
    }
    const t = cola.shift();
    esperando.set(t.msg.id, { resolve: t.resolve, w });
    if (t.alEmpezar) t.alEmpezar();
    w.postMessage(t.msg);
  }
}
function pedir(msg, alEmpezar) {
  return new Promise(resolve => { cola.push({ msg: { ...msg, id: ++serie }, resolve, alEmpezar }); atender(); });
}

// ---------------------------------------------------------------- opciones (se recuerdan)
document.querySelectorAll('.seg').forEach(s => s.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  opc[s.dataset.opc] = b.dataset.v;
  s.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b));
  try { localStorage.setItem('reveal_' + s.dataset.opc, b.dataset.v); } catch (_) { /* modo privado */ }
}));
for (const k of ['balance', 'rotar']) {
  let v = null;
  try { v = localStorage.getItem('reveal_' + k); } catch (_) { /* modo privado */ }
  const b = v && document.querySelector(`.seg[data-opc="${k}"] button[data-v="${CSS.escape(v)}"]`);
  if (b) b.click();
}

// ---------------------------------------------------------------- tarjetas
function listas() {
  return [...fotos.values()].filter(f => f.datos).map(f => f.datos);
}
function contar() {
  const t = [], n = listas().length;
  if (pendientes) t.push(`convirtiendo ${pendientes}…`);
  if (n) t.push(`${n} DNG ${n === 1 ? 'listo' : 'listos'}`);
  if (fallos) t.push(`${fallos} con error`);
  $('#cuenta').textContent = t.join(' · ');
  $('#zona').classList.toggle('compacta', fotos.size > 0);
  $('#zip').disabled = $('#guardar').disabled = !n || pendientes > 0;
}

function tarjeta(d) {
  let f = fotos.get(d.clave);
  if (f) {                          // la misma foto otra vez: se reconvierte en su tarjeta
    if (f.el.dataset.estado === 'error') fallos--;
    f.datos = null; f.disparo = d;
  } else {
    const el = document.createElement('div');
    el.className = 'foto';
    el.innerHTML = `<div class="marco"></div>
      <div class="pie"><div class="t"><div class="n"><span class="nom"></span><span class="cam"></span></div><div class="m"></div></div>
      <button type="button" class="ic" data-a="izq" title="Girar a la izquierda" aria-label="Girar a la izquierda">${ICON.izq}</button>
      <button type="button" class="ic" data-a="der" title="Girar a la derecha" aria-label="Girar a la derecha">${ICON.der}</button>
      <button type="button" class="ic" data-a="bajar" title="Descargar el DNG (y su JPG)" aria-label="Descargar">${ICON.bajar}</button></div>`;
    el.querySelector('.nom').textContent = d.titulo;
    el.querySelector('.cam').textContent = camara(d.camara).corto;
    $('#rejilla').prepend(el);
    f = { el, disparo: d, datos: null };
    fotos.set(d.clave, f);
    el.querySelector('.pie').addEventListener('click', e => {
      const b = e.target.closest('button');
      if (!b || !f.datos) return;
      if (b.dataset.a === 'bajar') return archivosDeFoto(f.datos).forEach(bajar);
      girarFoto(f.datos, b.dataset.a, camara(f.disparo.camara).orientarJpg);
      f.el.dataset.giro = f.datos.giro;
      pintarMiniatura(f);
    });
    el.querySelector('.marco').addEventListener('click', () => f.datos && ampliar(f));
  }
  f.el.dataset.estado = 'cola';
  f.el.querySelector('.marco').innerHTML = '<div class="cargando"></div><span class="estado">en cola</span>';
  f.el.querySelectorAll('.ic').forEach(b => { b.disabled = true; });
  const m = f.el.querySelector('.m');
  m.className = 'm'; m.textContent = '';
  return f;
}

function pintarMiniatura(f) {
  const { vista, giro } = f.datos;
  const lienzo = document.createElement('canvas');
  lienzo.width = giro % 2 ? vista.height : vista.width;
  lienzo.height = giro % 2 ? vista.width : vista.height;
  const tmp = document.createElement('canvas');
  tmp.width = vista.width; tmp.height = vista.height;
  tmp.getContext('2d').putImageData(vista, 0, 0);
  const c = lienzo.getContext('2d');
  c.translate(lienzo.width / 2, lienzo.height / 2);
  c.rotate(-giro * Math.PI / 2);                     // giro = cuartos de vuelta a la izquierda
  c.drawImage(tmp, -vista.width / 2, -vista.height / 2);
  const e = document.createElement('span');
  e.className = 'etq'; e.textContent = 'DNG';
  f.el.querySelector('.marco').replaceChildren(lienzo, e);
}

function mostrar(f, r) {
  const d = f.disparo;
  f.datos = {
    salida: d.salida, cabecera: r.cabecera, pixeles: new Blob([r.pixeles]), jpg: r.jpg, giro: r.giro, formato: r.formato,
    balance: r.balance, revelado: r.revelado, vista: new ImageData(new Uint8ClampedArray(r.vista.rgba), r.vista.ancho, r.vista.alto),
  };
  f.el.dataset.estado = 'lista'; f.el.dataset.giro = r.giro; f.el.dataset.ms = r.ms; f.el.dataset.balance = r.balance;
  pintarMiniatura(f);
  const meta = f.el.querySelector('.m');
  meta.textContent = meta.title = [r.formato, 'balance ' + r.balance.replace('_', ' '), r.jpg ? 'con JPG' : 'sin JPG'].join(' · ');
  f.el.querySelectorAll('.ic').forEach(b => { b.disabled = false; });
}
function fallo(f, msg) {
  f.el.dataset.estado = 'error';
  f.el.querySelector('.marco').innerHTML = '<span class="etq">error</span>';
  const m = f.el.querySelector('.m');
  m.className = 'm err'; m.textContent = msg;
  fallos++;
}

// ---------------------------------------------------------------- visor (espacio: DNG / JPG; Esc: cerrar)
const visor = $('#visor');
let visorFoto = null, visorQue = 'dng', visorURL = null, visorTurno = 0;
function ampliar(f) { visorFoto = f; visorQue = 'dng'; visor.classList.add('on'); pintarVisor(); }
function cerrarVisor() {
  visor.classList.remove('on');
  visorFoto = null; visorTurno++;
  if (visorURL) { URL.revokeObjectURL(visorURL); visorURL = null; }
  visor.querySelector('img').removeAttribute('src');
}
async function pintarVisor() {
  const d = visorFoto.datos, turno = ++visorTurno;
  const lienzo = visor.querySelector('canvas'), img = visor.querySelector('img');
  visor.dataset.que = visorQue;
  visor.querySelector('.pie-visor').textContent = `${d.salida} · ${visorQue === 'dng' ? 'DNG (vista previa rápida)' : 'JPG de la cámara'}` +
    (d.jpg ? ' · espacio: cambiar DNG / JPG' : '') + ' · Esc: cerrar';
  if (visorQue === 'jpg') {
    if (visorURL) URL.revokeObjectURL(visorURL);
    visorURL = URL.createObjectURL(new Blob([d.jpg], { type: 'image/jpeg' }));
    img.src = visorURL;                               // el navegador aplica la orientación del EXIF
    img.hidden = false; lienzo.hidden = true;
    return;
  }
  img.hidden = true; lienzo.hidden = false;
  // primero la miniatura ampliada; el revelado a media resolución llega en un momento
  const mini = visorFoto.el.querySelector('.marco canvas');
  lienzo.width = mini.width; lienzo.height = mini.height;
  lienzo.getContext('2d').drawImage(mini, 0, 0);
  const r = await pedir({ que: 'revelar', pixeles: d.pixeles, revelado: d.revelado, giro: d.giro, paso: 1 });
  if (turno !== visorTurno || !r.ok) return;
  lienzo.width = r.ancho; lienzo.height = r.alto;
  lienzo.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(r.rgba), r.ancho, r.alto), 0, 0);
  visor.dataset.revelado = `${r.ancho}x${r.alto}`;
}
visor.addEventListener('click', cerrarVisor);
document.addEventListener('keydown', e => {
  if (!visor.classList.contains('on')) return;
  if (e.key === 'Escape') cerrarVisor();
  if (e.key === ' ') {
    e.preventDefault();
    if (visorFoto.datos.jpg) { visorQue = visorQue === 'dng' ? 'jpg' : 'dng'; pintarVisor(); }
  }
});

// ---------------------------------------------------------------- entrada de archivos
function recibir(archivos) {
  const { disparos, ignorados } = repartir(archivos);
  for (const d of disparos) {
    const f = tarjeta(d);
    pendientes++;
    const estado = t => { const e = f.el.querySelector('.estado'); if (e) e.textContent = t; };
    pedir({ que: 'convertir', camara: d.camara, campos: d.campos, jpg: d.jpg, opciones: { ...opc }, pasoVista: PASO_MINIATURA },
      () => { f.el.dataset.estado = 'convirtiendo'; estado('convirtiendo'); })
      .then(r => {
        if (f.disparo !== d) return;                  // la soltaron otra vez mientras tanto
        if (r.ok) mostrar(f, r); else fallo(f, r.error);
      })
      .finally(() => { pendientes--; contar(); });
  }
  contar();
  if (!disparos.length) {
    aviso(ignorados ? `Ningún RAW conocido entre esos archivos (se espera ${CAMARAS.map(c => c.ayuda).join(' o ')})` : 'Nada que convertir');
  }
}

async function leerEntrada(ent, out) {
  if (ent.isFile) return new Promise(r => ent.file(f => { out.push(f); r(); }, r));
  if (ent.isDirectory) {
    const lector = ent.createReader();
    for (;;) {
      const lote = await new Promise(r => lector.readEntries(r, () => r([])));
      if (!lote.length) break;
      for (const e of lote) await leerEntrada(e, out);
    }
  }
}
const zona = $('#zona');
zona.addEventListener('click', () => $('#elegir').click());
zona.addEventListener('keydown', e => { if (e.target === zona && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); $('#elegir').click(); } });
$('#b-archivos').addEventListener('click', e => { e.stopPropagation(); $('#elegir').click(); });
$('#b-carpeta').addEventListener('click', e => { e.stopPropagation(); $('#elegir-carpeta').click(); });
if (!('webkitdirectory' in HTMLInputElement.prototype)) $('#b-carpeta').hidden = true;
for (const id of ['#elegir', '#elegir-carpeta']) {
  $(id).addEventListener('change', e => { recibir([...e.target.files]); e.target.value = ''; });
}
document.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('sobre'); });
document.addEventListener('dragleave', e => { if (!e.relatedTarget) zona.classList.remove('sobre'); });
document.addEventListener('drop', async e => {
  e.preventDefault(); zona.classList.remove('sobre');
  const ents = [...(e.dataTransfer.items || [])].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  const out = [];
  if (ents.length) for (const en of ents) await leerEntrada(en, out); else out.push(...e.dataTransfer.files);
  recibir(out);
});

// ---------------------------------------------------------------- salida: descargas, .zip y carpeta
function bajarBlob(blob, nombre) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = nombre;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 60_000);
}
function bajar(a) {
  bajarBlob(new Blob(a.partes, { type: a.nombre.endsWith('.JPG') ? 'image/jpeg' : 'image/x-adobe-dng' }), a.nombre);
}
function hoy() {
  const d = new Date(), p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
async function ocupado(boton, texto, tarea) {
  const antes = boton.textContent;
  boton.disabled = true; boton.textContent = texto;
  try { await tarea(); } catch (e) { if (e.name !== 'AbortError') aviso(e.message || String(e)); }
  boton.textContent = antes; contar();
}

$('#zip').addEventListener('click', () => ocupado($('#zip'), 'Preparando…', async () => {
  const entradas = [];
  for (const d of listas().sort((a, b) => (a.salida < b.salida ? -1 : 1))) {
    for (const a of archivosDeFoto(d)) {
      const r = await pedir({ que: 'crc', partes: a.partes });
      if (!r.ok) throw new Error(r.error);
      entradas.push({ nombre: a.nombre, datos: new Blob(a.partes), tam: a.tam, crc: r.crc, junto: d.salida });
    }
  }
  const grupos = repartirZips(entradas);
  grupos.forEach((g, i) => {
    const nombre = `reveal_${hoy()}${grupos.length > 1 ? `_${i + 1}de${grupos.length}` : ''}.zip`;
    bajarBlob(new Blob(armarZip(g), { type: 'application/zip' }), nombre);
  });
  if (grupos.length > 1) aviso(`Son muchas fotos: salen ${grupos.length} archivos .zip`);
}));

if ('showDirectoryPicker' in window) {
  $('#guardar').hidden = false;
  $('#guardar').addEventListener('click', () => ocupado($('#guardar'), 'Guardando…', async () => {
    const dir = await window.showDirectoryPicker({ mode: 'readwrite' });
    let n = 0;
    for (const d of listas()) {
      for (const a of archivosDeFoto(d)) {
        const w = await (await dir.getFileHandle(a.nombre, { create: true })).createWritable();
        await w.write(new Blob(a.partes));
        await w.close();
        n++;
      }
    }
    aviso(`${n} archivos guardados en «${dir.name}»`);
  }));
}

$('#camaras').textContent = 'Cámaras: ' + CAMARAS.map(c => `${c.nombre} (${c.ayuda})`).join(' · ') +
  '. La conversión corre en esta página; ningún archivo se envía a ningún sitio.';
contar();
