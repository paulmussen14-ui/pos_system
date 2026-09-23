"""Gráfico circular (donut) simple, sin QtCharts, con leyenda.

Pensado para desgloses cortos (métodos de pago, categorías), no para
docenas de segmentos.
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy
)
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtCore import Qt, QRectF

from utils.validators import formatear_moneda

PALETA = ["#2563eb", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4", "#84cc16"]


class _DonutCanvas(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(140, 140)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._segmentos: list[tuple[str, float]] = []
        self._moneda = "S/"
        self._color_fondo_anillo = QColor("#e5e7eb")
        self._color_texto = QColor("#111827")

    def set_datos(self, segmentos: list[tuple[str, float]], moneda: str = "S/") -> None:
        self._segmentos = segmentos
        self._moneda = moneda
        self.update()

    def set_colores(self, fondo_anillo: str, texto: str) -> None:
        self._color_fondo_anillo = QColor(fondo_anillo)
        self._color_texto = QColor(texto)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        lado = min(self.width(), self.height()) - 8
        rect = QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        grosor = max(lado * 0.18, 10)

        total = sum(v for _, v in self._segmentos)

        pen = QPen(self._color_fondo_anillo, grosor)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)
        painter.drawArc(rect.adjusted(grosor / 2, grosor / 2, -grosor / 2, -grosor / 2), 0, 360 * 16)

        if total > 0:
            angulo_inicio = 90 * 16
            for i, (_, valor) in enumerate(self._segmentos):
                color = QColor(PALETA[i % len(PALETA)])
                pen = QPen(color, grosor)
                pen.setCapStyle(Qt.FlatCap)
                painter.setPen(pen)
                angulo_barrido = -int(360 * 16 * (valor / total))
                painter.drawArc(
                    rect.adjusted(grosor / 2, grosor / 2, -grosor / 2, -grosor / 2),
                    angulo_inicio, angulo_barrido,
                )
                angulo_inicio += angulo_barrido

        painter.setPen(self._color_texto)
        texto = formatear_moneda(total, self._moneda) if total else "Sin\nventas"
        painter.drawText(rect, Qt.AlignCenter, texto)


class DonutChartWidget(QFrame):
    """Tarjeta con título + donut + leyenda. Uso:
    chart = DonutChartWidget("Ventas por método de pago (este mes)")
    chart.set_datos([("Efectivo", 350.0), ("Yape/Plin", 120.0)])
    """

    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")

        layout_principal = QVBoxLayout(self)
        layout_principal.setSpacing(10)

        label_titulo = QLabel(titulo)
        label_titulo.setProperty("class", "cardTitle")
        layout_principal.addWidget(label_titulo)

        fila = QHBoxLayout()
        fila.setSpacing(16)

        self._canvas = _DonutCanvas()
        fila.addWidget(self._canvas)

        self._layout_leyenda = QVBoxLayout()
        self._layout_leyenda.setSpacing(6)
        self._layout_leyenda.addStretch()
        fila.addLayout(self._layout_leyenda, 1)

        layout_principal.addLayout(fila)

    def set_datos(self, segmentos: list[tuple[str, float]], moneda: str = "S/") -> None:
        self._canvas.set_datos(segmentos, moneda)
        self._reconstruir_leyenda(segmentos, moneda)

    def set_modo_oscuro(self, oscuro: bool) -> None:
        if oscuro:
            self._canvas.set_colores(fondo_anillo="#374151", texto="#e5e7eb")
        else:
            self._canvas.set_colores(fondo_anillo="#e5e7eb", texto="#111827")

    def _reconstruir_leyenda(self, segmentos: list[tuple[str, float]], moneda: str = "S/") -> None:
        # Limpiar leyenda anterior (menos el stretch final).
        while self._layout_leyenda.count() > 1:
            item = self._layout_leyenda.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        total = sum(v for _, v in segmentos) or 1.0
        for i, (nombre, valor) in enumerate(segmentos):
            color = PALETA[i % len(PALETA)]
            porcentaje = round(valor / total * 100)
            fila_item = QLabel(
                f'<span style="color:{color};">●</span> {nombre} '
                f'<span style="color:#9ca3af;">— {formatear_moneda(valor, moneda)} ({porcentaje}%)</span>'
            )
            self._layout_leyenda.insertWidget(self._layout_leyenda.count() - 1, fila_item)

        if not segmentos:
            self._layout_leyenda.insertWidget(0, QLabel("Todavía no hay ventas este mes."))