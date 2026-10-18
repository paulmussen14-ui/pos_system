"""Convierte el logo del negocio a comandos ESC/POS de imagen para el ticket."""

from printing.imagen_escpos import generar_bytes_imagen_escpos

# Tamaño máximo del logo impreso, como fracción del ancho del papel.
# El logo ocupa como máximo el 50% del ancho y no puede ser más alto que el 40%
# del ancho (así un logo cuadrado o alto no gasta mucho papel). Súbelos o
# bájalos aquí si lo quieres más grande o más chico.
FRACCION_ANCHO_LOGO = 0.50
FRACCION_ALTO_MAX_LOGO = 0.40


def generar_bytes_logo_escpos(ruta_imagen: str, ancho_papel_mm: int | None) -> bytes:
    """
    Genera el comando GS v 0 para imprimir el logo, centrado, arriba del
    ticket. A diferencia del QR, el logo se pasa a blanco y negro con tramado
    (dithering) para que se conserven los grises y los degradados.
    """
    return generar_bytes_imagen_escpos(
        ruta_imagen,
        ancho_papel_mm,
        FRACCION_ANCHO_LOGO,
        fraccion_alto_max=FRACCION_ALTO_MAX_LOGO,
        dithering=True,
    )
