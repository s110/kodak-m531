# Kodak EasyShare M531: notas de ingeniería inversa

Inicio: 2026-11-11. Cámara: M531, serie USB `M531 020923046`, VID 0x040A PID 0x0600.

## Plataforma (confirmado leyendo la RAM viva)

- ODM Altek, ASIC **Sunny9 / SD9** (núcleo ARCompact), RTOS MQX, firmware "CamOS".
  Misma familia que la C713/CD703 de ModernShare (`ref/ModernShare`), que ya tiene DNG
  directo, looks de película y menú propio funcionando en cámara.
- Firmware de actualización: `B:\SYSTEM\KM531.FW` (B: = SD, A: = memoria interna).
  También `A:\KM531.FW`. El CD virtual es `B:\SYSTEM\IMAGE.ISO` / `A:\IMAGE.ISO`.
- Kodak nunca publicó (o no se archivó) un updater de la M531. Sólo hay `KM530170.exe`
  de la M530 y `download.kodak.com` ya no resuelve.

## Fuga de RAM por USB (sin tocar nada en la cámara)

La cámara se presenta como CD-ROM de 343 MB con bloques de 2352 B. Sólo el primer
~1 MB es el ISO de Kodak; el resto es una ventana de 64 MB que se repite y que es la
**SDRAM viva** de la cámara.

- Leer con `dd if=/dev/rdiskN bs=37632` (16 sectores). Con bs=2048 los datos salen
  desordenados; con bs=150528 no lee nada. Unos 3 MB/s.
- Cada bloque de 2352 B: 16 B de cabecera falsa + 2048 B de datos + 288 B de relleno.
- Mapeo: `RAM[a] = ventana[(a + 0xB22C00) mod 0x4000000]`. Verificado: 10/10 cadenas
  conocidas tienen punteros LE a `offset - 0xB22C00`.
- `dump/ram_snapshot.bin` = RAM lineal de 64 MB (instantánea, no es el .FW).

## Menú oculto (sin flashear)

- Crear la carpeta `\HiddenMenu` en la raíz de la SD → Menu → Setup → About.
- Ítems: FIRMWARE VERSION, PRODUCT INFORMATION, ERROR CODE, CALIBRATION DATA, DEBUG,
  TOTAL INFO, DEBUGMODE, NAND TOOL, LCD SELECT, STROBE SELECT, UPDATE FIRMWARE.
- DEBUG MENU: ThumFormat/VGAFormat/FullFormat, **SaveCCDRawOnTake**, SaveCFARawOnIRP,
  SaveThum/VGA/Full YRGB/JPEG, SaveAEOnS1, **Take12BitCCDRawImage**.
- Archivos disparadores en la SD: `ENABLE_NAND_TOOL`, `DISABLE_AUTO_POWER_OFF`,
  `DISABLE_BATGAUGE_POWER_OFF`, `DISABLE_TEMPER_PROTECT`, `STR_EN`, `ALLOW_ERASE_BOOT` (¡no!),
  `ALLOW_ROLLBACK_OLD_PARTITION` (¡no!), `RESET_DEFAULT_LCD_TYPE`.
- `\MEMDUMP.BIN`: volcado de RAM a la SD (la combinación de teclas está por confirmar).

## NAND Tool (Engineering Mode)

Sólo lectura, seguros: A1 Calibration.dmp, B3 MainCode.dmp, C1 BootCode.dmp,
D1 NANDPartition.txt, E1 CameraParam.dmp, F1 NANDReserved.dmp, G1 NANDP1.dmp,
I4 BFNSetting.txt, I5 BootNANDBase.dmp, M2 Face Registry.

**NO tocar:** A2/A3 (calibración), B1/B2 (main code), C2 (boot), D2, E2, F2, H1/H2
(formatean), I1–I3, I6, J1 (borra el sector 0 de la NAND), K1, L1, M1/M3.

Actualización del código principal por esta vía: `TBM_X.BIN` (en RAM aparece
`B:\TBM_HD14P.BIN` y `B:\TBIB_HD14P.BIN` para el boot).

## Sensor

- Menú de ajuste del AFE: "Take FR 8 bits / FR 14 bits / LV 12 bits / LV 14 bits",
  "Save Raw". El AFE digitaliza a 14 bits.
- `raw_img_info_sunny9` en RAM: estructura de metadatos del RAW.

## Firmware de fábrica en RAM (2026-11-11)

Cabecera RHIR completa en RAM `0xa05ffc` (modelo `0x01121410`, MAIN 1.0). Registros
(u16 tipo, u16 0, u16 sector inicial, u16 nº sectores, u32 destino RAM, u32 sum32):

| rec | tipo | archivo | destino | tamaño | sum32 | ¿coincide la RAM? |
|---|---|---|---|---|---|---|
| 0 código | 1 | 0x200 | 0x48000 | 0x361e00 | a53f33a3 | difiere en exactamente +0x08000000 |
| 1 datos | 1 | 0x362000 | 0x3aa000 | 0xeae00 | 4a34f20f | no (datos mutados en ejecución, esperado) |
| 2 gráficos | 0 | 0x44ce00 | 0x528000 | 0x51800 | e39ecc58 | **sí, exacto** |
| 3 | 1 | 0x49e600 | 0x5ae000 | 0x200 | 00f92e93 | **sí, exacto** |
| 4–6 idiomas | 0 | … | 0x5ae000 | … | … | sólo el idioma cargado |
| 7 especial | 2 | sector 46144 | 0 | 0x800 | 0 | no tocar |

- Validador del updater `0x2bd46c`: RHIR, palabra de modelo (devuelta por `0x4c1c0`),
  tamaño ≤ partición, y sum32 de los registros tipo 1. Sum32 = `0x2e06e4`.
  Rutina de actualización `0x2bcdb8`; códigos 0x1c00110 = no encontrado, 0x1c00111 = inválido.
  También acepta un contenedor con marcador `INFO` + `0x55aaaa55` (paquete 5-en-1).
- **Código de fábrica reconstruido byte a byte.** La diferencia de +0x08000000 es la variable
  `0x38ac4c` dentro de la sección de código: la función `0x30b0bc` hace `lr r1,[0x18]` y la
  guarda ahí al arrancar. Con esa palabra en 0, sum32 = `a53f33a3`, igual que la cabecera.
  Dos lecturas en sesiones distintas dan el mismo código. Guardado en `firmware/stock/`
  (`rec0_code_0x48000.bin`, gráficos, rec3 y los primeros 0xA0 B de la cabecera, con SHA256SUMS).
- Falta para un .FW completo: sección de datos original (rec1, mutada en RAM), idiomas
  (rec4–6) y la cola de cabecera (0xA0–0x1FF, ¿KHIR?). Fuente: NAND Tool → B3 MainCode.dmp.

## RAW

- Banderas (byte en RAM): SaveCFAonTake `0x3df0e4` (getter `0x1b0648`, setter `0x1b0654`),
  Take12BitCCDRaw `0x3dbdfe` (getter `0x12bf20`), SaveFullJPEG `0x3da92a` (=1).
- Captura: `0x127168` consulta SaveCFAonTake y guarda dos búferes con `0x1b066c`
  (sufijo 'O' y 'o', probablemente campos par/impar del CCD entrelazado) + `0x1b0754`.
- El motor de scripts (`B:\Batch\BatchScripts.txt`, `.SRT`) tiene comandos SaveCFAonTake,
  SaveCFAonIRP, Take12BitCCDRaw, SetExposureTime, SetIsoSpeed, SetAdGain, SetIrisIndex.
  Posible vía para activar RAW y exposición manual sin flashear.

## Herramientas

- Desensamblador: imagen Docker `kodak-arctools:24.04` (binutils-arc-linux-gnu 2.42 de Ubuntu).
  `tools/dis.sh INICIO FIN`. `work/code_full.s` = código completo desensamblado.
- La compilación nativa de binutils 2.43 falla en macOS (zlib/SDK); no hace falta.

## Motor de scripts (2026-11-11)

- ~200 comandos (tabla en RAM ~0x486000). Destacan: MemRead, MemWrite, Run_SpecifyFunc,
  SaveCFAonTake, SaveCFAonIRP, Take12BitCCDRaw, IRP_SaveNoCompressImg, IRP_SetDenoiseTH,
  IRP_SetEdgeEnhanceLUT, IRP_EnableShade/DisableShade, ImgCap_SetExposureTime/SetAperture/
  SetISOSpeed/SetFocusPosition, SetIsoSpeed, SetAdGain, Key* (teclas simuladas), Reboot, UpdateFW.
- Lanzadores: `0x53e44(unidad)` busca `<unidad>\Batch\BatchScripts.txt`; `0x53ebc(ruta)` corre un
  .srt concreto (usa `\TP$BATCH` y `\TEMP.SRT` como temporales). Log: "***** Script %s starts here".
- **Arranque (verificado en el código, falta probarlo en la cámara):** en la tabla de eventos de la
  pantalla de inicio (`0x4706d8`) el evento `0x7c0b` va a `0x1fe124` (el `0x7c0a` va a `0x1fdff4`, que
  no lanza scripts). `0x1fe124` llama en `0x1fe1dc` a `0x2bee0c("B:")` en cada encendido normal, salvo
  si hay una entrada especial pendiente (`0x107c98(0, 0x3301, 1)`) o un modo especial (`0x11d95c`).
  `0x2bee0c` pide el búfer del pool 6 (`0x4b980(6)`, `0x7574c`); **sólo si mide ≥ 0x20000 B** llama a
  `0x53e44`, que abre `B:\Batch\BatchScripts.txt` y, si existe, lo encola al hilo de scripts. Si el
  búfer falta o es más chico, no corre nada y no avisa: si las sondas no aparecen, revisar esto antes
  de dar por refutado el arranque automático.
  Rollback de esta vía: borrar `B:\Batch\` (o sacar la SD) y reiniciar.
- `Run_SpecifyFunc(f, nargs, outpos, a1..a6)` (`0x2da0c4`), leído en el desensamblado: si
  `nargs < outpos` o `nargs > 6` devuelve 0 **sin llamar** a f; con `outpos = 0` devuelve
  `f(a1, …, a_nargs)`; con `outpos = k ≠ 0` reemplaza `a_k` por `&resultado`. Siempre guarda f en la
  global `0x3e5060`. Ojo: en `docs/decomp_clave_1.c` Ghidra muestra nargs 3 y 4 llamando sólo a
  f(a1, a2); es un error del decompilador: en `0x2da174–0x2da1ae` r2 = a3 y r3 = a4 siguen cargados.
  Los scripts del kit sólo usan nargs 1 y 2.
- Caché: hay caché de datos (`dc_ctrl/dc_ivdl/dc_fldl`); `dcache_flush_range(addr, len)` = `0x24e140`,
  `dcache_inval_range` = `0x24e108`. **No está descartado que exista caché de instrucciones:** el
  firmware no la toca, pero el cargador de arranque podría encenderla y nada lee el registro de
  configuración (IC_BUILD, aux 0x77). Si existe, una función ya ejecutada podría seguir corriendo
  instrucciones viejas tras un parche en RAM. Mitigación: los primeros parches de código (MEMRW) van
  sobre funciones que nunca se ejecutaron antes (los stubs MemRead/MemWrite), y el kit verifica el
  resultado ejecutando el código parcheado (`MEMRWT.srt`). Rollback de los parches en RAM: apagar.
- `B:\Batch\Reset.srt` lo corre `0x2bd950` con OK (evento 0x580) en otra pantalla (tabla 0x489fd0).
- Pendiente: sintaxis exacta del .txt/.srt (parser en torno a `0x1078d8`, `0x1062e0`).

## Intérprete de scripts: sintaxis y funciones (2026-11-11, segunda ronda)

- BASIC con números de línea: `10 REM`, `LET x = expr`, `IF … THEN … ELSE`, `GOTO`, `GOSUB/RETURN`,
  `END`, `LOG_PRINT`, `SCREEN_PRINT`. Operadores tipo C (`&& || == != >= <= + - * / % ^ ~ & |`),
  separadores ` ,\t\n`, cadenas entre comillas.
- `BatchScripts.txt` es una lista: cada línea nombra un `.srt` de la misma carpeta (sin extensión).
- Llamadas con palabra clave: `SYSTEM f(...)` (tabla 0x4871f4), `FOREIGN f(...)` (0x486334),
  `DEBUGGING f(...)` (0x487404). Formato de cada entrada: `[ret][nombre\0][args…][0x07]`,
  tipos 00 int, 01 float, 02 str, 06 void. Catálogo: `docs_script_comandos.txt`;
  nombre → manejador: `docs_script_manejadores.json` (despachadores 0x29be6c / 0x29c068 / 0x29d118).
- **Stubs vacíos en producción:** `MemRead` (devuelve 1), `MemWrite`, `IRP_SetDenoiseTH`,
  `IRP_SetEdgeEnhanceLUT`.
- **Funcionan:** `SaveCFAonTake(x)` → setter `0x1b0654`; `Take12BitCCDRaw(x)` → SaveCFAonTake(x) + modo
  de captura 3 (`0x6e0b0`); `Run_SpecifyFunc(f, nargs, 0, a1..a6)` llama a cualquier dirección.
- Primitivas para RAM: `poke32` = `0x2e8a84` (`*a1 = a2`), `peek32` = `0x198bbc`, `copy32` = `0x2e8a88`
  (`*a2 = *a1`). Con Run_SpecifyFunc dan lectura/escritura de RAM (y de código) sin flashear.
- Nombre real de los RAW: `101O####.raw` y `101b####.raw` (el '_' del nombre del JPG pasa a 'O' o 'b').
- Nitidez: hay ajuste "Sharpness" en el menú normal. La reducción de ruido es del IPP del ASIC
  (tablas por ISO, sin localizar); se ataca con fotos de prueba.

## Herramientas nuevas

- `tools/m531raw.py`: RAW → DNG con detección automática (formato, ancho, campos, CFA) y balance
  de blancos por mundo gris. Prueba E2E `tools/e2e_raw.py`: 5 formatos desde una foto real, LibRaw
  lee el DNG idéntico píxel a píxel. Pendiente con fotos reales: negro, blanco, R vs B y matriz.
- `tools/km531fw.py`: info / vs-ram / patch con port del validador del firmware y zonas intocables.
  Prueba E2E `tools/e2e_fw.py` (10 casos) con la cabecera y el código reales.
- `tools/check_scripts.py`: lista blanca de funciones y destinos de poke32 antes de copiar a la SD.
- Ghidra 12.1.4 + módulo ARCompact (niooss-ledger d3fbf109, hashes = los de ModernShare) en
  `tools/ghidra`; proyecto en `ghidra_proj/m531`; script `tools/ghidra_scripts/Decomp.java`.
- `REVERSIBILIDAD.md` (niveles 0–4) y `sd_kit/PASOS.md` (qué hacer con la SD).

## Pendiente al cortar la sesión (2026-11-11)

- Nitidez/ruido: el ajuste "Sharpness" del menú existe; la tabla EXIF vive en RAM (entrada Sharpness
  0x3e93ac, valor en 0x3e93b4; selector de sub-tablas en 0x50580–0x505f0). Hay un bloque de
  depuración del IPP que se incrusta en el JPEG, delimitado por `iq_debug_str_sunny8`/`end_str_sunny8`
  y `iq_debug_str_asic`/`end_str_asic` (cadenas en 0x43c718.., referenciadas desde 0x17b2dc). Con un
  JPEG real de la M531 ese bloque daría los parámetros de NR/realce usados.
  **Revisado con Ghidra (`docs/decomp_iq_debug.c`):** lo arma `0x17b1c4`. `0x17b9f0` sólo copia una
  cadena ("Hagrid14", nombre de proyecto); `0x17bb6c` vuelca calibración/AE/sombreado (`0x6c55c`,
  `0x6c5d8`, `0x17bf60…`). La sección asic ocupa 0x34c B (no 6 valores). Quedan sin decompilar
  `0x17ba40` y `0x17bef0` (este último lee tablas por ISO en `0x50f9b4`): son el siguiente candidato
  para NR/realce sin SD. Con fotos reales a distintos ISO y Sharpness se confirma.
- Plantilla JPEG/EXIF de la cámara en RAM en 0x43dbac.
- Revisión externa: el agente Fable fue bloqueado por sus salvaguardas (req_011Cgve3VsVH4Y2hax6AVghm).
  Una revisión /code-review high (sobre el commit d5d962c) sí terminó: 7 hallazgos sobre las notas y la
  evidencia de Ghidra, todos corregidos en 29e7685 (precondición del pool 6, semántica completa de
  Run_SpecifyFunc, riesgo de caché de instrucciones + MEMRWT, procedencia de las decompilaciones).
- Arranque de scripts: verificado estáticamente con Ghidra; sólo falta la prueba en cámara (SD).

## Ajustes de la cámara y nitidez (2026-11-11, tercera ronda)

- Lector de ajustes por ID: `0x6615c(id)` = byte en `tabla + 4*id`, tabla en `0x495a5c` (literal en
  `0x66270`). Para id ≥ 0x61 hay una segunda tabla (`0x66164`).
- La tabla de ayuda del menú (`0x4617b8…`) empareja etiqueta y número: AF Zone → 7, ISO → 5,
  **Sharpness → 0xA**. Coincide con los IDs de ajuste (sospecha fuerte, sin prueba en cámara).
- 33 lecturas del ajuste 0xA en 31 funciones (lista en este commit); las revisadas sólo comparan con 0
  para dibujar iconos o páginas de menú. Ninguna está en la zona de captura (`0x12xxxx`). La que
  traduce Sharpness a parámetros del IPP no se encontró: probablemente copia los ajustes a una
  estructura de captura y la lee por desplazamiento, no por `0x6615c`.
- Siguiente paso con cámara: con el kit de RAM, leer con peek32 la tabla `0x495a5c` cambiando
  Sharpness en el menú confirma el ID; luego un barrido de fotos a Sharpness/ISO fijos ubica la tabla
  de realce y de NR.

## Parámetros de procesado por ISO (2026-11-11, cuarta ronda)

- `0x17bef0` (`docs/decomp_iq_iso.c`) lee, para el índice actual (`0x5dbd0` → `0x56058`, nivel de
  ISO), campos +0x24, +0x48, +0x3c de la tabla en `0x50f9b4`, y bytes −0x48, −0x47, −0x42 del bloque
  en `0x50facc`; más dos valores de `0x151b30` / `0x151bb0`. `0x17ba40` arma el encabezado del bloque
  (ISO, exposición, AE…). Candidatos fuertes a NR/realce/gamma por ISO.
- Esas tablas **están en cero en la RAM en reposo**: se llenan al capturar (`0x151b14` hace memcpy de
  0xac bytes a la global; `0x151ab4` de 0x38). No están en la imagen del firmware.
- **Vía sin SD:** sin tarjeta, la cámara guarda en la memoria interna. Tomar una foto (o varias, a
  ISO y Sharpness distintos) y leer por USB `0x50f900–0x50fc00` con `tools/leer_ram.py` muestra los
  valores reales y cómo cambian. Sólo requiere la cámara encendida y conectada.

## Tercera revisión (Fable, acotada al código Python) — 2026-11-11

Fable completó una revisión de `m531raw.py`, `e2e_raw.py` y `check_scripts.py` (la revisión amplia
del proyecto la había bloqueado por sus salvaguardas). Hallazgos principales y estado:
- Detección de ancho: correlacionaba filas de colores distintos; fallaba 76 de 90 casos con otras
  fotos. Ahora usa la diferencia horizontal entre píxeles del mismo color, desfases pares y decide
  W/2W por prominencia. Prueba E2E ampliada a 18 fotos × 6 formatos (108 casos, tamaños con
  h//8 o w//8 impares, u16_be): **108/108 OK**. R vs B por heurística acierta 66/108 y se informa
  como provisional (`cfa_rb_provisional`), no se oculta.
- CFA: el recorte perdía la fase con h//8 o w//8 impares → origen par. La E2E exige ahora la diagonal
  verde del DNG leído por LibRaw.
- Confianza: escenas sin estructura (ruido, plano, oscuro) fallan con mensaje en lugar de dar un
  formato inventado. 8 bits leídos como 16 se descartan por estadística de bytes. Disposición
  "apilado" se excluye si los dos campos son casi la misma imagen.
- `check_scripts.py` reescrito como parser estricto: 15 formas de esquivarlo (LET que tapa funciones,
  paréntesis sin cerrar, coma tras la palabra clave, ceros a la izquierda, barras en cadenas, GOTO a
  variable, REMxxx, etc.) quedan bloqueadas; esquemas de argumentos por función. Se quitaron las
  sondas P2/P3 (sintaxis sin palabra clave / con espacios): el verificador ya las prohíbe.
- Pendiente conocido: el orden de los dos campos no se detecta (`--invertir-campos`); el negro
  automático sobreestima en escenas sin negros; la matriz de color es provisional.
