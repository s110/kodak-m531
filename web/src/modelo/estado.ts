// Las máquinas de estado de la página, sin DOM. Cada una es un tipo con sus estados a la vista y una
// función de transición pura; la página (pagina/app.ts) guarda el valor, llama a la transición y pinta
// lo que salga. Las tablas completas, con sus invariantes, están en docs/ESTADOS_WEB.md.
//
// Regla común: una transición que no está en la tabla devuelve el mismo valor que recibió (no hace
// nada), así que quien llama sabe si hubo cambio comparando referencias.
import { girarFoto } from '../nucleo/comun/foto.js';
import type { Foto, OrientarJpg, Sentido } from '../nucleo/comun/foto.js';
import type { ParamsRevelado, Vista } from '../nucleo/comun/revelado.js';
import { BALANCES, ROTARES } from '../nucleo/camaras/perfil.js';
import type { DisparoDeCamara, Opciones } from '../nucleo/camaras/perfil.js';
import type { ArchivoLegible, BlobLegible } from './protocolo.js';
import { nunca } from './tareas.js';

// ---------------------------------------------------------------- tarjeta (una foto)
/** Una foto convertida, como la guarda la página. No se modifica: girar da otra. */
export interface FotoLista extends Foto<BlobLegible> {
  readonly formato: string;
  readonly balance: string;
  readonly revelado: ParamsRevelado;
  /** Miniatura sin girar. */
  readonly vista: Vista;
  readonly ms: number;
}

export type EstadoTarjeta =
  | { readonly tipo: 'cola' }
  | { readonly tipo: 'convirtiendo' }
  | { readonly tipo: 'lista'; readonly foto: FotoLista }
  | { readonly tipo: 'error'; readonly mensaje: string };

export type DisparoWeb = DisparoDeCamara<ArchivoLegible>;

export interface Tarjeta {
  readonly clave: string;
  /**
   * Cuántas veces se soltó esta foto. Cada conversión nace con la época de su tarjeta y sus noticias
   * (empezó, convertida, falló) sólo valen si la época sigue siendo ésa.
   */
  readonly epoca: number;
  readonly disparo: DisparoWeb;
  /** Los ajustes con los que se pidió esta conversión: los del momento de soltar. */
  readonly opciones: Opciones;
  readonly estado: EstadoTarjeta;
}

export type EventoTarjeta =
  | { readonly tipo: 'empezo'; readonly epoca: number }
  | { readonly tipo: 'convertida'; readonly epoca: number; readonly foto: FotoLista }
  | { readonly tipo: 'fallo'; readonly epoca: number; readonly mensaje: string }
  | { readonly tipo: 'girada'; readonly sentido: Sentido; readonly orientarJpg: OrientarJpg };

/** Soltar una foto: tarjeta nueva o, si ya existía, la misma con una época más y de vuelta a la cola. */
export function soltar(previa: Tarjeta | undefined, disparo: DisparoWeb, opciones: Opciones): Tarjeta {
  return { clave: disparo.clave, epoca: (previa?.epoca ?? 0) + 1, disparo, opciones, estado: { tipo: 'cola' } };
}

export function transicionTarjeta(t: Tarjeta, e: EventoTarjeta): Tarjeta {
  switch (e.tipo) {
    case 'empezo':
      return e.epoca === t.epoca && t.estado.tipo === 'cola' ? { ...t, estado: { tipo: 'convirtiendo' } } : t;
    case 'convertida':
      return e.epoca === t.epoca && enCurso(t.estado) ? { ...t, estado: { tipo: 'lista', foto: e.foto } } : t;
    case 'fallo':
      return e.epoca === t.epoca && enCurso(t.estado) ? { ...t, estado: { tipo: 'error', mensaje: e.mensaje } } : t;
    case 'girada':
      return t.estado.tipo === 'lista'
        ? { ...t, estado: { tipo: 'lista', foto: girarFoto(t.estado.foto, e.sentido, e.orientarJpg) } } : t;
    default:
      return nunca(e);
  }
}

function enCurso(e: EstadoTarjeta): boolean {
  return e.tipo === 'cola' || e.tipo === 'convirtiendo';
}

/** La foto de una tarjeta lista; null en cualquier otro estado. */
export function fotoDe(t: Tarjeta | undefined): FotoLista | null {
  return t && t.estado.tipo === 'lista' ? t.estado.foto : null;
}

// ---------------------------------------------------------------- lote (lo que se ve en el resumen)
/** El resumen no se lleva en contadores: se calcula de las tarjetas cada vez. */
export interface Resumen {
  readonly pendientes: number;
  readonly listas: number;
  readonly errores: number;
}

export function resumir(tarjetas: Iterable<Tarjeta>): Resumen {
  let pendientes = 0, listas = 0, errores = 0;
  for (const t of tarjetas) {
    switch (t.estado.tipo) {
      case 'cola': case 'convirtiendo': pendientes++; break;
      case 'lista': listas++; break;
      case 'error': errores++; break;
      default: nunca(t.estado);
    }
  }
  return { pendientes, listas, errores };
}

export function textoResumen(r: Resumen): string {
  const t: string[] = [];
  if (r.pendientes) t.push(`convirtiendo ${r.pendientes}…`);
  if (r.listas) t.push(`${r.listas} DNG ${r.listas === 1 ? 'listo' : 'listos'}`);
  if (r.errores) t.push(`${r.errores} con error`);
  return t.join(' · ');
}

// ---------------------------------------------------------------- exportación (.zip o carpeta)
export type Destino = 'zip' | 'carpeta';
export type Exportacion =
  | { readonly tipo: 'reposo' }
  | { readonly tipo: 'exportando'; readonly destino: Destino };

/**
 * Exportar es todo o nada: sólo cuando no queda ninguna foto por convertir, hay al menos una lista y
 * no hay otra exportación en marcha. Lo exportado es lo que había listo en el momento del clic.
 */
export function puedeExportar(r: Resumen, x: Exportacion): boolean {
  return x.tipo === 'reposo' && r.pendientes === 0 && r.listas > 0;
}

/** Por qué no se puede exportar ahora, para decírselo al usuario; null si se puede. */
export function motivoSinExportar(r: Resumen, x: Exportacion): string | null {
  if (x.tipo === 'exportando') return 'Ya hay una exportación en marcha';
  if (r.pendientes > 0) return `Espera a que terminen de convertirse ${r.pendientes === 1 ? 'la foto que falta' : `las ${r.pendientes} fotos que faltan`}`;
  if (r.listas === 0) return 'No hay ningún DNG listo';
  return null;
}

// ---------------------------------------------------------------- visor
export type Visor =
  | { readonly tipo: 'cerrado' }
  | { readonly tipo: 'abierto'; readonly clave: string; readonly que: 'dng' | 'jpg' };

export type EventoVisor =
  | { readonly tipo: 'abrir'; readonly clave: string }
  | { readonly tipo: 'alternar' }
  | { readonly tipo: 'cerrar' }
  /** Las tarjetas cambiaron: si la que se ve ya no está lista, el visor se cierra. */
  | { readonly tipo: 'tarjetas' };

export function transicionVisor(v: Visor, e: EventoVisor, tarjetas: ReadonlyMap<string, Tarjeta>): Visor {
  switch (e.tipo) {
    case 'abrir':
      return v.tipo === 'cerrado' && fotoDe(tarjetas.get(e.clave)) ? { tipo: 'abierto', clave: e.clave, que: 'dng' } : v;
    case 'alternar': {
      if (v.tipo !== 'abierto') return v;
      const foto = fotoDe(tarjetas.get(v.clave));
      if (v.que === 'jpg') return { ...v, que: 'dng' };
      return foto?.jpg ? { ...v, que: 'jpg' } : v;
    }
    case 'cerrar':
      return v.tipo === 'abierto' ? { tipo: 'cerrado' } : v;
    case 'tarjetas':
      return v.tipo === 'abierto' && !fotoDe(tarjetas.get(v.clave)) ? { tipo: 'cerrado' } : v;
    default:
      return nunca(e);
  }
}

// ---------------------------------------------------------------- ajustes (Balance y Giro)
/** Los ajustes con `clave` = `valor`; los mismos si la clave o el valor no existen (p. ej. algo viejo guardado). */
export function conOpcion(o: Opciones, clave: string, valor: string): Opciones {
  if (clave === 'balance') {
    const v = BALANCES.find(x => x === valor);
    return v && v !== o.balance ? { ...o, balance: v } : o;
  }
  if (clave === 'rotar') {
    const v = ROTARES.find(x => x === valor);
    return v && v !== o.rotar ? { ...o, rotar: v } : o;
  }
  return o;
}
