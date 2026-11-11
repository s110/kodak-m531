#!/bin/bash
# uso: tools/dis.sh INICIO FIN [archivo_bin]   (direcciones RAM en hex; el binario empieza en RAM 0)
set -e
cd /Volumes/Datos/proyectos/kodak-m531
B=${3:-work/ram_lo8M.bin}
ELF=work/elf_$(shasum -a 256 "$B" | cut -c1-16).elf   # un ELF por contenido: nunca el de otro binario
[ -f "$ELF" ] || docker run --rm -v $PWD:/w kodak-arctools:24.04 arc-linux-gnu-objcopy -I binary -O elf32-littlearc -B arc --set-section-flags .data=contents,alloc,load,readonly,code "$B" "$ELF"
docker run --rm -v $PWD:/w kodak-arctools:24.04 arc-linux-gnu-objdump -D -M cpu=arc700 "$ELF" --start-address=$1 --stop-address=$2 | tail -n +8 | sed -E 's/<_binary_[A-Za-z0-9_]+_start\+0x([0-9a-f]+)>/<\1>/'
