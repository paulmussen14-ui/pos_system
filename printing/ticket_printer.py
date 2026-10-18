"""
Envío de tickets a la impresora térmica.

En Windows usa el spooler nativo vía pywin32 (win32print), enviando los
datos como RAW — funciona con la gran mayoría de impresoras térmicas
ESC/POS que están instaladas como impresoras estándar de Windows.

Si pywin32 no está disponible (ej. desarrollo en Linux) o no hay impresora
configurada, cae en un modo "simulado" que guarda cada copia en un .txt para
poder revisarla, sin romper el flujo de venta.

Cada venta se puede imprimir en 1 o 2 copias (cliente y control interno) en
un mismo trabajo de impresión, separadas por el comando de corte de papel.

El texto del ticket puede incluir los marcadores MARCADOR_LOGO y
MARCADOR_QR_YAPE (ver ticket_template.py) donde deben ir la imagen del logo y
la del QR de Yape. Como los bytes de una imagen ESC/POS no son texto UTF-8
válido, el trabajo de impresión se arma en bytes (no en str): el texto se
codifica a la tabla de la impresora y, en el punto de cada marcador, se
insertan directamente los bytes del comando de imagen generados por
printing/logo_ticket.py y printing/qr_yape.py.
"""

import re
import sys
import unicodedata
from pathlib import Path

from config import APP_DATA_DIR
from utils.logger import logger
from printing.ticket_template import generar_copias_ticket, MARCADOR_QR_YAPE, MARCADOR_LOGO
from printing.qr_yape import generar_bytes_qr_escpos
from printing.logo_ticket import generar_bytes_logo_escpos

# --- Codificacion del ticket para la impresora termica ---
# Las impresoras termicas no entienden UTF-8: usan una "tabla de caracteres".
# CP858 (ESC t 19) trae n con tilde, vocales acentuadas y signos de espanol.
# Si en tu impresora los acentos salen mal, prueba con
# probar_acentos_impresora.py y cambia estas dos constantes:
#   CP858 -> ("cp858", 19)   CP850 -> ("cp850", 2)   CP437 -> ("cp437", 0)
CODEPAGE_PYTHON = "cp858"
CODEPAGE_ESCPOS = 19

# ESC @ (reiniciar impresora) + ESC t n (elegir tabla de caracteres).
INICIO_IMPRESORA = b"\x1b@" + b"\x1bt" + bytes([CODEPAGE_ESCPOS])


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


class TicketPrinterError(Exception):
    pass


def imprimir_ticket(texto_ticket: str, nombre_impresora: str | None = None) -> None:
    """Imprime un único texto de ticket ya generado (se mantiene por compatibilidad)."""
    if sys.platform == "win32" and nombre_impresora:
        _imprimir_windows_bytes([INICIO_IMPRESORA + _codificar(texto_ticket)], nombre_impresora)
    else:
        _guardar_ticket_simulado(texto_ticket, "ultimo_ticket.txt")


def imprimir_ticket_venta(
    venta: dict,
    config_negocio: dict,
    ancho_caracteres: int = 32,
    nombre_impresora: str | None = None,
    imprimir_dos_copias: bool = True,
) -> None:
    """
    Genera e imprime las copias del ticket de una venta (cliente + control
    interno, o solo una copia si imprimir_dos_copias es False). Úsalo en
    lugar de generar_texto_ticket + imprimir_ticket por separado: esta
    función ya arma las copias necesarias, resuelve el QR de Yape si
    corresponde, y las manda como un solo trabajo de impresión, separadas
    por el corte de papel.
    """
    es_impresora_real = sys.platform == "win32" and bool(nombre_impresora)
    copias = generar_copias_ticket(
        venta, config_negocio, ancho_caracteres,
        esc_pos=es_impresora_real,
        imprimir_dos_copias=imprimir_dos_copias,
    )

    if es_impresora_real:
        ancho_papel_mm = 80 if ancho_caracteres >= 48 else 58
        bloques = [_texto_a_bytes(texto, config_negocio, ancho_papel_mm) for _, texto in copias]
        _imprimir_windows_bytes(bloques, nombre_impresora)
    else:
        for etiqueta, texto in copias:
            texto_simulado = texto.replace(MARCADOR_QR_YAPE, "[QR de Yape]").replace(MARCADOR_LOGO, "[Logo]")
            _guardar_ticket_simulado(texto_simulado, f"ultimo_ticket_{etiqueta}.txt")


def _bytes_imagen(nombre: str, ruta: str | None, generador, ancho_papel_mm: int) -> bytes:
    """Bytes ESC/POS de una imagen del ticket, o b"" si no hay ruta o si la
    generación falla (imagen faltante, corrupta, Pillow no instalado, etc.).
    El error queda en el log: nunca se bloquea la venta por una imagen."""
    if not ruta:
        return b""
    try:
        return generador(ruta, ancho_papel_mm)
    except Exception as exc:
        logger.error(f"No se pudo generar {nombre} para el ticket: {exc}")
        return b""


def _texto_a_bytes(texto: str, config_negocio: dict, ancho_papel_mm: int) -> bytes:
    """
    Codifica el texto del ticket a bytes para la impresora (tabla CP858, ver
    arriba), reemplazando MARCADOR_LOGO y MARCADOR_QR_YAPE por los bytes
    reales del comando ESC/POS de imagen del logo y del QR de Yape. Cada copia
    empieza con INICIO_IMPRESORA.
    Si no hay imagen configurada, o si la generación falla, el ticket se
    imprime igual sin esa imagen y el error queda en el log.
    """
    imagenes = {
        MARCADOR_LOGO: _bytes_imagen(
            "el logo", config_negocio.get("logo_path"), generar_bytes_logo_escpos, ancho_papel_mm
        ) if MARCADOR_LOGO in texto else b"",
        MARCADOR_QR_YAPE: _bytes_imagen(
            "el QR de Yape", config_negocio.get("qr_yape_path"), generar_bytes_qr_escpos, ancho_papel_mm
        ) if MARCADOR_QR_YAPE in texto else b"",
    }

    patron = "(" + "|".join(re.escape(m) for m in imagenes) + ")"
    resultado = INICIO_IMPRESORA
    for parte in re.split(patron, texto):
        if parte in imagenes:
            resultado += imagenes[parte]
        else:
            resultado += _codificar(parte)
    return resultado


def _imprimir_windows_bytes(bloques: list[bytes], nombre_impresora: str) -> None:
    try:
        import win32print
    except ImportError:
        logger.warning("pywin32 no está instalado; se guardan los tickets en lugar de imprimirlos.")
        for i, bloque in enumerate(bloques, start=1):
            _guardar_ticket_simulado(bloque.decode(CODEPAGE_PYTHON, errors="replace"), f"ultimo_ticket_{i}.txt")
        return

    try:
        hprinter = win32print.OpenPrinter(nombre_impresora)
        try:
            hjob = win32print.StartDocPrinter(hprinter, 1, ("Ticket de venta", None, "RAW"))
            try:
                win32print.StartPagePrinter(hprinter)
                # Todas las copias van en el mismo trabajo de impresión,
                # separadas por el comando de corte que ya viene incluido en
                # cada bloque (solo cuando se generó con esc_pos=True).
                cuerpo = b"".join(bloques)
                win32print.WritePrinter(hprinter, cuerpo)
                win32print.EndPagePrinter(hprinter)
            finally:
                win32print.EndDocPrinter(hprinter)
        finally:
            win32print.ClosePrinter(hprinter)
    except Exception as exc:
        logger.error(f"Error al imprimir ticket: {exc}")
        raise TicketPrinterError(f"No se pudo imprimir el ticket: {exc}") from exc


def _guardar_ticket_simulado(texto_ticket: str, nombre_archivo: str = "ultimo_ticket.txt") -> Path:
    """Fallback: guarda el ticket como archivo de texto (modo desarrollo / sin impresora)."""
    destino = APP_DATA_DIR / nombre_archivo
    destino.write_text(texto_ticket, encoding="utf-8")
    logger.info(f"Ticket guardado (modo simulado) en: {destino}")
    return destino


def listar_impresoras_disponibles() -> list[str]:
    """Devuelve los nombres de las impresoras instaladas en Windows."""
    if sys.platform != "win32":
        return []
    try:
        import win32print
        return [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]
    except ImportError:
        return []