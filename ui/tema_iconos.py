"""Tema visual: une el tema base (light.qss / dark.qss), la capa de mejoras
(mejoras_claro.qss / mejoras_oscuro.qss) y la capa ERP (ui/estilos_erp.py) y dibuja los íconos pequeños que esa
capa necesita (palomita de los checkbox, punto de los radio, flechas de los
desplegables y de los campos numéricos).

Los íconos se dibujan con Qt al aplicar el tema y se guardan como PNG en
APP_DATA_DIR/iconos_tema (el QSS solo puede apuntar a archivos). Así no hay
imágenes que empaquetar y los colores siempre coinciden con el tema.

La capa de mejoras va DESPUÉS del tema base: si una regla se repite, gana la
de la capa; y lo que la capa no toca, se queda como está en el tema base.
Si algo falla (falta el archivo de la capa, no se pueden dibujar los íconos),
se usa solo el tema base y el error queda en el log.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

from config import APP_DATA_DIR, STYLES_DIR
from ui.estilos_erp import generar_capa_erp
from ui.tokens import recolorear_qss
from utils.logger import logger

CARPETA_ICONOS = APP_DATA_DIR / "iconos_tema"

# Color de las flechas según el tema (gris que se lee bien sobre el fondo de los campos).
COLOR_FLECHA = {"claro": "#6b7280", "oscuro": "#9ca3af"}

TAM_PALOMITA = 16   # = ancho/alto del indicador de checkbox/radio en la capa
TAM_FLECHA = 12


def _trazo(color: str, grosor: float) -> QPen:
    pen = QPen(QColor(color), grosor)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _dibujar_palomita(p: QPainter, s: int) -> None:
    p.setPen(_trazo("#ffffff", 2.0))
    ruta = QPainterPath(QPointF(s * 0.25, s * 0.53))
    ruta.lineTo(s * 0.43, s * 0.70)
    ruta.lineTo(s * 0.76, s * 0.32)
    p.drawPath(ruta)


def _dibujar_punto(p: QPainter, s: int) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    radio = s * 0.22
    p.drawEllipse(QRectF(s / 2 - radio, s / 2 - radio, radio * 2, radio * 2))


def _flecha(color: str, hacia_abajo: bool):
    def dibujar(p: QPainter, s: int) -> None:
        p.setPen(_trazo(color, 1.7))
        y_borde, y_punta = (s * 0.36, s * 0.64) if hacia_abajo else (s * 0.64, s * 0.36)
        ruta = QPainterPath(QPointF(s * 0.24, y_borde))
        ruta.lineTo(s * 0.50, y_punta)
        ruta.lineTo(s * 0.76, y_borde)
        p.drawPath(ruta)
    return dibujar


def _guardar_icono(nombre: str, tam: int, dibujar) -> Path:
    """Guarda nombre.png (tam x tam) y nombre@2x.png (para pantallas con escala
    alta; Qt elige solo el que corresponde)."""
    for factor, sufijo in ((1, ""), (2, "@2x")):
        imagen = QPixmap(tam * factor, tam * factor)
        imagen.fill(Qt.transparent)
        pintor = QPainter(imagen)
        pintor.setRenderHint(QPainter.Antialiasing, True)
        pintor.scale(factor, factor)
        dibujar(pintor, tam)
        pintor.end()
        if not imagen.save(str(CARPETA_ICONOS / f"{nombre}{sufijo}.png"), "PNG"):
            raise OSError(f"No se pudo guardar el ícono {nombre}{sufijo}.png en {CARPETA_ICONOS}")
    return CARPETA_ICONOS / f"{nombre}.png"


def preparar_iconos(tema: str) -> dict[str, str]:
    """Dibuja los íconos del tema y devuelve {marcador del QSS: ruta del PNG}."""
    CARPETA_ICONOS.mkdir(parents=True, exist_ok=True)
    color = COLOR_FLECHA.get(tema, COLOR_FLECHA["claro"])
    sufijo = "oscuro" if tema == "oscuro" else "claro"
    rutas = {
        "{{ICONO_PALOMITA}}": _guardar_icono("palomita", TAM_PALOMITA, _dibujar_palomita),
        "{{ICONO_PUNTO}}": _guardar_icono("punto", TAM_PALOMITA, _dibujar_punto),
        "{{ICONO_FLECHA_ABAJO}}": _guardar_icono(f"flecha_abajo_{sufijo}", TAM_FLECHA, _flecha(color, True)),
        "{{ICONO_FLECHA_ARRIBA}}": _guardar_icono(f"flecha_arriba_{sufijo}", TAM_FLECHA, _flecha(color, False)),
    }
    # En el QSS las rutas van con "/" aunque sea Windows, y entre comillas (soporta espacios).
    return {marcador: ruta.as_posix() for marcador, ruta in rutas.items()}


def componer_tema(qss_base: str, tema: str) -> str:
    """Devuelve el QSS completo: tema base + capa de mejoras (con las rutas de los
    íconos ya puestas) + capa ERP (sistema de diseño, ver ui/estilos_erp.py).
    Si una capa falla se omite y el error queda en el log; el tema base siempre se usa."""
    qss = qss_base
    nombre = "mejoras_oscuro.qss" if tema == "oscuro" else "mejoras_claro.qss"
    ruta = STYLES_DIR / nombre
    if ruta.is_file():
        try:
            mejoras = ruta.read_text(encoding="utf-8")
            for marcador, ruta_icono in preparar_iconos(tema).items():
                mejoras = mejoras.replace(marcador, ruta_icono)
            qss = qss + "\n\n" + mejoras
        except Exception:
            logger.exception("No se pudo aplicar la capa de mejoras del tema; se omite")
    # Color de marca del cliente sobre los verdes escritos a mano en el tema base y las mejoras.
    qss = recolorear_qss(qss, tema)
    try:
        qss = qss + "\n\n" + generar_capa_erp(tema)
    except Exception:
        logger.exception("No se pudo aplicar la capa ERP del tema; se omite")
    return qss
