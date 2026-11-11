# Cómo mantener todo reversible (Kodak M531)

Regla general: cada cambio entra por el nivel más bajo que lo permita, y sólo sube de nivel cuando
ya funcionó en el anterior. Un nivel sólo se usa si su vía de vuelta está comprobada.

| Nivel | Qué cambia | Cómo se deshace | Estado de la vía de vuelta |
|---|---|---|---|
| 0 | Nada: lectura de la RAM por USB | — | — |
| 1 | Archivos en la SD (HiddenMenu, banderas, scripts) | Borrar los archivos o sacar la SD | Segura por diseño |
| 2 | RAM en caliente con scripts (`Run_SpecifyFunc` + `poke32`) | Apagar y encender (o sacar la batería) | Segura; ver riesgos abajo |
| 3 | Firmware principal flasheado (`SYSTEM\KM531.FW`) | Reflashear el stock reconstruido | **Pendiente**: requiere los volcados de la NAND Tool |
| 4 | Calibración, parámetros, boot, particiones | Restaurar desde volcado | **Prohibido**: no se toca |

## Nivel 1: archivos en la SD

- El firmware sólo lee: carpeta `\HiddenMenu`, archivos vacíos `ENABLE_NAND_TOOL`,
  `DISABLE_AUTO_POWER_OFF`, y `\Batch\BatchScripts.txt` + `*.srt`.
- Peor caso: un script que cuelga la cámara en cada arranque. Arreglo: sacar la SD (sin SD no
  hay script) o editarla en el Mac. Por eso **nunca** se ponen scripts en la memoria interna (A:).
- Lista negra de funciones que ningún script nuestro llama: `Format`, `UpdateFW`, `UpdateCDROMImage`,
  `InfoMgr_*` (escriben calibración), `WriteClampAndOffsetToFlash`, `ToneCCM_WriteLCDTable2Nflash`,
  `FE_WriteStrobeTypeToNANDCali`, `NANDScript*`, `LCD_TypeSetup`, `StrobeScript_SetType`,
  `ModelNameChange`, `OneCard_*`, `LensCali_*`, `Reboot`. `tools/check_scripts.py` lo verifica.

## Nivel 2: parches en RAM

- `Run_SpecifyFunc(f, nargs, 0, a1..a6)` llama a cualquier dirección; `poke32` = `0x2e8a84`
  (`*a1 = a2`), `peek32` = `0x198bbc` (`return *a1`). El código del firmware vive en SDRAM
  (`0x48000–0x3a9e00`), así que también se puede parchear código en caliente.
- Se pierde al apagar: el firmware se recarga desde la NAND en cada arranque.
- Riesgo 1: un valor que el firmware **guarda** en la NAND al apagar (registro de ajustes).
  Mitigación: antes de parchear una variable, comprobar que no está en el bloque de ajustes que
  se guarda; si lo está, el menú "Reset camera" o el volcado `CameraParam.dmp` lo restauran.
- Riesgo 2: un parche que cuelga la cámara. Se arregla quitando batería y SD.
- Uso clave: **todo parche de firmware (nivel 3) se prueba primero como parche en RAM**, con los
  mismos bytes en las mismas direcciones. Sólo se flashea lo que ya funcionó así.

## Nivel 3: firmware flasheado — condiciones antes del primer flasheo

1. Volcados de la NAND Tool guardados en el Mac con SHA-256, dos copias:
   A1 Calibration, B3 MainCode, C1 BootCode, D1 NANDPartition, E1 CameraParam, F1 NANDReserved,
   G1 NANDP1, I4 BFNSetting, I5 BootNANDBase.
2. `KM531.FW` de fábrica reconstruido desde B3 que reproduce **todas** las sumas de la cabecera
   original (código ya verificado desde RAM: `a53f33a3`).
3. Confirmar en `BootCode.dmp` que el cargador de arranque:
   - no se reescribe al actualizar. **Verificado en código (2026-11-11):** el escritor `0x2bd5bc`
     valida la cabecera, escribe sólo la **partición 6** de la NAND (`0x1447a0(6, buf, 0, tamaño)`),
     la relee (`0x1433c0`) y compara con `memcmp` (`0x3019c8`), hasta 3 intentos. El tamaño se
     limita al de la partición 6 (`0x6584c(6, …)`). Mismo esquema que la C713. Y además:
   - tiene una vía de recuperación si el main no arranca (actualizar desde SD al encender o
     combinación de teclas). Si no la tiene, el nivel 3 queda **descartado**.
4. Los parches no tocan: la rutina de actualización (`0x2bcdb8–0x2bd800`), el menú oculto ni
   su opción UPDATE FIRMWARE, la NAND Tool. Así, si el firmware modificado arranca, siempre
   puede reflashear el stock por el mismo camino.
5. Batería cargada y SD probada; nunca flashear con la cámara en USB.

## Nivel 4: nunca

NAND Tool: sólo las opciones "Dump". Prohibidas: A2/A3, B1/B2, C2, D2, E2, F2, H1/H2, I1–I3, I6,
J1, K1, L1, M1/M3. Archivos `ALLOW_ERASE_BOOT` y `ALLOW_ROLLBACK_OLD_PARTITION`: jamás en la SD.
