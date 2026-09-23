"""Gráfico de línea simple (sin QtCharts) para tendencias del dashboard.

Se dibuja a mano con QPainter para no depender de PySide6.QtCharts, que no
está en requirements.txt. Pensado para series cortas (7-30 puntos), como
"ventas de los últimos 7 días".
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget, QSizePolicy
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QPainterPath, QLinearGradient
from PySide6.QtCore import Qt, QPointF, QRectF


class _AreaCanvas(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._puntos: list[tuple[str, float]] = []
        self._color_linea = QColor("#2563eb")
        self._color_texto = QColor("#6b7280")
        self._color_grilla = QColor("#e5e7eb")

    def set_datos(self, puntos: list[tuple[str, float]]) -> None:
        self._puntos = puntos
        self.update()

    def set_colores(self, linea: str, texto: str, grilla: str) -> None:
        self._color_linea = QColor(linea)
        self._color_texto = QColor(texto)
        self._color_grilla = QColor(grilla)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        margen_izq, margen_der, margen_arr, margen_abj = 46, 12, 16, 26
        ancho = self.width() - margen_izq - margen_der
        alto = self.height() - margen_arr - margen_abj

        if not self._puntos or ancho <= 0 or alto <= 0:
            painter.setPen(self._color_texto)
            painter.drawText(self.rect(), Qt.AlignCenter, "Sin datos todavía")
            return

        valores = [v for _, v in self._puntos]
        val_max = max(valores) or 1.0
        val_min = 0.0

        # --- Líneas guía horizontales + etiquetas del eje Y ---
        painter.setPen(QPen(self._color_grilla, 1))
        fuente_chica = QFont(self.font())
        fuente_chica.setPointSize(8)
        painter.setFont(fuente_chica)
        pasos = 3
        for i in range(pasos + 1):
            y = margen_arr + alto - (alto * i / pasos)
            painter.setPen(QPen(self._color_grilla, 1))
            painter.drawLine(QPointF(margen_izq, y), QPointF(margen_izq + ancho, y))
            valor_linea = val_min + (val_max - val_min) * i / pasos
            painter.setPen(self._color_texto)
            painter.drawText(
                QRectF(0, y - 8, margen_izq - 6, 16),
                Qt.AlignRight | Qt.AlignVCenter,
                f"{valor_linea:,.0f}",
            )

        # --- Posición de cada punto ---
        n = len(self._puntos)
        coords = []
        for i, (_, valor) in enumerate(self._puntos):
            x = margen_izq + (ancho * i / (n - 1) if n > 1 else ancho / 2)
            y = margen_arr + alto - (alto * (valor - val_min) / (val_max - val_min or 1))
            coords.append(QPointF(x, y))

        # --- Área bajo la curva (degradado) ---
        area = QPainterPath()
        area.moveTo(coords[0].x(), margen_arr + alto)
        for p in coords:
            area.lineTo(p)
        area.lineTo(coords[-1].x(), margen_arr + alto)
        area.closeSubpath()

        degradado = QLinearGradient(0, margen_arr, 0, margen_arr + alto)
        color_area = QColor(self._color_linea)
        color_area.setAlpha(70)
        degradado.setColorAt(0, color_area)
        color_area_fin = QColor(self._color_linea)
        color_area_fin.setAlpha(0)
        degradado.setColorAt(1, color_area_fin)
        painter.fillPath(area, degradado)

        # --- Línea ---
        linea = QPainterPath()
        linea.moveTo(coords[0])
        for p in coords[1:]:
            linea.lineTo(p)
        painter.setPen(QPen(self._color_linea, 2.4))
        painter.drawPath(linea)

        # --- Puntos + etiquetas del eje X ---
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color_linea)
        for p in coords:
            painter.drawEllipse(p, 3, 3)

        painter.setPen(self._color_texto)
        for i, (etiqueta, _) in enumerate(self._puntos):
            painter.drawText(
                QRectF(coords[i].x() - 24, margen_arr + alto + 4, 48, 16),
                Qt.AlignCenter,
                etiqueta,
            )


class LineChartWidget(QFrame):
    """Tarjeta con título + gráfico de línea. Uso:
    chart = LineChartWidget("Ventas de los últimos 7 días")
    chart.set_datos([("Lun", 120.0), ("Mar", 80.0), ...])
    """

    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        label_titulo = QLabel(titulo)
        label_titulo.setProperty("class", "cardTitle")
        layout.addWidget(label_titulo)

        self._canvas = _AreaCanvas()
        layout.addWidget(self._canvas)

    def set_datos(self, puntos: list[tuple[str, float]]) -> None:
        self._canvas.set_datos(puntos)

    def set_modo_oscuro(self, oscuro: bool) -> None:
        if oscuro:
            self._canvas.set_colores(linea="#3b82f6", texto="#9ca3af", grilla="#374151")
        else:
            self._canvas.set_colores(linea="#2563eb", texto="#6b7280", grilla="#e5e7eb")