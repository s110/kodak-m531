# Pasos con la SD de la Kodak M531

Todo lo de aquí es de nivel 1 o 2 (ver ../REVERSIBILIDAD.md): nada se escribe en la NAND.
Antes de empezar: batería cargada. Cámara fuera del USB salvo donde se indique.

## Paso 0 — Respaldo de la SD (en el Mac)
1. Saca la SD de la cámara y ponla en el lector del Mac.
2. Claude copia la SD entera a `dump/sd_original/` con SHA-256 (fotos incluidas).

## Paso 1 — Kit fase 1
1. Claude corre `tools/check_scripts.py sd_kit/fase1/Batch`, copia `sd_kit/fase1/*` a la raíz de la SD
   con `cp -X` (sin metadatos de macOS), corre `dot_clean` sobre la SD, vuelve a correr el verificador
   **sobre la copia en la SD** y compara hashes con el kit.
2. Expulsa la SD, ponla en la cámara y enciéndela.
3. Anota (o fotografía) qué aparece al arrancar: "P1 OK", dos números (P4: 0 y 1),
   "P5 == OK/NO" y "P5 != OK/NO".
   - Si no aparece nada, el arranque automático no corrió. Puede ser la precondición del búfer de
     128 KB (ver NOTAS.md) y no la falta de soporte: los logs de `Batch/` lo dirán.

## Paso 2 — Menú oculto y volcados de la NAND Tool (sólo opciones "Dump")
Kit, pasos detallados y lista de control: `nand_dump/LEEME.txt` y `nand_dump/LISTA.md` (sesión sin
scripts: sin `Batch/`). A1 y E1 escriben dos archivos cada una: en total vuelven 11 archivos.
1. Con la carpeta `HiddenMenu` en la SD: Menu → Setup → Format → en la pantalla de confirmación
   (sin confirmar), **mantener DELETE y pulsar DERECHA**. Debe abrir "HIDDEN MENU".
2. FIRMWARE VERSION: anota BOOT, MAIN, CamOS, IQLib, BFN (o foto con el celular).
3. NAND TOOL → ejecuta, una por una, **sólo** estas opciones:
   A1 Calibration.dmp · B3 MainCode.dmp · C1 BootCode.dmp · D1 NANDPartition.txt ·
   E1 CameraParam.dmp · F1 NANDReserved.dmp · G1 NANDP1.dmp · I4 BFNSetting.txt · I5 BootNANDBase.dmp
4. **No toques ninguna otra opción** (borran o reescriben la NAND).
5. Apaga, saca la SD y tráela al Mac. Claude guarda los volcados con hash en dos lugares, corre
   `tools/verificar_volcados.py` (0 errores) y reconstruye el `KM531.FW` de fábrica
   (`tools/km531fw.py info` debe dar "el firmware lo acepta").

## Paso 3 — Primera foto RAW
1. Con el kit en la SD, enciende (P4 deja activo el RAW hasta apagar).
   Si los scripts no corrieron solos: menú oculto → DEBUG → SaveCCDRawOnTake → On.
2. Toma 3 fotos: una carta gris o pared blanca con luz de día, una escena con detalle, una con poca luz.
3. Trae la SD: aparece un `101O####.RAW` junto a cada JPG.
4. Claude convierte la carpeta con `tools/convertir_carpeta.py` (DNG con balance por foto).

## Paso 4 — Fase 2 (sólo si P4 y P5 funcionaron con la sintaxis usada)
1. La fase 2 **reemplaza** `Batch/` de la fase 1 (no se mezclan: MEMRW debe correr antes de que
   cualquier otro script ejecute código de la misma línea de caché, `0x2d6600–0x2d663f`).
2. MEMRW usa `peek16`/`poke16` y el vaciado de caché, que todavía no corrieron en la cámara:
   va después de que EE0 (fase 3) confirme `IF` y `poke32`. Se regenera con `tools/patch2srt.py`.
3. Encender: debe verse "MEMRW OK" y "MEMRWT OK". Apagar y sacar la batería: el parche desaparece.

## Paso 5 — Fase 3: JPG sin realce (P8 + EE0)
1. Claude corre el verificador sobre `sd_kit/fase3/Batch` y copia a `Batch/` de la SD sólo
   `BatchScripts.txt` (P8, EE0), `P8.srt` y `EE0.srt`; verifica la copia y compara hashes.
2. Foto A con el kit anterior (P8 solo) y foto B con P8 + EE0: misma escena con detalle fino, ISO
   fijo 80 o 100, Sharpness Normal. Detalle en `fase3/LEEME.txt`.
3. `Batch/EE0.LOG` debe decir `VERIFY: 4473808` y luego `VERIFY: 4472856`.
4. Si la cámara se congela al encender: sacar batería y SD, quitar EE0 de `BatchScripts.txt`.
   EE0 es el primer script con `IF` y con `poke32` que corre en la cámara.
5. Todas las bandas de ISO: `BatchScripts.txt` = contenido de `fase3/Batch/BatchScripts_EET.txt`
   (P8, EET, EETV) más los tres `.srt`. Esperado: `EET.LOG` con una línea `VERIFY: 4472856` y
   `EETV.LOG` con once. Foto sin flash con ISO ≥ 160, contra una con P8 solo de la misma escena.
   Antes de copiar: `python3 -I tools/e2e_scripts.py` (16 casos) además del verificador.

## Paso 6 — Modo 3 sin cuelgue (experimental; EE0 ya corrió, así que se puede probar)
Requisitos: batería cargada, mismos ajustes de la cámara que en las fotos de modo 4 (P9), y ninguna
otra prueba en la misma sesión (M3F2 va **solo**).
1. Claude deja en `Batch/` de la SD **sólo** dos archivos: `M3F2.srt` y `BatchScripts.txt`, este
   último copiado de `fase1/Batch/BatchScripts_M3F2.txt` (una línea `M3F2`, CRLF). Borra de `Batch/`
   los `.LOG` y `.srt` anteriores. Copia con `cp -X`, `dot_clean`, verificador sobre la copia en la
   SD (debe decir `OK`) y comparación de hashes con el kit.
2. Enciende. Espera a que termine "Script / Run…".
3. Toma **una** foto de una escena normal y espera a que termine de guardar (vuelve la vista en
   vivo; deja pasar además unos 10 s: son dos archivos grandes). No dispares mientras guarda: una captura con la
   anterior en proceso tomaría la ranura 1 del pool 8, que queda fuera de la SDRAM.
4. Si la cámara sigue respondiendo, toma la segunda (la que colgaba sin el arreglo) y espera;
   después la tercera. Apaga con el botón y trae la SD.
5. Esperado en `Batch/M3F2.LOG`, entre las líneas "starts here" y "ends here":
   `VERIFY: 252054531`, `VERIFY: 235211523`, `VERIFY: 151391235`, `VERIFY: 134548227`, `VERIFY: 3`.
   Por foto: `101O####.RAW` de 28.200.960 B (16 bits, 12 útiles) y un JPG **con ruido** de tamaño
   normal (no de 224 B); la revisión en pantalla también se ve como ruido.
6. Cómo leer un resultado distinto:
   - Una o dos líneas `VERIFY` y la cámara normal (RAW no aparece): una guardia no coincidió y el
     script terminó sin escribir nada. Si la primera línea es `151391235`, la tabla ya estaba
     parcheada (la RAM no se reinició): sacar la batería unos segundos y repetir.
   - Tres o cuatro líneas y sin `VERIFY: 3`: la relectura no coincidió; el modo quedó en 0.
   - JPG de 224 B: el IRP siguió rechazando la foto; abrirlo como texto y anotar `IRPTask[...]`.
   - La cámara se congela (al encender o tras una foto): batería y SD fuera, traer la SD tal como
     quedó. Nada queda escrito en la cámara. Para volver a usarla, quitar `Batch/` de la SD.
7. Al terminar, Claude guarda la SD en el siguiente `dump/rawN` con `SHA256SUMS` y restaura el `Batch/` anterior.

## Paso 7 — Pantalla y revisión correctas con RAW de 12 bits (experimental: M3V, luego M4L; M2V de reserva)
Análisis y predicciones: `../NOTAS.md`, sección "Pantalla, revisión y JPG correctos con RAW de 12 bits".
Cada script va **solo**: en `Batch/` de la SD quedan únicamente `<nombre>.srt` y `BatchScripts.txt`
(copia de `fase1/Batch/BatchScripts_<nombre>.txt`). Preparación igual que en el paso 6.1: borrar
`.LOG` y `.srt` anteriores, `cp -X`, `dot_clean`, verificador sobre la SD (`OK`), hashes contra el
kit. Antes: `python3 -I tools/e2e_scripts.py` (26 casos). Quickview de la cámara en **On**.
Entre un script y otro: apagar y sacar la batería unos segundos. Una foto por vez, esperando el guardado.

### 7a — M3V (modo 3; sólo primitivas ya probadas)
1. Encender y esperar "Script / Run…". Mirar la pantalla **antes de disparar**: debe verse la
   escena normal (con M3F2 salía rojiza/verde).
2. Dos fotos, esperando el guardado de cada una. Apagar y traer la SD.
3. `Batch/M3V.LOG`: `VERIFY: 252054531`, `VERIFY: 235211523`, `VERIFY: 151391235`,
   `VERIFY: 50662147`, `VERIFY: 3`.
4. Esperado: vista en vivo normal antes y después de cada foto; revisión tras el disparo con ruido;
   por foto un `101O####.RAW` de 28.200.960 B y ningún JPG (como M3F2).
5. Si la vista sigue con ruido, la tabla `0x1286dc` no es la de la vista en vivo: anotarlo y no
   seguir con 7b hasta revisar el análisis.

### 7b — M4L (modo 4 lineal de 12 bits; estrena peek16/poke16 y cambia una instrucción)
1. Encender y esperar "Script / Run…". La pantalla debe verse normal.
2. Foto 1: escena con zonas claras (pared blanca, ventana). Esperar el guardado. Foto 2 y foto 3:
   escenas normales. Apagar y traer la SD.
3. `Batch/M4L.LOG`: `VERIFY: 8`, `VERIFY: 30757`, `VERIFY: 3`, `VERIFY: 28712`, `VERIFY: 4`.
4. Esperado por foto: revisión en pantalla normal, JPG normal (sin tinte rosado) y `101O####.RAW`
   de 21.150.720 B con 12 bits lineales (máximo por encima de 1020; hasta 4095 en zonas quemadas).
   Convertir con `tools/m531raw.py dng … --packing p12_lsb --width 4320 --cfa GBRG --black 0 --white 4095`.
5. Cómo leer un resultado distinto:
   - Cámara congelada al encender: batería y SD fuera. `M4L.LOG` vacío o sin `VERIFY`: falló la
     primera llamada a `peek16`. Nada queda escrito en la cámara.
   - Una o dos líneas y cámara normal: una guardia no coincidió, no se escribió nada. Si la primera
     es `3`, la RAM no se reinició: sacar la batería y repetir.
   - Log completo, JPG rosado y RAW con máximo ≤ 1020: corrió la instrucción vieja (cachés). El
     resultado equivale a P9 con la pantalla arreglada. Si la primera foto sale así y las
     siguientes bien, anotarlo: es el mismo efecto.
   - Log completo y JPG oscuro, quemado o con dominante: guardar RAW y JPG tal cual para medir.
6. No usar el modo 0 con M4L cargado: apagar primero.

### 7c — M2V (reserva: modo 2, 10 bits; sin tocar código)
Sólo si 7b no da un JPG correcto.
1. Igual que 7a: pantalla normal antes de disparar; tres fotos.
2. `Batch/M2V.LOG`: `VERIFY: 235211523`, `VERIFY: 235080451`, `VERIFY: 2`.
3. Esperado por foto: revisión y JPG con imagen correcta y medios algo más oscuros que en modo 0;
   `101O####.RAW` de 17.625.600 B (10 bits empaquetados, mismos datos que el modo 4).
4. JPG de 224 B o cuelgue: el modo 2 no es utilizable; batería y SD fuera, traer la SD.

Al terminar cada tramo, Claude guarda la SD en el siguiente `dump/rawN` con `SHA256SUMS`.

## Para deshacer todo
Borrar de la SD: `HiddenMenu/`, `ENABLE_NAND_TOOL`, `DISABLE_AUTO_POWER_OFF`, `Batch/` (incluye los
`*.log` del intérprete), `TP$BATCH` y `TEMP.SRT` si aparecen en la raíz, y los `._*`, `.fseventsd`,
`.Spotlight-V100` que macOS crea. Apagar, **sacar la batería** unos segundos y volver a encender.
La cámara queda como venía; para confirmarlo, comparar un volcado E1 `CameraParam.dmp` con el inicial.

## Ajustes de velocidad sin modificar nada (menú normal de la cámara)
- Advertencia de desenfoque (Blur Warning): Off. Tras cada foto, la cámara analiza la imagen
  (setter `0x68a48`, el mismo que el comando de script BlurWarning).
- Revisión rápida (Quickview) tras la foto: Off.
- Nitidez (Sharpness): Baja, para un JPEG menos procesado.
- Con RAW activo, cada foto escribe además dos archivos grandes: usa una SD rápida (clase 10)
  y espera a que termine la escritura antes de apagar.

## Opcional sin SD — parámetros de procesado por ISO
1. Sin tarjeta en la cámara, toma una foto (va a la memoria interna).
2. Conéctala por USB encendida: Claude lee `0x50f900–0x50fc00` con `tools/leer_ram.py`.
3. Repite con ISO 80, 400 y 1600, y con Sharpness alto y bajo: la diferencia ubica NR y realce.
