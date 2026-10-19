"""Boleta de servicio en PDF.

Se dibuja con QTextDocument + QPdfWriter, que ya vienen con PySide6: no hace falta
instalar nada más. Sirve para guardar la boleta o adjuntarla en un correo.

IMPORTANTE: es un comprobante interno de atención del negocio. No es un comprobante
electrónico SUNAT; para eso hace falta emitirlo con un facturador autorizado.
"""

import html
import re
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF, QUrl
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from config import APP_DATA_DIR
from services.reserva_service import ReservaService
from utils.fechas import fecha_dmy, fecha_larga, parsear_fecha
from utils.validators import formatear_moneda

CARPETA_BOLETAS = APP_DATA_DIR / "boletas"

# Colores del tema claro de la app (ui/tokens.py), para que la boleta combine con el sistema.
_COLOR_PRIMARIO = "#059669"
_COLOR_TEXTO = "#0f172a"
_COLOR_SUAVE = "#475569"
_COLOR_BORDE = "#e2e8f0"
_COLOR_FONDO = "#f8fafc"

_RESOLUCION_DPI = 96


def nombre_archivo_boleta(reserva: dict) -> str:
    """'Boleta_B001-000012_Juan_Perez.pdf' (sin caracteres que Windows no acepta)."""
    cliente = re.sub(r"[^\w\-]+", "_", reserva["cliente_nombre"], flags=re.UNICODE).strip("_")
    return f"Boleta_{reserva['boleta_texto']}_{cliente[:30] or 'cliente'}.pdf"


def ruta_boleta_por_defecto(reserva: dict) -> Path:
    CARPETA_BOLETAS.mkdir(parents=True, exist_ok=True)
    return CARPETA_BOLETAS / nombre_archivo_boleta(reserva)


def _html_boleta(reserva: dict, config_negocio: dict) -> str:
    esc = html.escape
    moneda = config_negocio.get("moneda", "S/")
    negocio = esc((config_negocio.get("nombre_negocio") or "").strip() or "Mi Negocio")

    datos_negocio = []
    for clave, prefijo in (("direccion", ""), ("ruc", "RUC: "), ("telefono", "Tel: ")):
        valor = (config_negocio.get(clave) or "").strip()
        if valor:
            datos_negocio.append(esc(prefijo + valor))
    datos_negocio_html = "<br>".join(datos_negocio)

    logo_html = ""
    ruta_logo = config_negocio.get("logo_path")
    if ruta_logo and Path(ruta_logo).is_file():
        logo_html = (
            f'<img src="{QUrl.fromLocalFile(ruta_logo).toString()}" height="56"><br>'
        )

    dia = parsear_fecha(reserva["fecha"])
    cita = f"{fecha_larga(dia).capitalize()} · {reserva['hora_inicio']} a {reserva['hora_fin']}"
    pagado_en = reserva.get("pagado_en") or ""
    emision = f"{fecha_dmy(parsear_fecha(pagado_en))} {pagado_en[11:16]}" if pagado_en else ""

    lineas = ReservaService.lineas_boleta(reserva)
    subtotal = sum(l["subtotal"] for l in lineas)
    descuento = float(reserva.get("descuento") or 0)
    total = float(reserva["total"] if reserva.get("total") is not None else subtotal)
    adelantos = float(reserva.get("adelanto_aplicado") or 0)

    borde = f"border-bottom:1px solid {_COLOR_BORDE};"
    filas_detalle = ""
    for linea in lineas:
        cantidad = f"{linea['cantidad']:g}"
        filas_detalle += (
            f'<tr><td style="{borde}">{esc(linea["nombre"])}</td>'
            f'<td align="center" style="{borde}">{cantidad}</td>'
            f'<td align="right" style="{borde}">{formatear_moneda(linea["precio_unitario"], moneda)}</td>'
            f'<td align="right" style="{borde}">{formatear_moneda(linea["subtotal"], moneda)}</td></tr>'
        )

    def fila_total(texto: str, valor: str, suave: bool = True) -> str:
        color = f' style="color:{_COLOR_SUAVE};"' if suave else ""
        return f'<tr><td align="right"{color}>{texto}</td><td align="right" width="110">{valor}</td></tr>'

    filas_totales = ""
    if descuento > 0:
        filas_totales += fila_total("Subtotal", formatear_moneda(subtotal, moneda))
        filas_totales += fila_total("Descuento", "- " + formatear_moneda(descuento, moneda))
    filas_totales += (
        f'<tr><td align="right" style="font-size:14pt; font-weight:bold;">TOTAL</td>'
        f'<td align="right" style="font-size:14pt; font-weight:bold; color:{_COLOR_PRIMARIO};">'
        f'{formatear_moneda(total, moneda)}</td></tr>'
    )
    if adelantos > 0:
        filas_totales += fila_total("Adelantos", "- " + formatear_moneda(adelantos, moneda))
        filas_totales += fila_total("<b>Saldo pagado</b>", f"<b>{formatear_moneda(total - adelantos, moneda)}</b>", False)

    notas = (reserva.get("notas") or "").strip()
    notas_html = (
        f'<p style="color:{_COLOR_SUAVE}; margin-top:6px;"><b>Notas:</b> {esc(notas)}</p>'
        if notas else ""
    )
    contacto = " · ".join(esc(x) for x in (reserva.get("cliente_telefono"), reserva.get("cliente_email")) if x)
    contacto_html = f'<br><span style="color:{_COLOR_SUAVE};">{contacto}</span>' if contacto else ""

    pie = esc((config_negocio.get("ticket_pie") or "").strip() or "Gracias por su preferencia")
    pago = esc(reserva.get("metodo_pago") or "—")

    return f"""
<html><body style="font-family:'Segoe UI','Helvetica','Arial',sans-serif; font-size:10pt; color:{_COLOR_TEXTO};">

<table width="100%" cellspacing="0" cellpadding="0">
  <tr>
    <td valign="top">
      {logo_html}
      <span style="font-size:17pt; font-weight:bold;">{negocio}</span><br>
      <span style="color:{_COLOR_SUAVE};">{datos_negocio_html}</span>
    </td>
    <td valign="top" align="right">
      <span style="font-size:9pt; color:{_COLOR_SUAVE};">BOLETA DE SERVICIO</span><br>
      <span style="font-size:15pt; font-weight:bold; color:{_COLOR_PRIMARIO};">{esc(reserva['boleta_texto'])}</span><br>
      <span style="color:{_COLOR_SUAVE};">Emitida: {esc(emision)}</span>
    </td>
  </tr>
</table>

<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:8px;"><tr><td bgcolor="{_COLOR_PRIMARIO}" style="font-size:2pt;">&nbsp;</td></tr></table>

<table width="100%" cellspacing="0" cellpadding="6" style="margin-top:6px;">
  <tr>
    <td width="50%" valign="top" bgcolor="{_COLOR_FONDO}">
      <span style="font-size:8pt; color:{_COLOR_SUAVE};">CLIENTE</span><br>
      <b>{esc(reserva['cliente_nombre'])}</b>{contacto_html}
    </td>
    <td width="50%" valign="top" bgcolor="{_COLOR_FONDO}">
      <span style="font-size:8pt; color:{_COLOR_SUAVE};">CITA</span><br>
      <b>{esc(cita)}</b>
    </td>
  </tr>
</table>

<table width="100%" cellspacing="0" cellpadding="7" style="margin-top:16px; border-collapse:collapse;">
  <tr bgcolor="{_COLOR_PRIMARIO}">
    <td style="color:#ffffff;"><b>Descripción</b></td>
    <td align="center" width="62" style="color:#ffffff;"><b>Cant.</b></td>
    <td align="right" width="90" style="color:#ffffff;"><b>P. unit.</b></td>
    <td align="right" width="90" style="color:#ffffff;"><b>Importe</b></td>
  </tr>
  {filas_detalle}
</table>

<table width="100%" cellspacing="0" cellpadding="4" style="margin-top:8px;">
  <tr>
    <td width="38%" valign="top">
      <span style="font-size:8pt; color:{_COLOR_SUAVE};">MÉTODO DE PAGO</span><br>
      <b>{pago}</b>
      {notas_html}
    </td>
    <td width="62%"><table width="100%" cellspacing="0" cellpadding="3">{filas_totales}</table></td>
  </tr>
</table>

<p align="center" style="margin-top:34px; color:{_COLOR_SUAVE};">{pie}</p>
<p align="center" style="font-size:7pt; color:#94a3b8;">Comprobante interno de atención. No es un comprobante de pago electrónico SUNAT.</p>

</body></html>
"""


def generar_boleta_pdf(reserva: dict, config_negocio: dict, ruta: Path | str | None = None) -> Path:
    """Crea el PDF de la boleta de una reserva cobrada y devuelve su ruta.

    Si no se indica `ruta`, se guarda en la carpeta de datos del programa
    (…/POSLocal/boletas/). Debe llamarse desde el hilo principal (usa fuentes de Qt).
    """
    if not reserva.get("numero_boleta"):
        raise ValueError("La reserva todavía no tiene boleta (no ha sido cobrada).")

    destino = Path(ruta) if ruta else ruta_boleta_por_defecto(reserva)
    destino.parent.mkdir(parents=True, exist_ok=True)

    escritor = QPdfWriter(str(destino))
    escritor.setResolution(_RESOLUCION_DPI)
    escritor.setPageSize(QPageSize(QPageSize.A5))
    escritor.setPageOrientation(QPageLayout.Portrait)
    escritor.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Millimeter)
    escritor.setTitle(f"Boleta {reserva['boleta_texto']}")
    escritor.setCreator(config_negocio.get("nombre_negocio") or "POS Local")

    documento = QTextDocument()
    documento.setDocumentMargin(0)
    documento.setPageSize(QSizeF(escritor.width(), escritor.height()))
    documento.setHtml(_html_boleta(reserva, config_negocio))
    documento.print_(escritor)
    return destino
