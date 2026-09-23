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

    def crear_linea_detalle(self, cursor, compra_id, producto_id, cantidad, costo_unitario, subtotal) -> int:
        cursor.execute(
            """INSERT INTO compra_detalle (compra_id, producto_id, cantidad, costo_unitario, subtotal)
               VALUES (?, ?, ?, ?, ?)""",
            (compra_id, producto_id, cantidad, costo_unitario, subtotal),
        )
        return cursor.lastrowid

    def registrar_historial_costo(self, cursor, producto_id, costo_unitario,
                                   costo_promedio_resultante, compra_detalle_id) -> None:
        cursor.execute(
            """INSERT INTO historial_costos
               (producto_id, costo_unitario, costo_promedio_resultante, compra_detalle_id, motivo)
               VALUES (?, ?, ?, ?, 'compra')""",
            (producto_id, costo_unitario, costo_promedio_resultante, compra_detalle_id),
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
