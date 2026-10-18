"""Aviso al abrir la app cuando hay datos en la carpeta de datos antigua."""

from PySide6.QtWidgets import QMessageBox

from utils.datos_antiguos import (
    detectar_datos_antiguos, marcar_aviso_visto, copiar_a_copias_de_seguridad,
)
from utils.logger import logger

TEXTO_BOTON_COPIAR = "Copiar a Copias de seguridad"
TEXTO_BOTON_AHORA_NO = "Ahora no"
TEXTO_BOTON_NO_AVISAR = "No volver a avisar"


def _resumen(conteo: dict) -> str:
    return f"{conteo['ventas']} ventas, {conteo['productos']} productos, {conteo['clientes']} clientes"


def mostrar_aviso_si_corresponde(parent=None) -> None:
    """Revisa si hay datos en la carpeta antigua y, si los hay, avisa una vez.
    Nunca rompe el arranque: cualquier error queda en el log."""
    try:
        info = detectar_datos_antiguos()
    except Exception:
        logger.exception("No se pudo revisar si hay datos en la carpeta antigua")
        return
    if info is None:
        return

    caja = QMessageBox(parent)
    caja.setIcon(QMessageBox.Warning)
    caja.setWindowTitle("Se encontraron datos en la carpeta antigua")
    caja.setText(
        "La app está usando una base con menos datos que la de la carpeta antigua.\n\n"
        f"Carpeta antigua: {info['carpeta']}\n"
        f"   Contiene: {_resumen(info['antiguos'])}\n"
        f"Base actual: {_resumen(info['actuales'])}\n\n"
        "Si esos datos son tuyos, puedes copiarlos a \"Copias de seguridad\" y restaurarlos "
        "desde Configuración. Antes de restaurar, la app guarda una copia de lo que tienes ahora."
    )
    boton_copiar = caja.addButton(TEXTO_BOTON_COPIAR, QMessageBox.AcceptRole)
    caja.addButton(TEXTO_BOTON_AHORA_NO, QMessageBox.RejectRole)
    boton_no_avisar = caja.addButton(TEXTO_BOTON_NO_AVISAR, QMessageBox.DestructiveRole)
    caja.exec()
    elegido = caja.clickedButton()

    if elegido is boton_copiar:
        marcar_aviso_visto(info)
        try:
            destino = copiar_a_copias_de_seguridad(info)
        except Exception as exc:
            logger.exception("No se pudo copiar la base de la carpeta antigua")
            QMessageBox.warning(parent, "No se pudo copiar", f"No se pudo copiar la base antigua:\n{exc}")
            return
        QMessageBox.information(
            parent,
            "Copia lista",
            f"Se guardó como:\n{destino.name}\n\n"
            "Ahora ve a Configuración → Copias de seguridad, elige esa copia y presiona "
            "\"Restaurar\". Antes de restaurar, la app guarda una copia de tus datos actuales.",
        )
    elif elegido is boton_no_avisar:
        marcar_aviso_visto(info)
    # "Ahora no" (o cerrar la ventana): no se marca, se vuelve a avisar en el próximo arranque.
