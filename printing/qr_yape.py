"""Convierte una imagen (el QR de Yape) a comandos ESC/POS de imagen."""

from PIL import Image


def generar_bytes_qr_escpos(ruta_imagen: str, ancho_papel_mm: int | None) -> bytes:
    """
    Genera el comando GS v 0 (raster bit image) para imprimir ruta_imagen
    en una impresora térmica ESC/POS. Ajusta el ancho a los dots físicos
    del papel (58mm ~ 384 dots, 80mm ~ 576 dots).

    Para que el QR siga siendo escaneable:
    - Las imágenes con transparencia se pintan sobre fondo BLANCO (si no,
      los píxeles transparentes se convierten en negro).
    - Se binariza con umbral duro (sin dithering) ANTES de reescalar.
    - Se reescala con NEAREST para no generar grises en los bordes.
    """
    ancho_dots = 576 if (ancho_papel_mm and ancho_papel_mm >= 80) else 384

    img = Image.open(ruta_imagen)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fondo = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(fondo, img)
    img = img.convert("L").point(lambda p: 255 if p >= 128 else 0)

    ratio = ancho_dots / img.width
    alto_dots = max(1, round(img.height * ratio))
    img = img.resize((ancho_dots, alto_dots), Image.NEAREST)
    img = img.convert("1")  # ya es blanco/negro puro: no hay nada que "dithear"

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