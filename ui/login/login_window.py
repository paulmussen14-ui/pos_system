"""Pantalla de inicio de sesión (tema oscuro moderno)."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
)
from PySide6.QtGui import (
    QPixmap, QIcon, QPainter, QPainterPath, QLinearGradient, QRadialGradient, QColor, QPen, QAction,
)
from PySide6.QtCore import Qt, Signal, QRectF

from services.auth_service import AuthService, AuthError
from config import APP_LOGO_PATH, APP_ICON_PATH, APP_VERSION
from ui.iconos import icono
from ui.tokens import paleta

_P = paleta("oscuro")
_FONDO = "#0b1018"
_PANEL = "#0f141c"
_COLOR_ICONO = "#6b778a"


def _logo_redondeado(ancho: int, radio: int):
    """Logo dentro de una tarjeta clara con esquinas redondeadas (el logo tiene
    texto azul oscuro y fondo claro, así que necesita una base clara sobre el tema oscuro)."""
    if not APP_LOGO_PATH.exists():
        return None
    origen = QPixmap(str(APP_LOGO_PATH)).scaledToWidth(ancho * 2, Qt.SmoothTransformation)
    destino = QPixmap(origen.size())
    destino.fill(Qt.transparent)
    p = QPainter(destino)
    p.setRenderHint(QPainter.Antialiasing, True)
    ruta = QPainterPath()
    ruta.addRoundedRect(QRectF(destino.rect()), radio * 2, radio * 2)
    p.setClipPath(ruta)
    p.drawPixmap(0, 0, origen)
    p.end()
    destino.setDevicePixelRatio(2)
    return destino


class _PanelMarca(QWidget):
    """Panel lateral con degradado y destellos suaves dibujados a mano."""

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        verde = QColor(_P["primario"])

        fondo = QLinearGradient(0, 0, w, h)
        fondo.setColorAt(0.0, QColor("#0d2f27"))
        fondo.setColorAt(0.55, QColor("#0b1a20"))
        fondo.setColorAt(1.0, QColor("#0a0f16"))
        p.fillRect(self.rect(), fondo)

        brillo = QRadialGradient(w * 0.85, h * 0.12, w * 0.75)
        c = QColor(verde)
        c.setAlpha(70)
        brillo.setColorAt(0.0, c)
        c.setAlpha(0)
        brillo.setColorAt(1.0, c)
        p.fillRect(self.rect(), brillo)

        brillo2 = QRadialGradient(w * 0.1, h * 0.95, w * 0.6)
        c2 = QColor("#0ea5e9")
        c2.setAlpha(38)
        brillo2.setColorAt(0.0, c2)
        c2.setAlpha(0)
        brillo2.setColorAt(1.0, c2)
        p.fillRect(self.rect(), brillo2)

        # Círculos decorativos de trazo fino
        for cx, cy, r, alfa in ((w * 0.92, h * 0.10, 150, 26), (w * 0.92, h * 0.10, 230, 16),
                                (w * 0.06, h * 0.92, 120, 20), (w * 0.06, h * 0.92, 190, 12)):
            borde = QColor("#ffffff")
            borde.setAlpha(alfa)
            p.setPen(QPen(borde, 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        p.end()


class LoginWindow(QWidget):

    sesion_iniciada = Signal(object)  # emite el objeto Usuario
    ir_a_recuperacion = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_service = AuthService()
        self._construir_ui()

    # ------------------------------------------------------------------
    def _construir_ui(self) -> None:
        self.setObjectName("loginRoot")
        self.setWindowTitle("Iniciar sesión")
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(920, 560)
        self.setMinimumSize(800, 500)
        self.setStyleSheet(self._qss())

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._construir_marca(), 5)
        raiz.addWidget(self._construir_formulario(), 5)

        self.input_usuario.setFocus()

    def _construir_marca(self) -> QWidget:
        panel = _PanelMarca()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(48, 40, 48, 36)
        lay.setSpacing(0)
        lay.addStretch(2)

        logo = _logo_redondeado(300, 22)
        if logo is not None:
            etiqueta = QLabel()
            etiqueta.setPixmap(logo)
            etiqueta.setAlignment(Qt.AlignCenter)
            lay.addWidget(etiqueta, 0, Qt.AlignHCenter)

        lay.addSpacing(34)
        titulo = QLabel("Tu negocio,\nbajo control.")
        titulo.setObjectName("marcaTitulo")
        titulo.setAlignment(Qt.AlignCenter)
        lay.addWidget(titulo)
        lay.addSpacing(10)
        sub = QLabel("Ventas, inventario, caja y reportes\nen un solo lugar.")
        sub.setObjectName("marcaSub")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)

        lay.addStretch(3)
        pie = QLabel(f"FayzerDev POS  ·  v{APP_VERSION}")
        pie.setObjectName("marcaPie")
        pie.setAlignment(Qt.AlignCenter)
        lay.addWidget(pie)
        return panel

    def _construir_formulario(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panelForm")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        externo = QHBoxLayout(panel)
        externo.setContentsMargins(40, 0, 40, 0)
        externo.addStretch()

        caja = QWidget()
        caja.setFixedWidth(360)
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addStretch()

        titulo = QLabel("Bienvenido de nuevo")
        titulo.setObjectName("titulo")
        lay.addWidget(titulo)
        lay.addSpacing(6)
        sub = QLabel("Ingresa tus credenciales para continuar")
        sub.setObjectName("subtitulo")
        lay.addWidget(sub)
        lay.addSpacing(30)

        lay.addWidget(self._etiqueta("Usuario"))
        lay.addSpacing(6)
        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("Ingresa tu usuario")
        self.input_usuario.setMinimumHeight(50)
        self.input_usuario.addAction(icono("usuario", _COLOR_ICONO, 18), QLineEdit.LeadingPosition)
        self.input_usuario.textChanged.connect(self._limpiar_error)
        self.input_usuario.returnPressed.connect(lambda: self.input_password.setFocus())
        lay.addWidget(self.input_usuario)
        lay.addSpacing(16)

        lay.addWidget(self._etiqueta("Contraseña"))
        lay.addSpacing(6)
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setPlaceholderText("Ingresa tu contraseña")
        self.input_password.setMinimumHeight(50)
        self.input_password.addAction(icono("candado", _COLOR_ICONO, 18), QLineEdit.LeadingPosition)
        self._accion_ver = QAction(self)
        self._accion_ver.setIcon(icono("ojo", _COLOR_ICONO, 18))
        self._accion_ver.setToolTip("Mostrar contraseña")
        self._accion_ver.triggered.connect(self._alternar_password)
        self.input_password.addAction(self._accion_ver, QLineEdit.TrailingPosition)
        self.input_password.textChanged.connect(self._limpiar_error)
        self.input_password.returnPressed.connect(self._iniciar_sesion)
        lay.addWidget(self.input_password)

        # Mensaje de error en línea (en vez de una ventana emergente)
        self.label_error = QLabel("")
        self.label_error.setObjectName("error")
        self.label_error.setWordWrap(True)
        self.label_error.setVisible(False)
        lay.addSpacing(10)
        lay.addWidget(self.label_error)

        lay.addSpacing(22)
        self.btn_ingresar = QPushButton("Ingresar")
        self.btn_ingresar.setObjectName("btnIngresar")
        self.btn_ingresar.setMinimumHeight(50)
        self.btn_ingresar.setCursor(Qt.PointingHandCursor)
        self.btn_ingresar.setDefault(True)
        self.btn_ingresar.clicked.connect(self._iniciar_sesion)
        lay.addWidget(self.btn_ingresar)

        lay.addSpacing(14)
        btn_olvide = QPushButton("¿Olvidaste tu contraseña?")
        btn_olvide.setObjectName("btnEnlace")
        btn_olvide.setCursor(Qt.PointingHandCursor)
        btn_olvide.setFlat(True)
        btn_olvide.clicked.connect(self.ir_a_recuperacion.emit)
        lay.addWidget(btn_olvide, 0, Qt.AlignHCenter)

        lay.addStretch()
        externo.addWidget(caja)
        externo.addStretch()
        return panel

    @staticmethod
    def _etiqueta(texto: str) -> QLabel:
        e = QLabel(texto)
        e.setObjectName("etiqueta")
        return e

    def _qss(self) -> str:
        primario, hover, presionado = _P["primario"], _P["primario_hover"], _P["primario_presionado"]
        return f"""
        QWidget#loginRoot {{ background-color: {_FONDO}; }}
        QWidget#panelForm {{ background-color: {_PANEL}; }}
        * {{ font-family: "Segoe UI", sans-serif; }}

        QLabel {{ background: transparent; color: #e6eaf0; }}
        QLabel#marcaTitulo {{ font-size: 30px; font-weight: 700; color: #ffffff; }}
        QLabel#marcaSub {{ font-size: 14px; color: #9fb0c3; }}
        QLabel#marcaPie {{ font-size: 12px; color: #5d6b7e; }}

        QLabel#titulo {{ font-size: 30px; font-weight: 700; color: #ffffff; }}
        QLabel#subtitulo {{ font-size: 14px; color: #8b97a8; }}
        QLabel#etiqueta {{ font-size: 13px; font-weight: 600; color: #c3ccd9; }}
        QLabel#error {{
            font-size: 13px; color: #fca5a5; background-color: #3a1a1f;
            border: 1px solid #6b2630; border-radius: 8px; padding: 9px 12px;
        }}

        QLineEdit {{
            font-size: 15px; color: #f1f5f9; background-color: #111823;
            border: 1px solid #2a3444; border-radius: 10px; padding: 0px 14px;
            selection-background-color: {primario}; selection-color: #ffffff;
        }}
        QLineEdit:hover {{ border: 1px solid #3b475a; }}
        QLineEdit:focus {{ border: 1.5px solid {primario}; background-color: #121b28; }}

        QPushButton#btnIngresar {{
            font-size: 15px; font-weight: 700; color: #ffffff; border: none; border-radius: 10px;
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {primario}, stop:1 {hover});
        }}
        QPushButton#btnIngresar:hover {{
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {hover}, stop:1 {presionado});
        }}
        QPushButton#btnIngresar:pressed {{ background-color: {presionado}; }}
        QPushButton#btnIngresar:disabled {{ background-color: #1f2a38; color: #6b778a; }}

        QPushButton#btnEnlace {{
            font-size: 13px; color: {_P["primario_texto"]}; background: transparent;
            border: none; padding: 6px 10px;
        }}
        QPushButton#btnEnlace:hover {{ color: #ffffff; text-decoration: underline; }}

        QToolTip {{ background-color: #1f2937; color: #e5e7eb; border: 1px solid #4b5563; padding: 4px 8px; }}
        """

    # ------------------------------------------------------------------
    def _alternar_password(self) -> None:
        visible = self.input_password.echoMode() == QLineEdit.Password
        self.input_password.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self._accion_ver.setIcon(icono("ojo_tachado" if visible else "ojo", _COLOR_ICONO, 18))
        self._accion_ver.setToolTip("Ocultar contraseña" if visible else "Mostrar contraseña")

    def _mostrar_error(self, texto: str) -> None:
        self.label_error.setText(texto)
        self.label_error.setVisible(True)

    def _limpiar_error(self) -> None:
        if self.label_error.isVisible():
            self.label_error.setVisible(False)

    def _iniciar_sesion(self) -> None:
        try:
            usuario = self.auth_service.iniciar_sesion(
                self.input_usuario.text(), self.input_password.text()
            )
        except AuthError as e:
            self._mostrar_error(str(e))
            self.input_password.selectAll()
            self.input_password.setFocus()
            return

        self.input_password.clear()
        self.sesion_iniciada.emit(usuario)
