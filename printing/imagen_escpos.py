"""Convierte una imagen (logo o QR) a comandos ESC/POS de imagen (GS v 0)."""

from PIL import Image

# Ancho del papel en dots según el rollo: 58 mm ~ 384 dots, 80 mm ~ 576 dots.
DOTS_58MM = 384
DOTS_80MM = 576


def ancho_papel_en_dots(ancho_papel_mm: int | None) -> int:
    return DOTS_80MM if (ancho_papel_mm and ancho_papel_mm >= 80) else DOTS_58MM


def generar_bytes_imagen_escpos(
    ruta_imagen: str,
    ancho_papel_mm: int | None,
    fraccion_ancho: float,
    fraccion_alto_max: float | None = None,
    dithering: bool = False,
) -> bytes:
    """
    Genera el comando GS v 0 (raster bit image) para imprimir ruta_imagen en
    una impresora térmica ESC/POS. La imagen ocupa fraccion_ancho del ancho
    del papel y queda CENTRADA.

    Para centrarla no se depende del comando de alineación de la impresora
    (varias lo ignoran en imágenes): la imagen se manda del ancho completo del
    papel, con márgenes blancos a los lados.

    - fraccion_alto_max: si se indica, la imagen no puede ser más alta que esa
      fracción del ancho del papel (se reduce manteniendo la proporción). Sirve
      para que un logo alto no gaste medio metro de papel.
    - dithering: False = umbral duro (módulos nítidos, ideal para un QR).
      True = tramado Floyd-Steinberg (conserva los grises, ideal para un logo).

    Siempre:
    - Las imágenes con transparencia se pintan sobre fondo BLANCO (si no, los
      píxeles transparentes se convierten en negro).
    - Se reduce con un filtro suave (LANCZOS) antes de pasar a blanco y negro.
    - El ancho de la imagen se ajusta a múltiplo de 8 dots.
    """
    ancho_papel_dots = ancho_papel_en_dots(ancho_papel_mm)
    ancho_img = max(8, int(ancho_papel_dots * fraccion_ancho) // 8 * 8)

    img = Image.open(ruta_imagen)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fondo = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(fondo, img)
    img = img.convert("L")

    alto_img = max(1, round(img.height * (ancho_img / img.width)))
    if fraccion_alto_max is not None:
        alto_max = max(8, int(ancho_papel_dots * fraccion_alto_max))
        if alto_img > alto_max:
            ancho_img = max(8, int(ancho_img * alto_max / alto_img) // 8 * 8)
            alto_img = max(1, round(img.height * (ancho_img / img.width)))
    img = img.resize((ancho_img, alto_img), Image.LANCZOS)

    if dithering:
        img = img.convert("1")  # Pillow aplica Floyd-Steinberg por defecto
        img = img.convert("L")
    else:
        img = img.point(lambda p: 255 if p >= 128 else 0)

    # Lienzo blanco del ancho del papel con la imagen pegada al centro.
    lienzo = Image.new("L", (ancho_papel_dots, alto_img), 255)
    lienzo.paste(img, ((ancho_papel_dots - ancho_img) // 2, 0))
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
