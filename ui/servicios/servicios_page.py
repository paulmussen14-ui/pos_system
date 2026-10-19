"""Servicios: el catálogo de lo que ofrece un negocio que trabaja con reservas
(consulta, corte de cabello, sesión, clase...). Cada servicio tiene precio y duración."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QDoubleSpinBox, QSpinBox,
    QMessageBox, QTabWidget, QComboBox, QCheckBox, QAbstractItemView,
)

from services.configuracion_service import ConfiguracionService
from services.servicio_service import ServicioService, ServicioError
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


class ServicioDialog(QDialog):
    """Formulario del servicio con tres pestañas: datos básicos (precio base y duración),
    sub-servicios (cada uno con su costo adicional) y productos que se usan al atender."""

    def __init__(self, service: ServicioService, servicio: dict | None = None,
                 moneda: str = "S/", parent=None):
        super().__init__(parent)
        self.service = service
        self.servicio = servicio
        self.moneda = moneda
        self._productos_disponibles = service.listar_productos_disponibles()
        self.setWindowTitle("Editar servicio" if servicio else "Nuevo servicio")
        self.resize(560, 470)

        raiz = QVBoxLayout(self)
        pestanas = QTabWidget()
        pestanas.addTab(self._pestana_datos(), "Datos")
        pestanas.addTab(self._pestana_subservicios(), "Sub-servicios")
        pestanas.addTab(self._pestana_productos(), "Productos")
        raiz.addWidget(pestanas, 1)

        if servicio:
            self.input_nombre.setText(servicio["nombre"])
            self.input_precio.setValue(servicio["precio"])
            self.input_duracion.setValue(servicio["duracion_min"])
            for sub in service.listar_subservicios(servicio["id"]):
                self._agregar_subservicio(sub["id"], sub["nombre"], sub["precio"])
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
        self.input_precio.setToolTip("Precio base. Los sub-servicios y productos cobrados aparte se suman a este.")
        formulario.addRow("Precio base:", self.input_precio)

        self.input_duracion = QSpinBox()
        self.input_duracion.setRange(5, 480)
        self.input_duracion.setSingleStep(5)
        self.input_duracion.setSuffix(" min")
        self.input_duracion.setValue(30)
        self.input_duracion.setToolTip("Cuánto dura la atención; la agenda reserva ese tiempo.")
        formulario.addRow("Duración:", self.input_duracion)
        return pagina

    def _pestana_subservicios(self) -> QWidget:
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        ayuda = QLabel("Opcional. Variantes o adicionales de este servicio. Al reservar se marcan "
                       "los que corresponden y su costo se suma al precio base.")
        ayuda.setProperty("class", "ayuda")
        ayuda.setWordWrap(True)
        capa.addWidget(ayuda)

        self.tabla_sub = QTableWidget(0, 2)
        self.tabla_sub.setHorizontalHeaderLabels(["Sub-servicio", "Costo adicional"])
        self.tabla_sub.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_sub.setColumnWidth(1, 150)
        self._config_tabla_editable(self.tabla_sub)
        capa.addWidget(self.tabla_sub, 1)
        capa.addLayout(self._botones_tabla("+ Agregar sub-servicio", self._agregar_subservicio,
                                           self.tabla_sub))
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

    def _agregar_subservicio(self, sub_id: int | None = None, nombre: str = "", precio: float = 0.0) -> None:
        fila = self.tabla_sub.rowCount()
        self.tabla_sub.insertRow(fila)
        campo = QLineEdit(nombre)
        campo.setPlaceholderText("Ej. Fluorización")
        campo.setProperty("sub_id", sub_id)
        costo = QDoubleSpinBox()
        costo.setMaximum(999999)
        costo.setDecimals(2)
        costo.setPrefix(f"{self.moneda} ")
        costo.setValue(precio)
        self.tabla_sub.setCellWidget(fila, 0, campo)
        self.tabla_sub.setCellWidget(fila, 1, costo)
        if sub_id is None:
            campo.setFocus()

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
    def _leer_subservicios(self) -> list[dict]:
        return [{"id": self.tabla_sub.cellWidget(f, 0).property("sub_id"),
                 "nombre": self.tabla_sub.cellWidget(f, 0).text(),
                 "precio": self.tabla_sub.cellWidget(f, 1).value()}
                for f in range(self.tabla_sub.rowCount())]

    def _leer_productos(self) -> list[dict]:
        return [{"producto_id": self.tabla_prod.cellWidget(f, 0).currentData(),
                 "cantidad": self.tabla_prod.cellWidget(f, 1).value(),
                 "cobrar": self.tabla_prod.cellWidget(f, 2).findChild(QCheckBox).isChecked()}
                for f in range(self.tabla_prod.rowCount())]

    def _guardar(self) -> None:
        try:
            datos = (self.input_nombre.text(), self.input_precio.value(), self.input_duracion.value())
            extras = dict(subservicios=self._leer_subservicios(), productos=self._leer_productos())
            if self.servicio:
                self.service.actualizar(self.servicio["id"], *datos, **extras)
            else:
                self.service.crear(*datos, **extras)
        except ServicioError as e:
            QMessageBox.warning(self, "No se pudo guardar el servicio", str(e))
            return
        self.accept()


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
        boton_nuevo = QPushButton("+  Nuevo servicio")
        boton_nuevo.setProperty("class", "success")
        boton_nuevo.clicked.connect(self._nuevo)
        cabecera.agregar_accion(boton_nuevo)
        raiz.addWidget(cabecera)

        tarjeta = Card("Mis servicios")
        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(["Servicio", "Incluye", "Duración", "Precio base", "Estado", ""])
        encabezado = self.tabla.horizontalHeader()
        encabezado.setSectionResizeMode(0, QHeaderView.Stretch)
        for columna in (1, 2, 3):
            encabezado.setSectionResizeMode(columna, QHeaderView.ResizeToContents)
        configurar_tabla_erp(self.tabla, derecha=(3,), centro=(2, 4), altura_fila=48)
        encabezado.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tabla.setColumnWidth(4, 110)
        encabezado.setSectionResizeMode(5, QHeaderView.Fixed)
        self.tabla.setColumnWidth(5, 230)
        self.tabla.itemDoubleClicked.connect(lambda item: self._editar(self._filas[item.row()]))
        tarjeta.cuerpo.addWidget(self.tabla, 1)

        self.label_vacio = QLabel("Aún no hay servicios. Crea el primero con «Nuevo servicio».")
        self.label_vacio.setProperty("class", "ayuda")
        self.label_vacio.setAlignment(Qt.AlignCenter)
        tarjeta.cuerpo.addWidget(self.label_vacio)
        raiz.addWidget(tarjeta, 1)

    def actualizar(self) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        self._filas = self.service.listar(solo_activos=False)
        self.label_vacio.setVisible(not self._filas)
        self.tabla.clearContents()
        self.tabla.setRowCount(len(self._filas))
        for i, servicio in enumerate(self._filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(servicio["nombre"]))
            n_sub = len(self.service.listar_subservicios(servicio["id"]))
            n_prod = len(self.service.listar_productos(servicio["id"]))
            incluye = " · ".join(x for x in (
                f"{n_sub} sub-servicio(s)" if n_sub else "", f"{n_prod} producto(s)" if n_prod else "") if x)
            self.tabla.setItem(i, 1, QTableWidgetItem(incluye or "—"))
            self.tabla.setItem(i, 2, item_centro(texto_duracion(servicio["duracion_min"])))
            self.tabla.setItem(i, 3, item_derecha(formatear_moneda(servicio["precio"], moneda)))
            estado = StatusBadge("Activo", "ok") if servicio["activo"] else StatusBadge("Inactivo", "neutral")
            self.tabla.setCellWidget(i, 4, estado)

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
            self.tabla.setCellWidget(i, 5, acciones)

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
