# Uso diario: disparar en RAW con la M531 y revelar en el Mac

Guía corta. Los detalles y las mediciones están en `NOTAS.md`; los pasos de cada kit, en `sd_kit/PASOS.md`.

## 1. Qué kit poner en la SD

Los scripts viven en `Batch/` de la SD y `Batch/BatchScripts.txt` dice cuáles corren al encender.
Todo queda en RAM: apagando la cámara vuelve a fábrica.

| Para qué | `BatchScripts.txt` | Qué sale |
|---|---|---|
| **Uso normal con RAW** | `M4L`, `M4Q`, `M4W` (copiar `BatchScripts_M4LQW.txt`) | RAW lineal de 12 bits (21,2 MB), JPG correcto, revisión correcta |
| RAW con el JPG y el balance automático de fábrica | `P8` (lista `P8`, o `P8` + `EE0` de `sd_kit/fase3`) | RAW de 8 bits con curva (14,1 MB), JPG y revisión de fábrica |
| Sólo JPG | SD sin `Batch/`, o cámara sin SD de scripts | JPG de fábrica |

Los dos RAW guardan la misma imagen: mismo ruido, mismo rango y mismo tope de luces (medido, ver
`NOTAS.md`, "¿Sirven los 12 bits?"). La diferencia práctica está en el JPG: con `P8` la cámara calcula su
balance automático; con `M4L` sin flash no lo calcula y el JPG sale cálido salvo que elijas un preset.

## 2. Cómo disparar

- **Una foto por vez.** Espera a que termine de guardar y vuelva la vista en vivo antes de la siguiente.
- **Sin zoom digital.** El zoom óptico sí.
- **Apaga antes de cambiar de kit** y antes de sacar la SD. No mezcles kits en una misma sesión.
- **Interior con luz cálida: preset Tungsteno** en el menú de balance de blancos. Con M4L y sin flash el
  automático queda en un valor fijo. El preset arregla el JPG; el DNG se balancea solo con la escena.
- Con flash la cámara sí calcula su balance, en cualquier kit.
- Cámara nivelada. Apuntando hacia abajo, el sensor de orientación gira el JPG aunque la cámara esté
  horizontal.
- Si una zona importante sale quemada en la revisión, baja la exposición (−0,3 a −1 EV) y repite: el RAW
  guarda entre 0,2 y 1 EV por encima del blanco del JPG, y nada por encima de su propio tope.

## 3. Importar

Con la SD en el lector del Mac:

```sh
cd /Volumes/Datos/proyectos/kodak-m531
./importar
```

Hace todo: copia los RAW, JPG y `.LOG` nuevos a `dump/<fecha>/`, verifica cada copia con SHA-256,
convierte cada RAW a DNG en `~/Pictures/m531_dng/<fecha>/` con su JPG al lado y enseña un resumen.
Lo que ya estaba importado se salta. La SD sólo se lee. Después, expulsa la SD desde Finder.

Opciones útiles:

| Opción | Para qué |
|---|---|
| `--verticales 2031,2034-2036` | esas fotos se tomaron con la cámara en vertical: DNG y JPG salen de pie |
| `--rotar camara` | usar en todas el giro que la cámara dio al JPG |
| `--balance camara` | usar el preset o el balance de flash de la cámara en vez del de la escena |
| `--abrir` | abrir la carpeta en darktable al terminar |
| `--origen CARPETA` | importar desde otra carpeta (una copia de la SD, por ejemplo) |

Por omisión todo sale **apaisado, como el sensor**. La cámara gira el JPG según su sensor de orientación
y en las tomas de prueba lo giró casi siempre, con la cámara horizontal o vertical, así que su giro no
sirve de guía. El RAW siempre es apaisado; el importador deja el JPG de `~/Pictures` igual que el DNG
cambiando sólo su etiqueta de orientación (la copia de `dump/` queda intacta).

Girar después, sin reconvertir (cambia dos bytes del archivo):

```sh
.venv/bin/python tools/m531raw.py rotar --rotar izq ~/Pictures/m531_dng/<fecha>/101_2031.DNG ~/Pictures/m531_dng/<fecha>/101_2031.JPG
```

`izq` es el giro que aplica la cámara; `der` el contrario; `180` cabeza abajo; `no` vuelve a apaisado.

Una carpeta ya copiada (sin SD) se convierte con
`.venv/bin/python tools/convertir_carpeta.py ORIGEN DESTINO [--sobrescribir]`.

## 4. Abrir y revelar

**Vista Previa / Finder.** Doble clic en el DNG. Sirve para mirar y exportar; el color sale parecido al
JPG de la cámara.

**darktable 5.6** (`./importar --abrir`, o arrastrar la carpeta a darktable):

1. *Balance de blancos*: viene "como se tomó" con el balance que calculó el importador. Si un blanco no
   sale neutro, usa el cuentagotas del módulo sobre algo blanco o gris.
2. *Exposición*: sube o baja a gusto. Subir sombras hasta +3 EV es razonable en ISO 64; más allá manda
   el ruido y aparece un velo violeta (el negro del RAW viene recortado en 0).
3. *Reconstrucción de luces*: recupera lo que el JPG quemó y el RAW no.
4. Reducción de ruido: darktable no trae perfil de ruido de esta cámara, así que ajústala a mano y con
   poca fuerza. Activa *píxeles calientes*: el RAW trae algunos.
5. Exporta a JPG o TIFF.

## 5. Problemas comunes

| Síntoma | Causa y arreglo |
|---|---|
| `No encuentro la SD` | La tarjeta no está montada o tiene otro nombre: `./importar --origen "/Volumes/<nombre>/DCIM/101KM531"` |
| Un blanco sale con dominante | Cuentagotas de darktable sobre el blanco. Si la escena no tiene nada claro y neutro y elegiste un preset: `--balance camara` |
| Foto vertical sale acostada | `m531raw.py rotar --rotar izq …` (o `der`), o `--verticales` al importar |
| Altas luces rosadas | No deberían salir (tope del RAW en 3950). Si salen, baja el punto blanco en el módulo de punto negro/blanco raw de darktable |
| `no se pudo convertir` en el resumen | RAW truncado (cámara apagada o colgada al guardar). La copia queda en `dump/<fecha>/`; las demás fotos se convierten igual |
| RAW sin JPG | Normal en modo 3 o si la cámara se colgó: el DNG se hace igual, con el balance de la escena |
| El JPG de la cámara sale naranja | M4L sin flash con balance automático: usa el preset Tungsteno, o quédate con el DNG |
| La revisión sale con ruido o verdosa | Falta `M4Q` (ruido) o `M4W` (verde) en `BatchScripts.txt` |
| La cámara se cuelga | Batería y SD fuera unos segundos. Revisa el `.LOG` del script en `dump/<fecha>/` |
