"""
Envío de tickets a la impresora térmica.

En Windows usa el spooler nativo vía pywin32 (win32print), enviando el texto
como RAW — funciona con la gran mayoría de impresoras térmicas ESC/POS que
están instaladas como impresoras estándar de Windows.

Si pywin32 no está disponible (ej. desarrollo en Linux) o no hay impresora
configurada, cae en un modo "simulado" que guarda cada copia en un .txt para
poder revisarla, sin romper el flujo de venta.

Cada venta se puede imprimir en 1 o 2 copias (cliente y control interno) en
un mismo trabajo de impresión, separadas por el comando de corte de papel.
"""

import sys
from pathlib import Path

from config import APP_DATA_DIR
from utils.logger import logger
from printing.ticket_template import generar_copias_ticket


class TicketPrinterError(Exception):
    pass


def imprimir_ticket(texto_ticket: str, nombre_impresora: str | None = None) -> None:
    """Imprime un único texto de ticket ya generado (se mantiene por compatibilidad)."""
    if sys.platform == "win32" and nombre_impresora:
        _imprimir_windows([texto_ticket], nombre_impresora)
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
    función ya arma las copias necesarias y las manda como un solo trabajo
    de impresión, separadas por el corte de papel.
    """
    es_impresora_real = sys.platform == "win32" and bool(nombre_impresora)
    copias = generar_copias_ticket(
        venta, config_negocio, ancho_caracteres,
        esc_pos=es_impresora_real,
        imprimir_dos_copias=imprimir_dos_copias,
    )

    if es_impresora_real:
        textos = [texto for _, texto in copias]
        _imprimir_windows(textos, nombre_impresora)
    else:
        for etiqueta, texto in copias:
            _guardar_ticket_simulado(texto, f"ultimo_ticket_{etiqueta}.txt")


def _imprimir_windows(textos_ticket: list[str], nombre_impresora: str) -> None:
    try:
        import win32print
    except ImportError:
        logger.warning("pywin32 no está instalado; se guardan los tickets en lugar de imprimirlos.")
        for i, texto in enumerate(textos_ticket, start=1):
            _guardar_ticket_simulado(texto, f"ultimo_ticket_{i}.txt")
        return

    try:
        hprinter = win32print.OpenPrinter(nombre_impresora)
        try:
            hjob = win32print.StartDocPrinter(hprinter, 1, ("Ticket de venta", None, "RAW"))
            try:
                win32print.StartPagePrinter(hprinter)
                # Todas las copias van en el mismo trabajo de impresión,
                # separadas por el comando de corte que ya viene incluido en
                # cada texto (solo cuando se generó con esc_pos=True).
                cuerpo = "".join(textos_ticket)
                win32print.WritePrinter(hprinter, cuerpo.encode("utf-8", errors="replace"))
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