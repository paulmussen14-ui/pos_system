"""Página de Caja: apertura, ingresos/egresos manuales, cierre con cálculo de diferencia."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFrame
)

from services.caja_service import CajaService, CajaError
from services.configuracion_service import ConfiguracionService
from utils.validators import formatear_moneda


class CajaPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.caja_service = CajaService()
        self.config_service = ConfiguracionService()
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        titulo = QLabel("Caja")
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        layout.addWidget(titulo)

        self.panel_estado = QFrame()
        self.panel_estado.setProperty("class", "card")
        layout_estado = QVBoxLayout(self.panel_estado)
        self.label_estado = QLabel()
        self.label_estado.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout_estado.addWidget(self.label_estado)
        layout.addWidget(self.panel_estado)

        # --- Sección apertura (visible si no hay caja abierta) ---
        self.panel_apertura = QWidget()
        layout_apertura = QHBoxLayout(self.panel_apertura)
        layout_apertura.addWidget(QLabel("Monto de apertura:"))
        self.input_monto_apertura = QDoubleSpinBox()
        self.input_monto_apertura.setMaximum(999999)
        self.input_monto_apertura.setPrefix("S/ ")
        layout_apertura.addWidget(self.input_monto_apertura)
        btn_abrir = QPushButton("Abrir caja")
        btn_abrir.setProperty("class", "success")
        btn_abrir.clicked.connect(self._abrir_caja)
        layout_apertura.addWidget(btn_abrir)
        layout_apertura.addStretch()
        layout.addWidget(self.panel_apertura)

        # --- Sección movimientos manuales (visible si hay caja abierta) ---
        self.panel_movimientos = QWidget()
        layout_movimientos = QHBoxLayout(self.panel_movimientos)
        layout_movimientos.addWidget(QLabel("Monto:"))
        self.input_monto_movimiento = QDoubleSpinBox()
        self.input_monto_movimiento.setMaximum(999999)
        self.input_monto_movimiento.setPrefix("S/ ")
        layout_movimientos.addWidget(self.input_monto_movimiento)

        self.input_descripcion_movimiento = QLineEdit()
        self.input_descripcion_movimiento.setPlaceholderText("Descripción")
        layout_movimientos.addWidget(self.input_descripcion_movimiento)

        btn_ingreso = QPushButton("+ Ingreso")
        btn_ingreso.setProperty("class", "success")
        btn_ingreso.clicked.connect(self._registrar_ingreso)
        layout_movimientos.addWidget(btn_ingreso)

        btn_egreso = QPushButton("- Egreso")
        btn_egreso.setProperty("class", "danger")
        btn_egreso.clicked.connect(self._registrar_egreso)
        layout_movimientos.addWidget(btn_egreso)

        btn_retiro = QPushButton("Retiro")
        btn_retiro.setProperty("class", "secondary")
        btn_retiro.clicked.connect(self._registrar_retiro)
        layout_movimientos.addWidget(btn_retiro)

        layout.addWidget(self.panel_movimientos)

        # Tabla de movimientos de la sesión actual
        self.tabla_movimientos = QTableWidget(0, 4)
        self.tabla_movimientos.setHorizontalHeaderLabels(["Fecha", "Tipo", "Monto", "Descripción"])
        self.tabla_movimientos.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla_movimientos.verticalHeader().setVisible(False)
        self.tabla_movimientos.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.tabla_movimientos)

        # --- Sección cierre ---
        self.panel_cierre = QWidget()
        layout_cierre = QHBoxLayout(self.panel_cierre)
        layout_cierre.addWidget(QLabel("Monto contado:"))
        self.input_monto_contado = QDoubleSpinBox()
        self.input_monto_contado.setMaximum(999999)
        self.input_monto_contado.setPrefix("S/ ")
        layout_cierre.addWidget(self.input_monto_contado)

        btn_cerrar_caja = QPushButton("Cerrar caja")
        btn_cerrar_caja.setProperty("class", "danger")
        btn_cerrar_caja.clicked.connect(self._cerrar_caja)
        layout_cierre.addWidget(btn_cerrar_caja)
        layout_cierre.addStretch()
        layout.addWidget(self.panel_cierre)

    def actualizar(self) -> None:
        moneda = self.config_service.obtener().get("moneda", "S/")
        estado = self.caja_service.estado_actual(self.usuario.id)

        hay_caja_abierta = estado.get("abierta", False)
        self.panel_apertura.setVisible(not hay_caja_abierta)
        self.panel_movimientos.setVisible(hay_caja_abierta)
        self.panel_cierre.setVisible(hay_caja_abierta)

        if hay_caja_abierta:
            self.label_estado.setText(
                f"Caja ABIERTA — Apertura: {formatear_moneda(estado['monto_apertura'], moneda)}   |   "
                f"Esperado ahora: {formatear_moneda(estado['monto_esperado'], moneda)}"
            )
            movimientos = self.caja_service.movimientos_sesion_actual(self.usuario.id)
            self.tabla_movimientos.setRowCount(len(movimientos))
            for fila, m in enumerate(movimientos):
                self.tabla_movimientos.setItem(fila, 0, QTableWidgetItem(str(m["fecha"])))
                self.tabla_movimientos.setItem(fila, 1, QTableWidgetItem(m["tipo"]))
                self.tabla_movimientos.setItem(fila, 2, QTableWidgetItem(formatear_moneda(m["monto"], moneda)))
                self.tabla_movimientos.setItem(fila, 3, QTableWidgetItem(m.get("descripcion") or "-"))
        else:
            self.label_estado.setText("Caja CERRADA. Abre la caja para comenzar a vender.")
            self.tabla_movimientos.setRowCount(0)

    def _abrir_caja(self) -> None:
        try:
            self.caja_service.abrir_caja(self.usuario.id, self.input_monto_apertura.value())
        except CajaError as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        self.input_monto_apertura.setValue(0)
        self.actualizar()

    def _registrar_ingreso(self) -> None:
        self._registrar_movimiento(self.caja_service.registrar_ingreso_manual)

    def _registrar_egreso(self) -> None:
        self._registrar_movimiento(self.caja_service.registrar_egreso)

    def _registrar_retiro(self) -> None:
        self._registrar_movimiento(self.caja_service.registrar_retiro)

    def _registrar_movimiento(self, metodo_servicio) -> None:
        try:
            metodo_servicio(
                self.usuario.id, self.input_monto_movimiento.value(), self.input_descripcion_movimiento.text()
            )
        except CajaError as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        self.input_monto_movimiento.setValue(0)
        self.input_descripcion_movimiento.clear()
        self.actualizar()

    def _cerrar_caja(self) -> None:
        respuesta = QMessageBox.question(self, "Confirmar cierre", "¿Cerrar la caja con el monto contado ingresado?")
        if respuesta != QMessageBox.Yes:
            return
        try:
            resultado = self.caja_service.cerrar_caja(self.usuario.id, self.input_monto_contado.value())
        except CajaError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        moneda = self.config_service.obtener().get("moneda", "S/")
        QMessageBox.information(
            self, "Caja cerrada",
            f"Esperado: {formatear_moneda(resultado['monto_esperado'], moneda)}\n"
            f"Contado: {formatear_moneda(resultado['monto_contado'], moneda)}\n"
            f"Diferencia: {formatear_moneda(resultado['diferencia'], moneda)}"
        )
        self.input_monto_contado.setValue(0)
        self.actualizar()
