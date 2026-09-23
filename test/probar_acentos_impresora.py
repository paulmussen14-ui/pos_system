"""Imprime una hoja de prueba con 4 tablas de caracteres, para ver cual muestra
bien los acentos en TU impresora termica. Gasta unos 15 cm de papel.

Uso (desde la carpeta pos_system, con la impresora conectada):
    python probar_acentos_impresora.py
    python probar_acentos_impresora.py "NOMBRE EXACTO DE LA IMPRESORA"

Mira el papel: la opcion cuya linea "Pina, Cafe..." se lea bien es la tuya.
"""
import sys

try:
    import win32print
except ImportError:
    print("Necesitas Windows con pywin32 instalado (pip install pywin32).")
    sys.exit(1)

# (letra, codificacion de Python, numero de tabla ESC t)
OPCIONES = [
    ("A", "cp858", 19),   # la que usa el ticket por defecto
    ("B", "cp850", 2),
    ("C", "cp437", 0),
    ("D", "cp1252", 16),
]
MUESTRA = "Piña, Café, Ñandú, ¿Qué? ¡Hola! ÁÉÍÓÚ ü S/ 10.50"
CORTE = b"\x1d\x56\x42\x05"


def elegir_impresora() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    nombres = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]
    for i, n in enumerate(nombres, 1):
        print(f"  {i}. {n}")
    return nombres[int(input("Numero de tu impresora termica: ")) - 1]


def main() -> None:
    nombre = elegir_impresora()
    datos = b""
    for letra, codec, tabla in OPCIONES:
        datos += b"\x1b@" + b"\x1bt" + bytes([tabla])
        datos += f"OPCION {letra}  ({codec}, tabla {tabla})\n".encode("ascii")
        datos += MUESTRA.encode(codec, errors="replace") + b"\n"
        datos += b"-" * 32 + b"\n\n"
    datos += CORTE

    h = win32print.OpenPrinter(nombre)
    try:
        win32print.StartDocPrinter(h, 1, ("Prueba de acentos", None, "RAW"))
        try:
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, datos)
            win32print.EndPagePrinter(h)
        finally:
            win32print.EndDocPrinter(h)
    finally:
        win32print.ClosePrinter(h)
    print(f"Enviado a '{nombre}'. Revisa el papel y dime que opcion se lee bien (A, B, C o D).")


if __name__ == "__main__":
    main()