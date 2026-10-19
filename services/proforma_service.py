"""Proformas (cotizaciones): no tocan stock ni caja hasta convertirse en venta."""

from database.connection import get_db


class ProformaError(Exception):
    pass


class ProformaService:

    def __init__(self):
        self.db = get_db()

    def crear(self, lineas, usuario_id: int, descuento: float = 0.0, cliente_id=None,
              cliente_nombre: str = "", cliente_tipo: str = "", validez_dias: int = 7,
              notas: str = "") -> int:
        if not lineas:
            raise ProformaError("La proforma debe tener al menos un producto.")
        subtotal = round(sum(l.subtotal for l in lineas), 2)
        if descuento < 0 or descuento > subtotal:
            raise ProformaError("El descuento no es válido.")
        with self.db.transaction() as cur:
            cur.execute(
                """INSERT INTO proformas (usuario_id, cliente_id, cliente_nombre, cliente_tipo,
                       subtotal, descuento, total, validez_dias, notas)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (usuario_id, cliente_id, (cliente_nombre or "").strip() or None,
                 (cliente_tipo or "").strip() or None, subtotal, descuento,
                 round(subtotal - descuento, 2), validez_dias, (notas or "").strip() or None),
            )
            pid = cur.lastrowid
            for l in lineas:
                cur.execute(
                    """INSERT INTO proforma_detalle (proforma_id, producto_id, nombre_producto,
                           cantidad, precio_unitario, subtotal, presentacion_nombre,
                           cantidad_presentacion, factor_unidades)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pid, l.producto_id, l.nombre_producto, l.cantidad, l.precio_venta_unitario,
                     l.subtotal, l.presentacion_nombre, l.cantidad_presentacion, l.factor_unidades),
                )
            return pid

    def listar(self, texto: str = "") -> list[dict]:
        sql = """SELECT p.*, COALESCE(c.nombre, p.cliente_nombre) AS cliente
                 FROM proformas p LEFT JOIN clientes c ON c.id = p.cliente_id"""
        params = []
        if texto.strip():
            sql += " WHERE COALESCE(c.nombre, p.cliente_nombre, '') LIKE ? OR p.id = ?"
            params = [f"%{texto.strip()}%", int(texto) if texto.strip().isdigit() else -1]
        sql += " ORDER BY p.id DESC LIMIT 500"
        return [dict(r) for r in self.db.get_connection().execute(sql, params).fetchall()]

    def obtener(self, proforma_id: int) -> dict | None:
        con = self.db.get_connection()
        fila = con.execute(
            """SELECT p.*, COALESCE(c.nombre, p.cliente_nombre) AS cliente
               FROM proformas p LEFT JOIN clientes c ON c.id = p.cliente_id WHERE p.id = ?""",
            (proforma_id,)).fetchone()
        if not fila:
            return None
        datos = dict(fila)
        datos["lineas"] = [dict(r) for r in con.execute(
            "SELECT * FROM proforma_detalle WHERE proforma_id = ? ORDER BY id", (proforma_id,))]
        return datos

    def anular(self, proforma_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute("UPDATE proformas SET estado = 'anulada' WHERE id = ? AND estado = 'pendiente'",
                        (proforma_id,))

    def marcar_convertida(self, proforma_id: int, venta_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute("UPDATE proformas SET estado = 'convertida', venta_id = ? WHERE id = ?",
                        (venta_id, proforma_id))
