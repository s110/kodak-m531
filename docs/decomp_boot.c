// Cargador de arranque de la M531, imagen residente en RAM 0x800000-0x82cff0 (sum32 = 0xbbb66ba4, igual a la
// cabecera de la partición 0). Ghidra 12.1.4 + ARCompact, -noanalysis, tools/ghidra_scripts/Decomp.java sobre
// work/boot_ram_0x800000.bin (base 0x800000, sha256 3ebb9672…10f6 = dump/ram_snapshot.bin[0x800000:0x860000]). Salida sin editar; los nombres FUN_/func_ son de Ghidra.
// 0x800df8 BootTask, 0x800f58 arranque desde NAND, 0x800ee0 carga de un registro (NAND), 0x801100 carga desde
// archivo, 0x801060 carga de un registro (archivo), 0x80011c inicio del boot (tecla -> SD primero),
// 0x800434/0x805830 SD presente, 0x8003cc parpadeo de error, 0x807890 lectura de la partición 6.

// ==== 0x800df8 -> FUN_ram_00800df8 @ ram:00800df8

void FUN_ram_00800df8(void)

{
  int *piVar1;
  int iVar2;
  int iVar3;
  
  func_0x00829c64();
  iVar2 = func_0x00804c60(uRam00800eb4,1,1,0);
  func_0x00800440(1);
  piVar1 = piRam00800ebc;
  if (iVar2 != 0) goto code_r0x00800e90;
  if (((*pcRam00800eb8 == '\x01') && (iVar2 = func_0x00800434(), iVar2 != 0)) &&
     (iVar2 = func_0x00801100(uRam00800ec0,uRam00800ec4), iVar2 == 0)) {
    iVar2 = 0;
  }
  else {
    iVar2 = func_0x00800f58();
    iVar3 = *piVar1;
    if (iVar2 == 0) {
      *(undefined1 *)(iVar3 + 0x28) = 0x10;
      iVar2 = 0;
      goto code_r0x00800e90;
    }
    *(undefined1 *)(iVar3 + 0x28) = 0x20;
    iVar2 = func_0x00801100(uRam00800ec8,uRam00800ecc);
    if (((iVar2 == 0) || (*pcRam00800ed0 != '\x01')) ||
       ((iVar3 = func_0x00800434(), iVar3 == 0 ||
        (iVar2 = func_0x00801100(uRam00800ed4,uRam00800ed8), iVar2 != 0)))) goto code_r0x00800e90;
  }
  *(undefined1 *)(*piVar1 + 0x28) = 0x20;
code_r0x00800e90:
  func_0x00800440(2);
  *piRam00800edc = iVar2;
  func_0x00804c18(uRam00800eb4,2);
  func_0x00808844();
  return;
}


// ==== 0x800f58 -> FUN_ram_00800f58 @ ram:00800f58

int FUN_ram_00800f58(void)

{
  undefined4 *puVar1;
  undefined4 uVar2;
  int iVar3;
  int extraout_r1;
  undefined1 *puVar4;
  uint uVar5;
  int iVar6;
  int iStack_21c;
  byte bStack_216;
  int iStack_214;
  undefined2 uStack_210;
  undefined2 uStack_20e;
  undefined1 uStack_20c;
  byte bStack_20b;
  undefined1 auStack_208 [16];
  undefined1 auStack_1f8 [496];
  
  func_0x00829c5c();
  iVar6 = 0;
  iVar3 = func_0x00807890(0,1,auStack_208);
  if (iVar3 == 0) {
    func_0x00808e90(&iStack_21c,auStack_208,0x10);
    uVar2 = uRam0080105c;
    puVar1 = puRam00801058;
    if (iStack_21c == 0x52494852) {
      if (iStack_214 == 0x1121410) {
        puRam00801058[1] = 0x1121410;
        *puVar1 = uVar2;
        *(undefined2 *)(puVar1 + 3) = uStack_210;
        *(undefined2 *)((int)puVar1 + 0xe) = uStack_20e;
        uStack_20c = 0x20;
        puVar4 = auStack_1f8;
        bStack_20b = 1;
        for (uVar5 = 0; uVar5 < bStack_216; uVar5 = uVar5 + 1 & 0xff) {
          func_0x00829d1c(bStack_20b + uVar5,uStack_20c);
          if (extraout_r1 == 0) {
            iVar6 = iVar6 + 1;
            iVar3 = func_0x00807890(iVar6,1,auStack_208);
            if (iVar3 != 0) goto code_r0x0080102a;
            puVar4 = auStack_208;
          }
          iVar3 = FUN_ram_00800ee0(puVar4,1);
          if (iVar3 != 0) {
            return iVar3;
          }
          puVar4 = puVar4 + 0x10;
        }
        iVar3 = 0;
      }
      else {
        iVar3 = 0xe;
      }
    }
    else {
      iVar3 = 0xb;
    }
  }
  else {
code_r0x0080102a:
    iVar3 = 7;
  }
  return iVar3;
}


// ==== 0x800ee0 -> FUN_ram_00800ee0 @ ram:00800ee0

undefined4 FUN_ram_00800ee0(void)

{
  short *psVar1;
  undefined4 uVar2;
  int iVar3;
  int iVar4;
  undefined4 uVar5;
  undefined8 uVar6;
  
  uVar6 = func_0x00829c5c();
  psVar1 = (short *)uVar6;
  if (*psVar1 == 1) {
    uVar2 = func_0x0082aed4(psVar1[2]);
    iVar3 = func_0x0082aed4(psVar1[3],(int)((ulonglong)uVar6 >> 0x20));
    uVar5 = *(undefined4 *)(psVar1 + 4);
    iVar4 = func_0x00807890(uVar2,iVar3,uVar5);
    if (iVar4 == 0) {
      iVar3 = func_0x00800000(uVar5,iVar3 << 9);
      if (iVar3 == *(int *)(psVar1 + 6)) {
        uVar2 = 0;
      }
      else {
        uVar2 = 0xd;
      }
    }
    else {
      uVar2 = 7;
    }
  }
  else if (*psVar1 == 2) {
    *puRam00800f54 = *(undefined4 *)(psVar1 + 2);
    uVar2 = 0;
  }
  else {
    uVar2 = 0;
  }
  return uVar2;
}


// ==== 0x801100 -> FUN_ram_00801100 @ ram:00801100

int FUN_ram_00801100(void)

{
  undefined4 *puVar1;
  int iVar2;
  byte bVar3;
  undefined8 uVar4;
  undefined4 uStack_30;
  int iStack_2c;
  int iStack_28;
  byte bStack_22;
  int iStack_20;
  undefined2 uStack_1c;
  undefined2 uStack_1a;
  undefined1 auStack_18 [16];
  
  uVar4 = func_0x00829c58();
  func_0x008003b4();
  iVar2 = func_0x0080599c((int)uVar4,0,0,0);
  if (((iVar2 == 0) || (iVar2 == 0x1a00037)) || (iVar2 == 0x1a00038)) {
    iVar2 = func_0x00805b70((int)((ulonglong)uVar4 >> 0x20),0x11,&uStack_30);
    if (iVar2 == 0) {
      iStack_2c = 0;
      iVar2 = func_0x00809298(uStack_30,&iStack_28,0x10,1,&iStack_2c);
      puVar1 = puRam00801058;
      if ((iVar2 == 0) && (iStack_2c == 0x10)) {
        if (iStack_28 == 0x52494852) {
          if (iStack_20 == 0x1121410) {
            *puRam00801058 = uRam0080105c;
            puVar1[1] = 0x1121410;
            *(undefined2 *)(puVar1 + 3) = uStack_1c;
            *(undefined2 *)((int)puVar1 + 0xe) = uStack_1a;
            for (bVar3 = 0; bVar3 < bStack_22; bVar3 = bVar3 + 1) {
              iStack_2c = 0;
              iVar2 = func_0x00809298(uStack_30,auStack_18,0x10,1,&iStack_2c);
              if ((iVar2 != 0) || (iStack_2c != 0x10)) goto code_r0x008011ea;
              iVar2 = FUN_ram_00801060(uStack_30,auStack_18);
              if (iVar2 != 0) goto code_r0x00801206;
            }
            iVar2 = 0;
          }
          else {
            iVar2 = 0xe;
          }
        }
        else {
          iVar2 = 0xb;
        }
      }
      else {
code_r0x008011ea:
        iVar2 = 10;
      }
code_r0x00801206:
      func_0x00805cd8(&uStack_30);
    }
    else {
      iVar2 = 9;
    }
    func_0x008093b8((int)uVar4);
  }
  else {
    iVar2 = 8;
  }
  return iVar2;
}


// ==== 0x801060 -> FUN_ram_00801060 @ ram:00801060

undefined4 FUN_ram_00801060(void)

{
  ushort uVar1;
  int iVar2;
  undefined4 uVar3;
  short *psVar4;
  undefined4 uVar5;
  undefined8 uVar6;
  int iStack_10;
  undefined1 auStack_c [4];
  
  uVar6 = func_0x00829c5c();
  psVar4 = (short *)((ulonglong)uVar6 >> 0x20);
  uVar3 = (undefined4)uVar6;
  if (*psVar4 == 1) {
    func_0x00808f60(uVar3,2,0,0,&iStack_10);
    func_0x00808f60(uVar3,1,(uint)(ushort)psVar4[2] << 9,0,auStack_c);
    uVar1 = psVar4[3];
    uVar5 = *(undefined4 *)(psVar4 + 4);
    func_0x00809298(uVar3,uVar5,(uint)uVar1 << 9,1,auStack_c);
    func_0x00808f60(uVar3,1,iStack_10,iStack_10 >> 0x1f,auStack_c);
    iVar2 = func_0x00800000(uVar5,(uint)uVar1 << 9);
    if (iVar2 == *(int *)(psVar4 + 6)) {
      uVar3 = 0;
    }
    else {
      uVar3 = 0xd;
    }
  }
  else if (*psVar4 == 2) {
    *puRam00800f54 = *(undefined4 *)(psVar4 + 2);
    uVar3 = 0;
  }
  else {
    uVar3 = 0;
  }
  return uVar3;
}


// ==== 0x80011c -> FUN_ram_0080011c @ ram:0080011c

void FUN_ram_0080011c(void)

{
  undefined1 *puVar1;
  int iVar2;
  undefined2 *puVar3;
  undefined1 uVar4;
  int iVar5;
  uint uVar6;
  
  func_0x00829c44();
  iVar2 = iRam0080014c;
  *(undefined4 *)(iRam0080014c + 0x14) = 0;
  FUN_ram_00800bec();
  func_0x00800cac();
  func_0x00802cac();
  *puRam00800160 = *puRam00800150 >> 8;
  puVar3 = puRam0080016c;
  *puRam0080016c = 0;
  *puVar3 = 1;
  *puRam00800180 = *puRam00800180 & 0xffbf;
  *puVar3 = 0;
  *puVar3 = 1;
  iVar5 = FUN_ram_0080081c();
  *(short *)(iVar2 + 0x34) = (short)iVar5;
  *(bool *)(iRam00800228 + 0xb) = iVar5 == 3;
  func_0x00800440(0);
  func_0x00800430();
  func_0x00802da4();
  func_0x00800570();
  FUN_ram_00800750();
  FUN_ram_008007ec(1);
  *(undefined4 *)(iVar2 + 0x18) = uRam0080022c;
  func_0x00803138(1);
  FUN_ram_008005a4();
  func_0x00803260();
  iVar5 = func_0x00803688();
  if (iVar5 == 0) {
    iVar5 = FUN_ram_00800630();
    if (iVar5 != 0) {
      FUN_ram_00800668(1,puRam00800230);
      puVar1 = (undefined1 *)*puRam00800230;
      iVar5 = func_0x0080368c();
      if (iVar5 == 0) {
        if ((&AP_AMV2 < puVar1) && ((int)(*puRam00800234 & 0x1000) >> 8 != 0))
        goto code_r0x00800258;
      }
      else if (&AP_AMV2 < puVar1) goto code_r0x00800258;
      func_0x008016b8(0);
    }
  }
  else {
    func_0x00803390(0);
  }
code_r0x00800258:
  iVar5 = FUN_ram_00800994(*(undefined2 *)(iVar2 + 0x34));
  if (iVar5 != 0) {
    FUN_ram_00800d48();
    FUN_ram_00800d90();
    FUN_ram_00800cb4(2);
    func_0x008038d0();
    func_0x00801aac();
    while (iVar5 = func_0x008039f0(), iVar5 != 0) {
      iVar5 = func_0x00801224();
      if (iVar5 == 0) {
        func_0x00801718();
        break;
      }
      func_0x00801acc();
    }
    func_0x00801abc();
    FUN_ram_00800cb4(1);
  }
  iVar5 = func_0x00800898(*(undefined2 *)(iVar2 + 0x34));
  if (iVar5 == 0) {
    func_0x008003a4();
  }
  else {
    *puRam008002b0 = *puRam008002b0 & 0xffef;
    *puVar3 = 0;
    *puVar3 = 1;
    func_0x00803b04(1,1);
    FUN_ram_00800b08();
    FUN_ram_00800b94();
    func_0x00803dcc();
    uVar6 = func_0x00803108();
    func_0x00800dd0();
    if ((~uVar6 & 0x1000) != 0) {
      *(undefined1 *)(iVar2 + 4) = 1;
      *(undefined1 *)(iVar2 + 5) = 0;
    }
    func_0x00802364(1);
    iVar5 = func_0x008040f0();
    if ((iVar5 != 0) && (*(int *)(iVar2 + 0x14) == 0)) {
      *(undefined4 *)(iVar2 + 0x14) = 6;
    }
    func_0x00804acc();
    FUN_ram_00804c18(uRam00800398,1);
    uVar4 = FUN_ram_008009e4();
    *(undefined1 *)(iRam0080039c + 0x1a) = uVar4;
    if (*(char *)(iVar2 + 0x36) == '\x01') {
      func_0x00804d8c(uRam008003a0);
      func_0x00804aec();
    }
    iVar5 = FUN_ram_00804c60(uRam00800398,2,1,0);
    if ((iVar5 != 0) && (*(int *)(iVar2 + 0x14) == 0)) {
      *(int *)(iVar2 + 0x14) = iVar5;
    }
    if ((*(int *)(iVar2 + 8) != 0) && (*(int *)(iVar2 + 0x14) == 0)) {
      *(int *)(iVar2 + 0x14) = *(int *)(iVar2 + 8);
    }
    if (*(int *)(iVar2 + 0x14) == 0) {
      func_0x00800440(3);
      FUN_ram_00800500();
      func_0x008021dc();
      func_0x0080517c(0);
    }
    else {
      func_0x00804b4c();
      func_0x00803b04(1,0);
      func_0x008003cc(*(undefined4 *)(iVar2 + 0x14));
    }
  }
  return;
}


// ==== 0x800434 -> FUN_ram_00800434 @ ram:00800434

void FUN_ram_00800434(void)

{
  func_0x00805988();
  func_0x00805830();
  return;
}


// ==== 0x805830 -> FUN_ram_00805830 @ ram:00805830

undefined4 FUN_ram_00805830(uint param_1)

{
  undefined4 uVar1;
  
  if (param_1 == *pbRam00805850) {
    if ((*puRam00805854 & 0x800) == 0) {
      uVar1 = 1;
    }
    else {
      uVar1 = 0;
    }
  }
  else {
    uVar1 = 0;
  }
  return uVar1;
}


// ==== 0x8003cc -> FUN_ram_008003cc @ ram:008003cc

void FUN_ram_008003cc(void)

{
  code *pcVar1;
  uint uVar2;
  uint uVar3;
  
  uVar2 = func_0x00829c64();
  pcVar1 = pcRam00800424;
  do {
    uVar3 = 0;
    if (uVar2 != 0) {
      do {
        func_0x00804d8c(uRam00800428);
        (*pcVar1)(3,1);
        (*pcVar1)(1,1);
        (*pcVar1)(2,1);
        func_0x00804d8c(uRam00800428);
        (*pcVar1)(3,0);
        (*pcVar1)(1,0);
        (*pcVar1)(2,0);
        uVar3 = uVar3 + 1;
      } while (uVar3 < uVar2);
    }
    func_0x00804d8c(uRam0080042c);
  } while( true );
}


// ==== 0x807890 -> FUN_ram_00807890 @ ram:00807890

undefined4 FUN_ram_00807890(undefined4 param_1,undefined4 param_2,undefined1 *param_3)

{
  int iVar1;
  undefined4 uVar2;
  int iVar3;
  uint in_mlo;
  undefined8 uVar4;
  int iStack_c;
  int aiStack_8 [2];
  
  uVar4 = func_0x00829c64();
  iVar3 = (int)((ulonglong)uVar4 >> 0x20);
  iStack_c = 0;
  aiStack_8[0] = 0;
  iVar1 = func_0x00809cd8();
  if (iVar1 == 0) {
    *param_3 = 0xff;
    uVar2 = uRam00807b20;
  }
  else {
    func_0x0080a570(&iStack_c);
    func_0x00809d1c(aiStack_8);
    Auxregs0104 = 0;
    asm_instruction_05(0xd,(uint)*(byte *)(iStack_c + 3),(uint)*(ushort *)(aiStack_8[0] + 0xde));
    uVar2 = uRam00807b24;
    if ((uint)(iVar3 + (int)uVar4) <= in_mlo) {
      asm_instruction_05(0xd,(uint)*(ushort *)(aiStack_8[0] + 0xd0),(uint)*(byte *)(iStack_c + 3));
      uVar2 = func_0x0080782c(in_mlo + (int)uVar4,iVar3,param_3,1);
    }
  }
  return uVar2;
}


// ==== 0x800500 -> FUN_ram_00800500 @ ram:00800500

void FUN_ram_00800500(void)

{
  int iVar1;
  undefined4 *puVar2;
  undefined4 uVar3;
  int iVar4;
  
  puVar2 = puRam00800564;
  iVar1 = iRam00800560;
  iVar4 = *(int *)(iRam00800560 + 0x18);
  *(undefined2 *)(iVar4 + 10) = 0x44c;
  *(undefined1 *)(iVar4 + 0x1c) = 0xff;
  uVar3 = uRam00800568;
  *(undefined2 *)(iVar4 + 8) = 0;
  *(undefined1 *)(iVar4 + 0x1d) = 0;
  *(undefined1 *)(iVar4 + 0x1e) = 0;
  *(undefined1 *)(iVar4 + 0x1f) = 0;
  *(undefined1 *)(iVar4 + 0x20) = 0;
  *(undefined1 *)(iVar4 + 0x21) = 0;
  *(undefined1 *)(iVar4 + 0x22) = 0;
  *puVar2 = uVar3;
  *(undefined4 *)(iVar4 + 0x24) = uRam0080056c;
  *(undefined1 *)(iVar4 + 0x29) = *(undefined1 *)(iVar1 + 0x28);
  *(undefined2 *)(iVar4 + 0x2c) = *(undefined2 *)(iVar1 + 0x2a);
  *(undefined2 *)(iVar4 + 0x2e) = *(undefined2 *)(iVar1 + 0x2c);
  *(undefined2 *)(iVar4 + 0x30) = *(undefined2 *)(iVar1 + 0x2e);
  *(undefined4 *)(iVar4 + 0x54) = *(undefined4 *)(iVar1 + 0x30);
  *(undefined2 *)(iVar4 + 0x58) = *(undefined2 *)(iVar1 + 0x34);
  *(undefined1 *)(iVar4 + 0x2a) = *(undefined1 *)(iVar1 + 0x36);
  func_0x0080047c();
  return;
}


// ==== 0x80fc74 -> FUN_ram_0080fc74 @ ram:0080fc74

void FUN_ram_0080fc74(void)

{
  int iVar1;
  undefined4 uVar2;
  
  func_0x00819e6c(1);
  uVar2 = func_0x00819ec8();
  iVar1 = iRam0080fd18;
  *(undefined4 *)(iRam0080fd18 + 0x30) = uVar2;
  *(short *)(iVar1 + 0x28) = (short)((uint)uVar2 >> 0x10);
  *(short *)(iVar1 + 0x2a) = (short)uVar2;
  return;
}

