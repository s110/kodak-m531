// Fuente: work/code_only.bin = dump/ram_snapshot.bin[0:0x500000], sha256 9e4c35fe181e2c8397ee7516f5776be494cf1c32c6a775c8a6899a821ad3f69a
// Ghidra 12.1.4 + ARCompact:LE:32:default (niooss-ledger d3fbf109), BinaryLoader, base 0, -noanalysis
// Script: tools/ghidra_scripts/Decomp.java. Es salida del decompilador, no prueba: ver NOTAS.md.

// ==== 0x17b1c4 -> FUN_ram_0017b1c4 @ ram:0017b1c4

void FUN_ram_0017b1c4(undefined4 param_1,undefined4 param_2,int param_3)

{
  undefined4 uVar1;
  undefined8 uVar2;
  undefined1 auStack_1c [4];
  undefined2 uStack_18;
  undefined2 uStack_16;
  undefined2 uStack_14;
  undefined2 uStack_12;
  
  uVar2 = func_0x00307158();
  func_0x0006c17c(auStack_1c);
  *(undefined4 *)(param_3 + 0x20) = 0xd6;
  *(undefined2 *)(param_3 + 0x34) = uStack_18;
  *(undefined2 *)(param_3 + 0x36) = uStack_16;
  *(undefined2 *)(param_3 + 0x38) = uStack_14;
  *(undefined2 *)(param_3 + 0x3a) = uStack_12;
  func_0x00151830(param_3 + 0x3c,param_3 + 0x3e);
  uVar1 = func_0x00080fd0();
  func_0x00301920(param_3 + 0x40,uVar1,0x28);
  uVar1 = uRam0017b2dc;
  *(undefined4 *)(param_3 + 0x68) = 0x5000;
  func_0x0017b988(param_3,uVar1);
  func_0x0017b9f0(param_3 + 0x24);
  func_0x0017bb6c(param_3 + 0x12d0);
  func_0x0017bef0(param_3 + 0x4988);
  func_0x0017ba40((int)uVar2,(int)((ulonglong)uVar2 >> 0x20),param_3 + 0x466c);
  func_0x0017b9bc(param_3 + 0x4fe8,uRam0017b2e0);
  func_0x0017b988(param_3 + 0x4b2c,uRam0017b2e4);
  func_0x0017b9bc(param_3 + 0x4e78,uRam0017b2e8);
  *(undefined1 **)(param_3 + 0x4b4c) = &BTA_LINK_BUILD;
  *(undefined2 *)(param_3 + 0x4b4e) = 0x2c;
  *(undefined2 *)(param_3 + 0x4b50) = 0x100;
  *(undefined2 *)(param_3 + 0x4b52) = 0x14;
  *(undefined2 *)(param_3 + 0x4b54) = 0x48;
  *(undefined2 *)(param_3 + 0x4b56) = 0xc;
  return;
}


// ==== 0x17b9f0 -> FUN_ram_0017b9f0 @ ram:0017b9f0

void FUN_ram_0017b9f0(void)

{
  byte bVar1;
  undefined4 uVar2;
  undefined1 auStack_18 [16];
  
  uVar2 = func_0x0030715c();
  func_0x00077cc0(auStack_18,uRam0017ba3c,9);
  bVar1 = func_0x00301908(auStack_18);
  if (0x10 < bVar1) {
    bVar1 = 0x18;
  }
  func_0x00301920(uVar2,auStack_18,bVar1);
  func_0x0017b92c(uVar2,bVar1);
  return;
}


// ==== 0x17bb6c -> FUN_ram_0017bb6c @ ram:0017bb6c

void FUN_ram_0017bb6c(void)

{
  short *psVar1;
  undefined2 uVar2;
  int iVar3;
  undefined1 *puVar4;
  int iVar5;
  int iVar6;
  int iVar7;
  int iVar8;
  short sVar9;
  undefined1 auStack_208 [2];
  short sStack_206;
  short sStack_204;
  short asStack_202 [10];
  undefined2 auStack_1ee [10];
  undefined2 auStack_1da [105];
  undefined1 auStack_108 [2];
  short sStack_106;
  short sStack_104;
  short asStack_102 [125];
  
  puVar4 = (undefined1 *)func_0x00307148();
  iVar5 = func_0x0005e558();
  iVar6 = func_0x0005e55c();
  iVar7 = func_0x0006c55c(auStack_208);
  if (iVar7 == 0) {
    sVar9 = 0;
    iVar7 = 0;
    if (0 < iVar6) {
      do {
        iVar8 = 0;
        if (0 < iVar5) {
          do {
            iVar3 = iVar8 * 10;
            iVar8 = iVar8 + 1;
            sVar9 = sVar9 + asStack_202[iVar7 + iVar3];
          } while (iVar8 < iVar5);
        }
        iVar7 = iVar7 + 1;
      } while (iVar7 < iVar6);
    }
    if (((sStack_206 == 0) || (sVar9 != sStack_204)) || (sStack_204 == -999)) {
      *puVar4 = 0;
    }
    else {
      *puVar4 = 1;
      *(short *)(puVar4 + 2) = (short)iVar6;
      *(short *)(puVar4 + 4) = (short)iVar5;
      iVar7 = 0;
      if (0 < iVar6) {
        do {
          *(undefined2 *)(puVar4 + iVar7 * 2 + 6) = auStack_1ee[iVar7];
          uVar2 = auStack_1da[iVar7];
          iVar8 = iVar7 + 1;
          *(short *)(puVar4 + (iVar6 + iVar7) * 2 + 6) = asStack_202[iVar7];
          puVar4[iVar7 + 0x106] = (char)uVar2;
          iVar7 = iVar8;
        } while (iVar8 < iVar6);
      }
    }
  }
  else {
    *puVar4 = 0xff;
  }
  iVar6 = func_0x0006c5d8(auStack_108);
  if (iVar6 == 0) {
    sVar9 = 0;
    iVar6 = 0;
    if (0 < iVar5) {
      do {
        psVar1 = asStack_102 + iVar6;
        iVar6 = iVar6 + 1;
        sVar9 = sVar9 - *psVar1;
      } while (iVar6 < iVar5);
    }
    if (((sStack_106 == 0) || (sVar9 != sStack_104)) || (sStack_104 == -0xbc2)) {
      puVar4[0x186] = 0;
    }
    else {
      puVar4[0x186] = 1;
      *(short *)(puVar4 + 0x188) = (short)iVar5;
      *(short *)(puVar4 + 0x18a) = -asStack_102[1];
      *(short *)(puVar4 + 0x18c) = -asStack_102[0];
    }
  }
  else {
    puVar4[0x186] = 0xff;
  }
  func_0x0017bf60(puVar4 + 0x3d8);
  func_0x0017bf8c(puVar4 + 0x3de);
  func_0x0017bda4(puVar4 + 0x3e4);
  func_0x0017bff8(puVar4 + 0x1ac);
  func_0x0017bd38(puVar4 + 0x414);
  func_0x0017bfb0(puVar4 + 0x5cc);
  func_0x0017bd54(puVar4 + 0x5dc);
  return;
}


// ==== 0x17bef0 -> FUN_ram_0017bef0 @ ram:0017bef0

void FUN_ram_0017bef0(void)

{
  int iVar1;
  undefined1 uVar2;
  undefined1 *puVar3;
  uint uVar4;
  int iVar5;
  
  puVar3 = (undefined1 *)func_0x0030715c();
  iVar1 = iRam0017bf58;
  func_0x00151ab4(iRam0017bf58 + -0x6c);
  func_0x00151b14(iRam0017bf5c);
  uVar4 = func_0x0005dbd0();
  if (0 < (int)uVar4) {
    uVar4 = uVar4 - 1 & 0xffff;
  }
  uVar2 = func_0x00151b30();
  *puVar3 = uVar2;
  uVar2 = func_0x00151bb0();
  iVar5 = iRam0017bf5c;
  puVar3[1] = uVar2;
  iVar5 = uVar4 + iVar5;
  puVar3[2] = *(undefined1 *)(iVar5 + 0x24);
  puVar3[3] = *(undefined1 *)(iVar5 + 0x48);
  puVar3[4] = *(undefined1 *)(iVar5 + 0x3c);
  puVar3[0xc] = *(undefined1 *)(iVar1 + -0x48);
  puVar3[0xd] = *(undefined1 *)(iVar1 + -0x47);
  puVar3[0xe] = *(undefined1 *)(iVar1 + -0x42);
  return;
}


