"""Página de gestión de productos (CRUD + historial de costos).

La consulta a la base de datos se hace en un hilo aparte (Worker), igual que
en ventas_page.py, para que la ventana no se congele con muchos productos.

Reglas para que los cambios NO oculten datos:
- Mientras carga, la tabla conserva las filas anteriores (no se vacía).
- Si la consulta falla, se muestra un mensaje rojo y se conservan las filas.
- Una etiqueta siempre dice cuántos productos se están mostrando.
- Si llegan dos respuestas, solo se aplica la de la última consulta.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtCore import QTimer, QThreadPool

from services.producto_service import ProductoService, ProductoError
from services.configuracion_service import ConfiguracionService
from ui.productos.producto_form_dialog import ProductoFormDialog
from utils.validators import formatear_moneda
from utils.worker import Worker
from utils.logger import logger


class ProductosPage(QWidget):

    ANCHO_COLUMNA_ACCIONES = 280

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.producto_service = ProductoService()
        self.config_service = ConfiguracionService()

        # Cada consulta lleva un número. Solo se aplica la respuesta de la
        # consulta con el número más alto (la más reciente).
        self._numero_consulta = 0

        # Debounce: espera 300ms sin escribir antes de consultar.
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

        # Línea de estado: cargando / cuántos productos se muestran / error.
        self.label_estado = QLabel("")
        self.label_estado.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self.label_estado)

    def _on_texto_busqueda(self) -> None:
        """Reinicia el temporizador de debounce en cada tecla."""
        self._timer_busqueda.start()

    # ------------------------------------------------------ Carga ----

    def actualizar(self) -> None:
        self._numero_consulta += 1
        numero = self._numero_consulta
        texto = self.input_busqueda.text()

        self.label_estado.setStyleSheet("color: #6b7280; font-size: 12px;")
        self.label_estado.setText("Cargando...")

        worker = Worker(self.producto_service.listar, texto)
        worker.signals.finished.connect(
            lambda productos, n=numero, t=texto: self._on_productos_listos(n, t, productos)
        )
        worker.signals.error.connect(
            lambda mensaje, n=numero: self._on_error_carga(n, mensaje)
        )
        QThreadPool.globalInstance().start(worker)

    def _on_error_carga(self, numero: int, mensaje: str) -> None:
        if numero != self._numero_consulta:
            return
        logger.error("Error cargando productos: %s", mensaje)
        # No se toca la tabla: se conservan las filas que ya estaban.
        self.label_estado.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: 600;")
        self.label_estado.setText(
            "No se pudo cargar la lista de productos. "
            "Los datos mostrados pueden estar desactualizados."
        )

    def _on_productos_listos(self, numero: int, texto: str, productos) -> None:
        if numero != self._numero_consulta:
            return

        moneda = self.config_service.obtener().get("moneda", "S/")

        # Se apaga el repintado mientras se llenan las filas para que
        # la tabla no se redibuje en cada celda.
        self.tabla.setUpdatesEnabled(False)
        try:
            self.tabla.setRowCount(len(productos))
            for fila, p in enumerate(productos):
                self._llenar_fila(fila, p, moneda)
        finally:
            self.tabla.setUpdatesEnabled(True)

        if len(productos) > 0:
            self.label_estado.setText(f"Mostrando {len(productos)} producto(s)")
        elif texto.strip():
            self.label_estado.setText(f"Sin resultados para '{texto}'")
        else:
            self.label_estado.setText("No hay productos registrados")

    def _llenar_fila(self, fila: int, p, moneda: str) -> None:
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

    # ---------------------------------------------------- Acciones ----

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