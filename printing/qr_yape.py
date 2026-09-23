"""Convierte una imagen (el QR de Yape) a comandos ESC/POS de imagen."""

from PIL import Image


def generar_bytes_qr_escpos(ruta_imagen: str, ancho_papel_mm: int | None) -> bytes:
    """
    Genera el comando GS v 0 (raster bit image) para imprimir ruta_imagen
    en una impresora térmica ESC/POS. Ajusta el ancho a los dots físicos
    del papel (58mm ~ 384 dots, 80mm ~ 576 dots) y aplica dithering al
    convertir a blanco/negro puro.
    """
    ancho_dots = 576 if (ancho_papel_mm and ancho_papel_mm >= 80) else 384

    img = Image.open(ruta_imagen).convert("L")
    ratio = ancho_dots / img.width
    alto_dots = max(1, round(img.height * ratio))
    img = img.resize((ancho_dots, alto_dots))
    img = img.convert("1")  # blanco/negro puro, con dithering Floyd-Steinberg

    ancho_bytes = (ancho_dots + 7) // 8
    pixeles = img.load()
    datos = bytearray(ancho_bytes * alto_dots)

    for y in range(alto_dots):
        offset_fila = y * ancho_bytes
        for x in range(ancho_dots):
            if pixeles[x, y] == 0:  # 0 = negro en modo "1" de Pillow
                datos[offset_fila + x // 8] |= (0x80 >> (x % 8))

    xL, xH = ancho_bytes & 0xFF, (ancho_bytes >> 8) & 0xFF
    yL, yH = alto_dots & 0xFF, (alto_dots >> 8) & 0xFF
    comando = bytes([0x1D, 0x76, 0x30, 0x00, xL, xH, yL, yH])

    return comando + bytes(datos)