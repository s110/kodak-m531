# Kodak EasyShare M531: RAW y firmware

Proyecto personal para darle vida nueva a una Kodak EasyShare M531 (2010): RAW de sensor, menos
postproceso y, más adelante, un firmware mejorado. Todo reversible: primero archivos en la SD, luego
cambios sólo en RAM, y flasheo sólo con respaldo y vía de recuperación verificados.

## Estado

- **RAW de sensor funcionando** con scripts de fábrica en la SD (`sd_kit/fase1/Batch`):
  - `P9` (modo 4): RAW de 10 bits efectivos, estable; el JPG de la cámara sale rosado.
  - `P8` (modo 0): RAW de 8 bits comprimidos + JPG normal.
  - `P6` (modo 3): 12 bits reales, pero rompe el JPG y cuelga la cámara en la segunda foto.
    `M3F2` (experimental, revisado contra el código, sin probar en la cámara): modo 3 con el IRP en el formato del modo 4.
- **Conversor RAW → DNG** (`tools/m531raw.py`, `tools/convertir_carpeta.py`): formato por tamaño,
  curva de descompresión del firmware, patrón GBRG, matriz ajustada; balance desde el JPG (modo 0) o
  por foto desde el propio RAW (modo 4, parche blanco con reserva a un neutro fijo).
- **JPG sin realce (fase 3, por probar)**: `sd_kit/fase3/Batch` con P8 + EE0 (curva de realce del
  ASIC a cero en ISO ≤ 159, sólo RAM).
- **Menú oculto**: carpeta `HiddenMenu` en la SD + Setup → Format → (confirmación) mantener DELETE y
  pulsar DERECHA. Ojo: en esa pantalla OK formatea la tarjeta.
- **Firmware**: código de fábrica reconstruido desde la RAM; formato y actualizador analizados.
  El cargador de arranque también se reconstruyó desde la RAM (suma verificada): arranca desde
  `TBM_HD14P.BIN` si la partición 6 falla, o con DELETE al encender. No se flashea nada hasta tener
  los volcados de la NAND Tool (`sd_kit/nand_dump/`) y probar esa vía en la cámara
  (ver `REVERSIBILIDAD.md`).

## Documentos

- `NOTAS.md`: hallazgos en orden, con fe de erratas.
- `REVERSIBILIDAD.md`: niveles de riesgo y qué se permite en cada uno.
- `sd_kit/PASOS.md`: qué hacer con la SD, paso a paso.
- `docs_script_comandos.txt`, `docs_script_manejadores.json`: intérprete de scripts de la cámara.

## Herramientas

| Archivo | Qué hace |
|---|---|
| `tools/m531raw.py` | RAW de la M531 → DNG |
| `tools/convertir_carpeta.py` | convierte una carpeta DCIM completa |
| `tools/check_scripts.py` | verificador estricto de scripts antes de copiarlos a la SD |
| `tools/patch2srt.py` | parche de código → script que lo aplica sólo en RAM, con guardia |
| `tools/km531fw.py` | inspecciona y parchea `KM531.FW` con las reglas del validador de la cámara |
| `tools/leer_ram.py` | lee la RAM de la cámara por USB (CD virtual, sin SD) |
| `tools/verificar_volcados.py` | comprueba los volcados de la NAND Tool (tamaños, hashes, RHIR, boot, tabla) |
| `tools/ajustar_ccm.py` | ajusta y valida la matriz de color con pares RAW/JPG |
| `tools/e2e_raw.py`, `tools/e2e_fw.py`, `tools/e2e_nand.py`, `tools/e2e_scripts.py` | pruebas de punta a punta |

Los volcados, binarios del fabricante, fotos y la RAM de la cámara no están en el repo (`.gitignore`).
