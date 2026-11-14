// Perfil de cámara: Kodak EasyShare M531 (RAW de fábrica sacado con scripts en la SD).
// Aquí está lo que es propio de esta cámara: qué archivos son suyos y cómo se emparejan, cómo se
// decodifica el RAW, de dónde sale el balance, qué pone el DNG en marca y modelo, y cómo se describe
// el formato. El trabajo de fondo está en m531raw.js (port de tools/m531raw.py).
import { bytesPixeles, cabeceraDng, ETIQUETA_GIRO } from '../comun/dng.js';
import { decodificarJpeg, TRUNCADO } from '../comun/jpeg.js';
import { CCM_M531, convertir, matrices_dng, Motivo, orientar_jpg } from './m531raw.js';

// 101O2037.RAW (campo principal), 101B2037.RAW (segundo campo, si lo hay) y 101_2037.JPG
const RE_ARCHIVO = /^(\d{3})([Ob_])(\d{4})\.(RAW|JPG)$/i;
const FORMATOS = { 28200960: 'modo 3, 16 bits', 14100480: 'modo 0 (P8), 8 bits con curva', 17625600: 'modo 2, 10 bits' };

function descripcion(info) {
  if (info.modo4 === 'lineal12') return 'M4L, 12 bits lineales';
  if (info.modo4 === 'curva10') return 'modo 4 (P9), 10 bits con curva';
  return FORMATOS[info.tamanos[0]] || `${info.packing} ${info.ancho}x${info.alto}`;
}

/** ¿El JPG se puede leer entero? (la cámara lo deja truncado si se dispara encima) */
function jpgEntero(jpg) {
  try {
    decodificarJpeg(jpg, { soloValidar: true });
    return true;
  } catch (e) {
    // Un JPG de un tipo que este decodificador no admite no es de la cámara, pero tampoco está roto.
    return e.message !== TRUNCADO && !/no es un JPEG|sin marcador|sin SOF/.test(e.message);
  }
}

export default {
  id: 'm531',
  nombre: 'Kodak EasyShare M531',
  corto: 'Kodak M531',
  /** Texto para la zona de soltar: qué archivos espera. */
  ayuda: '101O####.RAW con su 101_####.JPG',

  /**
   * De una lista de archivos ({ name }) aparta los disparos de esta cámara.
   * Devuelve [{ clave, titulo, salida, campos: [archivo…], jpg: archivo | null }]; los archivos que no
   * aparecen en ningún disparo quedan para otros perfiles.
   */
  agrupar(archivos) {
    const grupos = new Map();
    for (const f of archivos) {
      const m = RE_ARCHIVO.exec(f.name);
      if (!m) continue;
      const clave = m[1] + m[3];
      const g = grupos.get(clave) || { O: null, B: null, jpg: null, titulo: `${m[1]}_${m[3]}` };
      const letra = m[2].toUpperCase(), ext = m[4].toUpperCase();
      if (ext === 'RAW' && letra === 'O') g.O = f;
      else if (ext === 'RAW' && letra === 'B') g.B = f;
      else if (ext === 'JPG' && letra === '_') g.jpg = f;
      grupos.set(clave, g);
    }
    const disparos = [];
    for (const [clave, g] of [...grupos].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
      if (!g.O) continue;                               // sin el campo principal no hay foto
      disparos.push({ clave, titulo: g.titulo, salida: g.titulo, campos: g.B ? [g.O, g.B] : [g.O], jpg: g.jpg });
    }
    return disparos;
  },

  /**
   * Convierte un disparo. campos y jpg son Uint8Array con el contenido de los archivos.
   * opciones = { balance: 'auto' | 'camara', rotar: 'no' | 'camara' }.
   * Devuelve { cabecera, pixeles, jpg, info, formato, balance, giro, revelado }: el DNG es
   * cabecera + pixeles; jpg es la copia del JPG con la misma orientación (o null si falta o está roto);
   * revelado son los parámetros para la vista previa. Lanza Error con el motivo si no se puede.
   */
  convertir(campos, jpg, opciones = {}) {
    if (jpg && !jpg.length) jpg = null;
    const { img, info, neutro } = convertir(campos, jpg, { balance: opciones.balance || 'auto', rotar: opciones.rotar || 'no',
      nombres: opciones.nombres || null });
    const [cm1, cm2, fm] = matrices_dng(CCM_M531);
    const cabecera = cabeceraDng({
      ancho: img.w, alto: img.h, cfa: info.cfa, negro: info.negro, blanco: info.blanco, neutro,
      orientacion: info.orientacion, marca: 'Kodak', modelo: 'EasyShare M531', modeloUnico: 'Kodak EasyShare M531',
      software: 'm531raw.py', cm1, cm2, fm, iluminante1: 17, iluminante2: 21,    // A y D65
    });
    let jpgSalida = null;
    if (jpg && jpg.length > 10_000 && jpgEntero(jpg)) {
      jpgSalida = jpg.slice();
      orientar_jpg(jpgSalida, info.giro);
    }
    return {
      cabecera, pixeles: bytesPixeles(img.d), jpg: jpgSalida, info, formato: descripcion(info), balance: info.balance,
      giro: info.giro,
      revelado: { ancho: img.w, alto: img.h, cfa: info.cfa, negro: info.negro, blanco: info.blanco, neutro, ccm: CCM_M531 },
    };
  },

  /** Gira el JPG de la cámara (sólo su etiqueta EXIF) para que se vea como el DNG. */
  orientarJpg(jpg, giro) {
    return orientar_jpg(jpg, giro);
  },
  ETIQUETA_GIRO,
  esMotivo: e => e instanceof Motivo,
};
