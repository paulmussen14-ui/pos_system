"""Encabezado estándar de página: título y subtítulo a la izquierda, acciones a la derecha."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel

from ui.tokens import ESPACIO_SM


class PageHeader(QWidget):

    def __init__(self, titulo: str, subtitulo: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pageHeader")

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(ESPACIO_SM)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        self.label_titulo = QLabel(titulo)
        self.label_titulo.setObjectName("pageTitle")
        textos.addWidget(self.label_titulo)
        self.label_subtitulo = QLabel(subtitulo)
        self.label_subtitulo.setObjectName("pageSubtitle")
        self.label_subtitulo.setVisible(bool(subtitulo))
        textos.addWidget(self.label_subtitulo)
        raiz.addLayout(textos)
        raiz.addStretch()

        self._acciones = QHBoxLayout()
        self._acciones.setSpacing(ESPACIO_SM)
        raiz.addLayout(self._acciones)

    def set_subtitulo(self, texto: str) -> None:
        self.label_subtitulo.setText(texto)
        self.label_subtitulo.setVisible(bool(texto))

    def agregar_accion(self, widget: QWidget) -> None:
        """Agrega un botón de acción a la derecha (el primero agregado queda más a la izquierda)."""
        self._acciones.addWidget(widget)
