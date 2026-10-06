"""
Generador de datos de prueba para pos_system (HogarFeliz).
=============================================================
Inserta DIRECTO en el archivo .db (SQLite) datos realistas de:
  - clientes
  - productos
  - ventas + venta_detalle

Ajustado al esquema real (schema.sql) que compartiste: usuarios,
categorias, proveedores, productos, clientes, metodos_pago,
caja_sesiones, ventas, venta_detalle. Los triggers FTS5 de
clientes/productos se disparan solos al insertar, así que la
búsqueda queda indexada automáticamente.

Volumen configurado: 500 productos, 400 clientes, 20 000 ventas
(con 1-5 líneas cada una), pensado para el tamaño real de la
distribuidora.

IMPORTANTE - HAZ UN BACKUP ANTES DE CORRER ESTO
------------------------------------------------
Usa el botón "Crear copia de seguridad ahora" de tu app, o copia el
archivo .db a mano, ANTES de ejecutar el script. Esto escribe datos
de prueba directo en la base, no hay "deshacer".

Requisito: debe existir ya el usuario administrador (el que se crea
la primera vez que abres la app), porque no se puede fabricar un
usuario con password_hash/recovery_code_hash válidos desde aquí.

Cómo usarlo
-----------
1. Cierra la app (para que no haya locks sobre el .db).
2. python generar_datos_prueba.py --db ruta/a/pos_system.db
   (si no pasas --db, busca "pos_system.db" en la carpeta actual)
3. Abre la app y prueba: listado de productos, búsqueda, historial
   de cliente, reportes, caja. Ahí es donde vas a notar si "aguanta".

El script solo AGREGA filas nuevas; no borra ni modifica lo que ya
tenías.
"""

import argparse
import random
import sqlite3
import sys
from datetime import datetime, timedelta

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
CANTIDAD_PRODUCTOS = 500
CANTIDAD_CLIENTES = 400
CANTIDAD_VENTAS = 300_000
MESES_HISTORICO = 18  # rango de fechas hacia atrás para las ventas

CATEGORIAS_DEFAULT = ["Cocina", "Limpieza", "Baño", "Electro menor", "Organización", "Textil hogar", "Ferretería menor"]
PROVEEDORES_DEFAULT = ["Proveedor General", "Importadora Lima SAC", "Distribuidora Andina"]
METODOS_PAGO_DEFAULT = [("Efectivo", 1), ("Yape/Plin", 0), ("Tarjeta", 0)]

ITEMS_BASE = [
    "Olla de aluminio", "Sartén antiadherente", "Juego de cubiertos", "Cuchillo de cocina",
    "Tabla de picar", "Colador de acero", "Jarra medidora", "Ensaladera",
    "Detergente en polvo", "Lejía", "Esponja multiuso", "Trapeador",
    "Escoba", "Recogedor", "Bolsas de basura", "Limpiavidrios",
    "Toalla de baño", "Cortina de baño", "Jabonera", "Dispensador de jabón",
    "Licuadora", "Batidora manual", "Plancha a vapor", "Ventilador de mesa",
    "Organizador plástico", "Cesto multiuso", "Percha", "Tender de ropa",
    "Sábana", "Frazada", "Almohada", "Cubrecama",
    "Martillo", "Destornillador set", "Cinta métrica", "Foco LED",
]
MARCAS = ["HogarFeliz", "Rey", "Umco", "Facusa", "Tramontina", "Ajover", "Genérico", "ImportMax"]
UNIDADES = ["unidad", "caja", "docena", "paquete", "kg", "litro"]

NOMBRES = ["Jose", "Maria", "Carlos", "Ana", "Luis", "Rosa", "Jorge", "Carmen", "Miguel", "Elena",
           "Pedro", "Sofia", "Manuel", "Lucia", "Jean", "Paul", "Diana", "Victor", "Patricia", "Raul",
           "Karina", "Fernando", "Gabriela", "Ricardo", "Milagros", "Julio", "Yolanda", "Enrique", "Vanessa", "Hugo"]
APELLIDOS = ["Garcia", "Rodriguez", "Gonzalez", "Fernandez", "Lopez", "Martinez", "Sanchez", "Perez",
             "Gomez", "Diaz", "Torres", "Vasquez", "Ramos", "Flores", "Mendoza", "Chavez", "Rojas",
             "Nateros", "Moncada", "Quispe", "Huaman", "Paredes", "Salazar", "Cardenas"]

random.seed()  # cambia a un número fijo si quieres datos reproducibles


def azar_fecha(meses_atras: int) -> str:
    inicio = datetime.now() - timedelta(days=30 * meses_atras)
    delta_segundos = int((datetime.now() - inicio).total_seconds())
    fecha = inicio + timedelta(seconds=random.randint(0, delta_segundos))
    return fecha.strftime("%Y-%m-%d %H:%M:%S")


def obtener_o_crear_simple(cur, tabla, columna, valores_default):
    cur.execute(f"SELECT id FROM {tabla}")
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        return ids
    for valor in valores_default:
        cur.execute(f"INSERT INTO {tabla} ({columna}) VALUES (?)", (valor,))
    cur.execute(f"SELECT id FROM {tabla}")
    return [r[0] for r in cur.fetchall()]


def main():
    parser = argparse.ArgumentParser(description="Genera datos de prueba para pos_system")
    parser.add_argument("--db", default="pos_system.db", help="Ruta al archivo .db")
    args = parser.parse_args()

    print(f"Conectando a: {args.db}")
    con = sqlite3.connect(args.db)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()

    # Velocidad para carga masiva
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")

    # ---------------- USUARIO (obligatorio, no se fabrica) ----------------
    cur.execute("SELECT id FROM usuarios")
    usuario_ids = [r[0] for r in cur.fetchall()]
    if not usuario_ids:
        print("\nERROR: no existe ningún usuario administrador en la base.")
        print("Abre la app al menos una vez y crea el usuario admin antes de correr este script.")
        sys.exit(1)

    print("Resolviendo categorías, proveedores y métodos de pago...")
    categoria_ids = obtener_o_crear_simple(cur, "categorias", "nombre", CATEGORIAS_DEFAULT)
    proveedor_ids = obtener_o_crear_simple(cur, "proveedores", "nombre", PROVEEDORES_DEFAULT)

    cur.execute("SELECT id, es_efectivo FROM metodos_pago")
    metodos = cur.fetchall()
    if not metodos:
        for nombre, es_efectivo in METODOS_PAGO_DEFAULT:
            cur.execute("INSERT INTO metodos_pago (nombre, es_efectivo) VALUES (?, ?)", (nombre, es_efectivo))
        cur.execute("SELECT id, es_efectivo FROM metodos_pago")
        metodos = cur.fetchall()

    cur.execute("SELECT id FROM caja_sesiones")
    caja_ids = [r[0] for r in cur.fetchall()]

    # ---------------- CLIENTES ----------------
    print(f"Generando {CANTIDAD_CLIENTES} clientes...")
    documentos_usados = set()
    clientes_rows = []
    for _ in range(CANTIDAD_CLIENTES):
        nombre = f"{random.choice(NOMBRES)} {random.choice(APELLIDOS)} {random.choice(APELLIDOS)}"
        while True:
            documento = str(random.randint(10_000_000, 79_999_999))
            if documento not in documentos_usados:
                documentos_usados.add(documento)
                break
        telefono = "9" + str(random.randint(10_000_000, 99_999_999))
        direccion = f"Jr. {random.choice(APELLIDOS)} {random.randint(100, 1999)}, Lima"
        clientes_rows.append((nombre, documento, telefono, direccion))

    cur.executemany(
        "INSERT INTO clientes (nombre, documento, telefono, direccion) VALUES (?, ?, ?, ?)",
        clientes_rows,
    )
    cur.execute(f"SELECT id FROM clientes ORDER BY id DESC LIMIT {CANTIDAD_CLIENTES}")
    cliente_ids = [r[0] for r in cur.fetchall()]

    # ---------------- PRODUCTOS ----------------
    print(f"Generando {CANTIDAD_PRODUCTOS} productos...")
    productos_rows = []
    nombres_usados = set()
    intentos = 0
    while len(productos_rows) < CANTIDAD_PRODUCTOS and intentos < CANTIDAD_PRODUCTOS * 20:
        intentos += 1
        base = random.choice(ITEMS_BASE)
        marca = random.choice(MARCAS)
        variante = random.choice(["", " Grande", " Chico", " Pack x3", " 500ml", " 1L", " 2kg", " Nº2"])
        nombre = f"{base} {marca}{variante}".strip()
        if nombre in nombres_usados:
            continue
        nombres_usados.add(nombre)
        categoria_id = random.choice(categoria_ids) if categoria_ids else None
        proveedor_id = random.choice(proveedor_ids) if proveedor_ids else None
        unidad_medida = random.choice(UNIDADES)
        decimales = 2 if unidad_medida in ("kg", "litro") else 0
        costo = round(random.uniform(2.0, 90.0), 2)
        precio = round(costo * random.uniform(1.25, 1.8), 2)
        stock_actual = round(random.uniform(0, 400), decimales)
        stock_minimo = round(random.uniform(5, 20), decimales)
        activo = 0 if random.random() < 0.05 else 1
        productos_rows.append((
            nombre, categoria_id, marca, unidad_medida, precio, costo,
            stock_actual, stock_minimo, proveedor_id, activo,
        ))

    cur.executemany(
        """INSERT INTO productos
            (nombre, categoria_id, marca, unidad_medida, precio_venta_actual,
             costo_promedio_actual, stock_actual, stock_minimo, proveedor_id, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        productos_rows,
    )
    cur.execute(f"SELECT id, precio_venta_actual, costo_promedio_actual FROM productos ORDER BY id DESC LIMIT {len(productos_rows)}")
    productos_info = cur.fetchall()  # [(id, precio, costo), ...]

    con.commit()
    print(f"  -> {len(clientes_rows)} clientes y {len(productos_rows)} productos insertados.")

    # ---------------- VENTAS + DETALLE ----------------
    print(f"Generando {CANTIDAD_VENTAS} ventas (con 1-5 líneas cada una)...")
    detalle_rows = []

    print("Insertando ventas y su detalle (puede tardar unos segundos)...")
    for _ in range(CANTIDAD_VENTAS):
        fecha = azar_fecha(MESES_HISTORICO)
        cliente_id = random.choice(cliente_ids) if (cliente_ids and random.random() > 0.1) else None
        usuario_id = random.choice(usuario_ids)
        metodo_pago_id, pago_es_efectivo = random.choice(metodos)
        caja_sesion_id = random.choice(caja_ids) if caja_ids else None
        estado = "anulada" if random.random() < 0.04 else "completada"

        n_lineas = random.randint(1, 5)
        lineas = []
        for _ in range(n_lineas):
            prod_id, precio, costo = random.choice(productos_info)
            cantidad = random.choice([1, 1, 1, 2, 2, 3, 5, 10])
            lineas.append((prod_id, cantidad, precio, costo))

        subtotal = round(sum(c * p for _, c, p, _ in lineas), 2)
        descuento = round(subtotal * random.choice([0, 0, 0, 0.05, 0.1]), 2)
        total = round(subtotal - descuento, 2)

        cur.execute(
            """INSERT INTO ventas
                (cliente_id, usuario_id, fecha, subtotal, descuento, total,
                 metodo_pago_id, pago_es_efectivo, estado, caja_sesion_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cliente_id, usuario_id, fecha, subtotal, descuento, total,
             metodo_pago_id, pago_es_efectivo, estado, caja_sesion_id),
        )
        venta_id = cur.lastrowid
        for prod_id, cantidad, precio, costo in lineas:
            linea_subtotal = round(cantidad * precio, 2)
            detalle_rows.append((venta_id, prod_id, cantidad, precio, costo, linea_subtotal, "Unidad", cantidad, 1.0))

    cur.executemany(
        """INSERT INTO venta_detalle
            (venta_id, producto_id, cantidad, precio_venta_unitario, costo_unitario_snapshot,
             subtotal, presentacion_nombre, cantidad_presentacion, factor_unidades)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        detalle_rows,
    )

    con.commit()
    print(f"  -> {CANTIDAD_VENTAS} ventas y {len(detalle_rows)} líneas de detalle insertadas.")

    if not caja_ids:
        print("  (nota: no había caja_sesiones existentes, las ventas quedaron sin caja_sesion_id)")

    cur.execute("PRAGMA journal_mode = DELETE")
    con.commit()
    con.close()
    print("\nListo. Abre la app y prueba listados, búsqueda, reportes, caja e historial de cliente.")


if __name__ == "__main__":
    try:
        main()
    except sqlite3.OperationalError as e:
        print(f"\nERROR de SQLite: {e}")
        sys.exit(1)
