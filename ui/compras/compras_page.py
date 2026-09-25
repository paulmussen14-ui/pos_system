"""Página de Compras: listado de compras registradas y alta de nuevas compras."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFormLayout,
    QComboBox, QMessageBox
)
from PySide6.QtCore import QLocale, QThreadPool

from services.compra_service import CompraService, CompraError
from services.configuracion_service import ConfiguracionService
from services.producto_service import ProductoService
from ui.compras.compra_form_dialog import CompraFormDialog, _spinbox_con_punto
from utils.validators import formatear_moneda
from utils.worker import Worker
from utils.logger import logger

# Mismo estilo de tabla usado en Ventas y Clientes, para mantener
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


class ComprasPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.compra_service = CompraService()
        self.config_service = ConfiguracionService()
        self.producto_service = ProductoService()
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        cabecera = QHBoxLayout()
        titulo = QLabel("Compras")
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        cabecera.addWidget(titulo)
        cabecera.addStretch()

        btn_nueva = QPushButton("+ Nueva compra")
        btn_nueva.clicked.connect(self._nueva_compra)
        cabecera.addWidget(btn_nueva)
        layout.addLayout(cabecera)

        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels(
            ["#", "Fecha", "Proveedor", "N° Documento", "Total", "Pago", "Detalle"]
        )
        header = self.tabla.horizontalHeader()
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.tabla.setColumnWidth(6, 170)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setStyleSheet(ESTILO_TABLA)
        layout.addWidget(self.tabla)

    def actualizar(self) -> None:
        """Dispara la carga del listado de compras en segundo plano para no
        congelar la UI cuando ya hay muchas compras registradas (ver el
        mismo problema que causaba pantalla en blanco en Ventas)."""
        worker = Worker(self.compra_service.listar_compras)
        worker.signals.finished.connect(self._on_compras_listas)
        worker.signals.error.connect(self._on_error_carga)
        QThreadPool.globalInstance().start(worker)

    def _on_error_carga(self, error_texto: str) -> None:
        logger.error("Error al cargar compras: %s", error_texto)
        QMessageBox.warning(
            self, "Error al cargar compras",
            "No se pudo cargar el listado de compras. Intenta de nuevo.",
        )

    def _on_compras_listas(self, compras: list[dict]) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        self.tabla.setRowCount(len(compras))

        for fila, compra in enumerate(compras):
            self.tabla.setItem(fila, 0, QTableWidgetItem(str(compra["id"])))
            self.tabla.setItem(fila, 1, QTableWidgetItem(str(compra["fecha"])))
            self.tabla.setItem(fila, 2, QTableWidgetItem(compra.get("proveedor_nombre") or "-"))
            self.tabla.setItem(fila, 3, QTableWidgetItem(compra.get("numero_documento") or "-"))
            self.tabla.setItem(fila, 4, QTableWidgetItem(formatear_moneda(compra["total"], moneda)))
            pago = "Contado (caja)" if compra.get("pago_es_efectivo") else "Crédito / otro"
            self.tabla.setItem(fila, 5, QTableWidgetItem(pago))

            btn_ver = QPushButton("Ver detalle")
            btn_ver.setProperty("class", "secondary")
            btn_ver.setMinimumHeight(32)
            btn_ver.clicked.connect(lambda _, cid=compra["id"]: self._ver_detalle(cid))
            self.tabla.setCellWidget(fila, 6, btn_ver)
            self.tabla.setRowHeight(fila, 40)

    def _nueva_compra(self) -> None:
        dialogo = CompraFormDialog(usuario=self.usuario, parent=self)
        if dialogo.exec():
            self.actualizar()

    def _ver_detalle(self, compra_id: int) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")

        dialogo = QDialog(self)
        dialogo.setWindowTitle(f"Detalle de compra #{compra_id}")
        dialogo.resize(560, 380)
        layout = QVBoxLayout(dialogo)

        tabla = QTableWidget(0, 6)
        tabla.setHorizontalHeaderLabels(
            ["Producto", "Cantidad", "Presentación", "Costo unitario", "Subtotal", ""]
        )
        header = tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        tabla.setColumnWidth(5, 70)
        tabla.verticalHeader().setVisible(False)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        tabla.setAlternatingRowColors(True)
        tabla.setStyleSheet(ESTILO_TABLA)
        layout.addWidget(tabla)

        def refrescar_tabla_detalle():
            detalle = self.compra_service.obtener_compra_con_lineas(compra_id)
            lineas = detalle["lineas"]
            tabla.setRowCount(len(lineas))
            for fila, l in enumerate(lineas):
                cantidad_pres = l.get("cantidad_presentacion") or l["cantidad"]
                nombre_pres = l.get("presentacion_nombre") or "Unidad"
                tabla.setItem(fila, 0, QTableWidgetItem(l["producto_nombre"]))
                tabla.setItem(fila, 1, QTableWidgetItem(f"{cantidad_pres:g}"))
                tabla.setItem(fila, 2, QTableWidgetItem(nombre_pres))
                tabla.setItem(fila, 3, QTableWidgetItem(formatear_moneda(l["costo_unitario"], moneda)))
                tabla.setItem(fila, 4, QTableWidgetItem(formatear_moneda(l["subtotal"], moneda)))

                btn_editar = QPushButton("✎")
                btn_editar.setToolTip("Corregir esta línea")
                btn_editar.setProperty("class", "secondary")
                btn_editar.setMinimumSize(32, 28)
                btn_editar.clicked.connect(lambda _, linea=l: self._editar_linea_guardada(linea, refrescar_tabla_detalle))
                tabla.setCellWidget(fila, 5, btn_editar)
                tabla.setRowHeight(fila, 34)

            if not lineas:
                tabla.setRowCount(0)

        refrescar_tabla_detalle()

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(btn_cerrar)

        dialogo.exec()
        self.actualizar()  # por si una corrección cambió el total de la compra

    def _editar_linea_guardada(self, linea: dict, al_guardar_callback) -> None:
        """Corrige la cantidad/presentación/costo de una línea de una
        compra ya registrada. Ajusta stock y costo promedio del producto."""
        producto_id = linea["producto_id"]
        presentaciones = self.producto_service.presentaciones(producto_id)

        dialogo = QDialog(self)
        dialogo.setWindowTitle(f"Corregir línea — {linea['producto_nombre']}")
        dialogo.resize(360, 200)
        layout = QVBoxLayout(dialogo)

        aviso = QLabel(
            "Corrige esta línea si hubo un error al digitarla. Se ajustará "
            "el stock y el costo del producto según el cambio."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(aviso)

        form = QFormLayout()
        combo_presentacion = QComboBox()
        combo_presentacion.addItem("Unidad", (1.0, "Unidad"))
        for p in presentaciones:
            combo_presentacion.addItem(f"{p.nombre} (x{p.cantidad_unidades:g})", (p.cantidad_unidades, p.nombre))

        nombre_actual = linea.get("presentacion_nombre") or "Unidad"
        for i in range(combo_presentacion.count()):
            _, nombre_i = combo_presentacion.itemData(i)
            if nombre_i == nombre_actual:
                combo_presentacion.setCurrentIndex(i)
                break

        input_cantidad = _spinbox_con_punto(minimo=0.01)
        input_cantidad.setValue(linea.get("cantidad_presentacion") or linea["cantidad"])

        input_costo = _spinbox_con_punto(prefijo="S/ ")
        cantidad_presentacion_guardada = linea.get("cantidad_presentacion") or linea["cantidad"]
        factor_guardado = (linea["cantidad"] / cantidad_presentacion_guardada) if cantidad_presentacion_guardada else 1
        costo_presentacion_actual = linea["costo_unitario"] * factor_guardado
        input_costo.setValue(round(costo_presentacion_actual, 2))

        form.addRow("Presentación:", combo_presentacion)
        form.addRow("Cantidad:", input_cantidad)
        form.addRow("Costo (de esa presentación):", input_costo)
        layout.addLayout(form)

        botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "secondary")
        btn_cancelar.clicked.connect(dialogo.reject)
        btn_guardar = QPushButton("Guardar corrección")
        btn_guardar.setProperty("class", "success")
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        layout.addLayout(botones)

        def guardar():
            factor, nombre_presentacion = combo_presentacion.currentData()
            try:
                self.compra_service.editar_linea_compra(
                    detalle_id=linea["id"],
                    presentacion_nombre=nombre_presentacion,
                    factor_unidades=factor,
                    cantidad_presentacion=input_cantidad.value(),
                    costo_presentacion_total=input_costo.value(),
                )
            except CompraError as e:
                QMessageBox.warning(dialogo, "No se pudo corregir", str(e))
                return
            dialogo.accept()
            al_guardar_callback()

        btn_guardar.clicked.connect(guardar)
        dialogo.exec()