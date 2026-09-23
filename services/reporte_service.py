"""Lógica de agregación de datos para el dashboard y la sección de reportes."""

from database.connection import get_db
from repositories.venta_repository import VentaRepository
from repositories.compra_repository import CompraRepository
from repositories.producto_repository import ProductoRepository
from repositories.caja_repository import CajaRepository


class ReporteService:

    def __init__(self):
        self.db = get_db()
        self.venta_repo = VentaRepository()
        self.compra_repo = CompraRepository()
        self.producto_repo = ProductoRepository()
        self.caja_repo = CajaRepository()

    def resumen_dashboard(self, usuario_id: int) -> dict:
        ventas_dia = self.venta_repo.ventas_del_dia()
        utilidad_dia = self.venta_repo.utilidad_del_dia()
        compras_dia = self.compra_repo.compras_del_dia()
        estado_caja = self.caja_repo.estado_caja_actual(usuario_id)
        stock_bajo = self.producto_repo.listar_stock_bajo()
        agotados = self.producto_repo.listar_agotados()
        ultimas_ventas = self.venta_repo.ultimas_ventas(10)
        ventas_7_dias = self.venta_repo.ventas_ultimos_n_dias(7)

        ventas_mes = self.venta_repo.ventas_del_mes()
        utilidad_mes = self.venta_repo.utilidad_del_mes()
        compras_mes = self.compra_repo.compras_del_mes()
        ticket_promedio_mes = (
            round(ventas_mes["total_ventas"] / ventas_mes["cantidad"], 2)
            if ventas_mes["cantidad"] else 0.0
        )

        return {
            "ventas_del_dia_total": ventas_dia["total_ventas"],
            "ventas_del_dia_cantidad": ventas_dia["cantidad"],
            "utilidad_del_dia": utilidad_dia,
            "compras_del_dia_total": compras_dia["total_compras"],
            "estado_caja": estado_caja,
            "stock_bajo": stock_bajo,
            "agotados": agotados,
            "ultimas_ventas": ultimas_ventas,
            "ventas_7_dias": ventas_7_dias,
            "ventas_del_mes_total": ventas_mes["total_ventas"],
            "ventas_del_mes_cantidad": ventas_mes["cantidad"],
            "utilidad_del_mes": utilidad_mes,
            "compras_del_mes_total": compras_mes["total_compras"],
            "ticket_promedio_mes": ticket_promedio_mes,
        }

    def reporte_ventas(self, fecha_desde: str = "", fecha_hasta: str = "") -> list[dict]:
        return self.venta_repo.listar_ventas(fecha_desde, fecha_hasta)

    def reporte_utilidad(self, fecha_desde: str = "", fecha_hasta: str = "") -> list[dict]:
        query = """
            SELECT v.id AS venta_id, v.fecha, p.nombre AS producto,
                   vd.cantidad, vd.precio_venta_unitario, vd.costo_unitario_snapshot,
                   (vd.precio_venta_unitario - vd.costo_unitario_snapshot) * vd.cantidad AS utilidad
            FROM venta_detalle vd
            JOIN ventas v ON v.id = vd.venta_id
            JOIN productos p ON p.id = vd.producto_id
            WHERE v.estado = 'completada'
        """
        params: list = []
        if fecha_desde:
            query += " AND date(v.fecha) >= date(?)"
            params.append(fecha_desde)
        if fecha_hasta:
            query += " AND date(v.fecha) <= date(?)"
            params.append(fecha_hasta)
        query += " ORDER BY v.fecha DESC"

        cur = self.db.get_connection().execute(query, params)
        return [dict(r) for r in cur.fetchall()]

    def reporte_compras(self) -> list[dict]:
        return self.compra_repo.listar_compras()

    def reporte_productos_mas_vendidos(self, limite: int = 20) -> list[dict]:
        return self.venta_repo.productos_mas_vendidos(limite)

    def reporte_inventario(self) -> list[dict]:
        productos = self.producto_repo.listar(solo_activos=True)
        return [
            {
                "producto": p.nombre,
                "stock_actual": p.stock_actual,
                "stock_minimo": p.stock_minimo,
                "costo_promedio": p.costo_promedio_actual,
                "valor_inventario": round(p.stock_actual * p.costo_promedio_actual, 2),
            }
            for p in productos
        ]

    def reporte_ventas_por_cliente(self) -> list[dict]:
        cur = self.db.get_connection().execute(
            """SELECT c.nombre AS cliente, COUNT(v.id) AS cantidad_ventas,
                      COALESCE(SUM(v.total), 0) AS total_comprado
               FROM clientes c
               LEFT JOIN ventas v ON v.cliente_id = c.id AND v.estado = 'completada'
               GROUP BY c.id
               ORDER BY total_comprado DESC"""
        )
        return [dict(r) for r in cur.fetchall()]

    def exportar_a_excel(self, datos: list[dict], ruta_destino: str) -> None:
        """Exporta una lista de diccionarios a un archivo .xlsx usando openpyxl."""
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active

        if datos:
            encabezados = list(datos[0].keys())
            ws.append(encabezados)
            for fila in datos:
                ws.append([fila.get(col, "") for col in encabezados])

        wb.save(ruta_destino)
