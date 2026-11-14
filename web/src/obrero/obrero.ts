// Worker: aquí corre todo lo pesado (leer los archivos, convertir, revelar la vista previa, CRC del
// .zip) para que la página no se trabe. Los archivos se leen del disco del usuario y no salen de aquí.
// Una petición, una respuesta con su mismo id; lo que lanza una tarea vuelve como { ok: false }.
import { textoDeError } from '../modelo/protocolo.js';
import type { Peticion, Respuesta } from '../modelo/protocolo.js';
import { ejecutar } from '../modelo/tareas.js';

declare const self: DedicatedWorkerGlobalScope;

self.onmessage = async (e: MessageEvent<Peticion>) => {
  const m = e.data;
  let respuesta: Respuesta, transferir: ArrayBuffer[] = [];
  try {
    const hecho = await ejecutar(m);
    respuesta = { id: m.id, ok: true, datos: hecho.datos };
    transferir = hecho.transferir;
  } catch (err) {
    respuesta = { id: m.id, ok: false, error: textoDeError(err) };
  }
  self.postMessage(respuesta, transferir);
};
