"""Acceso a datos de ventas y su detalle.

Nota de rendimiento: las columnas de fecha se filtran con RANGOS
(fecha >= X AND fecha < Y) y no con date(fecha) / strftime(..., fecha),
porque aplicar una función a la columna impide usar idx_ventas_fecha y
obliga a recorrer toda la tabla. Las fechas se guardan como
'YYYY-MM-DD HH:MM:SS', así que la comparación de texto equivale a la de fechas.
"""

from database.connection import get_db

# Rangos reutilizables (SQL) para "hoy" y "mes en curso", en hora local.
_HOY_DESDE = "date('now', 'localtime')"
_HOY_HASTA = "date('now', 'localtime', '+1 day')"
_MES_DESDE = "date('now', 'localtime', 'start of month')"
_MES_HASTA = "date('now', 'localtime', 'start of month', '+1 month')"


class VentaRepository:

    def __init__(self):
        self.db = get_db()

    def crear_venta(self, cursor, cliente_id, usuario_id, subtotal, descuento, total,
                     metodo_pago_id, pago_es_efectivo, caja_sesion_id) -> int:
        cursor.execute(
            """INSERT INTO ventas
               (cliente_id, usuario_id, subtotal, descuento, total, metodo_pago_id,
                pago_es_efectivo, estado, caja_sesion_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'completada', ?)""",
            (cliente_id, usuario_id, subtotal, descuento, total,
             metodo_pago_id, int(pago_es_efectivo), caja_sesion_id),
        )
        return cursor.lastrowid

    def crear_linea_detalle(self, cursor, venta_id, producto_id, cantidad,
                             precio_venta_unitario, costo_unitario_snapshot, subtotal,
                             presentacion_nombre=None, cantidad_presentacion=None,
                             factor_unidades=None) -> None:
        cursor.execute(
            """INSERT INTO venta_detalle
               (venta_id, producto_id, cantidad, precio_venta_unitario,
                costo_unitario_snapshot, subtotal, presentacion_nombre,
                cantidad_presentacion, factor_unidades)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (venta_id, producto_id, cantidad, precio_venta_unitario, costo_unitario_snapshot, subtotal,
             presentacion_nombre, cantidad_presentacion, factor_unidades),
        )

    def listar_ventas(self, fecha_desde: str = "", fecha_hasta: str = "", limite: int = 500) -> list[dict]:
        query = """
            SELECT v.*, c.nombre AS cliente_nombre, c.direccion AS cliente_direccion,
                   mp.nombre AS metodo_pago_nombre
            FROM ventas v
            LEFT JOIN clientes c ON c.id = v.cliente_id
            LEFT JOIN metodos_pago mp ON mp.id = v.metodo_pago_id
        """
        condiciones = []
        params: list = []
        if fecha_desde:
            condiciones.append("v.fecha >= date(?)")
            params.append(fecha_desde)
        if fecha_hasta:
            condiciones.append("v.fecha < date(?, '+1 day')")
            params.append(fecha_hasta)
        if condiciones:
            query += " WHERE " + " AND ".join(condiciones)
        query += " ORDER BY v.fecha DESC LIMIT ?"
        params.append(limite)

        cur = self.db.get_connection().execute(query, params)
        return [dict(r) for r in cur.fetchall()]

    def obtener_venta(self, venta_id: int) -> dict | None:
        cur = self.db.get_connection().execute(
            """SELECT v.*, c.nombre AS cliente_nombre, c.direccion AS cliente_direccion,
                      mp.nombre AS metodo_pago_nombre
               FROM ventas v
               LEFT JOIN clientes c ON c.id = v.cliente_id
               LEFT JOIN metodos_pago mp ON mp.id = v.metodo_pago_id
               WHERE v.id = ?""",
            (venta_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def obtener_lineas(self, venta_id: int) -> list[dict]:
        cur = self.db.get_connection().execute(
            """SELECT vd.*, p.nombre AS producto_nombre
               FROM venta_detalle vd
               JOIN productos p ON p.id = vd.producto_id
               WHERE vd.venta_id = ?""",
            (venta_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def anular_venta(self, cursor, venta_id: int) -> None:
        cursor.execute("UPDATE ventas SET estado = 'anulada' WHERE id = ?", (venta_id,))

    def ventas_del_dia(self) -> dict:
        cur = self.db.get_connection().execute(
            f"""SELECT COALESCE(SUM(total), 0) AS total_ventas, COUNT(*) AS cantidad
               FROM ventas
               WHERE fecha >= {_HOY_DESDE} AND fecha < {_HOY_HASTA}
                 AND estado = 'completada'"""
        )
        return dict(cur.fetchone())

    def ventas_del_mes(self) -> dict:
        cur = self.db.get_connection().execute(
            f"""SELECT COALESCE(SUM(total), 0) AS total_ventas, COUNT(*) AS cantidad
               FROM ventas
               WHERE fecha >= {_MES_DESDE} AND fecha < {_MES_HASTA}
                 AND estado = 'completada'"""
        )
        return dict(cur.fetchone())

    def utilidad_del_dia(self) -> float:
        cur = self.db.get_connection().execute(
            f"""SELECT COALESCE(SUM((vd.precio_venta_unitario - vd.costo_unitario_snapshot) * vd.cantidad), 0) AS utilidad
               FROM venta_detalle vd
               JOIN ventas v ON v.id = vd.venta_id
               WHERE v.fecha >= {_HOY_DESDE} AND v.fecha < {_HOY_HASTA}
                 AND v.estado = 'completada'"""
        )
        return cur.fetchone()["utilidad"]

    def utilidad_del_mes(self) -> float:
        cur = self.db.get_connection().execute(
            f"""SELECT COALESCE(SUM((vd.precio_venta_unitario - vd.costo_unitario_snapshot) * vd.cantidad), 0) AS utilidad
               FROM venta_detalle vd
               JOIN ventas v ON v.id = vd.venta_id
               WHERE v.fecha >= {_MES_DESDE} AND v.fecha < {_MES_HASTA}
                 AND v.estado = 'completada'"""
        )
        return cur.fetchone()["utilidad"]

    def ultimas_ventas(self, limite: int = 10) -> list[dict]:
        cur = self.db.get_connection().execute(
            """SELECT v.*, c.nombre AS cliente_nombre
               FROM ventas v
               LEFT JOIN clientes c ON c.id = v.cliente_id
               WHERE v.estado = 'completada'
               ORDER BY v.fecha DESC LIMIT ?""",
            (limite,),
        )
        return [dict(r) for r in cur.fetchall()]

    def ventas_ultimos_n_dias(self, n: int = 7) -> list[dict]:
        cur = self.db.get_connection().execute(
            """SELECT date(fecha) AS dia, COALESCE(SUM(total), 0) AS total
               FROM ventas
               WHERE fecha >= date('now', 'localtime', ?) AND estado = 'completada'
               GROUP BY date(fecha)
               ORDER BY dia ASC""",
            (f"-{n - 1} days",),
        )
        return [dict(r) for r in cur.fetchall()]

    def ventas_por_mes_del_anio(self, anio: int) -> list[dict]:
        """Total vendido por mes calendario del año indicado. Se usa en el
        gráfico de línea del dashboard."""
        cur = self.db.get_connection().execute(
            """SELECT strftime('%m', fecha) AS mes, COALESCE(SUM(total), 0) AS total
               FROM ventas
               WHERE fecha >= ? AND fecha < ? AND estado = 'completada'
               GROUP BY strftime('%m', fecha)
               ORDER BY mes ASC""",
            (f"{anio:04d}-01-01", f"{anio + 1:04d}-01-01"),
        )
        return [dict(r) for r in cur.fetchall()]

    def productos_mas_vendidos(self, limite: int = 10) -> list[dict]:
        cur = self.db.get_connection().execute(
            """SELECT p.nombre, SUM(vd.cantidad) AS cantidad_total,
                      SUM(vd.subtotal) AS monto_total
               FROM venta_detalle vd
               JOIN productos p ON p.id = vd.producto_id
               JOIN ventas v ON v.id = vd.venta_id
               WHERE v.estado = 'completada'
               GROUP BY p.id
               ORDER BY cantidad_total DESC
               LIMIT ?""",
            (limite,),
        )
        return [dict(r) for r in cur.fetchall()]

    def ventas_por_metodo_pago_mes(self) -> list[dict]:
        """Total vendido en el mes calendario en curso, agrupado por método
        de pago. Se usa en el gráfico circular del dashboard."""
        cur = self.db.get_connection().execute(
            f"""SELECT COALESCE(mp.nombre, 'Sin método') AS metodo, SUM(v.total) AS total
               FROM ventas v
               LEFT JOIN metodos_pago mp ON mp.id = v.metodo_pago_id
               WHERE v.estado = 'completada'
                 AND v.fecha >= {_MES_DESDE} AND v.fecha < {_MES_HASTA}
               GROUP BY COALESCE(mp.nombre, 'Sin método')
               ORDER BY total DESC"""
        )
        return [dict(r) for r in cur.fetchall()]

    # ---- Métodos de pago ----
    def listar_metodos_pago(self) -> list[dict]:
        cur = self.db.get_connection().execute("SELECT * FROM metodos_pago WHERE activo = 1 ORDER BY nombre")
        return [dict(r) for r in cur.fetchall()]

    def metodo_pago_es_efectivo(self, metodo_pago_id: int | None) -> bool:
        """Determina si un método de pago mueve dinero físico de caja."""
        if metodo_pago_id is None:
            return False
        cur = self.db.get_connection().execute(
            "SELECT es_efectivo FROM metodos_pago WHERE id = ?", (metodo_pago_id,)
        )
        row = cur.fetchone()
        return bool(row["es_efectivo"]) if row else False

    # ---- Devoluciones ----
    def crear_devolucion(self, cursor, venta_id: int, producto_id: int, cantidad: float,
                          motivo: str, usuario_id: int) -> int:
        """Recibe un cursor externo: la devolucion y la reposicion de stock
        deben ocurrir en la MISMA transaccion (todo o nada)."""
        cursor.execute(
            """INSERT INTO devoluciones (venta_id, producto_id, cantidad, motivo, usuario_id)
               VALUES (?, ?, ?, ?, ?)""",
            (venta_id, producto_id, cantidad, motivo, usuario_id),
        )
        return cursor.lastrowid

    def cantidad_devuelta(self, cursor, venta_id: int, producto_id: int) -> float:
        """Total ya devuelto de un producto en una venta (unidad base)."""
        cursor.execute(
            """SELECT COALESCE(SUM(cantidad), 0) AS total
               FROM devoluciones WHERE venta_id = ? AND producto_id = ?""",
            (venta_id, producto_id),
        )
        return cursor.fetchone()["total"]

    def actualizar_cliente(self, cursor, venta_id: int, cliente_id: int | None) -> None:
        cursor.execute("UPDATE ventas SET cliente_id = ? WHERE id = ?", (cliente_id, venta_id))