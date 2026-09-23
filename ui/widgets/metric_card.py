"""Tarjeta reutilizable para mostrar una métrica en el dashboard."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class MetricCard(QFrame):

    def __init__(self, titulo: str, valor: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")
        self.setObjectName("metricCard")

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.label_titulo = QLabel(titulo)
        self.label_titulo.setProperty("class", "cardTitle")

        self.label_valor = QLabel(valor)
        self.label_valor.setProperty("class", "cardValue")
        self.label_valor.setAlignment(Qt.AlignLeft)

        layout.addWidget(self.label_titulo)
        layout.addWidget(self.label_valor)

    def actualizar_valor(self, nuevo_valor: str) -> None:
        self.label_valor.setText(nuevo_valor)
