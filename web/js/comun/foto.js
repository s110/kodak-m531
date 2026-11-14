// Una foto ya convertida, como la guarda la página, y lo que se le puede hacer sin reconvertir.
// Sin DOM: la página y la prueba E2E (en Node) usan estas mismas funciones.
import { ETIQUETA_GIRO, ponerOrientacion } from './dng.js';

/**
 * Gira la foto un cuarto de vuelta: sólo cambia la etiqueta Orientation de la cabecera del DNG y la
 * del EXIF del JPG (dos bytes cada una, sin recomprimir). foto = { cabecera, jpg, giro };
 * sentido = 'izq' | 'der'; orientarJpg es el del perfil de la cámara. Devuelve el giro nuevo.
 */
export function girarFoto(foto, sentido, orientarJpg) {
  const g = (foto.giro + (sentido === 'izq' ? 1 : 3)) % 4;
  ponerOrientacion(foto.cabecera, ETIQUETA_GIRO[g]);
  if (foto.jpg) orientarJpg(foto.jpg, g);
  foto.giro = g;
  return g;
}

/** Archivos que salen de una foto: [{ nombre, partes }] (partes para un Blob o para concatenar). */
export function archivosDeFoto(foto) {
  const out = [{ nombre: `${foto.salida}.DNG`, partes: [foto.cabecera, foto.pixeles], tam: foto.cabecera.length + (foto.pixeles.size ?? foto.pixeles.length) }];
  if (foto.jpg) out.push({ nombre: `${foto.salida}.JPG`, partes: [foto.jpg], tam: foto.jpg.length });
  return out;
}
