"""Servicios: el catálogo de lo que ofrece un negocio que trabaja con reservas
(consulta, corte de cabello, sesión, clase...). Cada servicio tiene precio y duración.

Las opciones (extras y tipos de servicio) se definen UNA sola vez en su propio catálogo
(pestaña «Opciones») y cada servicio solo marca cuáles le aplican, así no se repiten datos."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QDoubleSpinBox, QSpinBox,
    QMessageBox, QTabWidget, QComboBox, QCheckBox, QAbstractItemView, QListWidget,
    QListWidgetItem,
)

from services.configuracion_service import ConfiguracionService
from services.servicio_service import ServicioService, ServicioError, CLASE_EFECTO, CLASE_TIPO
from ui.tokens import MARGEN_PAGINA, ESPACIO_MD
from ui.widgets.card import Card
from ui.widgets.page_header import PageHeader
from ui.widgets.status_badge import StatusBadge
from ui.widgets.tabla_erp import configurar_tabla_erp, item_derecha, item_centro, compactar_boton
from utils.validators import formatear_moneda


def texto_duracion(minutos: int) -> str:
    """90 -> '1 h 30 min', 45 -> '45 min', 60 -> '1 h'."""
    horas, resto = divmod(int(minutos), 60)
    if horas and resto:
        return f"{horas} h {resto} min"
    if horas:
        return f"{horas} h"
    return f"{resto} min"


def texto_clase(clase: str) -> str:
    return "Tipo de servicio" if clase == CLASE_TIPO else "Extra"


class ServicioDialog(QDialog):
    """Formulario del servicio con tres pestañas: datos básicos (precio base y duración),
    opciones (marca cuáles efectos y tipos de servicio del catálogo aplican) y productos
    que se usan al atender."""

    def __init__(self, service: ServicioService, servicio: dict | None = None,
                 moneda: str = "S/", parent=None):
        super().__init__(parent)
        self.service = service
        self.servicio = servicio
        self.moneda = moneda
        self._productos_disponibles = service.listar_productos_disponibles()
        self._catalogo = service.listar_opciones(solo_activas=False)
        self.setWindowTitle("Editar servicio" if servicio else "Nuevo servicio")
        self.resize(560, 470)

        raiz = QVBoxLayout(self)
        pestanas = QTabWidget()
        pestanas.addTab(self._pestana_datos(), "Datos")
        pestanas.addTab(self._pestana_opciones(), "Opciones")
        pestanas.addTab(self._pestana_productos(), "Productos")
        raiz.addWidget(pestanas, 1)

        if servicio:
            self.input_nombre.setText(servicio["nombre"])
            self.input_precio.setValue(servicio["precio"])
            self.input_duracion.setValue(servicio["duracion_min"])
            for prod in service.listar_productos(servicio["id"]):
                self._agregar_producto(prod["producto_id"], prod["cantidad"], bool(prod["cobrar"]))

        botones = QHBoxLayout()
        botones.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setProperty("class", "secondary")
        cancelar.clicked.connect(self.reject)
        guardar = QPushButton("Guardar")
        guardar.setProperty("class", "success")
        guardar.clicked.connect(self._guardar)
        botones.addWidget(cancelar)
        botones.addWidget(guardar)
        raiz.addLayout(botones)

    # ------------------------------------------------------ Pestañas ----
    def _pestana_datos(self) -> QWidget:
        pagina = QWidget()
        formulario = QFormLayout(pagina)
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Ej. Limpieza dental")
        formulario.addRow("Nombre:", self.input_nombre)

        self.input_precio = QDoubleSpinBox()
        self.input_precio.setMaximum(999999)
        self.input_precio.setDecimals(2)
        self.input_precio.setPrefix(f"{self.moneda} ")
        self.input_precio.setToolTip("Precio base. Los extras, tipos de servicio y productos cobrados aparte se suman a este.")
        formulario.addRow("Precio base:", self.input_precio)

        self.input_duracion = QSpinBox()
        self.input_duracion.setRange(5, 480)
        self.input_duracion.setSingleStep(5)
        self.input_duracion.setSuffix(" min")
        self.input_duracion.setValue(30)
        self.input_duracion.setToolTip("Cuánto dura la atención; la agenda reserva ese tiempo.")
        formulario.addRow("Duración:", self.input_duracion)
        return pagina

    def _pestana_opciones(self) -> QWidget:
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        ayuda = QLabel("Marca los extras y tipos de servicio que se pueden elegir en este servicio. "
                       "Se crean una sola vez en la pestaña «Opciones» de esta pantalla; aquí solo "
                       "eliges cuáles aplican. Nada viene incluido en el precio base: lo que se elija "
                       "al reservar se suma aparte.")
        ayuda.setProperty("class", "ayuda")
        ayuda.setWordWrap(True)
        capa.addWidget(ayuda)

        vinculadas = set()
        if self.servicio:
            vinculadas = {o["id"] for o in self.service.listar_subservicios(self.servicio["id"],
                                                                            solo_activos=False)}
        self.lista_opciones = QListWidget()
        for opcion in self._catalogo:
            if not opcion["activo"] and opcion["id"] not in vinculadas:
                continue
            item = QListWidgetItem(f"{opcion['nombre']}  ·  {texto_clase(opcion['clase'])}  "
                                   f"(+{self.moneda} {opcion['precio']:.2f})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if opcion["id"] in vinculadas else Qt.Unchecked)
            item.setData(Qt.UserRole, opcion["id"])
            self.lista_opciones.addItem(item)
        capa.addWidget(self.lista_opciones, 1)

        if self.lista_opciones.count() == 0:
            vacio = QLabel("Aún no hay opciones. Créalas en la pestaña «Opciones» de Servicios.")
            vacio.setProperty("class", "ayuda")
            vacio.setWordWrap(True)
            capa.addWidget(vacio)
        return pagina

    def _pestana_productos(self) -> QWidget:
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        ayuda = QLabel("Opcional. Productos que se usan o entregan al atender: descuentan stock al "
                       "cobrar. Marca «Cobrar aparte» para sumar su precio de venta al total; si no, "
                       "va incluido en el precio del servicio.")
        ayuda.setProperty("class", "ayuda")
        ayuda.setWordWrap(True)
        capa.addWidget(ayuda)

        self.tabla_prod = QTableWidget(0, 3)
        self.tabla_prod.setHorizontalHeaderLabels(["Producto", "Cantidad", "Cobrar aparte"])
        self.tabla_prod.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_prod.setColumnWidth(1, 110)
        self.tabla_prod.setColumnWidth(2, 110)
        self._config_tabla_editable(self.tabla_prod)
        capa.addWidget(self.tabla_prod, 1)
        if not self._productos_disponibles:
            vacio = QLabel("Aún no tienes productos. Créalos en el menú Productos.")
            vacio.setProperty("class", "ayuda")
            vacio.setWordWrap(True)
            capa.addWidget(vacio)
        capa.addLayout(self._botones_tabla("+ Agregar producto", self._agregar_producto, self.tabla_prod))
        return pagina

    @staticmethod
    def _config_tabla_editable(tabla: QTableWidget) -> None:
        tabla.verticalHeader().setVisible(False)
        tabla.verticalHeader().setDefaultSectionSize(40)
        tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)

    @staticmethod
    def _botones_tabla(texto_agregar: str, funcion_agregar, tabla: QTableWidget) -> QHBoxLayout:
        fila = QHBoxLayout()
        agregar = QPushButton(texto_agregar)
        agregar.setProperty("class", "secondary")
        agregar.clicked.connect(lambda: funcion_agregar())
        quitar = QPushButton("Quitar seleccionado")
        quitar.setProperty("class", "secondary")
        quitar.clicked.connect(lambda: tabla.currentRow() >= 0 and tabla.removeRow(tabla.currentRow()))
        fila.addWidget(agregar)
        fila.addWidget(quitar)
        fila.addStretch()
        return fila

    def _agregar_producto(self, producto_id: int | None = None, cantidad: float = 1.0, cobrar: bool = False) -> None:
        if not self._productos_disponibles:
            QMessageBox.information(self, "Sin productos", "Primero crea productos en el menú Productos.")
            return
        fila = self.tabla_prod.rowCount()
        self.tabla_prod.insertRow(fila)
        combo = QComboBox()
        for prod in self._productos_disponibles:
            combo.addItem(f"{prod['nombre']}  (stock {prod['stock_actual']:g})", prod["id"])
        if producto_id is not None:
            combo.setCurrentIndex(max(0, combo.findData(producto_id)))
        cant = QDoubleSpinBox()
        cant.setRange(0.01, 99999)
        cant.setDecimals(2)
        cant.setValue(cantidad)
        check = QCheckBox("Sí")
        check.setChecked(cobrar)
        contenedor = QWidget()
        capa = QHBoxLayout(contenedor)
        capa.setContentsMargins(12, 0, 0, 0)
        capa.addWidget(check)
        self.tabla_prod.setCellWidget(fila, 0, combo)
        self.tabla_prod.setCellWidget(fila, 1, cant)
        self.tabla_prod.setCellWidget(fila, 2, contenedor)

    # ------------------------------------------------------ Guardar ----
    def _leer_opciones(self) -> list[int]:
        return [self.lista_opciones.item(i).data(Qt.UserRole)
                for i in range(self.lista_opciones.count())
                if self.lista_opciones.item(i).checkState() == Qt.Checked]

    def _leer_productos(self) -> list[dict]:
        return [{"producto_id": self.tabla_prod.cellWidget(f, 0).currentData(),
                 "cantidad": self.tabla_prod.cellWidget(f, 1).value(),
                 "cobrar": self.tabla_prod.cellWidget(f, 2).findChild(QCheckBox).isChecked()}
                for f in range(self.tabla_prod.rowCount())]

    def _guardar(self) -> None:
        try:
            datos = (self.input_nombre.text(), self.input_precio.value(), self.input_duracion.value())
            extras = dict(opcion_ids=self._leer_opciones(), productos=self._leer_productos())
            if self.servicio:
                self.service.actualizar(self.servicio["id"], *datos, **extras)
            else:
                self.service.crear(*datos, **extras)
        except ServicioError as e:
            QMessageBox.warning(self, "No se pudo guardar el servicio", str(e))
            return
        self.accept()


class OpcionDialog(QDialog):
    """Crea o edita una opción del catálogo: un extra (se cobra aparte, varios a la vez) o un
    tipo de servicio (otra modalidad que no es un extra, se elige uno solo)."""

    def __init__(self, service: ServicioService, opcion: dict | None = None,
                 moneda: str = "S/", parent=None):
        super().__init__(parent)
        self.service = service
        self.opcion = opcion
        self.setWindowTitle("Editar opción" if opcion else "Nueva opción")
        self.resize(440, 220)

        raiz = QVBoxLayout(self)
        formulario = QFormLayout()
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Ej. Ojo de gato")
        formulario.addRow("Nombre:", self.input_nombre)

        self.combo_clase = QComboBox()
        self.combo_clase.addItem("Extra (se pueden elegir varios)", CLASE_EFECTO)
        self.combo_clase.addItem("Tipo de servicio (se elige uno)", CLASE_TIPO)
        formulario.addRow("Clase:", self.combo_clase)

        self.input_costo = QDoubleSpinBox()
        self.input_costo.setMaximum(999999)
        self.input_costo.setDecimals(2)
        self.input_costo.setPrefix(f"{moneda} ")
        self.input_costo.setToolTip("Se suma al precio base del servicio; nunca va incluido en él.")
        formulario.addRow("Costo adicional:", self.input_costo)
        raiz.addLayout(formulario)

        if opcion:
            self.input_nombre.setText(opcion["nombre"])
            self.combo_clase.setCurrentIndex(max(0, self.combo_clase.findData(opcion["clase"])))
            self.input_costo.setValue(opcion["precio"])

        botones = QHBoxLayout()
        botones.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setProperty("class", "secondary")
        cancelar.clicked.connect(self.reject)
        guardar = QPushButton("Guardar")
        guardar.setProperty("class", "success")
        guardar.clicked.connect(self._guardar)
        botones.addWidget(cancelar)
        botones.addWidget(guardar)
        raiz.addLayout(botones)

    def _guardar(self) -> None:
        try:
            self.service.guardar_opcion(
                self.input_nombre.text(), self.input_costo.value(), self.combo_clase.currentData(),
                self.opcion["id"] if self.opcion else None)
        except ServicioError as e:
            QMessageBox.warning(self, "No se pudo guardar la opción", str(e))
            return
        self.accept()


class OpcionesPanel(QWidget):
    """Catálogo de opciones (extras y tipos de servicio), definidas una sola vez.
    Cada servicio marca después cuáles le aplican."""

    cambio = Signal()

    def __init__(self, service: ServicioService, parent=None):
        super().__init__(parent)
        self.service = service
        self.config_service = ConfiguracionService()
        self._filas: list[dict] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, ESPACIO_MD, 0, 0)
        tarjeta = Card("Catálogo de opciones")

        ayuda = QLabel("Crea aquí una sola vez los extras (se cobran aparte, se pueden elegir varios) y "
                       "los tipos de servicio (se elige uno). Luego, en cada servicio, solo marcas cuáles "
                       "aplican. Nada viene incluido en el precio base.")
        ayuda.setProperty("class", "ayuda")
        ayuda.setWordWrap(True)
        tarjeta.cuerpo.addWidget(ayuda)

        barra = QHBoxLayout()
        boton_nueva = QPushButton("+  Nueva opción")
        boton_nueva.setProperty("class", "success")
        boton_nueva.clicked.connect(self._nueva)
        barra.addWidget(boton_nueva)
        barra.addStretch()
        tarjeta.cuerpo.addLayout(barra)

        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["Opción", "Clase", "Costo adicional", "Estado", ""])
        encabezado = self.tabla.horizontalHeader()
        encabezado.setSectionResizeMode(0, QHeaderView.Stretch)
        for columna in (1, 2):
            encabezado.setSectionResizeMode(columna, QHeaderView.ResizeToContents)
        configurar_tabla_erp(self.tabla, derecha=(2,), centro=(1, 3), altura_fila=48)
        encabezado.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tabla.setColumnWidth(3, 110)
        encabezado.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tabla.setColumnWidth(4, 230)
        self.tabla.itemDoubleClicked.connect(lambda item: self._editar(self._filas[item.row()]))
        tarjeta.cuerpo.addWidget(self.tabla, 1)

        self.label_vacio = QLabel("Aún no hay opciones. Crea la primera con «Nueva opción».")
        self.label_vacio.setProperty("class", "ayuda")
        self.label_vacio.setAlignment(Qt.AlignCenter)
        tarjeta.cuerpo.addWidget(self.label_vacio)
        raiz.addWidget(tarjeta, 1)
        self.actualizar()

    def actualizar(self) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        self._filas = self.service.listar_opciones(solo_activas=False)
        self.label_vacio.setVisible(not self._filas)
        self.tabla.clearContents()
        self.tabla.setRowCount(len(self._filas))
        for i, opcion in enumerate(self._filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(opcion["nombre"]))
            self.tabla.setItem(i, 1, item_centro(texto_clase(opcion["clase"])))
            self.tabla.setItem(i, 2, item_derecha(formatear_moneda(opcion["precio"], moneda)))
            estado = StatusBadge("Activa", "ok") if opcion["activo"] else StatusBadge("Inactiva", "neutral")
            self.tabla.setCellWidget(i, 3, estado)

            acciones = QWidget()
            fila = QHBoxLayout(acciones)
            fila.setContentsMargins(4, 4, 4, 4)
            fila.setSpacing(6)
            for texto, funcion in (
                ("Editar", lambda _, o=opcion: self._editar(o)),
                ("Desactivar" if opcion["activo"] else "Activar", lambda _, o=opcion: self._alternar(o)),
            ):
                boton = QPushButton(texto)
                boton.setProperty("class", "secondary")
                compactar_boton(boton)
                boton.clicked.connect(funcion)
                fila.addWidget(boton)
            self.tabla.setCellWidget(i, 4, acciones)

    def _nueva(self) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        if OpcionDialog(self.service, None, moneda, self).exec() == QDialog.Accepted:
            self.actualizar()
            self.cambio.emit()

    def _editar(self, opcion: dict) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        if OpcionDialog(self.service, opcion, moneda, self).exec() == QDialog.Accepted:
            self.actualizar()
            self.cambio.emit()

    def _alternar(self, opcion: dict) -> None:
        self.service.cambiar_activo_opcion(opcion["id"], not opcion["activo"])
        self.actualizar()
        self.cambio.emit()


class ServiciosPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.service = ServicioService()
        self.config_service = ConfiguracionService()
        self._filas: list[dict] = []
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA)
        raiz.setSpacing(ESPACIO_MD)

        cabecera = PageHeader("Servicios", "Lo que ofreces a tus clientes; se eligen al hacer una reserva")
        self.boton_nuevo = QPushButton("+  Nuevo servicio")
        self.boton_nuevo.setProperty("class", "success")
        self.boton_nuevo.clicked.connect(self._nuevo)
        cabecera.agregar_accion(self.boton_nuevo)
        raiz.addWidget(cabecera)

        self.pestanas = QTabWidget()
        self.pestanas.addTab(self._pestana_servicios(), "Servicios")
        self.panel_opciones = OpcionesPanel(self.service)
        self.panel_opciones.cambio.connect(self.actualizar)
        self.pestanas.addTab(self.panel_opciones, "Opciones")
        self.pestanas.currentChanged.connect(lambda i: self.boton_nuevo.setVisible(i == 0))
        raiz.addWidget(self.pestanas, 1)

    def _pestana_servicios(self) -> QWidget:
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(0, ESPACIO_MD, 0, 0)

        tarjeta = Card("Mis servicios")
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["Servicio", "Duración", "Precio base", "Estado", ""])
        encabezado = self.tabla.horizontalHeader()
        encabezado.setSectionResizeMode(0, QHeaderView.Stretch)
        for columna in (1, 2):
            encabezado.setSectionResizeMode(columna, QHeaderView.ResizeToContents)
        configurar_tabla_erp(self.tabla, derecha=(2,), centro=(1, 3), altura_fila=48)
        encabezado.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tabla.setColumnWidth(3, 110)
        encabezado.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tabla.setColumnWidth(4, 230)
        self.tabla.itemDoubleClicked.connect(lambda item: self._editar(self._filas[item.row()]))
        tarjeta.cuerpo.addWidget(self.tabla, 1)

        self.label_vacio = QLabel("Aún no hay servicios. Crea el primero con «Nuevo servicio».")
        self.label_vacio.setProperty("class", "ayuda")
        self.label_vacio.setAlignment(Qt.AlignCenter)
        tarjeta.cuerpo.addWidget(self.label_vacio)
        capa.addWidget(tarjeta, 1)
        return pagina

    def actualizar(self) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        self._filas = self.service.listar(solo_activos=False)
        self.label_vacio.setVisible(not self._filas)
        self.tabla.clearContents()
        self.tabla.setRowCount(len(self._filas))
        for i, servicio in enumerate(self._filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(servicio["nombre"]))
            self.tabla.setItem(i, 1, item_centro(texto_duracion(servicio["duracion_min"])))
            self.tabla.setItem(i, 2, item_derecha(formatear_moneda(servicio["precio"], moneda)))
            estado = StatusBadge("Activo", "ok") if servicio["activo"] else StatusBadge("Inactivo", "neutral")
            self.tabla.setCellWidget(i, 3, estado)

            acciones = QWidget()
            fila = QHBoxLayout(acciones)
            fila.setContentsMargins(4, 4, 4, 4)
            fila.setSpacing(6)
            for texto, funcion in (
                ("Editar", lambda _, s=servicio: self._editar(s)),
                ("Desactivar" if servicio["activo"] else "Activar", lambda _, s=servicio: self._alternar(s)),
            ):
                boton = QPushButton(texto)
                boton.setProperty("class", "secondary")
                compactar_boton(boton)
                boton.clicked.connect(funcion)
                fila.addWidget(boton)
            self.tabla.setCellWidget(i, 4, acciones)

    def _nuevo(self) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        if ServicioDialog(self.service, None, moneda, self).exec() == QDialog.Accepted:
            self.actualizar()

    def _editar(self, servicio: dict) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        if ServicioDialog(self.service, servicio, moneda, self).exec() == QDialog.Accepted:
            self.actualizar()

    def _alternar(self, servicio: dict) -> None:
        self.service.cambiar_activo(servicio["id"], not servicio["activo"])
        self.actualizar()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self.actualizar()
        self.panel_opciones.actualizar()
