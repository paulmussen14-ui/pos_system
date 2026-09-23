"""
Backups de la base de datos SQLite.

Usa la API nativa de respaldo de sqlite3 (Connection.backup), que es segura
incluso con la base de datos en uso (a diferencia de copiar el archivo .db
directamente, que podría corromperse en modo WAL).
"""

import os
import re
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

from config import BACKUPS_DIR, DATABASE_PATH
from database.connection import get_db
from utils.logger import logger


def _limpiar_nombre(texto: str) -> str:
    """Deja solo letras, números, guion y guion bajo (nombre de archivo seguro)."""
    return re.sub(r"[^\w\-]+", "_", texto).strip("_") or "backup"


def crear_backup(nombre_personalizado: str | None = None) -> Path:
    """Crea un backup consistente de la base de datos actual."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefijo = _limpiar_nombre(nombre_personalizado) if nombre_personalizado else "backup"
    nombre_archivo = f"{prefijo}_{timestamp}.db"
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


def _borrar_con_auxiliares(ruta: Path) -> None:
    """Borra un archivo .db junto con sus -wal y -shm (si existen)."""
    for sufijo in ("", "-wal", "-shm"):
        Path(str(ruta) + sufijo).unlink(missing_ok=True)


def _validar_base(ruta: Path) -> None:
    """Verifica que el archivo sea una base SQLite íntegra del POS."""
    conn = sqlite3.connect(str(ruta))
    try:
        resultado = conn.execute("PRAGMA integrity_check").fetchone()
        if not resultado or resultado[0] != "ok":
            raise ValueError("El archivo de backup está dañado.")
        tiene_usuarios = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'usuarios'"
        ).fetchone()
        if not tiene_usuarios:
            raise ValueError("El archivo no es una base de datos de este sistema POS.")
    finally:
        conn.close()


def restaurar_backup(ruta_backup: Path) -> None:
    """
    Restaura un backup de forma segura. IMPORTANTE: requiere reiniciar la
    aplicación después, ya que la conexión activa queda cerrada.

    Pasos:
    1. Copia el backup a un archivo temporal junto a la base y lo valida
       (integridad + que sea una base de este POS). Si falla, no se toca nada.
    2. Guarda un backup de seguridad de la base actual ("antes_de_restaurar").
    3. Cierra la conexión y borra los archivos -wal/-shm de la base vieja
       (si quedaran, SQLite los aplicaría sobre la base restaurada).
    4. Reemplaza la base de forma atómica.
    """
    ruta_backup = Path(ruta_backup)
    if not ruta_backup.exists():
        raise FileNotFoundError(f"No se encontró el archivo de backup: {ruta_backup}")

    temporal = Path(str(DATABASE_PATH) + ".restaurando")
    shutil.copy2(str(ruta_backup), str(temporal))
    try:
        _validar_base(temporal)
    except Exception:
        _borrar_con_auxiliares(temporal)
        raise

    try:
        crear_backup("antes_de_restaurar")
    except Exception:
        _borrar_con_auxiliares(temporal)
        raise

    get_db().close()
    for sufijo in ("-wal", "-shm"):
        Path(str(DATABASE_PATH) + sufijo).unlink(missing_ok=True)
    os.replace(str(temporal), str(DATABASE_PATH))
    logger.info(f"Base de datos restaurada desde: {ruta_backup}")