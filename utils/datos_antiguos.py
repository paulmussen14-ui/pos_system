"""Detecta datos guardados en una carpeta de datos anterior de la app.

La carpeta de datos (%APPDATA%\\POSLocal) cambió de nombre en algún momento
(antes se llamaba "Sistema POS Local"). Si la app abre una base distinta a la
que se venía usando, parece que "se perdieron" ventas, productos o imágenes
cuando en realidad siguen en la otra carpeta. Este módulo lo detecta para
poder avisar y ofrecer recuperarlos con la restauración de backups de siempre.

Solo se avisa cuando la base antigua tiene MÁS datos que la actual (una base
antigua vacía no molesta), y una sola vez por cada estado de esa base: el
aviso se recuerda en APP_DATA_DIR/aviso_datos_antiguos.txt.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from config import APP_DATA_DIR, BACKUPS_DIR
from database.connection import get_db
from utils.logger import logger

# Carpetas de datos que usó la app antes (hermanas de APP_DATA_DIR).
CARPETAS_ANTIGUAS = ("Sistema POS Local",)

_TABLAS_CONTADAS = ("ventas", "productos", "clientes")
_ARCHIVO_AVISO = APP_DATA_DIR / "aviso_datos_antiguos.txt"


def _contar(conexion: sqlite3.Connection) -> dict[str, int]:
    """Cuenta los registros de las tablas principales (0 si la tabla no existe)."""
    conteo = {}
    for tabla in _TABLAS_CONTADAS:
        try:
            conteo[tabla] = int(conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
        except sqlite3.Error:
            conteo[tabla] = 0
    return conteo


def _abrir_solo_lectura(base: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{base.resolve().as_uri()}?mode=ro", uri=True)


def _firma(base: Path) -> str:
    estado = base.stat()
    return f"{estado.st_size}:{int(estado.st_mtime)}"


def _aviso_ya_visto(firma: str) -> bool:
    try:
        return _ARCHIVO_AVISO.read_text(encoding="utf-8").strip() == firma
    except OSError:
        return False


def detectar_datos_antiguos() -> dict | None:
    """
    Devuelve un dict con la carpeta, la base y los conteos (antiguos y
    actuales) si hay una carpeta antigua con más datos que la actual y el
    aviso todavía no se mostró para ese estado; si no, None. Nunca modifica
    la base antigua (se abre en solo lectura).
    """
    actuales = _contar(get_db().get_connection())

    for nombre in CARPETAS_ANTIGUAS:
        carpeta = APP_DATA_DIR.parent / nombre
        base = carpeta / "pos_local.db"
        if not base.is_file() or carpeta.resolve() == APP_DATA_DIR.resolve():
            continue

        try:
            conexion = _abrir_solo_lectura(base)
            try:
                antiguos = _contar(conexion)
            finally:
                conexion.close()
        except sqlite3.Error:
            logger.exception(f"No se pudo leer la base de la carpeta antigua: {base}")
            continue

        if sum(antiguos.values()) <= sum(actuales.values()):
            continue

        firma = _firma(base)
        if _aviso_ya_visto(firma):
            continue
        return {"carpeta": carpeta, "base": base, "firma": firma, "antiguos": antiguos, "actuales": actuales}
    return None


def marcar_aviso_visto(info: dict) -> None:
    """Recuerda que ya se avisó de esta base antigua (no vuelve a avisar hasta que cambie)."""
    try:
        _ARCHIVO_AVISO.write_text(info["firma"], encoding="utf-8")
    except OSError:
        logger.exception("No se pudo guardar que el aviso de datos antiguos ya se mostró")


def copiar_a_copias_de_seguridad(info: dict) -> Path:
    """
    Copia la base antigua a la carpeta de copias de seguridad como
    datos_antiguos_<fecha>.db, para poder restaurarla desde Configuración →
    Copias de seguridad (que antes guarda una copia de los datos actuales).
    Usa la API de respaldo de sqlite3, que también incluye lo que esté en el
    archivo -wal; la base antigua no se modifica.
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    destino = BACKUPS_DIR / f"datos_antiguos_{datetime.now():%Y%m%d_%H%M%S}.db"

    origen = _abrir_solo_lectura(info["base"])
    try:
        copia = sqlite3.connect(str(destino))
        try:
            origen.backup(copia)
        finally:
            copia.close()
    finally:
        origen.close()
    logger.info(f"Base de la carpeta antigua copiada a: {destino}")
    return destino
