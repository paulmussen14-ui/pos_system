"""

Página de Ventas.

Flujo: buscar producto -> agregar al carrito con cantidad -> los subtotales

y el total se recalculan automáticamente -> buscar y seleccionar cliente

(opcional) -> elegir método de pago -> registrar venta -> previsualizar e

imprimir el ticket. El costo interno nunca se muestra aquí.

También permite consultar las ventas recientes para anularlas, devolver

un producto o "corregirlas" (anular + recargar en el carrito) en caso de

error, sin modificar nunca una venta ya registrada directamente.

"""

from PySide6.QtWidgets import (

    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,

    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QDoubleSpinBox,

    QMessageBox, QSplitter, QDialog

)

from PySide6.QtCore import Qt, QTimer, QThreadPool

from services.producto_service import ProductoService

from services.venta_service import VentaService, VentaError

from services.cliente_service import ClienteService

from services.configuracion_service import ConfiguracionService

from services.caja_service import CajaService
from services.ticket_extras_service import TicketExtrasService

from models.venta import VentaDetalleItem

from printing.ticket_template import ancho_caracteres_por_papel

from ui.widgets.ticket_preview_dialog import TicketPreviewDialog

from ui.ventas.venta_dialog_devolucion import VentaDetalleDialog

from utils.validators import formatear_moneda

from utils.worker import Worker

from utils.logger import logger

ALTURA_FILA_CARRITO = 44

ALTURA_FILA_RESULTADOS = 34

ANCHO_COLUMNA_NUMERO = 32

ANCHO_COLUMNA_QUITAR = 56

# Estilo compartido para que todas las tablas de la app (Ventas, Clientes,

# Compras) tengan la misma separación visual entre encabezado y filas.

# El encabezado usa un tono azul-gris suave en vez de blanco/gris plano.

# IMPORTANTE: esto solo se pinta bien si en main.py se llamó

# app.setStyle("Fusion") antes de crear las ventanas.

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

class VentasPage(QWidget):

    def __init__(self, usuario, parent=None):

        super().__init__(parent)

        self.usuario = usuario

        self.producto_service = ProductoService()

        self.venta_service = VentaService()

        self.cliente_service = ClienteService()

        self.config_service = ConfiguracionService()

        self.caja_service = CajaService()

        self.carrito: list[VentaDetalleItem] = []

        self.cliente_seleccionado_id: int | None = None

        self.cliente_seleccionado_nombre: str | None = None

        # Debounce: evita disparar una consulta a la BD por cada tecla

        # presionada en las búsquedas de producto y de cliente.

        self._timer_busqueda_producto = QTimer(self)

        self._timer_busqueda_producto.setSingleShot(True)

        self._timer_busqueda_producto.setInterval(300)

        self._timer_busqueda_producto.timeout.connect(self._buscar_productos)

        self._timer_busqueda_cliente = QTimer(self)

        self._timer_busqueda_cliente.setSingleShot(True)

        self._timer_busqueda_cliente.setInterval(300)

        self._timer_busqueda_cliente.timeout.connect(self._buscar_clientes)

        # Guardan el texto que disparó la búsqueda en curso, para poder

        # descartar una respuesta que llega tarde y ya no corresponde a lo

        # que el usuario tiene escrito ahora (puede pasar si dos búsquedas

        # quedan en vuelo casi al mismo tiempo).

        self._ultima_busqueda_producto: str | None = None

        self._ultima_busqueda_cliente: str | None = None


        self._construir_ui()
        self.actualizar()
        self.actualizar_totales()


    # ---------------------------------------------------------- UI ----

    def _construir_ui(self) -> None:

        layout_principal = QVBoxLayout(self)

        layout_principal.setContentsMargins(24, 24, 24, 24)

        layout_principal.setSpacing(16)

        cabecera = QHBoxLayout()

        titulo = QLabel("Ventas")

        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")

        cabecera.addWidget(titulo)

        cabecera.addStretch()

        btn_ventas_recientes = QPushButton("Ventas recientes")

        btn_ventas_recientes.setProperty("class", "secondary")

        btn_ventas_recientes.clicked.connect(self._ver_ventas_recientes)

        cabecera.addWidget(btn_ventas_recientes)

        layout_principal.addLayout(cabecera)

        splitter = QSplitter()

        # ---- Columna izquierda: búsqueda de productos ----

        columna_productos = QVBoxLayout()

        label_productos = QLabel("Productos")

        label_productos.setStyleSheet("font-weight: 600;")

        columna_productos.addWidget(label_productos)

        self.input_busqueda_producto = QLineEdit()

        self.input_busqueda_producto.setPlaceholderText("Buscar producto por nombre...")

        self.input_busqueda_producto.textChanged.connect(

            lambda: self._timer_busqueda_producto.start()

        )

        columna_productos.addWidget(self.input_busqueda_producto)

        self.tabla_productos = QTableWidget(0, 4)

        self.tabla_productos.setHorizontalHeaderLabels(["Categoría", "Producto", "Precio", "Stock"])

        header_productos = self.tabla_productos.horizontalHeader()

        header_productos.setSectionResizeMode(0, QHeaderView.ResizeToContents)

        header_productos.setSectionResizeMode(1, QHeaderView.Stretch)

        header_productos.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        header_productos.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.tabla_productos.verticalHeader().setVisible(False)

        self.tabla_productos.setEditTriggers(QTableWidget.NoEditTriggers)

        self.tabla_productos.setSelectionBehavior(QTableWidget.SelectRows)

        self.tabla_productos.setAlternatingRowColors(True)

        self.tabla_productos.setStyleSheet(ESTILO_TABLA)

        self.tabla_productos.cellDoubleClicked.connect(self._agregar_producto_seleccionado)

        columna_productos.addWidget(self.tabla_productos)

        ayuda_productos = QLabel("Doble clic en un producto para agregarlo al carrito.")

        ayuda_productos.setWordWrap(True)

        ayuda_productos.setStyleSheet("color: #6b7280; font-size: 11px;")

        columna_productos.addWidget(ayuda_productos)

        contenedor_productos = QWidget()

        contenedor_productos.setLayout(columna_productos)

        contenedor_productos.setMinimumWidth(320)

        # ---- Columna central: búsqueda de clientes ----

        columna_clientes = QVBoxLayout()

        label_clientes = QLabel("Cliente")

        label_clientes.setStyleSheet("font-weight: 600;")

        columna_clientes.addWidget(label_clientes)

        self.input_busqueda_cliente = QLineEdit()

        self.input_busqueda_cliente.setPlaceholderText("Buscar cliente por nombre...")

        self.input_busqueda_cliente.textChanged.connect(

            lambda: self._timer_busqueda_cliente.start()

        )

        columna_clientes.addWidget(self.input_busqueda_cliente)

        self.tabla_clientes = QTableWidget(0, 2)

        self.tabla_clientes.setHorizontalHeaderLabels(["Nombre", "Teléfono"])

        header_clientes = self.tabla_clientes.horizontalHeader()

        header_clientes.setSectionResizeMode(0, QHeaderView.Stretch)

        header_clientes.setSectionResizeMode(1, QHeaderView.ResizeToContents)

        self.tabla_clientes.verticalHeader().setVisible(False)

        self.tabla_clientes.setEditTriggers(QTableWidget.NoEditTriggers)

        self.tabla_clientes.setSelectionBehavior(QTableWidget.SelectRows)

        self.tabla_clientes.setAlternatingRowColors(True)

        self.tabla_clientes.setStyleSheet(ESTILO_TABLA)

        self.tabla_clientes.cellDoubleClicked.connect(self._seleccionar_cliente)

        columna_clientes.addWidget(self.tabla_clientes)

        self.label_cliente_seleccionado = QLabel("Sin cliente seleccionado (venta general)")

        self.label_cliente_seleccionado.setWordWrap(True)

        self.label_cliente_seleccionado.setStyleSheet("font-weight: 600; color: #2563eb;")

        columna_clientes.addWidget(self.label_cliente_seleccionado)

        btn_quitar_cliente = QPushButton("Quitar cliente")

        btn_quitar_cliente.setProperty("class", "secondary")

        btn_quitar_cliente.clicked.connect(self._quitar_cliente)

        columna_clientes.addWidget(btn_quitar_cliente)

        ayuda_clientes = QLabel("Doble clic en un cliente de la lista para asociarlo a la venta.")

        ayuda_clientes.setWordWrap(True)

        ayuda_clientes.setStyleSheet("color: #6b7280; font-size: 11px;")

        columna_clientes.addWidget(ayuda_clientes)

        contenedor_clientes = QWidget()

        contenedor_clientes.setLayout(columna_clientes)

        contenedor_clientes.setMinimumWidth(280)

        # ---- Columna derecha: carrito ----

        columna_derecha = QVBoxLayout()

        self.tabla_carrito = QTableWidget(0, 7)

        self.tabla_carrito.setHorizontalHeaderLabels(

            ["#", "Producto", "Presentación", "Cantidad", "Precio", "Subtotal", ""]

        )

        header = self.tabla_carrito.horizontalHeader()

        header.setSectionResizeMode(0, QHeaderView.Fixed)

        header.setSectionResizeMode(1, QHeaderView.Stretch)

        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        header.setSectionResizeMode(6, QHeaderView.Fixed)

        self.tabla_carrito.setColumnWidth(0, ANCHO_COLUMNA_NUMERO)

        self.tabla_carrito.setColumnWidth(6, ANCHO_COLUMNA_QUITAR)

        self.tabla_carrito.verticalHeader().setVisible(False)

        self.tabla_carrito.setEditTriggers(QTableWidget.NoEditTriggers)

        self.tabla_carrito.setAlternatingRowColors(True)

        self.tabla_carrito.setStyleSheet(ESTILO_TABLA)

        columna_derecha.addWidget(self.tabla_carrito)

        fila_totales = QHBoxLayout()

        fila_totales.addWidget(QLabel("Descuento:"))

        self.input_descuento = QDoubleSpinBox()

        self.input_descuento.setMaximum(999999)

        self.input_descuento.setPrefix("S/ ")

        self.input_descuento.valueChanged.connect(self.actualizar_totales)

        fila_totales.addWidget(self.input_descuento)

        fila_totales.addStretch()

        self.label_total = QLabel("Total: S/ 0.00")

        self.label_total.setStyleSheet("font-size: 22px; font-weight: 700;")

        fila_totales.addWidget(self.label_total)

        columna_derecha.addLayout(fila_totales)

        fila_venta = QHBoxLayout()

        fila_venta.addWidget(QLabel("Método de pago:"))

        self.combo_metodo_pago = QComboBox()

        fila_venta.addWidget(self.combo_metodo_pago)
        fila_venta.addSpacing(16)
        fila_venta.addWidget(QLabel("Chofer:"))
        self.input_chofer = QLineEdit()
        self.input_chofer.setPlaceholderText("Chofer de esta venta")
        self.input_chofer.setMinimumWidth(180)
        fila_venta.addWidget(self.input_chofer)

        fila_venta.addStretch()

        columna_derecha.addLayout(fila_venta)

        fila_botones = QHBoxLayout()

        btn_limpiar = QPushButton("Limpiar carrito")

        btn_limpiar.setProperty("class", "secondary")

        btn_limpiar.setMinimumHeight(36)

        btn_limpiar.clicked.connect(self._limpiar_carrito)

        fila_botones.addWidget(btn_limpiar)

        btn_registrar = QPushButton("Registrar venta")

        btn_registrar.setProperty("class", "success")

        btn_registrar.setMinimumHeight(36)

        btn_registrar.clicked.connect(self._registrar_venta)

        fila_botones.addWidget(btn_registrar)

        columna_derecha.addLayout(fila_botones)

        contenedor_derecho = QWidget()

        contenedor_derecho.setLayout(columna_derecha)

        # ---- Columna izquierda: Cliente arriba, Productos debajo ----

        # (apilados verticalmente para que ambas tablas tengan ancho

        # completo y se vean todos sus campos sin comprimirse).

        columna_izquierda = QVBoxLayout()

        columna_izquierda.setSpacing(16)

        columna_izquierda.addWidget(contenedor_clientes)

        columna_izquierda.addWidget(contenedor_productos)

        contenedor_izquierdo = QWidget()

        contenedor_izquierdo.setLayout(columna_izquierda)

        splitter.addWidget(contenedor_izquierdo)

        splitter.addWidget(contenedor_derecho)

        splitter.setStretchFactor(0, 3)

        splitter.setStretchFactor(1, 2)

        layout_principal.addWidget(splitter)

    def actualizar(self) -> None:

        self._cargar_metodos_pago()
        self._cargar_chofer_por_defecto()

        self._buscar_clientes()

        self._buscar_productos()

    def _chofer_predeterminado(self) -> str:
        """Chofer guardado en Configuración > Datos del ticket."""
        try:
            return (TicketExtrasService().para_ticket().get("chofer") or "").strip()
        except Exception:
            logger.exception("No se pudo leer el chofer predeterminado")
            return ""

    def _cargar_chofer_por_defecto(self, forzar: bool = False) -> None:
        """Pone el chofer predeterminado en el campo. No pisa lo que el usuario
        escribió a mano, salvo que se pida (forzar) o siga siendo el anterior
        predeterminado."""
        nuevo = self._chofer_predeterminado()
        actual = self.input_chofer.text().strip()
        anterior = getattr(self, "_chofer_default_anterior", "")
        if forzar or not actual or actual == anterior:
            self.input_chofer.setText(nuevo)
        self._chofer_default_anterior = nuevo

    def _cargar_metodos_pago(self) -> None:

        metodo_actual = self.combo_metodo_pago.currentData()

        self.combo_metodo_pago.clear()

        for metodo in self.venta_service.metodos_pago():

            self.combo_metodo_pago.addItem(metodo["nombre"], metodo["id"])

        if metodo_actual is not None:

            idx = self.combo_metodo_pago.findData(metodo_actual)

            if idx >= 0:

                self.combo_metodo_pago.setCurrentIndex(idx)

    # ---------------------------------------------------- Búsqueda ----

    def _buscar_productos(self) -> None:
        texto = self.input_busqueda_producto.text()
        logger.debug("Buscando productos: %r", texto)

        self._ultima_busqueda_producto = texto

        worker = Worker(self.producto_service.listar, texto)

        worker.signals.finished.connect(
            lambda productos, texto=texto: self._on_productos_listos(texto, productos)
        )

        worker.signals.error.connect(self._on_error_busqueda)

        QThreadPool.globalInstance().start(worker)

    def _on_productos_listos(self, texto: str, productos) -> None:
        if texto != self._ultima_busqueda_producto:
            logger.debug(
                "Descartando resultados de productos atrasados (texto=%r, actual=%r)",
                texto, self._ultima_busqueda_producto,
            )
            return

        moneda = self.config_service.obtener().get("moneda", "S/")

        self.tabla_productos.setRowCount(len(productos))

        for fila, p in enumerate(productos):
            categoria = p.categoria_nombre or "Sin categoría"

            item_categoria = QTableWidgetItem(categoria)
            item_categoria.setData(Qt.UserRole, p.id)

            self.tabla_productos.setItem(fila, 0, item_categoria)
            self.tabla_productos.setItem(fila, 1, QTableWidgetItem(p.nombre))
            self.tabla_productos.setItem(
                fila,
                2,
                QTableWidgetItem(
                    formatear_moneda(p.precio_venta_actual, moneda)
                )
            )
            self.tabla_productos.setItem(
                fila,
                3,
                QTableWidgetItem(str(p.stock_actual))
            )

            self.tabla_productos.setRowHeight(
                fila,
                ALTURA_FILA_RESULTADOS
            )

    def _on_error_busqueda(self, mensaje: str) -> None:

        logger.error("Error en búsqueda en segundo plano: %s", mensaje)

    def _agregar_producto_seleccionado(self, fila: int, columna: int) -> None:

        item = self.tabla_productos.item(fila, 0)

        if item is None:

            return

        producto_id = item.data(Qt.UserRole)

        producto = self.producto_service.obtener(producto_id)

        if not producto:

            return

        if producto.stock_actual <= 0:

            QMessageBox.warning(self, "Sin stock", f"'{producto.nombre}' no tiene stock disponible.")

            return

        existente = next((l for l in self.carrito if l.producto_id == producto.id), None)

        if existente:

            # Se suma 1 en la MISMA presentación que ya tenía esa línea,

            # no en unidades base, para no descuadrar lo que el usuario ya

            # había elegido (ej. si ya vendía por "Caja", sigue sumando cajas).

            existente.cantidad_presentacion += 1

            existente.cantidad = round(existente.cantidad_presentacion * existente.factor_unidades, 4)

        else:

            self.carrito.append(VentaDetalleItem(

                producto_id=producto.id,

                nombre_producto=producto.nombre,

                cantidad=1,

                precio_venta_unitario=producto.precio_venta_actual,

                costo_unitario_snapshot=producto.costo_promedio_actual,

                presentacion_nombre="Unidad",

                cantidad_presentacion=1,

                factor_unidades=1.0,

            ))

        self._refrescar_tabla_carrito()

    def _buscar_clientes(self) -> None:
        texto = self.input_busqueda_cliente.text()
        logger.debug("Buscando clientes: %r", texto)

        self._ultima_busqueda_cliente = texto

        worker = Worker(self.cliente_service.listar, texto)

        worker.signals.finished.connect(
            lambda clientes, texto=texto: self._on_clientes_listos(texto, clientes)
        )

        worker.signals.error.connect(self._on_error_busqueda)

        QThreadPool.globalInstance().start(worker)

    def _on_clientes_listos(self, texto: str, clientes) -> None:
        if texto != self._ultima_busqueda_cliente:
            logger.debug(
                "Descartando resultados de clientes atrasados (texto=%r, actual=%r)",
                texto, self._ultima_busqueda_cliente,
            )
            return

        self.tabla_clientes.setRowCount(len(clientes))

        for fila, c in enumerate(clientes):
            item_nombre = QTableWidgetItem(c.nombre)
            item_nombre.setData(Qt.UserRole, (c.id, c.nombre))

            self.tabla_clientes.setItem(fila, 0, item_nombre)
            self.tabla_clientes.setItem(
                fila,
                1,
                QTableWidgetItem(c.telefono or "-")
            )

            self.tabla_clientes.setRowHeight(
                fila,
                ALTURA_FILA_RESULTADOS
            )

    def _seleccionar_cliente(self, fila: int, columna: int) -> None:

        item = self.tabla_clientes.item(fila, 0)

        if item is None:

            return

        cliente_id, cliente_nombre = item.data(Qt.UserRole)

        self.cliente_seleccionado_id = cliente_id

        self.cliente_seleccionado_nombre = cliente_nombre

        self.label_cliente_seleccionado.setText(f"Cliente: {cliente_nombre}")

    def _quitar_cliente(self) -> None:

        self.cliente_seleccionado_id = None

        self.cliente_seleccionado_nombre = None

        self.label_cliente_seleccionado.setText("Sin cliente seleccionado (venta general)")

    # ------------------------------------------------------ Carrito ----

    def _refrescar_tabla_carrito(self) -> None:

        moneda = self.config_service.obtener().get("moneda", "S/")

        self.tabla_carrito.setRowCount(len(self.carrito))

        for fila, linea in enumerate(self.carrito):

            item_numero = QTableWidgetItem(str(fila + 1))

            item_numero.setTextAlignment(Qt.AlignCenter)

            self.tabla_carrito.setItem(fila, 0, item_numero)

            self.tabla_carrito.setItem(fila, 1, QTableWidgetItem(linea.nombre_producto))

            # Combo de presentación: "Unidad" + las que tenga configuradas el

            # producto (igual que en Compras). Se arma y se posiciona en la

            # presentación actual de la línea ANTES de conectar la señal,

            # para que ese setCurrentIndex no dispare _cambiar_presentacion.

            combo_presentacion = QComboBox()

            combo_presentacion.addItem("Unidad", (1.0, "Unidad"))

            for p in self.producto_service.presentaciones(linea.producto_id):

                combo_presentacion.addItem(

                    f"{p.nombre} (x{p.cantidad_unidades:g})", (p.cantidad_unidades, p.nombre)

                )

            idx_actual = 0

            for i in range(combo_presentacion.count()):

                _, nombre_i = combo_presentacion.itemData(i)

                if nombre_i == linea.presentacion_nombre:

                    idx_actual = i

                    break

            combo_presentacion.setCurrentIndex(idx_actual)

            combo_presentacion.currentIndexChanged.connect(

                lambda _, idx=fila, combo=combo_presentacion: self._cambiar_presentacion(idx, combo)

            )

            self.tabla_carrito.setCellWidget(fila, 2, combo_presentacion)

            # La cantidad que edita el usuario es la cantidad DE ESA

            # PRESENTACIÓN (ej. "2" cajas), no las unidades base.

            spin_cantidad = QDoubleSpinBox()

            spin_cantidad.setMinimum(0.01)

            spin_cantidad.setMaximum(999999)

            spin_cantidad.setValue(linea.cantidad_presentacion)

            spin_cantidad.valueChanged.connect(lambda valor, idx=fila: self._cambiar_cantidad(idx, valor))

            self.tabla_carrito.setCellWidget(fila, 3, spin_cantidad)

            self.tabla_carrito.setItem(

                fila, 4, QTableWidgetItem(formatear_moneda(linea.precio_presentacion_unitario, moneda))

            )

            self.tabla_carrito.setItem(fila, 5, QTableWidgetItem(formatear_moneda(linea.subtotal, moneda)))

            btn_quitar = QPushButton("✕")

            btn_quitar.setProperty("class", "danger")

            btn_quitar.setMinimumSize(40, 32)

            btn_quitar.clicked.connect(lambda _, idx=fila: self._quitar_linea(idx))

            self.tabla_carrito.setCellWidget(fila, 6, btn_quitar)

            self.tabla_carrito.setRowHeight(fila, ALTURA_FILA_CARRITO)

        self.actualizar_totales()

    def _cambiar_cantidad(self, indice: int, nueva_cantidad_presentacion: float) -> None:

        if 0 <= indice < len(self.carrito):

            linea = self.carrito[indice]

            linea.cantidad_presentacion = nueva_cantidad_presentacion

            linea.cantidad = round(nueva_cantidad_presentacion * linea.factor_unidades, 4)

            moneda = self.config_service.obtener().get("moneda", "S/")

            self.tabla_carrito.setItem(indice, 5, QTableWidgetItem(

                formatear_moneda(linea.subtotal, moneda)

            ))

            self.actualizar_totales()

    def _cambiar_presentacion(self, indice: int, combo: QComboBox) -> None:

        """Al elegir otra presentación en el carrito, se recalcula el precio

        por unidad base y las unidades base (cantidad) a partir de la

        cantidad de esa presentación que ya tenía la línea, igual que en

        Compras."""

        if not (0 <= indice < len(self.carrito)):

            return

        linea = self.carrito[indice]

        factor, nombre_presentacion = combo.currentData() or (1.0, "Unidad")

        if nombre_presentacion == "Unidad":

            producto = self.producto_service.obtener(linea.producto_id)

            precio_unitario_base = producto.precio_venta_actual if producto else linea.precio_venta_unitario

        else:

            presentacion = next(

                (p for p in self.producto_service.presentaciones(linea.producto_id)

                 if p.nombre == nombre_presentacion),

                None,

            )

            precio_unitario_base = presentacion.precio_por_unidad if presentacion else linea.precio_venta_unitario

        linea.presentacion_nombre = nombre_presentacion

        linea.factor_unidades = factor

        linea.precio_venta_unitario = precio_unitario_base

        linea.cantidad = round(linea.cantidad_presentacion * factor, 4)

        self._refrescar_tabla_carrito()

    def _quitar_linea(self, indice: int) -> None:

        if 0 <= indice < len(self.carrito):

            del self.carrito[indice]

            self._refrescar_tabla_carrito()

    def _limpiar_carrito(self) -> None:

        self.carrito.clear()

        self._refrescar_tabla_carrito()

    def actualizar_totales(self) -> None:

        moneda = self.config_service.obtener().get("moneda", "S/")

        subtotal = sum(l.subtotal for l in self.carrito)

        descuento = self.input_descuento.value()

        total = max(subtotal - descuento, 0)

        self.label_total.setText(f"Total: {formatear_moneda(total, moneda)}")

    # ------------------------------------------------- Registrar venta ----

    def _registrar_venta(self) -> None:

        if not self.carrito:

            QMessageBox.warning(self, "Carrito vacío", "Agrega al menos un producto para registrar la venta.")

            return

        moneda = self.config_service.obtener().get("moneda", "S/")

        subtotal = sum(l.subtotal for l in self.carrito)

        descuento = self.input_descuento.value()

        total = max(subtotal - descuento, 0)

        cliente_texto = self.cliente_seleccionado_nombre or "Sin cliente (venta general)"

        metodo_texto = self.combo_metodo_pago.currentText()

        respuesta = QMessageBox.question(

            self, "Confirmar venta",

            f"¿Confirmar el registro de esta venta?\n\n"

            f"Cliente: {cliente_texto}\n"

            f"Método de pago: {metodo_texto}\n"

            f"Productos: {len(self.carrito)}\n"

            f"Total: {formatear_moneda(total, moneda)}"

        )

        if respuesta != QMessageBox.Yes:

            return

        metodo_pago_id = self.combo_metodo_pago.currentData()

        try:

            venta_id = self.venta_service.registrar_venta(

                lineas=self.carrito,

                usuario_id=self.usuario.id,

                cliente_id=self.cliente_seleccionado_id,

                metodo_pago_id=metodo_pago_id,

                descuento=self.input_descuento.value(),
                chofer=self.input_chofer.text(),

            )

        except VentaError as e:

            QMessageBox.warning(self, "No se pudo registrar la venta", str(e))

            return

        self._mostrar_vista_previa_ticket(venta_id)

        self._reiniciar_formulario_venta()

    def _reiniciar_formulario_venta(self) -> None:

        """Limpia carrito/cliente/descuento y vuelve a poblar las tablas de

        productos y clientes. .clear() en un QLineEdit vacío no dispara

        textChanged, así que hay que forzar la búsqueda para que la lista

        de productos nunca quede vacía tras registrar una venta."""

        self.carrito.clear()

        self.input_descuento.setValue(0)

        self.input_busqueda_producto.clear()

        self._buscar_productos()

        self._quitar_cliente()

        self.input_busqueda_cliente.clear()

        self._buscar_clientes()

        self._refrescar_tabla_carrito()

        self._cargar_metodos_pago()
        self._cargar_chofer_por_defecto(forzar=True)

    def _mostrar_vista_previa_ticket(self, venta_id: int) -> None:

        venta = self.venta_service.obtener_venta_con_lineas(venta_id)

        config_negocio = self.config_service.obtener()

        config_impresion = self.config_service.obtener_config_impresion()

        ancho = ancho_caracteres_por_papel(config_impresion.get("ancho_papel_mm"))

        nombre_impresora = config_impresion.get("nombre_impresora") if config_impresion.get("activo") else None

        imprimir_dos_copias = bool(config_impresion.get("imprimir_dos_copias", True))

        dialogo = TicketPreviewDialog(

            venta,

            config_negocio,

            nombre_impresora,

            ancho_caracteres=ancho,

            imprimir_dos_copias=imprimir_dos_copias,

            parent=self,

        )

        dialogo.setWindowTitle(f"Venta #{venta_id} registrada — Vista previa del ticket")

        dialogo.exec()

    # ------------------------------------------------- Ventas recientes ----

    def _ver_ventas_recientes(self) -> None:

        from datetime import date

        hoy = date.today().isoformat()

        ventas = self.venta_service.listar_ventas(fecha_desde=hoy, fecha_hasta=hoy)

        moneda = self.config_service.obtener().get("moneda", "S/")

        dialogo = QDialog(self)

        dialogo.setWindowTitle("Ventas de hoy")

        dialogo.resize(560, 420)

        layout = QVBoxLayout(dialogo)

        tabla = QTableWidget(0, 5)

        tabla.setHorizontalHeaderLabels(["#", "Fecha", "Cliente", "Total", ""])

        header = tabla.horizontalHeader()

        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)

        header.setSectionResizeMode(1, QHeaderView.Stretch)

        header.setSectionResizeMode(2, QHeaderView.Stretch)

        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        header.setSectionResizeMode(4, QHeaderView.Fixed)

        tabla.setColumnWidth(4, 160)

        tabla.verticalHeader().setVisible(False)

        tabla.setEditTriggers(QTableWidget.NoEditTriggers)

        tabla.setAlternatingRowColors(True)

        tabla.setStyleSheet(ESTILO_TABLA)

        layout.addWidget(tabla)

        if not ventas:

            layout.addWidget(QLabel("Todavía no hay ventas registradas hoy."))

        tabla.setRowCount(len(ventas))

        for fila, v in enumerate(ventas):

            estado = " (anulada)" if v["estado"] == "anulada" else ""

            tabla.setItem(fila, 0, QTableWidgetItem(str(v["id"])))

            tabla.setItem(fila, 1, QTableWidgetItem(str(v["fecha"])))

            tabla.setItem(fila, 2, QTableWidgetItem((v.get("cliente_nombre") or "Sin cliente") + estado))

            tabla.setItem(fila, 3, QTableWidgetItem(formatear_moneda(v["total"], moneda)))

            btn_ver = QPushButton("Ver / Corregir")

            btn_ver.setProperty("class", "secondary")

            btn_ver.setMinimumHeight(32)

            btn_ver.clicked.connect(lambda _, vid=v["id"]: self._abrir_detalle_venta(vid, dialogo))

            tabla.setCellWidget(fila, 4, btn_ver)

            tabla.setRowHeight(fila, 40)

        btn_cerrar = QPushButton("Cerrar")

        btn_cerrar.clicked.connect(dialogo.accept)

        layout.addWidget(btn_cerrar)

        dialogo.exec()

    def _abrir_detalle_venta(self, venta_id: int, dialogo_padre: QDialog) -> None:

        detalle = VentaDetalleDialog(venta_id, self.usuario, parent=self)

        detalle.venta_lista_para_recrear.connect(self._precargar_carrito_desde_venta)

        detalle.exec()

        dialogo_padre.accept()

    def _precargar_carrito_desde_venta(self, lineas: list[dict], cliente_id: int | None) -> None:

        self.carrito.clear()

        for linea in lineas:

            # Ventas anteriores a este cambio no tienen presentación guardada

            # (quedó NULL): se tratan como "Unidad" x1, igual que en el ticket.

            self.carrito.append(VentaDetalleItem(

                producto_id=linea["producto_id"],

                nombre_producto=linea["producto_nombre"],

                cantidad=linea["cantidad"],

                precio_venta_unitario=linea["precio_venta_unitario"],

                costo_unitario_snapshot=linea.get("costo_unitario_snapshot", 0.0),

                presentacion_nombre=linea.get("presentacion_nombre") or "Unidad",

                cantidad_presentacion=linea.get("cantidad_presentacion"),

                factor_unidades=linea.get("factor_unidades") or 1.0,

            ))

        self._refrescar_tabla_carrito()

        if cliente_id:

            cliente = self.cliente_service.obtener_por_id(cliente_id)

            if cliente:

                self.cliente_seleccionado_id = cliente.id

                self.cliente_seleccionado_nombre = cliente.nombre

                self.label_cliente_seleccionado.setText(f"Cliente: {cliente.nombre}")

        QMessageBox.information(

            self, "Venta anulada para corrección",

            "La venta anterior fue anulada y sus productos se cargaron en el "

            "carrito. Ajusta lo que sea necesario y registra la venta de nuevo."

        )