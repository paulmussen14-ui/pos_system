"""Diálogo para ver el detalle de una venta, anularla, corregirla o registrar una devolución parcial."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QComboBox, QDoubleSpinBox, QLineEdit, QMessageBox
)
from PySide6.QtCore import Signal

from services.venta_service import VentaService, VentaError
from services.configuracion_service import ConfiguracionService
from services.cliente_service import ClienteService
from printing.ticket_template import ancho_caracteres_por_papel
from ui.widgets.ticket_preview_dialog import TicketPreviewDialog
from utils.validators import formatear_moneda


class VentaDetalleDialog(QDialog):

    venta_lista_para_recrear = Signal(list, object)

    def __init__(self, venta_id: int, usuario, parent=None):
        super().__init__(parent)
        self.venta_id = venta_id
        self.usuario = usuario
        self.venta_service = VentaService()
        self.config_service = ConfiguracionService()
        self.cliente_service = ClienteService()
        self._construir_ui()
        self._cargar_datos()

    def _construir_ui(self) -> None:
        self.setWindowTitle(f"Detalle de venta #{self.venta_id}")
        self.resize(520, 460)

        layout = QVBoxLayout(self)

        self.label_info = QLabel()
        layout.addWidget(self.label_info)

        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["Producto", "Cantidad", "Presentación", "Precio", "Subtotal"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.tabla)

        fila_cliente = QHBoxLayout()
        fila_cliente.addWidget(QLabel("Cliente:"))
        self.combo_cliente = QComboBox()
        fila_cliente.addWidget(self.combo_cliente)
        btn_guardar_cliente = QPushButton("Guardar cliente")
        btn_guardar_cliente.setProperty("class", "secondary")
        btn_guardar_cliente.clicked.connect(self._guardar_cliente)
        fila_cliente.addWidget(btn_guardar_cliente)
        layout.addLayout(fila_cliente)

        fila_devolucion = QHBoxLayout()
        fila_devolucion.addWidget(QLabel("Producto:"))
        self.combo_producto_devolucion = QComboBox()
        self.combo_producto_devolucion.currentIndexChanged.connect(self._actualizar_combo_presentacion_devolucion)
        fila_devolucion.addWidget(self.combo_producto_devolucion)

        fila_devolucion.addWidget(QLabel("Cantidad:"))
        self.input_cantidad_devolucion = QDoubleSpinBox()
        self.input_cantidad_devolucion.setMinimum(0.01)
        self.input_cantidad_devolucion.setMaximum(999999)
        fila_devolucion.addWidget(self.input_cantidad_devolucion)

        fila_devolucion.addWidget(QLabel("en:"))
        self.combo_presentacion_devolucion = QComboBox()
        fila_devolucion.addWidget(self.combo_presentacion_devolucion)
        layout.addLayout(fila_devolucion)

        self.input_motivo_devolucion = QLineEdit()
        self.input_motivo_devolucion.setPlaceholderText("Motivo de la devolución")
        layout.addWidget(self.input_motivo_devolucion)

        btn_devolver = QPushButton("Registrar devolución")
        btn_devolver.setProperty("class", "secondary")
        btn_devolver.clicked.connect(self._registrar_devolucion)
        layout.addWidget(btn_devolver)

        self.btn_vista_previa = QPushButton("Vista previa / Imprimir ticket")
        self.btn_vista_previa.setProperty("class", "secondary")
        self.btn_vista_previa.clicked.connect(self._vista_previa_ticket)
        layout.addWidget(self.btn_vista_previa)

        botones = QHBoxLayout()
        self.btn_anular = QPushButton("Anular venta")
        self.btn_anular.setProperty("class", "danger")
        self.btn_anular.clicked.connect(self._anular_venta)
        botones.addWidget(self.btn_anular)

        self.btn_corregir = QPushButton("Corregir venta")
        self.btn_corregir.setProperty("class", "danger")
        self.btn_corregir.setToolTip(
            "Anula esta venta y carga sus productos en el carrito de Ventas\n"
            "para que puedas ajustarlos y registrarla de nuevo correctamente."
        )
        self.btn_corregir.clicked.connect(self._corregir_venta)
        botones.addWidget(self.btn_corregir)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.accept)
        botones.addWidget(btn_cerrar)
        layout.addLayout(botones)

    def _cargar_datos(self) -> None:
        venta = self.venta_service.obtener_venta_con_lineas(self.venta_id)
        if not venta:
            QMessageBox.warning(self, "Error", "Venta no encontrada.")
            self.reject()
            return

        moneda = self.config_service.obtener().get("moneda", "S/")
        self.label_info.setText(
            f"Fecha: {venta['fecha']}   |   Estado: {venta['estado']}   |   "
            f"Total: {formatear_moneda(venta['total'], moneda)}"
        )
        venta_anulada = venta["estado"] == "anulada"
        self.btn_anular.setEnabled(not venta_anulada)
        self.btn_corregir.setEnabled(not venta_anulada)
        self._venta_actual = venta

        self._cargar_combo_clientes(venta.get("cliente_id"))

        lineas = venta["lineas"]
        self.tabla.setRowCount(len(lineas))
        self.combo_producto_devolucion.clear()
        self._presentacion_vendida_por_producto = {}
        for fila, linea in enumerate(lineas):
            # Ventas viejas no tienen presentación guardada (NULL): se
            # muestran en unidad base, igual que en el ticket.
            cantidad_pres = linea.get("cantidad_presentacion") or linea["cantidad"]
            nombre_pres = linea.get("presentacion_nombre") or "Unidad"
            factor_pres = linea.get("factor_unidades") or 1.0
            self.tabla.setItem(fila, 0, QTableWidgetItem(linea["producto_nombre"]))
            self.tabla.setItem(fila, 1, QTableWidgetItem(f"{cantidad_pres:g}"))
            self.tabla.setItem(fila, 2, QTableWidgetItem(nombre_pres))
            self.tabla.setItem(fila, 3, QTableWidgetItem(formatear_moneda(linea["precio_venta_unitario"], moneda)))
            self.tabla.setItem(fila, 4, QTableWidgetItem(formatear_moneda(linea["subtotal"], moneda)))
            self.combo_producto_devolucion.addItem(linea["producto_nombre"], linea["producto_id"])
            # Se recuerda en qué presentación se vendió cada producto, para
            # ofrecerla como opción al devolver (ej. devolver "1 Caja" en vez
            # de tener que convertir a unidades sueltas a mano).
            self._presentacion_vendida_por_producto[linea["producto_id"]] = (nombre_pres, factor_pres)

        self._actualizar_combo_presentacion_devolucion()

    def _cargar_combo_clientes(self, cliente_id_actual: int | None) -> None:
        self.combo_cliente.clear()
        self.combo_cliente.addItem("Sin cliente (venta general)", None)
        for c in self.cliente_service.listar():
            self.combo_cliente.addItem(c.nombre, c.id)
        if cliente_id_actual:
            idx = self.combo_cliente.findData(cliente_id_actual)
            if idx >= 0:
                self.combo_cliente.setCurrentIndex(idx)

    def _guardar_cliente(self) -> None:
        nuevo_cliente_id = self.combo_cliente.currentData()
        try:
            self.venta_service.cambiar_cliente(self.venta_id, nuevo_cliente_id)
        except VentaError as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        QMessageBox.information(self, "Cliente actualizado", "El cliente de la venta fue actualizado.")

    def _anular_venta(self) -> None:
        respuesta = QMessageBox.question(self, "Confirmar", "¿Anular esta venta? Se repondrá el stock.")
        if respuesta != QMessageBox.Yes:
            return
        try:
            self.venta_service.anular_venta(self.venta_id, self.usuario.id)
        except VentaError as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        QMessageBox.information(self, "Venta anulada", "La venta fue anulada correctamente.")
        self._cargar_datos()

    def _actualizar_combo_presentacion_devolucion(self) -> None:
        """Arma las opciones de presentación para devolver el producto que
        está seleccionado en combo_producto_devolucion: la misma presentación
        con la que se vendió (preseleccionada) y, si era distinta, también
        "Unidad" por si el cliente abrió la caja/paquete y solo devuelve
        parte de lo vendido."""
        self.combo_presentacion_devolucion.clear()
        producto_id = self.combo_producto_devolucion.currentData()
        if producto_id is None:
            return

        nombre_pres, factor_pres = self._presentacion_vendida_por_producto.get(producto_id, ("Unidad", 1.0))
        self.combo_presentacion_devolucion.addItem(
            f"{nombre_pres} (x{factor_pres:g})" if factor_pres != 1 else nombre_pres, factor_pres
        )
        if factor_pres != 1:
            self.combo_presentacion_devolucion.addItem("Unidad", 1.0)

    def _registrar_devolucion(self) -> None:
        producto_id = self.combo_producto_devolucion.currentData()
        if producto_id is None:
            return
        factor = self.combo_presentacion_devolucion.currentData() or 1.0
        # La devolución y el stock siempre se manejan en unidad base
        # internamente; aquí solo se convierte lo que el usuario tipeó en la
        # presentación elegida (ej. "1 Caja" x12 = 12 unidades base).
        cantidad_base = round(self.input_cantidad_devolucion.value() * factor, 4)
        nombre_pres_elegida = self.combo_presentacion_devolucion.currentText() or "unidades"
        try:
            self.venta_service.registrar_devolucion(
                self.venta_id, producto_id, cantidad_base,
                self.input_motivo_devolucion.text(), self.usuario.id,
                factor_presentacion=factor, nombre_presentacion=nombre_pres_elegida,
            )
        except VentaError as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        QMessageBox.information(self, "Devolución registrada", "La devolución fue registrada y el stock repuesto.")
        self.input_motivo_devolucion.clear()

    def _vista_previa_ticket(self) -> None:
        config_negocio = self.config_service.obtener()
        config_impresion = self.config_service.obtener_config_impresion()
        ancho = ancho_caracteres_por_papel(config_impresion.get("ancho_papel_mm"))

        nombre_impresora = config_impresion.get("nombre_impresora") if config_impresion.get("activo") else None
        imprimir_dos_copias = bool(config_impresion.get("imprimir_dos_copias", True))

        dialogo = TicketPreviewDialog(
            self._venta_actual,
            config_negocio,
            nombre_impresora,
            ancho_caracteres=ancho,
            imprimir_dos_copias=imprimir_dos_copias,
            parent=self,
        )
        dialogo.exec()

    def _corregir_venta(self) -> None:
        respuesta = QMessageBox.question(
            self, "Corregir venta",
            "Esto anulará la venta actual (se repone el stock y, si aplica, la caja) "
            "y cargará los mismos productos en el carrito de Ventas para que los "
            "corrijas y registres la venta de nuevo.\n\n"
            "Las ventas ya registradas no se editan directamente, para conservar "
            "el historial de costos y utilidad. ¿Deseas continuar?"
        )
        if respuesta != QMessageBox.Yes:
            return

        lineas_originales = list(self._venta_actual.get("lineas", []))
        cliente_id = self._venta_actual.get("cliente_id")

        try:
            self.venta_service.anular_venta(self.venta_id, self.usuario.id)
        except VentaError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        self.venta_lista_para_recrear.emit(lineas_originales, cliente_id)
        self.accept()