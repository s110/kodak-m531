#!/bin/bash
# uso: tools/dis.sh INICIO FIN [archivo_bin]   (direcciones RAM en hex)
B=${3:-work/ram_lo8M.bin}
cd /Volumes/Datos/proyectos/kodak-m531
[ -f work/ram.elf ] && [ work/ram.elf -nt "$B" ] || docker run --rm -v $PWD:/w kodak-arctools:24.04 arc-linux-gnu-objcopy -I binary -O elf32-littlearc -B arc --set-section-flags .data=contents,alloc,load,readonly,code "$B" work/ram.elf
docker run --rm -v $PWD:/w kodak-arctools:24.04 arc-linux-gnu-objdump -D -M cpu=arc700 work/ram.elf --start-address=$1 --stop-address=$2 | tail -n +8 | sed -E 's/<_binary_work_ram_lo8M_bin_start\+0x([0-9a-f]+)>/<\1>/'
