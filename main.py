"""
Punto de entrada de la aplicación POS Local.

Flujo:
    - Muestra un splash screen mientras se inicializa la base de datos.
    - Si no existe cuenta -> SetupAdminWindow
    - Si existe cuenta -> LoginWindow (con opción "Olvidé mi contraseña" -> RecoveryWindow)
    - Al iniciar sesión correctamente -> MainWindow
    - Al cerrar sesión desde MainWindow -> vuelve a LoginWindow
"""

import sys

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation

from database.connection import get_db  # inicializa la BD y aplica el esquema
from services.auth_service import AuthService
from ui.login.setup_admin_window import SetupAdminWindow
from ui.login.login_window import LoginWindow
from ui.login.recovery_window import RecoveryWindow
from ui.main_window import MainWindow
from utils.logger import logger
from config import APP_ICON_PATH, APP_LOGO_PATH


def _excepthook(tipo, valor, tb) -> None:
    """Registra en el log cualquier excepción no controlada (por ejemplo,
    dentro de un slot de Qt). Sin esto, en el .exe sin consola el error se
    pierde en silencio."""
    logger.critical("Error no controlado", exc_info=(tipo, valor, tb))


sys.excepthook = _excepthook


class AppController:
    """Mantiene referencias vivas a las ventanas para evitar que Python las recolecte."""

    def __init__(self, app: QApplication):
        self.app = app
        self.auth_service = AuthService()
        self.ventana_actual = None
        self.iniciar()

    def iniciar(self) -> None:
        if self.auth_service.requiere_configuracion_inicial():
            self._mostrar_setup()
        else:
            self._mostrar_login()

    def _mostrar_setup(self) -> None:
        ventana = SetupAdminWindow()
        ventana.cuenta_creada.connect(self._mostrar_login)
        self._reemplazar_ventana(ventana)

    def _mostrar_login(self) -> None:
        ventana = LoginWindow()
        ventana.sesion_iniciada.connect(self._abrir_main_window)
        ventana.ir_a_recuperacion.connect(self._mostrar_recuperacion)
        self._reemplazar_ventana(ventana)

    def _mostrar_recuperacion(self) -> None:
        ventana = RecoveryWindow()
        ventana.password_restablecida.connect(self._mostrar_login)
        ventana.volver_a_login.connect(self._mostrar_login)
        self._reemplazar_ventana(ventana)

    def _abrir_main_window(self, usuario) -> None:
        ventana = MainWindow(usuario, cerrar_sesion_callback=self._mostrar_login)
        self._reemplazar_ventana(ventana)
        ventana.showMaximized()

    def _reemplazar_ventana(self, nueva_ventana) -> None:
        if self.ventana_actual is not None:
            self.ventana_actual.close()
        self.ventana_actual = nueva_ventana
        if not isinstance(nueva_ventana, MainWindow):
            nueva_ventana.show()


def _crear_splash() -> QSplashScreen | None:
    """Crea y muestra el splash screen con el logo, si el archivo existe."""
    if not APP_LOGO_PATH.exists():
        return None

    pixmap = QPixmap(str(APP_LOGO_PATH))
    pixmap = pixmap.scaledToWidth(420, Qt.SmoothTransformation)

    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.FramelessWindowHint)
    splash.showMessage(
        "Iniciando POS Local...",
        Qt.AlignBottom | Qt.AlignHCenter,
        Qt.darkGray,
    )
    splash.show()
    return splash


def _cerrar_splash_con_fundido(splash: QSplashScreen) -> None:
    """Desvanece el splash gradualmente en vez de cerrarlo de golpe."""
    animacion = QPropertyAnimation(splash, b"windowOpacity")
    animacion.setDuration(350)
    animacion.setStartValue(1.0)
    animacion.setEndValue(0.0)
    animacion.finished.connect(splash.close)
    animacion.start()
    splash._animacion_fundido = animacion  # evita que el garbage collector la borre a mitad de camino


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # sin esto Windows pinta los headers de las tablas con su tema nativo
    # y el background-color de QHeaderView::section del QSS queda ignorado (se ve blanco siempre).
    app.setApplicationName("POS Local")

    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    splash = _crear_splash()
    app.processEvents()

    try:
        get_db()  # fuerza inicialización de la base de datos al arrancar
        if splash:
            splash.showMessage(
                "Cargando módulos...",
                Qt.AlignBottom | Qt.AlignHCenter,
                Qt.darkGray,
            )
            app.processEvents()

        controlador = AppController(app)
    except Exception:
        if splash:
            splash.close()
        logger.exception("Error fatal al iniciar la aplicación")
        raise

    if splash:
        QTimer.singleShot(1200, lambda: _cerrar_splash_con_fundido(splash))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()