// Fuente: work/code_only.bin = dump/ram_snapshot.bin[0:0x500000], sha256 9e4c35fe181e2c8397ee7516f5776be494cf1c32c6a775c8a6899a821ad3f69a
// Ghidra 12.1.4 + ARCompact:LE:32:default (niooss-ledger d3fbf109), BinaryLoader, base 0, -noanalysis
// Script: tools/ghidra_scripts/Decomp.java. Es salida del decompilador, no prueba: ver NOTAS.md (p. ej. nargs 3/4 de Run_SpecifyFunc).

// ==== 0x2da0c4 -> FUN_ram_002da0c4 @ ram:002da0c4

undefined4
FUN_ram_002da0c4(undefined4 param_1,undefined4 param_2,int param_3,undefined4 *param_4,
                undefined4 *param_5,undefined4 *param_6,undefined4 *param_7,undefined4 *param_8)

{
  code *pcVar1;
  int iVar2;
  undefined4 *puVar3;
  undefined8 uVar4;
  undefined4 *in_stack_00000024;
  undefined4 uStack_c;
  
  uVar4 = func_0x00307144();
  iVar2 = (int)((ulonglong)uVar4 >> 0x20);
  pcVar1 = (code *)uVar4;
  if (iVar2 < param_3) {
    uStack_c = 0;
  }
  else {
    switch(iVar2) {
    case 0:
      *puRam002da314 = pcVar1;
      uStack_c = (*pcVar1)();
      break;
    case 1:
      if (param_3 == 0) {
        *puRam002da314 = pcVar1;
        uStack_c = (*pcVar1)(param_4);
      }
      else {
        *puRam002da314 = pcVar1;
        (*pcVar1)(&uStack_c);
      }
      break;
    case 2:
      if (param_3 == 0) {
        *puRam002da314 = pcVar1;
        uStack_c = (*pcVar1)(param_4,param_5);
      }
      else {
        puVar3 = &uStack_c;
        if (param_3 == 1) {
          *puRam002da314 = pcVar1;
          param_4 = puVar3;
          puVar3 = param_5;
        }
        else {
          *puRam002da314 = pcVar1;
        }
        (*pcVar1)(param_4,puVar3);
      }
      break;
    case 3:
      if (param_3 == 0) {
        *puRam002da314 = pcVar1;
        uStack_c = (*pcVar1)(param_4,param_5);
      }
      else {
        if (param_3 == 1) {
          *puRam002da314 = pcVar1;
          param_4 = &uStack_c;
        }
        else if (param_3 == 2) {
          *puRam002da314 = pcVar1;
          param_5 = &uStack_c;
        }
        else {
          *puRam002da314 = pcVar1;
          param_6 = &uStack_c;
        }
        (*pcVar1)(param_4,param_5,param_6);
      }
      break;
    case 4:
      if (param_3 == 0) {
        *puRam002da314 = pcVar1;
        uStack_c = (*pcVar1)(param_4,param_5);
      }
      else {
        if (param_3 == 1) {
          *puRam002da314 = pcVar1;
          param_4 = &uStack_c;
        }
        else if (param_3 == 2) {
          *puRam002da314 = pcVar1;
          param_5 = &uStack_c;
        }
        else if (param_3 == 3) {
          *puRam002da314 = pcVar1;
          param_6 = &uStack_c;
        }
        else {
          *puRam002da314 = pcVar1;
          param_7 = &uStack_c;
        }
        (*pcVar1)(param_4,param_5,param_6,param_7);
      }
      break;
    case 5:
      if (param_3 == 0) {
        *puRam002da314 = pcVar1;
        uStack_c = (*pcVar1)(param_4,param_5,param_6,param_7,param_8);
      }
      else {
        if (param_3 == 1) {
          *puRam002da314 = pcVar1;
          param_4 = &uStack_c;
        }
        else if (param_3 == 2) {
          *puRam002da314 = pcVar1;
          param_5 = &uStack_c;
        }
        else if (param_3 == 3) {
          *puRam002da314 = pcVar1;
          param_6 = &uStack_c;
        }
        else if (param_3 == 4) {
          *puRam002da314 = pcVar1;
          param_7 = &uStack_c;
        }
        else {
          *puRam002da314 = pcVar1;
          param_8 = &uStack_c;
        }
        (*pcVar1)(param_4,param_5,param_6,param_7,param_8);
      }
      break;
    case 6:
      if (param_3 == 0) {
        *puRam002da314 = pcVar1;
        uStack_c = (*pcVar1)(param_4,param_5,param_6,param_7,param_8,in_stack_00000024);
      }
      else {
        if (param_3 == 1) {
          *puRam002da314 = pcVar1;
          param_4 = &uStack_c;
        }
        else if (param_3 == 2) {
          *puRam002da314 = pcVar1;
          param_5 = &uStack_c;
        }
        else if (param_3 == 3) {
          *puRam002da314 = pcVar1;
          param_6 = &uStack_c;
        }
        else if (param_3 == 4) {
          *puRam002da314 = pcVar1;
          param_7 = &uStack_c;
        }
        else if (param_3 == 5) {
          *puRam002da314 = pcVar1;
          param_8 = &uStack_c;
        }
        else {
          *puRam002da314 = pcVar1;
          in_stack_00000024 = &uStack_c;
        }
        (*pcVar1)(param_4,param_5,param_6,param_7,param_8,in_stack_00000024);
      }
      break;
    default:
      uStack_c = 0;
    }
  }
  return uStack_c;
}


// ==== 0x1fdff4 -> FUN_ram_001fdff4 @ ram:001fdff4

void FUN_ram_001fdff4(undefined4 param_1,undefined4 param_2,int param_3)

{
  undefined4 uVar1;
  byte bVar2;
  bool bVar3;
  undefined1 auStack_1c [4];
  short sStack_18;
  
  func_0x00307154();
  if (param_3 != 4) {
    func_0x0006c17c(auStack_1c);
    bVar3 = sStack_18 == 0;
    if (bVar3) {
      func_0x00067a74(1);
      func_0x000f0538(0,0,0x1e0,0xf0,0xffffffff,0,0);
      uVar1 = uRam001fe110;
      if ((param_3 == 5) || (uVar1 = uRam001fe114, param_3 == 0xffff)) {
        func_0x000e2c00(0x1e,0x5a,uVar1);
      }
      else {
        func_0x000e2c00(0x1e,0x5a,uRam001fe118,param_3);
      }
      func_0x00067e6c();
    }
    func_0x0005ec50();
    func_0x0005ec1c();
    func_0x0005ec84();
    func_0x0005e8a4(0xdb);
    if (bVar3) {
      func_0x000debf8(uRam001fe11c);
    }
    func_0x00075370();
    if (bVar3) {
      func_0x000debf8(uRam001fe120);
    }
    return;
  }
  func_0x00067a74(1);
  func_0x000f0538(0,0,0x1e0,0xf0,0xffffffff,0,0);
  func_0x00067e6c();
  bVar2 = 0;
  do {
    if ((bVar2 & 1) == 0) {
      func_0x0011e170(0x1a4,0xd2,4);
    }
    else {
      func_0x000f0538(0,0,0x1e0,0xf0,0xffffffff,0,0);
    }
    func_0x000d7e2c();
    func_0x000debf8(uRam001fe10c);
    bVar2 = bVar2 + 1;
  } while (bVar2 < 10);
  func_0x00075370();
  do {
                    /* WARNING: Do nothing block with infinite loop */
  } while( true );
}


// ==== 0x2bee0c -> FUN_ram_002bee0c @ ram:002bee0c

undefined4 FUN_ram_002bee0c(void)

{
  undefined4 uVar1;
  undefined4 uVar2;
  int iVar3;
  undefined4 uStack_10;
  uint uStack_c;
  
  uVar1 = func_0x00307160();
  uVar2 = func_0x0004b980(6);
  iVar3 = func_0x0007574c(uVar2,&uStack_10,&uStack_c);
  if (iVar3 == 0) {
    if (uStack_c < 0x20000) {
      func_0x0004b980(6);
      func_0x00075768();
      uVar1 = 0;
    }
    else {
      func_0x0019a008(uStack_10,0x20000);
      iVar3 = func_0x00053e44(uVar1);
      if (iVar3 == 0) {
        func_0x0004b980(6);
        func_0x00075768();
        uVar1 = 0;
      }
      else {
        uVar1 = 1;
      }
    }
  }
  else {
    uVar1 = 0;
  }
  return uVar1;
}


// ==== 0x53e44 -> FUN_ram_00053e44 @ ram:00053e44

undefined4 FUN_ram_00053e44(undefined4 param_1)

{
  undefined1 *puVar1;
  undefined4 uVar2;
  int iVar3;
  int iVar4;
  undefined1 auStack_110 [260];
  undefined1 auStack_c [4];
  undefined1 auStack_8 [8];
  
  func_0x0030715c(param_1,param_1);
  func_0x00301968(auStack_110);
  iVar3 = func_0x00106084(auStack_110);
  iVar4 = iRam000541a0;
  if (iVar3 == 0) {
    func_0x00301994(auStack_110,iRam000541a0);
    func_0x00301994(auStack_110,iVar4 + 8);
    iVar4 = func_0x00106178(auStack_110,0x11,auStack_8);
    if (iVar4 == 0) {
      func_0x001062e0(auStack_8);
      uVar2 = uRam000541a8;
      puVar1 = puRam000541a4;
      puRam000541a4[1] = 1;
      iVar4 = func_0x000f14b0(uVar2,0,auStack_c);
      if (iVar4 == 0) {
        *puVar1 = 1;
        return 1;
      }
      return 0;
    }
  }
  return 0;
}


// ==== 0x10710c -> FUN_ram_0010710c @ ram:0010710c

void FUN_ram_0010710c(void)

{
  undefined1 *puVar1;
  char *pcVar2;
  int iVar3;
  undefined4 uVar4;
  int iVar5;
  char *pcVar6;
  undefined4 uVar7;
  undefined8 uVar8;
  
  uVar8 = func_0x00307150();
  pcVar6 = (char *)((ulonglong)uVar8 >> 0x20);
  uVar7 = (undefined4)uVar8;
  if (*pcVar6 != '\0') {
    puVar1 = (undefined1 *)func_0x00199680();
    pcVar2 = (char *)func_0x00199670();
    iVar5 = iRam00107478;
    iVar3 = func_0x00199694(pcVar6,iRam00107478);
    if (iVar3 == 0) {
      *puVar1 = 0;
      func_0x00199a04(pcVar6,pcVar2,0xfa);
    }
    else {
      uVar4 = func_0x00199670();
      func_0x001999c4(pcVar6,iVar5 + 2,uVar4,0xfa,0);
      func_0x00199a04(uVar4,puVar1,0x32);
      func_0x001999e4(pcVar6,iVar5 + 4,uVar4,0xfa,0);
      func_0x00199a04(uVar4,pcVar2,0xfa);
      func_0x00199650(uVar4);
    }
    if (*pcVar2 == '\0') {
      func_0x00198adc(iVar5 + 0x1f);
    }
    else {
      iVar3 = func_0x001996d0(uVar7,iVar5 + 6);
      if (iVar3 == 0) {
        uVar7 = 0x46;
      }
      else {
        iVar3 = func_0x001996d0(uVar7,iVar5 + 0xe);
        if (iVar3 == 0) {
          uVar7 = 0x53;
        }
        else {
          iVar5 = func_0x001996d0(uVar7,iVar5 + 0x15);
          if (iVar5 == 0) {
            uVar7 = 0x44;
          }
          else {
            uVar7 = 0x41;
          }
        }
      }
      func_0x00199b48(pcVar2,puVar1,uVar7);
    }
    func_0x00199650(pcVar2);
    func_0x00199660(puVar1);
  }
  return;
}


// ==== 0x1b066c -> FUN_ram_001b066c @ ram:001b066c

undefined8
FUN_ram_001b066c(undefined4 param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4,
                undefined1 param_5)

{
  int iVar1;
  undefined4 uVar2;
  int iVar3;
  undefined8 uVar4;
  undefined1 auStack_95 [5];
  undefined4 uStack_90;
  undefined1 auStack_8c [128];
  undefined4 uStack_c;
  
  uVar4 = func_0x00307150();
  uVar2 = (undefined4)((ulonglong)uVar4 >> 0x20);
  uStack_c = 0;
  iVar3 = 1;
  if ((int)uVar4 == 0) {
    func_0x000e8328(uVar2,auStack_8c);
    iVar3 = func_0x00301908(auStack_8c);
    auStack_95[iVar3] = param_5;
  }
  else {
    iVar1 = iRam001b0750;
    if ((int)uVar4 != 1) goto code_r0x001b0742;
    func_0x000e8328(uVar2,auStack_8c);
    iVar3 = func_0x00301908(auStack_8c);
    auStack_95[iVar3] = 0x62;
  }
  auStack_8c[iVar3 + -3] = 0x72;
  auStack_8c[iVar3 + -2] = 0x61;
  auStack_8c[iVar3 + -1] = 0x77;
  iVar3 = func_0x000e0d2c(auStack_8c,1,1,&uStack_90);
  iVar1 = iVar3;
  if (((iVar3 == 0) &&
      (iVar3 = func_0x000e0dd0(uStack_90,param_3,param_4,0,&uStack_c), iVar1 = iVar3, iVar3 == 0))
     && (iVar3 = func_0x000e0df0(&uStack_90), iVar1 = iVar3, iVar3 == 0)) {
    iVar1 = 0;
  }
code_r0x001b0742:
  return CONCAT44(iVar3,iVar1);
}


// ==== 0x127150 -> FUN_ram_00127150 @ ram:00127150

int FUN_ram_00127150(void)

{
  int iVar1;
  undefined4 uVar2;
  undefined4 uVar3;
  int unaff_r13;
  int *unaff_r14;
  int unaff_r15;
  
  func_0x0004b980();
  func_0x00075768();
  iVar1 = func_0x000677bc();
  if ((iVar1 != 0x38) && (iVar1 = func_0x000677bc(), iVar1 != 0x39)) {
    iVar1 = func_0x001b0648();
    if (iVar1 == 1) {
      uVar2 = func_0x0004bdf4();
      uVar3 = func_0x0004bdf8();
      func_0x001b0754(*(undefined4 *)(*unaff_r14 + 4),0,uVar2,uVar3,2);
    }
    if ((*pcRam00127270 == '\x01') &&
       (iVar1 = func_0x00128b9c(*unaff_r14), unaff_r13 = 0, iVar1 != 0)) {
      return iVar1;
    }
  }
  *puRam00127274 = 1;
  if ((unaff_r15 != 4) || (unaff_r13 = func_0x00052558(uRam00127278,*unaff_r14), unaff_r13 == 0)) {
    iVar1 = func_0x00081d64();
    func_0x00081d70(iVar1 + 1);
    iVar1 = func_0x001b0648();
    if ((iVar1 != 0) && (*(int *)(*unaff_r14 + 4) != 0)) {
      uVar2 = func_0x00076680();
      FUN_ram_001b066c(0,*(undefined4 *)(*unaff_r14 + 0x48),*(undefined4 *)(*unaff_r14 + 4),uVar2,
                       0x4f);
    }
    iVar1 = func_0x001b0648();
    if ((iVar1 != 0) && (*(int *)(*unaff_r14 + 0xc) != 0)) {
      uVar2 = func_0x00076680();
      FUN_ram_001b066c(1,*(undefined4 *)(*unaff_r14 + 0x48),*(undefined4 *)(*unaff_r14 + 0xc),uVar2,
                       0x6f);
    }
    iVar1 = func_0x00127720();
    if (iVar1 != 0) {
      iVar1 = func_0x0012b584();
      if (iVar1 != 0) {
        return iVar1;
      }
      iVar1 = *unaff_r14;
      if (*(int *)(iVar1 + 4) != *(int *)(iRam00127260 + 4)) {
        return iRam0012727c;
      }
      if (*(int *)(iVar1 + 8) != *(int *)(iRam00127260 + 8)) {
        return iRam0012727c;
      }
      func_0x00048120(iVar1,iRam00127260,0x5800);
      unaff_r13 = 0;
    }
    func_0x0012b6c8();
  }
  return unaff_r13;
}


