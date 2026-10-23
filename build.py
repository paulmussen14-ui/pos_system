"""Genera el ejecutable y el instalador de POS Local con la versión de config.py.

USO (en Windows, desde la raíz del proyecto):
    python build.py                 # solo el .exe  -> dist/POSLocal.exe
    python build.py --instalador    # .exe + instalador con Inno Setup
    python build.py --version 2.3.0 # cambia APP_VERSION en config.py y compila

Pasos: (1) lee/actualiza APP_VERSION, (2) escribe version_info.txt (propiedades del
.exe), (3) ejecuta PyInstaller con pos_local.spec, (4) opcionalmente compila
installer.iss con /DMyAppVersion=<versión> -> installer_output/POSLocal_Setup_<versión>.exe
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "config.py"
PATRON = re.compile(r'^(APP_VERSION\s*=\s*)"([^"]+)"', re.M)

RUTAS_ISCC = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
]


def leer_version() -> str:
    m = PATRON.search(CONFIG.read_text(encoding="utf-8"))
    if not m:
        sys.exit("No encontré APP_VERSION en config.py")
    return m.group(2)


def escribir_version(nueva: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", nueva):
        sys.exit("La versión debe tener el formato X.Y.Z (ej. 2.2.2)")
    texto = CONFIG.read_text(encoding="utf-8")
    CONFIG.write_text(PATRON.sub(rf'\g<1>"{nueva}"', texto, count=1), encoding="utf-8")


def generar_version_info(version: str) -> None:
    """Archivo de recursos de Windows: lo que se ve en Propiedades -> Detalles del .exe."""
    a, b, c = (int(x) for x in version.split("."))
    tupla = f"({a}, {b}, {c}, 0)"
    (RAIZ / "version_info.txt").write_text(f'''# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={tupla}, prodvers={tupla}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable("040A04B0", [
      StringStruct("CompanyName", "FayzerDEV"),
      StringStruct("FileDescription", "Sistema POS Local"),
      StringStruct("FileVersion", "{version}"),
      StringStruct("InternalName", "POSLocal"),
      StringStruct("OriginalFilename", "POSLocal.exe"),
      StringStruct("ProductName", "POS Local"),
      StringStruct("ProductVersion", "{version}")])]),
    VarFileInfo([VarStruct("Translation", [1034, 1200])])
  ]
)
''', encoding="utf-8")


def compilar_exe() -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    str(RAIZ / "pos_local.spec")], cwd=RAIZ, check=True)


def compilar_instalador(version: str) -> None:
    iscc = shutil.which("ISCC") or next((r for r in RUTAS_ISCC if Path(r).exists()), None)
    if not iscc:
        sys.exit("No encontré Inno Setup (ISCC.exe). Instálalo o abre installer.iss a mano.")
    subprocess.run([iscc, f"/DMyAppVersion={version}", str(RAIZ / "installer.iss")],
                   cwd=RAIZ, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--version", help="nueva versión X.Y.Z (actualiza config.py)")
    ap.add_argument("--instalador", action="store_true", help="también compila el instalador")
    args = ap.parse_args()

    if args.version:
        escribir_version(args.version)
    version = leer_version()
    print(f"==> Compilando POS Local v{version}")
    generar_version_info(version)
    compilar_exe()
    print(f"==> Listo: dist/POSLocal.exe (v{version})")
    if args.instalador:
        compilar_instalador(version)
        print(f"==> Listo: installer_output/POSLocal_Setup_{version}.exe")


if __name__ == "__main__":
    main()
