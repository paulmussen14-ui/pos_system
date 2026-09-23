"""
Backups de la base de datos SQLite.

Usa la API nativa de respaldo de sqlite3 (Connection.backup), que es segura
incluso con la base de datos en uso (a diferencia de copiar el archivo .db
directamente, que podría corromperse en modo WAL).
"""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

from config import BACKUPS_DIR, DATABASE_PATH
from database.connection import get_db
from utils.logger import logger


def crear_backup(nombre_personalizado: str | None = None) -> Path:
    """Crea un backup consistente de la base de datos actual."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"{nombre_personalizado or 'backup'}_{timestamp}.db"
    destino = BACKUPS_DIR / nombre_archivo

    origen_conn = get_db().get_connection()
    destino_conn = sqlite3.connect(str(destino))
    try:
        origen_conn.backup(destino_conn)
        logger.info(f"Backup creado: {destino}")
    finally:
        destino_conn.close()

    return destino


def listar_backups() -> list[Path]:
    return sorted(BACKUPS_DIR.glob("*.db"), reverse=True)


def restaurar_backup(ruta_backup: Path) -> None:
    """
    Restaura un backup. IMPORTANTE: requiere reiniciar la aplicación después,
    ya que la conexión activa apunta al archivo original.
    """
    if not ruta_backup.exists():
        raise FileNotFoundError(f"No se encontró el archivo de backup: {ruta_backup}")

    get_db().close()
    shutil.copy2(str(ruta_backup), str(DATABASE_PATH))
    logger.info(f"Base de datos restaurada desde: {ruta_backup}")
