"""Borra de TU base de datos los datos que dejó el test_devoluciones.py viejo
(el primero que te di, que por error usaba la base real).

Seguridad:
  1. Hace un backup completo ANTES de tocar nada.
  2. Solo borra lo que coincide con la "huella" exacta del test:
       - productos llamados P24-0, P24-1, ... (precio 2, sin marca,
         sin categoria ni proveedor)
       - el usuario 'a' (nombre 'A', hash 'x')
       - las ventas que contienen SOLO esos productos
  3. Te muestra que va a borrar y pide escribir 'si'.
  4. Si encuentra algo raro (ej. una venta que mezcla productos de prueba
     con productos reales), se detiene sin borrar nada.

Uso (con la app CERRADA):   python limpiar_datos_de_prueba.py
"""
import re
import sqlite3
import sys
from datetime import datetime

from config import DATABASE_PATH, BACKUPS_DIR


def main() -> int:
    print(f"Base de datos: {DATABASE_PATH}")
    if not DATABASE_PATH.exists():
        print("No existe la base de datos. Nada que limpiar.")
        return 1

    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # ---- 1) Identificar lo que es del test ----
    prods = [
        r for r in conn.execute(
            "SELECT * FROM productos WHERE precio_venta_actual = 2 "
            "AND COALESCE(marca,'') = '' AND categoria_id IS NULL AND proveedor_id IS NULL"
        ).fetchall()
        if re.fullmatch(r"P24-\d+", r["nombre"])
    ]
    ids = [p["id"] for p in prods]
    usuario_a = conn.execute(
        "SELECT id FROM usuarios WHERE usuario = 'a' AND nombre = 'A' AND password_hash = 'x'"
    ).fetchone()

    if not ids and not usuario_a:
        print("No encontre datos de prueba. Nada que limpiar.")
        return 0

    marcas = ",".join("?" * len(ids)) if ids else "NULL"
    ventas_ids = [
        r[0] for r in conn.execute(
            f"SELECT DISTINCT venta_id FROM venta_detalle WHERE producto_id IN ({marcas})", ids
        ).fetchall()
    ] if ids else []

    # Seguridad: cada venta debe contener SOLO productos de prueba.
    for vid in ventas_ids:
        ajenos = conn.execute(
            f"SELECT COUNT(*) FROM venta_detalle WHERE venta_id = ? AND producto_id NOT IN ({marcas})",
            [vid] + ids,
        ).fetchone()[0]
        if ajenos:
            print(f"ALTO: la venta #{vid} mezcla productos de prueba con productos reales.")
            print("No se borro nada. Avisame para revisarlo a mano.")
            return 2

    print("\nSe van a borrar:")
    for p in prods:
        print(f"  - producto #{p['id']}  {p['nombre']}")
    print(f"  - ventas de prueba: {ventas_ids or 'ninguna'}")
    print(f"  - usuario de prueba 'a': {'si' if usuario_a else 'no'}")
    print("  - sus devoluciones, movimientos de inventario e historial de precios")

    if input("\nEscribe 'si' para continuar: ").strip().lower() != "si":
        print("Cancelado. No se toco nada.")
        return 0

    # ---- 2) Backup ----
    destino = BACKUPS_DIR / f"antes_de_limpiar_pruebas_{datetime.now():%Y%m%d_%H%M%S}.db"
    respaldo = sqlite3.connect(str(destino))
    conn.backup(respaldo)
    respaldo.close()
    print(f"Backup creado: {destino}")

    # ---- 3) Borrar en orden (respetando claves foraneas) ----
    vm = ",".join("?" * len(ventas_ids)) if ventas_ids else "NULL"
    with conn:
        if ids:
            conn.execute(f"DELETE FROM devoluciones WHERE producto_id IN ({marcas})", ids)
            conn.execute(f"DELETE FROM inventario_movimientos WHERE producto_id IN ({marcas})", ids)
            conn.execute(f"DELETE FROM historial_precios WHERE producto_id IN ({marcas})", ids)
            conn.execute(f"DELETE FROM historial_costos WHERE producto_id IN ({marcas})", ids)
            conn.execute(f"DELETE FROM producto_presentaciones WHERE producto_id IN ({marcas})", ids)
        if ventas_ids:
            conn.execute(f"DELETE FROM caja_movimientos WHERE tipo IN ('venta','egreso') "
                         f"AND referencia_id IN ({vm}) AND descripcion LIKE '%enta #%'", ventas_ids)
            conn.execute(f"DELETE FROM devoluciones WHERE venta_id IN ({vm})", ventas_ids)
            conn.execute(f"DELETE FROM inventario_movimientos WHERE referencia_id IN ({vm}) "
                         f"AND referencia_tipo IN ('venta','anulacion','devolucion')", ventas_ids)
            conn.execute(f"DELETE FROM venta_detalle WHERE venta_id IN ({vm})", ventas_ids)
            conn.execute(f"DELETE FROM ventas WHERE id IN ({vm})", ventas_ids)
        if ids:
            conn.execute(f"DELETE FROM productos WHERE id IN ({marcas})", ids)
        if usuario_a:
            conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_a["id"],))

    print("Listo. Datos de prueba eliminados.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())