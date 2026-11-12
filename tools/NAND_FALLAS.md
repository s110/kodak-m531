# Verificador de volcados de la NAND Tool: cómo puede fallar (escrito antes del código)

Lo que se sabe por el código (`NOTAS.md`, sección "NAND Tool: manejadores de Dump"): cada opción
"Dump" lee una partición entera a un búfer relleno con 0xFF y lo escribe en `B:\<nombre>`.
El largo del archivo es el que devuelve la rutina de lectura (`0x1436fc`), que no está medido:
puede ser la partición completa o sólo lo ocupado. El verificador no puede dar por supuesto ninguno
de los dos.

## Archivos
1. Falta un archivo (opción no ejecutada, tarjeta llena, cámara apagada a mitad) → se pasaría por
   alto un volcado incompleto. Las opciones A1 y E1 escriben dos archivos cada una
   (`Calibration.dmp` + `Calibration_2.dmp`, `CameraParam.dmp` + `CameraParam_2.dmp`).
2. Nombres en mayúsculas o 8.3 distintos (FAT) → no encontrarlos y declararlos ausentes.
3. Archivo de largo 0, o todo 0xFF / todo 0x00 (lectura fallida o partición borrada).
4. Archivo truncado: escritura cortada por batería o por sacar la SD.
5. Archivo más grande que su partición: no es ese volcado, o la tabla es otra.
6. La copia al Mac alteró un archivo (dos copias con hashes distintos).
7. En la carpeta hay un archivo que nunca debió estar en la SD (`ALLOW_ERASE_BOOT`,
   `ALLOW_ROLLBACK_OLD_PARTITION`, `TBIB_*.BIN`, `TBM_*.BIN`, `KM531.FW`, `NANDUtility.txt`,
   `BootNANDBase.bin`): hay que avisarlo aunque los volcados estén bien.

## MainCode.dmp (partición 6)
8. No empieza por `RHIR` (volcado de otra partición o desplazado).
9. La cabecera difiere de la leída en la RAM (`firmware/stock/header_first_0xa0.bin`): otra
   versión de firmware o cabecera dañada.
10. Palabra de modelo distinta de `0x01121410`.
11. Un registro se sale del archivo (volcado truncado antes del final de los datos).
12. La sum32 de un registro tipo 1 no coincide (bit cambiado en código, datos o `rec3`).
13. La sum32 de un registro tipo 0 no coincide: el arranque no la revisa, así que un gráfico o un
    idioma dañado pasaría sin aviso.
14. El código coincide en suma y difiere del reconstruido desde la RAM (colisión de sum32 o error
    de la reconstrucción): comparar bytes, no sólo sumas.
15. Relleno 0xFF tras el final de los datos tomado por dato, o al revés.
16. El registro tipo 2 (bloque absoluto 1442) se intenta leer dentro del archivo.

## BootCode.dmp (partición 0)
17. No se sabe si el volcado empieza por la cabecera de 16 B (`0x800000, 0x2cff0, 0xbbb66ba4,
    0x800030`) o directo por el código: hay que probar las dos disposiciones y decir cuál es.
18. La sum32 del cuerpo no da `0xbbb66ba4`.
19. La suma coincide y los bytes difieren del boot residente en RAM.
20. La cabecera aparece en un desplazamiento inesperado (bloques de reserva antes del código).

## Tabla de particiones y textos
21. `NANDPartition.txt` con tamaños distintos de los de la tabla en RAM (`0x4da228`): el tamaño de
    la partición 6 que usa `km531fw.py --particion` sería otro.
22. `NANDPartition.txt` con otro formato (línea que falta, valor no hexadecimal).
23. `NANDP1.dmp` sin `P1IDSTR`.
24. Los tamaños de los archivos contradicen la tabla (por ejemplo `MainCode.dmp` de más de 500
    bloques).
25. `BFNSetting.txt` vacío o ilegible (no se conoce su contenido esperado: sólo se guarda).

## Comparaciones
26. `Calibration.dmp` y `Calibration_2.dmp` distintos: puede ser normal (dos copias con contador)
    o una copia dañada. No se sabe: se informa, no se condena.
27. `CameraParam.dmp` cambió respecto de un volcado anterior: es justo lo que se quiere medir
    (ajustes que la cámara guarda sola); hay que listar qué bytes cambian.

## Cómo lo cubre la prueba
`tools/e2e_nand.py` arma un juego de volcados con las piezas reales (cabecera, código, gráficos y
`rec3` de `firmware/stock`, boot residente en RAM, tabla de particiones de la RAM), en la
disposición más incómoda admitida (nombres en mayúsculas, partición completa con relleno 0xFF, boot
con cabecera) y exige el veredicto correcto para el juego sano y para cada daño: bit cambiado en
el código, bit cambiado en un gráfico, truncado, modelo cambiado, boot con un bit cambiado, boot
sin cabecera, tabla con otro tamaño, archivo prohibido presente, calibración borrada, archivo
ausente y segunda copia alterada. Lo que no puede cubrir: el contenido real de calibración,
parámetros, reserva, BFN y de la sección de datos e idiomas, que no existen fuera de la cámara.
