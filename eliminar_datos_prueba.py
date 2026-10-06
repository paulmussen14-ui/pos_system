"""
Elimina los datos de prueba insertados por generar_datos_prueba.py.

Asume que fueron los ÚLTIMOS registros insertados en cada tabla
(porque los IDs de SQLite son autoincrementales y nada más se
insertó después). Antes de borrar, te muestra una muestra y pide
confirmación explícita escribiendo "SI".

Si hiciste backup ANTES de correr el generador, es más seguro
simplemente restaurar ese backup desde la app en vez de usar este
script.

Uso:
    python eliminar_datos_prueba.py --db "ruta\al\pos_local.db"
"""

import argparse
import sqlite3
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="Ruta al archivo .db")
    parser.add_argument("--productos", type=int, default=500)
    parser.add_argument("--clientes", type=int, default=400)
    parser.add_argument("--ventas", type=int, default=20_000)
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()

    cur.execute(f"SELECT id, nombre FROM productos ORDER BY id DESC LIMIT {args.productos}")
    productos = cur.fetchall()
    cur.execute(f"SELECT id, nombre FROM clientes ORDER BY id DESC LIMIT {args.clientes}")
    clientes = cur.fetchall()
    cur.execute(f"SELECT id, fecha, total FROM ventas ORDER BY id DESC LIMIT {args.ventas}")
    ventas = cur.fetchall()

    venta_ids = [v[0] for v in ventas]
    producto_ids = [p[0] for p in productos]
    cliente_ids = [c[0] for c in clientes]

    cur.execute(
        f"SELECT COUNT(*) FROM venta_detalle WHERE venta_id IN ({','.join('?' * len(venta_ids))})",
        venta_ids,
    ) if venta_ids else None
    n_detalle = cur.fetchone()[0] if venta_ids else 0

    print("Se van a eliminar:")
    print(f"  - {len(ventas)} ventas (y {n_detalle} líneas de venta_detalle)")
    print(f"  - {len(productos)} productos")
    print(f"  - {len(clientes)} clientes")
    print("\nMuestra de productos que se borrarán (los primeros 5 y los últimos 5):")
    for p in (productos[:5] + productos[-5:] if len(productos) > 10 else productos):
        print(f"    id={p[0]}  {p[1]}")
    print("\nMuestra de clientes que se borrarán:")
    for c in (clientes[:5] + clientes[-5:] if len(clientes) > 10 else clientes):
        print(f"    id={c[0]}  {c[1]}")

    respuesta = input("\n¿Confirmas que TODO lo de arriba es basura de prueba? Escribe SI para borrar: ")
    if respuesta.strip().upper() != "SI":
        print("Cancelado. No se borró nada.")
        return

    if venta_ids:
        cur.execute(
            f"DELETE FROM venta_detalle WHERE venta_id IN ({','.join('?' * len(venta_ids))})",
            venta_ids,
        )
        cur.execute(
            f"DELETE FROM ventas WHERE id IN ({','.join('?' * len(venta_ids))})",
            venta_ids,
        )
    if producto_ids:
        cur.execute(
            f"DELETE FROM productos WHERE id IN ({','.join('?' * len(producto_ids))})",
            producto_ids,
        )
    if cliente_ids:
        cur.execute(
            f"DELETE FROM clientes WHERE id IN ({','.join('?' * len(cliente_ids))})",
            cliente_ids,
        )

    con.commit()
    con.close()
    print("\nListo. Datos de prueba eliminados. Las tablas FTS de clientes/productos")
    print("se actualizaron solas (los triggers AFTER DELETE ya se encargan de eso).")
    print("\nNota: no toqué categorias/proveedores/metodos_pago por si el generador")
    print("los creó como catálogo real que quieras conservar. Si quieres borrar esos")
    print("también, dime y te paso el detalle.")


if __name__ == "__main__":
    try:
        main()
    except sqlite3.OperationalError as e:
        print(f"\nERROR de SQLite: {e}")
        sys.exit(1)
