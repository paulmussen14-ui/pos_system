"""Convierte una imagen (el QR de Yape) a comandos ESC/POS de imagen."""

from PIL import Image

# Fracción del ancho del papel que ocupa el QR impreso. Antes ocupaba el 100%
# del ancho; ahora es un poco menos de la mitad (45%). Súbelo o bájalo aquí si
# lo quieres más grande o más chico (0.40 = más chico, 0.50 = la mitad).
FRACCION_ANCHO_QR = 0.45


def generar_bytes_qr_escpos(ruta_imagen: str, ancho_papel_mm: int | None) -> bytes:
    """
    Genera el comando GS v 0 (raster bit image) para imprimir ruta_imagen
    en una impresora térmica ESC/POS. El QR ocupa FRACCION_ANCHO_QR del ancho
    del papel (58mm ~ 384 dots, 80mm ~ 576 dots) y queda CENTRADO.

    Para centrarlo no se depende del comando de alineación de la impresora
    (varias lo ignoran en imágenes): la imagen se manda del ancho completo del
    papel, con márgenes blancos a los lados.

    Para que el QR siga siendo escaneable:
    - Las imágenes con transparencia se pintan sobre fondo BLANCO (si no,
      los píxeles transparentes se convierten en negro).
    - Se reduce con un filtro suave (LANCZOS) y recién después se binariza con
      umbral duro (sin dithering), para que los módulos queden nítidos.
    - El lado del QR se ajusta a múltiplo de 8 dots.
    """
    ancho_papel_dots = 576 if (ancho_papel_mm and ancho_papel_mm >= 80) else 384
    ancho_qr = max(8, int(ancho_papel_dots * FRACCION_ANCHO_QR) // 8 * 8)

    img = Image.open(ruta_imagen)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fondo = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(fondo, img)
    img = img.convert("L")

    ratio = ancho_qr / img.width
    alto_qr = max(1, round(img.height * ratio))
    img = img.resize((ancho_qr, alto_qr), Image.LANCZOS)
    img = img.point(lambda p: 255 if p >= 128 else 0)

    # Lienzo blanco del ancho del papel con el QR pegado al centro.
    lienzo = Image.new("L", (ancho_papel_dots, alto_qr), 255)
    lienzo.paste(img, ((ancho_papel_dots - ancho_qr) // 2, 0))
    img = lienzo.convert("1")  # ya es blanco/negro puro: no hay nada que "dithear"

    ancho_dots, alto_dots = img.size
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
