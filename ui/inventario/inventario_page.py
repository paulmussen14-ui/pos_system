"""Página de Inventario: consulta de stock, movimientos y ajustes manuales.

Las consultas (SELECT) corren fuera del hilo principal, con buscador (debounce
de 300 ms) y paginación ("Cargar más"). El ajuste manual es una escritura y se
mantiene en el hilo principal a propósito.
"""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QDoubleSpinBox,
    QLineEdit, QMessageBox
)

from services.inventario_service import InventarioService, InventarioError
from services.producto_service import ProductoService
from utils.validators import formatear_moneda


class _Senales(QObject):
    ok = Signal(int, object)      # (req_id, datos)
    error = Signal(int, str)      # (req_id, mensaje)


class _CargaInventario(QRunnable):
    """Ejecuta solo lecturas. Nunca tocar widgets desde run()."""

    def __init__(self, req_id: int, funcion, senales: _Senales):
        super().__init__()
        self.req_id = req_id
        self.funcion = funcion
        self.senales = senales

    def run(self) -> None:
        try:
            datos = self.funcion()
        except Exception as e:  # noqa: BLE001
            self.senales.error.emit(self.req_id, str(e))
            return
        self.senales.ok.emit(self.req_id, datos)


class InventarioPage(QWidget):
    PAGE = 100

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.inventario_service = InventarioService()
        self.producto_service = ProductoService()

        self._req_id = 0
        self._offset = 0
        self._pool = QThreadPool.globalInstance()
        self._senales = _Senales(self)
        self._senales.ok.connect(self._on_datos)
        self._senales.error.connect(self._on_error)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(lambda: self._cargar(0, completo=False))

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

        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText("Buscar producto…")
        self.buscador.setClearButtonEnabled(True)
        self.buscador.textChanged.connect(lambda _: self._debounce.start())
        layout_stock.addWidget(self.buscador)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet("color: #666;")
        layout_stock.addWidget(self.lbl_estado)

        self.tabla_stock = QTableWidget(0, 5)
        self.tabla_stock.setHorizontalHeaderLabels(
            ["Producto", "Stock actual", "Stock mínimo", "Estado", "Costo promedio"]
        )
        self.tabla_stock.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla_stock.verticalHeader().setVisible(False)
        self.tabla_stock.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_stock.addWidget(self.tabla_stock)

        self.btn_mas = QPushButton("Cargar más")
        self.btn_mas.setVisible(False)
        self.btn_mas.clicked.connect(lambda: self._cargar(self._offset, completo=False))
        layout_stock.addWidget(self.btn_mas)
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

        # Combo editable con búsqueda: escribe parte del nombre y elige de la lista.
        self.combo_producto_ajuste = QComboBox()
        self.combo_producto_ajuste.setEditable(True)
        self.combo_producto_ajuste.setInsertPolicy(QComboBox.NoInsert)
        completer = self.combo_producto_ajuste.completer()
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
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

        self.btn_ajustar = QPushButton("Aplicar ajuste")
        self.btn_ajustar.clicked.connect(self._aplicar_ajuste)
        layout_ajuste.addWidget(self.btn_ajustar)
        layout_ajuste.addStretch()
        tabs.addTab(tab_ajuste, "Ajuste manual")

        layout.addWidget(tabs)
        tabs.currentChanged.connect(lambda _: self.actualizar())

    # ------------------------------------------------------------------
    # Carga en segundo plano (solo SELECT)
    # ------------------------------------------------------------------
    def actualizar(self) -> None:
        """Recarga completa: primera página de stock + movimientos + combo."""
        self._cargar(0, completo=True)

    def _cargar(self, offset: int, completo: bool) -> None:
        self._debounce.stop()
        self._req_id += 1
        texto = self.buscador.text().strip()
        self.lbl_estado.setText("Cargando…")
        self.btn_mas.setEnabled(False)

        def leer() -> dict:
            # Corre en el hilo del Worker: solo lecturas, sin widgets.
            datos = {
                "offset": offset,
                "texto": texto,
                "productos": self.producto_service.listar(texto, self.PAGE, offset),
            }
            if completo:
                datos["movimientos"] = self.inventario_service.movimientos()
                datos["combo"] = self.producto_service.listar()
            return datos

        self._pool.start(_CargaInventario(self._req_id, leer, self._senales))

    def _on_datos(self, req_id: int, datos: dict) -> None:
        if req_id != self._req_id:   # respuesta vieja: hay una consulta más reciente
            return

        offset = datos["offset"]
        productos = datos["productos"]

        if offset == 0:
            self.tabla_stock.setRowCount(0)
        inicio = self.tabla_stock.rowCount()
        self.tabla_stock.setRowCount(inicio + len(productos))
        for i, p in enumerate(productos):
            fila = inicio + i
            self.tabla_stock.setItem(fila, 0, QTableWidgetItem(p.nombre))
            self.tabla_stock.setItem(fila, 1, QTableWidgetItem(f"{p.stock_actual} {p.unidad_medida}"))
            self.tabla_stock.setItem(fila, 2, QTableWidgetItem(str(p.stock_minimo)))
            estado = "Agotado" if p.agotado else ("Stock bajo" if p.stock_bajo else "OK")
            self.tabla_stock.setItem(fila, 3, QTableWidgetItem(estado))
            self.tabla_stock.setItem(fila, 4, QTableWidgetItem(formatear_moneda(p.costo_promedio_actual)))

        self._offset = offset + len(productos)
        total = self.tabla_stock.rowCount()
        self.btn_mas.setEnabled(True)
        self.btn_mas.setVisible(len(productos) == self.PAGE)
        if total:
            self.lbl_estado.setText(f"Mostrando {total}")
        else:
            self.lbl_estado.setText("Sin resultados")

        if "movimientos" in datos:
            movimientos = datos["movimientos"]
            self.tabla_movimientos.setRowCount(len(movimientos))
            for fila, m in enumerate(movimientos):
                self.tabla_movimientos.setItem(fila, 0, QTableWidgetItem(str(m["fecha"])))
                self.tabla_movimientos.setItem(fila, 1, QTableWidgetItem(m["producto_nombre"]))
                self.tabla_movimientos.setItem(fila, 2, QTableWidgetItem(m["tipo"]))
                self.tabla_movimientos.setItem(fila, 3, QTableWidgetItem(str(m["cantidad"])))
                self.tabla_movimientos.setItem(fila, 4, QTableWidgetItem(m.get("referencia_tipo") or "-"))

        if "combo" in datos:
            seleccionado = self.combo_producto_ajuste.currentData()
            self.combo_producto_ajuste.clear()
            for p in datos["combo"]:
                self.combo_producto_ajuste.addItem(p.nombre, p.id)
            idx = self.combo_producto_ajuste.findData(seleccionado) if seleccionado is not None else -1
            self.combo_producto_ajuste.setCurrentIndex(idx)  # -1 = sin selección

    def _on_error(self, req_id: int, mensaje: str) -> None:
        if req_id != self._req_id:
            return
        self.btn_mas.setEnabled(True)
        self.lbl_estado.setText(f"Error al cargar el inventario: {mensaje}")

    # ------------------------------------------------------------------
    # Escritura: se queda en el hilo principal
    # ------------------------------------------------------------------
    def _producto_elegido(self):
        combo = self.combo_producto_ajuste
        texto = combo.currentText().strip()
        idx = combo.currentIndex()
        if idx < 0 or combo.itemText(idx) != texto:
            idx = combo.findText(texto, Qt.MatchExactly)
        return combo.itemData(idx) if idx >= 0 else None

    def _aplicar_ajuste(self) -> None:
        producto_id = self._producto_elegido()
        if producto_id is None:
            QMessageBox.warning(self, "Producto", "Elige un producto de la lista.")
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