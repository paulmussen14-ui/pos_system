"""Diálogo para registrar una compra con una o varias líneas de producto."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QDoubleSpinBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLabel, QCheckBox
)

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
        self.input_impuesto = QDoubleSpinBox()
        self.input_impuesto.setMaximum(999999)
        self.input_impuesto.setPrefix("S/ ")

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
        fila_agregar = QHBoxLayout()
        self.combo_producto = QComboBox()
        self.input_cantidad = QDoubleSpinBox()
        self.input_cantidad.setMinimum(0.01)
        self.input_cantidad.setMaximum(999999)
        self.input_costo = QDoubleSpinBox()
        self.input_costo.setMaximum(999999)
        self.input_costo.setPrefix("S/ ")
        btn_agregar = QPushButton("Agregar línea")
        btn_agregar.clicked.connect(self._agregar_linea)

        fila_agregar.addWidget(self.combo_producto)
        fila_agregar.addWidget(self.input_cantidad)
        fila_agregar.addWidget(self.input_costo)
        fila_agregar.addWidget(btn_agregar)
        layout.addLayout(fila_agregar)

        self.tabla_lineas = QTableWidget(0, 5)
        self.tabla_lineas.setHorizontalHeaderLabels(["Producto", "Cantidad", "Costo unit.", "Subtotal", ""])
        header_lineas = self.tabla_lineas.horizontalHeader()
        header_lineas.setSectionResizeMode(0, QHeaderView.Stretch)
        header_lineas.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tabla_lineas.setColumnWidth(4, 50)
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

    def _agregar_linea(self) -> None:
        producto_id = self.combo_producto.currentData()
        if producto_id is None:
            return
        nombre = self.combo_producto.currentText()
        cantidad = self.input_cantidad.value()
        costo = self.input_costo.value()

        if cantidad <= 0:
            QMessageBox.warning(self, "Error", "La cantidad debe ser mayor a cero.")
            return

        self.lineas.append(CompraDetalleItem(
            producto_id=producto_id, nombre_producto=nombre, cantidad=cantidad, costo_unitario=costo,
        ))
        self._refrescar_tabla()
        self.input_cantidad.setValue(0.01)
        self.input_costo.setValue(0)

    def _refrescar_tabla(self) -> None:
        self.tabla_lineas.setRowCount(len(self.lineas))
        total = 0.0
        for fila, linea in enumerate(self.lineas):
            self.tabla_lineas.setItem(fila, 0, QTableWidgetItem(linea.nombre_producto))
            self.tabla_lineas.setItem(fila, 1, QTableWidgetItem(str(linea.cantidad)))
            self.tabla_lineas.setItem(fila, 2, QTableWidgetItem(formatear_moneda(linea.costo_unitario)))
            self.tabla_lineas.setItem(fila, 3, QTableWidgetItem(formatear_moneda(linea.subtotal)))

            btn_quitar = QPushButton("✕")
            btn_quitar.setProperty("class", "danger")
            btn_quitar.setMinimumSize(40, 28)
            btn_quitar.clicked.connect(lambda _, idx=fila: self._quitar_linea(idx))
            self.tabla_lineas.setCellWidget(fila, 4, btn_quitar)

            total += linea.subtotal
        total += self.input_impuesto.value()
        self.label_total.setText(f"Total: {formatear_moneda(total)}")

    def _quitar_linea(self, indice: int) -> None:
        if 0 <= indice < len(self.lineas):
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
