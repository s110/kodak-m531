// Fuente: work/code_only.bin, sha256 9e4c35fe181e2c8397ee7516f5776be494cf1c32c6a775c8a6899a821ad3f69a; Ghidra 12.1.4 ARCompact, base 0, -noanalysis; tools/ghidra_scripts/Decomp.java

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


// ==== 0x17ba40 -> FUN_ram_0017ba40 @ ram:0017ba40

void FUN_ram_0017ba40(undefined4 param_1,undefined4 param_2,int param_3)

{
  undefined2 uVar1;
  undefined2 uVar2;
  undefined4 uVar3;
  undefined2 extraout_r1;
  undefined2 uStack_1c;
  undefined2 uStack_1a;
  undefined2 uStack_18;
  undefined4 uStack_14;
  undefined4 uStack_10;
  undefined2 uStack_c;
  undefined1 auStack_a [2];
  
  uVar1 = func_0x0030715c();
  func_0x000e14b4(&uStack_1c);
  func_0x000e1178(&uStack_14);
  func_0x0005e11c(&uStack_c,auStack_a);
  uVar2 = func_0x0005dcd8();
  *(undefined2 *)(param_3 + 0x204) = uVar2;
  uVar2 = func_0x0005dbd0();
  *(undefined2 *)(param_3 + 0x206) = uVar2;
  uVar2 = func_0x0005dc98();
  *(undefined2 *)(param_3 + 0x208) = uVar2;
  *(undefined2 *)(param_3 + 0x20a) = uStack_c;
  uVar2 = func_0x0005e558();
  *(undefined2 *)(param_3 + 0x20c) = uVar2;
  uVar2 = func_0x0005e55c();
  *(undefined2 *)(param_3 + 0x212) = uVar2;
  *(undefined2 *)(param_3 + 0x20e) = 1;
  *(undefined2 *)(param_3 + 0x210) = 9;
  *(undefined2 *)(param_3 + 0x214) = 1;
  uVar2 = func_0x0005e560();
  *(undefined2 *)(param_3 + 0x216) = uVar2;
  uVar2 = func_0x000daddc();
  *(undefined2 *)(param_3 + 0x218) = uVar2;
  uVar2 = func_0x00076750();
  *(undefined2 *)(param_3 + 0x21a) = uVar2;
  uVar3 = func_0x000e4348();
  *(undefined4 *)(param_3 + 0x21c) = uVar3;
  *(undefined2 *)(param_3 + 0x220) = extraout_r1;
  *(undefined2 *)(param_3 + 0x224) = uVar1;
  uVar1 = func_0x000e10cc();
  *(undefined2 *)(param_3 + 0x226) = uVar1;
  *(undefined4 *)(param_3 + 0x228) = uStack_14;
  *(undefined4 *)(param_3 + 0x22c) = uStack_10;
  uVar1 = func_0x000e155c();
  *(undefined2 *)(param_3 + 0x236) = uVar1;
  *(undefined2 *)(param_3 + 0x230) = uStack_1c;
  *(undefined2 *)(param_3 + 0x232) = uStack_1a;
  *(undefined2 *)(param_3 + 0x234) = uStack_18;
  return;
}


