"""Convierte el texto del ticket a HTML para las vistas previas, reemplazando
la línea "[QR de Yape]" por la imagen real del QR (centrada y con el mismo
tamaño relativo que tendrá al imprimir)."""

import html
from pathlib import Path

from PySide6.QtCore import QUrl

from printing.qr_yape import FRACCION_ANCHO_QR
from utils.logger import logger

MARCADOR_TEXTO_QR = "[QR de Yape]"


def ticket_a_html(texto: str, ruta_qr: str | None, ancho_papel_px: int) -> str | None:
    """
    Devuelve el ticket en HTML con la imagen del QR en su lugar, o None si no
    se puede (sin QR configurado, archivo inexistente o sin marcador en el
    texto); en ese caso quien llama muestra el texto plano como siempre.

    ancho_papel_px: ancho en pixeles que ocupa el "papel" en pantalla (columnas
    del ticket * ancho de un carácter). El QR ocupa FRACCION_ANCHO_QR de eso.
    """
    if not ruta_qr:
        return None
    if not Path(ruta_qr).is_file():
        logger.warning(f"Vista previa: no se encontró el archivo del QR de Yape: {ruta_qr}")
        return None

    lineas = texto.split("\n")
    posicion = next((i for i, l in enumerate(lineas) if l.strip() == MARCADOR_TEXTO_QR), None)
    if posicion is None:
        return None

    def bloque(parte: list[str]) -> str:
        contenido = html.escape("\n".join(parte))
        return f'<pre style="margin:0; font-family:\'Courier New\', monospace;">{contenido}</pre>'

    ancho_qr = max(40, int(ancho_papel_px * FRACCION_ANCHO_QR))
    url = QUrl.fromLocalFile(str(ruta_qr)).toString()
    imagen = f'<p align="center" style="margin:4px 0;"><img src="{url}" width="{ancho_qr}"></p>'

    return bloque(lineas[:posicion]) + imagen + bloque(lineas[posicion + 1:])
