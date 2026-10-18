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
    QFrame, QGridLayout, QStackedLayout,

    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,

    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QDoubleSpinBox,

    QMessageBox, QSplitter, QDialog

)

from PySide6.QtCore import Qt, QTimer, QThreadPool, QObject, QEvent
from PySide6.QtGui import QKeySequence, QShortcut

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

ALTURA_FILA_RESULTADOS = 34

# Las listas de productos y clientes se piden por páginas: se muestran las
# primeras TAMANO_PAGINA_RESULTADOS y las siguientes se cargan solas al hacer
# scroll hasta el final. Así abrir Ventas cuesta lo mismo con 500 que con
# 50 000 productos.
TAMANO_PAGINA_RESULTADOS = 100

ANCHO_COLUMNA_NUMERO = 28

ANCHO_COLUMNA_QUITAR = 48
ANCHO_COLUMNA_PRESENTACION = 124
ANCHO_COLUMNA_CANTIDAD = 86
ANCHO_COLUMNA_MONTO = 96
ANCHO_COLUMNA_CATEGORIA = 92

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
        self._construir_ui()
        self.actualizar()
        self.actualizar_totales()


    # ---------------------------------------------------------- UI ----

    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA)
        raiz.setSpacing(ESPACIO_MD)

        # ---- Encabezado de página: título + acciones a la derecha ----
        encabezado = PageHeader(
            "Nueva venta",
            "F2 Producto   ·   F4 Cliente   ·   F9 Cobrar   ·   Esc Limpiar búsqueda   ·   Ctrl+N Nueva venta",
        )
        btn_limpiar = QPushButton("Limpiar carrito")
        btn_limpiar.setProperty("class", "secondary")
        btn_limpiar.clicked.connect(self._limpiar_carrito)
        encabezado.agregar_accion(btn_limpiar)
        btn_ventas_recientes = QPushButton("Ventas recientes")
        btn_ventas_recientes.setProperty("class", "secondary")
        btn_ventas_recientes.clicked.connect(self._ver_ventas_recientes)
        encabezado.agregar_accion(btn_ventas_recientes)
        raiz.addWidget(encabezado)

        # ---- Cuadrícula: izquierda (cliente y productos) 40 % / derecha (venta) 60 % ----
        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(ESPACIO_MD)
        cuerpo.addLayout(self._construir_panel_izquierdo(), 4)
        cuerpo.addWidget(self._construir_panel_derecho(), 6)
        raiz.addLayout(cuerpo, 1)

        self._configurar_atajos_y_foco()

    def _construir_panel_izquierdo(self) -> QVBoxLayout:
        columna = QVBoxLayout()
        columna.setSpacing(ESPACIO_MD)

        # ---- Tarjeta Cliente ----
        tarjeta_cliente = Card("Cliente")
        self.input_busqueda_cliente = QLineEdit()
        self.input_busqueda_cliente.setPlaceholderText("Buscar cliente por nombre...  (F4)")
        self.input_busqueda_cliente.setClearButtonEnabled(True)
        self.input_busqueda_cliente.textChanged.connect(
            lambda: self._timer_busqueda_cliente.start()
        )
        self.input_busqueda_cliente.returnPressed.connect(self._enter_en_busqueda_cliente)
        tarjeta_cliente.cuerpo.addWidget(self.input_busqueda_cliente)

        self.tabla_clientes = QTableWidget(0, 2)
        self.tabla_clientes.setHorizontalHeaderLabels(["Nombre", "Teléfono"])
        header_clientes = self.tabla_clientes.horizontalHeader()
        header_clientes.setSectionResizeMode(0, QHeaderView.Stretch)
        header_clientes.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        configurar_tabla_erp(self.tabla_clientes, altura_fila=ALTURA_FILA_RESULTADOS)
        self.tabla_clientes.setMinimumHeight(78)
        self.tabla_clientes.verticalScrollBar().valueChanged.connect(self._on_scroll_clientes)
        self.tabla_clientes.cellDoubleClicked.connect(self._seleccionar_cliente)
        tarjeta_cliente.cuerpo.addWidget(self.tabla_clientes, 1)

        fila_cliente = QHBoxLayout()
        fila_cliente.setSpacing(ESPACIO_SM)
        self.label_cliente_seleccionado = QLabel("Sin cliente seleccionado (venta general)")
        self.label_cliente_seleccionado.setProperty("class", "chip")
        self.label_cliente_seleccionado.setWordWrap(True)
        fila_cliente.addWidget(self.label_cliente_seleccionado, 1)
        btn_quitar_cliente = QPushButton("Quitar")
        btn_quitar_cliente.setProperty("class", "secondary")
        btn_quitar_cliente.clicked.connect(self._quitar_cliente)
        fila_cliente.addWidget(btn_quitar_cliente)
        tarjeta_cliente.cuerpo.addLayout(fila_cliente)
        columna.addWidget(tarjeta_cliente, 1)

        # ---- Tarjeta Productos ----
        tarjeta_productos = Card("Productos")
        self.input_busqueda_producto = QLineEdit()
        self.input_busqueda_producto.setPlaceholderText("Buscar producto por nombre...  (F2)")
        self.input_busqueda_producto.setClearButtonEnabled(True)
        self.input_busqueda_producto.textChanged.connect(
            lambda: self._timer_busqueda_producto.start()
        )
        self.input_busqueda_producto.returnPressed.connect(self._enter_en_busqueda_producto)
        tarjeta_productos.cuerpo.addWidget(self.input_busqueda_producto)

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
        configurar_tabla_erp(self.tabla_productos, derecha=(2, 3), altura_fila=ALTURA_FILA_RESULTADOS)
        self.tabla_productos.verticalScrollBar().valueChanged.connect(self._on_scroll_productos)
        self.tabla_productos.cellDoubleClicked.connect(self._agregar_producto_seleccionado)
        tarjeta_productos.cuerpo.addWidget(self.tabla_productos, 1)

        ayuda_productos = QLabel("Enter agrega el primer resultado   ·   ↓ va a la lista")
        ayuda_productos.setProperty("class", "ayuda")
        ayuda_productos.setWordWrap(True)
        tarjeta_productos.cuerpo.addWidget(ayuda_productos)
        columna.addWidget(tarjeta_productos, 2)
        return columna

    def _construir_panel_derecho(self) -> QWidget:
        tarjeta = Card("Resumen de venta")
        self.badge_items = StatusBadge("0 productos", "neutral")
        tarjeta.agregar_accion(self.badge_items)

        # ---- Carrito (con estado vacío que se reemplaza por la tabla) ----
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

        contenedor_carrito = QWidget()
        self._pila_carrito = QStackedLayout(contenedor_carrito)
        self._pila_carrito.setContentsMargins(0, 0, 0, 0)
        self._pila_carrito.addWidget(self._crear_estado_vacio_carrito())
        self._pila_carrito.addWidget(self.tabla_carrito)
        tarjeta.cuerpo.addWidget(contenedor_carrito, 1)

        # ---- Descuento, método de pago y chofer en una cuadrícula ----
        def etiqueta(texto: str, margen_superior: int = 0) -> QLabel:
            lbl = QLabel(texto)
            lbl.setProperty("class", "ayuda")
            lbl.setContentsMargins(0, margen_superior, 0, 0)
            return lbl

        self.input_descuento = QDoubleSpinBox()
        self.input_descuento.setMaximum(999999)
        self.input_descuento.setPrefix("S/ ")
        self.input_descuento.valueChanged.connect(self.actualizar_totales)
        self.combo_metodo_pago = QComboBox()
        self.input_chofer = QLineEdit()
        self.input_chofer.setPlaceholderText("Chofer de esta venta")

        formulario = QGridLayout()
        formulario.setHorizontalSpacing(ESPACIO_MD)
        formulario.setVerticalSpacing(4)
        formulario.setColumnStretch(0, 1)
        formulario.setColumnStretch(1, 1)
        formulario.addWidget(etiqueta("Descuento"), 0, 0)
        formulario.addWidget(etiqueta("Método de pago"), 0, 1)
        formulario.addWidget(self.input_descuento, 1, 0)
        formulario.addWidget(self.combo_metodo_pago, 1, 1)
        formulario.addWidget(etiqueta("Chofer", 6), 2, 0, 1, 2)
        formulario.addWidget(self.input_chofer, 3, 0, 1, 2)
        tarjeta.cuerpo.addLayout(formulario)

        # ---- Bloque de total destacado ----
        caja_total = QFrame()
        caja_total.setObjectName("totalBox")
        v_total = QVBoxLayout(caja_total)
        v_total.setContentsMargins(ESPACIO_MD, 12, ESPACIO_MD, 12)
        v_total.setSpacing(6)

        def fila_resumen(texto: str):
            fila = QHBoxLayout()
            lbl = QLabel(texto)
            lbl.setProperty("class", "ayuda")
            valor = QLabel("S/ 0.00")
            valor.setAlignment(ALINEAR_DERECHA)
            fila.addWidget(lbl)
            fila.addStretch()
            fila.addWidget(valor)
            v_total.addLayout(fila)
            return valor

        self.label_subtotal = fila_resumen("Subtotal")
        self.label_descuento_valor = fila_resumen("Descuento")
        separador = QFrame()
        separador.setObjectName("separador")
        v_total.addWidget(separador)
        fila_total = QHBoxLayout()
        titulo_total = QLabel("Total a pagar")
        titulo_total.setObjectName("cardHeading")
        self.label_total = QLabel("S/ 0.00")
        self.label_total.setProperty("class", "total")
        self.label_total.setAlignment(ALINEAR_DERECHA)
        fila_total.addWidget(titulo_total)
        fila_total.addStretch()
        fila_total.addWidget(self.label_total)
        v_total.addLayout(fila_total)
        tarjeta.cuerpo.addWidget(caja_total)

        # ---- Botón principal ----
        self.btn_registrar = QPushButton("Registrar venta   ·   F9")
        self.btn_registrar.setProperty("class", "success large")
        self.btn_registrar.clicked.connect(self._registrar_venta)
        tarjeta.cuerpo.addWidget(self.btn_registrar)
        return tarjeta

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
            self.producto_service.listar, texto, TAMANO_PAGINA_RESULTADOS + 1, offset
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

    def _quitar_cliente(self) -> None:

        self.cliente_seleccionado_id = None

        self.cliente_seleccionado_nombre = None

        self.label_cliente_seleccionado.setText("Sin cliente seleccionado (venta general)")

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
        total = max(subtotal - descuento, 0)
        self.label_subtotal.setText(formatear_moneda(subtotal, moneda))
        self.label_descuento_valor.setText(f"- {formatear_moneda(descuento, moneda)}")
        self.label_total.setText(formatear_moneda(total, moneda))

        # Estado de la pantalla según el carrito: mensaje vacío / tabla, contador y botón de cobro.
        cantidad = len(self.carrito)
        self._pila_carrito.setCurrentIndex(1 if cantidad else 0)
        self.badge_items.setText(f"{cantidad} producto" if cantidad == 1 else f"{cantidad} productos")
        self.badge_items.setProperty("class", "badgeInfo" if cantidad else "badgeNeutral")
        self.badge_items.style().unpolish(self.badge_items)
        self.badge_items.style().polish(self.badge_items)
        self.btn_registrar.setEnabled(cantidad > 0)

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