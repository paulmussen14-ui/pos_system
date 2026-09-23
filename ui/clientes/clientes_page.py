"""Página de Clientes: alta, edición y consulta de historial de compras."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFormLayout,
    QMessageBox
)
from PySide6.QtCore import QTimer

from services.cliente_service import ClienteService, ClienteError
from utils.validators import formatear_moneda

# Mismo estilo de tabla usado en Ventas y Compras, para mantener
# consistencia visual (encabezados con separación) en toda la app.
# El encabezado usa un tono azul-gris suave en vez de blanco/gris plano.
ESTILO_TABLA = """
    QTableWidget {
        background-color: transparent;
        color: #e5e7eb;

        border: 1px solid #3d414a;

        selection-background-color: #2f6fed;
        selection-color: white;
    }

    QHeaderView {
        background-color: transparent;
    }

    QHeaderView::section {
        background-color: #2a2e36;
        color: #ffffff;

        padding: 9px 12px;

        border: none;
        border-bottom: 2px solid #3b82f6;

        font-weight: 600;
    }

    QTableWidget::item {
        padding: 6px 10px;
        border: none;
        background-color: transparent;
    }

    QTableWidget::item:selected {
        background-color: #2f6fed;
        color: white;
    }
"""


class ClienteFormDialog(QDialog):

    def __init__(self, cliente=None, parent=None):
        super().__init__(parent)
        self.cliente_service = ClienteService()
        self.cliente = cliente
        self.setWindowTitle("Editar cliente" if cliente else "Nuevo cliente")
        self.resize(360, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.input_nombre = QLineEdit()
        self.input_telefono = QLineEdit()
        self.input_direccion = QLineEdit()

        form.addRow("Nombre:", self.input_nombre)
        form.addRow("Teléfono:", self.input_telefono)
        form.addRow("Dirección:", self.input_direccion)
        layout.addLayout(form)

        if cliente:
            self.input_nombre.setText(cliente.nombre)
            self.input_telefono.setText(cliente.telefono or "")
            self.input_direccion.setText(cliente.direccion or "")

        botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "secondary")
        btn_cancelar.clicked.connect(self.reject)
        btn_guardar = QPushButton("Guardar")
        btn_guardar.clicked.connect(self._guardar)
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        layout.addLayout(botones)

    def _guardar(self) -> None:
        try:
            if self.cliente:
                self.cliente_service.actualizar(
                    self.cliente.id, self.input_nombre.text(),
                    self.input_telefono.text(), self.input_direccion.text(),
                )
            else:
                self.cliente_service.crear(
                    self.input_nombre.text(),
                    self.input_telefono.text(), self.input_direccion.text(),
                )
        except ClienteError as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        self.accept()


class ClientesPage(QWidget):

    ANCHO_COLUMNA_ACCIONES = 260

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.cliente_service = ClienteService()

        # Debounce: evita disparar una consulta a la BD por cada tecla
        # presionada. Se espera 300ms de inactividad antes de buscar.
        self._timer_busqueda = QTimer(self)
        self._timer_busqueda.setSingleShot(True)
        self._timer_busqueda.setInterval(300)
        self._timer_busqueda.timeout.connect(self.actualizar)

        self._construir_ui()
        self.actualizar()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        cabecera = QHBoxLayout()
        titulo = QLabel("Clientes")
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        cabecera.addWidget(titulo)
        cabecera.addStretch()

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setPlaceholderText("Buscar cliente...")
        self.input_busqueda.setFixedWidth(240)
        self.input_busqueda.textChanged.connect(self._on_texto_busqueda)
        cabecera.addWidget(self.input_busqueda)

        btn_nuevo = QPushButton("+ Nuevo cliente")
        btn_nuevo.clicked.connect(self._nuevo_cliente)
        cabecera.addWidget(btn_nuevo)
        layout.addLayout(cabecera)

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Nombre", "Teléfono", "Dirección", "Acciones"])
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tabla.setColumnWidth(3, self.ANCHO_COLUMNA_ACCIONES)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setStyleSheet(ESTILO_TABLA)
        layout.addWidget(self.tabla)

    def _on_texto_busqueda(self) -> None:
        """Reinicia el temporizador de debounce en cada tecla."""
        self._timer_busqueda.start()

    def actualizar(self) -> None:
        clientes = self.cliente_service.listar(self.input_busqueda.text())
        self.tabla.setRowCount(len(clientes))

        for fila, c in enumerate(clientes):
            self.tabla.setItem(fila, 0, QTableWidgetItem(c.nombre))
            self.tabla.setItem(fila, 1, QTableWidgetItem(c.telefono or "-"))
            self.tabla.setItem(fila, 2, QTableWidgetItem(c.direccion or "-"))

            widget_acciones = QWidget()
            layout_acciones = QHBoxLayout(widget_acciones)
            layout_acciones.setContentsMargins(6, 4, 6, 4)
            layout_acciones.setSpacing(8)

            btn_historial = QPushButton("Historial")
            btn_historial.setProperty("class", "secondary")
            btn_historial.setMinimumHeight(32)
            btn_historial.clicked.connect(lambda _, cli=c: self._ver_historial(cli))

            btn_editar = QPushButton("Editar")
            btn_editar.setProperty("class", "secondary")
            btn_editar.setMinimumHeight(32)
            btn_editar.clicked.connect(lambda _, cli=c: self._editar_cliente(cli))

            layout_acciones.addWidget(btn_historial)
            layout_acciones.addWidget(btn_editar)
            self.tabla.setRowHeight(fila, 46)
            self.tabla.setCellWidget(fila, 3, widget_acciones)

    def _nuevo_cliente(self) -> None:
        dialogo = ClienteFormDialog(parent=self)
        if dialogo.exec():
            self.actualizar()

    def _editar_cliente(self, cliente) -> None:
        dialogo = ClienteFormDialog(cliente=cliente, parent=self)
        if dialogo.exec():
            self.actualizar()

    def _ver_historial(self, cliente) -> None:
        ventas = self.cliente_service.historial_compras(cliente.id)

        dialogo = QDialog(self)
        dialogo.setWindowTitle(f"Historial de {cliente.nombre}")
        dialogo.resize(420, 360)
        layout = QVBoxLayout(dialogo)

        tabla = QTableWidget(0, 3)
        tabla.setHorizontalHeaderLabels(["Venta #", "Fecha", "Total"])
        header = tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        tabla.verticalHeader().setVisible(False)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        tabla.setAlternatingRowColors(True)
        tabla.setStyleSheet(ESTILO_TABLA)
        layout.addWidget(tabla)

        if ventas:
            tabla.setRowCount(len(ventas))
            for fila, v in enumerate(ventas):
                tabla.setItem(fila, 0, QTableWidgetItem(str(v["id"])))
                tabla.setItem(fila, 1, QTableWidgetItem(str(v["fecha"])))
                tabla.setItem(fila, 2, QTableWidgetItem(formatear_moneda(v["total"])))
                tabla.setRowHeight(fila, 34)
        else:
            layout.addWidget(QLabel("Este cliente aún no tiene compras registradas."))

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(btn_cerrar)

        dialogo.exec()