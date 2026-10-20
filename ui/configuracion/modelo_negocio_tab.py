"""Pestaña "Modelo de negocio" de Configuración.

Permite elegir entre:
  - Ventas de productos: el sistema de siempre (catálogo, stock, ventas, compras).
  - Servicios con reserva: el menú suma una Agenda semanal por horas (el Inicio sigue siendo el dashboard);
    el cliente reserva su hora, el negocio cobra y genera su boleta (PDF o correo).

Cambiar de modelo NO borra nada: solo cambia el menú.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QRadioButton,
    QComboBox, QCheckBox, QMessageBox,
)

from services.configuracion_service import (
    ConfiguracionService, ConfiguracionError, MODELO_VENTAS, MODELO_SERVICIOS,
    INTERVALOS_AGENDA_MIN,
)
from services.reserva_service import ReservaService
from ui.tokens import ESPACIO_SM, ESPACIO_MD
from ui.widgets.card import Card
from utils.fechas import DIAS_SEMANA, a_hhmm


def _horas_disponibles() -> list[str]:
    """De 05:00 a 23:30, cada 30 minutos."""
    return [a_hhmm(m) for m in range(5 * 60, 24 * 60, 30)]


class ModeloNegocioTab(QWidget):

    # Se emite con el modelo elegido ('ventas' | 'servicios') después de guardar.
    modelo_cambiado = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_service = ConfiguracionService()
        self._construir_ui()
        self.cargar()

    # ------------------------------------------------------ Interfaz ----
    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, ESPACIO_MD, 0, 0)
        raiz.setSpacing(ESPACIO_MD)

        tarjeta_modelo = Card("¿Cómo trabaja tu negocio?")
        self.radio_ventas = QRadioButton("Ventas de productos")
        self.radio_servicios = QRadioButton("Servicios con reserva")
        for radio, ayuda in (
            (self.radio_ventas,
             "Tienes un catálogo de productos con stock. Vendes en mostrador, compras a "
             "proveedores y controlas el inventario."),
            (self.radio_servicios,
             "Solo vendes servicios (consultorio, salón, taller, clases...). Tienes una "
             "Agenda semanal por horas (el Inicio sigue mostrando tu dashboard): el cliente reserva su hora, tú cobras y generas su "
             "boleta para enviarla por correo o en PDF."),
        ):
            radio.toggled.connect(self._actualizar_visibilidad)
            tarjeta_modelo.cuerpo.addWidget(radio)
            etiqueta = QLabel(ayuda)
            etiqueta.setProperty("class", "ayuda")
            etiqueta.setWordWrap(True)
            etiqueta.setContentsMargins(26, 0, 0, ESPACIO_SM)
            tarjeta_modelo.cuerpo.addWidget(etiqueta)
        raiz.addWidget(tarjeta_modelo)

        # --- Horario de atención (solo se muestra con el modelo de servicios) ---
        self.tarjeta_agenda = Card("Horario de atención de la agenda")
        formulario = QFormLayout()
        formulario.setHorizontalSpacing(ESPACIO_MD)

        horas = _horas_disponibles()
        self.combo_apertura = QComboBox()
        self.combo_apertura.addItems(horas)
        self.combo_cierre = QComboBox()
        self.combo_cierre.addItems(horas + ["24:00"])
        self.combo_intervalo = QComboBox()
        for minutos in INTERVALOS_AGENDA_MIN:
            self.combo_intervalo.addItem(f"{minutos} minutos", minutos)

        formulario.addRow("Abre a las:", self.combo_apertura)
        formulario.addRow("Cierra a las:", self.combo_cierre)
        formulario.addRow("Cada reserva se mide en bloques de:", self.combo_intervalo)

        fila_dias = QHBoxLayout()
        fila_dias.setSpacing(ESPACIO_MD)
        self.checks_dias: list[QCheckBox] = []
        for nombre in DIAS_SEMANA:
            check = QCheckBox(nombre.capitalize())
            self.checks_dias.append(check)
            fila_dias.addWidget(check)
        fila_dias.addStretch()
        formulario.addRow("Días de atención:", fila_dias)
        self.tarjeta_agenda.cuerpo.addLayout(formulario)

        ayuda_agenda = QLabel(
            "Las filas de la agenda salen de este horario. Si ya hay reservas fuera de él "
            "(por ejemplo, de antes de cambiarlo), se siguen mostrando."
        )
        ayuda_agenda.setProperty("class", "ayuda")
        ayuda_agenda.setWordWrap(True)
        self.tarjeta_agenda.cuerpo.addWidget(ayuda_agenda)
        raiz.addWidget(self.tarjeta_agenda)

        # --- Guardar ---
        pie = QHBoxLayout()
        self.btn_guardar = QPushButton("Guardar modelo de negocio")
        self.btn_guardar.setProperty("class", "success")
        self.btn_guardar.clicked.connect(self._guardar)
        pie.addWidget(self.btn_guardar)
        nota = QLabel("Al cambiar de modelo no se borra nada: tus productos, ventas, "
                      "clientes y reservas se conservan.")
        nota.setProperty("class", "ayuda")
        nota.setWordWrap(True)
        pie.addWidget(nota, 1)
        raiz.addLayout(pie)
        raiz.addStretch()

    # ------------------------------------------------------- Datos ----
    def cargar(self) -> None:
        modelo = self.config_service.obtener_modelo_negocio()
        agenda = self.config_service.obtener_agenda()

        self.radio_servicios.setChecked(modelo == MODELO_SERVICIOS)
        self.radio_ventas.setChecked(modelo != MODELO_SERVICIOS)

        self._elegir_texto(self.combo_apertura, agenda["hora_inicio"])
        self._elegir_texto(self.combo_cierre, agenda["hora_fin"])
        indice = self.combo_intervalo.findData(agenda["intervalo_min"])
        self.combo_intervalo.setCurrentIndex(indice if indice >= 0 else self.combo_intervalo.findData(30))
        for i, check in enumerate(self.checks_dias):
            check.setChecked(i in agenda["dias"])
        self._actualizar_visibilidad()

    @staticmethod
    def _elegir_texto(combo: QComboBox, texto: str) -> None:
        indice = combo.findText(texto)
        if indice < 0:  # una hora guardada que no está en la lista (ej. 08:15)
            combo.addItem(texto)
            indice = combo.findText(texto)
        combo.setCurrentIndex(indice)

    def _modelo_elegido(self) -> str:
        return MODELO_SERVICIOS if self.radio_servicios.isChecked() else MODELO_VENTAS

    def _actualizar_visibilidad(self) -> None:
        self.tarjeta_agenda.setVisible(self._modelo_elegido() == MODELO_SERVICIOS)

    # ----------------------------------------------------- Acciones ----
    def _guardar(self) -> None:
        modelo = self._modelo_elegido()
        dias = [i for i, check in enumerate(self.checks_dias) if check.isChecked()]
        if modelo == MODELO_VENTAS and self.config_service.obtener_modelo_negocio() == MODELO_SERVICIOS:
            # Al pasar a Ventas la Agenda se oculta: las reservas pendientes y sus adelantos
            # quedarían sin poder cobrarse ni cancelarse hasta volver a Servicios con reserva.
            pendientes = ReservaService().resumen_pendientes()
            if pendientes["cantidad"]:
                moneda = self.config_service.obtener().get("moneda", "S/")
                detalle = (f" y {moneda} {pendientes['adelantos']:.2f} recibidos en adelantos"
                           if pendientes["adelantos"] else "")
                respuesta = QMessageBox.question(
                    self, "Tienes reservas pendientes",
                    f"Hay {pendientes['cantidad']} reserva(s) por atender{detalle}.\n\n"
                    "Si cambias a «Ventas de productos», la Agenda se oculta y no podrás cobrarlas, "
                    "cancelarlas ni devolver adelantos hasta volver a «Servicios con reserva». "
                    "No se borra nada.\n\n¿Cambiar de modelo de todos modos?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if respuesta != QMessageBox.Yes:
                    return
        try:
            self.config_service.actualizar_modelo_negocio(
                modelo,
                self.combo_apertura.currentText(),
                self.combo_cierre.currentText(),
                self.combo_intervalo.currentData(),
                dias,
            )
        except ConfiguracionError as e:
            QMessageBox.warning(self, "No se pudo guardar", str(e))
            return

        self.modelo_cambiado.emit(modelo)
        if modelo == MODELO_SERVICIOS:
            mensaje = ("Ahora tu negocio trabaja con servicios y reservas.\n\n"
                       "Siguiente paso: entra a «Servicios» en el menú y crea los servicios "
                       "que ofreces (con su precio y duración). Después podrás reservar horas "
                       "desde la Agenda.")
        else:
            mensaje = "Ahora tu negocio trabaja con ventas de productos."
        QMessageBox.information(self, "Modelo de negocio actualizado", mensaje)
