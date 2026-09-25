"""Reconstruye los índices de búsqueda (FTS5) de productos y clientes.

Por qué: schema.sql crea productos_fts y clientes_fts con "IF NOT EXISTS".
En una base que YA tenía datos, esas tablas se crean VACÍAS (los triggers
solo indexan lo que se inserte desde ese momento). Si la búsqueda usa FTS,
los productos y clientes antiguos NO aparecerían en los resultados.

Este script:
1. Hace una copia de seguridad de la base de datos.
2. Reconstruye ambos índices con 'rebuild' (es seguro repetirlo).
3. Prueba que cada producto y cada cliente se pueda encontrar por su nombre.

Uso (con la app cerrada):
    python verificar_fts.py
    python verificar_fts.py "C:\\ruta\\a\\pos_local.db"
"""

import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime


def ruta_por_defecto() -> str:
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "POSLocal", "pos_local.db")


def hacer_backup(ruta_db: str) -> str:
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_backup = f"{ruta_db}.antes_fts_{marca}.bak"
    shutil.copy2(ruta_db, ruta_backup)
    return ruta_backup


def consulta_segura(nombre: str) -> str:
    """Convierte un nombre en una consulta FTS5 que no falla con
    comillas, guiones u otros símbolos: cada palabra va entre comillas."""
    palabras = re.findall(r"\w+", nombre)
    partes = []
    for palabra in palabras:
        partes.append('"' + palabra + '"')
    return " ".join(partes)


def probar_tabla(conexion, tabla: str, tabla_fts: str) -> list:
    """Devuelve los (id, nombre) que NO se encuentran en el índice."""
    filas = conexion.execute(f"SELECT id, nombre FROM {tabla}").fetchall()
    no_encontrados = []

    for fila in filas:
        id_fila = fila[0]
        nombre = fila[1]
        consulta = consulta_segura(nombre)
        if consulta == "":
            continue

        resultado = conexion.execute(
            f"SELECT rowid FROM {tabla_fts} WHERE {tabla_fts} MATCH ? AND rowid = ?",
            (consulta, id_fila),
        ).fetchone()

        if resultado is None:
            no_encontrados.append((id_fila, nombre))

    return no_encontrados


def main() -> None:
    if len(sys.argv) > 1:
        ruta_db = sys.argv[1]
    else:
        ruta_db = ruta_por_defecto()

    if not os.path.exists(ruta_db):
        print(f"No se encontró la base de datos en: {ruta_db}")
        return

    ruta_backup = hacer_backup(ruta_db)
    print(f"Copia de seguridad creada: {ruta_backup}")

    conexion = sqlite3.connect(ruta_db)
    try:
        for tabla, tabla_fts in (("productos", "productos_fts"), ("clientes", "clientes_fts")):
            total = conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]

            conexion.execute(f"INSERT INTO {tabla_fts}({tabla_fts}) VALUES('rebuild')")
            conexion.commit()

            faltan = probar_tabla(conexion, tabla, tabla_fts)
            print(f"{tabla}: {total} registros, {len(faltan)} no encontrados en el índice")
            for id_fila, nombre in faltan[:10]:
                print(f"   - id {id_fila}: {nombre}")
    finally:
        conexion.close()


if __name__ == "__main__":
    main()