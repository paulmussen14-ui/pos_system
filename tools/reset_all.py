"""
Borra por completo la base de datos y todo lo relacionado (WAL, backups
opcional) para volver a empezar de cero. SOLO PARA PRUEBAS.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATABASE_PATH, APP_DATA_DIR

respuesta = input(
    f"Esto borrará TODA la base de datos en:\n{DATABASE_PATH}\n"
    "y no se puede deshacer. ¿Continuar? (escribe 'si' para confirmar): "
)
if respuesta.strip().lower() != "si":
    print("Cancelado.")
else:
    for sufijo in ("", "-wal", "-shm", "-journal"):
        archivo = DATABASE_PATH.parent / (DATABASE_PATH.name + sufijo)
        if archivo.exists():
            archivo.unlink()
            print(f"Borrado: {archivo}")
    print("Listo. La próxima vez que abras la app, te pedirá crear la cuenta admin de nuevo.")