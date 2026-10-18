"""Convierte el texto del ticket a HTML para las vistas previas, reemplazando
las líneas "[Logo]" y "[QR de Yape]" por las imágenes reales (centradas y con
el mismo tamaño relativo que tendrán al imprimir)."""

import html
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QImageReader

from printing.logo_ticket import FRACCION_ANCHO_LOGO, FRACCION_ALTO_MAX_LOGO
from printing.qr_yape import FRACCION_ANCHO_QR
from utils.logger import logger

MARCADOR_TEXTO_QR = "[QR de Yape]"
MARCADOR_TEXTO_LOGO = "[Logo]"


def _ruta_valida(ruta: str | None, descripcion: str) -> str | None:
    """Devuelve la ruta si el archivo existe; si no, None (y avisa en el log
    cuando había una ruta guardada pero el archivo ya no está)."""
    if not ruta:
        return None
    if not Path(ruta).is_file():
        logger.warning(f"Vista previa: no se encontró el archivo de {descripcion}: {ruta}")
        return None
    return str(ruta)


def _ancho_logo_px(ruta_logo: str, ancho_papel_px: int) -> int:
    """Ancho del logo en la vista previa. Replica lo que hace la impresión:
    ocupa FRACCION_ANCHO_LOGO del papel, pero sin pasar de FRACCION_ALTO_MAX_LOGO
    de alto (si el logo es alto, se reduce manteniendo la proporción)."""
    ancho = max(8, int(ancho_papel_px * FRACCION_ANCHO_LOGO))
    tamano = QImageReader(ruta_logo).size()
    if tamano.isValid() and tamano.width() > 0:
        alto = ancho * tamano.height() / tamano.width()
        alto_max = ancho_papel_px * FRACCION_ALTO_MAX_LOGO
        if alto > alto_max:
            ancho = max(8, int(ancho * alto_max / alto))
    return ancho


def ticket_a_html(
    texto: str,
    ruta_qr: str | None,
    ancho_papel_px: int,
    ruta_logo: str | None = None,
) -> str | None:
    """
    Devuelve el ticket en HTML con las imágenes en su lugar, o None si no se
    puede reemplazar ninguna (sin logo ni QR configurados, archivos
    inexistentes o sin marcadores en el texto); en ese caso quien llama
    muestra el texto plano como siempre.

    ancho_papel_px: ancho en pixeles que ocupa el "papel" en pantalla (columnas
    del ticket * ancho de un carácter). Cada imagen ocupa su fracción de eso.
    """
    ruta_qr = _ruta_valida(ruta_qr, "el QR de Yape")
    ruta_logo = _ruta_valida(ruta_logo, "el logo")
    if not ruta_qr and not ruta_logo:
        return None

    lineas = texto.split("\n")
    sustitutos: dict[int, str] = {}  # índice de línea -> <p> con la imagen

    def imagen(ruta: str, ancho: int) -> str:
        url = QUrl.fromLocalFile(ruta).toString()
        return f'<p align="center" style="margin:4px 0;"><img src="{url}" width="{ancho}"></p>'

    for i, linea in enumerate(lineas):
        marcador = linea.strip()
        if marcador == MARCADOR_TEXTO_LOGO and ruta_logo:
            sustitutos[i] = imagen(ruta_logo, _ancho_logo_px(ruta_logo, ancho_papel_px))
        elif marcador == MARCADOR_TEXTO_QR and ruta_qr:
            sustitutos[i] = imagen(ruta_qr, max(40, int(ancho_papel_px * FRACCION_ANCHO_QR)))

    if not sustitutos:
        return None

    def bloque(parte: list[str]) -> str:
        if not parte:
            return ""
        contenido = html.escape("\n".join(parte))
        return f'<pre style="margin:0; font-family:\'Courier New\', monospace;">{contenido}</pre>'

    resultado = []
    inicio = 0
    for i in sorted(sustitutos):
        resultado.append(bloque(lineas[inicio:i]))
        resultado.append(sustitutos[i])
        inicio = i + 1
    resultado.append(bloque(lineas[inicio:]))
    return "".join(resultado)
