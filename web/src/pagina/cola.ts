// Cola de trabajos sobre un grupo de Workers. Es la única dueña de los Workers y de qué trabajo tiene
// cada uno; la página sólo pide y, si ya no le interesa, cancela.
//
// Trabajo:  encolado → corriendo → resuelto            (resuelto = ok | error | cancelada)
//           encolado → resuelto (cancelada: no llega a enviarse al Worker)
// Obrero:   libre ⇄ ocupado (con un trabajo); cualquiera → muerto (se quita y, si hace falta, se repone)
//
// Invariantes: un trabajo se resuelve exactamente una vez; un obrero ocupado tiene exactamente un
// trabajo y un obrero muerto no está en el grupo; una respuesta sólo vale para el trabajo que ese
// obrero tiene en curso y con su mismo id (lo demás se descarta).
import type { Datos, Peticion, Que, Respuesta, Tarea } from '../modelo/protocolo.js';

export type Resultado<K extends Que> =
  | { readonly tipo: 'ok'; readonly datos: Datos[K] }
  | { readonly tipo: 'error'; readonly mensaje: string }
  | { readonly tipo: 'cancelada' };

export interface Pedido<K extends Que> {
  readonly resultado: Promise<Resultado<K>>;
  /** Deja de interesar: si no había empezado, no se envía; si ya corre, su respuesta se descarta. */
  cancelar(): void;
}

/** 'primero' pasa por delante del lote: lo que el usuario espera mirando (visor, exportación). */
export type Prioridad = 'primero' | 'lote';

interface Trabajo {
  readonly id: number;
  readonly tarea: Tarea;
  readonly prioridad: Prioridad;
  readonly alEmpezar: (() => void) | undefined;
  /** Resuelve la promesa; null cuando ya se resolvió. */
  resolver: ((r: Resultado<Que>) => void) | null;
}
interface Obrero {
  readonly w: Worker;
  trabajo: Trabajo | null;
}

export class Cola {
  private readonly obreros = new Set<Obrero>();
  private readonly espera: Trabajo[] = [];
  private serie = 0;
  private readonly crear: () => Worker;
  private readonly maximo: number;

  constructor(crear: () => Worker, maximo: number) {
    this.crear = crear;
    this.maximo = maximo;
  }

  pedir<K extends Que>(tarea: Extract<Tarea, { que: K }>, opciones: { prioridad?: Prioridad; alEmpezar?: () => void } = {}): Pedido<K> {
    let trabajo!: Trabajo;
    const resultado = new Promise<Resultado<K>>(resolve => {
      trabajo = { id: ++this.serie, tarea, prioridad: opciones.prioridad ?? 'lote', alEmpezar: opciones.alEmpezar,
        // El id une la tarea con su respuesta, así que el resultado es el de una tarea de tipo K.
        resolver: resolve as (r: Resultado<Que>) => void };
    });
    if (trabajo.prioridad === 'primero') {
      const i = this.espera.findIndex(t => t.prioridad === 'lote');
      this.espera.splice(i < 0 ? this.espera.length : i, 0, trabajo);
    } else this.espera.push(trabajo);
    this.atender();
    return { resultado, cancelar: () => this.cancelar(trabajo) };
  }

  private resolver(t: Trabajo, r: Resultado<Que>): void {
    const resolver = t.resolver;
    t.resolver = null;
    resolver?.(r);
  }

  private cancelar(t: Trabajo): void {
    const i = this.espera.indexOf(t);
    if (i >= 0) this.espera.splice(i, 1);
    this.resolver(t, { tipo: 'cancelada' });
  }

  private atender(): void {
    while (this.espera.length) {
      let libre: Obrero | undefined;
      for (const o of this.obreros) if (!o.trabajo) { libre = o; break; }
      if (!libre) {
        if (this.obreros.size >= this.maximo) return;
        libre = this.contratar();
      }
      const t = this.espera.shift();
      if (!t) return;
      libre.trabajo = t;
      t.alEmpezar?.();
      const peticion: Peticion = { ...t.tarea, id: t.id };
      libre.w.postMessage(peticion);
    }
  }

  private contratar(): Obrero {
    const o: Obrero = { w: this.crear(), trabajo: null };
    o.w.onmessage = (e: MessageEvent<Respuesta>) => {
      const t = o.trabajo, r = e.data;
      if (!t || r.id !== t.id) return;                  // respuesta de otro tiempo: no es de este trabajo
      o.trabajo = null;
      // `datos` es el de la tarea con ese id (protocolo.ts).
      this.resolver(t, r.ok ? { tipo: 'ok', datos: r.datos } : { tipo: 'error', mensaje: r.error });
      this.atender();
    };
    const murio = (mensaje: string) => {
      if (!this.obreros.delete(o)) return;
      o.w.terminate();
      if (o.trabajo) this.resolver(o.trabajo, { tipo: 'error', mensaje });
      o.trabajo = null;
      this.atender();
    };
    // El Worker murió (sin memoria, por ejemplo): falla su trabajo, se quita del grupo y se repone.
    o.w.onerror = e => { e.preventDefault(); murio(e.message || 'el conversor se detuvo (puede faltar memoria)'); };
    o.w.onmessageerror = () => murio('el conversor devolvió un resultado ilegible');
    this.obreros.add(o);
    return o;
  }
}
