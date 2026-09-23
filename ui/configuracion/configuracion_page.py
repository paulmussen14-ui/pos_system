"""Página de Configuración: datos del negocio, impresión, métodos de pago, backups, seguridad."""

from pathlib import Path
import os
import shutil
import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDoubleSpinBox, QTabWidget, QMessageBox,
    QFileDialog, QListWidget, QCheckBox, QSpinBox
)

from services.configuracion_service import ConfiguracionService
from services.auth_service import AuthService, AuthError
from utils.backup_manager import crear_backup, listar_backups, restaurar_backup
from printing.ticket_printer import listar_impresoras_disponibles
from ui.configuracion.ticket_extras_dialog import TicketExtrasDialog


class ConfiguracionPage(QWidget):

    tema_cambiado = None  # se asigna desde MainWindow (callback)

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.config_service = ConfiguracionService()
        self.auth_service = AuthService()
        self._construir_ui()
        self._cargar_datos()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        titulo = QLabel("Configuración")
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        layout.addWidget(titulo)

        tabs = QTabWidget()

        tabs.addTab(self._tab_negocio(), "Negocio")
        tabs.addTab(self._tab_impresion(), "Impresión")
        tabs.addTab(self._tab_metodos_pago(), "Métodos de pago")
        tabs.addTab(self._tab_backups(), "Copias de seguridad")
        tabs.addTab(self._tab_seguridad(), "Seguridad")
        tabs.addTab(self._tab_desarrollo(), "Desarrollo")
        layout.addWidget(tabs)

    # -------------------------------------------------- Tab: Negocio ----
    def _tab_negocio(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.input_nombre_negocio = QLineEdit()
        self.input_direccion = QLineEdit()
        self.combo_moneda = QComboBox()
        self.combo_moneda.addItems(["S/", "$", "€"])
        self.input_igv = QDoubleSpinBox()
        self.input_igv.setMaximum(100)
        self.input_igv.setSuffix(" %")
        self.input_ticket_pie = QLineEdit()
        self.combo_tema = QComboBox()
        self.combo_tema.addItems(["claro", "oscuro"])

        form.addRow("Nombre del negocio:", self.input_nombre_negocio)
        form.addRow("Dirección:", self.input_direccion)
        form.addRow("Moneda:", self.combo_moneda)
        form.addRow("IGV / Impuesto (%):", self.input_igv)
        form.addRow("Pie de ticket:", self.input_ticket_pie)
        form.addRow("Tema:", self.combo_tema)

        btn_logo = QPushButton("Cambiar logo...")
        btn_logo.clicked.connect(self._seleccionar_logo)
        form.addRow("Logo:", btn_logo)

        btn_guardar = QPushButton("Guardar cambios")
        btn_guardar.clicked.connect(self._guardar_negocio)
        form.addRow(btn_guardar)

        return tab

    def _tab_impresion(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.combo_tipo_impresora = QComboBox()
        self.combo_tipo_impresora.addItems(["termica_58mm", "termica_80mm", "ninguna"])

        self.combo_nombre_impresora = QComboBox()
        self.combo_nombre_impresora.setEditable(True)
        for nombre in listar_impresoras_disponibles():
            self.combo_nombre_impresora.addItem(nombre)

        self.check_impresion_activa = QCheckBox("Impresión activa")

        self.check_dos_copias = QCheckBox("Imprimir 2 copias (cliente + control interno)")
        self.check_dos_copias.setToolTip(
            "Si está marcado, cada venta imprime dos tickets seguidos: uno "
            "para el cliente y otro para tu control interno del negocio."
        )

        form.addRow("Tipo de impresora:", self.combo_tipo_impresora)
        form.addRow("Impresora de Windows:", self.combo_nombre_impresora)
        form.addRow(self.check_impresion_activa)
        form.addRow(self.check_dos_copias)

        btn_guardar = QPushButton("Guardar cambios")
        btn_guardar.clicked.connect(self._guardar_impresion)
        form.addRow(btn_guardar)

        # Textos que salen en el ticket: reclamos, devolución, Yape, chofer.
        # Se guardan por separado (ventana propia), no con "Guardar cambios".
        btn_ticket = QPushButton("Datos del ticket")
        btn_ticket.setProperty("class", "secondary")
        btn_ticket.setToolTip(
            "Número para reclamos, términos de devolución, Yape, chofer y "
            "número del negocio, con vista previa del ticket."
        )
        btn_ticket.clicked.connect(self._abrir_datos_ticket)
        form.addRow("Contenido del ticket:", btn_ticket)

        return tab

    def _tab_metodos_pago(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.lista_metodos_pago = QListWidget()
        layout.addWidget(self.lista_metodos_pago)

        fila = QHBoxLayout()
        self.input_nuevo_metodo = QLineEdit()
        self.input_nuevo_metodo.setPlaceholderText("Nuevo método de pago")
        fila.addWidget(self.input_nuevo_metodo)
        self.check_nuevo_metodo_efectivo = QCheckBox("Afecta caja (es efectivo)")
        fila.addWidget(self.check_nuevo_metodo_efectivo)
        btn_agregar = QPushButton("Agregar")
        btn_agregar.clicked.connect(self._agregar_metodo_pago)
        fila.addWidget(btn_agregar)
        layout.addLayout(fila)

        aviso = QLabel(
            "Marca \"Afecta caja\" solo para métodos que mueven dinero físico "
            "(ej. Efectivo). Las ventas y compras con ese método sí generan "
            "movimientos de caja; el resto (tarjeta, transferencia, etc.) no."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: #6b7280;")
        layout.addWidget(aviso)

        return tab

    def _tab_backups(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        btn_crear_backup = QPushButton("Crear copia de seguridad ahora")
        btn_crear_backup.setProperty("class", "success")
        btn_crear_backup.clicked.connect(self._crear_backup)
        layout.addWidget(btn_crear_backup)

        self.lista_backups = QListWidget()
        layout.addWidget(self.lista_backups)

        btn_restaurar = QPushButton("Restaurar copia seleccionada")
        btn_restaurar.setProperty("class", "danger")
        btn_restaurar.clicked.connect(self._restaurar_backup)
        layout.addWidget(btn_restaurar)

        aviso = QLabel("⚠ Restaurar una copia reemplaza los datos actuales. Reinicia la app después de restaurar.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: #92400e;")
        layout.addWidget(aviso)

        return tab

    def _tab_seguridad(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.input_password_actual = QLineEdit()
        self.input_password_actual.setEchoMode(QLineEdit.Password)
        self.input_password_nuevo = QLineEdit()
        self.input_password_nuevo.setEchoMode(QLineEdit.Password)
        self.input_password_confirmar = QLineEdit()
        self.input_password_confirmar.setEchoMode(QLineEdit.Password)

        form.addRow("Contraseña actual:", self.input_password_actual)
        form.addRow("Nueva contraseña:", self.input_password_nuevo)
        form.addRow("Confirmar nueva contraseña:", self.input_password_confirmar)

        btn_cambiar = QPushButton("Cambiar contraseña")
        btn_cambiar.clicked.connect(self._cambiar_password)
        form.addRow(btn_cambiar)

        return tab

    # --------------------------------------------------------- Datos ----
    def _cargar_datos(self) -> None:
        config = self.config_service.obtener()
        self.input_nombre_negocio.setText(config.get("nombre_negocio") or "")
        self.input_direccion.setText(config.get("direccion") or "")
        idx = self.combo_moneda.findText(config.get("moneda", "S/"))
        if idx >= 0:
            self.combo_moneda.setCurrentIndex(idx)
        self.input_igv.setValue(config.get("igv_porcentaje") or 0)
        self.input_ticket_pie.setText(config.get("ticket_pie") or "")
        idx_tema = self.combo_tema.findText(config.get("tema", "claro"))
        if idx_tema >= 0:
            self.combo_tema.setCurrentIndex(idx_tema)

        config_impresion = self.config_service.obtener_config_impresion()
        idx_tipo = self.combo_tipo_impresora.findText(config_impresion.get("tipo_impresora", "termica_58mm"))
        if idx_tipo >= 0:
            self.combo_tipo_impresora.setCurrentIndex(idx_tipo)
        self.combo_nombre_impresora.setCurrentText(config_impresion.get("nombre_impresora") or "")
        self.check_impresion_activa.setChecked(bool(config_impresion.get("activo")))
        self.check_dos_copias.setChecked(bool(config_impresion.get("imprimir_dos_copias", True)))

        self._cargar_metodos_pago()
        self._cargar_backups()

    def _cargar_metodos_pago(self) -> None:
        self.lista_metodos_pago.clear()
        for metodo in self.config_service.listar_metodos_pago():
            estado = "activo" if metodo["activo"] else "inactivo"
            afecta_caja = "afecta caja" if metodo.get("es_efectivo") else "no afecta caja"
            self.lista_metodos_pago.addItem(f"{metodo['nombre']} ({estado}, {afecta_caja})")

    def _cargar_backups(self) -> None:
        self.lista_backups.clear()
        for backup in listar_backups():
            self.lista_backups.addItem(backup.name)

    # -------------------------------------------------------- Acciones ----
    def _abrir_datos_ticket(self) -> None:
        dialogo = TicketExtrasDialog(parent=self)
        dialogo.exec()

    def _seleccionar_logo(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Seleccionar logo", "", "Imágenes (*.png *.jpg *.jpeg)")
        if ruta:
            self.config_service.actualizar_logo(ruta)
            QMessageBox.information(self, "Logo actualizado", "El logo se actualizó correctamente.")

    def _guardar_negocio(self) -> None:
        self.config_service.actualizar(
            self.input_nombre_negocio.text(), self.input_direccion.text(),
            self.combo_moneda.currentText(), self.input_igv.value(),
            self.input_ticket_pie.text(), self.combo_tema.currentText(),
        )
        QMessageBox.information(self, "Guardado", "Configuración del negocio actualizada.")
        if callable(self.tema_cambiado):
            self.tema_cambiado(self.combo_tema.currentText())

    def _guardar_impresion(self) -> None:
        self.config_service.actualizar_config_impresion(
            self.combo_tipo_impresora.currentText(),
            58 if "58" in self.combo_tipo_impresora.currentText() else 80,
            self.combo_nombre_impresora.currentText(),
            self.check_impresion_activa.isChecked(),
            self.check_dos_copias.isChecked(),
        )
        QMessageBox.information(self, "Guardado", "Configuración de impresión actualizada.")

    def _agregar_metodo_pago(self) -> None:
        nombre = self.input_nuevo_metodo.text().strip()
        if not nombre:
            return
        self.config_service.crear_metodo_pago(nombre, self.check_nuevo_metodo_efectivo.isChecked())
        self.input_nuevo_metodo.clear()
        self.check_nuevo_metodo_efectivo.setChecked(False)
        self._cargar_metodos_pago()

    def _crear_backup(self) -> None:
        ruta = crear_backup()
        QMessageBox.information(self, "Copia creada", f"Copia de seguridad guardada en:\n{ruta}")
        self._cargar_backups()

    def _restaurar_backup(self) -> None:
        item = self.lista_backups.currentItem()
        if not item:
            QMessageBox.information(self, "Selecciona una copia", "Elige una copia de seguridad de la lista.")
            return

        respuesta = QMessageBox.question(
            self, "Confirmar restauración",
            "Esto reemplazará los datos actuales. ¿Continuar?"
        )
        if respuesta != QMessageBox.Yes:
            return

        from config import BACKUPS_DIR
        ruta_backup = BACKUPS_DIR / item.text()
        try:
            restaurar_backup(ruta_backup)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        QMessageBox.information(self, "Restaurado", "Copia restaurada. Cierra y vuelve a abrir la aplicación.")

    def _cambiar_password(self) -> None:
        try:
            self.auth_service.cambiar_password(
                self.usuario.id, self.input_password_actual.text(),
                self.input_password_nuevo.text(), self.input_password_confirmar.text(),
            )
        except AuthError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        QMessageBox.information(self, "Contraseña actualizada", "Tu contraseña fue cambiada correctamente.")
        self.input_password_actual.clear()
        self.input_password_nuevo.clear()
        self.input_password_confirmar.clear()

    def _tab_desarrollo(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        aviso = QLabel(
            "⚠ SOLO PARA PRUEBAS. Esto borra TODA la base de datos (productos, "
            "ventas, clientes, caja, todo) y reinicia la aplicación desde cero, "
            "como si fuera la primera vez que se instala."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: #92400e; font-weight: 600;")
        layout.addWidget(aviso)

        btn_reset = QPushButton("Borrar todo y reiniciar la aplicación")
        btn_reset.setProperty("class", "danger")
        btn_reset.clicked.connect(self._reiniciar_aplicacion_completa)
        layout.addWidget(btn_reset)
        layout.addStretch()

        return tab

    def _reiniciar_aplicacion_completa(self) -> None:
            respuesta = QMessageBox.question(
                self, "Confirmar borrado total",
                "Esto borrará TODOS los datos (productos, ventas, clientes, caja, "
                "usuario administrador) sin posibilidad de deshacer, y reiniciará "
                "la aplicación. ¿Estás seguro?"
            )
            if respuesta != QMessageBox.Yes:
                return

            from database.connection import get_db, DATABASE_PATH
            from config import DATABASE_PATH as DB_PATH

            db = get_db()
            db.close()

            for sufijo in ("", "-wal", "-shm", "-journal"):
                archivo = DB_PATH.parent / (DB_PATH.name + sufijo)
                if archivo.exists():
                    archivo.unlink()

            # Reinicia el proceso de la app desde cero
            os.execv(sys.executable, [sys.executable] + sys.argv)