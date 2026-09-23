"""Arregla los acentos y la n con tilde en el ticket de la impresora termica.

Problema: hoy el ticket se manda a la impresora en UTF-8, pero casi todas las
termicas esperan una tabla de caracteres (ej. CP858). Resultado: "Pina" o
"Cafe" con tilde salen como simbolos raros.

Que hace este script (edita printing/ticket_printer.py):
  - Codifica el ticket en CP858 (la tabla habitual para espanol).
  - Envia al inicio de cada copia: ESC @ (reiniciar) + ESC t 19 (elegir CP858).
  - Si aparece un caracter que la impresora no tiene (ej. un emoji), lo
    reemplaza por su letra base o por "?", en vez de imprimir basura.
  - Deja dos constantes arriba del archivo (CODEPAGE_PYTHON y CODEPAGE_ESCPOS)
    por si tu impresora usa otra tabla.

Uso (desde la carpeta pos_system, app cerrada):
    python fix_acentos_ticket.py

- Guarda una copia .bak antes de tocar nada.
- Respeta los saltos de linea de tu archivo (Windows CRLF o Linux LF).
- Si algo no coincide con lo esperado, NO modifica nada y te avisa.
- Si ya esta aplicado, no hace nada.
"""
import shutil
import sys
from pathlib import Path

RUTA = Path("printing/ticket_printer.py")

BLOQUE_CONSTANTES = '''from printing.qr_yape import generar_bytes_qr_escpos

# --- Codificacion del ticket para la impresora termica ---
# Las impresoras termicas no entienden UTF-8: usan una "tabla de caracteres".
# CP858 (ESC t 19) trae n con tilde, vocales acentuadas y signos de espanol.
# Si en tu impresora los acentos salen mal, prueba con
# probar_acentos_impresora.py y cambia estas dos constantes:
#   CP858 -> ("cp858", 19)   CP850 -> ("cp850", 2)   CP437 -> ("cp437", 0)
CODEPAGE_PYTHON = "cp858"
CODEPAGE_ESCPOS = 19

# ESC @ (reiniciar impresora) + ESC t n (elegir tabla de caracteres).
INICIO_IMPRESORA = b"\\x1b@" + b"\\x1bt" + bytes([CODEPAGE_ESCPOS])


def _codificar(texto: str) -> bytes:
    """Codifica el texto a la tabla de la impresora. Un caracter que la tabla
    no tenga se reemplaza por su letra base (sin acento) o por "?"; nunca
    falla ni imprime basura."""
    try:
        return texto.encode(CODEPAGE_PYTHON)
    except UnicodeEncodeError:
        pass

    partes = []
    for caracter in texto:
        try:
            partes.append(caracter.encode(CODEPAGE_PYTHON))
        except UnicodeEncodeError:
            base = unicodedata.normalize("NFKD", caracter).encode("ascii", "ignore")
            partes.append(base or b"?")
    return b"".join(partes)
'''

NUEVA_TEXTO_A_BYTES = '''def _texto_a_bytes(texto: str, config_negocio: dict, ancho_papel_mm: int) -> bytes:
    """
    Codifica el texto del ticket a bytes para la impresora (tabla CP858, ver
    arriba), reemplazando MARCADOR_QR_YAPE por los bytes reales del comando
    ESC/POS de imagen del QR de Yape. Cada copia empieza con INICIO_IMPRESORA.
    Si no hay QR configurado, o si la generacion falla (imagen faltante,
    corrupta, Pillow no instalado, etc.), el ticket se imprime igual sin el
    QR y el error queda en el log: nunca se bloquea la venta por esto.
    """
    ruta_qr = config_negocio.get("qr_yape_path")
    if not ruta_qr or MARCADOR_QR_YAPE not in texto:
        return INICIO_IMPRESORA + _codificar(texto.replace(MARCADOR_QR_YAPE, ""))

    try:
        bytes_qr = generar_bytes_qr_escpos(ruta_qr, ancho_papel_mm)
    except Exception as exc:
        logger.error(f"No se pudo generar el QR de Yape para el ticket: {exc}")
        return INICIO_IMPRESORA + _codificar(texto.replace(MARCADOR_QR_YAPE, ""))

    partes = texto.split(MARCADOR_QR_YAPE)
    resultado = INICIO_IMPRESORA + _codificar(partes[0])
    for parte in partes[1:]:
        resultado += bytes_qr + _codificar(parte)
    return resultado


'''


def leer(ruta: Path):
    crudo = ruta.read_bytes().decode("utf-8")
    return crudo.replace("\r\n", "\n"), "\r\n" in crudo


def escribir(ruta: Path, texto: str, crlf: bool) -> None:
    if crlf:
        texto = texto.replace("\n", "\r\n")
    ruta.write_bytes(texto.encode("utf-8"))


def reemplazar_una_vez(texto: str, viejo: str, nuevo: str, nombre: str) -> str:
    if texto.count(viejo) != 1:
        raise ValueError(f"No encontre '{nombre}' (tu archivo es distinto al esperado).")
    return texto.replace(viejo, nuevo)


def main() -> int:
    print("== Arreglando acentos del ticket ==")
    print(f"Carpeta actual: {Path.cwd()}")
    if not RUTA.exists():
        print(f"No encuentro {RUTA}. Ejecuta este script desde la carpeta pos_system.")
        return 1

    src, crlf = leer(RUTA)
    if "CODEPAGE_ESCPOS" in src:
        print("El arreglo ya estaba aplicado. No se cambio nada.")
        return 0

    try:
        nuevo = reemplazar_una_vez(
            src, "import sys\nfrom pathlib import Path\n",
            "import sys\nimport unicodedata\nfrom pathlib import Path\n", "imports",
        )
        nuevo = reemplazar_una_vez(
            nuevo, "from printing.qr_yape import generar_bytes_qr_escpos\n",
            BLOQUE_CONSTANTES, "import de qr_yape",
        )
        nuevo = reemplazar_una_vez(
            nuevo,
            '_imprimir_windows_bytes([texto_ticket.encode("utf-8", errors="replace")], nombre_impresora)',
            '_imprimir_windows_bytes([INICIO_IMPRESORA + _codificar(texto_ticket)], nombre_impresora)',
            "imprimir_ticket",
        )
        a = nuevo.find("def _texto_a_bytes(")
        b = nuevo.find("def _imprimir_windows_bytes(")
        if a == -1 or b == -1 or b < a:
            raise ValueError("No encontre '_texto_a_bytes' (tu archivo es distinto al esperado).")
        nuevo = nuevo[:a] + NUEVA_TEXTO_A_BYTES + nuevo[b:]
        nuevo = reemplazar_una_vez(
            nuevo, 'bloque.decode("utf-8", errors="replace")',
            'bloque.decode(CODEPAGE_PYTHON, errors="replace")', "modo simulado",
        )
        compile(nuevo, str(RUTA), "exec")
    except (ValueError, SyntaxError) as e:
        print(f"ALTO: {e}\nNo se modifico nada. Mandame printing/ticket_printer.py y lo reviso.")
        return 2

    shutil.copy2(RUTA, str(RUTA) + ".bak")
    escribir(RUTA, nuevo, crlf)
    print(f"Listo. Arreglo aplicado en {RUTA}  (copia: {RUTA}.bak)")
    print("Para deshacer: borra el archivo y quita el '.bak' del nombre de la copia.")
    print("Siguiente paso: python test_acentos_ticket.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())