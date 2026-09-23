"""Página de gestión de productos (CRUD + historial de costos)."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtCore import QTimer

from services.producto_service import ProductoService, ProductoError
from services.configuracion_service import ConfiguracionService
from ui.productos.producto_form_dialog import ProductoFormDialog
from utils.validators import formatear_moneda


class ProductosPage(QWidget):

    ANCHO_COLUMNA_ACCIONES = 280

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.producto_service = ProductoService()
        self.config_service = ConfiguracionService()

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
        titulo = QLabel("Productos")
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        cabecera.addWidget(titulo)
        cabecera.addStretch()

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setPlaceholderText("Buscar producto por nombre...")
        self.input_busqueda.setFixedWidth(260)
        self.input_busqueda.textChanged.connect(self._on_texto_busqueda)
        cabecera.addWidget(self.input_busqueda)

        btn_nuevo = QPushButton("+ Nuevo producto")
        btn_nuevo.clicked.connect(self._nuevo_producto)
        cabecera.addWidget(btn_nuevo)

        layout.addLayout(cabecera)

        self.tabla = QTableWidget(0, 8)
        self.tabla.setHorizontalHeaderLabels(
            ["Nombre", "Categoría", "Marca", "Precio venta", "Stock", "Stock mín.", "Estado", "Acciones"]
        )
        header = self.tabla.horizontalHeader()
        for col in range(7):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        self.tabla.setColumnWidth(7, self.ANCHO_COLUMNA_ACCIONES)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.tabla)

    def _on_texto_busqueda(self) -> None:
        """Reinicia el temporizador de debounce en cada tecla."""
        self._timer_busqueda.start()

    def actualizar(self) -> None:
        config = self.config_service.obtener()
        moneda = config.get("moneda", "S/")
        productos = self.producto_service.listar(self.input_busqueda.text())

        self.tabla.setRowCount(len(productos))
        for fila, p in enumerate(productos):
            self.tabla.setItem(fila, 0, QTableWidgetItem(p.nombre))
            self.tabla.setItem(fila, 1, QTableWidgetItem(p.categoria_nombre or "-"))
            self.tabla.setItem(fila, 2, QTableWidgetItem(p.marca or "-"))
            self.tabla.setItem(fila, 3, QTableWidgetItem(formatear_moneda(p.precio_venta_actual, moneda)))
            self.tabla.setItem(fila, 4, QTableWidgetItem(f"{p.stock_actual} {p.unidad_medida}"))
            self.tabla.setItem(fila, 5, QTableWidgetItem(str(p.stock_minimo)))

            if p.agotado:
                estado = "Agotado"
            elif p.stock_bajo:
                estado = "Stock bajo"
            else:
                estado = "OK"
            self.tabla.setItem(fila, 6, QTableWidgetItem(estado))

            widget_acciones = QWidget()
            layout_acciones = QHBoxLayout(widget_acciones)
            layout_acciones.setContentsMargins(6, 4, 6, 4)
            layout_acciones.setSpacing(8)

            btn_editar = QPushButton("Editar")
            btn_editar.setProperty("class", "secondary")
            btn_editar.setMinimumHeight(32)
            btn_editar.clicked.connect(lambda _, prod=p: self._editar_producto(prod))

            btn_eliminar = QPushButton("Desactivar")
            btn_eliminar.setProperty("class", "danger")
            btn_eliminar.setMinimumHeight(32)
            btn_eliminar.clicked.connect(lambda _, prod=p: self._desactivar_producto(prod))

            layout_acciones.addWidget(btn_editar)
            layout_acciones.addWidget(btn_eliminar)
            self.tabla.setRowHeight(fila, 46)
            self.tabla.setCellWidget(fila, 7, widget_acciones)

    def _nuevo_producto(self) -> None:
        dialogo = ProductoFormDialog(producto=None, parent=self)
        if dialogo.exec():
            self.actualizar()

    def _editar_producto(self, producto) -> None:
        dialogo = ProductoFormDialog(producto=producto, parent=self)
        if dialogo.exec():
            self.actualizar()

    def _desactivar_producto(self, producto) -> None:
        respuesta = QMessageBox.question(
            self, "Confirmar", f"¿Desactivar el producto '{producto.nombre}'?"
        )
        if respuesta == QMessageBox.Yes:
            try:
                self.producto_service.desactivar_producto(producto.id)
                self.actualizar()
            except ProductoError as e:
                QMessageBox.warning(self, "Error", str(e))