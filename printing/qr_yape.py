"""Convierte una imagen (el QR de Yape) a comandos ESC/POS de imagen."""

from printing.imagen_escpos import generar_bytes_imagen_escpos

# Fracción del ancho del papel que ocupa el QR impreso. Antes ocupaba el 100%
# del ancho; ahora es un poco menos de la mitad (45%). Súbelo o bájalo aquí si
# lo quieres más grande o más chico (0.40 = más chico, 0.50 = la mitad).
FRACCION_ANCHO_QR = 0.45


def generar_bytes_qr_escpos(ruta_imagen: str, ancho_papel_mm: int | None) -> bytes:
    """
    Genera el comando GS v 0 (raster bit image) para imprimir el QR en una
    impresora térmica ESC/POS. El QR ocupa FRACCION_ANCHO_QR del ancho del
    papel y queda CENTRADO.

    Para que el QR siga siendo escaneable se binariza con umbral duro (sin
    dithering), de modo que los módulos queden nítidos. El detalle de la
    conversión está en printing/imagen_escpos.py.
    """
    return generar_bytes_imagen_escpos(
        ruta_imagen, ancho_papel_mm, FRACCION_ANCHO_QR, dithering=False
    )
