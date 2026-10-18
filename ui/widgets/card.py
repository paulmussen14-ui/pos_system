"""Tarjeta con título opcional y acciones a la derecha del título.

Es el bloque básico de contenido de todas las pantallas ERP: fondo de
superficie, borde fino y radio de 12 px (ver ui/estilos_erp.py).

Uso:
    tarjeta = Card("Productos")
    tarjeta.agregar_accion(boton)           # a la derecha del título
    tarjeta.cuerpo.addWidget(tabla, 1)      # contenido (QVBoxLayout)
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget

from ui.tokens import ESPACIO_SM, ESPACIO_MD


class Card(QFrame):

    def __init__(self, titulo: str = "", parent: QWidget | None = None, margen: int = ESPACIO_MD):
        super().__init__(parent)
        self.setObjectName("erpCard")

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(margen, margen, margen, margen)
        raiz.setSpacing(ESPACIO_SM + 4)

        self._fila_titulo = QHBoxLayout()
        self._fila_titulo.setSpacing(ESPACIO_SM)
        self.label_titulo = QLabel(titulo)
        self.label_titulo.setObjectName("cardHeading")
        self._fila_titulo.addWidget(self.label_titulo)
        self._fila_titulo.addStretch()
        raiz.addLayout(self._fila_titulo)
        self.label_titulo.setVisible(bool(titulo))

        self.cuerpo = QVBoxLayout()
        self.cuerpo.setSpacing(ESPACIO_SM)
        raiz.addLayout(self.cuerpo, 1)

    def set_titulo(self, titulo: str) -> None:
        self.label_titulo.setText(titulo)
        self.label_titulo.setVisible(bool(titulo))

    def agregar_accion(self, widget: QWidget) -> None:
        """Pone un widget (botón, badge) a la derecha de la fila del título."""
        self._fila_titulo.addWidget(widget)
