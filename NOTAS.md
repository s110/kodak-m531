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
