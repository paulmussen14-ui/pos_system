"""Cupones: el sistema genera el código; aquí se configuran y se activan o desactivan."""

from PySide6.QtCore import Qt, QDate, QThreadPool
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QComboBox, QDoubleSpinBox,
    QSpinBox, QCheckBox, QDateEdit, QMessageBox, QFileDialog, QInputDialog,
)

from printing.cupon_pdf import generar_cupon_pdf, nombre_archivo_cupon
from services import correo_service
from services.cupon_service import CuponService, CuponError
from services.configuracion_service import ConfiguracionService
from ui.tokens import MARGEN_PAGINA, ESPACIO_MD
from ui.widgets.card import Card
from ui.widgets.page_header import PageHeader
from ui.widgets.status_badge import StatusBadge
from ui.widgets.tabla_erp import configurar_tabla_erp, item_derecha, item_centro, compactar_boton
from utils.logger import logger
from utils.validators import formatear_moneda, es_email_valido
from utils.worker import Worker


# ====================================================================
# PDF y correo del cupón
# ====================================================================
def guardar_cupon_pdf(parent, cupon: dict) -> None:
    """Pide dónde guardar y crea el PDF del cupón."""
    config_negocio = ConfiguracionService().obtener()
    ruta, _ = QFileDialog.getSaveFileName(
        parent, "Guardar cupón en PDF", nombre_archivo_cupon(cupon), "PDF (*.pdf)")
    if not ruta:
        return
    if not ruta.lower().endswith(".pdf"):
        ruta += ".pdf"
    try:
        generar_cupon_pdf(cupon, config_negocio, ruta)
    except Exception as exc:
        QMessageBox.warning(parent, "No se pudo guardar el PDF", str(exc))
        return
    QMessageBox.information(parent, "Cupón guardado", f"El PDF se guardó en:\n{ruta}")


def enviar_cupon_por_correo(parent, cupon: dict) -> None:
    """Pide el correo del cliente, genera el PDF y lo envía sin congelar la pantalla."""
    if not correo_service.correo_configurado():
        QMessageBox.information(
            parent, "Falta configurar el correo",
            "Para enviar cupones por correo, primero completa los datos en "
            "Configuración → Correo.")
        return
    destinatario, ok = QInputDialog.getText(
        parent, "Enviar cupón por correo", f"Correo del cliente para el cupón {cupon['codigo']}:")
    if not ok:
        return
    destinatario = destinatario.strip()
    if not es_email_valido(destinatario):
        QMessageBox.warning(parent, "Correo no válido", "Escribe un correo válido.")
        return

    config_negocio = ConfiguracionService().obtener()
    try:
        ruta_pdf = generar_cupon_pdf(cupon, config_negocio)
    except Exception as exc:
        QMessageBox.warning(parent, "No se pudo crear el PDF", str(exc))
        return

    datos, nombre_negocio = correo_service.cargar_datos_correo()
    asunto, cuerpo = correo_service.armar_correo_cupon(cupon, config_negocio)

    def terminado(error) -> None:
        if error:
            logger.warning("Cupón %s no enviado: %s", cupon["codigo"], error)
            QMessageBox.warning(None, "No se pudo enviar el cupón", error)
            return
        QMessageBox.information(None, "Cupón enviado", f"El cupón se envió a {destinatario}.")

    worker = Worker(correo_service.enviar_correo_seguro, destinatario, asunto, cuerpo,
                    [ruta_pdf], datos, nombre_negocio)
    worker.signals.finished.connect(terminado)
    worker.signals.error.connect(lambda _: terminado("Ocurrió un error inesperado al enviar."))
    QThreadPool.globalInstance().start(worker)
    QMessageBox.information(parent, "Enviando cupón",
                            f"Enviando el cupón a {destinatario}... Te avisaremos cuando termine.")


class CuponCreadoDialog(QDialog):
    """Se muestra al crear un cupón: copiar código, descargar PDF o enviarlo por correo."""

    def __init__(self, cupon: dict, parent=None):
        super().__init__(parent)
        self.cupon = cupon
        self.setWindowTitle("Cupón creado")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setSpacing(ESPACIO_MD)

        titulo = QLabel("¡Cupón creado!")
        titulo.setProperty("class", "titulo")
        layout.addWidget(titulo)
        codigo = QLabel(cupon["codigo"])
        codigo.setAlignment(Qt.AlignCenter)
        codigo.setStyleSheet("font-size: 24px; font-weight: 700; letter-spacing: 2px; padding: 10px;")
        codigo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(codigo)
        ayuda = QLabel("El código ya se copió al portapapeles.")
        ayuda.setProperty("class", "ayuda")
        ayuda.setAlignment(Qt.AlignCenter)
        layout.addWidget(ayuda)

        fila = QHBoxLayout()
        btn_pdf = QPushButton("Descargar PDF")
        btn_pdf.setProperty("class", "success")
        btn_pdf.clicked.connect(lambda: guardar_cupon_pdf(self, self.cupon))
        btn_correo = QPushButton("Enviar por correo")
        btn_correo.setProperty("class", "secondary")
        btn_correo.clicked.connect(lambda: enviar_cupon_por_correo(self, self.cupon))
        fila.addWidget(btn_pdf)
        fila.addWidget(btn_correo)
        layout.addLayout(fila)

        cerrar = QPushButton("Cerrar")
        cerrar.setProperty("class", "secondary")
        cerrar.clicked.connect(self.accept)
        layout.addWidget(cerrar)


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
        self.tabla.setColumnWidth(7, 470)
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
                              ("PDF", lambda _, cc=c: guardar_cupon_pdf(self, cc)),
                              ("Correo", lambda _, cc=c: enviar_cupon_por_correo(self, cc)),
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
            cupon = self.service.obtener_por_codigo(d.codigo_creado or "")
            if cupon:
                CuponCreadoDialog(cupon, self).exec()

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
