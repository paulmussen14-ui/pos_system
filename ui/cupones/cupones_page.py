"""Cupones: el sistema genera el código; aquí se configuran y se activan o desactivan."""

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QComboBox, QDoubleSpinBox,
    QSpinBox, QCheckBox, QDateEdit, QMessageBox,
)

from services.cupon_service import CuponService, CuponError
from services.configuracion_service import ConfiguracionService
from ui.tokens import MARGEN_PAGINA, ESPACIO_MD
from ui.widgets.card import Card
from ui.widgets.page_header import PageHeader
from ui.widgets.status_badge import StatusBadge
from ui.widgets.tabla_erp import configurar_tabla_erp, item_derecha, item_centro, compactar_boton
from utils.validators import formatear_moneda


class CuponDialog(QDialog):

    def __init__(self, service: CuponService, parent=None):
        super().__init__(parent)
        self.service = service
        self.codigo_creado: str | None = None
        self.setWindowTitle("Nuevo cupón")
        self.resize(420, 400)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        fila_codigo = QHBoxLayout()
        self.input_codigo = QLineEdit(service.generar_codigo())
        self.input_codigo.setToolTip("Generado automáticamente. Puedes editarlo o generar otro.")
        btn_otro = QPushButton("Generar otro")
        btn_otro.setProperty("class", "secondary")
        btn_otro.clicked.connect(lambda: self.input_codigo.setText(self.service.generar_codigo()))
        fila_codigo.addWidget(self.input_codigo, 1)
        fila_codigo.addWidget(btn_otro)
        form.addRow("Código", fila_codigo)

        self.input_desc = QLineEdit()
        self.input_desc.setPlaceholderText("Ej. Promo clientes nuevos")
        form.addRow("Descripción", self.input_desc)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItem("Porcentaje (%)", "porcentaje")
        self.combo_tipo.addItem("Monto fijo", "monto")
        self.combo_tipo.currentIndexChanged.connect(self._ajustar_valor)
        form.addRow("Tipo", self.combo_tipo)

        self.input_valor = QDoubleSpinBox()
        self.input_valor.setMaximum(999999)
        self.input_valor.setDecimals(2)
        self.input_valor.setValue(10)
        form.addRow("Valor", self.input_valor)

        self.input_minima = QDoubleSpinBox()
        self.input_minima.setMaximum(999999)
        form.addRow("Compra mínima", self.input_minima)

        self.input_usos = QSpinBox()
        self.input_usos.setMaximum(1000000)
        self.input_usos.setSpecialValueText("Ilimitado")
        form.addRow("Usos máximos", self.input_usos)

        self.chk_vigencia = QCheckBox("Limitar por fechas")
        form.addRow("", self.chk_vigencia)
        self.fecha_ini = QDateEdit(QDate.currentDate())
        self.fecha_fin = QDateEdit(QDate.currentDate().addDays(30))
        for f in (self.fecha_ini, self.fecha_fin):
            f.setCalendarPopup(True)
            f.setDisplayFormat("yyyy-MM-dd")
            f.setEnabled(False)
            self.chk_vigencia.toggled.connect(f.setEnabled)
        form.addRow("Desde", self.fecha_ini)
        form.addRow("Hasta", self.fecha_fin)
        layout.addLayout(form)

        botones = QHBoxLayout()
        botones.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setProperty("class", "secondary")
        cancelar.clicked.connect(self.reject)
        guardar = QPushButton("Crear cupón")
        guardar.setProperty("class", "success")
        guardar.clicked.connect(self._guardar)
        botones.addWidget(cancelar)
        botones.addWidget(guardar)
        layout.addLayout(botones)
        self._ajustar_valor()

    def _ajustar_valor(self) -> None:
        porcentaje = self.combo_tipo.currentData() == "porcentaje"
        self.input_valor.setMaximum(100 if porcentaje else 999999)
        self.input_valor.setSuffix(" %" if porcentaje else "")
        self.input_valor.setPrefix("" if porcentaje else "S/ ")

    def _guardar(self) -> None:
        try:
            self.codigo_creado = self.service.crear(
                self.input_desc.text(), self.combo_tipo.currentData(), self.input_valor.value(),
                self.input_minima.value(),
                self.fecha_ini.date().toString("yyyy-MM-dd") if self.chk_vigencia.isChecked() else None,
                self.fecha_fin.date().toString("yyyy-MM-dd") if self.chk_vigencia.isChecked() else None,
                self.input_usos.value(), self.input_codigo.text(),
            )
        except CuponError as e:
            QMessageBox.warning(self, "No se pudo crear el cupón", str(e))
            return
        self.accept()


class CuponesPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.service = CuponService()
        self.config_service = ConfiguracionService()
        self._filas: list[dict] = []
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA)
        raiz.setSpacing(ESPACIO_MD)
        cab = PageHeader("Cupones", "Códigos de descuento generados por el sistema; se aplican en Ventas")
        btn_nuevo = QPushButton("+  Generar cupón")
        btn_nuevo.setProperty("class", "success")
        btn_nuevo.clicked.connect(self._nuevo)
        cab.agregar_accion(btn_nuevo)
        raiz.addWidget(cab)

        tarjeta = Card("Mis cupones")
        self.tabla = QTableWidget(0, 8)
        self.tabla.setHorizontalHeaderLabels(
            ["Código", "Descripción", "Descuento", "Mínimo", "Vigencia", "Usos", "Estado", ""])
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5, 6, 7):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        configurar_tabla_erp(self.tabla, derecha=(2, 3), centro=(5, 6), altura_fila=48)
        self.tabla.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.tabla.setColumnWidth(6, 110)
        self.tabla.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed)
        self.tabla.setColumnWidth(7, 320)
        tarjeta.cuerpo.addWidget(self.tabla, 1)
        self.label_vacio = QLabel("Aún no hay cupones. Crea el primero con «Generar cupón».")
        self.label_vacio.setProperty("class", "ayuda")
        self.label_vacio.setAlignment(Qt.AlignCenter)
        tarjeta.cuerpo.addWidget(self.label_vacio)
        raiz.addWidget(tarjeta, 1)

    def actualizar(self) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        self._filas = self.service.listar()
        self.label_vacio.setVisible(not self._filas)
        self.tabla.clearContents()
        self.tabla.setRowCount(len(self._filas))
        from datetime import date
        hoy = date.today().isoformat()
        for i, c in enumerate(self._filas):
            valor = f"{c['valor']:g} %" if c["tipo"] == "porcentaje" else formatear_moneda(c["valor"], moneda)
            if c["fecha_inicio"] or c["fecha_fin"]:
                vig = f"{(c['fecha_inicio'] or '…')[:10]} → {(c['fecha_fin'] or '…')[:10]}"
            else:
                vig = "Sin límite"
            usos = f"{c['usos']}/{c['usos_maximos']}" if c["usos_maximos"] else f"{c['usos']}"
            vencido = bool(c["fecha_fin"] and hoy > c["fecha_fin"][:10])
            agotado = bool(c["usos_maximos"] and c["usos"] >= c["usos_maximos"])
            self.tabla.setItem(i, 0, QTableWidgetItem(c["codigo"]))
            self.tabla.setItem(i, 1, QTableWidgetItem(c["descripcion"] or ""))
            self.tabla.setItem(i, 2, item_derecha(valor))
            self.tabla.setItem(i, 3, item_derecha(formatear_moneda(c["compra_minima"], moneda)
                                                   if c["compra_minima"] else "—"))
            self.tabla.setItem(i, 4, QTableWidgetItem(vig))
            self.tabla.setItem(i, 5, item_centro(usos))
            if not c["activo"]:
                estado = StatusBadge("Inactivo", "neutral")
            elif vencido:
                estado = StatusBadge("Vencido", "danger")
            elif agotado:
                estado = StatusBadge("Agotado", "warning")
            else:
                estado = StatusBadge("Activo", "ok")
            self.tabla.setCellWidget(i, 6, estado)
            acciones = QWidget()
            fila = QHBoxLayout(acciones)
            fila.setContentsMargins(4, 4, 4, 4)
            fila.setSpacing(6)
            for texto, fn in (("Copiar", lambda _, cc=c: self._copiar(cc)),
                              ("Desactivar" if c["activo"] else "Activar", lambda _, cc=c: self._alternar(cc)),
                              ("Eliminar", lambda _, cc=c: self._eliminar(cc))):
                b = QPushButton(texto)
                b.setProperty("class", "secondary")
                compactar_boton(b)
                b.clicked.connect(fn)
                fila.addWidget(b)
            self.tabla.setCellWidget(i, 7, acciones)

    def _nuevo(self) -> None:
        d = CuponDialog(self.service, self)
        if d.exec() == QDialog.Accepted:
            self.actualizar()
            QGuiApplication.clipboard().setText(d.codigo_creado or "")
            QMessageBox.information(self, "Cupón creado",
                                    f"Código: {d.codigo_creado}\n(Copiado al portapapeles)")

    def _copiar(self, c: dict) -> None:
        QGuiApplication.clipboard().setText(c["codigo"])

    def _alternar(self, c: dict) -> None:
        self.service.cambiar_activo(c["id"], not c["activo"])
        self.actualizar()

    def _eliminar(self, c: dict) -> None:
        if QMessageBox.question(self, "Eliminar cupón", f"¿Eliminar el cupón {c['codigo']}?\n"
                                "Las ventas ya hechas conservan el código usado.") == QMessageBox.Yes:
            self.service.eliminar(c["id"])
            self.actualizar()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.actualizar()
