# Reveal (`web/`): máquinas de estado

Qué estado tiene la página, quién lo guarda, qué transiciones valen y qué defectos tenía el código anterior
(commit `f0f7a0c`, `web/js/app.js`), donde ese estado estaba repartido entre variables sueltas, atributos del
DOM y promesas. El código está en `web/src/`; la prueba que recorre estas tablas en Chrome es `tools/e2e_web.py`.

## Reglas comunes

- **Un dueño por estado.** Todo el estado de la página vive en cinco variables de `pagina/app.ts`
  (`opciones`, `tarjetas`, `exportacion`, `visor`, `arrastrando`) y en la cola de Workers (`pagina/cola.ts`).
- **Las transiciones son funciones puras** de `modelo/estado.ts` sobre uniones discriminadas, con `switch`
  exhaustivo (`nunca(x: never)`): un estado o evento nuevo sin tratar no compila.
- **Una transición que no está en la tabla no hace nada**: devuelve el mismo valor que recibió.
- **El DOM es sólo salida.** Lo escriben las funciones `pintar…` a partir del estado; nunca se lee para decidir.
  Los atributos `data-estado`, `data-epoca`, `data-giro`, `data-exportando` y `data-foto` son esa salida.
- **Una `Foto` no se modifica**: girar devuelve otra (`nucleo/comun/foto.ts`). Quien tiene una en la mano
  (una exportación a medias) sigue viendo lo mismo.
- **Fichas de generación**, dos capas: el `id` de cada petición al Worker (una respuesta con otro `id` se
  descarta en la cola) y la `epoca` de cada tarjeta (una noticia de otra época no cambia la tarjeta).

## 1. Tarjeta (una foto)

Dueño: `tarjetas: Map<clave, Tarjeta>`; sólo escribe `cambiar()`. Transición: `soltar()` y `transicionTarjeta()`.

| Estado | Evento | Pasa a | Nota |
|---|---|---|---|
| (no existe) | soltar | `cola`, época 1 | guarda los ajustes de ese momento |
| cualquiera | soltar | `cola`, época + 1 | reemplaza: se cancela su conversión anterior y se pierde su giro |
| `cola` | empezó (misma época) | `convirtiendo` | |
| `cola`, `convirtiendo` | convertida (misma época) | `lista(foto)` | |
| `cola`, `convirtiendo` | falló (misma época) | `error(mensaje)` | |
| `lista` | girada | `lista(otra foto)` | copia con la etiqueta cambiada |
| cualquiera | noticia de otra época | (igual) | resultado viejo |
| `cola`, `convirtiendo`, `error` | girada, ampliar, descargar | (igual) | |

Invariantes: una tarjeta por `clave`; la época sólo crece; hay foto sólo en `lista`; los tres botones están
habilitados si y sólo si el estado es `lista`.

## 2. Lote y resumen

No hay contadores: `resumir(tarjetas)` cuenta fotos pendientes (`cola` + `convirtiendo`), listas y con error
cada vez que hace falta, y `textoResumen()` lo escribe. Invariante: el resumen dice lo que hay en las tarjetas.

## 3. Cola de Workers (`pagina/cola.ts`)

| Qué | Estados | Transiciones |
|---|---|---|
| Trabajo | encolado, corriendo, resuelto (ok, error o cancelada) | encolado → corriendo → resuelto; encolado → resuelto (cancelada, no se envía); corriendo → resuelto (cancelada: el Worker termina y su respuesta se descarta) |
| Obrero | libre, ocupado, muerto | libre ⇄ ocupado; cualquiera → muerto (`error` o `messageerror`): falla su trabajo, sale del grupo y se repone cuando haga falta |

Dos prioridades: `primero` (revelado del visor, CRC de la exportación) pasa por delante de `lote` (conversiones).
Invariantes: un trabajo se resuelve exactamente una vez; un obrero ocupado tiene un solo trabajo; un obrero
muerto no está en el grupo; una respuesta sólo vale para el trabajo en curso de ese obrero y con su `id`.

## 4. Ajustes (Balance, Giro)

Dueño: `opciones` (objeto que se sustituye, no se modifica). `conOpcion()` ignora claves o valores que no existen
(algo viejo en `localStorage`). **Semántica: los ajustes valen para lo que se suelte después.** Cada tarjeta lleva
los del momento en que se soltó; cambiar un ajuste con un lote en marcha no toca ese lote.

## 5. Exportación ("Descargar todo", "Guardar en carpeta")

Dueño: `exportacion`. Estados: `reposo`, `exportando(zip | carpeta)`.

| Estado | Evento | Condición | Pasa a |
|---|---|---|---|
| `reposo` | clic | ninguna pendiente y alguna lista | `exportando`, con las fotos listas en ese instante |
| `reposo` | clic | queda alguna pendiente, o ninguna lista | (igual) y aviso con el motivo |
| `exportando` | clic en cualquiera de los dos | | (igual) |
| `exportando` | termina, falla o se cancela el selector | | `reposo` |

**Semántica decidida: exportar es todo o nada.** A mitad de un lote los dos botones están deshabilitados, para
que nadie se lleve un .zip incompleto creyendo que es el lote. Mientras tanto cada foto lista se puede bajar con
su botón. **Lo exportado es lo que había al hacer clic**: girar una tarjeta o soltar más archivos durante la
exportación no la cambia y vale para la siguiente. Invariantes: los botones están habilitados si y sólo si se
puede exportar; el rótulo "Preparando…" / "Guardando…" aparece sólo en `exportando`; una exportación a la vez.

## 6. Visor

Dueño: `visor`. Estados: `cerrado`, `abierto(clave, dng | jpg)`. Transición: `transicionVisor()`.

| Estado | Evento | Pasa a |
|---|---|---|
| `cerrado` | abrir una tarjeta `lista` | `abierto(dng)` |
| `cerrado` | abrir una tarjeta en otro estado | (igual) |
| `abierto(dng)` | espacio, si la foto tiene JPG | `abierto(jpg)` |
| `abierto(jpg)` | espacio | `abierto(dng)` |
| `abierto` | Esc o clic | `cerrado` |
| `abierto` | su tarjeta deja de estar `lista` (se soltó otra vez) | `cerrado` |
| `abierto` | su tarjeta gira | (igual; se repinta con la foto nueva) |

Lo que el visor toma prestado y suelta cada vez que repinta: el revelado pendiente (se cancela) y la URL del JPG
(se revoca). Invariantes: el visor abierto enseña una foto `lista`; como mucho una URL viva, y sólo mientras se
ve el JPG; con el visor abierto, Esc y espacio no llegan a lo que hay debajo.

## 7. URL de objeto

| Dueño | Se crea | Se revoca |
|---|---|---|
| visor | al pasar a `abierto(jpg)` | al repintar el visor (otra foto, DNG, cerrar, tarjeta reemplazada) |
| cada descarga (`bajarBlob`) | al hacer clic | 60 s después |

Las tarjetas no tienen URL: su miniatura es un `canvas`.

## 8. Aviso y arrastre

- Aviso: oculto ⇄ visible; un aviso nuevo reemplaza al anterior y reinicia su reloj (`relojAviso`, 3,2 s).
- Arrastre: `arrastrando` pasa a cierto con `dragover` **de archivos**, y a falso al salir de la ventana o soltar.
- Las tandas soltadas se leen (las carpetas, de forma asíncrona) y se reciben de una en una, en orden.

## Defectos del código anterior y cómo reproducirlos

Sobre `f0f7a0c`. "Mutación" indica que `tools/e2e_web.py --mutaciones` reintroduce el defecto en el código nuevo y
comprueba que la prueba lo ve; los demás salen de leer el código anterior.

| # | Defecto | Reproducción | Arreglo |
|---|---|---|---|
| 1 | El resumen contaba trabajos, no fotos, y las conversiones viejas en cola se ejecutaban igual | Soltar una carpeta de 8 fotos y soltarla otra vez enseguida: "convirtiendo 16…" con 8 tarjetas, el doble de espera, y exportar bloqueado hasta acabar también las viejas | Resumen derivado de las tarjetas; soltar cancela la conversión anterior (mutación) |
| 2 | Soltar otra vez la foto que se estaba viendo rompía el visor | Ampliar una foto, soltar encima sus mismos archivos y pulsar espacio: `TypeError` (`visorFoto.datos` es `null`); el visor sigue abierto con una foto que ya no existe y la URL del JPG queda viva | El visor se cierra y suelta su URL (mutación) |
| 3 | Girar durante una exportación daba un .zip incoherente | Con varias fotos listas, "Descargar todo" y girar ↺ la primera mientras dice "Preparando…": el CRC se calculó con la cabecera de antes y el archivo lleva la de después (entrada dañada), o el DNG va con un giro y su JPG con otro. Igual en "Guardar en carpeta" | `Foto` inmutable; se exporta la del clic (mutación: el .zip sale con «CRC que no corresponde: 101_1988.DNG») |
| 4 | El botón de exportar se rehabilitaba a media exportación | "Descargar todo" y, mientras prepara, soltar cualquier archivo (`contar()` rehabilita el botón); segundo clic: dos .zip y el botón queda rotulado "Preparando…" para siempre. También se podían lanzar .zip y carpeta a la vez | Estado `exportando` explícito; botones y rótulo se pintan de él |
| 5 | "Guardar en carpeta" guardaba lo que hubiera al cerrar el selector | Clic en "Guardar en carpeta", girar una foto con el selector abierto, elegir carpeta: se guarda la girada | Se toman las fotos antes de abrir el selector |
| 6 | El visor esperaba detrás de todo el lote | Soltar 60 fotos y ampliar la primera que termine: la vista a media resolución no llega hasta que acaban las 60 (cola única, por orden de llegada). El CRC del .zip, igual | Prioridad `primero` (mutación) |
| 7 | Un Worker que fallaba estando libre seguía en la lista de libres | Latente: `w.dispatchEvent(new ErrorEvent('error'))` sobre un Worker libre; el siguiente trabajo se le envía ya terminado y su tarjeta queda "convirtiendo" para siempre, con exportar bloqueado. Tampoco se atendía `messageerror` | Un obrero muerto sale del grupo en un solo sitio |
| 8 | Girar con el teclado con el visor abierto | Ampliar una foto, Tab hasta ↺ de su tarjeta (el foco no queda atrapado) y Enter: la tarjeta gira y el visor no | El visor se repinta cuando cambia la foto de su tarjeta |
| 9 | Espacio con el visor abierto llegaba a la zona de soltar | Con el foco en la zona de soltar y el visor abierto, espacio alterna DNG / JPG y además abre el selector de archivos | Teclas del visor en fase de captura |
| 10 | Arrastrar algo que no son archivos | Seleccionar texto de la página y arrastrarlo: la zona se ilumina y al soltar sale "Nada que convertir" | Sólo cuenta un arrastre de archivos |
| 11 | Dos tandas soltadas seguidas podían recibirse en orden inverso | Soltar una carpeta grande y enseguida un archivo de una foto que está en ella: la carpeta tarda más en leerse y su versión pisa a la del archivo, que se soltó después | Lecturas en serie |
| 12 | "Guardar en carpeta" nacía habilitado en el HTML | Sólo visible un instante al cargar (lo encontró el invariante de la prueba) | `disabled` en `index.html` |

No era un defecto: los ajustes ya se copiaban al soltar. Quedó escrito como semántica (§4) y con prueba.

Límite conocido, sin cambiar: la identidad de una foto es cámara + número (`101` + `2037`). Si en una misma tanda
vienen dos carpetas con archivos del mismo número (dos tarjetas distintas), se tratan como una sola foto y el
`O` de una puede emparejarse con el JPG de la otra. Arreglarlo cambia el contrato de `agrupar` y los nombres
dentro del .zip.

## Lado Python (anotado, sin cambios)

`tools/conversor_ui.py`
- **Importación** (`Conversor.imp`): `reposo → corriendo → terminada(código)`. Explícita y con cerrojo al
  entrar. El hilo escribe en su propio diccionario, que hace de ficha de generación.
- **Carpeta de entrada** (`self.entrada`), estado implícito en el disco: lo subido se queda ahí hasta cerrar.
  `convertir` empareja el RAW con el JPG *que haya* con ese número, aunque sea de una subida anterior: subir
  `101O2037.RAW` + `101_2037.JPG`, y más tarde otro `101O2037.RAW` sin JPG (tarjeta formateada, número
  repetido), lo convierte con el JPG viejo (balance y copia del JPG equivocados).
- **Dos conversiones de la misma foto a la vez** (dos pestañas, o soltar otra vez mientras convierte) escriben
  el mismo `<dng>.parcial`; `girar` sobre ese DNG mientras se reemplaza trabaja sobre un archivo que desaparece.
  No hay cerrojo por foto.
- **Fecha de salida** (`fecha()`): se calcula en cada llamada; un lote que cruza la medianoche queda en dos carpetas.
- **Instancia única** (`ESTADO`: puerto, token, pid): `no hay → corriendo → cerrada`; un archivo viejo se
  detecta porque la petición falla. Correcto.

`tools/auto_vault.py`
- Por RAW: `nuevo → convertido | saltado (el DNG ya existe) | error`, y los tres terminan en `visto`. Un solo
  proceso (`flock`), estado guardado tras cada foto: una caída a medias sólo repite lo que estaba en vuelo.
- `error → visto` es definitivo a propósito (no reintentar en cada respaldo), así que un fallo pasajero (disco
  lleno) deja la foto sin convertir hasta borrar su línea del estado.
- `saltado` se decide por nombre y carpeta del día: si el mismo número viene de otro disparo (tarjeta
  formateada) el mismo día, se da por hecho y no se convierte.
