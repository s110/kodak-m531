//! Portero del agente `me.sebastian.m531-dng`.
//!
//! launchd lo corre cada vez que sdvault toca su sello. Recorre `<vault>/*/DCIM/<nnn>KM531/` y, para
//! cada `<nnn>O<nnnn>.RAW`, arma la misma clave que `tools/auto_vault.py`
//! (`ruta-relativa|tamaño|mtime-entero`) y la busca en el estado (`vistos.json`). Si todas están, sale
//! con 0 sin más: unos milisegundos y ~1 MB. Si falta alguna (o no se puede decidir), reemplaza su
//! proceso por el comando de Python que recibe tras `--` (exec), que es quien convierte.
//!
//! uso: m531-portero <vault> <vistos.json> -- <python> <auto_vault.py> [args...]
//! Sólo lee. Sin dependencias.

use std::fs;
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::{Command, ExitCode};
use std::time::UNIX_EPOCH;

fn digitos(s: &[u8]) -> bool {
    !s.is_empty() && s.iter().all(u8::is_ascii_digit)
}

/// `\d{3}KM531`, sin distinguir mayúsculas.
fn es_carpeta_m531(n: &str) -> bool {
    let b = n.as_bytes();
    b.len() == 8 && digitos(&b[..3]) && b[3..].eq_ignore_ascii_case(b"KM531")
}

/// `\d{3}O\d{4}\.RAW`, sin distinguir mayúsculas.
fn es_raw_m531(n: &str) -> bool {
    let b = n.as_bytes();
    b.len() == 12
        && digitos(&b[..3])
        && b[3].eq_ignore_ascii_case(&b'O')
        && digitos(&b[4..8])
        && b[8..].eq_ignore_ascii_case(b".RAW")
}

fn nombres(dir: &Path) -> Vec<String> {
    let mut v: Vec<String> = match fs::read_dir(dir) {
        Ok(it) => it.filter_map(|e| e.ok()?.file_name().into_string().ok()).collect(),
        Err(_) => Vec::new(),
    };
    v.sort();
    v
}

/// ¿Hay algún RAW de la M531 que no figure en el estado? `None` = no se puede decidir (que lo vea Python).
fn hay_nuevos(vault: &Path, vistos: &str) -> Option<bool> {
    for tarjeta in nombres(vault) {
        if tarjeta.starts_with('.') {
            continue;
        }
        let dcim = vault.join(&tarjeta).join("DCIM");
        for carpeta in nombres(&dcim).into_iter().filter(|c| es_carpeta_m531(c)) {
            for n in nombres(&dcim.join(&carpeta)).into_iter().filter(|n| es_raw_m531(n)) {
                let rel = format!("{tarjeta}/DCIM/{carpeta}/{n}");
                // json.dump escapa lo no ASCII, comillas y barras: esas claves las decide Python
                if !rel.bytes().all(|c| c.is_ascii_graphic() && c != b'"' && c != b'\\') {
                    return None;
                }
                let md = fs::metadata(vault.join(&rel)).ok()?;
                let mtime = md.modified().ok()?.duration_since(UNIX_EPOCH).ok()?.as_secs();
                if !vistos.contains(&format!("\"{rel}|{}|{mtime}\"", md.len())) {
                    return Some(true);
                }
            }
        }
    }
    Some(false)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let corte = args.iter().position(|a| a == "--");
    let (Some(corte), true) = (corte, args.len() >= 2) else {
        eprintln!("uso: m531-portero <vault> <vistos.json> -- <python> <auto_vault.py> [args...]");
        return ExitCode::from(2);
    };
    let (vault, estado, cmd) = (Path::new(&args[0]), &args[1], &args[corte + 1..]);
    if cmd.is_empty() || corte != 2 {
        eprintln!("uso: m531-portero <vault> <vistos.json> -- <python> <auto_vault.py> [args...]");
        return ExitCode::from(2);
    }
    if !vault.is_dir() {
        return ExitCode::SUCCESS; // disco desmontado
    }
    let vistos = fs::read_to_string(estado).unwrap_or_default();
    if hay_nuevos(vault, &vistos) == Some(false) {
        return ExitCode::SUCCESS;
    }
    let err = Command::new(&cmd[0]).args(&cmd[1..]).exec(); // sólo vuelve si falla
    eprintln!("m531-portero: no se pudo ejecutar {}: {err}", cmd[0]);
    ExitCode::from(1)
}
