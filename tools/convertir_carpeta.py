#!/usr/bin/env python3
"""Convierte todos los RAW de la M531 de una carpeta (p. ej. DCIM/101KM531 de la SD) a DNG.

uso: .venv/bin/python tools/convertir_carpeta.py CARPETA_ORIGEN CARPETA_DESTINO

- Busca 101O####.RAW (y su JPG hermano 101_####.JPG para el balance de blancos).
- Escribe 101_####.DNG en el destino; no sobrescribe DNG existentes.
- Copia el JPG hermano al destino para tener el par junto.
- Deja un resumen.json con formato, balance y errores por archivo.
No escribe nada en la carpeta de origen.
"""
import json
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    origen, destino = sys.argv[1], sys.argv[2]
    os.makedirs(destino, exist_ok=True)
    resumen = []
    raws = sorted(f for f in os.listdir(origen) if re.fullmatch(r'\d{3}O\d{4}\.RAW', f, re.I))
    for f in raws:
        num = f[4:8]
        dng = os.path.join(destino, f'{f[:3]}_{num}.DNG')
        jpg = os.path.join(origen, f'{f[:3]}_{num}.JPG')
        item = dict(raw=f)
        if os.path.exists(dng):
            item.update(estado='ya existía')
            resumen.append(item)
            continue
        if os.path.exists(jpg) and os.path.getsize(jpg) > 10_000:
            shutil.copy2(jpg, destino)
        p = subprocess.run([sys.executable, os.path.join(AQUI, 'm531raw.py'), 'dng', os.path.join(origen, f), '-o', dng],
                           capture_output=True, text=True)
        if p.returncode:
            item.update(estado='error', error=p.stderr.strip()[-300:])
        else:
            info = json.loads(p.stdout)
            item.update(estado='ok', formato=f"{info['packing']} {info['ancho']}x{info['alto']}",
                        cfa=info['cfa'], balance=info.get('balance'), neutro=info.get('neutro'))
        resumen.append(item)
        print(item['estado'].ljust(10), f, item.get('formato', ''), item.get('error', ''))
    json.dump(resumen, open(os.path.join(destino, 'resumen.json'), 'w'), indent=1, ensure_ascii=False)
    ok = sum(1 for x in resumen if x['estado'] == 'ok')
    print(f'{ok} convertidos, {len(resumen) - ok} sin convertir; resumen en {destino}/resumen.json')


if __name__ == '__main__':
    main()
