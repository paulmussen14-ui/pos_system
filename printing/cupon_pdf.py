"""Cupón de descuento en PDF.

Usa el mismo mecanismo que la boleta (QTextDocument + QPdfWriter, ya incluidos en
PySide6), así que no hace falta instalar nada más. Sirve para guardar el cupón
o adjuntarlo en un correo al cliente.
"""

import html
import re
from datetime import date
from pathlib import Path

from PySide6.QtCore import QUrl

from config import APP_DATA_DIR
from printing.boleta_pdf import (
    _escribir_pdf, _COLOR_PRIMARIO, _COLOR_TEXTO, _COLOR_SUAVE, _COLOR_BORDE, _COLOR_FONDO,
)
from utils.validators import formatear_moneda

CARPETA_CUPONES = APP_DATA_DIR / "cupones"


def nombre_archivo_cupon(cupon: dict) -> str:
    """'Cupon_CUP-SC87W6.pdf' (sin caracteres que Windows no acepta)."""
    codigo = re.sub(r"[^\w\-]+", "_", cupon["codigo"], flags=re.UNICODE).strip("_")
    return f"Cupon_{codigo}.pdf"


def ruta_cupon_por_defecto(cupon: dict) -> Path:
    CARPETA_CUPONES.mkdir(parents=True, exist_ok=True)
    return CARPETA_CUPONES / nombre_archivo_cupon(cupon)


def texto_descuento(cupon: dict, moneda: str = "S/") -> str:
    if cupon["tipo"] == "porcentaje":
        return f"{cupon['valor']:g}% DE DESCUENTO"
    return f"{formatear_moneda(cupon['valor'], moneda)} DE DESCUENTO"


def texto_vigencia(cupon: dict) -> str:
    ini = (cupon.get("fecha_inicio") or "")[:10]
    fin = (cupon.get("fecha_fin") or "")[:10]

    def dmy(iso: str) -> str:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")

    if ini and fin:
        return f"Válido del {dmy(ini)} al {dmy(fin)}"
    if fin:
        return f"Válido hasta el {dmy(fin)}"
    if ini:
        return f"Válido desde el {dmy(ini)}"
    return "Sin fecha de vencimiento"


def _html_cupon(cupon: dict, config_negocio: dict) -> str:
    esc = html.escape
    moneda = config_negocio.get("moneda", "S/")
    negocio = esc((config_negocio.get("nombre_negocio") or "").strip() or "Mi Negocio")

    datos_negocio = []
    for clave, prefijo in (("direccion", ""), ("telefono", "Tel: ")):
        valor = (config_negocio.get(clave) or "").strip()
        if valor:
            datos_negocio.append(esc(prefijo + valor))
    datos_negocio_html = "<br>".join(datos_negocio)

    logo_html = ""
    ruta_logo = config_negocio.get("logo_path")
    if ruta_logo and Path(ruta_logo).is_file():
        logo_html = f'<img src="{QUrl.fromLocalFile(ruta_logo).toString()}" height="56"><br>'

    condiciones = [texto_vigencia(cupon)]
    if cupon.get("compra_minima"):
        condiciones.append(f"Compra mínima: {formatear_moneda(cupon['compra_minima'], moneda)}")
    if cupon.get("usos_maximos"):
        n = int(cupon["usos_maximos"])
        condiciones.append("Válido para 1 uso" if n == 1 else f"Válido para {n} usos")
    condiciones.append("Preséntalo o indica el código al momento de pagar")
    condiciones_html = "<br>".join(esc(c) for c in condiciones)

    descripcion = esc((cupon.get("descripcion") or "").strip())
    descripcion_html = (
        f'<p align="center" style="font-size:12pt; color:{_COLOR_SUAVE}; margin-top:6px;">{descripcion}</p>'
        if descripcion else ""
    )

    return f"""
<html><body style="font-family:'Segoe UI','Helvetica','Arial',sans-serif; font-size:10pt; color:{_COLOR_TEXTO};">

<table width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
  {logo_html}
  <span style="font-size:17pt; font-weight:bold;">{negocio}</span><br>
  <span style="color:{_COLOR_SUAVE};">{datos_negocio_html}</span>
</td></tr></table>

<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:8px;"><tr><td bgcolor="{_COLOR_PRIMARIO}" style="font-size:2pt;">&nbsp;</td></tr></table>

<p align="center" style="margin-top:26px; font-size:9pt; color:{_COLOR_SUAVE};">CUPÓN DE DESCUENTO</p>
<p align="center" style="margin-top:0px; font-size:26pt; font-weight:bold; color:{_COLOR_PRIMARIO};">{esc(texto_descuento(cupon, moneda))}</p>
{descripcion_html}

<table width="100%" cellspacing="0" cellpadding="14" style="margin-top:22px; border:2px dashed {_COLOR_PRIMARIO};">
  <tr><td align="center" bgcolor="{_COLOR_FONDO}">
    <span style="font-size:9pt; color:{_COLOR_SUAVE};">TU CÓDIGO</span><br>
    <span style="font-size:24pt; font-weight:bold; letter-spacing:3px;">{esc(cupon['codigo'])}</span>
  </td></tr>
</table>

<table width="100%" cellspacing="0" cellpadding="8" style="margin-top:22px;">
  <tr><td align="center" style="border-top:1px solid {_COLOR_BORDE}; color:{_COLOR_SUAVE};">
    {condiciones_html}
  </td></tr>
</table>

</body></html>
"""


def generar_cupon_pdf(cupon: dict, config_negocio: dict, ruta: Path | str | None = None) -> Path:
    """Crea el PDF del cupón y devuelve su ruta.

    Si no se indica `ruta`, se guarda en la carpeta de datos del programa
    (…/POSLocal/cupones/). Debe llamarse desde el hilo principal (usa fuentes de Qt).
    """
    destino = Path(ruta) if ruta else ruta_cupon_por_defecto(cupon)
    return _escribir_pdf(_html_cupon(cupon, config_negocio), destino,
                         f"Cupón {cupon['codigo']}",
                         config_negocio.get("nombre_negocio") or "POS Local")
