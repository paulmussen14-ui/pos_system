"""Retención de registros: conserva solo los últimos DIAS_RETENCION días
(15 por defecto, ver config.py), contando el día de hoy.

Borra de forma DEFINITIVA, en este orden (por las llaves foráneas):
  1. devoluciones           de ventas antiguas
  2. venta_detalle          de ventas antiguas
  3. ventas                 anteriores al inicio de la ventana
  4. inventario_movimientos anteriores al inicio de la ventana

Como el historial de tickets de cada cliente sale de la tabla ventas,
también queda limitado a esa ventana.

No toca: productos (ni su stock_actual), clientes, caja_sesiones,
caja_movimientos, compras, historial_costos ni historial_precios.
"""

import sqlite3
from datetime import date

from config import APP_DATA_DIR, BACKUPS_DIR, DIAS_RETENCION
from utils.logger import logger

_MARCA_ULTIMA_EJECUCION = APP_DATA_DIR / "retencion_ultima.txt"
_BACKUPS_LIMPIEZA_A_CONSERVAR = 7
_FILAS_PARA_COMPACTAR = 5000


def limpiar_registros_antiguos(conn: sqlite3.Connection,
                               dias: int = DIAS_RETENCION,
                               simular: bool = False) -> dict:
    """Elimina registros fuera de la ventana de `dias` días (hoy incluido).
    Devuelve cuántas filas se borraron (o se borrarían, si simular=True)."""
    # Inicio de la ventana: 00:00 del día (hoy - (dias-1)). Con dias=15 se
    # conservan hoy y los 14 días anteriores.
    inicio = f"date('now','localtime','-{max(int(dias), 1) - 1} days')"
    sub_ventas = f"SELECT id FROM ventas WHERE fecha < {inicio}"

    pasos = [
        ("devoluciones", f"FROM devoluciones WHERE venta_id IN ({sub_ventas})"),
        ("venta_detalle", f"FROM venta_detalle WHERE venta_id IN ({sub_ventas})"),
        ("ventas", f"FROM ventas WHERE fecha < {inicio}"),
        ("inventario_movimientos", f"FROM inventario_movimientos WHERE fecha < {inicio}"),
    ]

    resultado = {}
    cur = conn.cursor()
    try:
        for tabla, resto in pasos:
            if simular:
                cur.execute(f"SELECT COUNT(*) {resto}")
                resultado[tabla] = cur.fetchone()[0]
            else:
                cur.execute(f"DELETE {resto}")
                resultado[tabla] = cur.rowcount
        if simular:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    return resultado


def compactar(conn: sqlite3.Connection) -> None:
    """Devuelve al disco el espacio liberado (VACUUM)."""
    conn.commit()
    conn.execute("VACUUM")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # que el archivo .db baje de tamaño ya


def _podar_backups_limpieza() -> None:
    antiguos = sorted(BACKUPS_DIR.glob("antes_limpieza_*.db"), reverse=True)
    for ruta in antiguos[_BACKUPS_LIMPIEZA_A_CONSERVAR:]:
        for sufijo in ("", "-wal", "-shm"):
            ruta.parent.joinpath(ruta.name + sufijo).unlink(missing_ok=True)


def ejecutar_retencion_diaria() -> dict | None:
    """Se llama al arrancar la app. Corre como máximo UNA vez por día.

    Si hay algo que borrar: primero crea un backup ("antes_limpieza_...",
    se conservan los 7 últimos) y recién entonces elimina. Nunca lanza
    excepciones hacia afuera: un fallo aquí no debe impedir abrir la app.
    Devuelve el detalle de lo borrado, o None si no hizo nada.
    """
    try:
        hoy = date.today().isoformat()
        if _MARCA_ULTIMA_EJECUCION.exists() and _MARCA_ULTIMA_EJECUCION.read_text().strip() == hoy:
            return None

        from database.connection import get_db
        from utils.backup_manager import crear_backup

        conn = get_db().get_connection()
        pendientes = limpiar_registros_antiguos(conn, simular=True)
        if not any(pendientes.values()):
            _MARCA_ULTIMA_EJECUCION.write_text(hoy)
            return None

        crear_backup("antes_limpieza")
        _podar_backups_limpieza()

        borrados = limpiar_registros_antiguos(conn)
        logger.info("Retención de %s días: %s", DIAS_RETENCION, borrados)

        if sum(borrados.values()) >= _FILAS_PARA_COMPACTAR:
            compactar(conn)

        _MARCA_ULTIMA_EJECUCION.write_text(hoy)
        return borrados
    except Exception:
        logger.exception("No se pudo ejecutar la limpieza diaria de registros antiguos")
        return None
