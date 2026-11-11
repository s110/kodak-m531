#!/usr/bin/env python3
"""Lee un rango de la RAM de la Kodak M531 a través de su CD virtual USB.

uso: python3 -I tools/leer_ram.py /dev/rdiskN INICIO FIN salida.bin   (direcciones RAM en hex)

La cámara expone un "CD" de bloques de 2352 B: 16 B de cabecera falsa + 2048 B de datos.
Más allá del ISO, la ventana de 64 MB es la SDRAM: RAM[a] = ventana[(a + 0xB22C00) % 64 MB].
Se lee de a 16 sectores con lseek explícito; las lecturas cortas se reintentan.
"""
import os, sys
K, WIN, S, BS = 0xB22C00, 0x4000000, 2352, 16

def leer(fd, a, n):
    out = bytearray()
    while n > 0:
        w = (a + K) % WIN
        sec = w // 2048
        base = sec - sec % BS
        os.lseek(fd, base * S, 0)
        buf = b''
        while len(buf) < BS * S:
            c = os.read(fd, BS * S - len(buf))
            if not c:
                raise IOError('lectura corta: ¿se apagó la cámara?')
            buf += c
        datos = b''.join(buf[i*S+16:i*S+2064] for i in range(BS))
        ini = w - base * 2048
        trozo = datos[ini:ini + min(n, len(datos) - ini, WIN - w)]
        out += trozo; a += len(trozo); n -= len(trozo)
    return bytes(out)

if __name__ == '__main__':
    dev, ini, fin, sal = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16), sys.argv[4]
    fd = os.open(dev, os.O_RDONLY)
    open(sal, 'wb').write(leer(fd, ini, fin - ini))
    print(f'{sal}: {fin-ini:#x} bytes desde RAM {ini:#x}')
