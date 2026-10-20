import os
import sys
from pathlib import Path

APP_NAME = "POSLocal"
APP_VERSION = "2.1.1"


def _get_app_data_dir() -> Path:
    """Carpeta de datos persistente (BD, backups, logs) — SIEMPRE %APPDATA%,
    sin importar si está empaquetado o en desarrollo."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home()))
    else:
        base = str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def _get_base_dir() -> Path:
    """Carpeta de recursos de solo lectura (QSS, íconos, schema.sql):
    temporal si está empaquetado (frozen), o el código fuente en desarrollo."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


# --- Datos persistentes del usuario (escribibles) ---
APP_DATA_DIR = _get_app_data_dir()
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = APP_DATA_DIR / "pos_local.db"
BACKUPS_DIR = APP_DATA_DIR / "backups"
LOGS_DIR = APP_DATA_DIR / "logs"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# --- Recursos empaquetados (solo lectura) ---
BASE_DIR = _get_base_dir()
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"
STYLES_DIR = BASE_DIR / "resources" / "styles"
ICONS_DIR = BASE_DIR / "resources" / "icons"
LOGO_DIR = BASE_DIR / "resources" / "logo"
APP_ICON_PATH = ICONS_DIR / "app.ico"
APP_LOGO_PATH = ICONS_DIR / "logo_completo.png"
APP_LOGO_SIDEBAR_PATH = ICONS_DIR / "logo_sidebar.png"

# Constantes de negocio
# Días de historial que muestran las pantallas (ventas, movimientos de inventario, reportes, etc.).
# Cambiar aquí cambia todo. Si BORRAR_HISTORIAL_ANTIGUO es True, lo más antiguo además se
# elimina solo al abrir la app; con False (por defecto) el historial completo se conserva.
DIAS_RETENCION = 15
BORRAR_HISTORIAL_ANTIGUO = False
"""Con False (lo normal) las pantallas muestran solo los últimos DIAS_RETENCION días pero
NADA se borra: el historial completo queda guardado en la base de datos. Con True se vuelve
al comportamiento anterior: al abrir la app se borran (con backup previo) las ventas y los
movimientos de inventario más antiguos que DIAS_RETENCION días."""
STOCK_BAJO_DEFAULT_MINIMO = 5
RECOVERY_CODE_LENGTH_BYTES = 8  # genera código de 16 caracteres hex