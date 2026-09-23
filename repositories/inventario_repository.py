"""Acceso a datos de movimientos de inventario."""

from database.connection import get_db


class InventarioRepository:

    def __init__(self):
        self.db = get_db()

    def registrar_movimiento(self, cursor, producto_id: int, tipo: str, cantidad: float,
                              referencia_tipo: str, referencia_id: int | None, usuario_id: int | None) -> None:
        """
        Recibe un cursor externo porque este movimiento SIEMPRE debe ocurrir
        dentro de la misma transacción que la venta/compra que lo origina.
        """
        cursor.execute(
            """INSERT INTO inventario_movimientos
               (producto_id, tipo, cantidad, referencia_tipo, referencia_id, usuario_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (producto_id, tipo, cantidad, referencia_tipo, referencia_id, usuario_id),
        )

    def listar_movimientos(self, producto_id: int | None = None, limite: int = 200) -> list[dict]:
        query = """
            SELECT m.*, p.nombre AS producto_nombre
            FROM inventario_movimientos m
            JOIN productos p ON p.id = m.producto_id
        """
        params: list = []
        if producto_id:
            query += " WHERE m.producto_id = ?"
            params.append(producto_id)
        query += " ORDER BY m.fecha DESC LIMIT ?"
        params.append(limite)

        cur = self.db.get_connection().execute(query, params)
        return [dict(r) for r in cur.fetchall()]

    def registrar_ajuste_manual(self, producto_id: int, cantidad_nueva: float, motivo: str, usuario_id: int) -> None:
        """Ajuste manual de stock (ej. por conteo físico), fuera de venta/compra."""
        with self.db.transaction() as cur:
            cur.execute("SELECT stock_actual FROM productos WHERE id = ?", (producto_id,))
            stock_actual = cur.fetchone()["stock_actual"]
            diferencia = cantidad_nueva - stock_actual

            cur.execute("UPDATE productos SET stock_actual = ? WHERE id = ?", (cantidad_nueva, producto_id))
            cur.execute(
                """INSERT INTO inventario_movimientos
                   (producto_id, tipo, cantidad, referencia_tipo, referencia_id, usuario_id)
                   VALUES (?, 'ajuste', ?, 'ajuste', NULL, ?)""",
                (producto_id, diferencia, usuario_id),
            )
