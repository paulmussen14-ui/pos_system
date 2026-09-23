"""Prueba de acentos del ticket. NO imprime nada de verdad y NO toca tu base
de datos: usa una carpeta temporal y una impresora falsa.

Uso (desde la carpeta pos_system):   python test_acentos_ticket.py
"""
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix="pos_test_")
os.environ["APPDATA"] = _TMP
os.environ["HOME"] = _TMP
os.environ["USERPROFILE"] = _TMP
sys.path.insert(0, os.getcwd())

from config import APP_DATA_DIR  # noqa: E402
if not str(APP_DATA_DIR).startswith(_TMP):
    print("ALTO: no pude aislar la carpeta de datos. No se ejecuto nada.")
    sys.exit(1)

from PIL import Image  # noqa: E402
from printing import ticket_printer  # noqa: E402

ok = True


def check(nombre, cond):
    global ok
    ok &= bool(cond)
    print(("OK   " if cond else "FALLA"), nombre)


# --- Impresora falsa: captura lo que se enviaria a la termica ---
enviado = []
falsa = types.ModuleType("win32print")
falsa.OpenPrinter = lambda nombre: "h"
falsa.StartDocPrinter = lambda h, nivel, doc: 1
falsa.StartPagePrinter = lambda h: None
falsa.WritePrinter = lambda h, datos: enviado.append(bytes(datos))
falsa.EndPagePrinter = lambda h: None
falsa.EndDocPrinter = lambda h: None
falsa.ClosePrinter = lambda h: None
sys.modules["win32print"] = falsa


def imprimir(venta, config, ancho=32, dos_copias=True):
    enviado.clear()
    plataforma = sys.platform
    sys.platform = "win32"          # solo durante la llamada
    try:
        ticket_printer.imprimir_ticket_venta(venta, config, ancho, "IMPRESORA FALSA", dos_copias)
    finally:
        sys.platform = plataforma
    return b"".join(enviado)


venta = {
    "id": 7, "fecha": "2026-09-23 10:00:00",
    "cliente_nombre": "José Muñoz", "cliente_direccion": "Jr. Ñandú 123, Cañete",
    "subtotal": 5.0, "descuento": 0, "total": 5.0, "metodo_pago_nombre": "Efectivo",
    "lineas": [{"producto_nombre": "Gaseosa Piña 500ml", "cantidad": 2,
                "precio_venta_unitario": 2.5, "subtotal": 5.0}],
}
config = {"nombre_negocio": "Bodega Peña", "moneda": "S/", "ticket_pie": "¡Gracias por su compra!"}

# ---- 1) Ticket normal con acentos, 2 copias ----
job = imprimir(venta, config)
check("cada copia empieza con ESC @ + ESC t 19 (2 copias)", job.count(b"\x1b@\x1bt\x13") == 2)
check("Piña -> ñ como byte 0xA4 (CP858)", b"Pi\xa4a" in job)
check("José -> é como byte 0x82", b"Jos\x82" in job)
check("Muñoz / Ñandú / Cañete con ñ, Ñ, ú", b"Mu\xa4oz" in job and b"\xa5and\xa3" in job and b"Ca\xa4ete" in job)
check("¡ y ! del pie: ¡ = 0xAD", b"\xadGracias" in job)
check("no quedan restos de UTF-8 (byte 0xC3)", b"\xc3" not in job)
check("el corte de papel sigue intacto (2 cortes)", job.count(b"\x1d\x56\x42\x05") == 2)
texto_ida_y_vuelta = job.decode("cp858", errors="replace")
check("al leerlo como CP858 vuelve el texto original",
      all(t in texto_ida_y_vuelta for t in ("Gaseosa Piña 500ml", "José Muñoz", "¡Gracias por su compra!")))

# ---- 2) Caracteres que la impresora no tiene ----
v2 = dict(venta, cliente_nombre="Ana 😀 Ńuñez")
job2 = imprimir(v2, config)
check("emoji -> '?' y Ń -> 'N' (sin basura ni error)", b"Ana ? Nu\xa4ez" in job2 or b"Ana ? N" in job2)

# ---- 3) Con QR de Yape: la imagen no se corrompe y el texto de despues si tiene acentos ----
qr = APP_DATA_DIR / "qr_prueba.png"
Image.new("RGB", (200, 200), "white").save(qr)
job3 = imprimir(venta, dict(config, qr_yape_path=str(qr), yape_numero="987654321",
                            politica_devolucion="Sin devoluciones después de 24 horas"))
check("QR presente (GS v 0)", b"\x1dv0\x00" in job3)
check("texto despues del QR con acentos (después: é = 0x82)", b"despu\x82s" in job3)

# ---- 4) Papel de 80 mm y 1 sola copia ----
job4 = imprimir(venta, config, ancho=48, dos_copias=False)
check("80 mm, 1 copia: un solo inicio y acentos ok", job4.count(b"\x1b@\x1bt\x13") == 1 and b"Pi\xa4a" in job4)

# ---- 5) Camino antiguo imprimir_ticket() ----
enviado.clear()
plataforma = sys.platform
sys.platform = "win32"
try:
    ticket_printer.imprimir_ticket("Piña Café\n", "IMPRESORA FALSA")
finally:
    sys.platform = plataforma
check("imprimir_ticket() tambien codifica bien", b"Pi\xa4a Caf\x82" in b"".join(enviado))

print("\nRESULTADO:", "TODO OK" if ok else "HAY FALLAS")
sys.exit(0 if ok else 1)