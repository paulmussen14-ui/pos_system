"""Página de Clientes: alta, edición y consulta de historial de compras.

La lista se carga en un hilo aparte (Worker) para no congelar la ventana.
Los cambios no ocultan datos: se conservan las filas anteriores mientras
carga o si hay un error, y una etiqueta indica cuántos clientes se muestran.

Paginación: igual que en Productos, cada consulta trae como máximo
TAMANO_PAGINA clientes. Al abrir la página o buscar se carga el primer
lote; si hay más resultados aparece "Cargar más" para traer el siguiente
lote sin recargar los que ya están en pantalla.
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFormLayout,
    QMessageBox
)
from PySide6.QtCore import QTimer, QThreadPool

from services.cliente_service import ClienteService, ClienteError
from services.venta_service import VentaService
from services.configuracion_service import ConfiguracionService
from printing.ticket_template import ancho_caracteres_por_papel
from ui.widgets.ticket_preview_dialog import TicketPreviewDialog
from utils.validators import formatear_moneda
from utils.worker import Worker
from utils.logger import logger

TAMANO_PAGINA = 200

# Mismo estilo de tabla usado en Ventas y Compras, para mantener
# consistencia visual (encabezados con separación) en toda la app.
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


class ClienteFormDialog(QDialog):

    def __init__(self, cliente=None, parent=None):
        super().__init__(parent)
        self.cliente_service = ClienteService()
        self.cliente = cliente
        self.setWindowTitle("Editar cliente" if cliente else "Nuevo cliente")
        self.resize(380, 270)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.input_nombre = QLineEdit()
        self.input_telefono = QLineEdit()
        self.input_direccion = QLineEdit()
        self.input_documento = QLineEdit()
        self.input_documento.setPlaceholderText("DNI o RUC (opcional)")

        form.addRow("Nombre:", self.input_nombre)
        form.addRow("Documento (DNI/RUC):", self.input_documento)
        form.addRow("Teléfono:", self.input_telefono)
        form.addRow("Dirección:", self.input_direccion)
        layout.addLayout(form)

        if cliente:
            self.input_nombre.setText(cliente.nombre)
            self.input_telefono.setText(cliente.telefono or "")
            self.input_direccion.setText(cliente.direccion or "")
            self.input_documento.setText(cliente.documento or "")

        botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "secondary")
        btn_cancelar.clicked.connect(self.reject)
        btn_guardar = QPushButton("Guardar")
        btn_guardar.clicked.connect(self._guardar)
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        layout.addLayout(botones)

    def _guardar(self) -> None:
        try:
            if self.cliente:
                self.cliente_service.actualizar(
                    self.cliente.id, self.input_nombre.text(),
                    self.input_telefono.text(), self.input_direccion.text(),
                    self.input_documento.text(),
                )
            else:
                self.cliente_service.crear(
                    self.input_nombre.text(),
                    self.input_telefono.text(), self.input_direccion.text(),
                    self.input_documento.text(),
                )
        except ClienteError as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        self.accept()


class ClientesPage(QWidget):

    ANCHO_COLUMNA_ACCIONES = 260

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.cliente_service = ClienteService()
        self.venta_service = VentaService()
        self.config_service = ConfiguracionService()

        # Cada consulta lleva un número. Solo se aplica la respuesta de la
        # consulta con el número más alto (la más reciente).
        self._numero_consulta = 0

        # Clientes ya cargados en la tabla (se acumulan al usar "Cargar
        # más"; se reinician al abrir la página o al cambiar la búsqueda).
        self._items: list = []
        self._hay_mas = False

        # Debounce: espera 300ms sin escribir antes de consultar.
        self._timer_busqueda = QTimer(self)
        self._timer_busqueda.setSingleShot(True)
        self._timer_busqueda.setInterval(300)
        self._timer_busqueda.timeout.connect(self.actualizar)

        self._construir_ui()
        self.actualizar()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        cabecera = QHBoxLayout()
        titulo = QLabel("Clientes")
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        cabecera.addWidget(titulo)
        cabecera.addStretch()

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setPlaceholderText("Buscar por nombre, teléfono o documento...")
        self.input_busqueda.setFixedWidth(340)
        self.input_busqueda.textChanged.connect(self._on_texto_busqueda)
        cabecera.addWidget(self.input_busqueda)

        btn_nuevo = QPushButton("+ Nuevo cliente")
        btn_nuevo.clicked.connect(self._nuevo_cliente)
        cabecera.addWidget(btn_nuevo)
        layout.addLayout(cabecera)

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Nombre", "Teléfono", "Dirección", "Acciones"])
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tabla.setColumnWidth(3, self.ANCHO_COLUMNA_ACCIONES)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setStyleSheet(ESTILO_TABLA)
        layout.addWidget(self.tabla)

        self.btn_cargar_mas = QPushButton("Cargar más")
        self.btn_cargar_mas.setProperty("class", "secondary")
        self.btn_cargar_mas.clicked.connect(self._cargar_mas)
        self.btn_cargar_mas.setVisible(False)
        layout.addWidget(self.btn_cargar_mas)

        # Línea de estado: cargando / cuántos clientes se muestran / error.
        self.label_estado = QLabel("")
        self.label_estado.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self.label_estado)

    def _on_texto_busqueda(self) -> None:
        """Reinicia el temporizador de debounce en cada tecla."""
        self._timer_busqueda.start()

    # ------------------------------------------------------ Carga ----

    def actualizar(self) -> None:
        """Carga inicial o nueva búsqueda: reinicia la paginación desde cero."""
        self._items = []
        self._hay_mas = False
        self.btn_cargar_mas.setVisible(False)
        self._cargar(modo="reset")

    def _cargar_mas(self) -> None:
        self._cargar(modo="append")

    def _cargar(self, modo: str) -> None:
        self._numero_consulta += 1
        numero = self._numero_consulta
        texto = self.input_busqueda.text()
        offset = 0 if modo == "reset" else len(self._items)

        self.btn_cargar_mas.setEnabled(False)
        if modo == "reset":
            self.label_estado.setStyleSheet("color: #6b7280; font-size: 12px;")
            self.label_estado.setText("Cargando...")
        else:
            self.label_estado.setText(f"Cargando más... (mostrando {len(self._items)})")

        # Se pide un cliente extra (TAMANO_PAGINA + 1) solo para saber si hay
        # más resultados después de este lote, sin necesitar un COUNT aparte;
        # ese cliente de más nunca se muestra en la tabla.
        worker = Worker(self.cliente_service.listar, texto, TAMANO_PAGINA + 1, offset)
        worker.signals.finished.connect(
            lambda clientes, n=numero, t=texto, m=modo: self._on_clientes_listos(n, t, clientes, m)
        )
        worker.signals.error.connect(
            lambda mensaje, n=numero: self._on_error_carga(n, mensaje)
        )
        QThreadPool.globalInstance().start(worker)

    def _on_error_carga(self, numero: int, mensaje: str) -> None:
        if numero != self._numero_consulta:
            return
        logger.error("Error cargando clientes: %s", mensaje)
        # No se toca la tabla: se conservan las filas que ya estaban.
        self.btn_cargar_mas.setEnabled(True)
        self.label_estado.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: 600;")
        self.label_estado.setText(
            "No se pudo cargar la lista de clientes. "
            "Los datos mostrados pueden estar desactualizados."
        )

    def _on_clientes_listos(self, numero: int, texto: str, clientes, modo: str) -> None:
        if numero != self._numero_consulta:
            return

        self._hay_mas = len(clientes) > TAMANO_PAGINA
        nuevos = clientes[:TAMANO_PAGINA]

        if modo == "reset":
            self._items = nuevos
            fila_inicial = 0
        else:
            fila_inicial = len(self._items)
            self._items.extend(nuevos)

        # Se apaga el repintado mientras se llenan las filas. En "Cargar
        # más" solo se llenan las filas nuevas; las que ya estaban no se
        # vuelven a tocar.
        self.tabla.setUpdatesEnabled(False)
        try:
            self.tabla.setRowCount(len(self._items))
            for i, c in enumerate(nuevos):
                self._llenar_fila(fila_inicial + i, c)
        finally:
            self.tabla.setUpdatesEnabled(True)

        self.btn_cargar_mas.setVisible(self._hay_mas)
        self.btn_cargar_mas.setEnabled(True)

        if len(self._items) > 0:
            texto_estado = f"Mostrando {len(self._items)} cliente(s)"
            if self._hay_mas:
                texto_estado += " — hay más resultados, usa \"Cargar más\""
            self.label_estado.setText(texto_estado)
        elif texto.strip():
            self.label_estado.setText(f"Sin resultados para '{texto}'")
        else:
            self.label_estado.setText("No hay clientes registrados")

    def _llenar_fila(self, fila: int, c) -> None:
        self.tabla.setItem(fila, 0, QTableWidgetItem(c.nombre))
        self.tabla.setItem(fila, 1, QTableWidgetItem(c.telefono or "-"))
        self.tabla.setItem(fila, 2, QTableWidgetItem(c.direccion or "-"))

        widget_acciones = QWidget()
        layout_acciones = QHBoxLayout(widget_acciones)
        layout_acciones.setContentsMargins(6, 4, 6, 4)
        layout_acciones.setSpacing(8)

        btn_historial = QPushButton("Historial")
        btn_historial.setProperty("class", "secondary")
        btn_historial.setMinimumHeight(32)
        btn_historial.clicked.connect(lambda _, cli=c: self._ver_historial(cli))

        btn_editar = QPushButton("Editar")
        btn_editar.setProperty("class", "secondary")
        btn_editar.setMinimumHeight(32)
        btn_editar.clicked.connect(lambda _, cli=c: self._editar_cliente(cli))

        layout_acciones.addWidget(btn_historial)
        layout_acciones.addWidget(btn_editar)
        self.tabla.setRowHeight(fila, 46)
        self.tabla.setCellWidget(fila, 3, widget_acciones)

    # ---------------------------------------------------- Acciones ----

    def _nuevo_cliente(self) -> None:
        dialogo = ClienteFormDialog(parent=self)
        if dialogo.exec():
            self.actualizar()

    def _editar_cliente(self, cliente) -> None:
        dialogo = ClienteFormDialog(cliente=cliente, parent=self)
        if dialogo.exec():
            self.actualizar()

    def _ver_historial(self, cliente) -> None:
        ventas = self.cliente_service.historial_compras(cliente.id)

        dialogo = QDialog(self)
        dialogo.setWindowTitle(f"Historial de {cliente.nombre}")
        dialogo.resize(640, 380)
        layout = QVBoxLayout(dialogo)

        tabla = QTableWidget(0, 4)
        tabla.setHorizontalHeaderLabels(["Venta #", "Fecha", "Total", ""])
        header = tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        tabla.setColumnWidth(3, 250)
        tabla.verticalHeader().setVisible(False)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        tabla.setSelectionBehavior(QTableWidget.SelectRows)
        tabla.setAlternatingRowColors(True)
        tabla.setStyleSheet(ESTILO_TABLA)
        layout.addWidget(tabla)

        if ventas:
            tabla.setRowCount(len(ventas))
            for fila, v in enumerate(ventas):
                tabla.setItem(fila, 0, QTableWidgetItem(str(v["id"])))
                tabla.setItem(fila, 1, QTableWidgetItem(str(v["fecha"])))
                tabla.setItem(fila, 2, QTableWidgetItem(formatear_moneda(v["total"])))

                widget_botones = QWidget()
                layout_botones = QHBoxLayout(widget_botones)
                layout_botones.setContentsMargins(4, 3, 4, 3)
                layout_botones.setSpacing(6)

                btn_ticket = QPushButton("Ver ticket")
                btn_ticket.setProperty("class", "secondary")
                btn_ticket.setMinimumHeight(30)
                btn_ticket.clicked.connect(
                    lambda _, venta_id=v["id"]: self._ver_ticket(venta_id, es_copia=False)
                )

                btn_copia = QPushButton("Imprimir copia")
                btn_copia.setProperty("class", "secondary")
                btn_copia.setMinimumHeight(30)
                btn_copia.clicked.connect(
                    lambda _, venta_id=v["id"]: self._ver_ticket(venta_id, es_copia=True)
                )

                layout_botones.addWidget(btn_ticket)
                layout_botones.addWidget(btn_copia)
                tabla.setCellWidget(fila, 3, widget_botones)
                tabla.setRowHeight(fila, 42)

            # Doble clic en cualquier parte de la fila también abre el ticket.
            tabla.cellDoubleClicked.connect(
                lambda fila, columna, t=tabla: self._ver_ticket_de_fila(t, fila)
            )

            ayuda = QLabel("Doble clic o \"Ver ticket\" para ver el ticket. \"Imprimir copia\" genera una reimpresión marcada como COPIA.")
            ayuda.setStyleSheet("color: #6b7280; font-size: 11px;")
            layout.addWidget(ayuda)
        else:
            layout.addWidget(QLabel("Este cliente aún no tiene compras registradas."))

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(btn_cerrar)

        dialogo.exec()

    def _ver_ticket_de_fila(self, tabla: QTableWidget, fila: int) -> None:
        item = tabla.item(fila, 0)
        if item is None:
            return
        self._ver_ticket(int(item.text()))

    def _ver_ticket(self, venta_id: int, es_copia: bool = False) -> None:
        """Abre la vista previa del ticket de una venta pasada, igual que
        se ve al registrarla en Ventas."""
        try:
            venta = self.venta_service.obtener_venta_con_lineas(venta_id)
            config_negocio = self.config_service.obtener()
            config_impresion = self.config_service.obtener_config_impresion()
        except Exception:
            logger.exception("No se pudo cargar el ticket de la venta %s", venta_id)
            QMessageBox.warning(
                self, "Ticket",
                f"No se pudo cargar el ticket de la venta #{venta_id}."
            )
            return

        if not venta:
            QMessageBox.warning(
                self, "Ticket", f"No se encontró la venta #{venta_id}."
            )
            return

        ancho = ancho_caracteres_por_papel(config_impresion.get("ancho_papel_mm"))
        if config_impresion.get("activo"):
            nombre_impresora = config_impresion.get("nombre_impresora")
        else:
            nombre_impresora = None
        imprimir_dos_copias = bool(config_impresion.get("imprimir_dos_copias", True))

        if es_copia:
            # Reimpresión para reclamos y verificaciones: una sola hoja,
            # con una marca arriba para que no se confunda con el original.
            # Se trabaja sobre una copia de la configuración, sin cambiar
            # lo que está guardado. ticket_template.py imprime esta marca.
            config_negocio = dict(config_negocio)
            config_negocio["etiqueta_reimpresion"] = (
                "*** COPIA - REIMPRESION ***\n"
                f"Impresa el {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            imprimir_dos_copias = False

        dialogo = TicketPreviewDialog(
            venta,
            config_negocio,
            nombre_impresora,
            ancho_caracteres=ancho,
            imprimir_dos_copias=imprimir_dos_copias,
            parent=self,
        )
        if es_copia:
            dialogo.setWindowTitle(f"Venta #{venta_id} — COPIA para reclamos")
        else:
            dialogo.setWindowTitle(f"Venta #{venta_id} — Ticket")
        dialogo.exec()