"""Íconos de línea de un solo color para toda la interfaz (menú, tarjetas, botones).

Son trazos SVG simples (cuadrícula de 24x24) que se pintan en memoria con el
color que se pida, así se ven nítidos a cualquier escala y combinan con el
tema claro y el oscuro. No hay archivos de imagen que empaquetar.

Uso:
    icono("carrito", "#ffffff", 20)                  -> QIcon de un color
    icono_menu("carrito", normal, activo, marcado)   -> QIcon con estados
"""

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

# Cada ícono es el contenido interno de un <svg viewBox="0 0 24 24"> con trazo.
_TRAZOS = {
    "inicio": (
        '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>'
        '<path d="M10 21v-6h4v6"/>'
    ),
    "carrito": (
        '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/>'
        '<path d="M2 3h3l2.7 12.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 7H6"/>'
    ),
    "caja_registradora": (
        '<path d="M3 7a2 2 0 0 1 2-2h13v4"/>'
        '<path d="M3 7v11a2 2 0 0 0 2 2h14a1 1 0 0 0 1-1V10a1 1 0 0 0-1-1H5a2 2 0 0 1-2-2z"/>'
        '<circle cx="16.5" cy="14.5" r="1"/>'
    ),
    "clientes": (
        '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/>'
        '<path d="M16 4.6a3.5 3.5 0 0 1 0 6.8"/><path d="M18 14.3c2.2.7 3.5 2.6 3.5 5.7"/>'
    ),
    "usuario": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
    "producto": (
        '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="M3 8l9 5 9-5"/><path d="M12 13v8"/>'
    ),
    "compras": (
        '<path d="M2 6h11v10H2z"/><path d="M13 9h4l4 4v3h-8"/>'
        '<circle cx="6.5" cy="18" r="2"/><circle cx="17.5" cy="18" r="2"/>'
    ),
    "inventario": (
        '<path d="M4 4h16v5H4z"/><path d="M5 9v11h14V9"/><path d="M10 13h4"/>'
    ),
    "reportes": (
        '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M9 16v-5"/>'
        '<path d="M14 16V7"/><path d="M19 16v-8"/>'
    ),
    "configuracion": (
        '<path d="M4 6h9"/><path d="M19 6h1"/><circle cx="16" cy="6" r="2.2"/>'
        '<path d="M4 12h1"/><path d="M11 12h9"/><circle cx="8" cy="12" r="2.2"/>'
        '<path d="M4 18h9"/><path d="M19 18h1"/><circle cx="16" cy="18" r="2.2"/>'
    ),
    "salir": (
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
        '<path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>'
    ),
    "ticket": (
        '<path d="M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2z"/><path d="M9 8h6"/><path d="M9 12h6"/>'
    ),
    "alerta": '<path d="M12 3 2 20h20z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
    "tendencia": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "moneda": (
        '<circle cx="12" cy="12" r="9"/><path d="M14.5 9.2c-.5-.8-1.4-1.2-2.5-1.2-1.4 0-2.5.7-2.5 1.8 '
        '0 2.4 5 1.2 5 3.6 0 1.1-1.1 1.8-2.5 1.8-1.1 0-2.1-.4-2.6-1.2"/><path d="M12 6.5V8"/><path d="M12 16v1.5"/>'
    ),
    "mas": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "buscar": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "actualizar": (
        '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>'
    ),
    "papelera": (
        '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>'
        '<path d="M10 11v6"/><path d="M14 11v6"/>'
    ),
    "editar": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "tarjeta": '<rect x="2.5" y="5" width="19" height="14" rx="2"/><path d="M2.5 10h19"/><path d="M6 15h4"/>',
    "calendario": (
        '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/>'
        '<path d="M8 3v4"/><path d="M16 3v4"/>'
    ),
    "descargar": '<path d="M12 4v11"/><path d="M7 11l5 5 5-5"/><path d="M4 20h16"/>',
    "etiqueta": (
        '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1"/>'
    ),
}

_CABECERA = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="{grosor}" stroke-linecap="round" stroke-linejoin="round">'
)

# Se dibuja al doble de tamaño y se marca con ratio 2 para que quede nítido en pantallas con escala.
_FACTOR = 2


def nombres_disponibles() -> list[str]:
    return sorted(_TRAZOS)


def pixmap_icono(nombre: str, color: str, tam: int = 20, grosor: float = 1.8) -> QPixmap:
    """Pinta el ícono `nombre` con `color` (ej. '#ffffff') y lo devuelve como QPixmap
    de tam x tam (lógicos). Si el nombre no existe devuelve un pixmap vacío."""
    lado = tam * _FACTOR
    pixmap = QPixmap(lado, lado)
    pixmap.fill(Qt.transparent)
    cuerpo = _TRAZOS.get(nombre)
    if cuerpo is None:
        return pixmap
    svg = _CABECERA.format(color=color, grosor=grosor) + cuerpo + "</svg>"
    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.Antialiasing, True)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(pintor)
    pintor.end()
    pixmap.setDevicePixelRatio(_FACTOR)
    return pixmap


def icono(nombre: str, color: str, tam: int = 20, grosor: float = 1.8) -> QIcon:
    """QIcon de un solo color."""
    return QIcon(pixmap_icono(nombre, color, tam, grosor))


def icono_menu(nombre: str, color_normal: str, color_activo: str, color_marcado: str,
               tam: int = 20) -> QIcon:
    """QIcon para botones del menú: color distinto en reposo, al pasar el mouse
    (Active) y cuando el botón está marcado (checked = estado On)."""
    resultado = QIcon()
    normal = pixmap_icono(nombre, color_normal, tam)
    activo = pixmap_icono(nombre, color_activo, tam)
    marcado = pixmap_icono(nombre, color_marcado, tam)
    resultado.addPixmap(normal, QIcon.Normal, QIcon.Off)
    resultado.addPixmap(activo, QIcon.Active, QIcon.Off)
    resultado.addPixmap(marcado, QIcon.Normal, QIcon.On)
    resultado.addPixmap(marcado, QIcon.Active, QIcon.On)
    return resultado
