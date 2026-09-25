"""
Borra TODA la base de datos (ventas, compras, clientes, productos, caja,
usuarios, todo) para volver a empezar de cero, como si la app se instalara
por primera vez.

Antes de borrar, crea automáticamente un backup de seguridad en la carpeta
de backups, por si te arrepientes o borraste por error. Ese backup NO se
borra con este script — solo el archivo activo de la base de datos.

USO (con la app cerrada):
    python tools/reset_all.py

Después de correrlo, la próxima vez que abras la app te va a pedir crear
la cuenta de administrador de nuevo, como una instalación nueva.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATABASE_PATH

FRASE_CONFIRMACION = "BORRAR TODO"


def _hacer_backup_de_seguridad() -> Path | None:
    """Intenta respaldar la base actual antes de borrar. Si la base no
    existe todavía (primera vez) o el backup falla, simplemente avisa y
    continúa: no tiene sentido bloquear el borrado por esto."""
    if not DATABASE_PATH.exists():
        return None
    try:
        from utils.backup_manager import crear_backup
        return crear_backup("antes_de_reset_all")
    except Exception as e:
        print(f"Aviso: no se pudo crear el backup de seguridad ({e}).")
        return None


def _cerrar_conexion_propia() -> None:
    """El backup abre una conexión a la base (vía get_db()) que se queda
    viva en este mismo proceso. En Windows no se puede borrar un archivo
    mientras algo lo tiene abierto -- ni siquiera el propio script -- así
    que hay que cerrarla antes de borrar."""
    try:
        from database.connection import get_db
        get_db().close()
    except Exception:
        pass


def _borrar_base_y_auxiliares() -> None:
    for sufijo in ("", "-wal", "-shm", "-journal"):
        archivo = DATABASE_PATH.parent / (DATABASE_PATH.name + sufijo)
        if not archivo.exists():
            continue
        try:
            archivo.unlink()
            print(f"Borrado: {archivo}")
        except PermissionError:
            print(
                f"No se pudo borrar {archivo}: otro programa lo tiene abierto.\n"
                "Cierra la aplicación POS Local (revisa también el Administrador "
                "de tareas por si quedó un proceso POSLocal.exe colgado) y vuelve "
                "a correr este script."
            )
            raise


def main() -> None:
    print(
        "Esto va a borrar POR COMPLETO la base de datos en:\n"
        f"  {DATABASE_PATH}\n"
        "Se perderán ventas, compras, clientes, productos, caja y usuarios.\n"
        "No se puede deshacer (aunque se hace un backup de seguridad antes).\n"
    )
    respuesta = input(
        f"Para confirmar, escribe exactamente: {FRASE_CONFIRMACION}\n> "
    )
    if respuesta.strip() != FRASE_CONFIRMACION:
        print("Cancelado. No se borró nada.")
        return

    backup = _hacer_backup_de_seguridad()
    if backup:
        print(f"Backup de seguridad creado en: {backup}")

    _cerrar_conexion_propia()
    _borrar_base_y_auxiliares()

    print(
        "\nListo. La próxima vez que abras la app, te va a pedir crear la "
        "cuenta de administrador de nuevo, como en una instalación nueva."
    )


if __name__ == "__main__":
    main()