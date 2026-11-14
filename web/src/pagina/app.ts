// Página de Reveal: recibe archivos, los reparte entre las cámaras conocidas, los convierte en
// Workers y enseña cada foto. Todo ocurre en el navegador: no hay servidor al que subir nada.
//
// Cómo está armada (el detalle, en docs/ESTADOS_WEB.md):
//   * El estado vive en las variables de la sección "estado", y en ningún otro sitio. El DOM sólo se
//     escribe en las funciones pintar…, a partir de ese estado; nunca se lee para decidir nada.
//   * Las transiciones son las de modelo/estado.ts. Aquí se guarda el valor nuevo y se pinta.
//   * Lo que tiene dueño y hay que soltar (pedidos a la cola, URL de objeto) está junto a quien lo usa.
import { CAMARAS, camara, repartir } from '../nucleo/camaras/index.js';
import type { Opciones } from '../nucleo/camaras/perfil.js';
import type { Bytes } from '../nucleo/comun/dng.js';
import { archivosDeFoto } from '../nucleo/comun/foto.js';
import type { ArchivoDeFoto } from '../nucleo/comun/foto.js';
import { armarZip, repartirZips } from '../nucleo/comun/zip.js';
import type { EntradaZip } from '../nucleo/comun/zip.js';
import { conOpcion, fotoDe, motivoSinExportar, puedeExportar, resumir, soltar, textoResumen, transicionTarjeta,
  transicionVisor } from '../modelo/estado.js';
import type { Destino, DisparoWeb, EventoTarjeta, EventoVisor, Exportacion, FotoLista, Tarjeta, Visor } from '../modelo/estado.js';
import { textoDeError } from '../modelo/protocolo.js';
import type { BlobLegible, Datos } from '../modelo/protocolo.js';
import { nunca } from '../modelo/tareas.js';
import { Cola } from './cola.js';
import type { Pedido } from './cola.js';

function $<T extends HTMLElement = HTMLElement>(selector: string, dentro: ParentNode = document): T {
  const e = dentro.querySelector<T>(selector);
  if (!e) throw new Error(`falta ${selector} en la página`);
  return e;
}

const PASO_MINIATURA = 4;           // 4320×3264 → 540×408
const ICON = {
  izq: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v6h6"/></svg>',
  der: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/></svg>',
  bajar: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11"/><path d="M7 11l5 5 5-5"/><path d="M5 20h14"/></svg>',
};

// ---------------------------------------------------------------- estado (único dueño: este módulo)
let opciones: Opciones = { balance: 'auto', rotar: 'no' };
const tarjetas = new Map<string, Tarjeta>();
let exportacion: Exportacion = { tipo: 'reposo' };
let visor: Visor = { tipo: 'cerrado' };
let arrastrando = false;

// Hasta tres conversiones a la vez; cada una ocupa unos 150 MB mientras dura, así que en equipos con
// poca memoria (o teléfonos) se queda en una o dos.
const memoria = (navigator as Navigator & { deviceMemory?: number }).deviceMemory;
const N_OBREROS = Math.max(1, Math.min(3, (navigator.hardwareConcurrency || 2) - 1, memoria && memoria <= 4 ? 1 : 3));
const cola = new Cola(() => new Worker(new URL('../obrero/obrero.js', import.meta.url), { type: 'module' }), N_OBREROS);

// ---------------------------------------------------------------- aviso
const elAviso = $('#aviso');
let relojAviso: number | undefined;
function aviso(texto: string): void {
  elAviso.textContent = texto;
  elAviso.classList.add('on');
  clearTimeout(relojAviso);
  relojAviso = setTimeout(() => elAviso.classList.remove('on'), 3200);
}

// ---------------------------------------------------------------- ajustes (se recuerdan)
const segmentos = [...document.querySelectorAll<HTMLElement>('.seg')];
function pintarOpciones(): void {
  for (const s of segmentos) {
    const valor = s.dataset.opc === 'balance' ? opciones.balance : opciones.rotar;
    for (const b of s.querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.v === valor));
  }
}
for (const s of segmentos) {
  const clave = s.dataset.opc ?? '';
  s.addEventListener('click', e => {
    const b = e.target instanceof Element ? e.target.closest('button') : null;
    if (!b) return;
    const nuevas = conOpcion(opciones, clave, b.dataset.v ?? '');
    if (nuevas === opciones) return;
    opciones = nuevas;                                // vale para lo que se suelte desde ahora
    pintarOpciones();
    try { localStorage.setItem('reveal_' + clave, b.dataset.v ?? ''); } catch { /* modo privado */ }
  });
  try { opciones = conOpcion(opciones, clave, localStorage.getItem('reveal_' + clave) ?? ''); } catch { /* modo privado */ }
}
pintarOpciones();

// ---------------------------------------------------------------- tarjetas
interface VistaTarjeta {
  readonly el: HTMLElement;
  readonly marco: HTMLElement;
  readonly meta: HTMLElement;
  readonly botones: HTMLButtonElement[];
  /** La foto cuya miniatura está pintada, para no repintarla sin motivo. */
  pintada: FotoLista | null;
}
const vistas = new Map<string, VistaTarjeta>();
/** La conversión en marcha de cada tarjeta, para cancelarla si la foto se suelta otra vez. */
const conversiones = new Map<string, Pedido<'convertir'>>();
const rejilla = $('#rejilla');

function crearVista(t: Tarjeta): VistaTarjeta {
  const clave = t.clave;
  const el = document.createElement('div');
  el.className = 'foto';
  el.innerHTML = `<div class="marco"></div>
    <div class="pie"><div class="t"><div class="n"><span class="nom"></span><span class="cam"></span></div><div class="m"></div></div>
    <button type="button" class="ic" data-a="izq" title="Girar a la izquierda" aria-label="Girar a la izquierda">${ICON.izq}</button>
    <button type="button" class="ic" data-a="der" title="Girar a la derecha" aria-label="Girar a la derecha">${ICON.der}</button>
    <button type="button" class="ic" data-a="bajar" title="Descargar el DNG (y su JPG)" aria-label="Descargar">${ICON.bajar}</button></div>`;
  $('.nom', el).textContent = t.disparo.titulo;
  $('.cam', el).textContent = camara(t.disparo.camara).corto;
  $('.pie', el).addEventListener('click', e => {
    const b = e.target instanceof Element ? e.target.closest('button') : null;
    const accion = b?.dataset.a;
    if (accion === 'izq' || accion === 'der') {
      const actual = tarjetas.get(clave);
      if (actual) despachar(clave, { tipo: 'girada', sentido: accion, orientarJpg: camara(actual.disparo.camara).orientarJpg });
    } else if (accion === 'bajar') {
      const foto = fotoDe(tarjetas.get(clave));
      if (foto) archivosDeFoto(foto).forEach(bajar);
    }
  });
  const marco = $('.marco', el);
  marco.addEventListener('click', () => eventoVisor({ tipo: 'abrir', clave }));
  rejilla.prepend(el);
  return { el, marco, meta: $('.m', el), botones: [...el.querySelectorAll<HTMLButtonElement>('.ic')], pintada: null };
}

function miniatura(foto: FotoLista): HTMLCanvasElement {
  const { vista, giro } = foto;
  const lienzo = document.createElement('canvas');
  lienzo.width = giro % 2 ? vista.alto : vista.ancho;
  lienzo.height = giro % 2 ? vista.ancho : vista.alto;
  const tmp = document.createElement('canvas');
  tmp.width = vista.ancho; tmp.height = vista.alto;
  tmp.getContext('2d')?.putImageData(new ImageData(vista.rgba, vista.ancho, vista.alto), 0, 0);
  const c = lienzo.getContext('2d');
  if (c) {
    c.translate(lienzo.width / 2, lienzo.height / 2);
    c.rotate(-giro * Math.PI / 2);                    // giro = cuartos de vuelta a la izquierda
    c.drawImage(tmp, -vista.ancho / 2, -vista.alto / 2);
  }
  return lienzo;
}

function etiqueta(clase: string, texto: string): HTMLElement {
  const e = document.createElement('span');
  e.className = clase; e.textContent = texto;
  return e;
}

/** Deja la tarjeta en pantalla como dice su estado. Es el único sitio que la escribe. */
function pintarTarjeta(t: Tarjeta): void {
  let v = vistas.get(t.clave);
  if (!v) { v = crearVista(t); vistas.set(t.clave, v); }
  const { el, marco, meta } = v, e = t.estado;
  el.dataset.estado = e.tipo;
  el.dataset.epoca = String(t.epoca);
  for (const b of v.botones) b.disabled = e.tipo !== 'lista';
  meta.className = e.tipo === 'error' ? 'm err' : 'm';
  if (e.tipo !== 'lista') {
    v.pintada = null;
    delete el.dataset.giro; delete el.dataset.ms; delete el.dataset.balance;
  }
  switch (e.tipo) {
    case 'cola':
    case 'convirtiendo': {
      const rueda = document.createElement('div');
      rueda.className = 'cargando';
      marco.replaceChildren(rueda, etiqueta('estado', e.tipo === 'cola' ? 'en cola' : 'convirtiendo'));
      meta.textContent = ''; meta.title = '';
      break;
    }
    case 'lista': {
      const f = e.foto;
      if (v.pintada !== f) { marco.replaceChildren(miniatura(f), etiqueta('etq', 'DNG')); v.pintada = f; }
      el.dataset.giro = String(f.giro); el.dataset.ms = String(f.ms); el.dataset.balance = f.balance;
      meta.textContent = meta.title = [f.formato, 'balance ' + f.balance.replace('_', ' '), f.jpg ? 'con JPG' : 'sin JPG'].join(' · ');
      break;
    }
    case 'error':
      marco.replaceChildren(etiqueta('etq', 'error'));
      meta.textContent = meta.title = e.mensaje;
      break;
    default:
      nunca(e);
  }
}

/** Guarda la tarjeta nueva y pinta todo lo que depende de ella. Único sitio que escribe en `tarjetas`. */
function cambiar(nueva: Tarjeta): void {
  if (tarjetas.get(nueva.clave) === nueva) return;
  tarjetas.set(nueva.clave, nueva);
  pintarTarjeta(nueva);
  eventoVisor({ tipo: 'tarjetas' });
  pintarResumen();
}
function despachar(clave: string, e: EventoTarjeta): void {
  const t = tarjetas.get(clave);
  if (t) cambiar(transicionTarjeta(t, e));
}

function fotoLista(d: DisparoWeb, r: Datos['convertir']): FotoLista {
  return { salida: d.salida, cabecera: r.cabecera, pixeles: new Blob([r.pixeles]), jpg: r.jpg, giro: r.giro, formato: r.formato,
    balance: r.balance, revelado: r.revelado, ms: r.ms,
    vista: { rgba: new Uint8ClampedArray(r.vista.rgba), ancho: r.vista.ancho, alto: r.vista.alto } };
}

/** Pone a convertir cada disparo, con los ajustes de este momento. Soltar otra vez una foto la reemplaza. */
function recibir(archivos: File[]): void {
  const { disparos, ignorados } = repartir(archivos);
  for (const d of disparos) {
    conversiones.get(d.clave)?.cancelar();            // la conversión anterior de esta foto ya no interesa
    const t = soltar(tarjetas.get(d.clave), d, opciones);
    cambiar(t);
    const pedido = cola.pedir({ que: 'convertir', camara: d.camara, campos: d.campos, jpg: d.jpg, opciones: t.opciones, pasoVista: PASO_MINIATURA },
      { alEmpezar: () => despachar(t.clave, { tipo: 'empezo', epoca: t.epoca }) });
    conversiones.set(t.clave, pedido);
    void pedido.resultado.then(r => {
      if (conversiones.get(t.clave) === pedido) conversiones.delete(t.clave);
      switch (r.tipo) {
        case 'ok': despachar(t.clave, { tipo: 'convertida', epoca: t.epoca, foto: fotoLista(d, r.datos) }); break;
        case 'error': despachar(t.clave, { tipo: 'fallo', epoca: t.epoca, mensaje: r.mensaje }); break;
        case 'cancelada': break;
        default: nunca(r);
      }
    });
  }
  if (!disparos.length) {
    aviso(ignorados ? `Ningún RAW conocido entre esos archivos (se espera ${CAMARAS.map(c => c.ayuda).join(' o ')})` : 'Nada que convertir');
  }
}

// ---------------------------------------------------------------- resumen y botones de exportar
const zona = $('#zona'), elResumen = $('#resumen'), elCuenta = $('#cuenta');
const bZip = $<HTMLButtonElement>('#zip'), bGuardar = $<HTMLButtonElement>('#guardar');
const TEXTO_BOTON: Record<Destino, { reposo: string; ocupado: string }> = {
  zip: { reposo: bZip.textContent ?? '', ocupado: 'Preparando…' },
  carpeta: { reposo: bGuardar.textContent ?? '', ocupado: 'Guardando…' },
};
function pintarResumen(): void {
  const r = resumir(tarjetas.values());
  elCuenta.textContent = textoResumen(r);
  zona.classList.toggle('compacta', tarjetas.size > 0);
  zona.classList.toggle('sobre', arrastrando);
  const en = exportacion.tipo === 'exportando' ? exportacion.destino : null;
  elResumen.dataset.exportando = en ?? '';
  bZip.disabled = bGuardar.disabled = !puedeExportar(r, exportacion);
  bZip.textContent = TEXTO_BOTON.zip[en === 'zip' ? 'ocupado' : 'reposo'];
  bGuardar.textContent = TEXTO_BOTON.carpeta[en === 'carpeta' ? 'ocupado' : 'reposo'];
}

// ---------------------------------------------------------------- visor (espacio: DNG / JPG; Esc: cerrar)
const elVisor = $('#visor'), lienzoVisor = $<HTMLCanvasElement>('canvas', elVisor), imgVisor = $<HTMLImageElement>('img', elVisor);
const pieVisor = $('.pie-visor', elVisor);
/** Lo que el visor tiene en pantalla y lo que tomó prestado para pintarlo (se suelta al repintar). */
let visorPintado: { readonly foto: FotoLista; readonly que: 'dng' | 'jpg' } | null = null;
let visorUrl: string | null = null;
let visorRevelado: Pedido<'revelar'> | null = null;

function eventoVisor(e: EventoVisor): void {
  visor = transicionVisor(visor, e, tarjetas);
  pintarVisor();
}

function pintarVisor(): void {
  const foto = visor.tipo === 'abierto' ? fotoDe(tarjetas.get(visor.clave)) : null;
  const que = visor.tipo === 'abierto' ? visor.que : 'dng';
  if (visorPintado ? visorPintado.foto === foto && visorPintado.que === que : !foto) return;
  // suelta lo de la pintada anterior: su revelado pendiente y su URL
  visorRevelado?.cancelar();
  visorRevelado = null;
  if (visorUrl) { URL.revokeObjectURL(visorUrl); visorUrl = null; }
  imgVisor.removeAttribute('src');
  delete elVisor.dataset.revelado;
  if (!foto) {
    visorPintado = null;
    elVisor.classList.remove('on');
    delete elVisor.dataset.foto;
    return;
  }
  visorPintado = { foto, que };
  elVisor.classList.add('on');
  elVisor.dataset.que = que;
  elVisor.dataset.foto = foto.salida;
  pieVisor.textContent = `${foto.salida} · ${que === 'dng' ? 'DNG (vista previa rápida)' : 'JPG de la cámara'}` +
    (foto.jpg ? ' · espacio: cambiar DNG / JPG' : '') + ' · Esc: cerrar';
  if (que === 'jpg' && foto.jpg) {
    visorUrl = URL.createObjectURL(new Blob([foto.jpg], { type: 'image/jpeg' }));
    imgVisor.src = visorUrl;                          // el navegador aplica la orientación del EXIF
    imgVisor.hidden = false; lienzoVisor.hidden = true;
    return;
  }
  imgVisor.hidden = true; lienzoVisor.hidden = false;
  // primero la miniatura ampliada; el revelado a media resolución llega en un momento
  const mini = miniatura(foto);
  lienzoVisor.width = mini.width; lienzoVisor.height = mini.height;
  lienzoVisor.getContext('2d')?.drawImage(mini, 0, 0);
  const pedido = cola.pedir({ que: 'revelar', pixeles: foto.pixeles, revelado: foto.revelado, giro: foto.giro, paso: 1 }, { prioridad: 'primero' });
  visorRevelado = pedido;
  void pedido.resultado.then(r => {
    if (visorRevelado !== pedido || r.tipo !== 'ok') return;       // el visor ya enseña otra cosa
    visorRevelado = null;
    lienzoVisor.width = r.datos.ancho; lienzoVisor.height = r.datos.alto;
    lienzoVisor.getContext('2d')?.putImageData(new ImageData(new Uint8ClampedArray(r.datos.rgba), r.datos.ancho, r.datos.alto), 0, 0);
    elVisor.dataset.revelado = `${r.datos.ancho}x${r.datos.alto}`;
  });
}
elVisor.addEventListener('click', () => eventoVisor({ tipo: 'cerrar' }));
// En captura: con el visor abierto, Esc y espacio son suyos y no llegan a lo que haya debajo.
document.addEventListener('keydown', e => {
  if (visor.tipo !== 'abierto' || (e.key !== 'Escape' && e.key !== ' ')) return;
  e.preventDefault(); e.stopPropagation();
  eventoVisor({ tipo: e.key === ' ' ? 'alternar' : 'cerrar' });
}, true);

// ---------------------------------------------------------------- entrada de archivos
async function leerEntrada(ent: FileSystemEntry, out: File[]): Promise<void> {
  if (ent.isFile) {
    await new Promise<void>(r => (ent as FileSystemFileEntry).file(f => { out.push(f); r(); }, () => r()));
  } else if (ent.isDirectory) {
    const lector = (ent as FileSystemDirectoryEntry).createReader();
    for (;;) {
      const lote = await new Promise<FileSystemEntry[]>(r => lector.readEntries(r, () => r([])));
      if (!lote.length) break;
      for (const e of lote) await leerEntrada(e, out);
    }
  }
}
const elegir = $<HTMLInputElement>('#elegir'), elegirCarpeta = $<HTMLInputElement>('#elegir-carpeta'), bCarpeta = $('#b-carpeta');
zona.addEventListener('click', () => elegir.click());
zona.addEventListener('keydown', e => { if (e.target === zona && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); elegir.click(); } });
$('#b-archivos').addEventListener('click', e => { e.stopPropagation(); elegir.click(); });
bCarpeta.addEventListener('click', e => { e.stopPropagation(); elegirCarpeta.click(); });
if (!('webkitdirectory' in HTMLInputElement.prototype)) bCarpeta.hidden = true;
for (const entrada of [elegir, elegirCarpeta]) {
  entrada.addEventListener('change', () => { recibir([...entrada.files ?? []]); entrada.value = ''; });
}

// Arrastre: sólo cuenta si lo que se arrastra son archivos (no un texto o un enlace de la propia página).
const traeArchivos = (e: DragEvent): boolean => Boolean(e.dataTransfer && [...e.dataTransfer.types].includes('Files'));
function ponerArrastre(v: boolean): void {
  if (arrastrando === v) return;
  arrastrando = v;
  pintarResumen();
}
/** Las tandas soltadas se leen y se reciben de una en una, en el orden en que se soltaron. */
let lecturas: Promise<void> = Promise.resolve();
document.addEventListener('dragover', e => { if (traeArchivos(e)) { e.preventDefault(); ponerArrastre(true); } });
document.addEventListener('dragleave', e => { if (!e.relatedTarget) ponerArrastre(false); });
document.addEventListener('drop', e => {
  ponerArrastre(false);
  if (!traeArchivos(e) || !e.dataTransfer) return;
  e.preventDefault();
  // Las entradas sólo se pueden pedir ahora, dentro del evento.
  const ents = [...e.dataTransfer.items].map(i => i.webkitGetAsEntry?.() ?? null).filter(x => x !== null);
  const sueltos = [...e.dataTransfer.files];
  lecturas = lecturas.then(async () => {
    const out: File[] = [];
    if (ents.length) for (const en of ents) await leerEntrada(en, out); else out.push(...sueltos);
    recibir(out);
  }).catch((err: unknown) => aviso(textoDeError(err)));
});

// ---------------------------------------------------------------- salida: descargas, .zip y carpeta
/** En la página los píxeles de una foto son siempre un Blob del navegador. */
function blobDe(partes: readonly (Bytes | BlobLegible)[], tipo = ''): Blob {
  return new Blob(partes as BlobPart[], { type: tipo });
}
function bajarBlob(blob: Blob, nombre: string): void {
  const a = document.createElement('a');
  const url = URL.createObjectURL(blob);              // dueña: esta descarga; se suelta al minuto
  a.href = url; a.download = nombre;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
function bajar(a: ArchivoDeFoto<BlobLegible>): void {
  bajarBlob(blobDe(a.partes, a.nombre.endsWith('.JPG') ? 'image/jpeg' : 'image/x-adobe-dng'), a.nombre);
}
function hoy(): string {
  const d = new Date(), p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/**
 * Exporta las fotos que están listas en este instante. Como una Foto no cambia nunca, lo que se
 * exporta es exactamente eso aunque mientras tanto se gire una tarjeta o se suelten más archivos.
 */
async function exportar(destino: Destino, tarea: (fotos: readonly FotoLista[]) => Promise<void>): Promise<void> {
  const motivo = motivoSinExportar(resumir(tarjetas.values()), exportacion);
  if (motivo) { aviso(motivo); return; }
  const fotos = [...tarjetas.values()].map(fotoDe).filter(f => f !== null).sort((a, b) => (a.salida < b.salida ? -1 : 1));
  exportacion = { tipo: 'exportando', destino };
  pintarResumen();
  try {
    await tarea(fotos);
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError')) aviso(textoDeError(e));
  } finally {
    exportacion = { tipo: 'reposo' };
    pintarResumen();
  }
}

bZip.addEventListener('click', () => void exportar('zip', async fotos => {
  const entradas: EntradaZip<Blob>[] = [];
  for (const f of fotos) {
    for (const a of archivosDeFoto(f)) {
      const r = await cola.pedir({ que: 'crc', partes: a.partes }, { prioridad: 'primero' }).resultado;
      if (r.tipo !== 'ok') throw new Error(r.tipo === 'error' ? r.mensaje : 'se canceló el cálculo del .zip');
      entradas.push({ nombre: a.nombre, datos: blobDe(a.partes), tam: a.tam, crc: r.datos.crc, junto: f.salida });
    }
  }
  const grupos = repartirZips(entradas);
  grupos.forEach((g, i) => {
    const nombre = `reveal_${hoy()}${grupos.length > 1 ? `_${i + 1}de${grupos.length}` : ''}.zip`;
    bajarBlob(new Blob(armarZip(g), { type: 'application/zip' }), nombre);
  });
  if (grupos.length > 1) aviso(`Son muchas fotos: salen ${grupos.length} archivos .zip`);
}));

interface ConSelectorDeCarpeta {
  showDirectoryPicker(opciones: { mode: 'readwrite' }): Promise<FileSystemDirectoryHandle>;
}
function tieneSelectorDeCarpeta(w: object): w is ConSelectorDeCarpeta {
  return 'showDirectoryPicker' in w;
}
if (tieneSelectorDeCarpeta(window)) {
  const ventana = window;
  bGuardar.hidden = false;
  bGuardar.addEventListener('click', () => void exportar('carpeta', async fotos => {
    const dir = await ventana.showDirectoryPicker({ mode: 'readwrite' });
    let n = 0;
    for (const f of fotos) {
      for (const a of archivosDeFoto(f)) {
        const w = await (await dir.getFileHandle(a.nombre, { create: true })).createWritable();
        await w.write(blobDe(a.partes));
        await w.close();
        n++;
      }
    }
    aviso(`${n} archivos guardados en «${dir.name}»`);
  }));
}

$('#camaras').textContent = 'Cámaras: ' + CAMARAS.map(c => `${c.nombre} (${c.ayuda})`).join(' · ') +
  '. La conversión corre en esta página; ningún archivo se envía a ningún sitio.';
pintarResumen();
