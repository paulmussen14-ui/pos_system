"""Ticket de prueba para comprobar la impresora sin registrar ninguna venta."""

from datetime import datetime

from printing.ticket_printer import imprimir_ticket_venta

MARCA_PRUEBA = "*** TICKET DE PRUEBA ***\nNo es una venta"


def venta_de_prueba() -> dict:
    """Venta de ejemplo (no se guarda en ningún lado). Incluye una línea con
    acentos y signos del español para comprobar la tabla de caracteres de la
    impresora (ver CODEPAGE_* en ticket_printer.py)."""
    return {
        "id": "PRUEBA",
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cliente_nombre": "Cliente de prueba",
        "subtotal": 25.5,
        "descuento": 0,
        "total": 25.5,
        "metodo_pago_nombre": "Efectivo",
        "lineas": [
            {
                "producto_nombre": "Producto de ejemplo",
                "cantidad": 2,
                "precio_venta_unitario": 5.0,
                "subtotal": 10.0,
            },
            {
                "producto_nombre": "Acentos: áéíóú ñÑ ¿Qué tal? ¡Hola! ü",
                "cantidad": 1,
                "precio_venta_unitario": 15.5,
                "subtotal": 15.5,
            },
        ],
    }


def imprimir_ticket_de_prueba(
    config_negocio: dict, ancho_caracteres: int, nombre_impresora: str | None
) -> None:
    """
    Imprime una sola copia del ticket de prueba con la misma configuración que
    un ticket real (logo, QR de Yape, datos del ticket, pie), marcada como
    prueba. Si nombre_impresora es None (o no es Windows), queda guardado como
    archivo de texto, igual que una venta sin impresora.
    Lanza TicketPrinterError si la impresora falla.
    """
    config = dict(config_negocio)
    config["etiqueta_reimpresion"] = MARCA_PRUEBA
    imprimir_ticket_venta(
        venta_de_prueba(), config, ancho_caracteres, nombre_impresora, imprimir_dos_copias=False
    )
