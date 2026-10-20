"""
Punto de entrada de la aplicación POS Local.

Flujo:
    - Muestra un splash screen mientras se inicializa la base de datos.
    - Si no existe cuenta -> SetupAdminWindow
    - Si existe cuenta -> LoginWindow (con opción "Olvidé mi contraseña" -> RecoveryWindow)
    - Al iniciar sesión correctamente -> MainWindow
    - Al cerrar sesión desde MainWindow -> vuelve a LoginWindow
"""

import faulthandler
import sys
import time

from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QThread, QTimer, QPropertyAnimation

from database.connection import get_db  # inicializa la BD y aplica el esquema
from services.auth_service import AuthService
from ui.login.setup_admin_window import SetupAdminWindow
from ui.login.login_window import LoginWindow
from ui.login.recovery_window import RecoveryWindow
from ui.main_window import MainWindow
from ui.widgets.aviso_datos_antiguos import mostrar_aviso_si_corresponde
from services.configuracion_service import ConfiguracionService
from utils.logger import logger
from utils.retencion import ejecutar_retencion_diaria
from config import APP_ICON_PATH, APP_LOGO_PATH, LOGS_DIR


_ultimo_aviso_error = 0.0


def _excepthook(tipo, valor, tb) -> None:
    """Registra en el log cualquier excepción no controlada (por ejemplo,
    dentro de un slot de Qt) y avisa al usuario. Sin esto, en el .exe sin
    consola el error se pierde en silencio y el botón "no hace nada"."""
    global _ultimo_aviso_error
    logger.critical("Error no controlado", exc_info=(tipo, valor, tb))
    try:
        app = QApplication.instance()
        # Solo desde el hilo de la interfaz, y como máximo un aviso cada 5 segundos.
        if app is None or QThread.currentThread() is not app.thread():
            return
        ahora = time.monotonic()
        if ahora - _ultimo_aviso_error < 5:
            return
        _ultimo_aviso_error = ahora
        QMessageBox.critical(
            None, "Ocurrió un error inesperado",
            "No se pudo completar la operación.\n\n"
            "Si estabas guardando algo (una venta, una reserva, un cobro), revisa que se haya "
            "registrado antes de repetirlo. Si el problema continúa, envía el archivo de "
            "registro (log) a soporte.\n\n"
            f"Detalle: {tipo.__name__}: {valor}")
    except Exception:
        pass  # el aviso nunca debe causar otro error


sys.excepthook = _excepthook

# Si el programa se cierra de golpe por un fallo interno de Qt (sin mensaje de error de Python),
# aquí queda escrito dónde pasó: %APPDATA%\POSLocal\logs\crash.log
try:
    _archivo_crash = open(LOGS_DIR / "crash.log", "a", encoding="utf-8")
    faulthandler.enable(file=_archivo_crash, all_threads=True)
except Exception:
    pass


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
        # Si hay datos en la carpeta de datos antigua, se avisa (una sola vez
        # por cada estado de esa carpeta). Se hace con la ventana ya visible.
        QTimer.singleShot(600, lambda: mostrar_aviso_si_corresponde(ventana))

    def _reemplazar_ventana(self, nueva_ventana) -> None:
        if self.ventana_actual is not None:
            self.ventana_actual.close()
        self.ventana_actual = nueva_ventana
        if not isinstance(nueva_ventana, MainWindow):
            nueva_ventana.show()


def _reparar_imagenes_guardadas() -> None:
    """Reconecta el logo y el QR de Yape con su archivo si la base perdió la
    ruta (ver ConfiguracionService.reparar_rutas_imagenes). Nunca rompe el arranque."""
    try:
        ConfiguracionService().reparar_rutas_imagenes()
    except Exception:
        logger.exception("No se pudieron reparar las rutas del logo / QR")


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
        _reparar_imagenes_guardadas()
        if splash:
            splash.showMessage(
                "Limpiando registros antiguos...",
                Qt.AlignBottom | Qt.AlignHCenter,
                Qt.darkGray,
            )
            app.processEvents()
        ejecutar_retencion_diaria()  # 1 vez al día; backup previo; nunca rompe el arranque
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