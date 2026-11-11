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
1. Menu → Setup → About. Debe abrir "HIDDEN MENU".
2. FIRMWARE VERSION: anota BOOT, MAIN, CamOS, IQLib, BFN (o foto con el celular).
3. NAND TOOL → ejecuta, una por una, **sólo** estas opciones:
   A1 Calibration.dmp · B3 MainCode.dmp · C1 BootCode.dmp · D1 NANDPartition.txt ·
   E1 CameraParam.dmp · F1 NANDReserved.dmp · G1 NANDP1.dmp · I4 BFNSetting.txt · I5 BootNANDBase.dmp
4. **No toques ninguna otra opción** (borran o reescriben la NAND).
5. Apaga, saca la SD y tráela al Mac. Claude guarda los volcados con hash en dos lugares y
   reconstruye el `KM531.FW` de fábrica (`tools/km531fw.py info` debe dar "el firmware lo acepta").

## Paso 3 — Primera foto RAW
1. Con el kit en la SD, enciende (P4 deja activo el RAW hasta apagar).
   Si los scripts no corrieron solos: menú oculto → DEBUG → SaveCCDRawOnTake → On.
2. Toma 3 fotos: una carta gris o pared blanca con luz de día, una escena con detalle, una con poca luz.
3. Trae la SD: aparecerán `101O####.raw` y `101b####.raw` junto a cada JPG.
4. Claude corre `tools/m531raw.py info` sobre cada par y calibra negro, blanco, CFA (R vs B) y la
   matriz de color con la foto gris y su JPG.

## Paso 4 — Fase 2 (sólo si P4 y P5 funcionaron con la sintaxis usada)
1. La fase 2 **reemplaza** `Batch/` de la fase 1 (no se mezclan: MEMRW debe correr antes de que
   cualquier otro script ejecute código de la misma línea de caché, `0x2d6600–0x2d663f`).
2. Si alguna sintaxis falló, Claude regenera MEMRW con la que funcionó (`tools/patch2srt.py`).
3. Encender: debe verse "MEMRW OK" y "MEMRWT OK". Apagar y sacar la batería: el parche desaparece.

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
