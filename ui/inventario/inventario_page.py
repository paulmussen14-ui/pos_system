"""Página de Inventario: consulta de stock, movimientos y ajustes manuales."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QDoubleSpinBox,
    QLineEdit, QMessageBox
)

from services.inventario_service import InventarioService, InventarioError
from services.producto_service import ProductoService
from utils.validators import formatear_moneda


class InventarioPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.inventario_service = InventarioService()
        self.producto_service = ProductoService()
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        titulo = QLabel("Inventario")
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        layout.addWidget(titulo)

        tabs = QTabWidget()

        # --- Tab: stock actual ---
        tab_stock = QWidget()
        layout_stock = QVBoxLayout(tab_stock)
        self.tabla_stock = QTableWidget(0, 5)
        self.tabla_stock.setHorizontalHeaderLabels(
            ["Producto", "Stock actual", "Stock mínimo", "Estado", "Costo promedio"]
        )
        self.tabla_stock.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla_stock.verticalHeader().setVisible(False)
        self.tabla_stock.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_stock.addWidget(self.tabla_stock)
        tabs.addTab(tab_stock, "Stock actual")

        # --- Tab: movimientos ---
        tab_movimientos = QWidget()
        layout_movimientos = QVBoxLayout(tab_movimientos)
        self.tabla_movimientos = QTableWidget(0, 5)
        self.tabla_movimientos.setHorizontalHeaderLabels(
            ["Fecha", "Producto", "Tipo", "Cantidad", "Referencia"]
        )
        self.tabla_movimientos.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla_movimientos.verticalHeader().setVisible(False)
        self.tabla_movimientos.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_movimientos.addWidget(self.tabla_movimientos)
        tabs.addTab(tab_movimientos, "Movimientos")

        # --- Tab: ajuste manual ---
        tab_ajuste = QWidget()
        layout_ajuste = QVBoxLayout(tab_ajuste)
        fila_ajuste = QHBoxLayout()

        self.combo_producto_ajuste = QComboBox()
        fila_ajuste.addWidget(QLabel("Producto:"))
        fila_ajuste.addWidget(self.combo_producto_ajuste)

        self.input_nuevo_stock = QDoubleSpinBox()
        self.input_nuevo_stock.setMaximum(999999)
        fila_ajuste.addWidget(QLabel("Nuevo stock:"))
        fila_ajuste.addWidget(self.input_nuevo_stock)
        layout_ajuste.addLayout(fila_ajuste)

        self.input_motivo = QLineEdit()
        self.input_motivo.setPlaceholderText("Motivo del ajuste (ej. conteo físico)")
        layout_ajuste.addWidget(self.input_motivo)

        btn_ajustar = QPushButton("Aplicar ajuste")
        btn_ajustar.clicked.connect(self._aplicar_ajuste)
        layout_ajuste.addWidget(btn_ajustar)
        layout_ajuste.addStretch()
        tabs.addTab(tab_ajuste, "Ajuste manual")

        layout.addWidget(tabs)
        tabs.currentChanged.connect(lambda _: self.actualizar())

    def actualizar(self) -> None:
        productos = self.producto_service.listar()

        self.tabla_stock.setRowCount(len(productos))
        for fila, p in enumerate(productos):
            self.tabla_stock.setItem(fila, 0, QTableWidgetItem(p.nombre))
            self.tabla_stock.setItem(fila, 1, QTableWidgetItem(f"{p.stock_actual} {p.unidad_medida}"))
            self.tabla_stock.setItem(fila, 2, QTableWidgetItem(str(p.stock_minimo)))
            estado = "Agotado" if p.agotado else ("Stock bajo" if p.stock_bajo else "OK")
            self.tabla_stock.setItem(fila, 3, QTableWidgetItem(estado))
            self.tabla_stock.setItem(fila, 4, QTableWidgetItem(formatear_moneda(p.costo_promedio_actual)))

        movimientos = self.inventario_service.movimientos()
        self.tabla_movimientos.setRowCount(len(movimientos))
        for fila, m in enumerate(movimientos):
            self.tabla_movimientos.setItem(fila, 0, QTableWidgetItem(str(m["fecha"])))
            self.tabla_movimientos.setItem(fila, 1, QTableWidgetItem(m["producto_nombre"]))
            self.tabla_movimientos.setItem(fila, 2, QTableWidgetItem(m["tipo"]))
            self.tabla_movimientos.setItem(fila, 3, QTableWidgetItem(str(m["cantidad"])))
            self.tabla_movimientos.setItem(fila, 4, QTableWidgetItem(m.get("referencia_tipo") or "-"))

        self.combo_producto_ajuste.clear()
        for p in productos:
            self.combo_producto_ajuste.addItem(p.nombre, p.id)

    def _aplicar_ajuste(self) -> None:
        producto_id = self.combo_producto_ajuste.currentData()
        if producto_id is None:
            return
        try:
            self.inventario_service.ajustar_stock(
                producto_id, self.input_nuevo_stock.value(), self.input_motivo.text(), self.usuario.id
            )
        except InventarioError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        QMessageBox.information(self, "Ajuste aplicado", "El stock fue actualizado correctamente.")
        self.input_motivo.clear()
        self.actualizar()
