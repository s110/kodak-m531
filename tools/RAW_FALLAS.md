# Conversor RAW M531 → DNG: cómo puede fallar (escrito antes del código)

Lo que sabemos del firmware: el RAW se guarda con `0x1b066c`, sin cabecera, en dos archivos
por disparo (101O####.raw y 101b####.raw: el firmware cambia el '_' del nombre del JPG por 'O' o 'b' y la extensión por raw; probablemente los dos campos de un CCD entrelazado). Tamaño
= ceil(ancho × alto × bits / 8) con bits ∈ {8, 10, 12, 16} según el modo (`0x76680`).
Las dimensiones se fijan al capturar; no están en la RAM en reposo.

## Formato desconocido
1. Profundidad de bits mal elegida → imagen con bandas diagonales o ruido puro.
2. Empaquetado mal elegido (flujo de bits LSB-first vs MSB-first, pares de 12 bits big-endian,
   16 bits LE vs BE) → valores escalonados, texturas en peine.
3. Ancho mal elegido → imagen cizallada en diagonal. Varios anchos dividen el total de píxeles.
4. Relleno al final de cada fila (stride ≠ ancho×bits/8) → cizalla leve que crece por fila.
5. Relleno o datos extra al final del archivo (ceil a bytes, alineación a sector) → el total
   de píxeles no es entero; hay que tolerar bytes sobrantes.
6. Los dos archivos no son campos par/impar sino mitades superior/inferior, o el mismo cuadro
   en dos exposiciones, o uno es un cuadro negro (dark frame) → intercalar filas los mezcla mal.
7. Campos entrelazados de a pares de filas (0,1 | 2,3) en lugar de filas sueltas.
8. Los campos tienen distinta cantidad de filas (n y n+1).

## Color y niveles
9. Patrón CFA mal identificado (RGGB/BGGR/GRBG/GBRG) → colores cambiados (magenta/verde).
10. R y B indistinguibles sólo con estadística → necesita una toma de referencia.
11. Nivel de negro desconocido; zonas de negro óptico en los bordes sesgan el autoajuste.
12. Valores ya comprimidos con curva (como el CCDI de la C713) → DNG no lineal.
13. Nivel de blanco distinto de 2^bits − 1 (ganancia digital, recorte previo).

## DNG
14. Etiquetas mal formadas → LibRaw/Lightroom lo rechazan o lo leen con otro tamaño.
15. Orden de bytes o BitsPerSample incoherentes con los datos escritos.
16. Recorte por defecto (DefaultCrop) fuera de rango.

## Cómo lo cubre la prueba
La prueba E2E fabrica desde una foto real un mosaico Bayer de tamaño no estándar, lo empaqueta en
cada formato, lo parte en dos campos y lo pasa por el conversor sin pistas. Exige detectar bits,
empaquetado, ancho, disposición de campos y fase CFA, y que LibRaw (rawpy) lea el DNG con valores
idénticos píxel a píxel. Los puntos 10, 12 y 13 no se pueden resolver sin una toma real: quedan
como opciones manuales (`--cfa`, `--black`, `--white`) y se resuelven con la primera foto.
