"""Acceso a datos de productos. Solo CRUD y consultas, sin lógica de negocio."""

from database.connection import get_db
from models.producto import Producto
from models.producto_presentacion import ProductoPresentacion
from utils.busqueda import filtro_por_palabras

_SELECT_BASE = """
    SELECT p.*, c.nombre AS categoria_nombre, pr.nombre AS proveedor_nombre
    FROM productos p
    LEFT JOIN categorias c ON c.id = p.categoria_id
    LEFT JOIN proveedores pr ON pr.id = p.proveedor_id
"""


class ProductoRepository:

    def __init__(self):
        self.db = get_db()

    def listar(self, solo_activos: bool = True, texto_busqueda: str = "") -> list[Producto]:
        query = _SELECT_BASE
        condiciones = []
        params: list = []

        if solo_activos:
            condiciones.append("p.activo = 1")

        # Cada palabra escrita debe aparecer en el nombre, en cualquier
        # orden y en cualquier parte (ej. "1.5 coca" encuentra "Coca-Cola 1.5L").
        # Los símbolos % y _ escritos por el usuario ya no actúan como comodines.
        filtro, params_filtro = filtro_por_palabras(["p.nombre"], texto_busqueda)
        if filtro:
            condiciones.append(filtro)
            params.extend(params_filtro)

        if condiciones:
            query += " WHERE " + " AND ".join(condiciones)
        query += " ORDER BY COALESCE(c.nombre, 'zzz_sin_categoria'), p.nombre ASC"

        cur = self.db.get_connection().execute(query, params)
        return [Producto.from_row(r) for r in cur.fetchall()]

    def obtener_por_id(self, producto_id: int) -> Producto | None:
        cur = self.db.get_connection().execute(_SELECT_BASE + " WHERE p.id = ?", (producto_id,))
        row = cur.fetchone()
        return Producto.from_row(row) if row else None

    def listar_stock_bajo(self) -> list[Producto]:
        cur = self.db.get_connection().execute(
            _SELECT_BASE + " WHERE p.activo = 1 AND p.stock_actual <= p.stock_minimo AND p.stock_actual > 0"
        )
        return [Producto.from_row(r) for r in cur.fetchall()]

    def listar_agotados(self) -> list[Producto]:
        cur = self.db.get_connection().execute(
            _SELECT_BASE + " WHERE p.activo = 1 AND p.stock_actual <= 0"
        )
        return [Producto.from_row(r) for r in cur.fetchall()]

    def crear(self, producto: Producto) -> int:
        with self.db.transaction() as cur:
            cur.execute(
                """INSERT INTO productos
                   (nombre, categoria_id, marca, unidad_medida, precio_venta_actual,
                    costo_promedio_actual, stock_actual, stock_minimo, proveedor_id, activo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    producto.nombre, producto.categoria_id, producto.marca, producto.unidad_medida,
                    producto.precio_venta_actual, producto.costo_promedio_actual,
                    producto.stock_actual, producto.stock_minimo, producto.proveedor_id,
                    int(producto.activo),
                ),
            )
            producto_id = cur.lastrowid
            cur.execute(
                "INSERT INTO historial_precios (producto_id, precio_venta) VALUES (?, ?)",
                (producto_id, producto.precio_venta_actual),
            )
            return producto_id

    def actualizar(self, producto: Producto, registrar_cambio_precio: bool) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                """UPDATE productos SET
                       nombre = ?, categoria_id = ?, marca = ?, unidad_medida = ?,
                       precio_venta_actual = ?, stock_minimo = ?, proveedor_id = ?, activo = ?
                   WHERE id = ?""",
                (
                    producto.nombre, producto.categoria_id, producto.marca, producto.unidad_medida,
                    producto.precio_venta_actual, producto.stock_minimo, producto.proveedor_id,
                    int(producto.activo), producto.id,
                ),
            )
            if registrar_cambio_precio:
                cur.execute(
                    "INSERT INTO historial_precios (producto_id, precio_venta) VALUES (?, ?)",
                    (producto.id, producto.precio_venta_actual),
                )

    def desactivar(self, producto_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute("UPDATE productos SET activo = 0 WHERE id = ?", (producto_id,))

    def actualizar_stock_y_costo(self, producto_id: int, nuevo_stock: float, nuevo_costo_promedio: float | None = None) -> None:
        """Usado internamente por servicios (compras/ventas), nunca directo desde UI."""
        with self.db.transaction() as cur:
            if nuevo_costo_promedio is not None:
                cur.execute(
                    "UPDATE productos SET stock_actual = ?, costo_promedio_actual = ? WHERE id = ?",
                    (nuevo_stock, nuevo_costo_promedio, producto_id),
                )
            else:
                cur.execute(
                    "UPDATE productos SET stock_actual = ? WHERE id = ?",
                    (nuevo_stock, producto_id),
                )

    def historial_costos(self, producto_id: int) -> list[dict]:
        cur = self.db.get_connection().execute(
            "SELECT * FROM historial_costos WHERE producto_id = ? ORDER BY fecha DESC",
            (producto_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    # ---- Categorías y proveedores (consultas simples para combos) ----
    def listar_categorias(self) -> list[dict]:
        cur = self.db.get_connection().execute("SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre")
        return [dict(r) for r in cur.fetchall()]

    def crear_categoria(self, nombre: str) -> int:
        with self.db.transaction() as cur:
            cur.execute("INSERT INTO categorias (nombre) VALUES (?)", (nombre,))
            return cur.lastrowid

    def listar_proveedores(self) -> list[dict]:
        cur = self.db.get_connection().execute("SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre")
        return [dict(r) for r in cur.fetchall()]

    def crear_proveedor(self, nombre: str, documento: str = "", telefono: str = "", direccion: str = "") -> int:
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO proveedores (nombre, documento, telefono, direccion) VALUES (?, ?, ?, ?)",
                (nombre, documento, telefono, direccion),
            )
            return cur.lastrowid

    # ---- Presentaciones de venta (caja, docena, paquete, etc.) ----
    def listar_presentaciones(self, producto_id: int) -> list[ProductoPresentacion]:
        cur = self.db.get_connection().execute(
            "SELECT * FROM producto_presentaciones WHERE producto_id = ? AND activo = 1 "
            "ORDER BY orden ASC, id ASC",
            (producto_id,),
        )
        return [ProductoPresentacion.from_row(r) for r in cur.fetchall()]

    def reemplazar_presentaciones(self, producto_id: int, presentaciones: list[ProductoPresentacion]) -> None:
        """Borra las presentaciones actuales del producto y guarda la lista
        nueva completa. Se usa así (en vez de diff) porque el formulario
        siempre envía el estado final de la lista tal como quedó editada."""
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM producto_presentaciones WHERE producto_id = ?", (producto_id,))
            for orden, p in enumerate(presentaciones):
                cur.execute(
                    """INSERT INTO producto_presentaciones
                       (producto_id, nombre, cantidad_unidades, precio, orden, activo)
                       VALUES (?, ?, ?, ?, ?, 1)""",
                    (producto_id, p.nombre, p.cantidad_unidades, p.precio, orden),
                )