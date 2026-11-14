# Kodak EasyShare M531: RAW y firmware

Proyecto personal para darle vida nueva a una Kodak EasyShare M531 (2010): RAW de sensor, menos
postproceso y, más adelante, un firmware mejorado. Todo reversible: primero archivos en la SD, luego
cambios sólo en RAM, y flasheo sólo con respaldo y vía de recuperación verificados.

## Estado

- **RAW de sensor funcionando** con scripts de fábrica en la SD (`sd_kit/fase1/Batch`):
  - `P9` (modo 4): RAW de 10 bits efectivos, estable; el JPG de la cámara sale rosado.
  - `P8` (modo 0): RAW de 8 bits comprimidos + JPG normal.
  - `P6` (modo 3): 12 bits reales, pero rompe el JPG y cuelga la cámara en la segunda foto.
    `M3F2` (probado): modo 3 con el IRP en el formato del modo 4; 12 bits reales sin cuelgue, sin JPG
    y con la pantalla con ruido.
  - `M4L` + `M4Q` + `M4W` (probado): modo 4 con 12 bits lineales, JPG y revisión correctos. Es el kit
    de uso. `M3V` y `M2V` quedan como experimentales; ver `sd_kit/PASOS.md`.
- **Uso diario**: kit `sd_kit/m4_diario` (`M4L` + `M4Q` + `M4W` + `EET` + `EETV`: RAW lineal de 12 bits,
  JPG y revisión correctos) con DNG automáticos tras el respaldo de sdvault, o `./conversor` (ventana) / `./importar`. Guía: [`docs/USO.md`](docs/USO.md).
- **Prueba de estrés (2026-11-13)**: 16 RAW intactos; disparar antes de que termine el procesado de la
  foto anterior daña el JPG de esa foto (3 de 3 casos) y puede colgar la cámara. Regla: 15 s entre
  disparos. Variante por probar con espera forzada: `sd_kit/m4_diario_s` (añade `M4S`, una sola ranura
  de RAW; sólo RAM).
- **Conversor RAW → DNG** (`tools/m531raw.py`): formato por tamaño, curva de descompresión del firmware,
  patrón GBRG, matriz ajustada; balance desde el JPG (modo 0) o por foto desde el propio RAW (lo claro y
  menos cálido de la escena, con reserva a las ganancias de la cámara); DNG apaisado por omisión, `--rotar`.
- **12 bits contra 8 con curva**: medido, el RAW de `P8` guarda la misma imagen que el de `M4L`
  (`tools/comparar_bits.py`, `NOTAS.md`).
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

- `docs/USO.md`: guía de uso diario (kit, cómo disparar, importar, revelar, problemas comunes).
- `NOTAS.md`: hallazgos en orden, con fe de erratas.
- `REVERSIBILIDAD.md`: niveles de riesgo y qué se permite en cada uno.
- `sd_kit/PASOS.md`: qué hacer con la SD, paso a paso.
- `docs_script_comandos.txt`, `docs_script_manejadores.json`: intérprete de scripts de la cámara.

## Herramientas

| Archivo | Qué hace |
|---|---|
| `tools/m531raw.py` | RAW de la M531 → DNG |
| `tools/auto_vault.py` + `tools/instalar_auto.py` | DNG automáticos tras cada respaldo de sdvault (agente launchd `me.sebastian.m531-dng`) |
| `conversor` (`tools/conversor_ui.py`) | ventana en el navegador: arrastrar RAW → DNG, importar de la SD, girar, comparar con el JPG |
| `importar` (`tools/importar_sd.py`) | SD → copia verificada con SHA-256 + DNG y JPG en `/Volumes/Datos/personal/Fotos/m531_dng/<fecha>/` |
| `tools/convertir_carpeta.py` | convierte una carpeta ya copiada |
| `tools/check_scripts.py` | verificador estricto de scripts antes de copiarlos a la SD |
| `tools/patch2srt.py` | parche de código → script que lo aplica sólo en RAM, con guardia |
| `tools/km531fw.py` | inspecciona y parchea `KM531.FW` con las reglas del validador de la cámara |
| `tools/leer_ram.py` | lee la RAM de la cámara por USB (CD virtual, sin SD) |
| `tools/verificar_volcados.py` | comprueba los volcados de la NAND Tool (tamaños, hashes, RHIR, boot, tabla) |
| `tools/ajustar_ccm.py` | ajusta y valida la matriz de color con pares RAW/JPG |
| `tools/medir_balance.py` | error del balance por foto contra 23 fotos con verdad independiente |
| `tools/comparar_bits.py` | P8 (8 bits con curva) contra M4L (12 bits): ruido, niveles, rango y recortes |
| `tools/e2e_raw.py`, `tools/e2e_importar.py`, `tools/e2e_conversor.py`, `tools/e2e_auto_vault.py`, `tools/e2e_fw.py`, `tools/e2e_nand.py`, `tools/e2e_scripts.py` | pruebas de punta a punta |

Los volcados, binarios del fabricante, fotos y la RAM de la cámara no están en el repo (`.gitignore`).
