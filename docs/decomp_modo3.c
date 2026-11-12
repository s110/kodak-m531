// Modo de captura 3 (RAW de 16 bits): funciones leídas para el análisis del cuelgue. Ghidra 12.1.4 + ARCompact,
// -noanalysis, tools/ghidra_scripts/Decomp.java sobre work/code_only.bin (sha256 9e4c35fe…f69a). Salida sin editar.
// 0x2b0948 arranque del HWIRP (llama al validador 0x2b0160, límite 0x1ffc: 430 líneas, queda en
// work/decomp_m3a.c), 0x1bc528 capa de estados,
// 0x12989c/0x129a1c inicio/parada de la tubería, 0x155b3c primer paso de la tarea JPEG, 0x15714c salida de la
// tarea (archivo de 224 B), 0x12aba4 ranuras del pool 8, 0x12b3c4 plan de búferes de la captura,
// 0x12bc04 liberación de la ranura, 0xf0d14 gancho de vista rápida.

// ==== 0x2b0948 -> FUN_ram_002b0948 @ ram:002b0948

int FUN_ram_002b0948(void)

{
  int iVar1;
  int iVar2;
  int iVar3;
  int iVar4;
  undefined4 uVar5;
  
  iVar2 = func_0x00307158();
  func_0x000fa21c(4);
  func_0x000dfc48(0x17,3,0xc000);
  func_0x00065d6c(uRam002b0ccc,uRam002b0cd0);
  iVar3 = func_0x00060dbc(0x603,uRam002b0cd4);
  if (iVar3 == 0) {
    iVar3 = 0;
  }
  iVar4 = func_0x00060d0c(0x603,0xff);
  iVar1 = iRam002b0cd8;
  uVar5 = uRam002b0ccc;
  if ((iVar4 != 0) && (iVar3 == 0)) {
    iVar3 = iVar4;
  }
  *(undefined4 *)(iRam002b0cd8 + 0x20) = 0;
  *(undefined4 *)(iVar1 + 0x1c) = 0;
  *(undefined4 *)(iVar1 + 0x18) = 0;
  *(undefined4 *)(iVar1 + 0x14) = 0;
  *(undefined4 *)(iVar1 + 0x10) = 0;
  func_0x00065d6c(uVar5,1);
  func_0x002dc8dc();
  func_0x002dc914();
  func_0x002dcaac(1);
  uVar5 = func_0x002df6b8();
  iVar4 = func_0x00065d90(uRam002b0ccc,1,0,uVar5);
  func_0x002ddbf8();
  func_0x002ddc14();
  if ((iVar4 != 0) && (iVar3 == 0)) {
    iVar3 = iVar4;
  }
  iVar4 = func_0x002afaa8(iVar2,1);
  if ((iVar4 != 0) && (iVar3 == 0)) {
    iVar3 = iVar4;
  }
  iVar4 = FUN_ram_002b0160(iVar2);
  if ((iVar4 != 0) && (iVar3 == 0)) {
    iVar3 = iVar4;
  }
  if (iVar3 == 0) {
    *(undefined1 *)(iVar1 + 5) = *(undefined1 *)(iVar2 + 0x65);
    func_0x000fa054();
    func_0x002dcb48(*(undefined1 *)(iVar1 + 5));
    func_0x002dcae0(*(undefined1 *)(iVar1 + 5));
    func_0x002dcb7c(1);
    func_0x002dcb14(1);
    func_0x000fa1e8();
    *(undefined1 *)(iVar1 + 4) = 1;
  }
  else {
    func_0x002b0930();
  }
  return iVar3;
}


// ==== 0x1bc528 -> FUN_ram_001bc528 @ ram:001bc528

int FUN_ram_001bc528(void)

{
  int *piVar1;
  int iVar2;
  int iVar3;
  undefined8 uVar4;
  
  uVar4 = func_0x0030715c();
  piVar1 = piRam001bc694;
  iVar2 = (int)uVar4;
  if ((*piRam001bc694 == 0) || (iVar3 = iRam001bc698, *piRam001bc694 == 0xff)) {
    func_0x000601a4(uRam001bc69c);
    if (((int)((ulonglong)uVar4 >> 0x20) == 0) &&
       (((*(int *)(iVar2 + 0x14) + 0xfU & 0xfffffff0) <= uRam001bc690 &&
        ((*(int *)(iVar2 + 0x1c) + 0xfU & 0xfffffff0) < 0x1000)))) {
      iVar3 = 0;
    }
    else if (*(int *)(iVar2 + 0x15c) == 0) {
      iVar3 = 2;
    }
    else {
      iVar3 = 1;
    }
    piVar1[1] = iVar3;
    if (iVar3 == 0) {
      iVar3 = FUN_ram_002b0a30(iVar2);
    }
    else if (iVar3 == 2) {
      iVar3 = func_0x002b0d8c();
    }
    else {
      iVar3 = func_0x002b1450(iVar2);
    }
    if (iVar3 == 0) {
      *piVar1 = 1;
    }
  }
  return iVar3;
}


// ==== 0x12989c -> FUN_ram_0012989c @ ram:0012989c

int FUN_ram_0012989c(void)

{
  int *piVar1;
  code *pcVar2;
  code *pcVar3;
  code *pcVar4;
  int *piVar5;
  int iVar6;
  uint uVar7;
  int iVar8;
  code *pcVar9;
  
  piVar5 = (int *)func_0x0030715c();
  piVar1 = piRam00129c04;
  if ((((*piRam00129c04 == 0) || (iVar6 = iRam00129c18, *piRam00129c04 == 4)) &&
      (iVar6 = iRam00129bf8, piVar5 != (int *)0x0)) &&
     ((iVar6 = func_0x001bb744(), iVar6 == 0 ||
      (((iVar6 = iRam00129c00, *(ushort *)(piVar5 + 0x17) != 0 &&
        ((int)(uint)*(ushort *)(piVar5 + 0x17) <= iRam00129bfc)) &&
       ((*(ushort *)((int)piVar5 + 0x5e) != 0 && (*(ushort *)((int)piVar5 + 0x5e) < 0x1000)))))))) {
    func_0x001bb798(0);
    func_0x001bc294();
    piVar1[6] = *piVar5;
    func_0x00065d6c(uRam00129c1c,0x10000000);
    iVar6 = func_0x001bb768();
    piVar1[10] = iVar6;
    uVar7 = func_0x000dcd68();
    if ((uVar7 < 4) && (0xfff < *(uint *)(piVar5[1] + 4))) {
      piVar5[2] = 0;
    }
    pcVar9 = pcRam00129c54;
    pcVar4 = pcRam00129c44;
    pcVar3 = pcRam00129c34;
    pcVar2 = pcRam00129c24;
    if (piVar5[2] == 0) {
      if (piVar5[4] == 0) {
        piVar1[3] = iRam00129c20;
        piVar1[4] = iRam00129c28;
        iVar6 = iRam00129c2c;
        piVar1[2] = (int)pcVar2;
        pcVar9 = pcVar2;
      }
      else {
        piVar1[3] = iRam00129c30;
        piVar1[4] = iRam00129c38;
        iVar6 = iRam00129c3c;
        piVar1[2] = (int)pcVar3;
        pcVar9 = pcVar3;
      }
    }
    else if (piVar5[4] == 0) {
      piVar1[3] = iRam00129c40;
      piVar1[4] = iRam00129c48;
      iVar6 = iRam00129c4c;
      piVar1[2] = (int)pcVar4;
      pcVar9 = pcVar4;
    }
    else {
      piVar1[3] = iRam00129c50;
      iVar6 = iRam00129c58;
      piVar1[2] = (int)pcVar9;
      piVar1[4] = iVar6;
      iVar6 = iRam00129c5c;
    }
    piVar1[5] = iVar6;
    iVar6 = (*pcVar9)(piVar5);
    if (iVar6 == 0) {
      iVar6 = 0;
    }
    if (iVar6 == 0) {
      *piVar1 = 1;
    }
    iVar8 = func_0x001bb768();
    piVar1[0xb] = iVar8;
  }
  return iVar6;
}


// ==== 0x129a1c -> FUN_ram_00129a1c @ ram:00129a1c

undefined4 FUN_ram_00129a1c(void)

{
  int *piVar1;
  int iVar2;
  undefined4 uVar3;
  
  func_0x0030715c();
  func_0x001bb798(4);
  piVar1 = piRam00129c04;
  iVar2 = *piRam00129c04;
  if ((((iVar2 == 3) || (iVar2 == 1)) || (iVar2 == 2)) || (uVar3 = uRam00129c18, iVar2 == 0)) {
    iVar2 = func_0x001bb768();
    piVar1[10] = iVar2;
    uVar3 = (*(code *)piVar1[5])();
    *piVar1 = 4;
    iVar2 = func_0x001bb768();
    piVar1[0xb] = iVar2;
    piVar1[6] = 0;
    func_0x001bc2ac();
  }
  return uVar3;
}


// ==== 0x155b3c -> FUN_ram_00155b3c @ ram:00155b3c

int FUN_ram_00155b3c(void)

{
  char cVar1;
  ushort uVar2;
  undefined1 *puVar3;
  int *piVar4;
  int iVar5;
  int iVar6;
  int iVar7;
  uint uVar8;
  int iVar9;
  undefined4 uVar10;
  code *pcVar11;
  int in_mlo;
  
  piVar4 = (int *)func_0x00307150();
  func_0x000601a4(uRam00155ec8);
  func_0x0004810c(piVar4,0x40);
  *piVar4 = piVar4[0xf5];
  iVar5 = (*(code *)**(undefined4 **)(iRam00155ecc + 4))(piVar4);
  if (iVar5 == 0) {
    iVar5 = 0;
  }
  if ((piVar4[0xf5] != *piVar4) && (iVar5 == 0)) {
    iVar5 = iRam00155ed0;
  }
  func_0x0004810c(piVar4 + 0x24,0x244);
  func_0x0004810c(piVar4 + 0xb5,0x44);
  func_0x0004810c(piVar4 + 0xc6,0x9c);
  func_0x0004810c(piVar4 + 0xed,0x20);
  func_0x0004810c(piVar4 + 0x24,0x114);
  func_0x0004810c(piVar4 + 0x69,0x114);
  func_0x0004810c(piVar4 + 0x10,0x50);
  iVar6 = func_0x000ea504();
  piVar4[0x10] = iVar6;
  iVar6 = func_0x000ea528();
  piVar4[0x11] = iVar6;
  iVar6 = func_0x000ea54c();
  piVar4[0x12] = iVar6;
  *(undefined1 *)(piVar4 + 0x23) = 0;
  piVar4[0xd8] = *(int *)(piVar4[0xf5] + 0x48);
  piVar4[0xdc] = piVar4[0xf5];
  piVar4[0xde] = 0;
  piVar4[0xdf] = 1;
  piVar4[0xe0] = 1;
  func_0x000e9798(piVar4 + 0xc6);
  iVar6 = func_0x00053ab0(uRam00155ed4);
  if ((iVar6 != 0) && (iVar5 == 0)) {
    iVar5 = iVar6;
  }
  iVar6 = func_0x00053aa0();
  if ((iVar6 != 0) && (iVar5 == 0)) {
    iVar5 = iVar6;
  }
  func_0x000e97ec(piVar4 + 0xed);
  if (iVar5 == 0) {
    iVar5 = piVar4[0xf4];
  }
  if (*(char *)(piVar4[0xf5] + 0x17c) != '\0') {
    pcVar11 = *(code **)(*(int *)(iRam00155ecc + 4) + 0x28);
    if ((pcVar11 != (code *)0x0) && (iVar5 == 0)) {
      iVar5 = (*pcVar11)(piVar4[6],piVar4[7]);
    }
    pcVar11 = *(code **)(*(int *)(iRam00155ecc + 4) + 0x2c);
    if ((pcVar11 != (code *)0x0) && (iVar5 == 0)) {
      iVar5 = (*pcVar11)(piVar4[0xf5]);
    }
    if (iVar5 != 0) {
      return iVar5;
    }
  }
  iVar5 = iRam00155ed8;
  func_0x0004810c(iRam00155ed8,100);
  puVar3 = puRam00155ee4;
  iVar9 = iRam00155ee0;
  iVar6 = iRam00155edc;
  iVar7 = piVar4[0xf5];
  *(int *)(iRam00155edc + 0x3e0) = iVar7;
  *(undefined4 *)(iVar6 + 0x3e4) = *(undefined4 *)(iVar7 + 0xac);
  *(undefined4 *)(iVar6 + 1000) = *(undefined4 *)(piVar4[0xf5] + 0xb0);
  *(undefined4 *)(iVar6 + 0x3ec) = *(undefined4 *)(piVar4[0xf5] + 0xb4);
  *(undefined4 *)(iVar6 + 0x3f0) = *(undefined4 *)(piVar4[0xf5] + 0xb8);
  *(undefined4 *)(iVar6 + 0x3f4) = *(undefined4 *)(piVar4[0xf5] + 0xbc);
  iVar7 = piVar4[0xf5];
  *(undefined4 *)(iVar6 + 0x3f8) = *(undefined4 *)(iVar7 + 0xc0);
  cVar1 = *(char *)(*(int *)(iVar5 + 4) + 99);
  *(char *)(iRam00155ecc + 0x10) = cVar1;
  *(int *)(iVar9 + -0x3f4) = piVar4[6];
  *(int *)(iVar9 + -0x3f0) = piVar4[7];
  *puVar3 = 1;
  Auxregs0104 = 0;
  uVar2 = *(ushort *)(iVar7 + 0x60);
  asm_instruction_05(0xd,(uint)*(ushort *)(iVar7 + 0x62),(uint)uVar2);
  if (cVar1 == '\0') {
    in_mlo = in_mlo * 3;
    if (in_mlo < 0) {
      in_mlo = in_mlo + 1;
    }
    in_mlo = in_mlo >> 1;
    iVar6 = 0x70800;
  }
  else {
    in_mlo = in_mlo * 2;
    iVar6 = 0x96000;
  }
  iVar6 = in_mlo * (uint)(in_mlo > iVar6) + iVar6 * (uint)(in_mlo <= iVar6);
  *(int *)(iVar9 + -0x3d8) = iVar6;
  iVar6 = func_0x000e9c34(iVar6,in_mlo,(uint)uVar2);
  if ((iVar6 != 0) || (iVar6 = func_0x000e9c44(), iVar6 != 0)) {
    *(int *)(iVar9 + -0x3d8) = *(int *)(iVar5 + 0x44) + 0xc00;
  }
  uVar8 = func_0x003086cc(*(undefined4 *)(*(int *)(iVar5 + 4) + 8),
                          *(undefined4 *)(*(int *)(iVar5 + 4) + 4));
  *(bool *)(iRam00155ee8 + 0x14) = 0x5fffff < uVar8;
  iVar6 = iRam00155eec;
  *(undefined2 *)(iRam00155eec + 0x40) = *(undefined2 *)(piVar4[0xf5] + 0x17e);
  *(undefined2 *)(iVar6 + 0x42) = *(undefined2 *)(piVar4[0xf5] + 0x180);
  func_0x00256aa4(0x40);
  func_0x00256ac0(0xc0);
  iVar6 = func_0x00129810();
  if (iVar6 != 0) {
    return iVar6;
  }
  if (*(uint *)(iVar5 + 0x2c) < *(uint *)(iVar5 + 0x24)) {
    return iRam00155ef0;
  }
  iVar6 = func_0x000e9c34();
  if (iVar6 == 0) {
    iVar9 = func_0x000e9c44();
    iVar6 = iRam00155ecc;
    uVar10 = *(undefined4 *)(iVar5 + 0x48);
    if (iVar9 == 0) {
      *(undefined4 *)(iRam00155ecc + 0x18) = uVar10;
      *(undefined4 *)(iVar6 + 0x14) = uVar10;
      goto code_r0x00155dd2;
    }
  }
  iVar6 = iRam00155ecc;
  iVar9 = *(int *)(iVar5 + 0x48);
  *(int *)(iRam00155ecc + 0x38) = iVar9;
  iVar9 = iVar9 + 0xc00;
  *(int *)(iVar6 + 0x18) = iVar9;
  *(int *)(iVar6 + 0x14) = iVar9;
code_r0x00155dd2:
  iVar6 = iRam00155ecc;
  uVar8 = *(int *)(iVar5 + 0x50) + 7U & 0xfffffff8;
  *(uint *)(iRam00155ecc + 0x30) = uVar8;
  *(uint *)(iVar6 + 0x34) = uVar8;
  iVar9 = *(int *)(iVar5 + 0x2c);
  iVar6 = *(int *)(iVar5 + 0x24);
  piVar4[9] = 0x60000;
  if ((uint)(iVar9 - iVar6) < 0x60000) {
    iVar6 = *(int *)(iVar5 + 0x54);
  }
  else {
    iVar6 = iVar6 + *(int *)(iVar5 + 0x28);
  }
  piVar4[8] = iVar6 + 7U & 0xfffffff8;
  if (*(int *)(iVar5 + 0x18) != 0) {
    func_0x0018e28c(uRam00155ef4,0,0);
  }
  func_0x00129aa8(uRam00155ef8);
  func_0x000601a4(uRam00155efc);
  iVar6 = FUN_ram_0012989c(iVar5);
  iVar5 = 0;
  if (iVar6 != 0) {
    func_0x00101f2c();
    func_0x00129a64();
    iVar5 = iVar6;
  }
  func_0x000601a4(uRam00155f00);
  return iVar5;
}


// ==== 0x15714c -> FUN_ram_0015714c @ ram:0015714c

int FUN_ram_0015714c(void)

{
  int iVar1;
  int iVar2;
  undefined4 uVar3;
  int iVar4;
  
  iVar1 = func_0x0030715c();
  iVar4 = *(int *)(iVar1 + 0x3dc);
  iVar2 = FUN_ram_00129a1c();
  if ((iVar2 != 0) && (func_0x00101f2c(), iVar4 == 0)) {
    iVar4 = iVar2;
  }
  iVar2 = func_0x000ea5d0();
  if (iVar2 != 0) {
    *(int *)(*(int *)(iVar1 + 0x3d4) + 0x4c) = *(int *)(iVar1 + 0x2c0) + *(int *)(iVar1 + 0x2b8);
    if (iVar4 != 0) {
      *(undefined4 *)(iVar1 + 0x74) = *(undefined4 *)(iVar1 + 0x18);
      *(undefined4 *)(iVar1 + 0x78) = *(undefined4 *)(iVar1 + 0x1c);
      **(undefined1 **)(iVar1 + 0x74) = 0xff;
      *(undefined1 *)(*(int *)(iVar1 + 0x74) + 1) = 0xd9;
      func_0x00077c84(*(int *)(iVar1 + 0x74) + 2,uRam00157324,iVar4,*(undefined4 *)(iVar1 + 0x3d0),
                      *(undefined1 *)(iVar1 + 0x8c),*(undefined4 *)(iVar1 + 0x40),
                      *(undefined4 *)(iVar1 + 0x44),*(undefined4 *)(iVar1 + 0x48),
                      *(undefined4 *)(iVar1 + 0x88),*(undefined4 *)(iVar1 + 0x68),
                      *(undefined4 *)(iVar1 + 0x7c),*(undefined4 *)(iVar1 + 0x80),
                      *(undefined4 *)(iVar1 + 0x84),*(undefined4 *)(iVar1 + 0x2c8),
                      *(undefined4 *)(iVar1 + 0x2cc),*(undefined4 *)(iVar1 + 0x2d0),
                      *(undefined4 *)(iVar1 + 0x2b8),*(undefined4 *)(iVar1 + 700),
                      *(undefined4 *)(iVar1 + 0x2c0),*(undefined4 *)(iVar1 + 0x2c4));
      func_0x000f0120(uRam00157328,0);
      uVar3 = func_0x00301908(*(undefined4 *)(iVar1 + 0x74));
      func_0x001bb420(6,1,*(undefined4 *)(*(int *)(iVar1 + 0x3d4) + 0x48),
                      *(undefined4 *)(iVar1 + 0x74),uVar3);
      func_0x001bb420(6,1,*(undefined4 *)(*(int *)(iVar1 + 0x3d4) + 0x48),
                      *(undefined4 *)(iVar1 + 0x304),*(undefined4 *)(iVar1 + 0x3bc));
      func_0x000f0190(uRam00157328);
    }
  }
  iVar2 = func_0x000e98cc();
  if (iVar2 != 0) {
    func_0x000e98d4(*(undefined4 *)(*(int *)(iVar1 + 0x3d4) + 0x48));
  }
  uVar3 = *(undefined4 *)(*(int *)(iVar1 + 0x3d4) + 0x48);
  iVar1 = (**(code **)(*piRam0015732c + 4))(iVar1);
  if ((iVar1 != 0) && (iVar4 == 0)) {
    iVar4 = iVar1;
  }
  iVar1 = func_0x000ea5d0();
  if (iVar1 != 0) {
    func_0x000f0120(uRam00157328,0);
    iVar1 = func_0x001bb420(6,2,uVar3,0,0);
    if ((iVar1 != 0) && (iVar4 == 0)) {
      iVar4 = iVar1;
    }
    func_0x000f0190(uRam00157328);
  }
  return iVar4;
}


// ==== 0x12aba4 -> FUN_ram_0012aba4 @ ram:0012aba4

int FUN_ram_0012aba4(undefined4 param_1,undefined4 param_2,uint *param_3,undefined1 *param_4)

{
  undefined4 *puVar1;
  int iVar2;
  undefined4 uVar3;
  int iVar4;
  int iVar5;
  uint uVar6;
  uint uVar7;
  undefined1 uVar8;
  undefined8 uVar9;
  int iStack_10;
  int iStack_c;
  
  uVar9 = func_0x00307140();
  uVar3 = (undefined4)((ulonglong)uVar9 >> 0x20);
  iVar4 = 0;
  uVar7 = 0;
  iStack_10 = 0;
  iStack_c = 0;
  uVar6 = 0;
  uVar8 = 0;
  func_0x000f0120(uRam0012ac88,0);
  puVar1 = puRam0012ab9c;
  if (*(char *)(puRam0012ab9c + 6) == '\0') {
    func_0x0004810c(uRam0012ac8c,0x78);
    iVar4 = FUN_ram_0007574c((int)uVar9,&iStack_10,&iStack_c);
    if (iVar4 == 0) {
      uVar7 = func_0x003086f0((iStack_c - puVar1[4]) - puVar1[5],uVar3);
      for (; uVar6 < uVar7; uVar6 = uVar6 + 1 & 0xff) {
        iVar5 = iStack_10 + puVar1[4];
        iVar2 = func_0x003086cc(uVar6,uVar3);
        iVar4 = iRam0012ac90;
        *(int *)(iRam0012ac90 + uVar6 * 0xc + 8) = iVar2 + iVar5;
        iVar4 = func_0x001901d4(*puVar1,iVar4 + uVar6 * 0xc);
        if (iVar4 != 0) break;
      }
      if ((iVar4 == 0) && (uVar7 != 0)) {
        *(undefined1 *)(puVar1 + 6) = 1;
        uVar8 = 1;
        puVar1[8] = 0;
        puVar1[7] = 0;
      }
    }
  }
  if (param_3 != (uint *)0x0) {
    *param_3 = uVar7;
  }
  if (param_4 != (undefined1 *)0x0) {
    *param_4 = uVar8;
  }
  func_0x000f0190(uRam0012ac88);
  return iVar4;
}


// ==== 0x12b3c4 -> FUN_ram_0012b3c4 @ ram:0012b3c4

int FUN_ram_0012b3c4(void)

{
  int *piVar1;
  undefined4 uVar2;
  int iVar3;
  int iVar4;
  int iVar5;
  int iVar6;
  undefined4 uVar7;
  int *piVar8;
  int iVar9;
  int in_mlo;
  undefined8 uVar10;
  undefined4 uStack_28;
  undefined1 auStack_24 [4];
  undefined1 auStack_20 [12];
  int iStack_14;
  undefined4 uStack_10;
  
  uVar10 = func_0x0030714c();
  piVar8 = (int *)((ulonglong)uVar10 >> 0x20);
  iVar6 = (int)uVar10;
  uStack_28 = 0;
  auStack_24[0] = 0;
  uVar2 = func_0x0004b980(0x22);
  func_0x00075778(uVar2,auStack_20);
  if (iVar6 == 0) {
    if (*pbRam0012b568 < 2) {
      *(byte *)(puRam0012b56c + 0xb) = *pbRam0012b568 + 1;
    }
    else {
      *(undefined1 *)(puRam0012b56c + 0xb) = 0;
    }
  }
  if (iVar6 == 0) {
    iVar3 = func_0x000f08b4(&uStack_28,auStack_24);
    iVar4 = 0;
    if ((iVar3 == 0) && (puRam0012b56c[7] == 0)) {
      iVar3 = func_0x0012af1c(*puRam0012b56c,puRam0012b56c + 7);
      if (iVar3 != 0) {
        return iRam0012b570;
      }
      uVar2 = func_0x003086f0(uStack_10,3);
      iVar4 = func_0x003086cc(uVar2,*(undefined1 *)(puRam0012b56c + 0xb));
      puRam0012b56c[9] = 0;
      iVar3 = 0;
      iVar4 = iStack_14 + iVar4;
    }
  }
  else {
    iVar3 = 0;
    *piRam0012b574 = iVar6;
    iVar4 = iVar6;
  }
  iVar5 = func_0x000677bc();
  iVar9 = 0;
  if (((iVar5 == 0x38) || (iVar5 = func_0x000677bc(), iVar5 == 0x39)) &&
     (iVar5 = func_0x0013e340(), iVar5 == 1)) {
    iVar9 = iRam0012b578;
  }
  piVar1 = piRam0012b57c;
  if (iVar6 == 0) {
    if (iVar3 == 0) {
      *piVar8 = iVar4;
      *(int *)(iVar4 + 4) = *(int *)(*piVar1 + 8) + iVar9;
      uVar2 = func_0x0004b980(0x25);
      func_0x00075778(uVar2,auStack_20);
      func_0x0006e0d0();
      *(int *)(*piVar8 + 8) = iStack_14;
      *(undefined4 *)(*piVar8 + 0xc) = 0;
    }
    iVar6 = func_0x000f0944();
    if (iVar6 != 0) {
      func_0x00065d6c(uRam0012b580,0x10);
    }
  }
  else {
    *piVar8 = iVar4;
    iVar6 = iVar4 + 0x5800;
    *(int *)(iVar4 + 4) = iVar6 + iVar9;
    iVar4 = func_0x0006e0d0();
    if (iVar4 == 0) {
      uVar2 = func_0x0004bdf4();
      uVar7 = func_0x0004bdf8();
      Auxregs0104 = 0;
      asm_instruction_05(0xd,uVar7,uVar2);
      iVar4 = in_mlo + 0x3ff;
      if (iVar4 < 0) {
        iVar4 = in_mlo + 0x7fe;
      }
      *(int *)(*piVar8 + 8) = (iVar4 >> 10) * 0x400 + iVar6 + iVar9;
    }
    else {
      uVar2 = func_0x0004bdf4();
      uVar7 = func_0x0004bdf8();
      Auxregs0104 = 0;
      asm_instruction_05(0xd,uVar7,uVar2);
      iVar4 = in_mlo + 0x3ff;
      if (iVar4 < 0) {
        iVar4 = in_mlo + 0x7fe;
      }
      *(int *)(*piVar8 + 8) = (iVar4 >> 10) * 0x800 + iVar6 + iVar9;
    }
    *(undefined4 *)(*piVar8 + 0xc) = 0;
  }
  return iVar3;
}


// ==== 0x12bc04 -> FUN_ram_0012bc04 @ ram:0012bc04

int FUN_ram_0012bc04(void)

{
  undefined4 *puVar1;
  int iVar2;
  int iVar3;
  undefined1 auStack_c [4];
  
  func_0x0030715c();
  puVar1 = puRam0012bba8;
  auStack_c[0] = 0;
  if ((puRam0012bba8[9] == 0) && (puRam0012bba8[8] != 0)) {
    iVar2 = FUN_ram_0012b03c(*puRam0012bba8);
    if (iVar2 == 0) {
      puVar1[8] = 0;
      FUN_ram_00065d48(uRam0012bb04,0x10);
      iVar2 = func_0x000f0908(auStack_c);
    }
  }
  else {
    puRam0012bba8[9] = 0;
    iVar2 = 0;
  }
  iVar3 = func_0x000f094c();
  if (iVar3 != 0) {
    func_0x0012772c(0);
  }
  return iVar2;
}


// ==== 0xf0d14 -> FUN_ram_000f0d14 @ ram:000f0d14

undefined4 FUN_ram_000f0d14(void)

{
  int iVar1;
  undefined1 *puVar2;
  int iVar3;
  int iVar4;
  undefined4 uVar5;
  undefined8 uVar6;
  
  uVar6 = func_0x0030714c();
  puVar2 = puRam000f0e6c;
  iVar1 = iRam000f0cf0;
  iVar3 = (int)uVar6;
  *(undefined2 *)(iRam000f0cf0 + 0x20) = 0;
  *(undefined2 *)(iVar1 + 0x22) = 0;
  *puVar2 = 0;
  func_0x0006d260();
  func_0x0018c784(0);
  func_0x0004dbc0(uRam000f0e70);
  iVar4 = func_0x000677bc();
  if ((iVar4 == 0x38) || (iVar4 = func_0x000677bc(), iVar4 == 0x39)) {
    FUN_ram_0012bc04();
    uVar5 = 0;
  }
  else {
    iVar4 = func_0x00066f30();
    if (iVar4 == 5) {
      FUN_ram_00065d90(uRam000f0e74,0x2000,0,0);
    }
    *(ushort *)(iVar1 + 0x2a) = *(short *)(iVar3 + 0x60) + 0xfU & 0xfff0;
    uVar5 = *(undefined4 *)(iVar3 + 4);
    *(ushort *)(iVar1 + 0x2c) = *(short *)(iVar3 + 0x62) + 0xfU & 0xfff0;
    uVar5 = FUN_ram_000f0e7c((int)((ulonglong)uVar6 >> 0x20),uVar5);
    iVar4 = func_0x000ea6ac();
    if (iVar4 != 0) {
      func_0x000f1408(iVar3,*(undefined4 *)(iVar1 + 0xc),*(undefined2 *)(iVar1 + 0x2a),
                      *(undefined2 *)(iVar1 + 0x2c),0);
    }
    if (*(int *)(iVar1 + 0x24) != 2) {
      while (iVar4 = func_0x000f09e8(), iVar4 != 0) {
        func_0x0011cd14(0x14);
      }
      func_0x0013a858();
      iVar4 = func_0x000dc964();
      if (iVar4 != 0) {
        func_0x000dc620();
      }
      *(undefined2 *)(iVar1 + 4) = 0;
      func_0x000f09cc(1);
      func_0x000f117c(*(undefined4 *)(iVar1 + 0xc),2,*(undefined1 *)(iVar3 + 0x2c),
                      *(char *)(iVar3 + 0x32) == '\0',*(undefined4 *)(iVar1 + 0x14),
                      *(undefined2 *)(iVar1 + 0x2a),*(undefined2 *)(iVar1 + 0x2c),0x280,0x1e0,
                      *(undefined4 *)(iVar1 + 0x10),0x300000);
      if (*(int *)(iVar1 + 0x24) == 1) {
        FUN_ram_0012bc04();
      }
      func_0x000f0fa8();
      func_0x000f09cc(0);
      func_0x0005ef00(0,uRam000f0cf4,0);
      if (*(char *)(iVar3 + 0x32) != '\0') {
        func_0x000f10e8(iVar3);
      }
      func_0x0018c784(1);
    }
    *(undefined1 *)(iVar1 + 2) = 0;
    func_0x000eb9ac();
    func_0x0005c3b8(uRam000f0e78,iVar3,0);
  }
  return uVar5;
}


// ==== 0x76680 -> FUN_ram_00076680 @ ram:00076680

int FUN_ram_00076680(void)

{
  ushort *puVar1;
  undefined4 uVar2;
  int iVar3;
  int iVar4;
  uint uVar5;
  undefined4 in_mlo;
  
  puVar1 = puRam0007674c;
  if ((*puRam0007674c == 0) || (puRam0007674c[1] == 0)) {
    func_0x000dae9c(puRam0007674c,puRam0007674c + 1);
  }
  uVar2 = func_0x000e43f0();
  switch(uVar2) {
  default:
    uVar2 = 8;
    break;
  case 1:
  case 3:
  case 5:
    uVar2 = 0x10;
    break;
  case 2:
    uVar2 = 10;
    break;
  case 4:
    uVar2 = 0xc;
  }
  uVar5 = (uint)*puVar1;
  Auxregs0104 = 0;
  asm_instruction_05(0xd,(uint)puVar1[1],uVar5);
  Auxregs0114 = in_mlo;
  iVar3 = func_0x003086cc(in_mlo,uVar2,uVar5);
  iVar4 = iVar3 + 7;
  if (iVar4 < 0) {
    iVar4 = iVar3 + 0xe;
  }
  return iVar4 >> 3;
}

