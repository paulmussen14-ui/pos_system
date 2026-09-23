"""Pantalla de recuperación de cuenta mediante código de recuperación."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QDialog, QTextEdit, QHBoxLayout
)
from PySide6.QtCore import Signal

from services.auth_service import AuthService, AuthError


class RecoveryWindow(QWidget):

    password_restablecida = Signal()
    volver_a_login = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_service = AuthService()
        self._construir_ui()

    def _construir_ui(self) -> None:
        self.setWindowTitle("Recuperar cuenta")
        self.resize(400, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        titulo = QLabel("Recuperar cuenta")
        titulo.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(titulo)

        info = QLabel("Ingresa el código de recuperación que guardaste al crear tu cuenta.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #6b7280;")
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)

        self.input_codigo = QLineEdit()
        self.input_codigo.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.input_password_nuevo = QLineEdit()
        self.input_password_nuevo.setEchoMode(QLineEdit.Password)
        self.input_password_nuevo.setPlaceholderText("Mínimo 8 caracteres")
        self.input_confirmar = QLineEdit()
        self.input_confirmar.setEchoMode(QLineEdit.Password)

        form.addRow("Código de recuperación:", self.input_codigo)
        form.addRow("Nueva contraseña:", self.input_password_nuevo)
        form.addRow("Confirmar contraseña:", self.input_confirmar)
        layout.addLayout(form)

        self.btn_restablecer = QPushButton("Restablecer contraseña")
        self.btn_restablecer.clicked.connect(self._restablecer)
        layout.addWidget(self.btn_restablecer)

        self.btn_volver = QPushButton("Volver a iniciar sesión")
        self.btn_volver.setProperty("class", "secondary")
        self.btn_volver.clicked.connect(self.volver_a_login.emit)
        layout.addWidget(self.btn_volver)

        layout.addStretch()

    def _restablecer(self) -> None:
        try:
            nuevo_codigo = self.auth_service.restablecer_password_con_codigo(
                self.input_codigo.text(),
                self.input_password_nuevo.text(),
                self.input_confirmar.text(),
            )
        except AuthError as e:
            QMessageBox.warning(self, "No se pudo restablecer", str(e))
            return

        self._mostrar_nuevo_codigo(nuevo_codigo)
        self.input_codigo.clear()
        self.input_password_nuevo.clear()
        self.input_confirmar.clear()
        self.password_restablecida.emit()

    def _mostrar_nuevo_codigo(self, codigo: str) -> None:
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Nuevo código de recuperación")
        dialogo.resize(420, 240)
        layout = QVBoxLayout(dialogo)

        aviso = QLabel(
            "Tu contraseña fue restablecida.\n"
            "Se generó un NUEVO código de recuperación (el anterior ya no sirve).\n"
            "Guárdalo en un lugar seguro:"
        )
        aviso.setWordWrap(True)
        layout.addWidget(aviso)

        campo = QTextEdit()
        campo.setPlainText(codigo)
        campo.setReadOnly(True)
        campo.setFixedHeight(60)
        campo.setStyleSheet("font-size: 18px; font-weight: 700; font-family: monospace;")
        layout.addWidget(campo)

        btn_ok = QPushButton("Entendido")
        btn_ok.clicked.connect(dialogo.accept)
        layout.addWidget(btn_ok)

        dialogo.exec()
