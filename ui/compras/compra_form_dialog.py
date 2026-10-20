"""Diálogo para registrar una compra con una o varias líneas de producto."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QDoubleSpinBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLabel, QCheckBox, QWidget, QSplitter, QScrollArea, QFrame, QButtonGroup,
)
from PySide6.QtCore import Qt, QLocale, QObject, QEvent, QTimer
from PySide6.QtGui import QGuiApplication

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
from services.configuracion_service import ConfiguracionService
from models.compra import CompraDetalleItem
from ui.tokens import ESPACIO_SM, ESPACIO_MD
from ui.widgets.card import Card
from ui.widgets.tabla_erp import configurar_tabla_erp, item_derecha, colorear_stock
from utils.tablas import carga_rapida, cerca_del_final
from utils.validators import formatear_moneda

TAMANO_PAGINA_PRODUCTOS = 100
ALTURA_FILA_PRODUCTOS = 40
ANCHO_COLUMNA_CATEGORIA = 130


class _RuedaHorizontal(QObject):
    """La rueda del mouse desplaza la fila de categorías hacia los lados."""

    def __init__(self, area: QScrollArea):
        super().__init__(area)
        self._area = area
        area.viewport().installEventFilter(self)

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Wheel:
            barra = self._area.horizontalScrollBar()
            barra.setValue(barra.value() - (evento.angleDelta().y() or evento.angleDelta().x()))
            return True
        return False


class CompraFormDialog(QDialog):
    """Registrar una compra. A la izquierda se ve TODA la lista de productos (con buscador y
    categorías, como en Ventas e Inventario); a la derecha, la compra que se va armando."""

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.producto_service = ProductoService()
        self.compra_service = CompraService()
        self.caja_service = CajaService()
        self.lineas: list[CompraDetalleItem] = []
        self._producto_id = None
        self._producto_nombre = ""
        self._producto_unidad = ""
        self._categoria_filtro = None
        self._categorias_firma: tuple = ()
        self._hay_mas_productos = False
        self._productos_cargados = 0
        self._tema = ConfiguracionService().obtener().get("tema", "claro")

        self._timer_busqueda = QTimer(self)
        self._timer_busqueda.setSingleShot(True)
        self._timer_busqueda.setInterval(250)
        self._timer_busqueda.timeout.connect(self._buscar_productos)

        self._construir_ui()
        self._cargar_combos()
        self._cargar_categorias()
        self._buscar_productos()
        self.input_busqueda.setFocus()

    # ------------------------------------------------------ Interfaz ----
    def _construir_ui(self) -> None:
        self.setWindowTitle("Nueva compra")
        # Grande por defecto, pero sin pasarse de la pantalla (laptops de 1366x768).
        pantalla = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(1200, int(pantalla.width() * 0.92)), min(740, int(pantalla.height() * 0.88)))
        self.setMinimumSize(min(920, pantalla.width()), min(540, pantalla.height()))
        # Panel amplio: se puede agrandar, maximizar y estirar desde la esquina.
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(ESPACIO_SM)

        # --- Datos de la compra (una sola fila) ---
        cabecera = QHBoxLayout()
        cabecera.setSpacing(ESPACIO_MD)
        self.combo_proveedor = QComboBox()
        self.combo_proveedor.setMinimumWidth(220)
        self.input_numero_documento = QLineEdit()
        self.input_numero_documento.setText(self.compra_service.sugerir_numero_documento())
        self.input_numero_documento.setMaximumWidth(190)
        self.input_impuesto = _spinbox_con_punto(prefijo="S/ ")
        self.input_impuesto.setMaximumWidth(150)
        self.input_impuesto.valueChanged.connect(self._refrescar_tabla)
        for texto, widget, estiramiento in (("Proveedor:", self.combo_proveedor, 1),
                                            ("N° de documento:", self.input_numero_documento, 0),
                                            ("Impuesto (IGV, si aplica):", self.input_impuesto, 0)):
            cabecera.addWidget(QLabel(texto))
            cabecera.addWidget(widget, estiramiento)
        layout.addLayout(cabecera)

        self.check_pago_efectivo = QCheckBox("Pagada al contado (se descuenta de la caja)")
        self.check_pago_efectivo.toggled.connect(self._actualizar_aviso_caja)
        layout.addWidget(self.check_pago_efectivo)

        self.label_aviso_caja = QLabel()
        self.label_aviso_caja.setWordWrap(True)
        self.label_aviso_caja.setStyleSheet("color: #92400e;")
        self.label_aviso_caja.setVisible(False)
        layout.addWidget(self.label_aviso_caja)

        # --- Dos paneles que se pueden ajustar arrastrando la división ---
        divisor = QSplitter(Qt.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.addWidget(self._construir_panel_productos())
        divisor.addWidget(self._construir_panel_compra())
        divisor.setStretchFactor(0, 5)
        divisor.setStretchFactor(1, 6)
        divisor.setSizes([470, 700])
        layout.addWidget(divisor, 1)

    def _construir_panel_productos(self) -> QWidget:
        tarjeta = Card("Productos")
        self.input_busqueda = QLineEdit()
        self.input_busqueda.setPlaceholderText("Buscar producto por nombre...")
        self.input_busqueda.setClearButtonEnabled(True)
        self.input_busqueda.textChanged.connect(lambda: self._timer_busqueda.start())
        self.input_busqueda.returnPressed.connect(self._enter_en_busqueda)
        tarjeta.cuerpo.addWidget(self.input_busqueda)

        # Categorías como botones (igual que en Ventas); se desplazan hacia el lado si no caben.
        self.scroll_categorias = QScrollArea()
        self.scroll_categorias.setObjectName("chipsScroll")
        self.scroll_categorias.setWidgetResizable(True)
        self.scroll_categorias.setFrameShape(QFrame.NoFrame)
        self.scroll_categorias.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_categorias.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_categorias.setFixedHeight(40)
        self._rueda_categorias = _RuedaHorizontal(self.scroll_categorias)
        contenido_chips = QWidget()
        contenido_chips.setObjectName("chipsContenido")
        self.fila_categorias = QHBoxLayout(contenido_chips)
        self.fila_categorias.setContentsMargins(0, 2, 0, 2)
        self.fila_categorias.setSpacing(ESPACIO_SM)
        self.fila_categorias.addStretch()
        self.scroll_categorias.setWidget(contenido_chips)
        self.grupo_categorias = QButtonGroup(self)
        self.grupo_categorias.setExclusive(True)
        tarjeta.cuerpo.addWidget(self.scroll_categorias)

        self.tabla_productos = QTableWidget(0, 3)
        self.tabla_productos.setHorizontalHeaderLabels(["Categoría", "Producto", "Stock"])
        cab = self.tabla_productos.horizontalHeader()
        cab.setSectionResizeMode(0, QHeaderView.Fixed)
        self.tabla_productos.setColumnWidth(0, ANCHO_COLUMNA_CATEGORIA)
        cab.setSectionResizeMode(1, QHeaderView.Stretch)
        cab.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        configurar_tabla_erp(self.tabla_productos, derecha=(2,), altura_fila=ALTURA_FILA_PRODUCTOS)
        self.tabla_productos.verticalScrollBar().valueChanged.connect(self._on_scroll_productos)
        self.tabla_productos.cellClicked.connect(lambda fila, _c: self._elegir_fila(fila, enfocar=False))
        self.tabla_productos.cellDoubleClicked.connect(lambda fila, _c: self._elegir_fila(fila, enfocar=True))
        self.tabla_productos.itemActivated.connect(lambda item: self._elegir_fila(item.row(), enfocar=True))
        tarjeta.cuerpo.addWidget(self.tabla_productos, 1)

        ayuda = QLabel("Haz clic en un producto para elegirlo.  Enter en el buscador elige el primero.")
        ayuda.setProperty("class", "ayuda")
        ayuda.setWordWrap(True)
        tarjeta.cuerpo.addWidget(ayuda)
        return tarjeta

    def _construir_panel_compra(self) -> QWidget:
        tarjeta = Card("Compra")

        self.label_producto = QLabel()
        self.label_producto.setStyleSheet("font-size: 15px; font-weight: 700;")
        self.label_producto.setWordWrap(True)
        tarjeta.cuerpo.addWidget(self.label_producto)

        ayuda_agregar = QLabel(
            "Elige la presentación en la que estás comprando (Unidad, Caja, Docena...). "
            "La cantidad es cuántas de esa presentación compraste, y el costo es el "
            "precio de esa presentación completa (ej. el precio de 1 caja)."
        )
        ayuda_agregar.setWordWrap(True)
        ayuda_agregar.setProperty("class", "ayuda")
        tarjeta.cuerpo.addWidget(ayuda_agregar)

        fila_agregar = QHBoxLayout()
        fila_agregar.setSpacing(ESPACIO_SM)
        self.combo_presentacion = QComboBox()
        self.combo_presentacion.setMinimumWidth(150)
        self.input_cantidad = _spinbox_con_punto(minimo=0.01)
        self.input_cantidad.setValue(0.01)
        self.input_cantidad.setToolTip("Cantidad comprada (en la presentación elegida)")
        self.input_costo = _spinbox_con_punto(prefijo="S/ ")
        self.input_costo.setToolTip("Costo de la presentación completa")
        self.btn_agregar = QPushButton("Agregar línea")
        self.btn_agregar.setProperty("class", "success")
        self.btn_agregar.clicked.connect(self._agregar_linea)
        # Enter en la cantidad pasa al costo; Enter en el costo agrega la línea.
        self.input_cantidad.lineEdit().returnPressed.connect(
            lambda: (self.input_costo.setFocus(), self.input_costo.selectAll()))
        self.input_costo.lineEdit().returnPressed.connect(self._agregar_linea)
        fila_agregar.addWidget(self.combo_presentacion, 1)
        fila_agregar.addWidget(self.input_cantidad)
        fila_agregar.addWidget(self.input_costo)
        fila_agregar.addWidget(self.btn_agregar)
        tarjeta.cuerpo.addLayout(fila_agregar)

        self.tabla_lineas = QTableWidget(0, 6)
        self.tabla_lineas.setHorizontalHeaderLabels(
            ["Producto", "Cant.", "Presentación", "Costo", "Subtotal", ""]
        )
        self.tabla_lineas.horizontalHeaderItem(3).setToolTip("Costo de la presentación completa")
        header_lineas = self.tabla_lineas.horizontalHeader()
        header_lineas.setSectionResizeMode(0, QHeaderView.Stretch)
        header_lineas.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header_lineas.setSectionResizeMode(5, QHeaderView.Fixed)
        self.tabla_lineas.setColumnWidth(5, 88)
        header_lineas.setMinimumSectionSize(60)
        configurar_tabla_erp(self.tabla_lineas, derecha=(3, 4), centro=(1,), altura_fila=44)
        self.tabla_lineas.setEditTriggers(QTableWidget.NoEditTriggers)
        tarjeta.cuerpo.addWidget(self.tabla_lineas, 1)

        self.label_total = self._crear_label_total()
        tarjeta.cuerpo.addWidget(self.label_total)

        botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "secondary")
        btn_cancelar.clicked.connect(self.reject)
        btn_guardar = QPushButton("Registrar compra")
        btn_guardar.setProperty("class", "success")
        btn_guardar.clicked.connect(self._guardar)
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        tarjeta.cuerpo.addLayout(botones)

        self._mostrar_producto_elegido()
        return tarjeta

    def _crear_label_total(self):
        label = QLabel("Total: S/ 0.00")
        label.setStyleSheet("font-size: 18px; font-weight: 700;")
        return label

    # --------------------------------------------- Lista de productos ----
    def _cargar_combos(self) -> None:
        self.combo_proveedor.addItem("Sin proveedor", None)
        for proveedor in self.producto_service.proveedores():
            self.combo_proveedor.addItem(proveedor["nombre"], proveedor["id"])

    def _cargar_categorias(self) -> None:
        categorias = self.producto_service.categorias_con_productos()
        self.scroll_categorias.setVisible(bool(categorias))
        opciones = [("Todas", None)] + [(c["nombre"], c["id"]) for c in categorias]
        for posicion, (nombre, categoria_id) in enumerate(opciones):
            boton = QPushButton(nombre)
            boton.setObjectName("chipCategoria")
            boton.setCheckable(True)
            boton.setCursor(Qt.PointingHandCursor)
            boton.setChecked(categoria_id is None)
            boton.clicked.connect(lambda _=False, c=categoria_id: self._filtrar_por_categoria(c))
            self.grupo_categorias.addButton(boton)
            self.fila_categorias.insertWidget(posicion, boton)

    def _filtrar_por_categoria(self, categoria_id) -> None:
        self._categoria_filtro = categoria_id
        self._buscar_productos()
        self.input_busqueda.setFocus()

    def _buscar_productos(self) -> None:
        """Nueva búsqueda: vuelve al inicio de la lista."""
        self._cargar_productos(offset=0)

    def _on_scroll_productos(self) -> None:
        if self._hay_mas_productos and cerca_del_final(self.tabla_productos):
            self._cargar_productos(offset=self._productos_cargados)

    def _cargar_productos(self, offset: int) -> None:
        # Se pide uno de más solo para saber si queda otra página; nunca se muestra.
        productos = self.producto_service.listar(
            self.input_busqueda.text(), TAMANO_PAGINA_PRODUCTOS + 1, offset, self._categoria_filtro)
        self._hay_mas_productos = len(productos) > TAMANO_PAGINA_PRODUCTOS
        nuevos = productos[:TAMANO_PAGINA_PRODUCTOS]
        with carga_rapida(self.tabla_productos):
            if offset == 0:
                self.tabla_productos.setRowCount(0)
            inicio = self.tabla_productos.rowCount()
            self.tabla_productos.setRowCount(inicio + len(nuevos))
            for i, p in enumerate(nuevos):
                fila = inicio + i
                categoria = QTableWidgetItem(p.categoria_nombre or "Sin categoría")
                categoria.setData(Qt.UserRole, p.id)
                categoria.setToolTip(p.categoria_nombre or "Sin categoría")
                self.tabla_productos.setItem(fila, 0, categoria)
                nombre = QTableWidgetItem(p.nombre)
                nombre.setToolTip(p.nombre)
                nombre.setData(Qt.UserRole, (p.id, p.nombre, p.unidad_medida))
                self.tabla_productos.setItem(fila, 1, nombre)
                stock = item_derecha(f"{p.stock_actual:g} {p.unidad_medida}".strip())
                colorear_stock(stock, p.agotado, p.stock_bajo, self._tema)
                self.tabla_productos.setItem(fila, 2, stock)
        self._productos_cargados = self.tabla_productos.rowCount()

    def _enter_en_busqueda(self) -> None:
        """Enter en el buscador: busca ya y elige el primer resultado."""
        self._timer_busqueda.stop()
        self._buscar_productos()
        if self.tabla_productos.rowCount() > 0:
            self._elegir_fila(0, enfocar=True)

    def _elegir_fila(self, fila: int, enfocar: bool) -> None:
        item = self.tabla_productos.item(fila, 1)
        datos = item.data(Qt.UserRole) if item else None
        if not datos:
            return
        self.tabla_productos.selectRow(fila)
        self._elegir_producto(*datos)
        if enfocar:
            self.input_cantidad.setFocus()
            self.input_cantidad.selectAll()

    def _elegir_producto(self, producto_id: int, nombre: str, unidad: str = "") -> None:
        self._producto_id = producto_id
        self._producto_nombre = nombre
        self._producto_unidad = (unidad or "").strip()
        self._cargar_presentaciones_producto()
        self._mostrar_producto_elegido()

    def _mostrar_producto_elegido(self) -> None:
        elegido = self._producto_id is not None
        self.label_producto.setText(
            f"Producto: {self._producto_nombre}" if elegido
            else "Elige un producto de la lista de la izquierda")
        for widget in (self.combo_presentacion, self.input_cantidad, self.input_costo, self.btn_agregar):
            widget.setEnabled(elegido)

    def _cargar_presentaciones_producto(self) -> None:
        """Recarga el combo de presentaciones (la unidad base + las que tenga el producto
        elegido) cada vez que cambia el producto seleccionado."""
        self.combo_presentacion.clear()
        unidad = self._producto_unidad
        base = "Unidad" if not unidad or unidad.lower() == "unidad" else unidad
        self.combo_presentacion.addItem(base, (1.0, base))
        if self._producto_id is not None:
            for p in self.producto_service.presentaciones(self._producto_id):
                self.combo_presentacion.addItem(
                    f"{p.nombre} (x{p.cantidad_unidades:g})", (p.cantidad_unidades, p.nombre)
                )

    def _agregar_linea(self) -> None:
        producto_id = self._producto_id
        if producto_id is None:
            return
        nombre = self._producto_nombre
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
        # Listo para el siguiente producto: se limpia la elección y el foco vuelve al buscador.
        self._producto_id = None
        self._producto_nombre = ""
        self._producto_unidad = ""
        self.combo_presentacion.clear()
        self._mostrar_producto_elegido()
        self.tabla_productos.clearSelection()
        self.input_busqueda.setFocus()
        self.input_busqueda.selectAll()

    def _refrescar_tabla(self) -> None:
        self.tabla_lineas.setRowCount(len(self.lineas))
        total = 0.0
        for fila, linea in enumerate(self.lineas):
            self.tabla_lineas.setItem(fila, 0, QTableWidgetItem(linea.nombre_producto))
            cantidad = QTableWidgetItem(f"{linea.cantidad_presentacion:g}")
            cantidad.setTextAlignment(Qt.AlignCenter)
            self.tabla_lineas.setItem(fila, 1, cantidad)
            self.tabla_lineas.setItem(
                fila, 2, QTableWidgetItem(f"{linea.presentacion_nombre} (x{linea.factor_unidades:g})")
            )
            self.tabla_lineas.setItem(fila, 3, item_derecha(formatear_moneda(linea.costo_presentacion_total)))
            self.tabla_lineas.setItem(fila, 4, item_derecha(formatear_moneda(linea.subtotal)))

            contenedor_botones = QWidget()
            layout_botones = QHBoxLayout(contenedor_botones)
            layout_botones.setContentsMargins(4, 4, 4, 4)
            layout_botones.setSpacing(4)

            btn_editar = QPushButton("✎")
            btn_editar.setToolTip("Editar esta línea")
            btn_editar.setProperty("class", "secondary")
            btn_editar.setFixedSize(34, 32)
            btn_editar.setStyleSheet("padding: 0px;")
            btn_editar.clicked.connect(lambda _, idx=fila: self._editar_linea(idx))
            layout_botones.addWidget(btn_editar)

            btn_quitar = QPushButton("✕")
            btn_quitar.setToolTip("Quitar esta línea")
            btn_quitar.setProperty("class", "danger")
            btn_quitar.setFixedSize(34, 32)
            btn_quitar.setStyleSheet("padding: 0px;")
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

        producto = self.producto_service.obtener(linea.producto_id)
        self._elegir_producto(linea.producto_id, linea.nombre_producto,
                              producto.unidad_medida if producto else "")

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