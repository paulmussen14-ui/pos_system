"""Diálogos de la agenda: reservar una hora, ver/gestionar una reserva, cobrarla y
mostrar su boleta (vista previa, PDF, correo, impresión)."""

from datetime import date

from PySide6.QtCore import Qt, QDate, QThreadPool
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QCheckBox, QMessageBox,
    QFileDialog, QInputDialog, QScrollArea, QFrame, QWidget, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from shiboken6 import isValid

from printing.boleta_pdf import (
    generar_boleta_pdf, generar_comprobante_reserva_pdf, nombre_archivo_boleta,
)
from printing.ticket_template import ancho_caracteres_por_papel
from services import correo_service
from services.caja_service import CajaService
from services.cliente_service import ClienteService
from services.configuracion_service import ConfiguracionService
from services.reserva_service import (
    ReservaService, ReservaError, ESTADO_RESERVADA, ESTADO_ATENDIDA, ESTADO_NO_ASISTIO,
)
from services.servicio_service import ServicioService, CLASE_TIPO
from ui.tokens import ESPACIO_SM, ESPACIO_MD
from ui.widgets.card import Card
from ui.widgets.status_badge import StatusBadge
from ui.widgets.tabla_erp import configurar_tabla_erp, item_derecha
from ui.widgets.ticket_preview_dialog import TicketPreviewDialog
from utils.logger import logger
from utils.fechas import DIAS_CORTOS, a_hhmm, a_minutos, fecha_dmy, fecha_larga, parsear_fecha
from utils.validators import es_email_valido, formatear_moneda
from utils.worker import Worker


# ====================================================================
# Envío de la boleta por correo (en segundo plano)
# ====================================================================
def enviar_boleta_por_correo(parent, reserva: dict, destinatario: str) -> None:
    """Genera el PDF y lo envía sin congelar la pantalla. Al terminar avisa del
    resultado y, si salió bien, anota a qué correo se envió."""
    if not es_email_valido(destinatario):
        QMessageBox.warning(parent, "Correo no válido", "Escribe un correo válido para el cliente.")
        return
    if not correo_service.correo_configurado():
        QMessageBox.information(
            parent, "Falta configurar el correo",
            "Para enviar boletas por correo, primero completa los datos en "
            "Configuración → Correo.")
        return

    config_negocio = ConfiguracionService().obtener()
    try:
        ruta_pdf = generar_boleta_pdf(reserva, config_negocio)
    except Exception as exc:  # el PDF se arma con Qt; cualquier fallo se muestra, no se pierde
        QMessageBox.warning(parent, "No se pudo crear el PDF", str(exc))
        return

    datos, nombre_negocio = correo_service.cargar_datos_correo()
    asunto, cuerpo = correo_service.armar_correo_boleta(reserva, config_negocio)
    reserva_id = reserva["id"]

    def terminado(error) -> None:
        if error:
            QMessageBox.warning(None, "No se pudo enviar la boleta", error)
            return
        ReservaService().registrar_envio(reserva_id, destinatario)
        QMessageBox.information(None, "Boleta enviada", f"La boleta se envió a {destinatario}.")

    worker = Worker(correo_service.enviar_correo_seguro, destinatario, asunto, cuerpo,
                    [ruta_pdf], datos, nombre_negocio)
    worker.signals.finished.connect(terminado)
    worker.signals.error.connect(lambda _: terminado("Ocurrió un error inesperado al enviar."))
    QThreadPool.globalInstance().start(worker)
    QMessageBox.information(parent, "Enviando boleta",
                            f"Enviando la boleta a {destinatario}... Te avisaremos cuando termine.")


def enviar_comprobante_reserva_por_correo(reserva_id: int, al_terminar=None) -> None:
    """Al reservar: envía al cliente un correo avisando que tiene una cita pendiente, con el
    comprobante de reserva en PDF. Solo si la reserva tiene correo y el correo del negocio
    está configurado; si no, no hace nada. Va en segundo plano y no interrumpe: solo se
    muestra algo si el envío falla (la reserva ya quedó guardada). Nunca lanza excepciones."""
    try:
        _enviar_comprobante_reserva(reserva_id, al_terminar)
    except Exception:
        logger.exception("No se pudo enviar el comprobante de la reserva %s", reserva_id)


def _enviar_comprobante_reserva(reserva_id: int, al_terminar=None) -> None:
    if not correo_service.correo_configurado():
        logger.info("Reserva %s: correo del negocio sin configurar, no se envía comprobante", reserva_id)
        if al_terminar:
            QMessageBox.information(
                None, "Falta configurar el correo",
                "Para enviar correos, primero completa los datos en Configuración → Correo.")
        return
    reserva = ReservaService().obtener(reserva_id)
    destinatario = ((reserva or {}).get("cliente_email") or "").strip()
    if not destinatario or not es_email_valido(destinatario):
        return
    config_negocio = ConfiguracionService().obtener()
    try:
        ruta_pdf = generar_comprobante_reserva_pdf(reserva, config_negocio)
    except Exception as exc:
        logger.exception("No se pudo crear el PDF de la reserva %s", reserva_id)
        QMessageBox.warning(
            None, "No se pudo crear el comprobante de la reserva",
            f"La reserva se guardó, pero no se pudo generar el PDF para {destinatario}.\n\n{exc}")
        return
    datos, nombre_negocio = correo_service.cargar_datos_correo()
    asunto, cuerpo = correo_service.armar_correo_reserva(reserva, config_negocio)

    def terminado(error) -> None:
        if error:
            logger.warning("Comprobante de reserva %s no enviado: %s", reserva_id, error)
            QMessageBox.warning(
                None, "No se pudo enviar el comprobante de la reserva",
                f"La reserva se guardó, pero no se pudo enviar el correo a {destinatario}.\n\n{error}")
        else:
            logger.info("Comprobante de reserva %s enviado a %s", reserva_id, destinatario)
            ReservaService().registrar_envio_comprobante(reserva_id, destinatario)
        if al_terminar:
            al_terminar()

    worker = Worker(correo_service.enviar_correo_seguro, destinatario, asunto, cuerpo,
                    [ruta_pdf], datos, nombre_negocio)
    worker.signals.finished.connect(terminado)
    worker.signals.error.connect(lambda _: terminado("Ocurrió un error inesperado al enviar."))
    QThreadPool.globalInstance().start(worker)


def avisar_adelanto_por_correo(reserva_id: int, monto: float) -> None:
    """Avisa por correo al cliente que recibimos su adelanto. Solo si la reserva tiene correo
    y el correo del negocio está configurado; si no, no hace nada. Va en segundo plano y no
    interrumpe: solo se muestra algo si el envío falla."""
    if not monto or monto <= 0 or not correo_service.correo_configurado():
        return
    reserva = ReservaService().obtener(reserva_id)
    destinatario = ((reserva or {}).get("cliente_email") or "").strip()
    if not destinatario:
        return
    config_negocio = ConfiguracionService().obtener()
    datos, nombre_negocio = correo_service.cargar_datos_correo()
    asunto, cuerpo = correo_service.armar_correo_adelanto(reserva, config_negocio, monto)

    def terminado(error) -> None:
        if error:
            QMessageBox.warning(
                None, "No se pudo avisar el adelanto por correo",
                f"El adelanto se registró, pero no se pudo enviar el correo a {destinatario}.\n\n{error}")

    worker = Worker(correo_service.enviar_correo_seguro, destinatario, asunto, cuerpo,
                    [], datos, nombre_negocio)
    worker.signals.finished.connect(terminado)
    worker.signals.error.connect(lambda _: terminado("Ocurrió un error inesperado al enviar."))
    QThreadPool.globalInstance().start(worker)


def guardar_boleta_pdf(parent, reserva: dict) -> None:
    """Pide dónde guardar y crea el PDF de la boleta."""
    config_negocio = ConfiguracionService().obtener()
    ruta, _ = QFileDialog.getSaveFileName(
        parent, "Guardar boleta en PDF", nombre_archivo_boleta(reserva), "PDF (*.pdf)")
    if not ruta:
        return
    if not ruta.lower().endswith(".pdf"):
        ruta += ".pdf"
    try:
        generar_boleta_pdf(reserva, config_negocio, ruta)
    except Exception as exc:
        QMessageBox.warning(parent, "No se pudo guardar el PDF", str(exc))
        return
    QMessageBox.information(parent, "Boleta guardada", f"El PDF se guardó en:\n{ruta}")


# ====================================================================
# Boleta (vista previa + PDF + correo + impresión)
# ====================================================================
class BoletaDialog(TicketPreviewDialog):
    """Reutiliza la vista previa del ticket de Ventas y le suma PDF y correo."""

    def __init__(self, reserva: dict, parent=None):
        config_negocio = ConfiguracionService().obtener()
        config_impresion = ConfiguracionService().obtener_config_impresion()
        venta = ReservaService.venta_para_ticket(reserva, config_negocio.get("moneda", "S/"))
        nombre_impresora = config_impresion.get("nombre_impresora") if config_impresion.get("activo") else None
        super().__init__(
            venta, config_negocio, nombre_impresora,
            ancho_caracteres=ancho_caracteres_por_papel(config_impresion.get("ancho_papel_mm")),
            imprimir_dos_copias=bool(config_impresion.get("imprimir_dos_copias", True)),
            parent=parent,
        )
        self.reserva = reserva
        self.setWindowTitle(f"Boleta {reserva['boleta_texto']}")

        self.btn_imprimir.setProperty("class", "secondary")
        btn_pdf = QPushButton("Guardar PDF...")
        btn_pdf.setProperty("class", "secondary")
        btn_pdf.clicked.connect(lambda: guardar_boleta_pdf(self, self.reserva))
        btn_correo = QPushButton("Enviar por correo...")
        btn_correo.setProperty("class", "success")
        btn_correo.clicked.connect(self._enviar_correo)
        self.layout_botones.insertWidget(1, btn_pdf)
        self.layout_botones.insertWidget(2, btn_correo)

    def _enviar_correo(self) -> None:
        sugerido = self.reserva.get("boleta_enviada_a") or self.reserva.get("cliente_email") or ""
        correo, aceptado = QInputDialog.getText(
            self, "Enviar boleta", "Correo del cliente:", text=sugerido)
        if aceptado:
            enviar_boleta_por_correo(self, self.reserva, correo.strip())


# ====================================================================
# Nueva reserva / editar
# ====================================================================
class ReservaDialog(QDialog):
    """Reservar una hora (o editar una reserva). Permite elegir un tipo de servicio (uno solo) y
    extras (varios), que se cobran aparte y suman su costo; quitar productos del servicio y,
    al crear, recibir un adelanto del monto que se escriba."""

    def __init__(self, fecha: date, hora: str, reserva: dict | None = None, usuario=None, parent=None):
        super().__init__(parent)
        self.reserva = reserva
        self.usuario = usuario
        self.reserva_id: int | None = reserva["id"] if reserva else None
        self.reserva_nueva_id: int | None = None  # solo si se creó una reserva nueva
        self.service = ReservaService()
        self.servicio_service = ServicioService()
        self.config = ConfiguracionService()
        self.agenda = self.config.obtener_agenda()
        self.moneda = self.config.obtener().get("moneda", "S/")
        self._cliente_id: int | None = reserva.get("cliente_id") if reserva else None
        self._clientes = ClienteService().listar(limite=1000)
        self._servicios = self.servicio_service.listar(solo_activos=True)
        if reserva and not any(s["id"] == reserva["servicio_id"] for s in self._servicios):
            actual = self.servicio_service.obtener(reserva["servicio_id"])
            if actual:
                self._servicios.append(actual)
        self._cargando = False

        self.setWindowTitle("Editar reserva" if reserva else "Nueva reserva")
        self.resize(540, 720)
        self._construir_ui(fecha, hora)
        if reserva:
            self._cargar_reserva(reserva)
        else:
            self._al_cambiar_servicio()
            self._actualizar_check_cliente()

    # ------------------------------------------------------ Interfaz ----
    def _construir_ui(self, fecha: date, hora: str) -> None:
        raiz = QVBoxLayout(self)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        contenido = QWidget()
        cuerpo = QVBoxLayout(contenido)
        cuerpo.setContentsMargins(0, 0, 8, 0)
        area.setWidget(contenido)
        raiz.addWidget(area, 1)

        formulario = QFormLayout()
        formulario.setVerticalSpacing(10)

        self.input_fecha = QDateEdit(QDate(fecha.year, fecha.month, fecha.day))
        self.input_fecha.setCalendarPopup(True)
        self.input_fecha.setDisplayFormat("dd/MM/yyyy")
        formulario.addRow("Fecha:", self.input_fecha)

        self.combo_hora = QComboBox()
        paso = self.agenda["intervalo_min"]
        for minutos in range(a_minutos(self.agenda["hora_inicio"]), a_minutos(self.agenda["hora_fin"]), paso):
            self.combo_hora.addItem(a_hhmm(minutos))
        if self.combo_hora.findText(hora) < 0:  # reserva fuera del horario actual
            self.combo_hora.addItem(hora)
        self.combo_hora.setCurrentIndex(self.combo_hora.findText(hora))
        formulario.addRow("Hora de inicio:", self.combo_hora)

        self.combo_servicio = QComboBox()
        for servicio in self._servicios:
            self.combo_servicio.addItem(servicio["nombre"], servicio)
        self.combo_servicio.currentIndexChanged.connect(self._al_cambiar_servicio)
        formulario.addRow("Servicio:", self.combo_servicio)

        self.input_duracion = QSpinBox()
        self.input_duracion.setRange(paso, 480)
        self.input_duracion.setSingleStep(paso)
        self.input_duracion.setSuffix(" min")
        formulario.addRow("Duración:", self.input_duracion)

        self.input_precio = QDoubleSpinBox()
        self.input_precio.setMaximum(999999)
        self.input_precio.setDecimals(2)
        self.input_precio.setPrefix(f"{self.moneda} ")
        self.input_precio.valueChanged.connect(self._actualizar_total)
        formulario.addRow("Precio base:", self.input_precio)

        self.combo_tipo = QComboBox()
        self.combo_tipo.currentIndexChanged.connect(self._actualizar_total)
        self.etiqueta_tipo = QLabel("Tipo de servicio:")
        formulario.addRow(self.etiqueta_tipo, self.combo_tipo)

        self.lista_efectos = QListWidget()
        self.lista_efectos.setMaximumHeight(112)
        self.lista_efectos.itemChanged.connect(self._actualizar_total)
        self.etiqueta_efectos = QLabel("Extras:")
        formulario.addRow(self.etiqueta_efectos, self.lista_efectos)

        self.lista_prod = QListWidget()
        self.lista_prod.setMaximumHeight(112)
        self.lista_prod.itemChanged.connect(self._actualizar_total)
        self.etiqueta_prod = QLabel("Productos:")
        formulario.addRow(self.etiqueta_prod, self.lista_prod)

        self.combo_cliente = QComboBox()
        self.combo_cliente.setEditable(True)
        self.combo_cliente.setInsertPolicy(QComboBox.NoInsert)
        for cliente in self._clientes:
            self.combo_cliente.addItem(cliente.nombre, cliente)
        self.combo_cliente.setCurrentIndex(-1)
        self.combo_cliente.lineEdit().setPlaceholderText("Escribe o elige un cliente")
        completador = self.combo_cliente.completer()
        completador.setFilterMode(Qt.MatchContains)
        completador.setCaseSensitivity(Qt.CaseInsensitive)
        self.combo_cliente.editTextChanged.connect(self._al_cambiar_cliente)
        formulario.addRow("Cliente:", self.combo_cliente)

        self.input_telefono = QLineEdit()
        formulario.addRow("Teléfono:", self.input_telefono)
        self.input_email = QLineEdit()
        self.input_email.setPlaceholderText("Recibe aviso de adelanto y boleta (opcional)")
        formulario.addRow("Correo:", self.input_email)
        self.input_notas = QLineEdit()
        self.input_notas.setPlaceholderText("Motivo, observaciones... (opcional)")
        formulario.addRow("Notas:", self.input_notas)
        cuerpo.addLayout(formulario)

        self.check_guardar_cliente = QCheckBox("Guardar como cliente nuevo")
        self.check_guardar_cliente.setChecked(True)
        cuerpo.addWidget(self.check_guardar_cliente)

        # --- Total y adelanto ---
        self.label_total = QLabel()
        self.label_total.setStyleSheet("font-size: 16px; font-weight: 700;")
        cuerpo.addStretch()
        raiz.addWidget(self.label_total)

        self.bloque_adelanto = QWidget()
        form_adelanto = QFormLayout(self.bloque_adelanto)
        form_adelanto.setContentsMargins(0, 0, 0, 0)
        self.input_adelanto = QDoubleSpinBox()
        self.input_adelanto.setMaximum(999999)
        self.input_adelanto.setDecimals(2)
        self.input_adelanto.setPrefix(f"{self.moneda} ")
        self.input_adelanto.setToolTip("Escribe cuánto deja el cliente ahora. Déjalo en 0 si no hay adelanto.")
        self.input_adelanto.valueChanged.connect(self._actualizar_total)
        form_adelanto.addRow("Pago recibido (adelanto o total):", self.input_adelanto)
        self.combo_metodo = QComboBox()
        for metodo in self.config.listar_metodos_pago():
            if metodo["activo"]:
                self.combo_metodo.addItem(metodo["nombre"], metodo)
        self.combo_metodo.currentIndexChanged.connect(self._actualizar_total)
        form_adelanto.addRow("Pagó con:", self.combo_metodo)
        raiz.addWidget(self.bloque_adelanto)
        self.bloque_adelanto.setVisible(self.reserva is None)

        self.label_aviso = QLabel("")
        self.label_aviso.setProperty("class", "ayuda")
        self.label_aviso.setWordWrap(True)
        raiz.addWidget(self.label_aviso)

        botones = QHBoxLayout()
        botones.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setProperty("class", "secondary")
        cancelar.clicked.connect(self.reject)
        guardar = QPushButton("Guardar cambios" if self.reserva else "Reservar")
        guardar.setProperty("class", "success")
        guardar.clicked.connect(self._guardar)
        botones.addWidget(cancelar)
        botones.addWidget(guardar)
        raiz.addLayout(botones)

    def _llenar_extras(self, servicio_id: int, marcados_sub: set | None = None,
                       marcados_prod: set | None = None) -> None:
        """Muestra los tipos de servicio, efectos y productos del servicio elegido. Por defecto
        no hay tipo ni efecto elegido y todos los productos sí; al editar se respeta lo guardado.
        Tipos y efectos se cobran aparte: nunca vienen incluidos en el precio base."""
        marcados_sub = marcados_sub or set()
        self.combo_tipo.blockSignals(True)
        self.lista_efectos.blockSignals(True)
        self.lista_prod.blockSignals(True)
        self.combo_tipo.clear()
        self.lista_efectos.clear()
        self.lista_prod.clear()

        self.combo_tipo.addItem("Ninguno", None)
        hay_tipos = False
        # Los tipos dependen del servicio, pero los efectos salen SIEMPRE (catálogo global),
        # sin importar a qué servicio se les haya vinculado.
        subs = [s for s in self.servicio_service.listar_subservicios(servicio_id, solo_activos=False)
                if s.get("clase") == CLASE_TIPO]
        subs += [o for o in self.servicio_service.listar_opciones(solo_activas=False)
                 if o.get("clase") != CLASE_TIPO]
        for sub in subs:
            if not sub["activo"] and sub["id"] not in marcados_sub:
                continue
            texto = f"{sub['nombre']}  (+{self.moneda} {sub['precio']:.2f})"
            if sub.get("clase") == CLASE_TIPO:
                hay_tipos = True
                self.combo_tipo.addItem(texto, sub)
                if sub["id"] in marcados_sub:
                    self.combo_tipo.setCurrentIndex(self.combo_tipo.count() - 1)
            else:
                item = QListWidgetItem(texto)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if sub["id"] in marcados_sub else Qt.Unchecked)
                item.setData(Qt.UserRole, sub)
                self.lista_efectos.addItem(item)

        for prod in self.servicio_service.listar_productos(servicio_id):
            detalle = (f"+{self.moneda} {prod['precio'] * prod['cantidad']:.2f}" if prod["cobrar"]
                       else "incluido")
            cantidad_txt = f"{prod['cantidad']:g} {(prod.get('unidad_medida') or '').strip()}".strip()
            item = QListWidgetItem(f"{prod['nombre']} × {cantidad_txt}  ({detalle})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            marcado = marcados_prod is None or prod["producto_id"] in marcados_prod
            item.setCheckState(Qt.Checked if marcado else Qt.Unchecked)
            item.setData(Qt.UserRole, prod)
            self.lista_prod.addItem(item)

        self.combo_tipo.blockSignals(False)
        self.lista_efectos.blockSignals(False)
        self.lista_prod.blockSignals(False)
        self.combo_tipo.setVisible(hay_tipos)
        self.etiqueta_tipo.setVisible(hay_tipos)
        # Efectos: siempre visibles en cualquier servicio.
        self.lista_efectos.setVisible(True)
        self.etiqueta_efectos.setVisible(True)
        hay_prod = self.lista_prod.count() > 0
        self.lista_prod.setVisible(hay_prod)
        self.etiqueta_prod.setVisible(hay_prod)

    def _cargar_reserva(self, r: dict) -> None:
        self._cargando = True
        for i in range(self.combo_servicio.count()):
            if self.combo_servicio.itemData(i)["id"] == r["servicio_id"]:
                self.combo_servicio.blockSignals(True)
                self.combo_servicio.setCurrentIndex(i)
                self.combo_servicio.blockSignals(False)
        self._llenar_extras(
            r["servicio_id"],
            {i["referencia_id"] for i in r["items"] if i["tipo"] == "subservicio"},
            {i["referencia_id"] for i in r["items"] if i["tipo"] == "producto"},
        )
        self.input_duracion.setValue(a_minutos(r["hora_fin"]) - a_minutos(r["hora_inicio"]))
        self.input_precio.setValue(r["precio"])
        self.combo_cliente.setEditText(r["cliente_nombre"])
        self._cliente_id = r.get("cliente_id")
        self.input_telefono.setText(r.get("cliente_telefono") or "")
        self.input_email.setText(r.get("cliente_email") or "")
        self.input_notas.setText(r.get("notas") or "")
        self._cargando = False
        self._actualizar_check_cliente()
        self._actualizar_total()

    # ------------------------------------------------------ Eventos ----
    def _al_cambiar_servicio(self) -> None:
        servicio = self.combo_servicio.currentData()
        if not servicio:
            return
        paso = self.agenda["intervalo_min"]
        # La duración se redondea hacia arriba al bloque de la agenda.
        bloques = -(-servicio["duracion_min"] // paso)
        self.input_duracion.setValue(max(paso, bloques * paso))
        self.input_precio.setValue(servicio["precio"])
        self._llenar_extras(servicio["id"])
        self._actualizar_total()

    def _ids_marcados(self, lista: QListWidget, clave: str) -> list[int]:
        return [lista.item(i).data(Qt.UserRole)[clave] for i in range(lista.count())
                if lista.item(i).checkState() == Qt.Checked]

    def _subservicio_ids(self) -> list[int]:
        """Ids de los efectos marcados (varios) más el tipo de servicio elegido (uno solo)."""
        ids = self._ids_marcados(self.lista_efectos, "id")
        tipo = self.combo_tipo.currentData()
        if tipo:
            ids.append(tipo["id"])
        return ids

    def _total(self) -> float:
        total = self.input_precio.value()
        tipo = self.combo_tipo.currentData()
        if tipo:
            total += tipo["precio"]
        for i in range(self.lista_efectos.count()):
            if self.lista_efectos.item(i).checkState() == Qt.Checked:
                total += self.lista_efectos.item(i).data(Qt.UserRole)["precio"]
        for i in range(self.lista_prod.count()):
            item = self.lista_prod.item(i)
            prod = item.data(Qt.UserRole)
            if item.checkState() == Qt.Checked and prod["cobrar"]:
                total += prod["precio"] * prod["cantidad"]
        return round(total, 2)

    def _actualizar_total(self, *_) -> None:
        if self._cargando:
            return
        total = self._total()
        texto = f"Total: {formatear_moneda(total, self.moneda)}"
        if self.reserva is None:
            self.input_adelanto.blockSignals(True)
            self.input_adelanto.setMaximum(max(total, 0.0))
            self.input_adelanto.blockSignals(False)
            adelanto = self.input_adelanto.value()
            self.combo_metodo.setEnabled(adelanto > 0)
            if adelanto > 0:
                texto += f"   ·   Adelanto: {formatear_moneda(adelanto, self.moneda)}   ·   Saldo: {formatear_moneda(total - adelanto, self.moneda)}"
                metodo = self.combo_metodo.currentData()
                if metodo and metodo.get("es_efectivo"):
                    self.label_aviso.setText("El adelanto en efectivo entra a la caja abierta.")
                else:
                    self.label_aviso.setText("")
            else:
                self.label_aviso.setText("")
        else:
            recibido = self.reserva.get("adelanto_total", 0)
            if recibido:
                texto += f"   ·   Adelantos recibidos: {formatear_moneda(recibido, self.moneda)}"
        self.label_total.setText(texto)

    def _cliente_por_nombre(self, texto: str):
        texto = texto.strip().lower()
        for cliente in self._clientes:
            if cliente.nombre.strip().lower() == texto:
                return cliente
        return None

    def _al_cambiar_cliente(self, texto: str) -> None:
        cliente = self._cliente_por_nombre(texto)
        self._cliente_id = cliente.id if cliente else None
        if cliente:
            if not self.input_telefono.text().strip():
                self.input_telefono.setText(cliente.telefono or "")
            if not self.input_email.text().strip():
                self.input_email.setText(cliente.email or "")
        self._actualizar_check_cliente()

    def _actualizar_check_cliente(self) -> None:
        self.check_guardar_cliente.setVisible(
            self._cliente_id is None and bool(self.combo_cliente.currentText().strip()))

    # ------------------------------------------------------ Guardar ----
    def _guardar(self) -> None:
        if self.combo_servicio.count() == 0:
            QMessageBox.warning(self, "Falta un servicio",
                                "Primero crea al menos un servicio en el menú «Servicios».")
            return
        datos = dict(
            fecha=self.input_fecha.date().toString("yyyy-MM-dd"),
            hora_inicio=self.combo_hora.currentText(),
            duracion_min=self.input_duracion.value(),
            servicio_id=self.combo_servicio.currentData()["id"],
            precio=self.input_precio.value(),
            cliente_nombre=self.combo_cliente.currentText(),
            cliente_telefono=self.input_telefono.text(),
            cliente_email=self.input_email.text(),
            notas=self.input_notas.text(),
            cliente_id=self._cliente_id,
            guardar_cliente=self.check_guardar_cliente.isChecked(),
            subservicio_ids=self._subservicio_ids(),
            producto_ids=self._ids_marcados(self.lista_prod, "producto_id"),
        )
        try:
            if self.reserva_id:
                self.service.actualizar(self.reserva_id, **datos)
            else:
                adelanto = self.input_adelanto.value()
                metodo = self.combo_metodo.currentData()
                self.reserva_id = self.service.crear(
                    **datos, adelanto=adelanto,
                    adelanto_metodo_id=metodo["id"] if metodo else None,
                    usuario_id=self.usuario.id if self.usuario else None)
        except ReservaError as e:
            QMessageBox.warning(self, "No se pudo guardar la reserva", str(e))
            return
        if not self.reserva:
            # Reserva nueva: la agenda enviará el comprobante en PDF cuando este diálogo ya se cerró.
            self.reserva_nueva_id = self.reserva_id
        self.accept()


# ====================================================================
# Cobrar
# ====================================================================
class CobrarDialog(QDialog):
    """Cobra la reserva. Muestra el desglose, descuenta los adelantos ya recibidos y
    cobra solo el saldo."""

    def __init__(self, reserva: dict, usuario, parent=None):
        super().__init__(parent)
        self.reserva = reserva
        self.usuario = usuario
        self.service = ReservaService()
        self.resultado: dict | None = None
        self.enviar_correo_a: str | None = None
        config = ConfiguracionService()
        self.moneda = config.obtener().get("moneda", "S/")
        self._caja_abierta = bool(CajaService().estado_actual(usuario.id).get("abierta"))
        self._subtotal = reserva["total_estimado"]
        self._adelantos = reserva["adelanto_total"]

        self.setWindowTitle("Marcar como atendida y cobrar el saldo")
        self.resize(440, 480)
        raiz = QVBoxLayout(self)

        raiz.addWidget(QLabel(f"<b>{reserva['cliente_nombre']}</b><br>{reserva['servicio_nombre']} · "
                              f"{reserva['hora_inicio']} a {reserva['hora_fin']}"))

        # Desglose de lo que se cobra
        desglose = QGridLayout()
        desglose.setHorizontalSpacing(12)
        for i, linea in enumerate(ReservaService.lineas_boleta(reserva)):
            cantidad = f" × {linea['cantidad']:g}" if linea["cantidad"] != 1 else ""
            desglose.addWidget(QLabel(f"{linea['nombre']}{cantidad}"), i, 0)
            importe = QLabel(formatear_moneda(linea["subtotal"], self.moneda))
            importe.setAlignment(Qt.AlignRight)
            desglose.addWidget(importe, i, 1)
        desglose.setColumnStretch(0, 1)
        raiz.addSpacing(6)
        raiz.addLayout(desglose)

        formulario = QFormLayout()
        formulario.setVerticalSpacing(10)
        self.input_descuento = QDoubleSpinBox()
        self.input_descuento.setMaximum(self._subtotal)
        self.input_descuento.setDecimals(2)
        self.input_descuento.setPrefix(f"{self.moneda} ")
        self.input_descuento.valueChanged.connect(self._actualizar)
        formulario.addRow("Descuento:", self.input_descuento)

        self.combo_metodo = QComboBox()
        for metodo in config.listar_metodos_pago():
            if metodo["activo"]:
                self.combo_metodo.addItem(metodo["nombre"], metodo)
        self.combo_metodo.currentIndexChanged.connect(self._actualizar)
        formulario.addRow("Método de pago del saldo:", self.combo_metodo)

        # Solo en efectivo: con cuánto paga el cliente, para mostrar el cambio (vuelto) en la boleta.
        self._pide_recibido = False
        self.label_recibido = QLabel("El cliente paga con:")
        self.input_recibido = QDoubleSpinBox()
        self.input_recibido.setDecimals(2)
        self.input_recibido.setMaximum(99999)
        self.input_recibido.setPrefix(f"{self.moneda} ")
        self.input_recibido.setSpecialValueText("Monto exacto (sin cambio)")
        self.input_recibido.valueChanged.connect(self._actualizar)
        formulario.addRow(self.label_recibido, self.input_recibido)
        raiz.addLayout(formulario)

        self.label_total = QLabel()
        self.label_total.setTextFormat(Qt.RichText)
        raiz.addWidget(self.label_total)

        self.label_aviso = QLabel("")
        self.label_aviso.setProperty("class", "badgeDanger")
        self.label_aviso.setWordWrap(True)
        raiz.addWidget(self.label_aviso)

        email = (reserva.get("cliente_email") or "").strip()
        self.check_correo = QCheckBox(f"Enviar la boleta a {email}" if email else "Enviar la boleta por correo")
        self.check_correo.setEnabled(bool(email))
        if email:
            self.check_correo.setChecked(correo_service.correo_configurado())
            if not correo_service.correo_configurado():
                self.check_correo.setText(self.check_correo.text() + " (configura el correo primero)")
                self.check_correo.setEnabled(False)
        else:
            self.check_correo.setToolTip("La reserva no tiene correo. Puedes enviarla después desde la boleta.")
        raiz.addWidget(self.check_correo)
        raiz.addStretch()

        botones = QHBoxLayout()
        botones.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setProperty("class", "secondary")
        cancelar.clicked.connect(self.reject)
        self.btn_cobrar = QPushButton("Cobrar saldo y marcar atendida")
        self.btn_cobrar.setProperty("class", "success")
        self.btn_cobrar.clicked.connect(self._cobrar)
        botones.addWidget(cancelar)
        botones.addWidget(self.btn_cobrar)
        raiz.addLayout(botones)
        self._actualizar()

    def _actualizar(self) -> None:
        total = round(self._subtotal - self.input_descuento.value(), 2)
        saldo = round(total - self._adelantos, 2)
        texto = f"<span style='font-size:15px'>Total: <b>{formatear_moneda(total, self.moneda)}</b></span>"
        if self._adelantos > 0:
            texto += (f"<br>Adelantos recibidos: -{formatear_moneda(self._adelantos, self.moneda)}")
        texto += (f"<br><span style='font-size:22px; font-weight:700'>Saldo a cobrar: "
                  f"{formatear_moneda(max(saldo, 0), self.moneda)}</span>")
        self.label_total.setText(texto)

        necesita_pago = saldo > 0
        self.combo_metodo.setEnabled(necesita_pago and self.combo_metodo.count() > 0)
        metodo = self.combo_metodo.currentData()
        self._pide_recibido = bool(necesita_pago and metodo and metodo.get("es_efectivo"))
        self.label_recibido.setVisible(self._pide_recibido)
        self.input_recibido.setVisible(self._pide_recibido)
        recibido = self.input_recibido.value() if self._pide_recibido else 0.0
        aviso = ""
        if saldo < 0:
            aviso = "El descuento deja el total por debajo de los adelantos recibidos. Baja el descuento."
        elif necesita_pago and metodo and metodo.get("es_efectivo") and not self._caja_abierta:
            aviso = "Abre la caja (menú Caja) para poder cobrar en efectivo."
        elif recibido > 0 and recibido + 0.001 < saldo:
            aviso = "El monto con el que paga el cliente no alcanza para el saldo."
        if recibido > 0 and recibido + 0.001 >= saldo:
            texto += (f"<br><span style='font-size:15px'>Recibido: {formatear_moneda(recibido, self.moneda)}"
                      f" · <b>Cambio: {formatear_moneda(recibido - saldo, self.moneda)}</b></span>")
            self.label_total.setText(texto)
        self.label_aviso.setText(aviso)
        self.label_aviso.setVisible(bool(aviso))
        self.btn_cobrar.setEnabled(not aviso and (not necesita_pago or self.combo_metodo.count() > 0))

    def _cobrar(self) -> None:
        saldo = round(self._subtotal - self.input_descuento.value() - self._adelantos, 2)
        metodo = self.combo_metodo.currentData() if saldo > 0 else None
        try:
            recibido = self.input_recibido.value() if self._pide_recibido else 0.0
            self.resultado = self.service.cobrar(
                self.reserva["id"], self.usuario.id, metodo["id"] if metodo else None,
                self.input_descuento.value(), recibido if recibido > 0 else None)
        except ReservaError as e:
            QMessageBox.warning(self, "No se pudo cobrar", str(e))
            return
        if self.check_correo.isChecked():
            self.enviar_correo_a = self.reserva["cliente_email"].strip()
        self.accept()


class AdelantoDialog(QDialog):
    """Recibir un pago a cuenta (adelanto o el total): el monto lo escribe el negocio, hasta lo que falta.
    Pagar no marca la cita como atendida."""

    def __init__(self, reserva: dict, usuario, parent=None):
        super().__init__(parent)
        self.reserva = reserva
        self.usuario = usuario
        self.service = ReservaService()
        config = ConfiguracionService()
        self.moneda = config.obtener().get("moneda", "S/")
        falta = round(reserva["total_estimado"] - reserva["adelanto_total"], 2)
        self.setWindowTitle("Recibir pago")
        self.setMinimumWidth(380)

        raiz = QVBoxLayout(self)
        raiz.addWidget(QLabel(
            f"<b>{reserva['cliente_nombre']}</b> · {reserva['servicio_nombre']}<br>"
            f"Total: {formatear_moneda(reserva['total_estimado'], self.moneda)} · "
            f"Ya adelantó: {formatear_moneda(reserva['adelanto_total'], self.moneda)} · "
            f"<b>Falta: {formatear_moneda(falta, self.moneda)}</b>"))

        formulario = QFormLayout()
        self.input_monto = QDoubleSpinBox()
        self.input_monto.setRange(0.0, max(falta, 0.0))
        self.input_monto.setDecimals(2)
        self.input_monto.setPrefix(f"{self.moneda} ")
        formulario.addRow("Monto recibido:", self.input_monto)
        self.combo_metodo = QComboBox()
        for metodo in config.listar_metodos_pago():
            if metodo["activo"]:
                self.combo_metodo.addItem(metodo["nombre"], metodo)
        formulario.addRow("Pagó con:", self.combo_metodo)
        raiz.addLayout(formulario)

        botones = QHBoxLayout()
        botones.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setProperty("class", "secondary")
        cancelar.clicked.connect(self.reject)
        guardar = QPushButton("Registrar pago")
        guardar.setProperty("class", "success")
        guardar.clicked.connect(self._guardar)
        botones.addWidget(cancelar)
        botones.addWidget(guardar)
        raiz.addLayout(botones)

    def _guardar(self) -> None:
        metodo = self.combo_metodo.currentData()
        try:
            self.service.registrar_adelanto(self.reserva["id"], self.input_monto.value(),
                                            metodo["id"] if metodo else None, self.usuario.id)
        except ReservaError as e:
            QMessageBox.warning(self, "No se pudo registrar el adelanto", str(e))
            return
        avisar_adelanto_por_correo(self.reserva["id"], self.input_monto.value())
        self.accept()


# ====================================================================
# Detalle de una reserva
# ====================================================================
class DetalleReservaDialog(QDialog):
    """Resumen de una reserva con las acciones que corresponden a su estado."""

    def __init__(self, reserva_id: int, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.service = ReservaService()
        self.reserva_id = reserva_id
        self.cambio = False  # True si algo cambió y la agenda debe refrescarse
        self.setWindowTitle("Reserva")
        self.setMinimumWidth(600)
        self.resize(640, 780)
        self._raiz = QVBoxLayout(self)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        contenido = QWidget()
        self._cuerpo = QVBoxLayout(contenido)
        self._cuerpo.setContentsMargins(0, 0, 8, 0)
        self._cuerpo.setSpacing(ESPACIO_MD)
        area.setWidget(contenido)
        self._raiz.addWidget(area, 1)
        self._botones = QVBoxLayout()
        self._botones.setSpacing(ESPACIO_SM)
        self._raiz.addLayout(self._botones)
        self._construir()

    # ------------------------------------------------ Piezas de la vista ----
    @staticmethod
    def _dato(titulo: str, valor: str, grande: bool = False) -> QWidget:
        """Un dato con su título pequeño arriba y el valor debajo."""
        caja = QWidget()
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        etiqueta = QLabel(titulo.upper())
        etiqueta.setProperty("class", "ayuda")
        texto = QLabel(valor)
        texto.setWordWrap(True)
        texto.setTextInteractionFlags(Qt.TextSelectableByMouse)
        texto.setStyleSheet(f"font-size: {17 if grande else 13}px; font-weight: 700;")
        lay.addWidget(etiqueta)
        lay.addWidget(texto)
        return caja

    @staticmethod
    def _tabla(columnas: list[str], filas: list[list[str]], derecha=()) -> QTableWidget:
        """Tabla de solo lectura, sin scroll, que mide justo lo que ocupan sus filas."""
        tabla = QTableWidget(len(filas), len(columnas))
        tabla.setHorizontalHeaderLabels(columnas)
        configurar_tabla_erp(tabla, derecha=derecha, altura_fila=34)
        tabla.setSelectionMode(QTableWidget.NoSelection)
        tabla.setFocusPolicy(Qt.NoFocus)
        tabla.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for i, fila in enumerate(filas):
            for j, texto in enumerate(fila):
                tabla.setItem(i, j, item_derecha(str(texto)) if j in derecha
                              else QTableWidgetItem(str(texto)))
        encabezado = tabla.horizontalHeader()
        encabezado.setFixedHeight(34)
        encabezado.setSectionResizeMode(0, QHeaderView.Stretch)
        for j in range(1, len(columnas)):
            encabezado.setSectionResizeMode(j, QHeaderView.ResizeToContents)
        tabla.setFixedHeight(34 + 34 * len(filas) + 4)
        return tabla

    def _estado_correo(self, titulo: str, insignia: StatusBadge, detalle: str, boton=None) -> QWidget:
        fila = QWidget()
        lay = QHBoxLayout(fila)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACIO_SM)
        nombre = QLabel(titulo)
        nombre.setStyleSheet("font-weight: 600;")
        nombre.setMinimumWidth(170)
        lay.addWidget(nombre)
        lay.addWidget(insignia)
        info = QLabel(detalle)
        info.setProperty("class", "ayuda")
        info.setWordWrap(True)
        lay.addWidget(info, 1)
        if boton:
            lay.addWidget(boton)
        return fila

    def _construir(self) -> None:
        self._vaciar(self._cuerpo)
        self._vaciar(self._botones)

        r = self.service.obtener(self.reserva_id)
        if not r:
            QMessageBox.warning(self, "Reserva", "La reserva ya no existe.")
            self.reject()
            return
        self.reserva = r
        moneda = ConfiguracionService().obtener().get("moneda", "S/")
        dinero = lambda valor: formatear_moneda(valor, moneda)  # noqa: E731
        atendida = r["estado"] == ESTADO_ATENDIDA
        total, pagado, saldo = r["total_estimado"], r["adelanto_total"], r["saldo_estimado"]
        correo = (r.get("cliente_email") or "").strip()

        # --- Cabecera: cliente, servicio y estado ---
        cabecera = QHBoxLayout()
        bloque = QVBoxLayout()
        bloque.setSpacing(2)
        titulo = QLabel(r["cliente_nombre"])
        titulo.setStyleSheet("font-size: 22px; font-weight: 700;")
        servicio = QLabel(r["servicio_nombre"])
        servicio.setProperty("class", "ayuda")
        bloque.addWidget(titulo)
        bloque.addWidget(servicio)
        cabecera.addLayout(bloque, 1)
        estado = {
            ESTADO_RESERVADA: ("Reservada", "info"),
            ESTADO_ATENDIDA: ("Atendida", "ok"),
            ESTADO_NO_ASISTIO: ("No asistió", "warning"),
        }.get(r["estado"], (r["estado"], "neutral"))
        insignias = QHBoxLayout()
        insignias.setSpacing(ESPACIO_SM)
        if not atendida:
            if self._pagada_completa(r):
                insignias.addWidget(StatusBadge("Pagado completo", "ok"))
            elif pagado > 0:
                insignias.addWidget(StatusBadge(f"Saldo {dinero(saldo)}", "warning"))
            else:
                insignias.addWidget(StatusBadge("Sin pagos", "neutral"))
        insignias.addWidget(StatusBadge(*estado))
        cabecera.addLayout(insignias)
        self._cuerpo.addLayout(cabecera)

        # --- Cuándo: fecha, hora y duración ---
        dia = parsear_fecha(r["fecha"])
        minutos = a_minutos(r["hora_fin"]) - a_minutos(r["hora_inicio"])
        duracion = (f"{minutos // 60} h" + (f" {minutos % 60} min" if minutos % 60 else "")) if minutos >= 60 \
            else f"{minutos} min"
        fila_cuando = QHBoxLayout()
        fila_cuando.setSpacing(ESPACIO_SM + 4)
        for nombre, valor in (("Fecha", f"{DIAS_CORTOS[dia.weekday()]} {fecha_dmy(dia)}"),
                              ("Hora", f"{r['hora_inicio']} – {r['hora_fin']}"),
                              ("Duración", duracion)):
            tarjeta = Card(margen=ESPACIO_SM + 4)
            tarjeta.cuerpo.addWidget(self._dato(nombre, valor, grande=True))
            fila_cuando.addWidget(tarjeta, 1)
        self._cuerpo.addLayout(fila_cuando)

        # --- Cliente ---
        tarjeta = Card("Cliente")
        grilla = QGridLayout()
        grilla.setHorizontalSpacing(24)
        grilla.setVerticalSpacing(ESPACIO_SM + 4)
        grilla.addWidget(self._dato("Teléfono", r.get("cliente_telefono") or "—"), 0, 0)
        grilla.addWidget(self._dato("Correo", correo or "—"), 0, 1)
        if r.get("notas"):
            grilla.addWidget(self._dato("Notas", r["notas"]), 1, 0, 1, 2)
        grilla.setColumnStretch(0, 1)
        grilla.setColumnStretch(1, 2)
        tarjeta.cuerpo.addLayout(grilla)
        self._cuerpo.addWidget(tarjeta)

        # --- Detalle del servicio ---
        tarjeta = Card("Detalle del servicio")
        filas = [[r["servicio_nombre"], "Servicio", dinero(r["precio"])]]
        for item in r["items"]:
            cantidad = f" × {item['cantidad']:g}" if item["cantidad"] != 1 else ""
            tipo = "Sub-servicio" if item["tipo"] == "subservicio" else "Producto"
            costo = dinero(item["subtotal"]) if item["subtotal"] > 0 else "Incluido"
            filas.append([f"{item['nombre']}{cantidad}", tipo, costo])
        tarjeta.cuerpo.addWidget(self._tabla(["Concepto", "Tipo", "Importe"], filas, derecha=(2,)))
        fila_total = QHBoxLayout()
        fila_total.addStretch()
        fila_total.addWidget(QLabel("Total"))
        monto_total = QLabel(dinero(total))
        monto_total.setStyleSheet("font-size: 18px; font-weight: 700;")
        fila_total.addWidget(monto_total)
        tarjeta.cuerpo.addLayout(fila_total)
        self._cuerpo.addWidget(tarjeta)

        # --- Pagos ---
        tarjeta = Card("Pagos")
        if atendida:
            tarjeta.agregar_accion(StatusBadge(f"Boleta {r['boleta_texto']}", "ok"))
        if r["pagos"]:
            hay_estados = any(p["estado"] != "vigente" for p in r["pagos"])
            columnas = ["Fecha", "Método", "Monto"] + (["Estado"] if hay_estados else [])
            filas = []
            for p in r["pagos"]:
                fecha = p.get("fecha") or ""
                cuando = f"{fecha_dmy(parsear_fecha(fecha))} {fecha[11:16]}" if fecha else "—"
                fila = [cuando, p["metodo_nombre"] or "—", dinero(p["monto"])]
                if hay_estados:
                    fila.append({"vigente": "Vigente", "devuelto": "Devuelto",
                                 "retenido": "Retenido"}.get(p["estado"], p["estado"]))
                filas.append(fila)
            tarjeta.cuerpo.addWidget(self._tabla(columnas, filas, derecha=(2,)))
        else:
            vacio = QLabel("Todavía no hay pagos registrados.")
            vacio.setProperty("class", "ayuda")
            tarjeta.cuerpo.addWidget(vacio)
        resumen = QHBoxLayout()
        resumen.setSpacing(ESPACIO_MD)
        if atendida:
            datos = [("Total cobrado", dinero(r["total"])),
                     ("Adelantos aplicados", dinero(r.get("adelanto_aplicado") or 0)),
                     ("Saldo pagado", f"{dinero(r['total'] - (r.get('adelanto_aplicado') or 0))}"
                                      f" ({r['metodo_pago'] or '—'})")]
        else:
            datos = [("Total", dinero(total)), ("Pagado", dinero(pagado)),
                     ("Saldo por pagar", dinero(saldo))]
        for nombre, valor in datos:
            resumen.addWidget(self._dato(nombre, valor), 1)
        tarjeta.cuerpo.addLayout(resumen)
        self._cuerpo.addWidget(tarjeta)

        # --- Correos al cliente ---
        tarjeta = Card("Correos al cliente")
        boton_reenviar = None
        if correo:
            comprobante_a = (r.get("comprobante_enviado_a") or "").strip()
            if comprobante_a:
                insignia = StatusBadge("Enviado", "ok")
                detalle = comprobante_a
            else:
                insignia = StatusBadge("No enviado", "warning")
                detalle = correo
            if not atendida and r["estado"] == ESTADO_RESERVADA:
                boton_reenviar = QPushButton("Reenviar" if comprobante_a else "Enviar ahora")
                boton_reenviar.setProperty("class", "secondary")
                boton_reenviar.clicked.connect(self._enviar_comprobante)
            tarjeta.cuerpo.addWidget(self._estado_correo(
                "Comprobante de reserva", insignia, detalle, boton_reenviar))
            if atendida:
                enviada = (r.get("boleta_enviada_a") or "").strip()
                tarjeta.cuerpo.addWidget(self._estado_correo(
                    "Boleta final",
                    StatusBadge("Enviada", "ok") if enviada else StatusBadge("No enviada", "warning"),
                    enviada or "Puedes enviarla con «Enviar por correo»."))
            else:
                tarjeta.cuerpo.addWidget(self._estado_correo(
                    "Boleta final", StatusBadge("Pendiente", "neutral"),
                    "Se envía al marcar la cita como atendida."))
        else:
            sin_correo = QLabel("Esta reserva no tiene correo: no se envían comprobantes ni boleta.")
            sin_correo.setProperty("class", "ayuda")
            sin_correo.setWordWrap(True)
            tarjeta.cuerpo.addWidget(sin_correo)
        self._cuerpo.addWidget(tarjeta)
        self._cuerpo.addStretch()

        # --- Botones: acciones principales arriba; secundarias y «Cerrar» abajo ---
        fila_a, fila_b = QHBoxLayout(), QHBoxLayout()
        fila_a.setSpacing(8)
        fila_b.setSpacing(8)

        def boton(texto, clase, funcion, fila=fila_a):
            b = QPushButton(texto)
            b.setProperty("class", clase)
            b.clicked.connect(funcion)
            fila.addWidget(b)
            return b

        if r["estado"] == ESTADO_ATENDIDA:
            boton("Ver boleta", "success", self._ver_boleta)
            boton("Guardar PDF...", "secondary", lambda: guardar_boleta_pdf(self, self.reserva))
            boton("Enviar por correo...", "secondary", self._enviar_correo)
        else:
            if r["estado"] == ESTADO_RESERVADA:
                boton("Marcar como atendida", "success", self._marcar_atendida)
            else:
                boton("Volver a reservada", "success", lambda: self._estado(ESTADO_RESERVADA))
            if r["saldo_estimado"] > 0:
                boton("Recibir pago", "secondary", self._adelanto)
            boton("Editar", "secondary", self._editar)
            if r["estado"] == ESTADO_RESERVADA:
                boton("No asistió", "secondary", lambda: self._estado(ESTADO_NO_ASISTIO), fila_b)
            boton("Cancelar reserva", "danger", self._cancelar, fila_b)
        fila_a.addStretch()
        fila_b.addStretch()
        boton("Cerrar", "secondary", self.accept, fila_b if r["estado"] != ESTADO_ATENDIDA else fila_a)
        self._botones.addLayout(fila_a)
        if fila_b.count() > 1:
            self._botones.addLayout(fila_b)

    def _enviar_comprobante(self) -> None:
        """Envía (o reenvía) el comprobante de la reserva y refresca el estado al terminar."""
        def refrescar() -> None:
            if isValid(self):
                self._construir()
        enviar_comprobante_reserva_por_correo(self.reserva_id, al_terminar=refrescar)
        QMessageBox.information(self, "Enviando comprobante",
                                "Enviando el comprobante... Esta pantalla se actualizará al terminar.")

    def _vaciar(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)  # desaparece ya; deleteLater lo libera después
                widget.deleteLater()
            elif item.layout():
                self._vaciar(item.layout())

    @staticmethod
    def _pagada_completa(r: dict) -> bool:
        """El cliente ya pagó todo por adelantado: no hay saldo, pero la cita sigue pendiente
        hasta que el negocio confirme que el servicio se realizó."""
        return r["adelanto_total"] > 0 and r["saldo_estimado"] <= 0

    # ----------------------------------------------------- Acciones ----
    def _marcar_atendida(self) -> None:
        """El negocio confirma que el servicio ya se realizó. Pagar (adelanto o total) no
        marca la cita como atendida: eso se valida aquí. Si todavía debe saldo se abre el
        cobro; si ya pagó todo se confirma y se genera la boleta final, que se envía por
        correo si el cliente tiene uno."""
        r = self.reserva
        if r["saldo_estimado"] > 0:
            self._cobrar()  # todavía debe saldo: se cobra y recién ahí queda atendida
            return
        confirmacion = QMessageBox.question(
            self, "Marcar como atendida",
            f"¿Confirmas que {r['cliente_nombre']} ya fue atendida?\n\n"
            "Se generará su boleta final"
            + (" y se enviará a su correo." if (r.get("cliente_email") or "").strip() else "."),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirmacion != QMessageBox.Yes:
            return
        try:
            reserva = self.service.cobrar(r["id"], self.usuario.id, None)
        except ReservaError as e:
            QMessageBox.warning(self, "No se pudo marcar como atendida", str(e))
            return
        self.cambio = True
        correo = (reserva.get("cliente_email") or "").strip()
        if correo and correo_service.correo_configurado():
            enviar_boleta_por_correo(self, reserva, correo)
        BoletaDialog(reserva, self).exec()
        self._construir()

    def _cobrar(self) -> None:
        dialogo = CobrarDialog(self.reserva, self.usuario, self)
        if dialogo.exec() != QDialog.Accepted:
            return
        self.cambio = True
        reserva = dialogo.resultado
        if dialogo.enviar_correo_a:
            enviar_boleta_por_correo(self, reserva, dialogo.enviar_correo_a)
        BoletaDialog(reserva, self).exec()
        self._construir()

    def _ver_boleta(self) -> None:
        BoletaDialog(self.reserva, self).exec()
        self._construir()  # por si se envió por correo desde la vista

    def _enviar_correo(self) -> None:
        sugerido = self.reserva.get("boleta_enviada_a") or self.reserva.get("cliente_email") or ""
        correo, aceptado = QInputDialog.getText(self, "Enviar boleta", "Correo del cliente:", text=sugerido)
        if aceptado:
            enviar_boleta_por_correo(self, self.reserva, correo.strip())

    def _editar(self) -> None:
        r = self.reserva
        dialogo = ReservaDialog(parsear_fecha(r["fecha"]), r["hora_inicio"], r, self.usuario, self)
        if dialogo.exec() == QDialog.Accepted:
            self.cambio = True
            self._construir()

    def _estado(self, estado: str) -> None:
        try:
            self.service.cambiar_estado(self.reserva_id, estado)
        except ReservaError as e:
            QMessageBox.warning(self, "No se pudo cambiar el estado", str(e))
            return
        self.cambio = True
        self._construir()

    def _adelanto(self) -> None:
        if AdelantoDialog(self.reserva, self.usuario, self).exec() == QDialog.Accepted:
            self.cambio = True
            self._construir()

    def _cancelar(self) -> None:
        r = self.reserva
        devolver = False
        if r["adelanto_total"] > 0:
            monto = formatear_moneda(r["adelanto_total"], ConfiguracionService().obtener().get("moneda", "S/"))
            caja = QMessageBox(self)
            caja.setIcon(QMessageBox.Question)
            caja.setWindowTitle("Cancelar reserva con adelanto")
            caja.setText(f"{r['cliente_nombre']} ya dejó {monto} de adelanto.\n\n"
                         "¿Qué hacemos con ese dinero al cancelar la reserva?")
            btn_devolver = caja.addButton("Devolver adelanto", QMessageBox.AcceptRole)
            btn_retener = caja.addButton("Retener adelanto", QMessageBox.DestructiveRole)
            caja.addButton("No cancelar", QMessageBox.RejectRole)
            caja.exec()
            if caja.clickedButton() is btn_devolver:
                devolver = True
            elif caja.clickedButton() is not btn_retener:
                return
        elif QMessageBox.question(
            self, "Cancelar reserva",
            f"¿Cancelar la reserva de {r['cliente_nombre']} ({r['hora_inicio']})?\n"
            "La hora quedará libre en la agenda.",
        ) != QMessageBox.Yes:
            return
        try:
            self.service.cancelar(self.reserva_id, self.usuario.id, devolver)
        except ReservaError as e:
            QMessageBox.warning(self, "No se pudo cancelar", str(e))
            return
        self.cambio = True
        self.accept()
