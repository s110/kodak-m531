# Pasos con la SD de la Kodak M531

Todo lo de aquí es de nivel 1 o 2 (ver ../REVERSIBILIDAD.md): nada se escribe en la NAND.
Antes de empezar: batería cargada. Cámara fuera del USB salvo donde se indique.

## Paso 0 — Respaldo de la SD (en el Mac)
1. Saca la SD de la cámara y ponla en el lector del Mac.
2. Claude copia la SD entera a `dump/sd_original/` con SHA-256 (fotos incluidas).

## Paso 1 — Kit fase 1
1. Claude corre `tools/check_scripts.py sd_kit/fase1/Batch` y copia `sd_kit/fase1/*` a la raíz de la SD.
2. Expulsa la SD, ponla en la cámara y enciéndela.
3. Anota qué aparece en pantalla al arrancar: "P1 OK", "P2 OK", "P3 OK" y dos números (P4).
   - Si no aparece nada, los scripts no corren solos al encender; se buscará otro disparador.

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

## Para deshacer todo
Borrar de la SD: `HiddenMenu/`, `ENABLE_NAND_TOOL`, `DISABLE_AUTO_POWER_OFF`, `Batch/`.
Apagar y encender. La cámara queda exactamente como venía.

## Ajustes de velocidad sin modificar nada (menú normal de la cámara)
- Advertencia de desenfoque (Blur Warning): Off. Tras cada foto, la cámara analiza la imagen
  (setter `0x68a48`, el mismo que el comando de script BlurWarning).
- Revisión rápida (Quickview) tras la foto: Off.
- Nitidez (Sharpness): Baja, para un JPEG menos procesado.
- Con RAW activo, cada foto escribe además dos archivos grandes: usa una SD rápida (clase 10)
  y espera a que termine la escritura antes de apagar.
