# Lista de control: volcados de la NAND Tool

Marcar cada punto. Si uno falla, parar ahí.

## Antes (Mac)
- [ ] Batería cargada.
- [ ] SD con ≥ 32 MB libres; `Batch/` de sesiones anteriores movida al Mac.
- [ ] En la raíz de la SD sólo se agregan `HiddenMenu/`, `ENABLE_NAND_TOOL`, `DISABLE_AUTO_POWER_OFF`.
- [ ] `ls -la` de la raíz: no existe ninguno de `ALLOW_ERASE_BOOT`, `ALLOW_ROLLBACK_OLD_PARTITION`,
      `TBIB_*.BIN`, `TBM_*.BIN`, `SYSTEM/KM531.FW`, `SYSTEM/IMAGE.ISO`, `NANDUtility.txt`, `BootNANDBase.bin`.
- [ ] `dot_clean` hecho; hashes de la copia iguales a `sd_kit/nand_dump/sd/`.

## En la cámara
- [ ] Cámara fuera del USB.
- [ ] Menú oculto abierto con DELETE + DERECHA en la confirmación de formateo (sin pulsar OK).
- [ ] Foto de FIRMWARE VERSION.
- [ ] Foto de cada pantalla de la NAND Tool; textos y orden iguales a `LEEME.txt`.
- [ ] A1 ejecutada, resultado anotado.
- [ ] B3 ejecutada, resultado anotado.
- [ ] C1 ejecutada, resultado anotado.
- [ ] D1 ejecutada, resultado anotado.
- [ ] E1 ejecutada, resultado anotado.
- [ ] F1 ejecutada, resultado anotado.
- [ ] G1 ejecutada, resultado anotado.
- [ ] I4 ejecutada, resultado anotado.
- [ ] I5 ejecutada, resultado anotado.
- [ ] Ninguna otra opción ejecutada.
- [ ] EXIT, cámara apagada con su botón, SD fuera.

## Después (Mac)
- [ ] Los 11 archivos están: `Calibration.dmp`, `Calibration_2.dmp`, `MainCode.dmp`, `BootCode.dmp`,
      `NANDPartition.txt`, `CameraParam.dmp`, `CameraParam_2.dmp`, `NANDReserved.dmp`, `NANDP1.dmp`,
      `BFNSetting.txt`, `BootNANDBase.dmp`.
- [ ] Copiados a `dump/nand_tool/` y a una segunda carpeta en otro disco.
- [ ] `tools/verificar_volcados.py dump/nand_tool --copia <segunda> --escribir-sumas --json …` con 0 errores.
- [ ] Cada AVISO leído y resuelto (largo de los archivos, cola de `MainCode.dmp`, copias `_2`).
- [ ] `MainCode.dmp`: cabecera, código, gráficos y `rec3` idénticos a los de la RAM.
- [ ] `BootCode.dmp`: sum32 `0xbbb66ba4` y bytes idénticos al boot residente en RAM.
- [ ] `NANDPartition.txt`: `uwSize_HexMain 0x01F4` (partición 6 = `0x7d0000` B).
- [ ] `CameraParam.dmp` guardado como referencia para comparar tras sesiones con scripts
      (`--e1-anterior`).
- [ ] Kit quitado de la SD.
