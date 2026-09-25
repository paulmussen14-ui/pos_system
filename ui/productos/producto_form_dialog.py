"""Diálogo modal para crear o editar un producto."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QDoubleSpinBox, QPushButton, QHBoxLayout, QMessageBox, QInputDialog,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)

from services.producto_service import ProductoService, ProductoError


class ProductoFormDialog(QDialog):

    def __init__(self, producto=None, parent=None):
        super().__init__(parent)
        self.producto_service = ProductoService()
        self.producto = producto  # None = creación, objeto = edición
        self._construir_ui()
        self._cargar_combos()
        if self.producto:
            self._precargar_datos()

    def _construir_ui(self) -> None:
        self.setWindowTitle("Editar producto" if self.producto else "Nuevo producto")
        self.resize(520, 660)
        self.setMinimumSize(500, 600)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.input_nombre = QLineEdit()
        self.combo_categoria = QComboBox()
        btn_nueva_categoria = QPushButton("+")
        btn_nueva_categoria.setFixedWidth(30)
        btn_nueva_categoria.clicked.connect(self._crear_categoria)
        fila_categoria = QHBoxLayout()
        fila_categoria.addWidget(self.combo_categoria)
        fila_categoria.addWidget(btn_nueva_categoria)

        self.input_marca = QLineEdit()
        self.input_unidad = QLineEdit()
        self.input_unidad.setText("unidad")

        self.input_precio = QDoubleSpinBox()
        self.input_precio.setMaximum(999999)
        self.input_precio.setDecimals(2)
        self.input_precio.setPrefix("S/ ")

        self.input_stock_minimo = QDoubleSpinBox()
        self.input_stock_minimo.setMaximum(999999)

        self.combo_proveedor = QComboBox()
        btn_nuevo_proveedor = QPushButton("+")
        btn_nuevo_proveedor.setFixedWidth(30)
        btn_nuevo_proveedor.clicked.connect(self._crear_proveedor)
        fila_proveedor = QHBoxLayout()
        fila_proveedor.addWidget(self.combo_proveedor)
        fila_proveedor.addWidget(btn_nuevo_proveedor)

        form.addRow("Nombre:", self.input_nombre)
        form.addRow("Categoría:", fila_categoria)
        form.addRow("Marca:", self.input_marca)
        form.addRow("Unidad de medida:", self.input_unidad)
        form.addRow("Precio de venta:", self.input_precio)
        form.addRow("Stock mínimo:", self.input_stock_minimo)
        form.addRow("Proveedor:", fila_proveedor)

        if not self.producto:
            self.input_stock_inicial = QDoubleSpinBox()
            self.input_stock_inicial.setMaximum(999999)
            self.input_costo_inicial = QDoubleSpinBox()
            self.input_costo_inicial.setMaximum(999999)
            self.input_costo_inicial.setPrefix("S/ ")
            form.addRow("Stock inicial:", self.input_stock_inicial)
            form.addRow("Costo inicial:", self.input_costo_inicial)

        layout.addLayout(form)

        # ---- Presentaciones de venta (caja, docena, paquete, etc.) ----
        # Precio y unidad de arriba = presentación base "unidad". Aquí se
        # agregan formas extra de vender el mismo producto sin duplicarlo.
        label_presentaciones = QLabel("Presentaciones adicionales (caja, docena, paquete...):")
        label_presentaciones.setStyleSheet("font-weight: 600; margin-top: 6px;")
        layout.addWidget(label_presentaciones)

        ayuda_presentaciones = QLabel(
            "La unidad de arriba ya es una presentación (\"Unidad\"). Agrega aquí "
            "otras formas de vender este producto: cuántas unidades equivale y a "
            "qué precio se vende esa presentación completa."
        )
        ayuda_presentaciones.setWordWrap(True)
        ayuda_presentaciones.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(ayuda_presentaciones)

        self.tabla_presentaciones = QTableWidget(0, 3)
        self.tabla_presentaciones.setHorizontalHeaderLabels(
            ["Nombre (ej. Caja)", "Equivale a (unidades)", "Precio de venta"]
        )
        header_pres = self.tabla_presentaciones.horizontalHeader()
        header_pres.setSectionResizeMode(0, QHeaderView.Stretch)
        header_pres.setSectionResizeMode(1, QHeaderView.Interactive)
        header_pres.setSectionResizeMode(2, QHeaderView.Interactive)
        header_pres.setMinimumSectionSize(120)
        self.tabla_presentaciones.setColumnWidth(1, 140)
        self.tabla_presentaciones.setColumnWidth(2, 130)
        self.tabla_presentaciones.verticalHeader().setVisible(False)
        # Alto de fila suficiente para que el editor de texto no se vea
        # recortado mientras se escribe (antes usaba el alto por defecto,
        # demasiado angosto para ver lo que se tipea).
        self.tabla_presentaciones.verticalHeader().setDefaultSectionSize(40)
        self.tabla_presentaciones.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.tabla_presentaciones.setMinimumHeight(160)
        layout.addWidget(self.tabla_presentaciones)

        fila_botones_presentaciones = QHBoxLayout()
        btn_agregar_presentacion = QPushButton("+ Agregar presentación")
        btn_agregar_presentacion.setProperty("class", "secondary")
        btn_agregar_presentacion.clicked.connect(self._agregar_fila_presentacion)
        fila_botones_presentaciones.addWidget(btn_agregar_presentacion)

        btn_quitar_presentacion = QPushButton("Quitar seleccionada")
        btn_quitar_presentacion.setProperty("class", "secondary")
        btn_quitar_presentacion.clicked.connect(self._quitar_fila_presentacion)
        fila_botones_presentaciones.addWidget(btn_quitar_presentacion)
        fila_botones_presentaciones.addStretch()
        layout.addLayout(fila_botones_presentaciones)

        botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "secondary")
        btn_cancelar.clicked.connect(self.reject)
        btn_guardar = QPushButton("Guardar")
        btn_guardar.clicked.connect(self._guardar)
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        layout.addLayout(botones)

    def _cargar_combos(self) -> None:
        self.combo_categoria.addItem("Sin categoría", None)
        for categoria in self.producto_service.categorias():
            self.combo_categoria.addItem(categoria["nombre"], categoria["id"])

        self.combo_proveedor.addItem("Sin proveedor", None)
        for proveedor in self.producto_service.proveedores():
            self.combo_proveedor.addItem(proveedor["nombre"], proveedor["id"])

    def _crear_categoria(self) -> None:
        nombre, ok = QInputDialog.getText(self, "Nueva categoría", "Nombre de la categoría:")
        if ok and nombre.strip():
            try:
                nueva_id = self.producto_service.crear_categoria(nombre)
                self.combo_categoria.addItem(nombre.strip(), nueva_id)
                self.combo_categoria.setCurrentIndex(self.combo_categoria.count() - 1)
            except ProductoError as e:
                QMessageBox.warning(self, "Error", str(e))

    def _crear_proveedor(self) -> None:
        nombre, ok = QInputDialog.getText(self, "Nuevo proveedor", "Nombre del proveedor:")
        if ok and nombre.strip():
            try:
                nueva_id = self.producto_service.crear_proveedor(nombre)
                self.combo_proveedor.addItem(nombre.strip(), nueva_id)
                self.combo_proveedor.setCurrentIndex(self.combo_proveedor.count() - 1)
            except ProductoError as e:
                QMessageBox.warning(self, "Error", str(e))

    def _agregar_fila_presentacion(self, nombre: str = "", cantidad: str = "", precio: str = "") -> None:
        fila = self.tabla_presentaciones.rowCount()
        self.tabla_presentaciones.insertRow(fila)
        self.tabla_presentaciones.setItem(fila, 0, QTableWidgetItem(nombre))
        self.tabla_presentaciones.setItem(fila, 1, QTableWidgetItem(cantidad))
        self.tabla_presentaciones.setItem(fila, 2, QTableWidgetItem(precio))
        self.tabla_presentaciones.setRowHeight(fila, 40)

    def _quitar_fila_presentacion(self) -> None:
        fila = self.tabla_presentaciones.currentRow()
        if fila >= 0:
            self.tabla_presentaciones.removeRow(fila)

    def _leer_filas_presentaciones(self) -> list[dict]:
        filas = []
        for fila in range(self.tabla_presentaciones.rowCount()):
            def texto(col):
                item = self.tabla_presentaciones.item(fila, col)
                return item.text().strip() if item else ""

            filas.append({
                "nombre": texto(0),
                "cantidad_unidades": texto(1),
                "precio": texto(2),
            })
        return filas

    def _precargar_datos(self) -> None:
        p = self.producto
        self.input_nombre.setText(p.nombre)
        self.input_marca.setText(p.marca or "")
        self.input_unidad.setText(p.unidad_medida)
        self.input_precio.setValue(p.precio_venta_actual)
        self.input_stock_minimo.setValue(p.stock_minimo)

        if p.categoria_id:
            idx = self.combo_categoria.findData(p.categoria_id)
            if idx >= 0:
                self.combo_categoria.setCurrentIndex(idx)
        if p.proveedor_id:
            idx = self.combo_proveedor.findData(p.proveedor_id)
            if idx >= 0:
                self.combo_proveedor.setCurrentIndex(idx)

        for presentacion in self.producto_service.presentaciones(p.id):
            self._agregar_fila_presentacion(
                presentacion.nombre,
                str(presentacion.cantidad_unidades),
                str(presentacion.precio),
            )

    def _guardar(self) -> None:
        try:
            if self.producto:
                self.producto_service.actualizar_producto(
                    self.producto.id,
                    self.input_nombre.text(),
                    self.combo_categoria.currentData(),
                    self.input_marca.text(),
                    self.input_unidad.text(),
                    self.input_precio.value(),
                    self.input_stock_minimo.value(),
                    self.combo_proveedor.currentData(),
                )
                producto_id = self.producto.id
            else:
                producto_id = self.producto_service.crear_producto(
                    self.input_nombre.text(),
                    self.combo_categoria.currentData(),
                    self.input_marca.text(),
                    self.input_unidad.text(),
                    self.input_precio.value(),
                    self.input_stock_inicial.value(),
                    self.input_stock_minimo.value(),
                    self.combo_proveedor.currentData(),
                    self.input_costo_inicial.value(),
                )

            self.producto_service.guardar_presentaciones(
                producto_id, self._leer_filas_presentaciones()
            )
        except ProductoError as e:
            QMessageBox.warning(self, "No se pudo guardar", str(e))
            return

        self.accept()