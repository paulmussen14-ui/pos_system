"""Diálogo para registrar una compra con una o varias líneas de producto."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QDoubleSpinBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLabel, QCheckBox, QWidget
)
from PySide6.QtCore import QLocale

_LOCALE_PUNTO = QLocale(QLocale.English, QLocale.UnitedStates)


def _spinbox_con_punto(maximo: float = 999999, prefijo: str = "", minimo: float = 0.0) -> QDoubleSpinBox:
    """QDoubleSpinBox que siempre usa punto decimal, sin importar la
    configuración regional de Windows (que muchas veces usa coma)."""
    spin = QDoubleSpinBox()
    spin.setLocale(_LOCALE_PUNTO)
    spin.setMaximum(maximo)
    spin.setMinimum(minimo)
    if prefijo:
        spin.setPrefix(prefijo)
    return spin

from services.producto_service import ProductoService
from services.compra_service import CompraService, CompraError
from services.caja_service import CajaService
from models.compra import CompraDetalleItem
from utils.validators import formatear_moneda


class CompraFormDialog(QDialog):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.producto_service = ProductoService()
        self.compra_service = CompraService()
        self.caja_service = CajaService()
        self.lineas: list[CompraDetalleItem] = []
        self._construir_ui()
        self._cargar_combos()

    def _construir_ui(self) -> None:
        self.setWindowTitle("Nueva compra")
        self.resize(560, 560)

        layout = QVBoxLayout(self)

        form_cabecera = QFormLayout()
        self.combo_proveedor = QComboBox()
        self.input_numero_documento = QLineEdit()
        self.input_numero_documento.setText(self.compra_service.sugerir_numero_documento())
        self.input_impuesto = _spinbox_con_punto(prefijo="S/ ")

        form_cabecera.addRow("Proveedor:", self.combo_proveedor)
        form_cabecera.addRow("N° de documento:", self.input_numero_documento)
        form_cabecera.addRow("Impuesto (IGV, si aplica):", self.input_impuesto)
        layout.addLayout(form_cabecera)

        self.check_pago_efectivo = QCheckBox("Pagada al contado (se descuenta de la caja)")
        self.check_pago_efectivo.toggled.connect(self._actualizar_aviso_caja)
        layout.addWidget(self.check_pago_efectivo)

        self.label_aviso_caja = QLabel()
        self.label_aviso_caja.setWordWrap(True)
        self.label_aviso_caja.setStyleSheet("color: #92400e;")
        self.label_aviso_caja.setVisible(False)
        layout.addWidget(self.label_aviso_caja)

        # Agregar línea
        ayuda_agregar = QLabel(
            "Elige la presentación en la que estás comprando (Unidad, Caja, Docena...). "
            "La cantidad es cuántas de esa presentación compraste, y el costo es el "
            "precio de esa presentación completa (ej. el precio de 1 caja)."
        )
        ayuda_agregar.setWordWrap(True)
        ayuda_agregar.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(ayuda_agregar)

        fila_agregar = QHBoxLayout()
        self.combo_producto = QComboBox()
        self.combo_producto.currentIndexChanged.connect(self._cargar_presentaciones_producto)
        self.combo_presentacion = QComboBox()
        self.input_cantidad = _spinbox_con_punto(minimo=0.01)
        self.input_cantidad.setValue(0.01)
        self.input_costo = _spinbox_con_punto(prefijo="S/ ")
        btn_agregar = QPushButton("Agregar línea")
        btn_agregar.clicked.connect(self._agregar_linea)

        fila_agregar.addWidget(self.combo_producto)
        fila_agregar.addWidget(self.combo_presentacion)
        fila_agregar.addWidget(self.input_cantidad)
        fila_agregar.addWidget(self.input_costo)
        fila_agregar.addWidget(btn_agregar)
        layout.addLayout(fila_agregar)

        self.tabla_lineas = QTableWidget(0, 6)
        self.tabla_lineas.setHorizontalHeaderLabels(
            ["Producto", "Cantidad", "Presentación", "Costo (de la presentación)", "Subtotal", ""]
        )
        header_lineas = self.tabla_lineas.horizontalHeader()
        header_lineas.setSectionResizeMode(0, QHeaderView.Stretch)
        header_lineas.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(5, QHeaderView.Fixed)
        self.tabla_lineas.setColumnWidth(5, 110)
        self.tabla_lineas.verticalHeader().setVisible(False)
        self.tabla_lineas.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.tabla_lineas)

        self.label_total = self._crear_label_total()
        layout.addWidget(self.label_total)

        botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "secondary")
        btn_cancelar.clicked.connect(self.reject)
        btn_guardar = QPushButton("Registrar compra")
        btn_guardar.setProperty("class", "success")
        btn_guardar.clicked.connect(self._guardar)
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        layout.addLayout(botones)

    def _crear_label_total(self):
        label = QLabel("Total: S/ 0.00")
        label.setStyleSheet("font-size: 18px; font-weight: 700;")
        return label

    def _cargar_combos(self) -> None:
        self.combo_proveedor.addItem("Sin proveedor", None)
        for proveedor in self.producto_service.proveedores():
            self.combo_proveedor.addItem(proveedor["nombre"], proveedor["id"])

        self.combo_producto.clear()
        for producto in self.producto_service.listar():
            self.combo_producto.addItem(producto.nombre, producto.id)
        self._cargar_presentaciones_producto()

    def _cargar_presentaciones_producto(self) -> None:
        """Recarga el combo de presentaciones (Unidad + las que tenga el
        producto elegido) cada vez que cambia el producto seleccionado."""
        self.combo_presentacion.clear()
        self.combo_presentacion.addItem("Unidad", (1.0, "Unidad"))
        producto_id = self.combo_producto.currentData()
        if producto_id is not None:
            for p in self.producto_service.presentaciones(producto_id):
                self.combo_presentacion.addItem(
                    f"{p.nombre} (x{p.cantidad_unidades:g})", (p.cantidad_unidades, p.nombre)
                )

    def _agregar_linea(self) -> None:
        producto_id = self.combo_producto.currentData()
        if producto_id is None:
            return
        nombre = self.combo_producto.currentText()
        factor, nombre_presentacion = self.combo_presentacion.currentData() or (1.0, "Unidad")
        cantidad_presentacion = self.input_cantidad.value()
        costo_presentacion = self.input_costo.value()

        if cantidad_presentacion <= 0:
            QMessageBox.warning(self, "Error", "La cantidad debe ser mayor a cero.")
            return

        cantidad_base = cantidad_presentacion * factor
        costo_unitario_base = round(costo_presentacion / factor, 4) if factor else costo_presentacion

        self.lineas.append(CompraDetalleItem(
            producto_id=producto_id, nombre_producto=nombre, cantidad=cantidad_base,
            costo_unitario=costo_unitario_base, presentacion_nombre=nombre_presentacion,
            cantidad_presentacion=cantidad_presentacion, factor_unidades=factor,
        ))
        self._refrescar_tabla()
        self.input_cantidad.setValue(0.01)
        self.input_costo.setValue(0)

    def _refrescar_tabla(self) -> None:
        self.tabla_lineas.setRowCount(len(self.lineas))
        total = 0.0
        for fila, linea in enumerate(self.lineas):
            self.tabla_lineas.setItem(fila, 0, QTableWidgetItem(linea.nombre_producto))
            self.tabla_lineas.setItem(fila, 1, QTableWidgetItem(f"{linea.cantidad_presentacion:g}"))
            self.tabla_lineas.setItem(
                fila, 2, QTableWidgetItem(f"{linea.presentacion_nombre} (x{linea.factor_unidades:g})")
            )
            self.tabla_lineas.setItem(fila, 3, QTableWidgetItem(formatear_moneda(linea.costo_presentacion_total)))
            self.tabla_lineas.setItem(fila, 4, QTableWidgetItem(formatear_moneda(linea.subtotal)))

            contenedor_botones = QWidget()
            layout_botones = QHBoxLayout(contenedor_botones)
            layout_botones.setContentsMargins(2, 2, 2, 2)
            layout_botones.setSpacing(4)

            btn_editar = QPushButton("✎")
            btn_editar.setToolTip("Editar esta línea")
            btn_editar.setProperty("class", "secondary")
            btn_editar.setMinimumSize(32, 28)
            btn_editar.clicked.connect(lambda _, idx=fila: self._editar_linea(idx))
            layout_botones.addWidget(btn_editar)

            btn_quitar = QPushButton("✕")
            btn_quitar.setToolTip("Quitar esta línea")
            btn_quitar.setProperty("class", "danger")
            btn_quitar.setMinimumSize(32, 28)
            btn_quitar.clicked.connect(lambda _, idx=fila: self._quitar_linea(idx))
            layout_botones.addWidget(btn_quitar)

            self.tabla_lineas.setCellWidget(fila, 5, contenedor_botones)

            total += linea.subtotal
        total += self.input_impuesto.value()
        self.label_total.setText(f"Total: {formatear_moneda(total)}")

    def _quitar_linea(self, indice: int) -> None:
        if 0 <= indice < len(self.lineas):
            del self.lineas[indice]
            self._refrescar_tabla()

    def _editar_linea(self, indice: int) -> None:
        """'Editar' = recargar la línea en los campos de arriba y quitarla
        de la lista, para que el usuario la corrija y la vuelva a agregar
        con 'Agregar línea'. Así se reutiliza toda la validación existente
        sin duplicar lógica de edición en línea dentro de la tabla."""
        if not (0 <= indice < len(self.lineas)):
            return
        linea = self.lineas[indice]

        idx_producto = self.combo_producto.findData(linea.producto_id)
        if idx_producto >= 0:
            self.combo_producto.setCurrentIndex(idx_producto)

        idx_presentacion = 0
        for i in range(self.combo_presentacion.count()):
            _, nombre_i = self.combo_presentacion.itemData(i)
            if nombre_i == linea.presentacion_nombre:
                idx_presentacion = i
                break
        self.combo_presentacion.setCurrentIndex(idx_presentacion)

        self.input_cantidad.setValue(linea.cantidad_presentacion)
        self.input_costo.setValue(linea.costo_presentacion_total)

        del self.lineas[indice]
        self._refrescar_tabla()

    def _actualizar_aviso_caja(self, marcado: bool) -> None:
        if not marcado:
            self.label_aviso_caja.setVisible(False)
            return
        estado = self.caja_service.estado_actual(self.usuario.id)
        if not estado.get("abierta"):
            self.label_aviso_caja.setText(
                "⚠ No hay una caja abierta. Debes abrir la caja para registrar esta compra como pagada al contado."
            )
            self.label_aviso_caja.setVisible(True)
        else:
            self.label_aviso_caja.setVisible(False)

    def _guardar(self) -> None:
        if not self.lineas:
            QMessageBox.warning(self, "Compra vacía", "Agrega al menos un producto a la compra.")
            return
        try:
            self.compra_service.registrar_compra(
                lineas=self.lineas,
                proveedor_id=self.combo_proveedor.currentData(),
                numero_documento=self.input_numero_documento.text(),
                impuesto=self.input_impuesto.value(),
                usuario_id=self.usuario.id,
                pago_es_efectivo=self.check_pago_efectivo.isChecked(),
            )
        except CompraError as e:
            QMessageBox.warning(self, "No se pudo registrar la compra", str(e))
            return
        self.accept()