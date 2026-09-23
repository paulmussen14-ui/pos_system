"""Pantalla de inicio de sesión."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, Signal

from services.auth_service import AuthService, AuthError
from config import APP_LOGO_PATH, APP_ICON_PATH


class LoginWindow(QWidget):

    sesion_iniciada = Signal(object)  # emite el objeto Usuario
    ir_a_recuperacion = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_service = AuthService()
        self._construir_ui()

    def _construir_ui(self) -> None:
        self.setWindowTitle("Iniciar sesión")
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(860, 520)
        self.setMinimumSize(760, 460)

        layout_general = QHBoxLayout(self)
        layout_general.setContentsMargins(0, 0, 0, 0)
        layout_general.setSpacing(0)

        # ---- Panel izquierdo: formulario de login ----
        panel_formulario = QWidget()
        layout_exterior = QVBoxLayout(panel_formulario)
        layout_exterior.setContentsMargins(70, 0, 70, 0)
        layout_exterior.addStretch()

        titulo = QLabel("Iniciar sesión")
        titulo.setStyleSheet("font-size: 30px; font-weight: 700; margin-bottom: 6px;")
        layout_exterior.addWidget(titulo)

        subtitulo = QLabel("Ingresa tus credenciales para continuar")
        subtitulo.setStyleSheet("font-size: 14px; color: #6b7280; margin-bottom: 20px;")
        layout_exterior.addWidget(subtitulo)

        estilo_label = "font-size: 14px; font-weight: 600; margin-top: 6px;"
        estilo_input = """
            QLineEdit {
                font-size: 15px;
                padding: 12px 14px;
                border: 1px solid #d1d5db;
                border-radius: 8px;
            }
            QLineEdit:focus {
                border: 1.5px solid #2563eb;
            }
        """

        label_usuario = QLabel("Usuario")
        label_usuario.setStyleSheet(estilo_label)
        layout_exterior.addWidget(label_usuario)

        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("Ingresa tu usuario")
        self.input_usuario.setMinimumHeight(46)
        self.input_usuario.setStyleSheet(estilo_input)
        layout_exterior.addWidget(self.input_usuario)

        label_password = QLabel("Contraseña")
        label_password.setStyleSheet(estilo_label)
        layout_exterior.addWidget(label_password)

        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setPlaceholderText("Ingresa tu contraseña")
        self.input_password.setMinimumHeight(46)
        self.input_password.setStyleSheet(estilo_input)
        self.input_password.returnPressed.connect(self._iniciar_sesion)
        layout_exterior.addWidget(self.input_password)

        layout_exterior.addSpacing(20)

        self.btn_ingresar = QPushButton("Ingresar")
        self.btn_ingresar.setMinimumHeight(48)
        self.btn_ingresar.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.btn_ingresar.clicked.connect(self._iniciar_sesion)
        layout_exterior.addWidget(self.btn_ingresar)

        layout_exterior.addSpacing(10)

        btn_olvide = QPushButton("¿Olvidaste tu contraseña?")
        btn_olvide.setProperty("class", "secondary")
        btn_olvide.setMinimumHeight(42)
        btn_olvide.setStyleSheet("font-size: 13px;")
        btn_olvide.clicked.connect(self.ir_a_recuperacion.emit)
        layout_exterior.addWidget(btn_olvide)

        layout_exterior.addStretch()

        # ---- Panel derecho: logo ----
        panel_logo = QWidget()
        panel_logo.setObjectName("loginLogoPanel")
        panel_logo.setStyleSheet("background-color: #f8fafc;")
        layout_logo = QVBoxLayout(panel_logo)
        layout_logo.setContentsMargins(30, 30, 30, 30)
        layout_logo.setAlignment(Qt.AlignCenter)

        if APP_LOGO_PATH.exists():
            label_logo = QLabel()
            pixmap = QPixmap(str(APP_LOGO_PATH))
            pixmap = pixmap.scaledToWidth(320, Qt.SmoothTransformation)
            label_logo.setPixmap(pixmap)
            label_logo.setAlignment(Qt.AlignCenter)
            layout_logo.addWidget(label_logo)

        layout_general.addWidget(panel_formulario, stretch=3)
        layout_general.addWidget(panel_logo, stretch=2)

    def _iniciar_sesion(self) -> None:
        try:
            usuario = self.auth_service.iniciar_sesion(
                self.input_usuario.text(), self.input_password.text()
            )
        except AuthError as e:
            QMessageBox.warning(self, "Error de acceso", str(e))
            return

        self.input_password.clear()
        self.sesion_iniciada.emit(usuario)