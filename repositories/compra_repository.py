"""Acceso a datos de compras y su detalle."""

from database.connection import get_db


class CompraRepository:

    def __init__(self):
        self.db = get_db()

    def crear_compra(self, cursor, proveedor_id, numero_documento, subtotal, impuesto, total,
                      pago_es_efectivo, caja_sesion_id, usuario_id) -> int:
        cursor.execute(
            """INSERT INTO compras
               (proveedor_id, numero_documento, subtotal, impuesto, total,
                pago_es_efectivo, caja_sesion_id, usuario_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (proveedor_id, numero_documento, subtotal, impuesto, total,
             int(pago_es_efectivo), caja_sesion_id, usuario_id),
        )
        return cursor.lastrowid

    def crear_linea_detalle(self, cursor, compra_id, producto_id, cantidad, costo_unitario, subtotal,
                             presentacion_nombre: str = "Unidad", cantidad_presentacion: float = None) -> int:
        cursor.execute(
            """INSERT INTO compra_detalle
               (compra_id, producto_id, cantidad, costo_unitario, subtotal,
                presentacion_nombre, cantidad_presentacion)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (compra_id, producto_id, cantidad, costo_unitario, subtotal,
             presentacion_nombre, cantidad_presentacion if cantidad_presentacion is not None else cantidad),
        )
        return cursor.lastrowid

    def obtener_linea_por_id(self, detalle_id: int) -> dict | None:
        cur = self.db.get_connection().execute(
            "SELECT * FROM compra_detalle WHERE id = ?", (detalle_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def actualizar_linea(self, cursor, detalle_id, cantidad, costo_unitario, subtotal,
                          presentacion_nombre, cantidad_presentacion) -> None:
        cursor.execute(
            """UPDATE compra_detalle SET
                   cantidad = ?, costo_unitario = ?, subtotal = ?,
                   presentacion_nombre = ?, cantidad_presentacion = ?
               WHERE id = ?""",
            (cantidad, costo_unitario, subtotal, presentacion_nombre, cantidad_presentacion, detalle_id),
        )

    def recalcular_totales_compra(self, cursor, compra_id: int) -> None:
        """Recalcula subtotal/total de la cabecera sumando sus líneas
        vigentes, tras editar una línea. El impuesto no cambia."""
        cur = cursor.execute(
            "SELECT COALESCE(SUM(subtotal), 0) AS suma FROM compra_detalle WHERE compra_id = ?",
            (compra_id,),
        )
        nuevo_subtotal = cur.fetchone()["suma"]
        cursor.execute(
            "UPDATE compras SET subtotal = ?, total = ? + impuesto WHERE id = ?",
            (nuevo_subtotal, nuevo_subtotal, compra_id),
        )

    def siguiente_numero_documento(self) -> str:
        """Correlativo sugerido para el N° de documento de la próxima compra.
        Usa MAX(id)+1 (nunca se reutiliza aunque no haya borrado ninguna)."""
        cur = self.db.get_connection().execute("SELECT COALESCE(MAX(id), 0) + 1 AS siguiente FROM compras")
        siguiente = cur.fetchone()["siguiente"]
        return f"COMP-{siguiente:06d}"

    def registrar_historial_costo(self, cursor, producto_id, costo_unitario,
                                   costo_promedio_resultante, compra_detalle_id, motivo: str = "compra") -> None:
        cursor.execute(
            """INSERT INTO historial_costos
               (producto_id, costo_unitario, costo_promedio_resultante, compra_detalle_id, motivo)
               VALUES (?, ?, ?, ?, ?)""",
            (producto_id, costo_unitario, costo_promedio_resultante, compra_detalle_id, motivo),
        )

    def listar_compras(self, limite: int = 500) -> list[dict]:
        cur = self.db.get_connection().execute(
            """SELECT co.*, pr.nombre AS proveedor_nombre
               FROM compras co
               LEFT JOIN proveedores pr ON pr.id = co.proveedor_id
               ORDER BY co.fecha DESC LIMIT ?""",
            (limite,),
        )
        return [dict(r) for r in cur.fetchall()]

    def obtener_lineas(self, compra_id: int) -> list[dict]:
        cur = self.db.get_connection().execute(
            """SELECT cd.*, p.nombre AS producto_nombre
               FROM compra_detalle cd
               JOIN productos p ON p.id = cd.producto_id
               WHERE cd.compra_id = ?""",
            (compra_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def compras_del_dia(self) -> dict:
        cur = self.db.get_connection().execute(
            """SELECT COALESCE(SUM(total), 0) AS total_compras, COUNT(*) AS cantidad
               FROM compras WHERE date(fecha) = date('now', 'localtime')"""
        )
        return dict(cur.fetchone())

    def compras_del_mes(self) -> dict:
        cur = self.db.get_connection().execute(
            """SELECT COALESCE(SUM(total), 0) AS total_compras, COUNT(*) AS cantidad
               FROM compras
               WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now', 'localtime')"""
        )
        return dict(cur.fetchone())