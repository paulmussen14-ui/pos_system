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
    QFrame, QGridLayout, QStackedLayout, QScrollArea, QButtonGroup,

    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,

    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QDoubleSpinBox,

    QMessageBox, QSplitter, QDialog, QSizePolicy

)

from PySide6.QtCore import Qt, QTimer, QThreadPool, QObject, QEvent, QPoint
from PySide6.QtGui import QKeySequence, QShortcut

from services.producto_service import ProductoService

from services.venta_service import VentaService, VentaError

from services.cliente_service import ClienteService

from services.configuracion_service import ConfiguracionService

from services.caja_service import CajaService
from services.ticket_extras_service import TicketExtrasService

from services.cupon_service import CuponService, CuponError

from services.proforma_service import ProformaService, ProformaError

from models.venta import VentaDetalleItem

from printing.ticket_template import ancho_caracteres_por_papel

from ui.widgets.ticket_preview_dialog import TicketPreviewDialog

from ui.ventas.venta_dialog_devolucion import VentaDetalleDialog

from utils.validators import formatear_moneda

from utils.worker import Worker

from utils.tablas import carga_rapida, cerca_del_final

from utils.logger import logger
from ui.iconos import icono, pixmap_icono
from ui.tokens import MARGEN_PAGINA, ESPACIO_SM, ESPACIO_MD
from ui.widgets.card import Card
from ui.widgets.page_header import PageHeader
from ui.widgets.status_badge import StatusBadge
from ui.widgets.tabla_erp import (
    configurar_tabla_erp, item_derecha, item_centro, colorear_stock, ALINEAR_DERECHA,
)

ALTURA_FILA_CARRITO = 44

# --- Responsive (laptops con escala de Windows 125 % / 150 %) ---
# El carrito nunca baja de esta altura: si la pantalla es muy baja, la página
# se desplaza (scroll) en vez de aplastar el carrito y encimar los totales.
ALTURA_MINIMA_CARRITO = 190
ALTURA_MINIMA_CUERPO = 470          # altura mínima del cuerpo antes de activar el scroll
ALTURA_MINIMA_CUERPO_BAJA = 400     # idem en pantallas bajas
ALTURA_MINIMA_CARRITO_BAJA = 110    # carrito mínimo en pantallas bajas
ANCHO_MINIMO_PANEL_PRODUCTOS = 300
ANCHO_MINIMO_PANEL_VENTA = 440
ALTURA_PANTALLA_BAJA = 680          # por debajo de esto se reducen márgenes y espacios
ANCHO_PANTALLA_ANGOSTA = 1040       # por debajo de esto se acortan los textos de ayuda
ALTURA_MAX_RESULTADOS_CLIENTE = 200
ANCHO_PANEL_PARA_CATEGORIA = 420    # panel de productos más angosto que esto: sin columna Categoría
SUBTITULO_LARGO = "F2 Producto   ·   F4 Cliente   ·   F9 Cobrar   ·   Esc Limpiar búsqueda   ·   Ctrl+N Nueva venta"
SUBTITULO_CORTO = "F2 Producto  ·  F4 Cliente  ·  F9 Cobrar"

ALTURA_FILA_RESULTADOS = 34

ALTURA_FILA_PRODUCTOS = 40

TEXTO_VENTA_GENERAL = "Venta general (sin cliente)"
TIPOS_CLIENTE_LIBRE = ["Mostrador", "Delivery", "Premium", "Mayorista", "Otro"]

# Las listas de productos y clientes se piden por páginas: se muestran las
# primeras TAMANO_PAGINA_RESULTADOS y las siguientes se cargan solas al hacer
# scroll hasta el final. Así abrir Ventas cuesta lo mismo con 500 que con
# 50 000 productos.
TAMANO_PAGINA_RESULTADOS = 100

ANCHO_COLUMNA_NUMERO = 28

ANCHO_COLUMNA_QUITAR = 46
ANCHO_COLUMNA_PRESENTACION = 112
ANCHO_COLUMNA_CANTIDAD = 82
ANCHO_COLUMNA_MONTO = 80
ANCHO_COLUMNA_CATEGORIA = 96

# El estilo de las tablas sale del tema (ui/estilos_erp.py): es igual en todas las
# pantallas y en los dos temas. La constante queda vacía para que los
# setStyleSheet(ESTILO_TABLA) existentes no pisen el tema con colores fijos.
# (Recuerda: main.py usa app.setStyle("Fusion"), necesario para pintar los encabezados.)
ESTILO_TABLA = ""

class _FlechaAbajoALista(QObject):
    """Filtro de eventos: con la flecha abajo en un buscador, el foco salta a su lista
    (y selecciona la primera fila si no había ninguna)."""

    def __init__(self, tabla: QTableWidget, buscador: QLineEdit):
        super().__init__(buscador)
        self._tabla = tabla
        buscador.installEventFilter(self)

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.KeyPress and evento.key() == Qt.Key_Down:
            if self._tabla.rowCount() > 0:
                self._tabla.setFocus()
                if self._tabla.currentRow() < 0:
                    self._tabla.selectRow(0)
                return True
        return False


class _RuedaHorizontal(QObject):
    """Filtro de eventos: la rueda del mouse desplaza una fila de botones hacia los lados
    (así no hace falta mostrar la barra de desplazamiento)."""

    def __init__(self, area: QScrollArea):
        super().__init__(area)
        self._area = area
        area.viewport().installEventFilter(self)

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Wheel:
            barra = self._area.horizontalScrollBar()
            delta = evento.angleDelta().y() or evento.angleDelta().x()
            barra.setValue(barra.value() - delta)
            return True
        return False


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

        self._cupon: dict | None = None  # cupón aplicado (resultado de CuponService.validar)

        self._proforma_origen_id: int | None = None  # si el carrito viene de una proforma

        self.cupon_service = CuponService()

        self.proforma_service = ProformaService()

        self.proforma_guardada = None  # callback opcional (id) para refrescar Proformas

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

        # Cada consulta lleva un número: solo se aplica la respuesta de la más
        # reciente, así una respuesta que llega tarde (y ya no corresponde a lo
        # que el usuario tiene escrito) se descarta.
        # `cargados` = filas ya en la tabla; `hay_mas` = quedan más páginas;
        # `cargando` = hay una consulta en vuelo (evita pedir dos veces la
        # misma página al hacer scroll).

        self._consulta_producto = 0

        self._productos_cargados = 0

        self._hay_mas_productos = False

        self._cargando_productos = False

        self._consulta_cliente = 0

        self._clientes_cargados = 0

        self._hay_mas_clientes = False

        self._cargando_clientes = False
        # Enter en un buscador: si los resultados aún no llegan, se agrega/selecciona
        # el primero apenas lleguen (ver _enter_en_busqueda_producto / _cliente).
        self._agregar_primer_producto_al_llegar = False
        self._seleccionar_primer_cliente_al_llegar = False
        # Filtro de categoría de la lista de productos (None = todas).
        self._categoria_filtro: int | None = None
        self._categorias_firma = None
        self._construir_ui()
        self.actualizar()
        self.actualizar_totales()


    # ---------------------------------------------------------- UI ----

    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        self._raiz = raiz
        raiz.setContentsMargins(MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA)
        raiz.setSpacing(ESPACIO_MD)

        # ---- Encabezado de página: título + acciones a la derecha ----
        self._encabezado = PageHeader("Nueva venta", SUBTITULO_LARGO)
        btn_limpiar = QPushButton("Limpiar carrito")
        btn_limpiar.setProperty("class", "secondary")
        btn_limpiar.clicked.connect(self._limpiar_carrito)
        self._encabezado.agregar_accion(btn_limpiar)
        btn_ventas_recientes = QPushButton("Ventas recientes")
        btn_ventas_recientes.setProperty("class", "secondary")
        btn_ventas_recientes.clicked.connect(self._ver_ventas_recientes)
        self._encabezado.agregar_accion(btn_ventas_recientes)
        raiz.addWidget(self._encabezado)

        # ---- Cuerpo: productos a la izquierda, resumen/carrito a la derecha ----
        # Va dentro de un área con scroll: si la ventana es muy baja, aparece la barra
        # de desplazamiento en lugar de que los bloques se aplasten unos a otros.
        self._contenido = QWidget()
        self._contenido.setObjectName("ventasContenido")
        self._contenido.setMinimumHeight(ALTURA_MINIMA_CUERPO)
        self._cuerpo = QHBoxLayout(self._contenido)
        self._cuerpo.setContentsMargins(0, 0, 0, 0)
        self._cuerpo.setSpacing(ESPACIO_MD)
        self._cuerpo.addWidget(self._construir_panel_izquierdo(), 3)
        self._cuerpo.addWidget(self._construir_panel_derecho(), 7)

        self._scroll_cuerpo = QScrollArea()
        self._scroll_cuerpo.setObjectName("ventasScroll")
        self._scroll_cuerpo.setWidgetResizable(True)
        self._scroll_cuerpo.setFrameShape(QFrame.NoFrame)
        self._scroll_cuerpo.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_cuerpo.setWidget(self._contenido)
        raiz.addWidget(self._scroll_cuerpo, 1)

        self._configurar_atajos_y_foco()
        self._adaptar_a_tamano()

    # ------------------------------------------------- Responsive ----
    def _adaptar_a_tamano(self) -> None:
        """Ajusta márgenes y textos al tamaño disponible (laptops pequeñas)."""
        if not hasattr(self, "_raiz"):
            return
        bajo = self.height() < ALTURA_PANTALLA_BAJA
        margen = ESPACIO_SM + 4 if bajo else MARGEN_PAGINA
        self._raiz.setContentsMargins(margen, margen, margen, margen)
        self._raiz.setSpacing(ESPACIO_SM if bajo else ESPACIO_MD)
        self._cuerpo.setSpacing(ESPACIO_SM if bajo else ESPACIO_MD)
        self._contenido.setMinimumHeight(ALTURA_MINIMA_CUERPO_BAJA if bajo else ALTURA_MINIMA_CUERPO)
        self._contenedor_carrito.setMinimumHeight(ALTURA_MINIMA_CARRITO_BAJA if bajo else ALTURA_MINIMA_CARRITO)
        # Con poco ancho, la columna Categoría de la lista de productos se oculta: el nombre
        # del producto es más importante (las categorías siguen como botones de filtro).
        ancho_panel = (self.width() - 2 * margen - self._cuerpo.spacing()) * 3 / 10
        self.tabla_productos.setColumnHidden(0, ancho_panel < ANCHO_PANEL_PARA_CATEGORIA)
        angosto = self.width() < ANCHO_PANTALLA_ANGOSTA
        subtitulo = "" if self.height() < 600 else (SUBTITULO_CORTO if angosto else SUBTITULO_LARGO)
        self._encabezado.set_subtitulo(subtitulo)

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self._adaptar_a_tamano()
        self._posicionar_resultados_clientes()

    def _construir_panel_izquierdo(self) -> QWidget:
        """Productos: buscador, categorías como botones y la lista."""
        tarjeta_productos = Card("Productos")
        tarjeta_productos.setMinimumWidth(ANCHO_MINIMO_PANEL_PRODUCTOS)
        self.input_busqueda_producto = QLineEdit()
        self.input_busqueda_producto.setPlaceholderText("Buscar producto por nombre...  (F2)")
        self.input_busqueda_producto.setClearButtonEnabled(True)
        self.input_busqueda_producto.textChanged.connect(
            lambda: self._timer_busqueda_producto.start()
        )
        self.input_busqueda_producto.returnPressed.connect(self._enter_en_busqueda_producto)
        tarjeta_productos.cuerpo.addWidget(self.input_busqueda_producto)

        # Categorías: fila de botones que se desplaza hacia el lado si no caben.
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
        tarjeta_productos.cuerpo.addWidget(self.scroll_categorias)
        self._cargar_categorias()

        self.tabla_productos = QTableWidget(0, 4)
        self.tabla_productos.setHorizontalHeaderLabels(["Categoría", "Producto", "Precio", "Stock"])
        header_productos = self.tabla_productos.horizontalHeader()
        # Categoría de ancho fijo (el texto largo se recorta, el nombre completo sale
        # en el tooltip) para que el nombre del producto conserve el espacio.
        header_productos.setSectionResizeMode(0, QHeaderView.Fixed)
        self.tabla_productos.setColumnWidth(0, ANCHO_COLUMNA_CATEGORIA)
        header_productos.setSectionResizeMode(1, QHeaderView.Stretch)
        header_productos.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_productos.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        # Altura de fila fija para toda la tabla (en vez de setRowHeight fila
        # por fila) y carga de la siguiente página al llegar al final.
        configurar_tabla_erp(self.tabla_productos, derecha=(2, 3), altura_fila=ALTURA_FILA_PRODUCTOS)
        self.tabla_productos.verticalScrollBar().valueChanged.connect(self._on_scroll_productos)
        self.tabla_productos.cellDoubleClicked.connect(self._agregar_producto_seleccionado)
        tarjeta_productos.cuerpo.addWidget(self.tabla_productos, 1)

        ayuda_productos = QLabel("Enter agrega el primer resultado   ·   ↓ va a la lista")
        ayuda_productos.setProperty("class", "ayuda")
        ayuda_productos.setWordWrap(True)
        tarjeta_productos.cuerpo.addWidget(ayuda_productos)
        return tarjeta_productos

    def _construir_bloque_cliente(self) -> QWidget:
        """Cliente de la venta, compacto: buscador + cliente elegido en una sola fila.
        Los resultados de la búsqueda se muestran FLOTANDO sobre el carrito (no empujan
        ni aplastan el resto de la pantalla) y solo aparecen mientras se busca."""
        contenedor = QWidget()
        self._bloque_cliente = contenedor
        columna = QVBoxLayout(contenedor)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(ESPACIO_SM)

        fila = QHBoxLayout()
        fila.setSpacing(ESPACIO_SM)
        self.input_busqueda_cliente = QLineEdit()
        self.input_busqueda_cliente.setPlaceholderText("Buscar cliente...  (F4)")
        self.input_busqueda_cliente.setClearButtonEnabled(True)
        self.input_busqueda_cliente.setMinimumWidth(150)
        self.input_busqueda_cliente.textChanged.connect(
            lambda: self._timer_busqueda_cliente.start()
        )
        self.input_busqueda_cliente.textChanged.connect(self._actualizar_visibilidad_clientes)
        self.input_busqueda_cliente.returnPressed.connect(self._enter_en_busqueda_cliente)
        fila.addWidget(self.input_busqueda_cliente, 3)

        self.label_cliente_seleccionado = QLabel(TEXTO_VENTA_GENERAL)
        self.label_cliente_seleccionado.setProperty("class", "chip")
        self.label_cliente_seleccionado.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.label_cliente_seleccionado.setMinimumWidth(120)
        fila.addWidget(self.label_cliente_seleccionado, 4)
        btn_quitar_cliente = QPushButton("Quitar")
        btn_quitar_cliente.setProperty("class", "secondary")
        btn_quitar_cliente.clicked.connect(self._quitar_cliente)
        fila.addWidget(btn_quitar_cliente)
        columna.addLayout(fila)

        # Cliente libre: se escribe a mano, NO se guarda en la lista de clientes;
        # solo queda anotado en la venta para poder diferenciarla.
        fila_libre = QHBoxLayout()
        fila_libre.setSpacing(ESPACIO_SM)
        self.input_cliente_libre = QLineEdit()
        self.input_cliente_libre.setPlaceholderText("O escribe un cliente libre (no se guarda)")
        self.input_cliente_libre.setClearButtonEnabled(True)
        self.input_cliente_libre.textChanged.connect(self._on_cliente_libre_cambia)
        fila_libre.addWidget(self.input_cliente_libre, 1)
        self.combo_tipo_libre = QComboBox()
        self.combo_tipo_libre.addItems(TIPOS_CLIENTE_LIBRE)
        self.combo_tipo_libre.setToolTip("Tipo de cliente (solo para diferenciar la venta)")
        fila_libre.addWidget(self.combo_tipo_libre)
        columna.addLayout(fila_libre)

        # Resultados: tabla flotante, hija de la página (no entra en ningún layout).
        self.tabla_clientes = QTableWidget(0, 2, self)
        self.tabla_clientes.setObjectName("resultadosCliente")
        self.tabla_clientes.setHorizontalHeaderLabels(["Nombre", "Teléfono"])
        header_clientes = self.tabla_clientes.horizontalHeader()
        header_clientes.setSectionResizeMode(0, QHeaderView.Stretch)
        header_clientes.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        configurar_tabla_erp(self.tabla_clientes, altura_fila=ALTURA_FILA_RESULTADOS)
        self.tabla_clientes.verticalScrollBar().valueChanged.connect(self._on_scroll_clientes)
        self.tabla_clientes.cellDoubleClicked.connect(self._seleccionar_cliente)
        self.tabla_clientes.setVisible(False)
        return contenedor

    def _actualizar_visibilidad_clientes(self) -> None:
        self.tabla_clientes.setVisible(bool(self.input_busqueda_cliente.text().strip()))
        self._posicionar_resultados_clientes()

    def _posicionar_resultados_clientes(self) -> None:
        """Coloca la lista de resultados justo debajo del buscador de cliente, por encima
        de todo lo demás, con el ancho del bloque y sin salirse de la página."""
        if not hasattr(self, "tabla_clientes") or not self.tabla_clientes.isVisible():
            return
        entrada = self.input_busqueda_cliente
        origen = self._bloque_cliente.mapTo(self, QPoint(0, 0))
        y = entrada.mapTo(self, QPoint(0, entrada.height() + 4)).y()
        filas = max(self.tabla_clientes.rowCount(), 1)
        alto_deseado = 34 + filas * ALTURA_FILA_RESULTADOS + 4
        alto_libre = max(self.height() - y - 12, 90)
        alto = min(alto_deseado, ALTURA_MAX_RESULTADOS_CLIENTE, alto_libre)
        self.tabla_clientes.setGeometry(origen.x(), y, self._bloque_cliente.width(), alto)
        self.tabla_clientes.raise_()

    def _cargar_categorias(self) -> None:
        """Arma los botones de categoría (solo si la lista de categorías cambió)."""
        try:
            categorias = self.producto_service.categorias_con_productos()
        except Exception:
            logger.exception("No se pudieron cargar las categorías")
            return
        # Sin categorías con productos no hay nada que filtrar: se oculta toda la fila.
        self.scroll_categorias.setVisible(bool(categorias))
        firma = tuple((c["id"], c["nombre"]) for c in categorias)
        if firma == self._categorias_firma:
            return
        self._categorias_firma = firma

        for boton in list(self.grupo_categorias.buttons()):
            self.grupo_categorias.removeButton(boton)
            self.fila_categorias.removeWidget(boton)
            boton.deleteLater()

        if self._categoria_filtro not in {c["id"] for c in categorias}:
            self._categoria_filtro = None

        opciones = [("Todas", None)] + [(c["nombre"], c["id"]) for c in categorias]
        for posicion, (nombre, categoria_id) in enumerate(opciones):
            boton = QPushButton(nombre)
            boton.setObjectName("chipCategoria")
            boton.setCheckable(True)
            boton.setCursor(Qt.PointingHandCursor)
            boton.setChecked(categoria_id == self._categoria_filtro)
            boton.clicked.connect(lambda _=False, c=categoria_id: self._filtrar_por_categoria(c))
            self.grupo_categorias.addButton(boton)
            self.fila_categorias.insertWidget(posicion, boton)

    def _filtrar_por_categoria(self, categoria_id) -> None:
        self._categoria_filtro = categoria_id
        self._buscar_productos()
        self._enfocar_busqueda_producto()

    def _construir_panel_derecho(self) -> QWidget:
        tarjeta = Card("Resumen de venta")
        tarjeta.setMinimumWidth(ANCHO_MINIMO_PANEL_VENTA)
        self.badge_items = StatusBadge("0 productos", "neutral")
        tarjeta.agregar_accion(self.badge_items)
        tarjeta.cuerpo.addWidget(self._construir_bloque_cliente())

        # ---- Carrito (con estado vacío que se reemplaza por la tabla) ----
        # Es lo único que se estira; tiene una altura mínima propia para que siempre
        # se vea la lista de productos aunque la pantalla sea pequeña.
        self.tabla_carrito = QTableWidget(0, 7)
        self.tabla_carrito.setHorizontalHeaderLabels(
            ["#", "Producto", "Presentación", "Cantidad", "Precio", "Subtotal", ""]
        )
        header = self.tabla_carrito.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        # Anchos fijos para los controles: así la columna "Producto" (la que
        # se estira) siempre conserva espacio para el nombre.
        for columna, ancho in ((2, ANCHO_COLUMNA_PRESENTACION), (3, ANCHO_COLUMNA_CANTIDAD),
                               (4, ANCHO_COLUMNA_MONTO), (5, ANCHO_COLUMNA_MONTO + 8)):
            header.setSectionResizeMode(columna, QHeaderView.Fixed)
            self.tabla_carrito.setColumnWidth(columna, ancho)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.tabla_carrito.setColumnWidth(0, ANCHO_COLUMNA_NUMERO)
        self.tabla_carrito.setColumnWidth(6, ANCHO_COLUMNA_QUITAR)
        configurar_tabla_erp(self.tabla_carrito, derecha=(4, 5), centro=(0,), altura_fila=ALTURA_FILA_CARRITO)
        self.tabla_carrito.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        contenedor_carrito = QWidget()
        self._contenedor_carrito = contenedor_carrito
        contenedor_carrito.setMinimumHeight(ALTURA_MINIMA_CARRITO)
        self._pila_carrito = QStackedLayout(contenedor_carrito)
        self._pila_carrito.setContentsMargins(0, 0, 0, 0)
        self._pila_carrito.addWidget(self._crear_estado_vacio_carrito())
        self._pila_carrito.addWidget(self.tabla_carrito)
        tarjeta.cuerpo.addWidget(contenedor_carrito, 1)

        tarjeta.cuerpo.addWidget(self._construir_pie_cobro())
        return tarjeta

    def _construir_pie_cobro(self) -> QWidget:
        """Zona de cobro compacta (siempre visible bajo el carrito):
        descuento / método de pago / chofer, cupón, y total junto a los botones."""
        pie = QWidget()
        pie.setObjectName("pieCobro")
        columna = QVBoxLayout(pie)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(ESPACIO_SM)

        self.input_descuento = QDoubleSpinBox()
        self.input_descuento.setMaximum(999999)
        self.input_descuento.setPrefix("Desc. S/ ")
        self.input_descuento.setToolTip("Descuento en soles")
        self.input_descuento.valueChanged.connect(self.actualizar_totales)
        self.combo_metodo_pago = QComboBox()
        self.combo_metodo_pago.setToolTip("Método de pago")
        self.input_chofer = QLineEdit()
        self.input_chofer.setPlaceholderText("Chofer")
        self.input_chofer.setToolTip("Chofer (opcional)")

        fila_datos = QHBoxLayout()
        fila_datos.setSpacing(ESPACIO_SM)
        fila_datos.addWidget(self.input_descuento, 4)
        fila_datos.addWidget(self.combo_metodo_pago, 4)
        fila_datos.addWidget(self.input_chofer, 3)
        columna.addLayout(fila_datos)

        # ---- Cupón ----
        fila_cupon = QHBoxLayout()
        fila_cupon.setSpacing(ESPACIO_SM)
        self.input_cupon = QLineEdit()
        self.input_cupon.setPlaceholderText("Cupón de descuento (ej. CUP-AB12CD)")
        self.input_cupon.returnPressed.connect(self._aplicar_cupon)
        fila_cupon.addWidget(self.input_cupon, 1)
        self.btn_cupon = QPushButton("Aplicar")
        self.btn_cupon.setProperty("class", "secondary")
        self.btn_cupon.clicked.connect(self._aplicar_cupon)
        fila_cupon.addWidget(self.btn_cupon)
        self.btn_quitar_cupon = QPushButton("Quitar")
        self.btn_quitar_cupon.setProperty("class", "secondary")
        self.btn_quitar_cupon.clicked.connect(self._quitar_cupon)
        self.btn_quitar_cupon.setVisible(False)
        fila_cupon.addWidget(self.btn_quitar_cupon)
        columna.addLayout(fila_cupon)
        self.label_cupon = QLabel("")
        self.label_cupon.setProperty("class", "ayuda")
        self.label_cupon.setVisible(False)
        columna.addWidget(self.label_cupon)

        # ---- Total (izquierda) + botones de cobro (derecha), en la misma fila ----
        fila_cobro = QHBoxLayout()
        fila_cobro.setSpacing(ESPACIO_SM + 4)

        caja_total = QFrame()
        caja_total.setObjectName("totalBox")
        v_total = QVBoxLayout(caja_total)
        v_total.setContentsMargins(ESPACIO_MD, 8, ESPACIO_MD, 8)
        v_total.setSpacing(2)

        def fila_resumen(texto: str):
            """Fila pequeña 'texto ........ valor'. Devuelve (widget de la fila, etiqueta del valor)."""
            contenedor = QWidget()
            fila = QHBoxLayout(contenedor)
            fila.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(texto)
            lbl.setProperty("class", "ayuda")
            valor = QLabel("S/ 0.00")
            valor.setAlignment(ALINEAR_DERECHA)
            fila.addWidget(lbl)
            fila.addStretch()
            fila.addWidget(valor)
            v_total.addWidget(contenedor)
            return contenedor, valor

        _, self.label_subtotal = fila_resumen("Subtotal")
        # Descuento y cupón solo ocupan espacio cuando hay algo que mostrar.
        self._fila_descuento, self.label_descuento_valor = fila_resumen("Descuento")
        self._fila_cupon_valor, self.label_cupon_valor = fila_resumen("Cupón")
        self._fila_descuento.setVisible(False)
        self._fila_cupon_valor.setVisible(False)
        titulo_total = QLabel("Total a pagar")
        titulo_total.setObjectName("cardHeading")
        v_total.addWidget(titulo_total)
        self.label_total = QLabel("S/ 0.00")
        self.label_total.setProperty("class", "total")
        self.label_total.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        v_total.addWidget(self.label_total)
        fila_cobro.addWidget(caja_total, 5)

        botones = QVBoxLayout()
        botones.setSpacing(ESPACIO_SM - 2)
        self.btn_registrar = QPushButton("Registrar venta   ·   F9")
        self.btn_registrar.setProperty("class", "success large")
        self.btn_registrar.clicked.connect(self._registrar_venta)
        self.btn_registrar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        botones.addWidget(self.btn_registrar, 2)
        self.btn_proforma = QPushButton("Guardar como proforma")
        self.btn_proforma.setProperty("class", "secondary")
        self.btn_proforma.clicked.connect(self._guardar_proforma)
        botones.addWidget(self.btn_proforma)
        fila_cobro.addLayout(botones, 5)
        columna.addLayout(fila_cobro)
        return pie

    def _crear_estado_vacio_carrito(self) -> QWidget:
        """Mensaje que se muestra mientras el carrito no tiene productos."""
        pagina = QWidget()
        v = QVBoxLayout(pagina)
        v.setAlignment(Qt.AlignCenter)
        v.setSpacing(ESPACIO_SM)
        icono_vacio = QLabel()
        icono_vacio.setPixmap(pixmap_icono("carrito", "#94a3b8", 44, 1.5))
        icono_vacio.setAlignment(Qt.AlignCenter)
        v.addWidget(icono_vacio)
        titulo = QLabel("El carrito está vacío")
        titulo.setObjectName("cardHeading")
        titulo.setAlignment(Qt.AlignCenter)
        v.addWidget(titulo)
        ayuda = QLabel("Busca un producto (F2) y presiona Enter, o haz doble clic en la lista.")
        ayuda.setProperty("class", "ayuda")
        ayuda.setAlignment(Qt.AlignCenter)
        ayuda.setWordWrap(True)
        v.addWidget(ayuda)
        return pagina

    # ------------------------------------------- Atajos, foco y teclado ----
    def _configurar_atajos_y_foco(self) -> None:
        """Atajos de teclado y orden de tabulación para vender sin usar el mouse.

        Los atajos solo funcionan mientras esta pantalla está visible (Qt no
        activa los atajos de widgets ocultos), así que no chocan con otras páginas.
        """
        def atajo(secuencia: str, accion, widget=None, contexto=Qt.WindowShortcut) -> None:
            s = QShortcut(QKeySequence(secuencia), widget or self)
            s.setContext(contexto)
            s.activated.connect(accion)

        atajo("F2", self._enfocar_busqueda_producto)
        atajo("F4", self._enfocar_busqueda_cliente)
        atajo("F9", self._registrar_venta)
        atajo("Ctrl+N", self._nueva_venta)
        # Esc solo actúa si el foco está dentro de esta pantalla (así no interfiere
        # con listas desplegables abiertas).
        atajo("Esc", self._limpiar_busquedas, contexto=Qt.WidgetWithChildrenShortcut)
        for tecla in ("Return", "Enter"):
            atajo(tecla, self._agregar_producto_actual, self.tabla_productos, Qt.WidgetShortcut)
            atajo(tecla, self._seleccionar_cliente_actual, self.tabla_clientes, Qt.WidgetShortcut)

        # Flecha abajo en un buscador = saltar a su lista.
        self._filtro_producto = _FlechaAbajoALista(self.tabla_productos, self.input_busqueda_producto)
        self._filtro_cliente = _FlechaAbajoALista(self.tabla_clientes, self.input_busqueda_cliente)

        orden = [
            self.input_busqueda_producto, self.tabla_productos,
            self.input_busqueda_cliente, self.tabla_clientes,
            self.input_descuento, self.combo_metodo_pago, self.input_chofer,
            self.btn_registrar,
        ]
        for anterior, siguiente in zip(orden, orden[1:]):
            QWidget.setTabOrder(anterior, siguiente)

    def showEvent(self, evento) -> None:
        """Al abrir la pantalla, el cursor queda listo en el buscador de productos."""
        super().showEvent(evento)
        QTimer.singleShot(0, self._enfocar_busqueda_producto)

    def _enfocar_busqueda_producto(self) -> None:
        self.input_busqueda_producto.setFocus()
        self.input_busqueda_producto.selectAll()

    def _enfocar_busqueda_cliente(self) -> None:
        self.input_busqueda_cliente.setFocus()
        self.input_busqueda_cliente.selectAll()

    def _limpiar_busquedas(self) -> None:
        self.input_busqueda_producto.clear()
        self.input_busqueda_cliente.clear()
        self._enfocar_busqueda_producto()

    def _nueva_venta(self) -> None:
        """Ctrl+N: empieza una venta nueva (pide confirmación si hay productos en el carrito)."""
        if self.carrito:
            respuesta = QMessageBox.question(
                self, "Nueva venta", "¿Descartar la venta en curso y empezar una nueva?"
            )
            if respuesta != QMessageBox.Yes:
                return
        self._reiniciar_formulario_venta()
        self._enfocar_busqueda_producto()

    def _agregar_producto_actual(self) -> None:
        fila = self.tabla_productos.currentRow()
        if fila >= 0:
            self._agregar_producto_seleccionado(fila, 0)

    def _seleccionar_cliente_actual(self) -> None:
        fila = self.tabla_clientes.currentRow()
        if fila >= 0:
            self._seleccionar_cliente(fila, 0)
            self._enfocar_busqueda_producto()

    def _enter_en_busqueda_producto(self) -> None:
        """Enter en el buscador: agrega el primer resultado al carrito. Si todavía
        hay una búsqueda pendiente, espera a que lleguen los resultados correctos."""
        if not self.input_busqueda_producto.text().strip():
            return
        if self._timer_busqueda_producto.isActive():
            self._timer_busqueda_producto.stop()
            self._agregar_primer_producto_al_llegar = True
            self._buscar_productos()
        elif self._cargando_productos:
            self._agregar_primer_producto_al_llegar = True
        else:
            self._agregar_primer_producto()

    def _agregar_primer_producto(self) -> None:
        """Agrega la primera fila de la lista y deja el buscador limpio y listo para el siguiente."""
        if self.tabla_productos.rowCount() == 0:
            return
        self._agregar_producto_seleccionado(0, 0)
        self.input_busqueda_producto.clear()
        self._enfocar_busqueda_producto()

    def _enter_en_busqueda_cliente(self) -> None:
        if not self.input_busqueda_cliente.text().strip():
            return
        if self._timer_busqueda_cliente.isActive():
            self._timer_busqueda_cliente.stop()
            self._seleccionar_primer_cliente_al_llegar = True
            self._buscar_clientes()
        elif self._cargando_clientes:
            self._seleccionar_primer_cliente_al_llegar = True
        else:
            self._seleccionar_primer_cliente()

    def _seleccionar_primer_cliente(self) -> None:
        if self.tabla_clientes.rowCount() == 0:
            return
        self._seleccionar_cliente(0, 0)
        self._enfocar_busqueda_producto()

    def actualizar(self) -> None:

        self._cargar_categorias()
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
        """Nueva búsqueda: reinicia la lista desde la primera página."""
        self._consulta_producto += 1

        self._productos_cargados = 0

        self._hay_mas_productos = False

        self._cargar_productos(self._consulta_producto, offset=0)

    def _on_scroll_productos(self) -> None:
        """Al llegar al final de la lista pide la siguiente página."""
        if (
            self._hay_mas_productos
            and not self._cargando_productos
            and cerca_del_final(self.tabla_productos)
        ):
            self._cargar_productos(self._consulta_producto, offset=self._productos_cargados)

    def _cargar_productos(self, numero: int, offset: int) -> None:
        texto = self.input_busqueda_producto.text()
        logger.debug("Buscando productos: %r (offset=%d)", texto, offset)

        self._cargando_productos = True

        # Se pide uno de más solo para saber si queda otra página, sin un
        # COUNT aparte; ese de más nunca se muestra.
        worker = Worker(
            self.producto_service.listar, texto, TAMANO_PAGINA_RESULTADOS + 1, offset,
            self._categoria_filtro,
        )

        worker.signals.finished.connect(
            lambda productos, n=numero, o=offset: self._on_productos_listos(n, o, productos)
        )

        worker.signals.error.connect(
            lambda mensaje, n=numero: self._on_error_busqueda(mensaje, n, "producto")
        )

        QThreadPool.globalInstance().start(worker)

    def _on_productos_listos(self, numero: int, offset: int, productos) -> None:
        if numero != self._consulta_producto:
            logger.debug("Descartando resultados de productos atrasados (consulta %d)", numero)
            return

        self._cargando_productos = False

        self._hay_mas_productos = len(productos) > TAMANO_PAGINA_RESULTADOS

        nuevos = productos[:TAMANO_PAGINA_RESULTADOS]

        config = self.config_service.obtener()
        moneda = config.get("moneda", "S/")
        tema = config.get("tema", "claro")
        # Nueva búsqueda (offset 0) reemplaza la lista; "página siguiente" solo
        # agrega filas al final, sin tocar las que ya estaban.
        with carga_rapida(self.tabla_productos):
            if offset == 0:
                self.tabla_productos.setRowCount(0)

            fila_inicial = self.tabla_productos.rowCount()

            self.tabla_productos.setRowCount(fila_inicial + len(nuevos))

            for i, p in enumerate(nuevos):
                fila = fila_inicial + i

                item_categoria = QTableWidgetItem(p.categoria_nombre or "Sin categoría")
                item_categoria.setData(Qt.UserRole, p.id)
                item_categoria.setToolTip(p.categoria_nombre or "Sin categoría")

                self.tabla_productos.setItem(fila, 0, item_categoria)
                item_nombre = QTableWidgetItem(p.nombre)
                item_nombre.setToolTip(p.nombre)
                self.tabla_productos.setItem(fila, 1, item_nombre)
                self.tabla_productos.setItem(
                    fila, 2, item_derecha(formatear_moneda(p.precio_venta_actual, moneda))
                )
                item_stock = item_derecha(f"{p.stock_actual:g}")
                colorear_stock(item_stock, p.agotado, p.stock_bajo, tema)
                self.tabla_productos.setItem(fila, 3, item_stock)

        self._productos_cargados = self.tabla_productos.rowCount()
        if self._agregar_primer_producto_al_llegar:
            self._agregar_primer_producto_al_llegar = False
            self._agregar_primer_producto()

    def _on_error_busqueda(self, mensaje: str, numero: int = 0, lista: str = "") -> None:

        logger.error("Error en búsqueda en segundo plano: %s", mensaje)

        # Libera la bandera de la lista que falló; si no, el scroll nunca
        # volvería a pedir la página siguiente.
        if lista == "producto":
            self._agregar_primer_producto_al_llegar = False
        elif lista == "cliente":
            self._seleccionar_primer_cliente_al_llegar = False
        if lista == "producto" and numero == self._consulta_producto:

            self._cargando_productos = False

        elif lista == "cliente" and numero == self._consulta_cliente:

            self._cargando_clientes = False

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
        """Nueva búsqueda: reinicia la lista desde la primera página."""
        self._consulta_cliente += 1

        self._clientes_cargados = 0

        self._hay_mas_clientes = False

        self._cargar_clientes(self._consulta_cliente, offset=0)

    def _on_scroll_clientes(self) -> None:
        """Al llegar al final de la lista pide la siguiente página."""
        if (
            self._hay_mas_clientes
            and not self._cargando_clientes
            and cerca_del_final(self.tabla_clientes)
        ):
            self._cargar_clientes(self._consulta_cliente, offset=self._clientes_cargados)

    def _cargar_clientes(self, numero: int, offset: int) -> None:
        texto = self.input_busqueda_cliente.text()
        logger.debug("Buscando clientes: %r (offset=%d)", texto, offset)

        self._cargando_clientes = True

        worker = Worker(
            self.cliente_service.listar, texto, TAMANO_PAGINA_RESULTADOS + 1, offset
        )

        worker.signals.finished.connect(
            lambda clientes, n=numero, o=offset: self._on_clientes_listos(n, o, clientes)
        )

        worker.signals.error.connect(
            lambda mensaje, n=numero: self._on_error_busqueda(mensaje, n, "cliente")
        )

        QThreadPool.globalInstance().start(worker)

    def _on_clientes_listos(self, numero: int, offset: int, clientes) -> None:
        if numero != self._consulta_cliente:
            logger.debug("Descartando resultados de clientes atrasados (consulta %d)", numero)
            return

        self._cargando_clientes = False

        self._hay_mas_clientes = len(clientes) > TAMANO_PAGINA_RESULTADOS

        nuevos = clientes[:TAMANO_PAGINA_RESULTADOS]

        with carga_rapida(self.tabla_clientes):
            if offset == 0:
                self.tabla_clientes.setRowCount(0)

            fila_inicial = self.tabla_clientes.rowCount()

            self.tabla_clientes.setRowCount(fila_inicial + len(nuevos))

            for i, c in enumerate(nuevos):
                fila = fila_inicial + i

                item_nombre = QTableWidgetItem(c.nombre)
                item_nombre.setData(Qt.UserRole, (c.id, c.nombre))

                self.tabla_clientes.setItem(fila, 0, item_nombre)
                self.tabla_clientes.setItem(fila, 1, QTableWidgetItem(c.telefono or "-"))

        self._clientes_cargados = self.tabla_clientes.rowCount()
        self._posicionar_resultados_clientes()  # ajusta la altura a la cantidad de resultados
        if self._seleccionar_primer_cliente_al_llegar:
            self._seleccionar_primer_cliente_al_llegar = False
            self._seleccionar_primer_cliente()

    def _seleccionar_cliente(self, fila: int, columna: int) -> None:

        item = self.tabla_clientes.item(fila, 0)

        if item is None:

            return

        cliente_id, cliente_nombre = item.data(Qt.UserRole)

        self.cliente_seleccionado_id = cliente_id

        self.cliente_seleccionado_nombre = cliente_nombre

        self.label_cliente_seleccionado.setText(f"Cliente: {cliente_nombre}")
        self.input_cliente_libre.clear()
        # Se limpia el buscador: así la lista de resultados se oculta y queda solo el cliente elegido.
        self.input_busqueda_cliente.clear()

    def _quitar_cliente(self) -> None:

        self.cliente_seleccionado_id = None

        self.cliente_seleccionado_nombre = None

        self.label_cliente_seleccionado.setText(TEXTO_VENTA_GENERAL)

    # ------------------------------------------------------ Carrito ----

    def _refrescar_tabla_carrito(self) -> None:

        moneda = self.config_service.obtener().get("moneda", "S/")

        self.tabla_carrito.setRowCount(len(self.carrito))

        for fila, linea in enumerate(self.carrito):

            self.tabla_carrito.setItem(fila, 0, item_centro(str(fila + 1)))
            item_nombre = QTableWidgetItem(linea.nombre_producto)
            item_nombre.setToolTip(linea.nombre_producto)
            self.tabla_carrito.setItem(fila, 1, item_nombre)

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
                fila, 4, item_derecha(formatear_moneda(linea.precio_presentacion_unitario, moneda))
            )
            self.tabla_carrito.setItem(fila, 5, item_derecha(formatear_moneda(linea.subtotal, moneda)))
            btn_quitar = QPushButton()
            btn_quitar.setProperty("class", "danger")
            btn_quitar.setIcon(icono("papelera", "#ffffff", 16))
            btn_quitar.setToolTip("Quitar del carrito")
            btn_quitar.setMinimumSize(36, 30)

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
        descuento_cupon = self._descuento_cupon(subtotal)
        total = max(subtotal - descuento - descuento_cupon, 0)
        self.label_subtotal.setText(formatear_moneda(subtotal, moneda))
        self.label_descuento_valor.setText(f"- {formatear_moneda(descuento, moneda)}")
        self.label_cupon_valor.setText(f"- {formatear_moneda(descuento_cupon, moneda)}")
        self.label_total.setText(formatear_moneda(total, moneda))
        self._fila_descuento.setVisible(descuento > 0)
        self._fila_cupon_valor.setVisible(descuento_cupon > 0)

        # Estado de la pantalla según el carrito: mensaje vacío / tabla, contador y botón de cobro.
        cantidad = len(self.carrito)
        self._pila_carrito.setCurrentIndex(1 if cantidad else 0)
        self.badge_items.setText(f"{cantidad} producto" if cantidad == 1 else f"{cantidad} productos")
        self.badge_items.setProperty("class", "badgeInfo" if cantidad else "badgeNeutral")
        self.badge_items.style().unpolish(self.badge_items)
        self.badge_items.style().polish(self.badge_items)
        self.btn_registrar.setEnabled(cantidad > 0)
        self.btn_proforma.setEnabled(cantidad > 0)

    # ------------------------------------------------------ Cupón ----

    def _descuento_cupon(self, subtotal: float) -> float:
        """Descuento del cupón aplicado para el subtotal actual (0 si no hay o ya no aplica)."""
        if not self._cupon:
            return 0.0
        try:
            return self.cupon_service.validar(self._cupon["codigo"], subtotal)["descuento"]
        except CuponError as e:
            # Por ejemplo, se quitaron productos y ya no llega a la compra mínima.
            self._mostrar_estado_cupon(f"Cupón {self._cupon['codigo']} no aplica: {e}", error=True)
            return 0.0

    def _mostrar_estado_cupon(self, texto: str, error: bool = False) -> None:
        self.label_cupon.setText(texto)
        self.label_cupon.setVisible(bool(texto))
        self.label_cupon.setProperty("estado", "error" if error else "ok")
        self.label_cupon.setStyleSheet("color: #dc2626;" if error else "color: #059669;")

    def _aplicar_cupon(self) -> None:
        subtotal = sum(l.subtotal for l in self.carrito)
        if subtotal <= 0:
            self._mostrar_estado_cupon("Agrega productos antes de aplicar un cupón.", error=True)
            return
        try:
            resultado = self.cupon_service.validar(self.input_cupon.text(), subtotal)
        except CuponError as e:
            self._cupon = None
            self._mostrar_estado_cupon(str(e), error=True)
            self.actualizar_totales()
            return
        self._cupon = resultado
        self.input_cupon.setText(resultado["codigo"])
        self.input_cupon.setEnabled(False)
        self.btn_cupon.setEnabled(False)
        self.btn_quitar_cupon.setVisible(True)
        self._mostrar_estado_cupon(f"Cupón {resultado['codigo']} aplicado.")
        self.actualizar_totales()

    def _quitar_cupon(self) -> None:
        self._cupon = None
        self.input_cupon.clear()
        self.input_cupon.setEnabled(True)
        self.btn_cupon.setEnabled(True)
        self.btn_quitar_cupon.setVisible(False)
        self._mostrar_estado_cupon("")
        self.actualizar_totales()

    # --------------------------------------------------- Cliente libre ----

    def _on_cliente_libre_cambia(self, texto: str) -> None:
        # Un cliente guardado y uno libre no conviven: escribir uno quita el otro.
        if texto.strip() and self.cliente_seleccionado_id is not None:
            self._quitar_cliente()

    def _cliente_libre(self) -> tuple[str | None, str | None]:
        nombre = self.input_cliente_libre.text().strip()
        if not nombre:
            return None, None
        return nombre, self.combo_tipo_libre.currentText()

    # ------------------------------------------------------- Proformas ----

    def _guardar_proforma(self) -> None:
        if not self.carrito:
            return
        nombre_libre, tipo_libre = self._cliente_libre()
        subtotal = sum(l.subtotal for l in self.carrito)
        descuento = round(self.input_descuento.value() + self._descuento_cupon(subtotal), 2)
        try:
            proforma_id = self.proforma_service.crear(
                self.carrito, self.usuario.id, descuento=min(descuento, subtotal),
                cliente_id=self.cliente_seleccionado_id,
                cliente_nombre=nombre_libre or "", cliente_tipo=tipo_libre or "",
            )
        except ProformaError as e:
            QMessageBox.warning(self, "No se pudo guardar la proforma", str(e))
            return
        if self.proforma_guardada:
            self.proforma_guardada(proforma_id)
        QMessageBox.information(
            self, "Proforma guardada",
            f"Proforma #{proforma_id} guardada. No se descontó stock ni se movió la caja.\n"
            "Puedes verla, imprimirla o convertirla en venta desde el menú Proformas."
        )
        self._reiniciar_formulario_venta()

    def cargar_proforma(self, proforma: dict) -> None:
        """Carga una proforma en el carrito para cobrarla como venta."""
        self._reiniciar_formulario_venta()
        self.carrito.clear()
        for l in proforma["lineas"]:
            self.carrito.append(VentaDetalleItem(
                producto_id=l["producto_id"], nombre_producto=l["nombre_producto"],
                cantidad=l["cantidad"], precio_venta_unitario=l["precio_unitario"],
                costo_unitario_snapshot=0.0,
                presentacion_nombre=l.get("presentacion_nombre") or "Unidad",
                cantidad_presentacion=l.get("cantidad_presentacion"),
                factor_unidades=l.get("factor_unidades") or 1.0,
            ))
        self._refrescar_tabla_carrito()
        if proforma.get("cliente_id"):
            cliente = self.cliente_service.obtener_por_id(proforma["cliente_id"])
            if cliente:
                self.cliente_seleccionado_id = cliente.id
                self.cliente_seleccionado_nombre = cliente.nombre
                self.label_cliente_seleccionado.setText(f"Cliente: {cliente.nombre}")
        elif proforma.get("cliente_nombre"):
            self.input_cliente_libre.setText(proforma["cliente_nombre"])
            tipo = proforma.get("cliente_tipo")
            if tipo:
                indice = self.combo_tipo_libre.findText(tipo)
                self.combo_tipo_libre.setCurrentIndex(indice if indice >= 0 else self.combo_tipo_libre.count() - 1)
        if proforma.get("descuento"):
            self.input_descuento.setValue(proforma["descuento"])
        self._proforma_origen_id = proforma["id"]
        self.badge_items.setToolTip(f"Desde la proforma #{proforma['id']}")
        self.actualizar_totales()

    # ------------------------------------------------- Registrar venta ----

    def _registrar_venta(self) -> None:

        if not self.carrito:

            QMessageBox.warning(self, "Carrito vacío", "Agrega al menos un producto para registrar la venta.")

            return

        moneda = self.config_service.obtener().get("moneda", "S/")

        subtotal = sum(l.subtotal for l in self.carrito)

        descuento = self.input_descuento.value() + self._descuento_cupon(subtotal)

        total = max(subtotal - descuento, 0)

        nombre_libre, tipo_libre = self._cliente_libre()

        cliente_texto = self.cliente_seleccionado_nombre or (
            f"{nombre_libre} ({tipo_libre})" if nombre_libre else "Sin cliente (venta general)")

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
                cliente_libre_nombre=nombre_libre,
                cliente_libre_tipo=tipo_libre,
                cupon_codigo=self._cupon["codigo"] if self._cupon else None,

            )

        except VentaError as e:

            QMessageBox.warning(self, "No se pudo registrar la venta", str(e))

            return

        if self._proforma_origen_id:
            self.proforma_service.marcar_convertida(self._proforma_origen_id, venta_id)
            if self.proforma_guardada:
                self.proforma_guardada(self._proforma_origen_id)

        self._mostrar_vista_previa_ticket(venta_id)

        self._reiniciar_formulario_venta()

    def _reiniciar_formulario_venta(self) -> None:

        """Limpia carrito/cliente/descuento y vuelve a poblar las tablas de

        productos y clientes. .clear() en un QLineEdit vacío no dispara

        textChanged, así que hay que forzar la búsqueda para que la lista

        de productos nunca quede vacía tras registrar una venta."""

        self.carrito.clear()

        self.input_descuento.setValue(0)

        self._quitar_cupon()

        self.input_cliente_libre.clear()

        self.combo_tipo_libre.setCurrentIndex(0)

        self._proforma_origen_id = None

        self.badge_items.setToolTip("")

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