# Cómo mantener todo reversible (Kodak M531)

Regla general: cada cambio entra por el nivel más bajo que lo permita, y sólo sube de nivel cuando
ya funcionó en el anterior. Un nivel sólo se usa si su vía de vuelta está comprobada.

| Nivel | Qué cambia | Cómo se deshace | Estado de la vía de vuelta |
|---|---|---|---|
| 0 | Nada: lectura de la RAM por USB | — | — |
| 1 | Archivos en la SD (HiddenMenu, banderas, scripts) | Borrar los archivos o sacar la SD | Segura por diseño |
| 2 | RAM en caliente con scripts (`Run_SpecifyFunc` + `poke32`) | Apagar y **sacar la batería** unos segundos | Segura; ver riesgos abajo |
| 3 | Firmware principal flasheado (`SYSTEM\KM531.FW`) | Reflashear el stock reconstruido | **Pendiente**: requiere los volcados de la NAND Tool |
| 4 | Calibración, parámetros, boot, particiones | Restaurar desde volcado | **Prohibido**: no se toca |

## Nivel 1: archivos en la SD

- El **kit** sólo usa: carpeta `\HiddenMenu`, archivos vacíos `ENABLE_NAND_TOOL`,
  `DISABLE_AUTO_POWER_OFF`, y `\Batch\BatchScripts.txt` + `*.srt`. El firmware reacciona además a
  `B:\SYSTEM\KM531.FW`, `B:\SYSTEM\IMAGE.ISO`, `B:\TBM_HD14P.BIN`, `B:\TBIB_HD14P.BIN`,
  `ALLOW_ERASE_BOOT`, `ALLOW_ROLLBACK_OLD_PARTITION`, `RESET_DEFAULT_LCD_TYPE`, `STR_EN`: ninguno
  va en la SD.
- **Ojo con el menú oculto:** se entra desde la pantalla de confirmación de formateo; ahí **OK
  formatea la tarjeta**. Con `ENABLE_NAND_TOOL`, las opciones destructivas (J1, H1/H2, B1, C2)
  quedan a pocas teclas: entrar sólo con un objetivo concreto.
- Peor caso: un script con un error. **Cualquier error de script detiene la CPU** (`0x4b4e0`): la
  cámara se congela en cada arranque con esa SD. Arreglo: sacar batería y SD, borrar o corregir
  `\Batch` en el Mac. Que nada quede escrito en la NAND no está auditado (comparar E1 antes/después). Mitigación: verificador estricto y pruebas
  nuevas siempre con un script mínimo primero. Por eso **nunca** se ponen scripts en la memoria interna (A:).
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

### Correcciones tras la revisión externa (2026-11-11)

- **Hay una segunda vía que escribe la partición 0** (corregido tras la revisión de Fable):
  la rutina simple `0x2bcdb8` (opción UPDATE FIRMWARE, pantalla `0x1f2c00`) sólo llama a `0x2bd5bc`
  (partición 6). La que busca el marcador `INFO` + `0x55aaaa55` es **`0x2bd024`** (llamada desde
  `0x1f93ba`, pantalla `0x1f9000`): sólo lo busca en contenedores que **no** empiezan por `RHIR`; si
  lo encuentra, `0x2bd664` escribe la partición 0 y luego `0x2bd5bc` la 6. El actualizador del boot
  `0x2bcf28` usa `B:\TBIB_HD14P.BIN` y lo llaman `0x24cc38`, `0x24cdca`, `0x2c1af4`, el comando de
  script `UpdateFW` (`0x2d81e6`) y `NANDScriptEx_ExecuteCmd` (`0x2da67c`, `0x2da81c`).
  Reglas: todo `.FW` propio empieza por `RHIR`; `km531fw.py` rechaza el marcador; ningún
  `TBIB_*.BIN` ni `TBM_*.BIN` va nunca a la SD.
- **Zonas intocables** ampliadas a las funciones de las que depende la vía de vuelta (modelo
  `0x4c1c0`, tamaño de partición `0x6584c`, NAND `0x1433c0/0x1436fc/0x143a90/0x1447a0/0x657b8`,
  memcmp `0x3019c8`, pool `0x7574c`, archivos `0xe0c00–0xe1000`). Pendiente: derivarlas del grafo de
  llamadas completo en vez de una lista a mano.
- **Registro 7 (tipo 2)**: el sector 46144 no es un desplazamiento del `.FW` (corregido): es el
  bloque absoluto 1442 de la NAND, fuera de las 7 particiones (terminan en el bloque 710). La
  partición 6 ocupa los bloques 195–695 = **0x7d0000 B** (tabla en RAM `0x4da228`, bloques de 16 KiB)
  y `0x1445d0` limita la escritura a ese tamaño. Falta saber quién usa el bloque 1442 (G1/F1).
- **Ajustes guardados en la NAND (riesgo 1 del nivel 2)**: volcar E1 `CameraParam.dmp` antes de
  correr scripts y otra vez después de una sesión con scripts; comparar. Confirmar también si
  SaveCCDRawOnTake del menú DEBUG queda guardado y cómo se apaga.
- **Opciones "Dump" de la NAND Tool**: su inocuidad sale de los nombres. Antes de usarlas,
  fotografiar el menú en la cámara y compararlo con la lista; revisar en el código que cada
  manejador de Dump sólo lea la NAND y escriba un archivo.
- **Ensayo del actualizador** antes del primer flasheo real: lanzar UPDATE FIRMWARE con un `.FW`
  con sum32 mal hecha a propósito y confirmar el rechazo ("Firmware file is invalid"). Verificado en
  código que el validador corre antes de escribir en `0x2bd5bc`; falta revisar el resto de la ruta.
- **Tamaño de la partición 6**: sacarlo de D1 `NANDPartition.txt` y pasarlo siempre con
  `km531fw.py patch … --particion=TAMAÑO`.

- **Límite de "probar antes en RAM":** no cubre código que corre antes del lanzador de scripts
  (`0x1fe1dc`) ni la sección de datos (`rec1`). Los parches de nivel 3 se limitan a funciones que se
  ejecutan después del arranque y que ya funcionaron como parche en RAM.
- **Escritura en sitio:** `0x2bd5bc` escribe la partición 6 sin copia de respaldo; un corte de
  energía la deja a medias. Batería llena, cámara fuera de USB.
- **Primer flasheo = stock idéntico** (desde B3), para probar el camino completo sin cambios.

## Nivel 4: nunca

NAND Tool: sólo las opciones "Dump". Prohibidas: A2/A3, B1/B2, C2, D2, E2, F2, H1/H2, I1–I3, I6,
J1, K1, L1, M1/M3. Archivos `ALLOW_ERASE_BOOT` y `ALLOW_ROLLBACK_OLD_PARTITION`: jamás en la SD.
