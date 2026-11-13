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

## Origen de los parámetros de procesado (2026-11-11, quinta ronda)

- `0x151b14` / `0x151ab4` no llenan las tablas: **copian hacia afuera** (getters) desde globales
  `0x4f8258` (0xac B) y `0x4f81e8` (0x38 B). Las llena la rutina de `0x151890–0x151a00`, que primero
  llama a `0x6c21c` (lector de calibración/parámetros de la NAND, misma familia que `0x6c55c` y
  `0x6c5d8`) y luego deriva bytes por ISO (`stb … [r1,36]` y `[r1,72]` en bucle).
- Esas globales **sí tienen datos en la RAM en reposo**; guardados en
  `firmware/stock/iq_runtime_0x4f81e8_0x4f8304.bin` (con hash). Son por unidad (calibración).
- Qué campo es NR y cuál realce no se puede deducir sólo del código: hace falta comparar la RAM
  tras capturas con ISO y Sharpness distintos (procedimiento en `sd_kit/PASOS.md`, sin SD).

## Prueba 1 en cámara (2026-11-11)

- **Arranque automático confirmado:** al encender aparece "Script" y luego "Run…"; el firmware crea
  `B:\Batch\BatchScripts.log` y un `.LOG` por script. P1, P4 y P5 corrieron de principio a fin
  **sin ningún error de sintaxis** (copias en `dump/prueba1/`). El reloj de la cámara marca 13-oct.
- Lo dibujado con `ScreenString`/`ScreenInt32` no se ve (la pantalla de arranque lo tapa o el OSD no
  está activo). Para leer valores: `LOG_PRINT <0|1|TRUE|FALSE> <expresión>` escribe en el `.LOG`.
- Foto tomada después (`101_1964.JPG`): **sin RAW**. Nada vuelve a poner la bandera en 0 al entrar a
  captura (los otros llamadores del setter son pruebas de fábrica). Hipótesis: el guardado del CFA
  necesita además el modo de captura 3 → sonda P6 con `Take12BitCCDRaw(1)` y LOG_PRINT.

## Prueba 3 (2026-11-11, cortada por límite de uso)

- Con la SD puesta, la cámara conectada al Mac se presenta como **PTP (clase USB 6)**, no como
  almacenamiento: no aparece el CD virtual y **no se puede leer la RAM** por esa vía. La lectura de
  RAM sólo funcionó sin SD (CD virtual, clase 8). Probar: encender con SD (corre el script), sacar
  la SD con la cámara encendida, conectar USB → ¿aparece el CD? Si no, revisar el ajuste USB del menú.
- El menú oculto **no aparece** con la carpeta `\HiddenMenu` (vía tomada del manual de la M530).
  Pendiente buscar en el código qué comprueba `\HiddenMenu` (cadena referenciada desde 0x23bd5c)
  y si hace falta además una combinación de teclas en About.
- P6 (Take12BitCCDRaw) corrió sin error y sin RAW en las fotos 1965/1966. P6 corregido con
  `LOG_PRINT VERIFY` ya está en la SD; falta leer su .LOG tras el próximo arranque.

## Menú oculto: condición real (2026-11-11)

- La comprobación de `\HiddenMenu` está en `0x23bcf0`, manejador del evento `0x500` (**tecla
  DERECHA**) de la pantalla **`Setup_FormatMenuConfirm`** (tabla en `0x47e7c0`, el nombre encabeza
  la tabla). Pide: carpeta `B:\HiddenMenu` **y** ajuste `0xF` ≠ 0 (`0x6615c(0xf)`); entonces abre la
  pantalla `0x34`. No es "About" como en la M530.
- El ajuste `0xF` vale 0 (palabra `0x00011100` en `0x495a98`; byte bajo = valor). Sólo lo leen el
  menú oculto y pantallas de fábrica (prueba de TV, prueba del AFE). Ningún código lo escribe con ID
  fijo (el escritor genérico es `0x65f68(x, id, valor, y)`).
- Sonda P7: con guardia, lo pone en 1 en RAM y registra antes/después con `LOG_PRINT VERIFY`.
  `sd_kit/fase1/P7OFF.srt` lo devuelve a 0 si quedara guardado al apagar.

## Verificación de Fable antes de ejecutar (2026-11-11) — correcciones importantes

- **RUN**: las líneas numeradas se guardan; sólo una línea `RUN` sin número las ejecuta
  (`0x10776c` → `0x107678`). Confirmado por Fable. Todas las pruebas anteriores sólo cargaron.
- **Sintaxis real** (Fable, verificado): asignar el resultado de una función es
  `FOREIGN a = Run_SpecifyFunc(...)` (`0x10710c`); `LET a = FOREIGN f()` NO existe (LET sólo evalúa
  operandos simples, `0x1993b8`). `IF cond THEN 60` (sin GOTO: `0x107578` arma "GOTO" + resto).
  `LOG_PRINT VERIFY|IGNORE|0|1 <expr sin espacios>` escribe `VERIFY: <valor>` en el .LOG.
- **Cualquier error de script detiene la CPU** (`0x198adc` → `0x3031dc(-1)` → `0x4b4e0` = `flag 1`
  + bucle): la cámara se congela en cada arranque con esa SD. Recuperación: sacar batería y SD,
  corregir o borrar `\Batch`. Por eso el verificador es estricto y la primera prueba es mínima (P0).
- **"Ajuste 0xF" era un estado de tecla:** `0x6615c` es el manejador de `KeyStateGet`; la tabla
  `0x495a5c` se pone a cero en cada arranque y refleja el estado de las teclas. 0xF = **DELETE**
  (0x780 >> 7), 0xA = **DERECHA**, 0xB = OK. **La nota "Sharpness = ajuste 0xA" era errónea** (0xA es la
  tecla derecha); la tabla de ayuda empareja etiquetas de menú rápido con otra cosa.
- **Menú oculto (sin scripts):** carpeta `\HiddenMenu` en la SD, Setup → Format → en la pantalla de
  confirmación, **mantener DELETE y pulsar DERECHA**. P7/P7OFF se descartaron.
- P6 corregido lee el modo de captura en `0x3d97a8` (= 4036520), no en `0x3dbdfc`. Esperado: a=0,
  b=1, c=3. La captura RAW (`0x127168`) sólo exige `SaveCFAonTake == 1`; la hipótesis del "modo 3"
  no tiene respaldo: las fotos sin RAW se explican porque nada se ejecutaba.
- Sin auditar: escrituras a NAND en la ruta de captura en modo 3 (switch `0x128330`).

## PRIMER RAW REAL (2026-11-11, prueba 4)

- P0 y P6 se ejecutaron (con `RUN`): `VERIFY: 0` → `VERIFY: 1` (SaveCFAonTake) y `VERIFY: 3` (modo de
  captura `0x3d97a8`). Sintaxis `FOREIGN a = f()`, `LOG_PRINT VERIFY a` confirmadas en la cámara.
- **Menú oculto abierto** con DELETE+DERECHA en la confirmación de formateo (sin scripts).
- Fotos 1968 y 1969: `101O19xx.RAW` de **28.200.960 B = 4320×3264, u16 LE, 12 bits útiles**
  (máx 4095, negro ≈ 117–120), verdes en (0,0)/(1,1) → GRBG, R/B correctos a ojo (LED rosa). DNG
  revelado con LibRaw: imagen correcta (`dump/raw1/101_1968_preview.png`). Sólo se escribe el
  archivo 'O' (un único cuadro, no dos campos).
- Con modo 3 el JPEG sale roto: un "JPG" de 224 B con texto de diagnóstico
  `Result:IRPTask[3300003] JPEGTask[0] IRPEnd[0]…`; vista previa roja/superpuesta y la segunda foto
  colgó la cámara. Siguiente: P8 activa sólo `SaveCFAonTake(1)` (la captura en `0x127168` sólo exige
  esa bandera) para tener RAW + JPEG normal.
- Conversor: perfil fijo por tamaño (28.200.960 B → u16_le 4320×3264) porque la detección automática
  falló en la foto oscura 1969.

## RAW con JPEG normal (2026-11-11, prueba 5 — P8)

- P8 (`FOREIGN SaveCFAonTake(1)` sólo): `VERIFY 0 → 1`, modo de captura 0. Fotos 1970 y 1971: **JPG
  normal + `101O####.RAW` de 14.100.480 B = 4320×3264, 1 byte/píxel**, sin cuelgues.
- Los 8 bits vienen comprimidos y con el negro ya restado. La tabla de descompresión 8→10 bits está
  en RAM en `0x429c4c` (copia en `0x42a24c`; la inversa justo antes) y es **idéntica a la de la C713**.
- **Patrón Bayer real: GBRG.** La heurística daba GRBG; el ajuste RAW↔JPG (JPG = RAW recortado 16/24 px
  por lado y rotado −90°) dio una matriz con diagonal invertida hasta cambiar R↔B.
- Conversor: perfiles por tamaño (14.100.480 → u8 + tabla, 28.200.960 → u16 12 bits), CFA GBRG,
  balance por foto ajustado contra el JPG hermano (fallback mundo gris), CCM ajustada M531
  (`firmware/stock/ccm_ajustada_1970_1971.json`, provisional: 2 escenas de interior) o `--matriz c713`.
  Comparación visual: `dump/raw2/comparacion_matrices.png`.
- La orientación: el RAW sale en la orientación del sensor; el JPG lo rota la cámara (sensor de
  orientación). No se fuerza rotación en el DNG.

## Modo de 12 bits sin romper el JPEG (Fable, 2026-11-11) — por probar

- El JPG de 224 B sale de `0x15714c` cuando el IRP no arranca. Error `0x03300003` del validador
  `0x2b0160`: la línea de entrada supera `0x1ffc` B. Modos 1 y 3 (16 bits) → 8640 B/línea → fallan.
- Modo de captura → formato IRP (`0x128344`): 0→0 (8 b), 1→5, 2→1 (10 b empaquetado, 5400 B/línea),
  3→6, 4→2 (**12 b empaquetado, 6480 B/línea, pasa**). RAW esperado en modo 4: 21.150.720 B;
  en modo 2: 17.625.600 B. Registro del sensor `0x0ff10080` (`0x17ac50`/`0x17ace8`).
- Vista previa roja (sospecha fuerte): el IRP de previsualización (`0x128542`) también toma el modo
  global mientras el sensor queda en 8 bits. Puede seguir dañada en modo 4. Cuelgue de la 2.ª foto:
  causa sin determinar (sospechas: vista previa mal formateada; parada incompleta en `0x129a1c`).
- P9: `SaveCFAonTake(1)` + `Run_SpecifyFunc(0x6e0b0, 1, 0, 4, …)` (setter de modo, sólo RAM),
  registra el modo (esperado 4). El verificador admite ese destino con valores 0–4.
- Conversor: perfiles 21.150.720 (12 b) y 17.625.600 (10 b) con orden de empaquetado detectado
  (probado con mosaicos sintéticos p12_msb y p12_lsb de 4320×3264).

## FE DE ERRATAS (revisión de Fable, 2026-11-12) — prevalece sobre lo anterior

Secciones anteriores que quedan superadas (no se reescriben para conservar el historial):
- Menú oculto por "Setup → About" (y la carpeta sola): **incorrecto**. Es Setup → Format →
  confirmación, mantener DELETE y pulsar DERECHA. En esa pantalla OK formatea.
- `0x6615c` como lector de ajustes, "Sharpness = ajuste 0xA", "ajuste 0xF", P7/P7OFF y el plan de leer
  `0x495a5c`: **incorrecto**. `0x6615c` es el estado de teclas (`KeyStateGet`).
- "P1, P4 y P5 corrieron sin errores de sintaxis": sólo se **cargaron** (sin `RUN`). Lo confirmado
  en la prueba 1 es el arranque automático y la creación de los `.LOG`.
- Nombres de RAW: sólo se escribe `101O####.RAW` (un cuadro), no dos campos 'O'/'o'/'b'.
- Patrón "GRBG, R/B correctos a ojo": **incorrecto**; es GBRG, verificado en 8 bits (1970/1971) y en
  modo 4 (1972–1974, correlación de croma con el JPG −0,84 a −0,93). Para los RAW de 16 bits (modo 3)
  sigue siendo extrapolación. Los DNG de `dump/raw1` se generaron con el patrón viejo.
- Hipótesis "hace falta modo 3 para el RAW": **incorrecto** (bastaba la bandera; nada se ejecutaba).
- "0x2bcdb8 llama a 0x2bd664": **incorrecto** — ver REVERSIBILIDAD (ruta 5-en-1 en `0x2bd024`).
- "rec4–6 idiomas: coincide el idioma cargado": sin respaldo; ninguna suma coincide con la RAM.
- La tabla `0x429c4c` como decodificación del RAW de 8 bits: correcta por resultado y por la C713,
  pero sin traza de código que la use (punteros en `0x13aa70–0x13aa7c`, `0x4d1ef4`).
- "El JPG lo rota la cámara (sensor de orientación)": sospecha; los JPG tienen EXIF orientación 1.

## Modo 4 en cámara (2026-11-12, prueba 6 — P9)

- `VERIFY: 4`. Tres fotos (1972–1974) **sin cuelgue**: RAW de 21.150.720 B (12 b empaquetado, orden
  lsb) con **datos de 10 bits lineales, negro restado** (máx 1020) + JPG válido de ~2 MB pero con
  **tinte rosado**; la revisión tras el disparo se ve como ruido morado (vista previa con formato
  equivocado, como predijo Fable). Patrón GBRG verificado. El balance no se puede calibrar con estas
  fotos: los canales llegan con otras ganancias que en el modo 0 y el JPG no sirve de referencia.
  Siguiente: la misma escena en modo 0 y en modo 4 para medir la relación entre ambos.
- Macropad (1975–1977, modo 4): neutro sobre la tecla casi blanca = (0,81, 1, 0,77), estable entre
  fotos; queda como balance fijo del modo 4 (`NEUTRO_M531_MODO4`). La madera sigue verdosa-amarilla con
  ambas matrices; la de la C713 da colores de teclas más fieles en este modo. Pendiente: la misma escena
  en modo 0 (P8, ya en la SD) para comparar contra el JPG bueno y ajustar matriz/balance del modo 4.

## Modo 4 calibrado (2026-11-12, prueba 7 — pares modo 0 / modo 4)

- Pares de la misma escena con flash (ISO 64, 1/30, f/3,1): 1976↔1978 y 1977↔1979; sin flash 1975↔1980.
- **Los datos del modo 4 vienen comprimidos con la misma curva que el modo de 8 bits, pero con 10 bits
  de precisión** (código10 ≈ 4·código8). Sin decodificar, la relación con el modo 0 tenía pendiente
  log-log 0,68; con la curva, 0,89 y casi constante en medios y altos. Tras decodificar, los canales
  coinciden con el modo 0 (R 0,94–0,99, B 1,02–1,06): mismos datos, más precisión.
- Conversor: perfil 21.150.720 B decodifica con la curva de 10 bits; balance fijo del modo 4 =
  (0,62, 1, 0,60) con flash. Resultado visual igual al JPG de la cámara
  (`dump/raw5/modo4_decodificado.png`).
- Conclusión práctica: **P9 (modo 4) da RAW de 10 bits efectivos, estable, sin cuelgues**; el JPG de
  ese modo sale rosado (no importa si se usa el RAW). P8 (modo 0) da RAW de 8 bits + JPG correcto.

## Reducción de ruido y realce del JPG (Fable, 2026-11-12) — mapa y primer script

- Pipeline de foto fija: HWIRP → CFR → NRE → ASharp → (ALT) → JPEG (`0x12989c`, variante con NRE
  `0x1c3410`). Montaje por captura en `0x127ef0`.
- **Realce del ASIC:** LUT de 35 puntos de 7 bits en `cfg+0x130` → registro `0x0ff50c18`; elegida por
  `0x1b3930` según Sharpness (byte vivo `0x3dbccb`, setter `0x123448`; 0 Normal, 1 Bajo, 2 Alto) y por
  banda de ISO (`0x1b399c`, 11 bandas). Los punteros salen de literales de código con una única carga
  cada uno (tabla completa en el informe de Fable; ISO ≤159 Normal = `0x1b3d80` → `0x4443d0`,
  curva 0→50). Sospecha fuerte: es ganancia (Bajo = 20, Normal = 50, Alto = 77; baja con el ISO).
- **NR:** NRE multiescala (`0x1baa88` → `0x511f1c`): por debajo de ISO 221 sólo croma, desde 221 también
  luma. Sub-bloque Y/C del ASIC: modo 0 hasta ISO 220. ASharp es un segundo realce independiente de
  Sharpness (desactivable con un parche de código en `0x128900`).
- **Persistencia:** los pokes a literales viven en RAM; el setter de Sharpness desde script no llega a
  la NAND salvo que luego se confirme Sharpness en el menú (equivale a elegirlo a mano).
- Corrección: `0x5dbd0` es el paso de zoom, no el nivel de ISO.
- Kit `sd_kit/fase3`: P8 + EE0 (realce a cero en ISO ≤159 Normal), verificado contra la RAM.

## Balance de blancos por foto en modo 4 (2026-11-12)

- **El AWB de la cámara queda en el MakerNote del JPG**: ganancias R, G, B (÷256) como tres u32 en los
  desplazamientos `0x1318` y `0x21a0` del MakerNote (copias u16 en `0x483e` y `0x4c74`). En modo 0
  coinciden con el ajuste RAW↔JPG: 1978 = (400, 256, 451) → neutro (0,640, 1, 0,568) contra (0,639, 1,
  0,578) del ajuste; 1980 = (248, 290, 948) → (1,169, 1, 0,306) contra (1,157, 1, 0,322).
- **Idea descartada: sacar el balance del JPG rosado del modo 4.** Sin flash, la cámara deja en modo 4
  el valor por omisión (400, 256, 456) — el mismo en 1975 y 1981, y el mismo de la 1920 en modo 0 —
  cuando la luz real pide (248, 290, 948): el AWB no llega a calcularse (la vista previa tiene el
  formato equivocado) y el JPG no lleva información de la luz. Con flash sí se mueve, con un corrimiento
  estable en la única escena con par (verdad ÷ modo 4: R 1,19–1,25, B 0,870–0,874 en 1976, 1977, 1982);
  aplicado a las fotos sin flash da (0,78, 1, 0,49) contra (1,17, 1, 0,31): error de 40–47 %.
  El ajuste RAW↔JPG tampoco sirve: sobre datos decodificados da correlación < 0,9 en 7 de 8 fotos y
  neutros negativos en 3; sobre códigos sin decodificar da B ≈ 0,62 constante con y sin flash.
- **Método elegido: parche blanco sobre el RAW** (`neutro_parche_blanco`, 2 % más claro sin saturar),
  aceptado sólo si cae cerca del lugar de los balances que la cámara elige. Ese lugar sale del
  MakerNote de 67 JPG de modo 0 (1900–1971): ln(nB) = −0,924 − 0,883·ln(nR), rms 0,028. Fuera de
  ±0,20 o del rango de ln(nR) −0,74…0,33, cae al neutro fijo (0,62, 1, 0,60).
- Error contra el AWB de la cámara (máximo de |ln| en R y B) en 10 fotos con verdad independiente
  (modo 0: 1970, 1971, 1978–1980; modo 4 con par: 1975–1977, 1981, 1982): parche blanco media 0,083,
  peor 0,18; mundo gris media 0,16, peor 0,31; proyectar sobre la recta no mejora (0,10 / 0,20).
  Foto 1981 (sin flash): (1,091, 1, 0,323) contra (1,157, 1, 0,322) de la 1980; antes salía naranja
  con (0,62, 1, 0,60). Comparación: `dump/raw6/balance_por_foto.png`.
- `m531raw.py dng` informa `awb_camara` y acepta `--balance fijo`. `e2e_raw.py` compara el neutro de
  cuatro RAW de modo 4 con su par de modo 0 (tolerancia 0,15) y exige la caída al fijo en una escena
  cuyo punto más claro es verde.

## Revisión de los kits de la SD (2026-11-12)

- **Ningún `IF` corrió todavía en la cámara.** Los .LOG de P0, P6, P8 y P9 sólo prueban
  `FOREIGN v = Run_SpecifyFunc`, `FOREIGN f(x)`, `LOG_PRINT VERIFY` y `END`. EE0 es el primer script con
  `IF` y con `poke32` (`0x2e8a84` = `j_s.d [blink]; st_s r1,[r0,0]`).
- **`IF` leído en el desensamblado** (`0x107578`): corta en `THEN`, recorta espacios (`0x1996f4`),
  evalúa la condición con `0x19943c` y exige resultado booleano; si es cierta ejecuta `GOTO` + destino
  por `0x1071ec`, el mismo camino de un `GOTO` suelto. El evaluador `0x1991f4` prueba los operadores en
  el orden de la tabla `0x442630` (`&& || >= <= == != ! > < + - * / % ^ ~ & |`), parte en el primero
  que aparece y exige que cada lado sea un símbolo simple (`0x1990d0`: sólo dígitos, decimal con un
  punto, TRUE/FALSE, cadena o variable).
- **Un literal negativo como operando detiene la CPU**: en `v == -670990368` el lado derecho no es
  ningún símbolo válido. Los MEMRW, ASHARP0 y NRE0 anteriores tenían esa comparación: habrían congelado
  la cámara. `patch2srt.py` ahora trabaja por mitades de 16 bits con `peek16` = `0x736e6`
  (`j_s.d [blink]; ldw_s r0,[r0,0]`) y `poke16` = `0x13f09a` (`j_s.d [blink]; stw_s r1,[r0,0]`), sin
  números negativos, sin GOTO y con variables de una letra; los tres scripts están regenerados.
- EET reescrito sin GOTO: las 11 guardias primero (si una falla, anota y termina), luego las 11
  escrituras y las 11 relecturas.
- `check_scripts.py` rechaza ahora: `IF` que no sea `IF var == ENTERO_SIN_SIGNO THEN línea`, argumentos
  negativos o mayores que 2147483647 en `Run_SpecifyFunc`, GOTO/GOSUB/RETURN/ELSE/LET, y líneas sin
  CRLF. Admite `peek16`/`poke16` con las mismas zonas intocables.
- EE0 verificado: `0x1b3d80` vale `0x4443d0` en el código de fábrica y en la RAM, y lo carga una sola
  instrucción (`0x1b3ae0`, rama ISO ≤ 159, destino `[r2+0x38]`); `0x4443d0` es la curva 0→50 de 35
  puntos u16; `0x444018` es una tabla de ceros del firmware (literal `0x1b3d48`), con ceros hasta
  `0x4440e3`. Las 11 direcciones de EET y las guardias de MEMRW/ASHARP0/NRE0 coinciden con la RAM.
- La única palabra del código que difiere entre `rec0_code_0x48000.bin` y la RAM es `0x38ac4c`
  (0 contra 0x08000000); ningún script la toca.
- SD: copiados `BatchScripts.txt` (P8, EE0), `P8.srt` y `EE0.srt`. Los .LOG anteriores quedaron en
  `dump/raw7/` (no había fotos nuevas después de la 1982).

## Modo 3 (RAW de 16 bits): JPG roto y cuelgue en la segunda foto — análisis estático (2026-11-12)

Evidencia: `docs/decomp_modo3.c` (Ghidra, sin editar), `work/code_full.s`, la tabla de pools de la
RAM y los archivos de `dump/raw1`. Sin cámara: lo que sigue separa lo leído de lo supuesto.

**Demostrado en el código**
- El validador del HWIRP `0x2b0160` calcula los bytes por línea según el formato (`ctx+0x2c`):
  0 → ancho; 1 → ancho·10/8; 2 → ancho·12/8; 5 y 6 → ancho·2; y exige ≤ `0x1ffc`. Con 4320 px los
  formatos 5 y 6 dan 8640 y devuelve `0x03300003`. Los formatos 3 y 4 saltan esa comprobación
  (rama `default`); nada los usa.
- El modo de captura se traduce a formato del IRP en dos tablas de saltos de un byte por modo:
  `0x128344` (bytes `03 0c 06 0f 09`, montaje de la foto, `0x127ff4`) y `0x1286dc` (bytes
  `03 0b 05 0e 08`, función `0x12853c`). Modo 0 → 0, 1 → 5, 2 → 1, 3 → 6, 4 → 2. Son el único uso
  del modo dentro de la configuración del IRP.
- El error nace en el primer paso de la tarea JPEG (`0x155b3c` → `0x12989c` → cuerpo `0x1c3410` →
  `0x1bc528`/`0x1bc5a8`) y el cuerpo sale por `0x1c6326` sin pasar por `0x129ba0` ni `0x129be0`.
  Esas dos funciones son las únicas halladas que llaman al gancho de vista rápida (`0xf0d14`,
  puntero en `0x3dbdb4`), y de ese gancho cuelgan los tres llamadores de `0x12bc04`, que es quien devuelve la
  ranura del RAW a la cola libre, activa el evento `0x10` del grupo `0x40100004` y desarma la cola.
  Con el IRP rechazado, esa liberación no ocurre por esta vía.
- La tarea termina en `0x15714c`, que escribe el "JPG" de 224 B (`FF D9` + texto de `0x3dc694`).
  Los dos archivos de `dump/raw1` (1968 y 1969) son idénticos: `IRPTask[3300003] JPEGTask[0]`.
- Primera y segunda falla no recorren lo mismo. La tubería (`0x3dbd98`) arranca en estado 0; en la
  primera falla `0x129a1c` acepta el estado 0, corre la parada, borra el contexto del gancho
  (`+0x18`), suelta el reloj (`0x1bc2ac` → `0xfa338(6)`) y deja el estado en 4. En la segunda,
  `0x12989c` vuelve a tomar el reloj (`0x1bc294` → `0xfa21c(6)`) y a armar el gancho, falla, y
  `0x129a1c` encuentra el estado 4: devuelve `0x04800101` sin parar nada, sin borrar `+0x18` y sin
  soltar el reloj. `0xfa21c`/`0xfa338` son contadores de referencia de reloj, no cerrojos.
- En la ruta directa del HWIRP (`0x2b0948`) la validación corre después de tomar el reloj
  (`0xfa21c(4)`), fijar pines y habilitar la interrupción `0x603`; al fallar sólo se llama a
  `0x2b0930` (bandera + evento `0x100`). No se encontró ningún lector de la bandera `0x3e506c`.
- **Memoria del RAW.** Tabla de pools en `0x3e7c40` (gestor `0x4964dc`, entradas de 0x18 B). El
  pool 8 mide `0x1ae5000` = 28.200.960 B (`0x213e000–0x3c23000`): exactamente un RAW de 16 bits.
  `0x12aba4` lo parte en ranuras de `ceil1024(ancho·alto)` = 14.100.480 B **sin mirar el modo**: dos
  ranuras, en `0x213e000` y `0x2eb0800`, que salen de una cola FIFO (`0x294594`/`0x2945e8`). La
  cola se arma en cada disparo si estaba desarmada (`0xf08b4`) y `0x12bc04` → `0x12ac94` la
  desarma cuando no queda nada pendiente, así que un disparo aislado cae siempre en la ranura 0.
  Un RAW de modo 3 (28,2 MB) o de modo 4 (21,15 MB) escrito en la ranura 1 pasaría el final del
  pool y el de la SDRAM (`0x4995800` y `0x42dc400` contra `0x4000000`).
- `Take12BitCCDRaw` del menú DEBUG hace lo mismo que el script: `0x1f289c` invierte SaveCFAonTake
  y pone el modo 3 o 0. No hay otra preparación de fábrica para el modo 3.

**Demostrado con los archivos**
- `101O1969.RAW` (segunda foto) es una imagen completa y coherente hasta la última fila. Las filas
  2100 en adelante habrían quedado fuera de la SDRAM si esa captura hubiese ido a la ranura 1: la
  segunda captura **no** desbordó. El cuelgue llegó después de escribir el segundo RAW y el segundo
  "JPG" de 224 B.

**Sin determinar**
- La instrucción donde se cuelga. Lo leído deja dos sospechas, ninguna probada: (a) el estado que
  la segunda falla deja sin limpiar (gancho armado con contexto viejo, parada omitida); (b) las
  esperas sin tiempo límite sobre el evento `0x10` (`0x12ae6c`) y sobre la cola de trabajos
  (`0x76664`, bucles en `0x12bc64` y `0x1ea5ba`), que dependen de una liberación que no llega.
- Por qué la segunda captura volvió a la ranura 0 si la primera no se liberó por `0x12bc04`: hay
  otro desarme (`0x12bc64` → `0x12ad2c`, llamado desde la interfaz) que no se siguió.

**Arreglo propuesto, sólo RAM: `sd_kit/fase1/Batch/M3F2.srt` (experimental, fuera de BatchScripts.txt)**
- Cambia el byte del modo 3 en las dos tablas para que el IRP use el formato 2, el mismo del modo 4
  (6480 B por línea, pasa el validador): palabra `0x128344` de `0x0f060c03` a `0x09060c03` y palabra
  `0x1286dc` de `0x0e050b03` a `0x08050b03`. Luego SaveCFAonTake(1) y modo 3. Con guardia: si una
  palabra no es la de fábrica, anota la lectura y termina.
- Son bytes de tablas dentro de la sección de código que se leen como datos (`ldb.x`), igual que el
  literal de EE0: no hace falta vaciar caché. Coinciden en `rec0_code_0x48000.bin` y en la RAM.
- Efecto esperado: el sensor sigue entregando 16 bits y el RAW sale de 28.200.960 B con 12 bits
  lineales. El IRP lee ese búfer como 12 bits empaquetados (usa 21,15 MB de los 28,2), así que el
  JPG y la revisión salen como ruido, pero la tarea JPEG recorre el mismo camino que en el modo 4,
  que en la cámara no se cuelga: el gancho corre y la ranura se libera.
- Lo que no garantiza: que el cuelgue desaparezca (la causa exacta no está probada) ni el tamaño
  del JPG de ruido. Si la cámara se congela: batería y SD fuera; nada queda escrito.
- Un cambio del límite `0x1ffc` no es seguro: es el tope de la línea de entrada del ASIC, y el
  comparador es un inmediato de instrucción (`0x2b028a`), no un literal.
- Precaución para P9 (modo 4) y M3F2: esperar a que termine de guardar antes de disparar otra vez.
  Una captura con la anterior todavía en proceso tomaría la ranura 1.
- Orden de prueba: EE0 primero (estrena `IF` y `poke32`); después M3F2 solo en `BatchScripts.txt`,
  tres fotos seguidas esperando el guardado, y leer `M3F2.LOG` (esperado: `252054531`, `235211523`,
  `151391235`, `134548227`, `3`).

## Cargador de arranque leído desde la RAM (2026-11-12)

- **El boot está entero en la RAM**: `0x800000–0x82cff0`, con su cabecera de 16 B justo antes
  (`0x7ffff0`: carga `0x800000`, tamaño `0x2cff0`, sum32 `0xbbb66ba4`, entrada `0x800030`). La
  sum32 de esos `0x2cff0` B en `dump/ram_snapshot.bin` da `0xbbb66ba4`, la misma que guarda la tabla
  de particiones (`0x4da228 + 0xb4`). Copia en `firmware/stock/boot_hdr16_0x800000.bin` (con hash;
  SHA-256 del cuerpo `feedac93…2129e`). Datos inicializados en `0x850000…` con valores de la última
  ejecución. Decompilación: `docs/decomp_boot.c`; proyecto Ghidra `boot_ram_0x800000.bin`.
- Es una aplicación MQX con FAT: tareas `BootTask` (`0x800df8`), `MCUCTRL_Task`, `RTOSINIT`;
  dispositivos `DEVNAND:`, `PMNAND:`, `DEVSD:`, `PMSD:`. No tiene cadenas ni descriptores de USB de
  almacenamiento o descarga; la rama con USB (`0x801224`) es la carga de la batería.
- **Arranque desde la NAND** (`0x800f58`): lee el sector 0 de la partición 6 (`0x807890`, mismos
  campos `+0xd0`/`+0xde` de la tabla que usa el firmware), exige `RHIR` (error `0xb`) y palabra de
  modelo `0x01121410` (error `0xe`), y recorre los registros: los de tipo 1 se leen a su dirección
  de RAM y se comprueba su sum32 con la función de `0x800000` (error `0xd`; lectura fallida `7`); el
  de tipo 2 sólo guarda su sector y cuenta en `0x850400` (hoy `0x0004b440`: sector 46144, 4
  sectores); los de tipo 0 no se leen. No mira `KHIR` ni el tamaño total.
- **Vía de recuperación** (`0x800df8`): si el arranque desde la NAND falla, carga
  `A:\TBM_HD14P.BIN` (`0x801100`) y, si también falla, hay SD y el byte `0x850405` vale 1,
  `B:\TBM_HD14P.BIN`. El archivo tiene el formato RHIR de `KM531.FW`: cabecera de 16 B, registros a
  continuación, cada tipo 1 se lee del archivo a RAM y se verifica con sum32 (`0x801060`). Esta
  ruta sólo lee: no escribe la NAND.
- **Arranque forzado desde la SD**: al inicio (`0x8002e6`) el boot lee el estado de teclas
  (`0x803108`, registros `0x0fe70224`/`0x0fe70228`); con el bit 12 en 0 pone `0x850404 = 1` y
  `0x850405 = 0`, y entonces `BootTask` prueba `B:\TBM_HD14P.BIN` **antes** que la NAND. En el
  firmware principal ese mismo bit es la tecla de identificador `0xF` (tabla `0x3ea620`, entrada
  17: máscara `0x1000`), que es **DELETE** (la del menú oculto). En reposo el estado es
  `0x01ffffff` (teclas activas en 0) y `0x850404` vale 0: el último arranque fue normal.
- Si todo falla, `0x8003cc` parpadea los tres LED tantas veces como el código de error, sin fin
  (7 lectura, 8 unidad, 9 archivo, 10 lectura corta, 11 magia, 13 suma, 14 modelo).
- El boot deja en `0x900` el bloque `INFO` (`+0x24 = 0x55aaaa55`, `+0x28` = origen: `0x10` NAND,
  `0x20` archivo). Hoy vale `0x10`. El firmware principal lo lee en `0x7c1da`: con `0x20` pasa la
  ruta de `B:\TBM_HD14P.BIN` (`0x4c1c8`) a `0x17151c` antes de cada lectura con `0x171524`
  (`0x7c1f4`, `0x137e92`, `0x1380cc`, `0x234554`). Por el patrón, es el origen de los recursos
  (gráficos e idiomas, registros tipo 0) cuando se arrancó desde archivo; es una inferencia: esas
  dos funciones no se leyeron. Los demás usos de la ruta están en la NAND Tool y en los scripts.
- **Tabla de particiones** (`0x4da228`, empieza por `P1IDSTR`; bloques de 32 sectores = 16 KiB):
  P0 boot 695–710 (0x3c000 B), P1 calibración 0–10, P2 calibración (copia) 10–20, P3 parámetros
  20, P4 parámetros (copia) 21, P5 reserva 22–195 (0x2b4000 B), P6 código principal 195–695
  (0x7d0000 B). El boot ocupa 12 bloques (`+0xac`).
- **Actualizadores del firmware principal** (`work/decomp_upd.c`):
  `0x2bd5bc` (partición 6) valida con `0x2bd46c` antes de escribir, escribe, relee y compara,
  hasta 3 veces; escribe en sitio, sin copia.
  `0x2bcf28` (boot, `B:\TBIB_HD14P.BIN`) → `0x2bd664` sólo exige tamaño ≤ partición 0 y, según un
  parámetro, la palabra de modelo en los últimos 16 B; no verifica ninguna suma del boot antes de
  escribir. Escribe la partición 0 y actualiza la cabecera del boot en la tabla (`0x1445d0` caso 0).
  `0x2bd024` (5-en-1): primera palabra = XOR del resto (`0x2bd58c`), dos bloques (principal y
  boot); busca `INFO`+`0x55aaaa55` en el bloque del boot y entonces escribe la partición 0 y luego
  la 6.
- **Qué pasa con una partición 6 mala**: cabecera, modelo, lectura o suma de un registro tipo 1
  incorrectos → el boot no la arranca y pasa a los archivos TBM. Una partición 6 con sumas
  correctas y código que no funciona **sí** arranca: para ese caso está DELETE al encender.
- La C713 de referencia (`ref/ModernShare/docs/research-notes.md`) sólo dice que el boot no forma
  parte de la actualización y que por eso una imagen mala "hasta ahora siempre fue recuperable";
  no describe el mecanismo. Lo de arriba sale del boot de la M531, no de la C713.

## NAND Tool: manejadores de Dump (2026-11-12)

- Despachador en `0x24cb26`: tabla de saltos de 16 bits en `0x24cb44`, 32 entradas (identificadores
  `0x19–0x38`). Volcados: `0x19` → `0x2c0510(1)` y `0x2c0510(2)` (A1); `0x1e` → `0x2c0510(6)` (B3);
  `0x21` → `0x2c0510(0)` (C1); `0x23` → `0x2c0738` (D1); `0x24` → `0x2c0510(3)` y `(4)` (E1);
  `0x26` → `0x2c0510(5)` (F1); `0x28` → `0x2c0620` (G1); `0x34` → `0x2c09e4` (I4); `0x36` →
  `0x2c1908` (I5).
- `0x2c0510(partición)`: arma `B:\` + nombre (bloque de cadenas en `0x3534b8`: 0 `BootCode.dmp`,
  1 `Calibration.dmp`, 2 `Calibration_2.dmp`, 3 `CameraParam.dmp`, 4 `CameraParam_2.dmp`,
  5 `NANDReserved.dmp`, 6 `MainCode.dmp`), pide el búfer del pool `0x20`, comprueba que la partición
  quepa, lo llena de `0xFF`, lee con `0x1436fc` y escribe el archivo con `0x2c06b0`. **A1 y E1
  escriben dos archivos cada una.**
- D1 escribe diez líneas `"%-40s0x%04X\r\n"`: `uwReg_Configuration`, `uwReg_AutoRefresh`,
  `uwReg_Control`, `uwSize_BootCode`, `uwSize_Calibration`, `uwSize_CameraPara`, `uwSize_Reserved`,
  `uwSize_HexMain`, `uwProductID`, `uwPartition_Ver`. Con la tabla de la RAM: `0, 0, 0, 0xF, 0xA,
  0x1, 0xAD, 0x1F4, 0x1224, 0x10`.
- **Quién puede escribir la NAND.** Todas las órdenes al chip pasan por `0x12ebfc` (21 llamadas en
  todo el código). Programan (órdenes `0x80`/`0x10`) sólo `0x131ad0`, `0x131b58`, `0x131bb4` y
  `0x131c0c`; borra (`0x60`/`0xD0`) sólo `0x1d1540`. El resto son lecturas (`0x00` en `0x130e14`,
  `0x50` zona de reserva en `0x130e9c`), estado (`0x70`) y reinicio (`0xFF`).
- Cierre de llamadas directas (`bl`) sobre `work/code_full.s`: desde la escritura de partición
  `0x1447a0` se llega a programar y borrar en 4 niveles y el cierre se agota en 211 funciones. Desde
  las lecturas de I4 (`0x14382c`, 34 funciones), I5 (`0x1439d4`, 29), G1 (`0x143774`, 15) y D1
  (`0x657e0`, 4) el cierre se agota sin tocar ninguna de las cinco. Desde `0x1436fc` (A1, B3, C1,
  E1, F1) no aparece ninguna en 16 niveles; más allá el cierre abarca todo el firmware (los
  literales desensamblados como saltos lo contaminan) y deja de informar. Límites: no sigue saltos
  de cola ni llamadas por puntero. Los archivos se escriben en `B:` (SD), no en la memoria interna.
- Escriben o borran: `0x1a` A2 (`0x2c0704`), `0x1b` A3 y `0x1c` B2 y `0x27` F2 (`0x2c0450`, borra la
  partición), `0x1d` B1 (`0x2bcdb8` con `TBM`), `0x1f` C2 (`0x2bcf28`), `0x22` D2, `0x25` E2, `0x29`
  y `0x2a` formateos, `0x33` 5-en-1. La entrada `0x20` no tiene texto en la lista del menú: consulta
  `B:\ALLOW_ERASE_BOOT` y llama a `0x2c0450(0)`.
- Sin determinar: el aspecto del menú en pantalla y sus teclas, y el largo de cada archivo.
- Kit: `sd_kit/nand_dump/`. Verificador: `tools/verificar_volcados.py` (fallas previstas en
  `tools/NAND_FALLAS.md`; prueba `tools/e2e_nand.py`, 16 casos).

## Matriz de color v2 (2026-11-12)

- `tools/ajustar_ccm.py` ajusta `CCM_M531` con las cinco fotos de modo 0 que tienen JPG del mismo
  disparo (1970, 1971, 1978, 1979, 1980): balance del MakerNote, bloques de 32 px, Huber, filas que
  suman 1 y una curva de tono por foto. Valida dejando una escena fuera (1970 | 1971 | macropad).
- ΔE2000 medio en la foto retenida, contra el JPG de la cámara: anterior 3,32 · C713 3,35 · nueva
  2,92 (1970: 4,56/4,94/4,45; 1971: 2,65/2,67/2,05; 1978: 3,15/2,59/2,62; 1979: 3,02/2,75/2,43;
  1980: 3,23/3,82/3,05). Mejora a la anterior en las cinco. Adoptada; `--matriz c713` sigue igual.
  Resultado completo en `firmware/stock/ccm_ajustada_v2.json`.
- Límites: tres escenas de interior y dos luces; la referencia es el JPG de la cámara (reproduce su
  color, no una carta); el término de regularización se eligió mirando los mismos pliegues (con
  0,02 hacia la identidad la nueva no gana; quedó en 0, mínimos cuadrados sin regularizar). Los RAW
  de modo 4 no entraron: su par de modo 0 es otro disparo y no alinea píxel a píxel. Los DNG ya
  generados en `dump/` llevan la matriz anterior.

## Fe de erratas, añadido del 2026-11-12 (tarde)

- "Falta saber quién usa el bloque 1442": el boot guarda el sector y la cuenta del registro tipo 2
  en `0x850400`; qué hace con ellos no se leyó.
- "A1 Calibration.dmp" y "E1 CameraParam.dmp" como un archivo por opción: son dos por opción.
- "No se flashea nada hasta tener … la vía de recuperación del boot": la vía existe en el código
  del boot (archivos TBM y DELETE al encender). Falta probarla en la cámara; ver REVERSIBILIDAD.
- "El cuelgue de la segunda foto en modo 3: sospecha de vista previa mal formateada": la segunda
  captura y su "JPG" de 224 B se completaron; el cuelgue es posterior y su causa sigue sin probar.

## 2026-11-12 — EE0 probado en la cámara: realce del JPG a cero (ISO ≤ 159)

- Primera vez que corren en la cámara un `IF` y un `poke32`: `EE0.LOG` = `VERIFY: 4473808` y luego
  `VERIFY: 4472856`. Sin congelamiento. P8 siguió dando `0 / 1 / 0`.
- Fotos en `dump/raw8` (con `SHA256SUMS`), modo 0 (P8), Sharpness Normal, misma escena:

  | foto | kit | ISO | flash | borde JPG / borde RAW | energía alta frec. JPG | RAW |
  |---|---|---|---|---|---|---|
  | 1984 | P8 + EE0 | 64 | sí | 0,356 | 0,054 | 0,084 |
  | 1985 | P8 solo | 64 | sí | 0,568 | 0,118 | 0,073 |
  | 1983 | P8 + EE0 | 160 | no | 0,396 | 0,106 | 0,120 |
  | 1986 | P8 solo | 160 | no | 0,375 | 0,115 | 0,126 |

  "Borde" = media |laplaciano| en el centro; la razón JPG/RAW quita la diferencia de enfoque y escena.
  Con ISO 64 EE0 baja el realce un 37 % y la energía de alta frecuencia del JPG a la mitad, con el RAW
  igual. Con ISO 160 no cambia nada: es la banda siguiente, que EE0 no toca. Coincide con el análisis.
- Para cubrir ISO ≥ 160 hace falta EET (todas las bandas), todavía sin probar.
- 101_1987.JPG quedó de 0 B (disparo seguido); el RAW está completo. `m531raw.py` ya no falla con un
  JPG hermano vacío o truncado.
- El único error del verificador sobre la SD fue `._BatchScripts.txt` (metadatos de macOS al escribir
  con `printf >`); escribir en la SD con `cp -X` o borrar los `._*` antes de expulsar.

## M3F2: revisión independiente antes de probarlo (Fable, 2026-11-12)

Revisión del script contra `firmware/stock/rec0_code_0x48000.bin`, `dump/ram_snapshot.bin` y
`work/code_full.s`. Sin cámara. Veredicto: el arreglo es coherente con el código y se puede probar;
la causa del cuelgue sigue sin estar probada, así que la prueba es la que decide.

**Comprobado**
- Tablas: `0x128344` = `03 0c 06 0f 09` y `0x1286dc` = `03 0b 05 0e 08`, iguales en el firmware de
  fábrica y en la RAM. Base de cada tabla = `pcl + 0xc` (`0x128338`, `0x1286d0`), destino = base +
  2·byte. Modo 3: `0x128362` y `0x1286f8` (`mov_s r0,6`); modo 4: `0x128356` y `0x1286ec`
  (`mov_s r0,2`). Cambiar el byte 3 a `09` / `08` lleva el modo 3 al bloque del modo 4.
- Los cuatro bytes de cada palabra escrita (`0x128344–47`, `0x1286dc–df`) son las entradas 0–3 de la
  tabla; la entrada 4 está en la palabra siguiente y no se toca. Las palabras nuevas `0x09060c03`
  (151391235) y `0x08050b03` (134548227) conservan los otros tres bytes. Ninguna instrucción cambia.
- Caché: las tablas se leen con `ldb.x` (carga de datos) y se escriben con `poke32` (almacenamiento
  de datos): mismo camino que el literal de EE0 (`0x1b3d80`, también dentro de la sección de código),
  que funcionó en la cámara. Una caché de instrucciones, si existe, no interviene porque no cambia
  ningún byte ejecutable. No hace falta `dcache_flush_range`, y no usarlo evita estrenar una primitiva.
- El modo (`0x3d97a8`) sólo se lee con `0x6e0d0`; no hay accesos directos (las cuatro coincidencias
  de la búsqueda son `0x4d97a8`). Diez llamadores: las dos tablas; `0x12b4a0`, `0x12b536`, `0x12b628`
  (distinguen modo 0 del resto: modos 3 y 4 reciben el mismo plan de búferes, 2 B por píxel);
  `0x1290a0` (sólo modo 0); `0x128fa0`, `0x128fe4`, `0x12916e` (lado de la captura: con SaveCFAonTake
  y modo 3 usa `0x1228f0` para las ganancias y pasa el modo a `0x17d77c`); `0x1b0ab6` (salida de una
  pantalla de prueba, `0x1b08b4` exige `0x4c38c() == 3`).
- El tamaño del RAW no sale de las tablas: `0x76680` lee `0x3da828`, que la captura (`0xe3d52`)
  copia del modo. Con el parche el modo sigue siendo 3: el RAW sigue de 16 bits, 28.200.960 B.
- `0x12b6ec` exige `ctx+0x8c` (entrada que pide el IRP; `0x2afaa8` la calcula: formato 2 →
  ⌈ancho/8⌉·12·alto = 21.150.720) ≤ tamaño del RAW (28.200.960).
  El IRP lee dentro del búfer.
- Lo que el parche cambia respecto de la prueba 4 (modo 3 sin parche, dos RAW correctos) es sólo el
  formato del IRP, y esa configuración del IRP es la del modo 4, que corrió en la cámara sin cuelgue.
- Orden `SaveCFAonTake(1)` → setter de modo: el mismo de fábrica (`0x2d83c0` y `0x1f289c`) y el de
  P9. Son dos escrituras independientes (`0x1b0654` escribe un byte, `0x6e0b0` una palabra).
- Intérprete: el nombre de variable es una cadena validada carácter a carácter (`0x29bce8`: `_`,
  dígitos, letras) y guardada en una lista enlazada con memoria dinámica (`0x198f78`), sin tope de
  cantidad. Un operando se resuelve como cadena, `TRUE`/`FALSE` (palabra entera), entero (sólo
  dígitos, `0x199770`), flotante (dígitos y un punto, `0x19978c`) o variable (`0x1990d0`). Las letras
  `d`, `e` y `q` recorren las mismas instrucciones que `a`, `b`, `c`, `p` y `r`, ya probadas.
  `SaveCFAonTake` es `void` y va sin asignar (así corrió en P8 y P9); las llamadas a
  `Run_SpecifyFunc` (`int`) van todas asignadas.

**Cambios en el script**
- Antes: dos escrituras seguidas y después las dos relecturas. Ahora cada tabla hace escritura →
  relectura → registro → guardia antes de tocar la siguiente; el primer tramo es la secuencia exacta
  de EE0. Si la primera relectura no coincide, la segunda tabla queda intacta.
- Las guardias cierran en falso: el camino normal sólo usa `IF` verdadero con salto (lo probado en
  EE0); si un valor no coincide la línea siguiente es `END`, y si el intérprete fallara ahí la CPU se
  detiene sin haber puesto el modo 3. Un parche a medias es inocuo: las entradas del modo 3 sólo se
  usan con el modo 3, que se activa en la última línea útil.
- `sd_kit/fase1/Batch/BatchScripts_M3F2.txt` (una línea, CRLF) para copiarlo a la SD como
  `BatchScripts.txt`. `BatchScripts.txt` del kit sigue con P9 solo. El verificador no necesita cambios.

**Riesgo que queda**
- Que el cuelgue no dependa del rechazo del IRP. El script no lo empeora: sería el mismo cuelgue de
  la prueba 4 (batería y SD fuera, nada escrito).
- El IRP procesa palabras de 16 bits como si fueran 12 bits empaquetados: imagen de ruido de alta
  frecuencia. No se leyó qué hace la tarea JPEG si el archivo comprimido supera su búfer; un error
  ahí llevaría a la salida de error de la tarea (`0x15714c`), por un camino que no es el del modo 4.
- Pool 8: el RAW de 28,2 MB ocupa el pool entero desde la ranura 0 (el de modo 4 ocupaba 21,15 MB).
  No se encontró otro uso de la ranura 1 en un disparo aislado; un disparo con el anterior en
  proceso iría a la ranura 1 y pasaría el final de la SDRAM. Por eso: una foto, esperar, la siguiente.
- La rama falsa de `IF` (seguir en la línea siguiente) nunca corrió en la cámara.

Procedimiento y registro esperado: `sd_kit/PASOS.md`, paso 6.

## 2026-11-12 — EET colgó la cámara: llamada sin asignar a Run_SpecifyFunc (fe de erratas)

- **Qué pasó.** EET reescrito con las 11 escrituras en la forma `FOREIGN Run_SpecifyFunc(...)` (sin
  variable), por analogía con `FOREIGN SaveCFAonTake(1)`. La cámara se quedó en "RUN". `EET.LOG`
  (respaldo en `dump/raw9`):
  `460 FOREIGN Run_SpecifyFunc(3050116, 2, 0, 1785216, 4472856, 0, 0, 0, 0)` /
  `Error: function returns a FLOAT32 or integer.` El verificador había dado OK.
- **Lo que sí probó:** las 11 guardias pasaron (cada literal de banda tenía su valor de fábrica),
  once variables `a`…`k` en un mismo script, y un programa de 79 líneas cargado. Ninguna escritura
  corrió: el error sale al casar la firma, antes de despachar la llamada.
- **Causa, leída en el código.** `0x10710c` parte la sentencia en el `=`; sin `=` el nombre de
  variable queda vacío. `0x199b48` evalúa los argumentos y busca la función; al casar la firma,
  `0x199488` mira el byte de tipo de retorno de la entrada (`+0xc`, el primer byte de la firma en
  las tablas `0x486334` / `0x4871f4` / `0x487404`: 0 entero, 1 FLOAT32, 6 void):
  - sin variable y retorno 0 o 1 → `Error: function returns a FLOAT32 or integer.` (`0x1994aa`);
  - con variable y retorno 6 → `Error: function returns no value.` (`0x1994a0`).
  Los dos pasan por `0x198adc` y detienen la CPU. `Run_SpecifyFunc` es `int` (byte 0), sea cual sea
  la función a la que salta; `SaveCFAonTake` es `void` (byte 6), por eso sin asignar funciona.
- **Errata:** "`FOREIGN f(x)` está probado" valía sólo para funciones void. La regla es por firma y
  en los dos sentidos: las 80 funciones `int` del catálogo van siempre asignadas, las 161 `void`
  nunca. `tools/e2e_scripts.py` coteja los 241 tipos de `docs_script_manejadores.json` con las
  tablas de la RAM: coinciden todos.
- **Variables, leído en el código.** `set_add_variable` (`0x198f78`) busca el nombre en la lista
  enlazada del contexto (`+0x10`); si no está, crea un nodo (tres bloques del montículo, sin tope
  de cantidad); si está (`0x198ff0`) y el tamaño coincide, copia el valor nuevo sobre el mismo
  búfer. Reasignar es válido. El validador de nombres (`0x29bce8`) acepta `[A-Za-z0-9_]+`.
  El lote (`0x1078d8`) reinicia el montículo una vez (`0x19a010`: 3/4 del búfer para datos, 1/4
  para descriptores de 16 B) y, por cada script, crea el contexto (`0x198cd0`), lo ejecuta
  (`0x10776c`) y lo destruye con sus líneas y variables (`0x198d9c`): **las variables no pasan de
  un script al siguiente**, así que ningún script ejecutado en la cámara reasignó una variable.
  `BatchScripts.log` anota el máximo del montículo por lote (22.096 B con P8 + EE0).
- **Arreglo.** Hacen falta 33 resultados y hay 26 letras. Elegido: dos scripts, cada letra una sola
  vez por script, porque así todo lo que se ejecuta ya corrió en la cámara (crear variable, `IF`,
  `poke32` asignado, `LOG_PRINT`), mientras que reasignar sólo está leído.
  `EET.srt`: 11 guardias (`a`…`k`, idénticas byte a byte a las que pasaron), 11 escrituras
  asignadas (`l`…`v`) y relectura de la primera banda (`w`). `EETV.srt`: relee las 11 (`a`…`k`).
  Lista `fase3/Batch/BatchScripts_EET.txt` = P8, EET, EETV. Lo nuevo respecto de lo ejecutado: 23
  variables en un script (antes 11); por código la lista no tiene tope y EET ocupa menos líneas (59)
  que el programa que ya cargó (79).
  Esperado: `EET.LOG` una línea `VERIFY: 4472856`; `EETV.LOG` once líneas `VERIFY: 4472856`.
  Si `EET.LOG` trae otro número, es la lectura de la banda cuya guardia falló (nada escrito).
- **Verificador.** `check_scripts.py` exige el tipo de retorno de la firma en las tres tablas
  (sin asignar sólo void, asignada sólo int), variables de una letra minúscula y una sola
  asignación por variable en cada script. `tools/e2e_scripts.py` (fallas previstas en su cabecera,
  16 casos, artefacto `work/e2e_scripts/reporte.json`) corre la CLI sobre los kits, sobre el juego
  de la SD y sobre `dump/raw9/EET.srt`: debe marcar las 11 líneas sin asignar, empezando por la que
  la cámara nombró en su log.
- **Auditoría del resto de `sd_kit`** con la regla nueva: fase1 (P0, P6, P8, P9, M3F2), fase2
  (MEMRW, MEMRWT) y fase3 (EE0, ASHARP0, NRE0) pasan; ninguno tiene una llamada sin asignar a una
  función con valor ni una void asignada. Siguen sin correr en la cámara: `peek16`/`poke16` y el
  vaciado de caché (MEMRW, ASHARP0, NRE0), la palabra clave `SYSTEM` y `SYSTEM a = MemRead(...)`
  (MEMRWT), y un `END` ejecutado en mitad del programa (rama de guardia fallida de todos).

## 2026-11-12 — EET probado en la cámara

- `EET.LOG` = `VERIFY: 4472856`; `EETV.LOG` = once `VERIFY: 4472856`. Las 11 bandas de ISO quedaron con el
  realce a cero y la cámara no se colgó. Fotos y logs en `dump/raw10` (con `SHA256SUMS`).
- Medidas (misma escena, P8 = modo 0, Sharpness Normal; borde = |laplaciano| JPG / RAW en el centro):

  | foto | kit | ISO | flash | borde JPG/RAW | alta frec. JPG | RAW |
  |---|---|---|---|---|---|---|
  | 1985 | P8 solo | 64 | sí | 0,568 | 0,118 | 0,073 |
  | 1984 | P8 + EE0 | 64 | sí | 0,356 | 0,054 | 0,084 |
  | 1989 | P8 + EET | 64 | sí | 0,302 | 0,061 | 0,063 |
  | 1986 | P8 solo | 160 | no | 0,375 | 0,115 | 0,126 |
  | 1988 | P8 + EET | 135 | no | 0,331 | 0,064 | 0,092 |

- La 1988 salió en ISO 135 (banda ≤ 159, la misma de EE0), así que todavía falta una foto con ISO ≥ 160
  para ver en la imagen las bandas que sólo EET toca; el log ya prueba que se escribieron.

## 2026-11-12 — M3F2 probado en la cámara: 12 bits reales sin cuelgue

- `M3F2.LOG`, exactamente el esperado: `252054531`, `235211523`, `151391235`, `134548227`, `3`.
- Dos fotos seguidas (1990 y 1991, separadas 18 s) **sin cuelgue**: el modo 3 con el IRP en formato 2
  arregla el cuelgue de la segunda foto. Datos en `dump/raw11` (con `SHA256SUMS`).
- Cada foto deja sólo `101O####.RAW` de 28.200.960 B. **No hay JPG** (ni el de 224 B de antes). La
  vista previa en pantalla sale rojiza/verde: el IRP lee 16 bits como 12 empaquetados.
- RAW: u16 LE, máx 4095 (12 bits llenos), negro ≈ 103–118, sin filas vacías, estructura Bayer GBRG
  correcta (|d| mismo color 20–33 contra 136–203 entre vecinos). `m531raw.py` los convierte a DNG sin
  cambios. Vista revelada en `dump/raw11/vista_modo3.png`: imagen limpia, colores correctos.
- La cámara escribe también `MISC/AUTPRINT.MRK` y `MISC/SSECUPLD.XML` al apagar (normal, sin fotos listadas).
- Pendiente: cuántas fotos seguidas aguanta, el tiempo de guardado (~18 s entre disparos) y si con un
  disparo durante el guardado se pasa del pool 8 (no probar a propósito).

## 2026-11-12 — Pantalla, revisión y JPG correctos con RAW de 12 bits: análisis y scripts M3V, M4L, M2V

Objetivo: que la pantalla y la revisión tras el disparo muestren una imagen normal y que el RAW
conserve los 12 bits. Análisis estático sobre `firmware/stock/rec0_code_0x48000.bin`,
`dump/ram_snapshot.bin`, `work/code_full.s` y Ghidra. Sin cámara: nada de esta sección está probado
en ella todavía.

**Resumen**
- La pantalla con ruido tiene una causa propia, separada del JPG: el IRP de la vista en vivo toma su
  formato de la tabla `0x1286dc` según el modo de captura, y el sensor entrega la vista siempre en
  8 bits. Con un byte de esa tabla la vista queda como en el modo 0. Sirve en los modos 2, 3 y 4.
- El JPG rosado del modo 4 sale porque el IRP trata los formatos de 12 bits como datos lineales y
  el sensor, en ese modo, manda códigos de 10 bits comprimidos con la curva.
- El contenedor de 16 bits del modo 3 queda fuera del alcance del IRP: 2160 palabras por línea
  contra un tope de 2047. Ninguna vía sólo-RAM segura hace que el IRP lo lea, así que en modo 3 la
  revisión y el JPG siguen sin salir. Lo que sí se arregla en modo 3 es la vista en vivo (`M3V`).
- Los mismos 12 bits lineales caben en el contenedor empaquetado del modo 4, que el IRP sí lee.
  Para eso hay que apagar la curva en la captura: una instrucción de 16 bits en una función que
  sólo corre al disparar (`M4L`). Es la vía que cumple el objetivo completo.
- Reserva sin tocar código: el modo 2 (10 bits empaquetados), único modo extendido donde sensor e
  IRP están pensados para entenderse (`M2V`).

**Leído en el código**
1. *Tabla de linealización del IRP.* `0x1b172c` (`0x1b177a–0x1b1786`): con formato 2 o 6 pone
   `ctx+0x41 = 1` (tabla apagada). Con los demás la enciende si `[0x3df4f8+0x172] < 0x1900` y
   elige la tabla: formato 0 → `0x123704()` = `[0x4d1f04]` = `0x42c068`; resto → `0x123710()` =
   `[0x4d1f08]` = `0x42c870`. El cargador `0x2de294` copia 1024 entradas u16 a `0x0ff52000 + 4·i`
   y tres valores finales (4095). `0x42c068` sólo tiene datos en los índices múltiplos de 4 (código
   de 8 bits × 4) y sale 0–4092; `0x42c870` usa los 1024 y sale 0–4095. El IRP trabaja por dentro
   en 12 bits lineales con el negro restado, y eso es lo que espera recibir tal cual en los
   formatos 2 y 6.
2. *Formato de salida del sensor* (registro `0x0ff10080`). `0x17ac50`: bits 2–3 = contenedor
   (modo 0: 8 bits; 1 y 3: 16 bits; 2 y 4: empaquetado), bit 11 = 12 bits (modos 3 y 4).
   `0x17ae50`: bits 12–13 = desplazamiento, que `0xe3540` elige con la bandera de curva y el modo:

   | | modo 0 | modos 1–2 | modos 3–4 |
   |---|---|---|---|
   | sin curva (dato de 12 bits) | 2 | 1 | 0 |
   | con curva (dato de 10 bits) | 1 | 0 | 0 |

   La curva de captura (`0x1b0250`) son 1024 bytes de `0x427e14` multiplicados por 4: sale un código
   de 10 bits con tope `0x3fc` = 1020, el máximo medido en los RAW de modo 4. En modo 4 el
   desplazamiento es 0, así que el contenedor de 12 bits lleva el código de 10 bits sin escalar.
   El IRP lo toma por lineal: sombras iguales (la curva es 1:1 hasta ~312), claros a 0,25–0,6 de su
   valor antes del balance de blancos. Resultado: negros neutros y claros rosados, que es lo que
   muestran los JPG de `dump/raw3`.
3. *Etapas de la captura* (`0x147670`, una por bit de la palabra de banderas): bit 3 → `0xe1128`
   (cuatro u16, uno por canal: nivel de negro), bit 6 → `0xe1474` (tres ganancias), bit 7 →
   `0xe1580` (curva). La captura normal (`0x12273c`) arma las banderas en `0x122778–0x122782`:
   `[0x1228ec]` (= `0x3048`) OR `[0x511580]` (= `0x80`, lo escribe `0x1b0250` en cada disparo). La
   captura lineal (`0x1228f0`, banderas `0x3000`: sin negro, sin ganancias, sin curva) sólo entra
   con SaveCFAonTake = 1 y modo = 3 (`0x128f9c–0x128fa6`). `0x12273c` tiene dos llamadores, los dos
   de captura (`0x128fd2`, `0x129162`); `0x1b0250` sólo lo llama `0x12273c`.
4. *Vista en vivo.* La tarea `0x59aca` configura el IRP por cada cuadro: `0x5a97c` → `0x127fac` →
   `0x12853c`, con el tamaño de `0xdb0e8`, `ctx+0x41 = 1` fijo (`0x12877e`) y el formato sacado de
   la tabla `0x1286dc` con el modo global (`0x1286c6`). El arranque del flujo del sensor para la
   vista (`0xdb140`, tramo `0xdb2a8–0xdb2ea`) llama a `0x17ac50(0)`: 8 bits, sin mirar el modo.
   En modo 0 coinciden. En los modos 2, 3 y 4 el IRP lee esos 8 bits como 10 empaquetados, 16 o
   12 empaquetados. M3F2 dejó esa entrada en formato 2 (12 empaquetados).
5. *Tabla `0x1286dc`.* Bytes `03 0b 05 0e` + `08 00`; destino = `0x1286dc + 2·byte`. El formato 0
   es el byte `03` → `0x1286e2` = `st_s r14,[r13,0x2c]` (`0xa5cb`), con `r14 = 0` desde `0x128558`.
   La entrada del modo 4 vive en la palabra siguiente (`0x1286e0` = `0xa5cb0008`), que tiene el
   bit 31: se lee y escribe en 16 bits.
6. *Revisión tras el disparo.* `0xf0d14` reduce a 640×480 la salida YUV del IRP de la foto
   (`0xf117c`). No hay otra fuente: si el IRP de la foto procesa mal, la revisión sale mal.
7. *Por qué el modo 3 no tiene arreglo en el IRP.* `0x2afe48` programa el paso de línea en palabras
   de 32 bits en `0x0ff50410` (`0x2dcddc`, máscara de 12 bits). El validador (`0x2b028a`) rechaza
   más de `0x1ffc` B = 2047 palabras; 4320 px × 2 B son 2160. El paso explícito (`ctx+0x70`) existe
   pero `0x127ff4` lo pone a cero en cada foto. Saltar el validador pide cambiar una instrucción de
   una función que corre con cada cuadro de la vista, y nada en el código dice que el ASIC acepte
   líneas de 2160 palabras. Descartado.
8. *Modo 2.* Sensor: empaquetado de 10 bits, desplazamiento 0, o sea el mismo código de 10 bits
   del modo 4 sin relleno. RAW = 4320·3264·10/8 = 17.625.600 B (`0x76680`). IRP formato 1: pasa el
   validador (5400 B por línea, ancho múltiplo de 16), pide 17.625.600 B (`0x2afaa8`) y decodifica
   con `0x42c870`.

**Deducido (sin prueba en la cámara)**
- *M4L.* Con las banderas en `0x3048` (sin el bit 7) y modo 4: negro restado, ganancias, sin curva,
  desplazamiento 0, 12 bits empaquetados. Es el dominio que el IRP espera en formato 2. La
  captura sin curva está prevista en el firmware (fila "sin curva" de `0xe3540`, rama `0xe150c` de
  `0x147670`) y corrió en la cámara con el modo 3; el empaquetado de 12 bits es el de P9. Lo nuevo
  es juntarlos y mantener encendidas las etapas de negro y ganancias sin la curva detrás.
- *Tabla del modo 2.* `0x42c870` no es la inversa exacta de la curva de captura: valor lineal →
  código → `0x42c870` da 1024 → 856, 2048 → 1600, 3072 → 2258 (la tabla de 8 bits da 1064, 2116,
  3160). El JPG del modo 2 saldría con los medios y claros hasta un 29 % más oscuros que el del
  modo 0: imagen correcta de forma y color aproximado, con otro tono.
- *Cachés.* M4L cambia una instrucción. `poke16` escribe por la caché de datos; la CPU ejecuta lo
  que haya en la memoria (o en una caché de instrucciones, si existe) cuando esa línea se cargue.
  A `0x12273c` sólo la llaman funciones de captura: antes del primer disparo su línea no está
  cargada como código.
  Para empujar la línea escrita a la memoria, el script lee después ocho direcciones separadas
  64 KB (`0x132780`…`0x1a2780`): caen en el mismo conjunto de la caché de datos para cualquier
  tamaño de vía hasta 64 KB y desalojan la línea con asociatividad hasta 8. Sólo usa `peek32`.
  Si aun así corre la instrucción vieja, el resultado es exactamente P9 (RAW con máximo 1020 y JPG
  rosado): se nota en el RAW y no rompe nada.

**Scripts** (`sd_kit/fase1/Batch`, fuera de `BatchScripts.txt`; cada uno va solo en la SD)

| script | qué escribe en RAM | modo | RAW | pantalla | revisión y JPG |
|---|---|---|---|---|---|
| `M3V` | M3F2 con otro byte: `0x128344` → `0x09060c03`, `0x1286dc` → `0x03050b03` | 3 | 28.200.960 B, u16, 12 bits lineales con negro (igual que M3F2) | normal | sin JPG; revisión con ruido |
| `M4L` | `0x1286e0`: `0x0008` → `0x0003`; `0x122780`: `or_s r0,r0,r1` (`0x7825`) → `mov_s r0,r1` (`0x7028`) | 4 | 21.150.720 B, 12 bits empaquetados (lsb), lineales, negro restado, máximo 4095 | normal | normales |
| `M2V` | `0x1286dc` → `0x0e030b03` | 2 | 17.625.600 B, 10 bits empaquetados, comprimidos con la curva | normal | normales, con los medios más oscuros |

- `M3V` y `M2V` usan sólo `peek32`, `poke32`, el setter de modo y SaveCFAonTake: todo eso ya corrió.
  `M3V` difiere de M3F2 en un número (`50662147` en vez de `134548227`).
- `M4L` estrena `peek16` (`0x736e6`) y `poke16` (`0x13f09a`). Motivo: las dos palabras que toca
  tienen el bit 31 y el intérprete no admite literales negativos en un `IF`, así que con `peek32` no
  hay guardia posible. Las dos primitivas son colas de función con la misma forma que las probadas
  (`j_s.d [blink]` + `ldw_s r0,[r0,0]` / `stw_s r1,[r0,0]`; `peek32` es `j_s.d [blink]` +
  `ld_s r0,[r0,0]`), iguales en el firmware de fábrica y en la RAM. `Run_SpecifyFunc` salta con
  `jl_s [r13]`, que admite destinos pares no múltiplos de 4: las tablas de saltos del propio
  firmware lo hacen en cada foto (`j_s [r12]` a `0x12834a`). `ldw_s` extiende con ceros: los
  valores leídos (8, 30757) son positivos.
- `M4L` hace primero las dos guardias (sólo lecturas) y después escribe; si una guardia falla,
  termina sin escribir. Una escritura a medias es inocua: la entrada de tabla sólo se usa en modo 4
  y el modo se pone al final.
- Mientras `M4L` esté en RAM, una foto en modo 0 saldría mal (8 bits lineales contra un IRP que
  espera la curva). El script deja el modo 4; apagar la cámara lo deshace todo.
- `tools/e2e_scripts.py` coteja las guardias y los bytes cambiados de los tres scripts con el
  firmware de fábrica y comprueba que cada byte de tabla nuevo salta a la instrucción buscada
  (casos F10–F12, 26 casos en total).

**Conversión del RAW de M4L.** El perfil de 21.150.720 B de `m531raw.py` supone el código de 10 bits
y lo decodifica. Para un RAW lineal de M4L, pasar el formato a mano hasta ajustar el perfil con
fotos reales: `--packing p12_lsb --width 4320 --cfa GBRG --black 0 --white 4095`. Señal de que el
parche actuó: máximo del RAW por encima de 1020.

**Riesgo que queda**
- `M4L`: primera ejecución de `peek16`/`poke16`. Si la cámara se congela al encender, batería y SD
  fuera; nada queda escrito en la cámara.
- `M4L`: que corra la instrucción vieja por las cachés (resultado: P9), o que el modo 4 lineal
  tenga un efecto no leído (la combinación no existe de fábrica). Un cuelgue se resuelve igual.
- `M2V`: el modo 2 nunca corrió en esta cámara. Pasa el validador que tumbaba al modo 3; el resto
  del recorrido es el de los modos 0 y 4.
- Los tres: la regla de un disparo por vez sigue vigente (ranura 1 del pool 8).
- La identificación de la tarea `0x59aca` como vista en vivo es por su estructura (cuatro búferes
  en rotación, evento por cuadro, tamaño de `0xdb0e8`); `M3V` la confirma o la refuta en la cámara
  con el menor cambio posible.

**Siguientes opciones si M4L falla**
1. `M4L` más `dcache_flush_range` (`0x24e140`) sobre `0x122780`, si el RAW sale con máximo 1020.
2. `M2V` (10 bits, sin tocar código).
3. Modo 4 con la captura lineal del modo 3 (`0x128fa4`: `cmp_s r0,3` → `cmp_s r0,4`): RAW idéntico
   al del modo 3 pero empaquetado; el JPG saldría con velo, porque el IRP no resta el negro (~110).

Procedimiento y registros esperados: `sd_kit/PASOS.md`, paso 7.

## 2026-11-12 — M3V probado en la cámara (y corrección del usuario)

- `M3V.LOG` exacto: `252054531`, `235211523`, `151391235`, `50662147`, `3`. Dos fotos (1992, 1993) sin
  cuelgue; RAW u16 de 12 bits correctos (máx 3732/3332, sin filas vacías), sin JPG. `dump/raw12`.
- **Corrección del usuario:** la pantalla en vivo **siempre se vio bien**, en todos los kits. Lo que sale
  rojo/verde con ruido es sólo la **revisión** tras el disparo. La premisa de M3V ("vista en vivo con
  ruido") era falsa: devolver `0x1286dc[3]` a `03` no cambió nada visible y tampoco reabrió el cuelgue,
  así que el arreglo del cuelgue lo da sólo `0x128344[3]` (formato del IRP de la foto).
- Lo que sí falta es la revisión y el JPG: es el objetivo de M4L.

## 2026-11-12 — M4L probado: JPG correcto con RAW lineal de 12 bits; la revisión sale con ruido

- `M4L.LOG` exacto: `8`, `30757`, `3`, `28712`, `4`. Primera vez que `peek16`/`poke16` y un parche de
  instrucción (`0x122780` `or_s` → `mov_s`) corren en la cámara: funcionan, sin congelamiento.
- RAW 1994/1995 (21.150.720 B, p12_lsb): máximo 3832/4095, mediana ~400, millones de píxeles > 1020.
  **La curva quedó apagada: 12 bits lineales** (P9 se quedaba en 1020). `dump/raw13`.
- **El JPG de la cámara sale correcto** (4288×3216, imagen reconocible, algo cálido por el AWB
  por omisión del modo 4). Comparación en `dump/raw13/jpg_vs_raw_1994.png`.
- La **revisión** tras el disparo sale con ruido. Hipótesis: `0x1286dc` no es la vista en vivo (que
  siempre estuvo bien) sino el formato del IRP de la **revisión**; M4L puso la entrada del modo 4 en 3
  (8 bits) y la revisión lee 12 bits como 8. M4R = M4L sin ese cambio, para probarlo.
- Conversión de estos RAW: `m531raw.py dng ... --packing p12_lsb --width 4320 --cfa GBRG --black 0 --white 4095`
  (el perfil automático de 21.150.720 B todavía asume la curva del modo 4 de fábrica).

## 2026-11-12 — La revisión tras el disparo: qué la produce, qué quedó descartado, y M4R medido

> **Fe de erratas (misma fecha, sección "Revisión en modo ≠ 0: causa leída").** Los puntos 1 a 3 de
> "Leído en el código" describen el gancho de **detección de caras** de la foto (`0xf0d14`), no la
> revisión. La imagen que se ve tras el disparo la genera `0x148b78` directamente desde el RAW. Las
> mediciones de esta sección siguen siendo válidas.

Análisis estático (`work/code_full.s`, Ghidra, `dump/ram_snapshot.bin`) más las fotos de `dump/raw13`
y `dump/raw14`. **La causa del ruido de la revisión sigue sin identificar.** Por eso no existe `M4Q`:
un parche de código sin causa leída es una apuesta, y un error en un script detiene la CPU.

**Medido con archivos de la cámara**
- `dump/raw14` (M4R, fotos 1996–2001): los seis JPG son **correctos**, igual que los de M4L. Los seis RAW
  son lineales de 12 bits (máximos 4078–4095). El cambio de `0x1286e0` (8 → 3) que M4L hace y M4R omite
  **no influye en el JPG, ni en el RAW, ni en la revisión**.
- Cada JPG de M4L y M4R lleva dentro tres imágenes: miniatura EXIF de 160×120, imagen intermedia de
  360×480 y la foto de 3216×4288. **Las tres son correctas** (la intermedia correlaciona 0,999 con la
  foto reducida). Las imágenes pequeñas que salen del IRP están bien; el fallo de la revisión queda
  después del IRP.
- Todas las fotos de prueba de modo 4 (raw3, raw6, raw13, raw14) están en **vertical**: la cámara guardó
  el JPG girado (3216×4288). Ninguna prueba de revisión en modo 4 se hizo con la cámara horizontal.
- Los RAW guardados no llevan rastro del área de trabajo de la revisión (bytes `0x300000–0x396000` con la
  misma estadística que el resto): el archivo se escribe antes de que la revisión use esa memoria.

**Leído en el código**
1. *Gancho de revisión.* `0xf0d14` se registra con `0x129a98` en `0x3dbdb4` y lo llama `0x129ba0` desde
   la etapa de procesado (`0x1c043a` para imágenes de hasta 4095 px de ancho, `0x1c065e` para las más
   anchas, que es el caso de la foto de 4288). Recibe la cabecera de la captura (`ctx`) y una
   estructura de 0x34 B con el búfer de la imagen pequeña.
2. *Origen de la imagen de revisión.* Antes de llamar al gancho, la etapa reduce la salida YUV del IRP con
   `0x12a52c` hacia `param+0x60` (tamaño `param+0x5c/0x5e` = `ctx+0x17e/0x180`). El búfer lo coloca
   `0x1becd4` dentro del búfer de salida, detrás de las franjas YUV y del búfer de `param+0x44`. En la
   foto ancha esa reducción sale de una primera pasada del IRP (`0x1bc528` tipo 2: cuatro cuadrantes con
   `0x2b0d8c`/`0x2b1098`) y la foto grande de una segunda pasada (tipo 1). Las dos usan la misma
   estructura del IRP, con el mismo formato de entrada (`0x128344`).
3. *Presentación.* `0xf0e7c` usa **el propio búfer del RAW** (`ctx+4`) como área de trabajo: `raw+0`
   (3 MB, destino de `0xdc9d4`), `raw+0x300000` (lienzo de 640×480) y `raw+0x34b000` (copia de la imagen
   pequeña). `0xf117c` centra la imagen en el lienzo según `ctx+0x2c` (1–2 o 3–4, por orientación) y
   llama a `0xdc9d4`. En el caso habitual el dibujo lo hace después `0xf0ad8`, como trabajo diferido.
4. *Lectores del modo de captura* (`0x6e0d0`, diez llamadas): las dos tablas de formato (`0x128330`,
   `0x1286c6`), la captura (`0x128fa0`, `0x128fe4`, `0x1290a0`, `0x12916e`), el guardado (`0x1b0ab6`) y
   **la disposición de la cabecera** (`0x12b4a0`, `0x12b536`, `0x12b628`): `ctx+8 = raw + N·(ancho·alto
   redondeado a 1 KB)`, con N = 1 en modo 0 y N = 2 en los demás.
5. *Mapa de memoria* (tabla de pools en `0x3e7c40`, leída del volcado de RAM): el pool 8 (RAW) ocupa
   `0x0213e000–0x03c23000` = 28.200.960 B exactos, y el RAW empieza en `+0x5800`. En modo ≠ 0,
   `ctx+8` = `0x03c28800`: **cae fuera del pool 8**, sobre memoria de otros pools (`0x03c23000` en
   adelante). En modo 0 cae dentro (`raw + 14,1 MB`). Los búferes propios de la revisión (pool `0x45`,
   640×480, en `0x005afc00`; pool `0x44`, 640×480×1,5, en `0x020bd000`) quedan fuera del RAW en todos los modos.
6. *Guardado del RAW.* `0x12701c` lo escribe con `0x1b066c` (sufijo `O`, tamaño de `0x76680`) al volver
   de la captura; `0x1b0754`, que sólo corre con SaveCFAonTake, cambia el bit bajo de 32 bytes del RAW
   (marca) y nada más. `0x1289a8` (cuatro planos de depuración) sólo corre en modo 0.

**Descartado**
- Que la revisión dependa de `0x1286dc`/`0x1286e0`: M4L y M4R dan la misma revisión y los mismos JPG.
- Que la revisión se decodifique del JPG guardado o de su miniatura: sale de la reducción YUV del punto 2.
- Que la revisión lea el RAW como si fuera YUV por un formato propio: no hay segunda tabla de formato en
  ese camino, y la imagen pequeña que produce el IRP es correcta (está dentro del JPG).
- Que el archivo RAW se dañe por la revisión.

**Inferido, sin prueba**
- El candidato con más apoyo es el punto 5: una imagen de 640×480 que el código coloca en `ctx+8` queda,
  en modo ≠ 0, fuera del pool del RAW y sobre memoria ajena. `0x12754e` usa `ctx+8` como búfer de imagen
  de 640×480. Falta leer si el camino normal de la revisión (`0xf0ad8` → `0xdc9d4` → `0x186694`) pasa por
  `ctx+8`; en `0xf0d14` y `0xf0e7c` sólo aparece `ctx+4`.
- Segundo candidato: la rama de orientación de `0xf117c`. En modo 0 el usuario vio revisiones buenas, pero
  no consta que fueran en vertical.
- Un arreglo por `ctx+8` pediría cambiar la cuenta de `0x12b536` (N = 2 → 1,5), o sea instrucciones de una
  función que corre en cada disparo, y además comprobar quién más usa ese puntero. Sin esa lectura, no se escribe.

**Pruebas que separan los candidatos** (ninguna toca código nuevo en la cámara; pasos en `sd_kit/PASOS.md`, 7d)
1. Con M4L (ya en la SD): una foto con la cámara **horizontal** y otra en vertical. Si la horizontal se
   revisa bien, el fallo está en la rama de orientación y no en el modo.
2. `M4N` = M4R sin SaveCFAonTake (modo 4 lineal sin archivo RAW). Si la revisión sale bien, depende del
   guardado del RAW; si sale igual, depende sólo del modo (apoya el punto 5).
3. P8 (modo 0 con RAW) en vertical: confirma que el modo 0 revisa bien en la misma orientación.

**Conversor.** `tools/m531raw.py` separa solo los dos archivos de 21.150.720 B: máximo > 1020 → lineal de
12 bits (negro 0, blanco 4095, sin curva); máximo ≤ 1020 → curva de fábrica (P9), como antes. Una toma de
M4L sin nada por encima de un cuarto de escala se tomaría por comprimida: para ésa, los parámetros a mano.
`tools/e2e_raw.py` lo comprueba con 1994, 1995, 1996 y 2001 (mosaico idéntico al archivo, correlación 0,993
y pendiente 1,13–1,17 contra el JPG de la cámara) y con 1981 y 1982 de P9. `tools/e2e_scripts.py`: 32 casos
(entran M4R y M4N).

## 2026-11-12 — Revisión con ruido en modo 4: orientación y guardado del RAW descartados

- **M4L horizontal y vertical** (`dump/raw15`, 2002–2005; log `8, 30757, 3, 28712, 4`): la revisión sale
  igual de roja/verde y con ruido en las dos posiciones. La orientación no es la causa.
- **M4N** = M4R sin SaveCFAonTake (`dump/raw16`, 2006–2009; log `30757, 28712, 4`): sólo JPG, sin RAW,
  JPG correctos. La revisión sale **igual de mal**, pero bastante más rápido. Guardar el RAW tampoco es la causa.
- Conclusión: la revisión se rompe con cualquier modo de captura ≠ 0 (P9, M3F2/M3V, M4L/M4R/M4N), aunque
  la salida del IRP (JPG y sus miniaturas) esté bien. En modo 0 (P8) está bien. El candidato
  `ctx+8 = raw + N·ancho·alto` quedó descartado después para la foto normal (ver la sección "el candidato
  `ctx+8` queda descartado"). Sin M4Q todavía.
- Aparte: con cualquier kit de scripts **todas** las fotos salen en vertical (3216×4288, etiqueta 1),
  también las tomadas en horizontal, en el JPG y en la revisión; las de fábrica salen horizontales
  (499 de 4288×3216 y 155 de 3216×4288 en `dump/sd_original`). En análisis aparte.

## 2026-11-12 — Fotos horizontales guardadas en vertical: lo decide el sensor de orientación; script ORI

Análisis estático (`firmware/stock/rec0_code_0x48000.bin`, `work/code_full.s`, `dump/ram_snapshot.bin`)
más los archivos de `dump/`. Sin cámara: ORI no corrió todavía.

**Resumen**
- El giro lo decide, en cada disparo, la lectura del sensor de orientación. Ningún script del kit, ni
  SaveCFAonTake, ni el cambio de modo, ni el arranque por `B:\Batch` escriben nada de esa cadena: los
  cuatro candidatos de software quedan descartados por código.
- Lo que sigue abierto es por qué el sensor contesta "vertical" en las tomas de prueba. Hay dos
  explicaciones y los archivos disponibles no las separan (ver "Inferido").
- `ORI` deja la función lectora del firmware devolviendo siempre 0 ("cámara horizontal"), que es el valor
  que devuelve en cada foto horizontal desde que la cámara salió de fábrica. Efecto: JPG y revisión sin
  girar en todos los kits. Costo: las fotos tomadas en vertical tampoco se giran (quedan como el RAW).

**Medido con archivos**
- Los 35 JPG tomados con scripts (1970–2009) miden 3216×4288 con etiqueta de orientación 1.
- En los 20 pares con RAW (1970, 1971, 1983–1986, 1988, 1989, 1994–2005), el JPG es el RAW girado 90°
  en sentido antihorario (`np.rot90(raw, 1)`): correlación 0,89–0,97; con el giro contrario, −0,27 a 0,41.
  El giro es **el mismo en todas**, con la cámara horizontal o vertical.
- Por el contenido: en 2003, 2004, 2005 y 2007 la escena queda derecha (cámara vertical, giro correcto).
  En 30 la escena queda acostada (cámara horizontal, giro de más). La 2009 no tiene referencia clara.
- Las 30 acostadas son tomas en picado hacia el escritorio (teclado, macropad vistos desde arriba). Las
  cuatro derechas se tomaron con la cámara casi nivelada, mirando al frente.
- M4N (2006–2009) no llama a SaveCFAonTake y gira igual. P8 solo (1970, 1971, 1985, 1986) deja el modo 0 y
  gira igual. P6/P9 (1972–1982) también.
- Fábrica (`dump/sd_original`): la última foto horizontal es la 1960 (2024-06-29). Las dos siguientes,
  1961 y 1963 (2025-11-18), miden 3216×4288 y muestran la escena derecha: se tomaron en vertical.
  **No existe ninguna foto horizontal y nivelada posterior a junio de 2024**, con scripts o sin ellos.
  Las 1964–1967 (pruebas 1–3, con los scripts cargados y sin ejecutar) no quedaron guardadas en `dump/`.
- Corrección a la sección "La revisión tras el disparo": donde dice que todas las fotos de prueba de modo 4
  "están en vertical", las fotos se tomaron en horizontal y la cámara las giró. Y en la prueba de M4L
  horizontal/vertical (`dump/raw15`) las dos posiciones pasaron por la misma rama de giro: la rama sin
  giro de la revisión en modo 4 sigue sin probarse. Con ORI cargado se puede probar.

**Leído en el código**
1. *Variable de la decisión.* Byte `ctx+0x2c` de la cabecera de la captura. Lo escribe `0x127a2a` dentro
   de `0x127978` (llamada desde la captura en `0x1270c2`); la segunda variante de captura hace lo mismo
   en `0x127cc8`. Valores: 0 = sin giro; 1 y 2 = giro de píxeles (ajuste "Sensor de orientación" en
   Activado); 3 y 4 = con el ajuste en otro valor ("En transferencia": el texto de ayuda en `0x4a2680`
   dice que la foto se muestra sin girar y se gira al transferir).
2. *Quién lo usa.* `0x128022` (montaje del IRP de la foto): con 1 o 2 intercambia ancho y alto de la
   salida (`ctx+0x64`/`ctx+0x66`); con cualquier otro valor los deja como están. `0xf0b70` y `0xf0e0c`
   pasan el mismo byte a `0xf117c` (revisión). `0x12951c` lo copia a la estructura del archivo.
3. *Lector del sensor* `0xf02a0`. Base `0x3da998` (literal en `0xf032c`). Devuelve 0 sin tocar el
   hardware si `[0x3da998] == 0` (sensor sin alimentar) o si `[0x3da999] == 0` (sensor deshabilitado):
   `0xf02b6–0xf02c5`, las dos ramas van a `0xf036a` = `mov_s r0,0`. Si no, espera hasta 5 ms desde el
   encendido y lee el puerto `0x0ff04034`: bit 7 → 1; si no, bit 5 → 2; ninguno → 0.
   `0xf0228` enciende el sensor (bit 13 de `0x0ff04000`) y pone `[0x3da998] = 1`; `0xf0270` lo apaga y
   pone 0. `[0x3da999]` sólo lo escribe `0xf0378`, que no tiene ninguna llamada ni puntero en el
   firmware: es una constante de la sección de datos. En la RAM volcada los dos bytes valen 1.
4. *Ajuste del menú.* Byte `0x3d9a81` (0 Activado, 2 Desactivado), getter `0x75ad0`, setter `0x75adc`.
   Lo escriben la carga de parámetros (`0x4ce6c`, `0x66c42`), los menús (`0x1e4ad4`, `0x1e4e5a`,
   `0x2394ec`, `0x2c0146`) y el comando de script `OrientationSensor` (`0x2d756c`), que ningún kit usa.
5. *Secuencia en la captura* (`0x126f20`): si el ajuste ≠ 2, `0xf0228` (`0x126f60`); exposición;
   `0x127978` lee el sensor (`0x12799c`); si el ajuste ≠ 2, `0xf0270` (`0x1270d4`). El archivo RAW se
   escribe después (`0x1271e8`), con el sensor ya apagado: SaveCFAonTake no cambia ni el momento ni el
   resultado de la lectura.
6. *Qué escriben los kits.* `SaveCFAonTake` (`0x1b0654`): sólo el byte `0x3df0e4`. Cambio de modo
   (`0x6e0b0`): sólo la palabra `0x3d97a8`. EE0/EET: 11 literales de código en `0x1b3d80–0x1b4b68`.
   M4L/M4R/M4N: `0x1286e0` y `0x122780`. Las demás llamadas son lecturas. Las direcciones `0x3d9a81`,
   `0x3da998` y `0x3da999` sólo aparecen como literal en las funciones de los puntos 3 y 4.

**Inferido, sin prueba**
- El sensor contesta 1 o 2 (siempre el mismo valor) en las tomas horizontales de prueba. Explicaciones:
  a) *Picado.* Las 30 tomas giradas de más apuntan hacia abajo. Un sensor de inclinación de dos salidas
     pierde la referencia cuando el objetivo mira al suelo y puede quedarse en la posición "vertical".
     Las fotos de fábrica horizontales son, en su mayoría, tomas niveladas.
  b) *Sensor atascado* en una posición desde algún momento posterior a junio de 2024 (la cámara pasó
     más de un año guardada). Predice que una toma horizontal nivelada también sale girada.
- Prueba que las separa, sin scripts (SD sin `Batch/`, o con el kit actual: da lo mismo según el código):
  una foto horizontal nivelada mirando al frente y otra horizontal en picado al escritorio. Nivelada
  4288×3216 y picada 3216×4288 → (a). Las dos 3216×4288 → (b).
- El valor inicial de `[0x3da998]` es 1: en la RAM volcada vale 1 y el sello de tiempo que `0xf0228`
  guarda al lado (`0x3da99c–0x3da9a3`) está en cero, o sea que nadie lo llamó desde el arranque.

**Script `ORI`** (`sd_kit/fase3/Batch/ORI.srt`, copia idéntica en `fase1/Batch`)
- Lee con `peek16` la palabra `0x3da998` (byte bajo = alimentado, byte alto = habilitado) y la anota.
  Si vale 257 (`0x0101`) escribe 1 con `poke16`; si vale 256 (`0x0100`) escribe 0. En los dos casos el
  byte bajo queda como estaba y el alto pasa a 0. Relee y anota. Con cualquier otro valor termina sin
  escribir. Es el único byte que cambia; se pierde al apagar.
- Por qué es seguro, por código: (1) el byte alto sólo lo lee `0xf02a0` y nadie lo escribe; (2) con ese
  byte en 0 la función sale por la misma rama que usa cuando el sensor está apagado y devuelve 0, el
  mismo valor que devuelve en toda foto horizontal; (3) sus llamadores (`0x51524`, `0x12799c`,
  `0x127cc8`, `0x13e2f4`, `0x1e05f2`, `0x1e1aee`, más la pantalla de prueba `0x1f5cf0`) ya manejan el 0;
  (4) el encendido y apagado del sensor siguen igual; (5) es un dato, no código: no intervienen las
  cachés de instrucciones; (6) `peek16`/`poke16` ya corrieron en la cámara con M4L.
- `IF` falso: la rama "condición falsa sin ELSE" de `0x107578` (`0x10763c–0x107650`) libera los búferes
  y sigue en la línea siguiente. Es la rama de la que depende el corte por guardia de todos los scripts
  y **no corrió todavía en la cámara** (todas las guardias dieron cierto). ORI la usa si la palabra vale 256.
- Composición: no comparte direcciones con ningún otro script; va al final de la lista. Listas de prueba:
  `fase3/Batch/BatchScripts_ORI.txt` (P8, EET, EETV, ORI) y `fase1/Batch/BatchScripts_ORIM4L.txt` (M4L, ORI).
- `tools/e2e_scripts.py`, 41 casos (F13–F15): la dirección de ORI contra el literal de `0xf032c`, la
  compuerta contra las instrucciones de fábrica, y ORI ejecutado en un intérprete mínimo con ocho estados
  iniciales (dos escriben, seis no), con dos scripts mutados de control.

**Riesgo que queda**
- Las fotos verticales dejan de girarse en la cámara (JPG y revisión en la orientación del sensor, igual
  que el RAW). El ajuste del menú no cambia; al apagar vuelve el comportamiento de fábrica.
- Entre la lectura y la escritura de ORI pasan unos milisegundos; si en ese hueco otra tarea cambiara el
  byte bajo, ORI lo devolvería al valor leído. Consecuencia máxima: el sensor queda alimentado hasta el
  siguiente disparo. Durante "Script / Run…" no hay captura en curso.
- Si la palabra no vale 257 ni 256 al arrancar, ORI no hace nada y el `.LOG` trae un solo número.
- Alternativa sin script: Menu → Setup → Sensor de orientación → Desactivado. Persiste en la
  cámara. Por código no garantiza el 0: con el ajuste en 2 la captura no enciende el sensor, pero
  `0xf02a0` lee igual mientras `[0x3da998]` siga en 1, y un 1 o 2 con el ajuste ≠ 0 da 3 o 4.

Procedimiento: `sd_kit/PASOS.md`, paso 8.

## 2026-11-12 — Revisión con ruido en modo ≠ 0: el candidato `ctx+8` queda descartado; sin M4Q

> **Fe de erratas (misma fecha, sección siguiente).** Tres cosas de esta sección quedan corregidas:
> 1. *Los pools están mal identificados.* `0x4b980(n)` traduce un número lógico al identificador del
>    pool; esta sección tomó el argumento por el identificador. Lo correcto: `0x4b980(0x22)` → pool
>    `0x40` (`0x0212d800`, tres cabeceras de `0x5800` B); `0x4b980(0x25)` → pool `0x44` (`0x020bd000`,
>    640×480×1,5: es `ctx+8`, **la imagen de revisión**); `0x4b980(0x26)` → pool `0x45` (`0x005afc00`,
>    640×480); `0x4b980(0x13)` → pool `0x33` (`0x03d98400`). La conclusión del punto 1 se mantiene:
>    `ctx+8` no depende del modo.
> 2. *`0xf0d14`, `0xf0e7c`, `0xf117c`, `0xf0ad8`, `0xdc7ec` y `0xdc9d4` son la detección y el
>    reconocimiento de caras de la foto* (marcas de tiempo `Still FD Start/End`, `Still FR Start/End`;
>    `0xea7a0` escribe las etiquetas de caras), y sólo corren si `0x1bb744() ≠ 0`. Que esos búferes no
>    dependan del modo es cierto y no dice nada de la revisión.
> 3. *La hipótesis del RAW que pisa otros pools queda descartada.* La revisión no usa ninguno de esos
>    pools; lee el RAW con el formato equivocado. `0x1b0ab6` (lector del modo) es la salida de la
>    pantalla de revisión, no el guardado.

Análisis estático (`work/code_full.s`, Ghidra con `-noanalysis`, `dump/ram_snapshot.bin`). Sin cámara.
**La causa sigue sin identificar y no hay `M4Q`**: ninguna escritura de RAM se puede justificar con lo
leído. Lo nuevo es que el camino de una foto normal no pasa por el puntero que era el candidato principal.

**Leído en el código**
1. *Disparo normal.* Los manejadores del disparador (`0x1e4ba0`, `0x1e5018`) llaman a `0x12923c` con
   `r2 = 0`, que llega a `0x126f20` como `r16 = 0`. Con `r16 = 0` hay dos caminos y ninguno usa el modo
   para colocar `ctx+8`:
   - normal (`0x126fdc` → `0x12b3c4` con `r0 = 0`, rama `0x12b518–0x12b546`): la cabecera `ctx` sale de
     una de las tres ranuras del pool `0x22` (`0x03c23000`, `0x22400` B); `ctx+4` (RAW) = `[P+8] + r19`,
     con `P` sacado de la cola de búferes `[0x3dbdcc] = 0x3ffa30` por `0x12af1c`; **`ctx+8` = base del
     pool `0x25`** (`0x03b6c000`, `0xb7000` B). La llamada a `0x6e0d0` de `0x12b536` descarta el resultado.
   - ráfaga (`0x126f68`, sólo si `r15 = 1` y `0xf0944() ≠ 0`): `ctx+8 = búfer + ancho·alto` (N = 1 fijo).
   La cuenta `ctx+8 = raw + N·ancho·alto` con N = 2 en modo ≠ 0 (`0x12b4a0`, `0x12b628`) sólo corre cuando
   se pasa un búfer: lanzadores `0x7d402`, `0x7d928`, `0x7dc1a` (zona de los envíos por USB) y la cabecera
   siguiente de ráfaga (`0x127220` → `0x12b584`, sólo con el byte `[0x3dbd80] = 1`, que pone la rama de
   ráfaga). **En una foto normal `ctx+8` no depende del modo.**
2. *Buffers de la revisión* (`0xf0d14` → `0xf0e7c`, `0xf117c`, diferido `0xf0ad8`):
   - imagen pequeña de origen: `struct+4` = `param+0x60` del procesado, dentro del búfer de salida del
     trabajo de procesado; ese búfer es el pool `0x0e` (`0x005fac00–0x020bd000`), puesto por `0x12b6ec`
     (`job+0x18/0x1c`, `[img+0x74]`).
   - `0xdc7ec(2, 1, origen, S+8, …)` la reduce al pool `0x26` (`0x03ce4400`, `0x20000` B); `0xf0e7c`
     rechaza la revisión si `S+0x2a · S+0x2c` no cabe ahí. `S` = `0x3da9ac`.
   - con `[0x3d95ff] ≠ 5` (`0x66f30`): `S+0x10 = raw`, `S+0x14 = raw+0x300000`, `S+0x24 = 2`, copia de la
     imagen pequeña a `raw+0x34b000` (`0x48120` es `memmove`) y dibujo diferido por `0xf0ad8`
     (puesto en cola con `0x5c3b8`). En la rama con giro (`ctx+0x2c` = 1 o 2) `0xf117c` copia filas desde
     `S+0xc` (pool `0x26`) al lienzo `raw+0x300000` y llama a `0xdc9d4` con área de trabajo `raw` (≥ 3 MB).
   - `0xf0ad8` usa además el pool `0x13` (`0x024b8400`) para los recuadros de caras.
   Todas estas direcciones salen de `ctx+4` o de pools fijos. Ninguna lee `ctx+8` ni el modo.
3. *Segundo portador del modo.* `0xe3cd4` (lectura del sensor) guarda el modo del disparo en
   `[0x3da804+0x24]` = `0x3da828`. Su único lector (`0xe43f0`) es `0x76680`, el tamaño del RAW
   (8, 12 o 16 bits por píxel). Lo usan el guardado del RAW (`0x1271d4`, `0x1271fc`), `job+0xc` del
   procesado (`0x12b7c6`, con tope `[img+140]`) y los lanzadores de USB.
4. *Vista previa por hardware durante la lectura* (`0xe3ac0`, bit 10 de `0x0ff10080`, registro
   `0x0ff10088`): sólo se arma si `[0x3dbd7c] ≠ 0`. Su único escritor (`0x127700`) no tiene llamadas ni
   punteros en el firmware y en la RAM volcada vale 0. No interviene.

**Descartado (por código)**
- Que `ctx+8` (N = 2) coloque algo de la revisión fuera del pool 8 en una foto normal: ese puntero, en
  el disparo normal, apunta al pool `0x25` en todos los modos.
- Que la revisión lea un búfer cuya dirección dependa del modo: la lista del punto 2 es completa para
  `0xf0d14`, `0xf0e7c`, `0xf117c` y `0xf0ad8`.

**Inferido, sin prueba**
- Lo único del camino que cambia con el modo y no se ve en el JPG es la extensión del RAW: 14,1 MB en
  modo 0, 21,15 MB en modo 4 y 28,2 MB en modo 3. Si el RAW empieza en la base del pool 8, en modo 4
  ocupa hasta `0x0358a400` y pisa pools superpuestos que el modo 0 deja libres (`0x0a`, `0x21`, `0x2d`,
  `0x46`, `0x47`, `0x19`, `0x24`, entre otros). Una revisión que reutilice algo preparado antes del
  disparo en esa zona saldría con ruido en todos los modos ≠ 0. Falta leer qué hay en `[P+8]` (la cola
  `0x3ffa30` está vacía en el volcado) y qué usa `0x186694` además del área de trabajo. Es una hipótesis
  de trabajo: no hay una lectura concreta que la respalde.
- La rama sin giro de `0xf117c` (`default`) toma otro formato de salida (`0xdc9c8`) y otro origen. Sigue
  sin probarse en modo 4 (ver la sección de ORI).

**Por qué no hay M4Q.** No se sabe qué memoria se corrompe ni en qué momento. Cualquier parche (cambiar
N, mover el área de trabajo, forzar `[0x3d95ff]`) toca funciones que corren en cada disparo o variables
que leen otras partes del firmware, y no se puede demostrar que dejen intactos el RAW, el JPG y los
demás pools.

**Siguiente prueba en la cámara** (`sd_kit/PASOS.md`, 7e): primero 8c (M4L + ORI, ya preparada); después
M2V si 8c sale con ruido.

## 2026-11-12 — Revisión en modo ≠ 0: causa leída en el código (formato del RAW fijo en 0) y script M4Q

Análisis estático (`work/code_full.s`, Ghidra `-noanalysis`, `dump/ram_snapshot.bin`,
`firmware/stock`). Sin cámara. (M4Q corrió después: ver la sección siguiente.)

**Causa (leída en el código)**
1. *Quién dibuja la revisión.* El disparo termina con el evento `0x7ce2` (`0x12923c` → `0x5ef00`). La
   tabla del estado `CaptureImage` (`0x460ffc`) lo lleva a `0x1e4e8c`, que deja programada
   `0x1e5190` (`0x1e55a0` → `0x545c4`). En la foto normal ésta llama a `0x1e53ac`, que llama, en
   este orden, a `0x127754(ctx)` (estadística de balance sobre el RAW), a `0x148b78(ctx, 0xff)`
   (genera la imagen de revisión en `ctx+8`; en ráfaga `0x1e5190` la llama con 1) y a
   `0x164ed4(0, 0, ctx+8, pantalla, ctx+0x60, ctx+0x62, …)`, que la copia al búfer de pantalla
   (`0xd54f0`, pool 7). `0x1b0b40` caso 6 repite esa copia. Si `0x148b78` devuelve error, la pantalla
   se rellena con ceros.
2. *De dónde sale la imagen.* `0x148b78` llama a `0x25239c(formato, RAW, ancho, alto, destino, 640,
   480, 1, …)`: una pasada del IRP con entrada desde memoria que lee **el búfer del RAW** (`ctx+4`) y
   escribe 640×480 (480×360 si la foto va girada). El archivo RAW y el JPG no intervienen.
3. *El formato está fijo.* `0x25239c` es general: su primer argumento es el formato del RAW con la misma
   numeración que el modo de captura (0 = 8 bits, 2 = 10 bits empaquetados, 4 = 12 bits empaquetados,
   1/3/5 = 16 bits). Con él calcula bytes por línea (`0xf65f4` → `0x186848`: código 2 ×1, 7 ×10/8,
   9 ×12/8, 3/8/4 ×2) y programa el formato de entrada (`0x17aaf4`, registro `0x0ff10200`). Su única
   llamada en todo el firmware está en `0x148ee8` y pasa `r16`, que vale 0 desde `0x148b94`
   (`mov_s r16,r15` con `r15 = 0`). **La revisión lee siempre el RAW como 8 bits.** En modo 4 el búfer
   lleva 12 bits empaquetados (1,5 B por píxel): cada tres bytes hay dos píxeles y el IRP toma tres, la
   fase del mosaico cambia de byte en byte y sale ruido de color. Lo mismo en modo 2 y en modo 3.
4. *La numeración coincide con el modo de captura.* En el arranque de la vista en vivo (`0xdbb94`) el
   mismo registro `r17` va a `0x17ace8` (formato del DMA del sensor) y a `0x17aaf4`; la captura
   (`0xe3cd4`) llama a `0x17ace8` con el modo de captura (`struct+4` = `0x6e0d0()`).

Esto explica todas las observaciones: ruido con cualquier modo ≠ 0 y bien en modo 0; vista en vivo
bien (otro camino); JPG y miniaturas bien (el procesado usa `0x128344`); igual sin SaveCFAonTake (M4N),
porque el sensor llena el búfer del RAW en todos los casos y la revisión lee el búfer, no el archivo;
igual en horizontal y en vertical (la orientación sólo cambia el destino); más rápida en M4N porque el
evento `0x7ce2` llega al volver de la captura, después de escribir el RAW.

**Hallazgo aparte, sin tocar.** La estadística de balance por foto (`0x127754` → `0x86d14` →
`0x147b14(0, RAW, …)`) tiene el mismo defecto: formato 0 fijo. Es la razón de código de que el AWB no
se calcule en modo 4 (sección "Balance de blancos por foto en modo 4"). No se corrige aquí: su ventana
se coloca con desplazamientos en bytes de 8 bits (`fila·ancho`), que en 12 bits caen a mitad de línea,
y su resultado entra en el JPG.

**M4Q** (`sd_kit/fase1/Batch/M4Q.srt`, lista `BatchScripts_M4LQ.txt` = M4L, M4Q). Dos palabras de 16
bits en RAM, contiguas, en la preparación de la llamada:

| Dirección | De fábrica | M4Q | Efecto |
|---|---|---|---|
| `0x148ed6` | `0xc044` `st_s r0,[sp,0x10]` | `0xc744` `st_s r15,[sp,0x10]` | recorte nulo: cuadro completo |
| `0x148ed8` | `0x700a` `mov_s r0,r16` | `0xd804` `mov_s r0,0x4` | formato 4: 12 bits empaquetados |

Guardias: modo de captura = 4 (`0x3d97a8`), las dos palabras iguales a las de fábrica antes de la
primera escritura, relectura y registro de cada una, y ocho lecturas a 64 KB para desalojar la línea
de la caché de datos. Orden: primero el recorte (inocuo con formato 0), después el formato.

*Por qué hace falta el recorte nulo.* Con el recorte de fábrica (x 4, y 24, 4300×3216) la rama del
recorte de `0x25239c` coloca el origen en bytes de 8 bits y pasa el ancho 4300 a `0xf65f4`. En 12 bits
son 6450 B, que no es múltiplo de 4: en ráfaga (escala 3) `0xf65f4` devuelve error y `0x25239c` sale
sin deshacer `0xe2fb4(1)` / `0xe2f5c(1)`. Con el puntero nulo y zoom digital 100 la misma rama toma
origen 0 y el cuadro entero (4320×3264), y todos los tamaños son múltiplos de 4.

**Demostrado por código**
- *RAW.* `0x1b066c` lo escribe dentro de la captura, antes del evento `0x7ce2`. `0x148b78` sólo lee
  ese búfer. Con M4Q la lectura abarca 816 × 25.920 B (escala 2, foto normal) o 1088 × 19.440 B
  (escala 3, ráfaga) = 21.150.720 B: exactamente el RAW del modo 4, dentro del pool 8.
- *Otros pools.* El destino y su tamaño no cambian: `0xf58e4` / `0xf5b64` reciben los mismos 640×480 o
  480×360, y `0xf1764` programa el escalador con esas dimensiones de salida.
- *Sin camino de error.* Origen `0x0213e000` (múltiplo de 4); escala 2: 12.960 B leídos y 12.960
  saltados; escala 3: 6480 y 12.960; `0xf1e48(4320, …)` cae en el mismo preescalado que con 4300
  (umbral `0x10f3` = 4339). `r15` vale 0 en `0x148ed6`: sus tres escrituras intermedias (`0x148c56`,
  `0x148ce4`, `0x148df2`) salen a `0x148f3c` si el resultado no es 0, y ningún salto entra entre
  `0x148ea0` y `0x148ee8`.
- *JPG.* El registro `0x0ff10200` sólo se toca desde el módulo `0x17a…`; el formato (bits 2, 3 y 9)
  sólo lo escribe `0x17aaf4`, y sus cuatro llamadores (vista en vivo `0xdbe48`, estadística `0x147bac`,
  `0x1479ee`, revisión `0x2525bc`) lo fijan antes de cada pasada. El procesado de la foto no llama a
  `0x17aaf4` ni habilita ese módulo (`0x17aa08`), y `0x25239c` lo deja deshabilitado al salir
  (`0x17aa24`).

**Inferido, sin prueba en la cámara**
- Que el IRP con entrada de memoria en formato 4 desempaquete igual que el DMA del sensor en modo 4
  (misma numeración, mismo hardware; ese camino con formato ≠ 0 nunca corrió).
- El tono de la revisión: la tabla de módulos de la revisión (`0x122944`) es la del RAW de 8 bits con
  curva; con 12 bits lineales la imagen puede verse más oscura o con dominante cálida (el AWB del modo
  4 sigue en su valor por omisión). Es una imagen reconocible, sin ruido.
- La rama nula con el cuadro completo no la usa el firmware de fábrica (siempre pasa recorte); comparte
  todo el código con la rama del recorte desde `0x25240e`.

**Riesgo que queda**
- Zoom digital ≠ 100 con M4Q: `0x25239c` toma la rama `0x2524e8`, que sí calcula todo según el formato
  (`0xf1ae0` alinea a 8 píxeles en formato 4) y que el firmware de fábrica tampoco ejecuta. Probar M4Q
  sin zoom digital.
- Modo 0 con M4Q cargado: la revisión leería 8 bits como 12 (ruido; lectura dentro del pool 8). M4Q
  sólo escribe con el modo en 4; para volver al modo 0, apagar.
- Si la primera foto muestra ruido y las siguientes salen bien, corrió la instrucción vieja desde la
  caché de instrucciones (mismo efecto anotado para M4L).

**Prueba E2E.** `tools/e2e_scripts.py`, 47 casos. Nuevos: el sitio del parche contra el firmware de
fábrica (palabras de `0x148b78` y `0x25239c`, y barrido de todo el código: una sola referencia a
`0x25239c`); M4Q ejecutado entero sobre el firmware como memoria en cinco estados (modo 4 de fábrica,
modo 0, cada palabra ajena, ya aplicado) con un control de valor cambiado; y el juego M4L + M4Q armado
como va a la SD. Pasos en la cámara: `sd_kit/PASOS.md`, paso 9.

## 2026-11-12 — M4Q probado: revisión sin ruido; tono verdoso por la tabla de linealización; script M4W

**Medido en la cámara** (`dump/raw18`, fotos 2012–2014, M4L + M4Q)
- `M4L.LOG`: `8`, `30757`, `3`, `28712`, `4`. `M4Q.LOG`: `4`, `49220`, `28682`, `51012`, `55300`.
- **La revisión sale reconocible y sin ruido.** La causa de la sección anterior queda confirmada: el
  IRP con entrada de memoria desempaqueta el formato 4 igual que el sensor lo escribe.
- La revisión se ve **verdosa**.
- Los tres JPG son correctos (3216×4288, escena reconocible, dominante cálida como con M4L solo;
  MakerNote con ganancias 481/256/390 y 471/256/396). Los tres RAW miden 21.150.720 B, 12 bits
  lineales (máximos 3644–4085) y **negro 0** (percentil 0,1 = 0 en los cuatro canales): el nivel de
  negro ya viene restado de la captura y no explica el color.

**Causa del tono verdoso (leída en el código)**
- La tabla de módulos de la revisión (`0x122944`, que sólo llama `0x148b78`) toma sus banderas de
  `0x1b02e0`: literal `0x00380300` en `0x1b03bc`. El bit 19 hace que `0x147670` cargue en el IRP la
  tabla de `0x1236e0` (`0x18fcf8`, 1024 palabras a `0x0ff11000`) y la habilite (`0x18fcc0`, bit 9 de
  `0x0ff100e0` en 0). Sin el bit, `0x147670` llama a `0x18fcdc` (bit 9 en 1: módulo en paso directo).
- Esa tabla (`0x429c4c`, 256 entradas: 64 → 66, 128 → 166, 192 → 415, 255 → 1023) es la **inversa de
  la curva del sensor** (`0x427e14`: 66 → 64, 166 → 128, 415 → 194, 1023 → 255): linealiza el RAW de
  8 bits con curva. La misma tabla la usa el AWB por software (`0x8cb52`, entre otros).
- M4L apaga la curva en la captura, así que la revisión **linealiza por segunda vez** datos que ya son
  lineales. Los canales con más señal suben más que los de menos, y en el RAW el verde es siempre el
  mayor: las ganancias de balance, calculadas para datos lineales, quedan cortas para rojo y azul. Es
  el efecto contrario al JPG rosado de P9 (datos con curva tratados como lineales).
- La vista en vivo, que procesa datos lineales del sensor con los mismos módulos, lleva las banderas
  `0x300401`: sin el bit 19. El paso directo es la configuración normal para datos lineales.

**M4W** (`sd_kit/fase1/Batch/M4W.srt`, lista `BatchScripts_M4LQW.txt` = M4L, M4Q, M4W). Una palabra de
16 bits: `0x1b03be` de `0x0038` a `0x0030` (el literal pasa de `0x00380300` a `0x00300300`: sólo se
apaga el bit 19). Guardias: M4L aplicado (`0x122780` = 28712), M4Q aplicado (`0x148ed8` = 55300),
literal de fábrica (56); relectura y registro. Es un dato leído con `ld_s [pcl]`: no pide desalojo de
caché. No corrió todavía en la cámara.

**Demostrado por código**
- *Alcance.* El literal `0x1b03bc` lo carga una sola instrucción (`0x1b02fa`, dentro de `0x1b02e0`);
  `0x1b02e0` tiene una sola llamada (`0x1229e8`) y `0x122944` otra sola (`0x148c52`). Sólo cambia la
  tabla de módulos de la revisión.
- *RAW.* La captura fija el módulo por su cuenta en cada disparo (`0xe3eaa` → `0x147670` con la tabla
  de captura, sin el bit 19) y el RAW se escribe antes de la revisión.
- *JPG.* Con el firmware de fábrica la revisión deja la linealización habilitada antes del procesado
  de cada foto, en todos los modos, y aun así el procesado linealiza en modo 0 y no linealiza en modo
  4 (JPG rosado de P9, JPG correcto de M4L). El procesado decide su linealización por sí mismo y no
  depende del estado que deja la revisión.
- *Otros usuarios.* Los seis llamadores de `0x147670` (vista en vivo, captura, estadística, revisión)
  ponen o quitan el paso directo según su propia tabla en cada pasada.

**Inferido, sin prueba en la cámara**
- Que el tono verdoso se deba sólo a esa tabla. Una simulación sobre el RAW 2013 con las ganancias de
  la cámara da (134, 114, 97) sin la tabla y (181, 179, 108) con ella: el verde alcanza al rojo.
- El brillo de la revisión en paso directo. Con M4W la revisión debería parecerse al JPG: cálida,
  porque usa las mismas ganancias de AWB.

**AWB del modo 4 (dominante cálida del JPG): evaluado, sin tocar**
- La estadística por foto (`0x86d14` → `0x147b14(0, RAW, …)`) lee el RAW con formato 0. Cambiar sólo
  ese argumento a 4 no alcanza: las 48 franjas se colocan en `fila·ancho` bytes de 8 bits, y en 12
  bits dos de cada tres empiezan a mitad de línea, con las filas del mosaico mezcladas.
- Además el cálculo del AWB linealiza por software con la misma tabla (`0x8cb52`): con datos lineales
  repetiría el defecto de la revisión.
- Arreglarlo pide tres cambios de código en funciones que alimentan el JPG. Por definición cambia el
  JPG guardado, así que queda fuera de M4W. Dos salidas sin riesgo: el balance del conversor
  (`m531raw.py`, parche blanco) y probar en la cámara un balance fijo del menú (Luz día, Tungsteno),
  cuyas ganancias no salen de la estadística. Esa prueba no se hizo.

**Prueba E2E.** `tools/e2e_scripts.py`, 53 casos. Nuevos: el sitio de M4W contra el firmware de
fábrica (literal, única carga, llamada única de `0x1b02e0` y de `0x122944`, bit 19 en `0x147824`),
M4W ejecutado sobre el firmware con M4L y M4Q encima en cinco estados con un control, y el juego
M4L + M4Q + M4W. Pasos en la cámara: `sd_kit/PASOS.md`, paso 10.

## 2026-11-12 — M4W probado en la cámara: revisión mejor, kit M4L + M4Q + M4W

- Logs exactos: M4L `8, 30757, 3, 28712, 4`; M4Q `4, 49220, 28682, 51012, 55300`; M4W `28712, 55300, 56, 48`.
- El usuario: la revisión "salió mejor", sin el tono verdoso. Fotos 2015–2018 en `dump/raw19` (con `SHA256SUMS`).
- JPG correctos. Las cuatro con flash (`Flash` = 25). Ganancias AWB del MakerNote ya no son las por omisión
  (400, 256, 456): 2015–2017 ≈ (471–491, 256, 389–392); 2018, con el preset Luz día (`WhiteBalance` = 1,
  `LightSource` = 1), (504, 256, 375).
- Blanco de referencia: el mouse blanco (más blanco que las teclas). En 2017 (vista cenital) y 2018 el mouse
  satura en parte (3,8 % de píxeles a 254+); las zonas claras sin saturar salen neutras (R/G 1,00–1,01,
  B/G 0,98–1,00). En 2015/2016 los claros mezclan madera y salen cálidos (R/G 1,19–1,25).

## 2026-11-12 — DNG verdoso en Vista Previa: matriz de cámara balanceada donde la norma pide cámara sin balancear

**Síntoma.** Los DNG de `m531raw.py` salían amarillo-verdosos en el motor RAW de macOS (Vista Previa, `sips`):
madera amarilla saturada, con el blanco casi bien. El JPG de la cámara y el revelado propio salían bien.

**Causa.** `CCM_M531` lleva cámara *ya balanceada* a sRGB lineal (filas que suman 1), que es el camino de la
cámara: balance en su espacio y después la matriz. El DNG escribía en `ColorMatrix1` la inversa de eso, con
iluminante D65. La norma DNG 1.4 pide en `ColorMatrix` XYZ → cámara *sin balancear*: al blanco D65 le toca
el neutro de la cámara con luz de día, y la matriz escrita le daba (1, 1, 1). Un motor que sigue la norma
aplica la matriz a los datos sin balancear y corrige el blanco después con una adaptación cromática en XYZ:
el blanco queda neutro y todo lo que tiene color se va a amarillo. LibRaw y darktable normalizan las filas de
la matriz y por eso casi no lo notaban. No había `ForwardMatrix` ni segundo iluminante.

**Arreglo en `m531raw.py`** (`matrices_dng`)
- `ColorMatrix2` (D65) = diag(neutro luz día) · inv(sRGB→XYZ · CCM). `ColorMatrix1` (iluminante A) = diag(neutro
  tungsteno) · inv(sRGB→XYZ · CCM) · Bradford(A→D65). `CalibrationIlluminant1/2` = 17 y 21.
- Neutros de la cámara: inversa de las ganancias de sus presets en el MakerNote de fotos sin flash de
  `dump/raw20`: Luz día 2021 = (451, 256, 417), Tungsteno 2020 = (248, 263, 828).
- `ForwardMatrix1/2` = Bradford(D65→D50) · sRGB→XYZ · CCM: el camino del conversor, para los motores que la usan.
- `AsShotNeutral` normalizado a máximo 1 (antes relativo a G, con R > 1 en luz cálida).
- La matriz es la misma `CCM_M531`; el mosaico no cambia.

**Dos fallos más que el revelado en darktable destapó, en el modo 4 lineal (M4L)**
- *Altas luces rosadas.* `WhiteLevel` era 4095, pero el sensor satura antes: el firmware resta el negro (≈ 120)
  después de saturar y quedan mesetas en 3965–4085 según canal y zona (2014, 2017, 2018, 2019). El motor las
  tomaba por datos válidos y el verde saturado quedaba corto tras el balance. `BLANCO_M4_LINEAL` = 3950.
- *Balance con flash de cerca.* Con el blanco quemado, lo más claro sin saturar es la madera y el parche blanco
  se va a cálido: contra el mouse blanco, error (máx. |ln| en R y B) 0,31 en 2018 y 0,21 en 2019. En esas tomas
  el AWB de la cámara sí se calcula y acierta (0,08 y 0,04). Regla: M4L con más de 2 % de celdas quemadas y AWB
  distinto del valor por omisión (400, 256, 456) → balance `awb_camara`. Aplica a 2017, 2018 y 2019.

**Medido** (sRGB linealizado del revelado; conversor anterior → nuevo)

| foto | parche | sips | darktable 5.6.2 |
| --- | --- | --- | --- |
| 2020 (M4L, tungsteno) | madera B/G (JPG de la cámara 0,96) | 0,21 → 0,88 | 0,74 → 0,85 |
| 2020 | mouse R/G, B/G | 0,94, 1,19 → 0,95, 1,12 | 0,93, 1,20 → 0,93, 1,16 |
| 2019 (M4L, flash, 27 % quemado) | mouse R/G, B/G | 0,99, 1,02 → 1,00, 1,00 | 1,00, 1,09 → 1,00, 1,01 |
| 2019 | zona rosada del mouse R/G, B/G | — | 1,06, 1,19 → 1,00, 1,00 |
| 2017 (M4L, flash) | mouse R/G, B/G | 1,00, 1,00 → 1,00, 1,00 | 1,02, 1,03 → 1,00, 0,98 |
| 1983 (modo 0) | madera, distancia al JPG (ln) | 1,58 → 0,02 | 0,29 → 0,11 |
| 1981 (P9) | madera, distancia a LibRaw (ln) | 1,54 → 0,07 | 0,02 → 0,03 |
| 1992 (modo 3) | madera, distancia a LibRaw (ln) | 0,52 → 0,02 | 0,13 → 0,10 |

- Queda: en 2020 y 2021 el mouse sale 12–16 % azulado. Es el balance por foto (parche blanco, error 0,09 contra
  el mouse; recibe además luz del monitor), no las etiquetas. El JPG de la cámara lo deja más azul (B/G 1,41).
  Subir el percentil del parche a 99,5 arregla esas dos y empeora los pares de modo 4 de `raw4`/`raw6`; no se tocó.
- Queda: los DNG de fotos verticales salen apaisados (la cámara gira el JPG y deja `Orientation` = 1).

**Prueba E2E.** `tools/e2e_raw.py`, `color_motores`: seis fotos reales de los cuatro formatos (M4L ×3, modo 0,
P9, modo 3) reveladas con `sips` y con `darktable-cli` si está. Exige el mouse neutro (tolerancia 0,18), madera
y teclas a menos de 0,25 del revelado de LibRaw y, en modo 0, a menos de 0,25 del JPG de la cámara. Con el
conversor anterior fallan cinco de los seis casos. Reporte y revelados en `work/e2e_raw/`.

**Archivos.** Regenerados todos los DNG de `dump/raw*/` (carpetas `dng`, `dng_v2` y los sueltos de raw1, raw2,
raw12, raw13). `convertir_carpeta.py` acepta `--sobrescribir`. Para el usuario: `~/Pictures/m531_dng/raw11` …
`raw20` (28 DNG con su JPG al lado; raw16 no tiene RAW).

## 2026-11-12 — Flujo de uso: balance por la escena, orientación, `./importar` y guía

**Balance de blancos por foto (`m531raw.py`, `neutro_claros_frios` y `elegir_balance`)**
- Síntoma: mouse blanco 12–16 % azulado en 2020 y 2021. El parche blanco (2 % más claro) mezclaba la
  madera iluminada con el blanco: neutro demasiado cálido, blanco azulado.
- Estimador nuevo: bloques de 8×8 celdas sin saturar, 15 % más claro y, de eso, la franja del 70 al 95 %
  más fría (ln B/R). Lo blanco es, entre lo claro, lo menos cálido; el 5 % más frío queda fuera.
- Medido con `tools/medir_balance.py` (23 fotos; verdad = mouse blanco en M4L, AWB de la cámara del par de
  modo 0 en P9, AWB propio en modo 0; error = máx. |ln| en R y B), fotos sin quemado:

  | grupo | parche blanco 98 % | parche 99,5 % | nuevo |
  | --- | --- | --- | --- |
  | M4L (2015, 2016, 2020, 2021) | 0,076 / 0,090 | 0,051 / 0,107 | 0,045 / 0,081 |
  | P9 (1975–1977, 1981, 1982) | 0,066 / 0,101 | 0,101 / 0,169 | 0,050 / 0,085 |
  | modo 0 (11 fotos) | 0,058 / 0,099 | 0,069 / 0,162 | 0,051 / 0,081 |

  (media / peor). 2020 y 2021 pasan de 0,090 a 0,032 y 0,036. Los tres parámetros no son un ajuste fino:
  toda la zona 80–90 / 70–80 / 90–98 da media 0,047–0,054.
- Revelado: mouse de 2020, B/G 1,12 → 1,04 en `sips` y 1,16 → 1,09 en darktable; 2021 igual (1,04 y 1,08).
  Queda un 4–9 % de azul: el mouse recibe además la luz del monitor.
- **Ganancias de la cámara (MakerNote `0x1318`) contra el mouse, en M4L:**

  | foto | qué son | error cámara | error escena |
  | --- | --- | --- | --- |
  | 2020 | preset Tungsteno, sin flash | 0,150 | 0,032 |
  | 2021 | preset Luz día con luz de lámpara | 0,554 | 0,036 |
  | 2015, 2016 | flash, mouse lejos (luz mixta) | 0,139, 0,212 | 0,081, 0,032 |
  | 2017 | flash, 6 % quemado | 0,044 | 0,046 |
  | 2018, 2019 | flash de cerca, 25–29 % quemado | 0,100, 0,033 | 0,158, 0,144 |

  El preset es el iluminante nominal, no la luz real: no pasa por delante de la escena. Las ganancias de
  flash ganan sólo cuando lo blanco está quemado.
- Regla (`--balance auto`): JPG en modo 0 → M4L con > 2 % quemado y AWB calculado: cámara → escena, si
  cae en el lugar de balances de la cámara → ganancias de la cámara si no son las por omisión → fijo
  (modo 4) o mundo gris. `--balance camara` fuerza las de la cámara. Modo 3 y modo 0 sin JPG usan ahora
  el estimador de escena en vez del mundo gris (1987 sin JPG: 0,05 contra la 1986 de la misma escena).

**Orientación**
- Decisión: el DNG sale **apaisado, como el sensor** (`Orientation` = 1). El giro del JPG no dice cómo se
  sostuvo la cámara (30 de 34 tomas giradas de más) y deja la etiqueta en 1. Con el RAW apaisado el
  error posible es uno solo y conocido: las tomas verticales salen acostadas.
- `--rotar no|izq|der|180|camara` en `m531raw.py dng`; `m531raw.py rotar` cambia sólo la etiqueta de un DNG
  o un JPG ya hecho (dos bytes). `izq` es el giro de la cámara (`Orientation` = 8).
- El JPG que queda junto al DNG lleva la misma orientación (etiqueta 6 sobre los píxeles girados); la
  copia verificada de `dump/` no se toca.
- Medido: darktable 5.6.2 y QuickLook (Finder, Vista Previa) giran según la etiqueta; `sips` no gira los
  píxeles, pasa la etiqueta al archivo que escribe.
- Pendiente en la cámara: una toma horizontal **nivelada**. Si sale sin girar, el sensor funciona en uso
  normal y `--rotar camara` pasa a ser la opción buena.

**`./importar`** (`tools/importar_sd.py`): SD → `dump/<fecha>/` con SHA-256 (lectura única, relectura del
disco, `SHA256SUMS`) → DNG y JPG en `~/Pictures/m531_dng/<fecha>/`. Salta lo ya importado por contenido
(cualquier carpeta de `dump/` con `SHA256SUMS`), un nombre repetido con otro contenido va a `<fecha>_2`,
un RAW ilegible no detiene a los demás, la SD sólo se abre en lectura. Guía: `docs/USO.md`.

**Pruebas E2E.** `tools/e2e_importar.py`: SD de mentira con fotos reales (M4L, modo 0, modo 3 sin JPG, JPG
de 0 bytes, una ya importada, un RAW truncado, un archivo ilegible, basura de macOS), sin permiso de
escritura y comparada entera antes y después; tres pasadas, 25 comprobaciones. Destapó que `sips` no
gira los píxeles. `tools/e2e_raw.py`: caso nuevo 2021 (preset equivocado) y tolerancia del blanco de
0,18 a 0,12. Regenerados los DNG de `~/Pictures/m531_dng/raw11` … `raw20`.

## 2026-11-12 — ¿Sirven los 12 bits? P8 (8 bits con curva) contra M4L (12 bits lineales), medido

`tools/comparar_bits.py` → `work/bits12/` (`reporte.json` y recortes). Fotos: modo 0 de raw8, raw10 y
raw17; M4L de raw13, raw18, raw19 y raw20. Unidad: DN12 = cuenta del RAW de 12 bits.

**Veredicto: en esta cámara el RAW de P8 guarda la misma imagen que el de M4L.** El ruido del sensor
tapa los bits de más en toda la escala.

- **Escala.** 1 cuenta de P8 decodificado = 4 DN12. La curva de ruido lo confirma: a igual señal e ISO,
  misma varianza en los dos modos (ISO 64: K = 1,14 en M4L y 1,18 en P8; ISO 160: 2,58 y 2,81).
- **Ruido en negro** (zonas sin luz, normal truncada porque el firmware recorta el negro en 0): 7,3 DN12
  en ISO 64 y 18,6 en ISO 160. Los 2,9 bits de abajo del RAW de 12 bits (4,2 en ISO 160) son ruido.
- **Niveles por paso** bajo el tope (P8 / 12 bits): 49 / 2046, 48 / 1023, 49 / 512, 48 / 256, 31 / 128,
  15 / 64, 8 / 32, 4 / 16, 2 / 8, 1 / 4. P8 tiene 256 códigos y los usa todos.
- **Escalón de P8 contra el ruido** (ISO 64, el caso más exigente): 40 DN12 con ruido 58 en el paso más
  alto (0,69 σ, +2,0 % de ruido); 20 con 41 (+1,0 %); 12 con 30 (+0,7 %); 4 DN12 de ahí hacia abajo
  con ruido 8–22 (0,2–0,5 σ, menos de +1 %). En ISO 160, menos de +0,9 % en todos los pasos.
- **Tope de luces.** El mismo: P8 llega al código 255 (4092 DN12) y M4L a 4095, con las mesetas de
  saturación del sensor en 3965–4085. Los 12 bits no dan margen arriba.
- **Rango útil** (del tope 3950 a SNR = 1): 9,08 EV en M4L y 9,07 en P8 en ISO 64; 7,73 y 7,73 en ISO 160.
- **Bandas al forzar.** P8 simulado desde la misma foto M4L (÷4, código más cercano, decodificar):
  error por píxel 1,2–13 DN12, siempre bajo el ruido; tras promediar 16×16 el sesgo es 0,07–1,2 DN12
  (≤ 0,6 %). Sombras subidas +5 EV hasta gris medio y suavizadas 9×9: diferencia media 0,5 niveles de
  255, percentil 99 de 3–4. Balance extremo (B ×2,5, R ×0,6): media 0,4, percentil 99 de 1–2. Sin
  bandas ni posterización en ninguno. Recortes: `sombras_*.png`, `sombras_nr_*.png`, `balance_*.png`,
  y P8 real contra M4L real en `sombras_reales_p8_m4l.png`.
- Límite de la simulación: supone que la cámara codifica al código más cercano. Los P8 reales lo
  respaldan (mismo ruido por tramo que M4L, mismo tope).

**Dónde importan los 12 bits:** en nada visible. Ventajas reales de M4L: datos lineales sin depender de la
tabla `0x429c4c`, y escalones finos en el paso más alto (ahí P8 añade 2 % de ruido).
**Costos de M4L:** 21,2 MB por foto contra 14,1; tres parches en RAM; el balance automático del JPG no
se calcula sin flash (queda en 400/256/456).

**Qué da el RAW (los dos modos por igual), por orden de provecho**
1. Balance de blancos después de la toma, sin pérdida. Es lo que más rinde: el JPG de M4L sin flash sale
   con el balance por omisión y el preset queda a 0,15 de un blanco real.
2. Recuperar luces que el JPG quemó: el JPG llega a blanco con el RAW en 1850–3350 DN12, entre 0,24 y
   1,1 EV bajo el tope. De lo que el JPG quema, el RAW conserva sin saturar del 25 al 100 % según la toma.
3. Subir sombras: +2 a +3 EV utilizables en ISO 64. Más allá manda el ruido de lectura y aparece un
   velo violeta, porque el negro viene recortado en 0 (media de +6 DN12 en lo que debería ser 0).
4. Reducción de ruido y nitidez propias en vez de las de la cámara. El RAW trae píxeles calientes.
5. Apilar varias tomas con trípode: el ruido baja con √N y los 8 bits de P8 no lo estorban (el ruido
   reparte la cuantización). El recorte del negro en 0 es el límite.
6. Horquillado de exposición: 9 EV por toma en ISO 64 y 7,7 en ISO 160; dos tomas a ±2 EV dan unos 11.

**Prueba en cámara que cerraría lo que los archivos no cierran** (trípode, escena fija con una zona de
sombra y algo blanco, ISO fijo si el menú lo permite, sin flash):
1. Kit P8: una toma normal, una a −2 EV y una con el objetivo tapado.
2. Apagar, kit M4L + M4Q + M4W: las mismas tres.
3. Opcional: ocho tomas iguales con cada kit, para apilar.
Mide: la codificación real de P8 contra la simulada (misma escena y exposición), el ruido de lectura en
negro verdadero y si la toma a −2 EV subida +2 EV iguala a la normal en los dos modos.
