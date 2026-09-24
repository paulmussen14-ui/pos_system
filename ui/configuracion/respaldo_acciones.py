"""Acciones de respaldo para la pantalla de Configuración.

- exportar_productos_ui / importar_productos_ui: migrar el catálogo a otra PC.
- restaurar_backup_ui: restaura un backup completo de la base y REINICIA la
  aplicación de forma controlada (la conexión queda cerrada tras restaurar).
"""

import os
import subprocess
import sys
from datetime import datetime

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from config import BACKUPS_DIR
from utils.backup_manager import BaseCerradaError, restaurar_backup
from services.backup_productos_service import BackupProductosService, ProductoBackupError
from utils.logger import logger


def reiniciar_aplicacion() -> None:
    """Abre una instancia nueva del programa y cierra la actual."""
    if getattr(sys, "frozen", False):          # .exe empaquetado
        comando = [sys.executable, *sys.argv[1:]]
    else:                                       # python main.py
        comando = [sys.executable, *sys.argv]

    opciones = {}
    if os.name == "nt":
        opciones["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(comando, cwd=os.getcwd(), close_fds=True, **opciones)
    except Exception:
        logger.exception("No se pudo reiniciar la aplicación automáticamente")
        QMessageBox.warning(None, "Reinicio", "Cierra el programa y ábrelo de nuevo para continuar.")
    QApplication.quit()


def exportar_productos_ui(parent) -> None:
    nombre = f"productos_{datetime.now():%Y%m%d}.json"
    ruta, _ = QFileDialog.getSaveFileName(parent, "Exportar productos", nombre, "Productos (*.json)")
    if not ruta:
        return
    try:
        cantidad = BackupProductosService().exportar(ruta)
    except Exception as e:
        logger.exception("Error al exportar productos")
        QMessageBox.critical(parent, "Exportar productos", f"No se pudo exportar:\n{e}")
        return
    QMessageBox.information(parent, "Exportar productos", f"Se exportaron {cantidad} productos a:\n{ruta}")


def importar_productos_ui(parent, usuario_id: int | None = None) -> dict | None:
    """Devuelve el resumen si se importó algo, para que la pantalla se refresque."""
    ruta, _ = QFileDialog.getOpenFileName(parent, "Importar productos", "", "Productos (*.json)")
    if not ruta:
        return None
    try:
        resumen = BackupProductosService().importar(ruta, usuario_id)
    except ProductoBackupError as e:
        QMessageBox.warning(parent, "Importar productos", str(e))
        return None
    except Exception as e:
        logger.exception("Error al importar productos")
        QMessageBox.critical(parent, "Importar productos", f"No se pudo importar:\n{e}")
        return None

    mensaje = f"Productos creados: {resumen['creados']}"
    omitidos = resumen["omitidos"]
    if omitidos:
        mensaje += (f"\nOmitidos por ya existir o estar repetidos: {len(omitidos)}\n"
                    + ", ".join(omitidos[:10]) + ("…" if len(omitidos) > 10 else ""))
    QMessageBox.information(parent, "Importar productos", mensaje)
    return resumen


def restaurar_backup_ui(parent, ruta=None) -> None:
    if ruta is None:
        ruta, _ = QFileDialog.getOpenFileName(
            parent, "Elegir backup a restaurar", str(BACKUPS_DIR), "Base de datos (*.db)"
        )
    if not ruta:
        return

    respuesta = QMessageBox.warning(
        parent, "Restaurar backup",
        "Se reemplazará TODA la información actual (ventas, productos, clientes, "
        "usuarios y configuración) por la del backup elegido.\n\n"
        "Antes se guardará una copia de seguridad de lo actual, y la aplicación se "
        "reiniciará al terminar.\n\n¿Continuar?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    )
    if respuesta != QMessageBox.Yes:
        return

    try:
        restaurar_backup(ruta)
    except BaseCerradaError as e:
        # La conexión ya se cerró: hay que reiniciar sí o sí.
        QMessageBox.critical(parent, "Restaurar backup", str(e))
        reiniciar_aplicacion()
        return
    except Exception as e:
        # Falló antes de tocar la base actual: se puede seguir trabajando.
        logger.exception("Error al restaurar backup")
        QMessageBox.critical(parent, "Restaurar backup", f"No se pudo restaurar:\n{e}")
        return

    QMessageBox.information(parent, "Restaurar backup",
                            "Backup restaurado. La aplicación se reiniciará ahora.")
    reiniciar_aplicacion()
