// Decompila funciones por dirección. Uso: -postScript Decomp.java salida.c addr1,addr2,...
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import java.io.*;
public class Decomp extends GhidraScript {
  public void run() throws Exception {
    String[] a = getScriptArgs();
    PrintWriter out = new PrintWriter(new FileWriter(a[0]));
    DecompInterface d = new DecompInterface(); d.openProgram(currentProgram);
    for (String s : a[1].split(",")) {
      Address ad = toAddr(Long.parseLong(s.replace("0x",""),16));
      Function f = getFunctionContaining(ad);
      if (f == null) { createFunction(ad, null); f = getFunctionAt(ad); }
      if (f == null) { out.println("// no function at " + s); continue; }
      DecompileResults r = d.decompileFunction(f, 120, monitor);
      out.println("// ==== " + s + " -> " + f.getName() + " @ " + f.getEntryPoint());
      out.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// fallo: " + r.getErrorMessage());
    }
    out.close();
  }
}
