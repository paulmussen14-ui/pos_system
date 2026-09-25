"""Gráfico de barras horizontales simple (sin QtCharts), para rankings cortos
del dashboard como "productos más vendidos". Mismo enfoque que line_chart.py
y donut_chart.py: se dibuja a mano con QPainter, sin dependencias nuevas.
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtCore import Qt, QRectF

PALETA = ["#2563eb", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4", "#84cc16"]


class _BarCanvas(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._barras: list[tuple[str, float]] = []
        self._formateador = str
        self._color_texto = QColor("#6b7280")
        self._color_fondo_barra = QColor("#e5e7eb")

    def set_datos(self, barras: list[tuple[str, float]], formateador=str) -> None:
        self._barras = barras
        self._formateador = formateador
        alto_fila = 28
        self.setMinimumHeight(max(60, alto_fila * len(barras) + 16))
        self.update()

    def set_colores(self, texto: str, fondo_barra: str) -> None:
        self._color_texto = QColor(texto)
        self._color_fondo_barra = QColor(fondo_barra)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self._barras:
            painter.setPen(self._color_texto)
            painter.drawText(self.rect(), Qt.AlignCenter, "Sin datos todavía")
            return

        fuente = QFont(self.font())
        fuente.setPointSize(9)
        painter.setFont(fuente)

        maximo = max(v for _, v in self._barras) or 1.0
        ancho_etiqueta = 130
        ancho_valor = 70
        margen = 6
        alto_fila = 28
        alto_barra = 14

        ancho_disponible = self.width() - ancho_etiqueta - ancho_valor - margen * 2
        ancho_disponible = max(ancho_disponible, 20)

        for i, (etiqueta, valor) in enumerate(self._barras):
            y = margen + i * alto_fila
            color = QColor(PALETA[i % len(PALETA)])

            # Etiqueta (nombre del producto), recortada si es muy larga.
            painter.setPen(self._color_texto)
            metricas = painter.fontMetrics()
            etiqueta_corta = metricas.elidedText(etiqueta, Qt.ElideRight, ancho_etiqueta - 8)
            painter.drawText(
                QRectF(0, y, ancho_etiqueta, alto_fila),
                Qt.AlignVCenter | Qt.AlignLeft,
                etiqueta_corta,
            )

            # Fondo de la barra (ancho total disponible).
            x0 = ancho_etiqueta
            y_barra = y + (alto_fila - alto_barra) / 2
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._color_fondo_barra)
            painter.drawRoundedRect(QRectF(x0, y_barra, ancho_disponible, alto_barra), 4, 4)

            # Barra proporcional al valor.
            ancho_barra = max(ancho_disponible * (valor / maximo), 3)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x0, y_barra, ancho_barra, alto_barra), 4, 4)

            # Valor al final de la fila.
            painter.setPen(self._color_texto)
            painter.drawText(
                QRectF(x0 + ancho_disponible + 8, y, ancho_valor - 8, alto_fila),
                Qt.AlignVCenter | Qt.AlignRight,
                self._formateador(valor),
            )


class BarChartWidget(QFrame):
    """Tarjeta con título + ranking de barras horizontales. Uso:
    chart = BarChartWidget("Productos más vendidos (este mes)")
    chart.set_datos([("Coca Cola 500ml", 120), ("Pan francés", 95)], formateador=lambda v: f"{v:.0f}")
    """

    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        label_titulo = QLabel(titulo)
        label_titulo.setProperty("class", "cardTitle")
        layout.addWidget(label_titulo)

        self._canvas = _BarCanvas()
        layout.addWidget(self._canvas)

        self._label_vacio = None

    def set_datos(self, barras: list[tuple[str, float]], formateador=str) -> None:
        self._canvas.set_datos(barras, formateador)

    def set_modo_oscuro(self, oscuro: bool) -> None:
        if oscuro:
            self._canvas.set_colores(texto="#9ca3af", fondo_barra="#374151")
        else:
            self._canvas.set_colores(texto="#6b7280", fondo_barra="#e5e7eb")
