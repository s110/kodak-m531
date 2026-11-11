// Fuente: work/code_only.bin = dump/ram_snapshot.bin[0:0x500000], sha256 9e4c35fe181e2c8397ee7516f5776be494cf1c32c6a775c8a6899a821ad3f69a
// Ghidra 12.1.4 + ARCompact:LE:32:default (niooss-ledger d3fbf109), BinaryLoader, base 0, -noanalysis
// Script: tools/ghidra_scripts/Decomp.java. Es salida del decompilador, no prueba: ver NOTAS.md (p. ej. nargs 3/4 de Run_SpecifyFunc).

// ==== 0x1fe124 -> FUN_ram_001fe124 @ ram:001fe124

void FUN_ram_001fe124(void)

{
  undefined1 uVar1;
  undefined4 uVar2;
  int iVar3;
  undefined4 uVar4;
  undefined4 uVar5;
  
  uVar2 = func_0x00307154();
  uVar5 = 0;
  *puRam001fe30c = 1;
  func_0x0006d074();
  iVar3 = func_0x000680a4();
  if ((iVar3 == 0) && (iVar3 = func_0x0006c974(0), iVar3 != 0)) {
    iVar3 = func_0x0011c534();
    if ((iVar3 != 0) && (iVar3 = func_0x0006a6c8(), iVar3 == 1)) {
      func_0x0011b7d4(0,1);
      func_0x0011b6a4();
    }
    func_0x000cefd4();
  }
  func_0x0011c490(uRam001fe310);
  iVar3 = func_0x00107c98(0,uRam001fe314,1);
  if (iVar3 == 0) {
    iVar3 = func_0x0011d95c(uVar2);
    if (iVar3 != 0) {
      uVar1 = func_0x0006abd4();
      func_0x000759ec(uVar1);
      func_0x0011d638();
      goto code_r0x001fe18c;
    }
    iVar3 = func_0x000681f0();
    if (iVar3 == 0) {
      iVar3 = func_0x00068214();
      if (iVar3 != 0) {
        func_0x0011da08();
      }
    }
    else {
      uVar4 = func_0x000e1c1c(1);
      func_0x0005ed84(uVar4,0x4002,0x17);
    }
    iVar3 = FUN_ram_002bee0c(uRam001fe31c);
    if (iVar3 == 1) {
      func_0x00065d90(uRam001fe318,8,0,2000);
      iVar3 = func_0x001fe4a8();
      if ((iVar3 == 0) && (iVar3 = func_0x001fe4f4(), iVar3 == 0)) {
        func_0x001080d8(0);
        func_0x001394d8(0);
      }
      func_0x0005c22c();
    }
    iVar3 = func_0x000680a4();
    if ((iVar3 == 0) &&
       ((iVar3 = func_0x000663d0(), iVar3 != 0 ||
        (iVar3 = func_0x00107c30(0,0x3180,0x3180), iVar3 != 0)))) {
      func_0x00065d90(uRam001fe318,8,0,2000);
      func_0x0006821c(0x83);
      func_0x00066390(0);
      iVar3 = func_0x000663d0();
      if (iVar3 != 0) {
        uVar5 = 0x200;
      }
      func_0x001a4570(uVar2,uRam001fe320,uVar5);
    }
    else {
      func_0x0011d090(0);
      iVar3 = func_0x0006c214();
      if ((iVar3 == 3) ||
         ((iVar3 = func_0x0006c214(), iVar3 == 2 &&
          (iVar3 = func_0x0006a59c(uRam001fe324), iVar3 != 0)))) {
        func_0x000e1f5c(0xe6,0);
      }
      else {
        uVar5 = func_0x0006615c(0x61);
        func_0x001a4570(uVar2,uRam001fe328,uVar5);
      }
      func_0x0011d090(1);
      func_0x00066390(0);
    }
  }
  else {
code_r0x001fe18c:
    func_0x00065d90(uRam001fe318,8,0,2000);
  }
  iVar3 = func_0x00107c30(0,uRam001fe32c,uRam001fe32c);
  if (iVar3 == 0) {
    iVar3 = func_0x0006615c(0x65);
    if (iVar3 == 0) {
      iVar3 = func_0x00067e00();
      if (iVar3 != 1) goto code_r0x001fe2f2;
      uVar2 = func_0x0006615c(0x65);
    }
    else {
      iVar3 = func_0x00067e00();
      if (iVar3 != 0) goto code_r0x001fe2f2;
      uVar2 = func_0x0006615c(0x65);
    }
    func_0x0005ef40(0,uRam001fe32c,uVar2);
  }
code_r0x001fe2f2:
  func_0x0007a9c4(0);
  iVar3 = func_0x0006615c(0xc);
  if (iVar3 == 0) {
    func_0x0005e618();
  }
  return;
}


// ==== 0x1fd950 -> FUN_ram_001fd950 @ ram:001fd950

void FUN_ram_001fd950(undefined4 param_1,undefined4 param_2,undefined4 param_3)

{
  int iVar1;
  int iVar2;
  undefined8 uVar3;
  
  uVar3 = func_0x0030715c();
  iVar2 = (int)((ulonglong)uVar3 >> 0x20);
  if (*(char *)(iRam001fd9c0 + 10) == '\0') {
    if ((iVar2 == 0x100) || (iVar1 = func_0x0006615c(2), iVar1 != 0)) {
      func_0x00066390(1);
    }
  }
  else if (((iVar2 == 0x3301) || (iVar2 == 0x4004)) || (iVar2 == 0x3181)) {
    func_0x001a4570((int)uVar3,iVar2,param_3);
    return;
  }
  func_0x0005ef58(uRam001fd9c4,uRam001fd9c8,(int)uVar3,iVar2,param_3);
  return;
}


// ==== 0x2d6644 -> FUN_ram_002d6644 @ ram:002d6644

int FUN_ram_002d6644(short param_1,short param_2,undefined4 param_3)

{
  int iVar1;
  undefined4 uVar2;
  undefined8 uVar3;
  undefined1 auStack_84 [132];
  
  uVar2 = uRam002d6654;
  func_0x00308cd8((int)param_1,(int)param_2,uRam002d6654,param_3);
  uVar3 = func_0x00307154();
  func_0x000d7748(0);
  iVar1 = func_0x0017ceec(auStack_84,uVar2,&stack0x00000020);
  if (iVar1 < 1) {
    iVar1 = 0x400001;
  }
  else {
    iVar1 = func_0x000e2afc((int)uVar3,(int)((ulonglong)uVar3 >> 0x20),auStack_84,1);
    if (iVar1 == 0) {
      iVar1 = func_0x000d53f8();
      if (((iVar1 != 1) && (iVar1 = func_0x000d53f8(), iVar1 != 2)) &&
         (iVar1 = func_0x000d53f8(), iVar1 != 3)) {
        func_0x000d7e2c();
      }
      iVar1 = 0;
    }
  }
  return iVar1;
}


// ==== 0x107e3c -> FUN_ram_00107e3c @ ram:00107e3c

void FUN_ram_00107e3c(int param_1,undefined2 param_2,int param_3,int *param_4)

{
  ushort uVar1;
  int unaff_r13;
  int unaff_r16;
  int unaff_r17;
  int unaff_r18;
  
  do {
    *(undefined2 *)(param_4 + 1) = param_2;
    do {
      uVar1 = (ushort)(param_1 + 1 >> 0x16);
      param_1 = (int)(short)(((short)(param_1 + 1) + (uVar1 >> 9) & 0x7f) - (uVar1 >> 9));
      if (param_1 == param_3) {
        func_0x00107d00();
        if (unaff_r18 == 0) {
          func_0x000f0190(uRam00107dec);
        }
        return;
      }
      param_4 = (int *)(param_1 * 0xc + iRam00107df0);
    } while ((((unaff_r13 != 0) && (unaff_r13 != *param_4)) || ((short)param_4[1] != unaff_r16)) ||
            (param_4[2] != unaff_r17));
    param_2 = 0;
  } while( true );
}


