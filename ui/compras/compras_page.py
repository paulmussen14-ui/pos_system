"""Página de Compras: listado de compras registradas y alta de nuevas compras."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog
)

from services.compra_service import CompraService
from services.configuracion_service import ConfiguracionService
from ui.compras.compra_form_dialog import CompraFormDialog
from utils.validators import formatear_moneda

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
        moneda = self.config_service.obtener().get("moneda", "S/")
        compras = self.compra_service.listar_compras()
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
        detalle = self.compra_service.obtener_compra_con_lineas(compra_id)
        lineas = detalle["lineas"]

        dialogo = QDialog(self)
        dialogo.setWindowTitle(f"Detalle de compra #{compra_id}")
        dialogo.resize(460, 360)
        layout = QVBoxLayout(dialogo)

        tabla = QTableWidget(0, 4)
        tabla.setHorizontalHeaderLabels(["Producto", "Cantidad", "Costo unitario", "Subtotal"])
        header = tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        tabla.verticalHeader().setVisible(False)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        tabla.setAlternatingRowColors(True)
        tabla.setStyleSheet(ESTILO_TABLA)
        layout.addWidget(tabla)

        if lineas:
            tabla.setRowCount(len(lineas))
            for fila, l in enumerate(lineas):
                tabla.setItem(fila, 0, QTableWidgetItem(l["producto_nombre"]))
                tabla.setItem(fila, 1, QTableWidgetItem(str(l["cantidad"])))
                tabla.setItem(fila, 2, QTableWidgetItem(formatear_moneda(l["costo_unitario"], moneda)))
                tabla.setItem(fila, 3, QTableWidgetItem(formatear_moneda(l["subtotal"], moneda)))
                tabla.setRowHeight(fila, 34)
        else:
            layout.addWidget(QLabel("Sin líneas registradas."))

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(btn_cerrar)

        dialogo.exec()