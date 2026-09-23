"""Genera el texto plano del ticket de venta a partir de los datos de la venta."""

from utils.validators import formatear_moneda

# --- Comandos ESC/POS para impresoras térmicas (se ignoran en modo texto plano) ---
ESC = "\x1b"
GS = "\x1d"

_ESC_POS = {
    "bold_on": ESC + "\x45\x01",
    "bold_off": ESC + "\x45\x00",
    "align_center": ESC + "\x61\x01",
    "align_left": ESC + "\x61\x00",
    "doble_tam": GS + "\x21\x11",
    "tam_normal": GS + "\x21\x00",
    # GS V 66 n ("feed and cut"): primero alimenta n líneas de papel y
    # recién después corta. A diferencia de GS V 1 (corte inmediato en la
    # posición actual del cabezal), este evita que el corte caiga encima de
    # las últimas líneas del ticket, que todavía no pasaron la cuchilla.
    "corte": GS + "\x56\x42\x05",
}


def ancho_caracteres_por_papel(ancho_papel_mm: int | None) -> int:
    """
    Aproxima cuántos caracteres monoespaciados entran por línea según el
    ancho físico del rollo térmico (58mm ~= 32 columnas, 80mm ~= 48 columnas
    con la fuente típica de estas impresoras).
    """
    if ancho_papel_mm and ancho_papel_mm >= 80:
        return 48
    return 32


def _anchos_columna(ancho_caracteres: int) -> dict:
    """
    Calcula el ancho fijo de cada columna de la tabla de items (cantidad,
    precio unitario, subtotal) según el ancho total del papel. Usar columnas
    fijas -en vez de espacios calculados sobre la marcha- es lo que hace que
    todas las filas queden alineadas entre sí, como una tabla real.
    """
    col_cant = 5      # ej. "1.0" + margen
    conector = 2       # "x "
    col_subtotal = 10 if ancho_caracteres >= 48 else 9
    col_precio = ancho_caracteres - col_cant - conector - col_subtotal
    return {"cant": col_cant, "conector": conector, "precio": max(col_precio, 6), "subtotal": col_subtotal}


def _fila_item(cantidad, precio, subtotal, moneda, ancho_caracteres) -> str:
    """Arma la fila 'cantidad x precio ... subtotal' con columnas fijas, sin
    importar cuántos dígitos tenga cada número, para que quede alineada con
    el resto de filas de la tabla de items."""
    col = _anchos_columna(ancho_caracteres)
    cant_str = f"{cantidad:g}".ljust(col["cant"])
    precio_str = formatear_moneda(precio, moneda).ljust(col["precio"])
    subtotal_str = formatear_moneda(subtotal, moneda).rjust(col["subtotal"])
    return f"{cant_str}x {precio_str}{subtotal_str}"[:ancho_caracteres]


def generar_texto_ticket(
    venta: dict,
    config_negocio: dict,
    ancho_caracteres: int = 32,
    etiqueta_copia: str | None = None,
    esc_pos: bool = False,
) -> str:
    """
    Genera el ticket de venta como texto plano formateado para impresora
    térmica, con la tabla de items alineada en columnas fijas.
    NUNCA incluye el costo interno del producto, solo precio de venta.

    - etiqueta_copia: si se indica (ej. "COPIA CLIENTE"), se agrega esa marca
      debajo del encabezado para diferenciar cada copia impresa.
    - esc_pos: si es True, agrega comandos ESC/POS (negrita, centrado, doble
      tamaño, corte de papel) para impresoras térmicas compatibles. Si es
      False, genera texto plano legible (modo vista previa / .txt).
    """
    moneda = config_negocio.get("moneda", "S/")
    c = _ESC_POS if esc_pos else {k: "" for k in _ESC_POS}
    lineas = []

    # --- Encabezado ---
    nombre_negocio = config_negocio.get("nombre_negocio", "Mi Negocio")
    if esc_pos:
        lineas.append(c["align_center"] + c["doble_tam"] + c["bold_on"])
        lineas.append(nombre_negocio)
        lineas.append(c["tam_normal"] + c["bold_off"])
    else:
        lineas.append(centrar(nombre_negocio, ancho_caracteres))

    if config_negocio.get("direccion"):
        direccion = config_negocio["direccion"]
        lineas.append(direccion if esc_pos else centrar(direccion, ancho_caracteres))
    if config_negocio.get("ruc"):
        linea_ruc = f"RUC: {config_negocio['ruc']}"
        lineas.append(linea_ruc if esc_pos else centrar(linea_ruc, ancho_caracteres))
    if config_negocio.get("telefono"):
        linea_tel = f"Tel: {config_negocio['telefono']}"
        lineas.append(linea_tel if esc_pos else centrar(linea_tel, ancho_caracteres))

    if esc_pos:
        lineas.append(c["align_left"])

    lineas.append("=" * ancho_caracteres)

    if etiqueta_copia:
        marca = centrar(f"*** {etiqueta_copia} ***", ancho_caracteres)
        lineas.append(c["bold_on"] + marca + c["bold_off"] if esc_pos else marca)
        lineas.append("-" * ancho_caracteres)

    lineas.append(f"Venta #{venta['id']}")
    lineas.append(f"Fecha: {venta['fecha']}")
    if venta.get("cliente_nombre"):
        lineas.append(f"Cliente: {venta['cliente_nombre']}")
    lineas.append("-" * ancho_caracteres)

    # --- Tabla de items ---
    col = _anchos_columna(ancho_caracteres)
    encabezado_tabla = (
        f"{'CANT'.ljust(col['cant'])}  "
        f"{'P.UNIT'.ljust(col['precio'])}"
        f"{'SUBTOTAL'.rjust(col['subtotal'])}"
    )
    lineas.append(encabezado_tabla[:ancho_caracteres])
    lineas.append("-" * ancho_caracteres)

    for linea in venta.get("lineas", []):
        nombre = linea["producto_nombre"]
        cantidad = linea["cantidad"]
        precio = linea["precio_venta_unitario"]
        subtotal = linea["subtotal"]

        nombre_linea = nombre[:ancho_caracteres]
        lineas.append(c["bold_on"] + nombre_linea + c["bold_off"] if esc_pos else nombre_linea)
        lineas.append(_fila_item(cantidad, precio, subtotal, moneda, ancho_caracteres))

    lineas.append("-" * ancho_caracteres)
    if venta.get("descuento", 0) > 0:
        lineas.append(alinear_derecha(f"Subtotal: {formatear_moneda(venta['subtotal'], moneda)}", ancho_caracteres))
        lineas.append(alinear_derecha(f"Descuento: -{formatear_moneda(venta['descuento'], moneda)}", ancho_caracteres))

    total_str = alinear_derecha(f"TOTAL: {formatear_moneda(venta['total'], moneda)}", ancho_caracteres)
    lineas.append(c["bold_on"] + total_str + c["bold_off"] if esc_pos else total_str)
    lineas.append("=" * ancho_caracteres)

    if venta.get("metodo_pago_nombre"):
        lineas.append(f"Pago: {venta['metodo_pago_nombre']}")

    lineas.append("")
    pie = config_negocio.get("ticket_pie", "Gracias por su compra")
    if esc_pos:
        lineas.append(c["align_center"] + pie + c["align_left"])
    else:
        lineas.append(centrar(pie, ancho_caracteres))
    lineas.append("")

    if esc_pos:
        lineas.append(c["corte"])

    return "\n".join(lineas)


def generar_copias_ticket(
    venta: dict,
    config_negocio: dict,
    ancho_caracteres: int = 32,
    esc_pos: bool = False,
    imprimir_dos_copias: bool = True,
) -> list[tuple[str, str]]:
    """
    Genera las copias del ticket de una venta.

    Si imprimir_dos_copias es True (valor por defecto), devuelve dos copias:
    una para el cliente y otra para control interno del negocio. Si es
    False, devuelve una sola copia sin etiqueta.

    Devuelve una lista de tuplas (etiqueta, texto_ticket).
    """
    if not imprimir_dos_copias:
        return [("unica", generar_texto_ticket(venta, config_negocio, ancho_caracteres, None, esc_pos))]

    return [
        ("cliente", generar_texto_ticket(venta, config_negocio, ancho_caracteres, "COPIA CLIENTE", esc_pos)),
        ("control_interno", generar_texto_ticket(venta, config_negocio, ancho_caracteres, "CONTROL INTERNO", esc_pos)),
    ]


def centrar(texto: str, ancho: int) -> str:
    return texto.center(ancho)


def alinear_derecha(texto: str, ancho: int) -> str:
    return texto.rjust(ancho)