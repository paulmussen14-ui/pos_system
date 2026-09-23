"""Pantalla de primera instalación: creación de la única cuenta de administrador."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QDialog, QHBoxLayout, QTextEdit
)
from PySide6.QtCore import Qt, Signal

from services.auth_service import AuthService, AuthError


class SetupAdminWindow(QWidget):
    """Se muestra solo si no existe ninguna cuenta creada todavía."""

    cuenta_creada = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_service = AuthService()
        self._construir_ui()

    def _construir_ui(self) -> None:
        self.setWindowTitle("Configuración inicial - Crear cuenta de administrador")
        self.resize(420, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        titulo = QLabel("Bienvenido")
        titulo.setStyleSheet("font-size: 22px; font-weight: 700;")
        subtitulo = QLabel("Crea la cuenta de administrador para tu negocio.\nEsta será la única cuenta del sistema.")
        subtitulo.setWordWrap(True)
        subtitulo.setStyleSheet("color: #6b7280;")

        layout.addWidget(titulo)
        layout.addWidget(subtitulo)

        form = QFormLayout()
        form.setSpacing(10)

        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Ej. Camile Flores")
        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("Nombre de usuario")
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setPlaceholderText("Mínimo 8 caracteres")
        self.input_confirmar = QLineEdit()
        self.input_confirmar.setEchoMode(QLineEdit.Password)

        form.addRow("Nombre completo:", self.input_nombre)
        form.addRow("Usuario:", self.input_usuario)
        form.addRow("Contraseña:", self.input_password)
        form.addRow("Confirmar contraseña:", self.input_confirmar)

        layout.addLayout(form)

        self.btn_crear = QPushButton("Crear cuenta de administrador")
        self.btn_crear.clicked.connect(self._crear_cuenta)
        layout.addWidget(self.btn_crear)

        layout.addStretch()

    def _crear_cuenta(self) -> None:
        try:
            codigo_recuperacion = self.auth_service.crear_cuenta_administrador(
                self.input_nombre.text(),
                self.input_usuario.text(),
                self.input_password.text(),
                self.input_confirmar.text(),
            )
        except AuthError as e:
            QMessageBox.warning(self, "No se pudo crear la cuenta", str(e))
            return

        self._mostrar_codigo_recuperacion(codigo_recuperacion)
        self.cuenta_creada.emit()

    def _mostrar_codigo_recuperacion(self, codigo: str) -> None:
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Guarda tu código de recuperación")
        dialogo.setModal(True)
        dialogo.resize(420, 260)

        layout = QVBoxLayout(dialogo)

        aviso = QLabel(
            "⚠️ Este código solo se muestra UNA vez.\n"
            "Guárdalo en un lugar seguro: es la única forma de recuperar\n"
            "tu cuenta si olvidas la contraseña."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("font-weight: 600;")
        layout.addWidget(aviso)

        campo_codigo = QTextEdit()
        campo_codigo.setPlainText(codigo)
        campo_codigo.setReadOnly(True)
        campo_codigo.setStyleSheet("font-size: 20px; font-weight: 700; font-family: monospace;")
        campo_codigo.setFixedHeight(60)
        layout.addWidget(campo_codigo)

        botones = QHBoxLayout()
        btn_copiar = QPushButton("Copiar código")
        btn_copiar.setProperty("class", "secondary")
        btn_copiar.clicked.connect(lambda: self._copiar_al_portapapeles(codigo))
        btn_continuar = QPushButton("Ya lo guardé, continuar")
        btn_continuar.clicked.connect(dialogo.accept)

        botones.addWidget(btn_copiar)
        botones.addWidget(btn_continuar)
        layout.addLayout(botones)

        dialogo.exec()

    def _copiar_al_portapapeles(self, texto: str) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(texto)
        QMessageBox.information(self, "Copiado", "Código copiado al portapapeles.")
