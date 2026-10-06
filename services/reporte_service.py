"""Lógica de agregación de datos para el dashboard y la sección de reportes."""

from datetime import date, timedelta

from config import DIAS_RETENCION
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
        """Datos del dashboard: métricas del día + gráficos de la ventana de
        retención (últimos DIAS_RETENCION días). No calcula nada que la
        pantalla no muestre, para que abrir/refrescar sea lo más liviano posible."""
        ventas_dia = self.venta_repo.ventas_del_dia()
        return {
            "ventas_del_dia_total": ventas_dia["total_ventas"],
            "ventas_del_dia_cantidad": ventas_dia["cantidad"],
            "utilidad_del_dia": self.venta_repo.utilidad_del_dia(),
            "estado_caja": self.caja_repo.estado_caja_actual(usuario_id),
            "stock_bajo": self.producto_repo.listar_stock_bajo(),
            "agotados": self.producto_repo.listar_agotados(),
            "ventas_por_dia": self._rellenar_dias_sin_ventas(
                self.venta_repo.ventas_por_dia_ventana()
            ),
            "ventas_metodo_pago": self.venta_repo.ventas_por_metodo_pago_ventana(),
            "productos_mas_vendidos": self.venta_repo.productos_mas_vendidos_ventana(8),
        }

    @staticmethod
    def _rellenar_dias_sin_ventas(filas: list[dict]) -> list[dict]:
        """`ventas_por_dia_ventana` solo trae los días con ventas. Para que el
        gráfico muestre los DIAS_RETENCION días seguidos, se completan los
        días sin ventas con total 0."""
        totales = {fila["dia"]: fila["total"] for fila in filas}
        hoy = date.today()
        dias = [hoy - timedelta(days=i) for i in range(DIAS_RETENCION - 1, -1, -1)]
        return [
            {"dia": d.isoformat(), "etiqueta": d.strftime("%d/%m"),
             "total": totales.get(d.isoformat(), 0.0)}
            for d in dias
        ]

    def reporte_ventas(self, fecha_desde: str = "", fecha_hasta: str = "") -> list[dict]:
        return self.venta_repo.listar_ventas(fecha_desde, fecha_hasta)

    def reporte_utilidad(self, fecha_desde: str = "", fecha_hasta: str = "") -> list[dict]:
        query = f"""
            SELECT v.id AS venta_id, v.fecha, p.nombre AS producto,
                   vd.cantidad, vd.precio_venta_unitario, vd.costo_unitario_snapshot,
                   (vd.precio_venta_unitario - vd.costo_unitario_snapshot) * vd.cantidad AS utilidad
            FROM venta_detalle vd
            JOIN ventas v ON v.id = vd.venta_id
            JOIN productos p ON p.id = vd.producto_id
            WHERE v.estado = 'completada'
              AND v.fecha >= date('now', 'localtime', '-{DIAS_RETENCION - 1} days')
        """
        params: list = []
        # Rangos sobre la columna (no date(v.fecha)): aplicar una función a la
        # columna impide usar idx_ventas_fecha. Equivale a la comparación por
        # día porque las fechas se guardan como 'YYYY-MM-DD HH:MM:SS'.
        if fecha_desde:
            query += " AND v.fecha >= date(?)"
            params.append(fecha_desde)
        if fecha_hasta:
            query += " AND v.fecha < date(?, '+1 day')"
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
                    AND v.fecha >= date('now', 'localtime', ?)
               GROUP BY c.id
               ORDER BY total_comprado DESC""",
            (f"-{DIAS_RETENCION - 1} days",),
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