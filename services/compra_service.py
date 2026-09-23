"""
Lógica de negocio de compras.

Al registrar una compra:
1. Se inserta cabecera + líneas.
2. Por cada línea: se recalcula el costo promedio ponderado del producto,
   se guarda en historial_costos (nunca se sobrescribe el historial),
   se aumenta el stock y se registra el movimiento de inventario.
3. Si la compra se pagó al contado, se registra un egreso en la sesión de
   caja abierta (todas las compras salen de la caja del negocio, así que
   las que se pagan en efectivo deben descontarse igual que cualquier
   otro egreso).

Todo dentro de una única transacción SQLite.
"""

from database.connection import get_db
from repositories.producto_repository import ProductoRepository
from repositories.compra_repository import CompraRepository
from repositories.inventario_repository import InventarioRepository
from repositories.caja_repository import CajaRepository
from models.compra import CompraDetalleItem
from services.costo_service import calcular_costo_promedio_ponderado


class CompraError(Exception):
    pass


class CompraService:

    def __init__(self):
        self.db = get_db()
        self.producto_repo = ProductoRepository()
        self.compra_repo = CompraRepository()
        self.inventario_repo = InventarioRepository()
        self.caja_repo = CajaRepository()

    def registrar_compra(
        self,
        lineas: list[CompraDetalleItem],
        proveedor_id: int | None,
        numero_documento: str,
        impuesto: float,
        usuario_id: int,
        pago_es_efectivo: bool = False,
    ) -> int:
        if not lineas:
            raise CompraError("La compra debe tener al menos un producto.")
        for linea in lineas:
            if linea.cantidad <= 0:
                raise CompraError(f"La cantidad de '{linea.nombre_producto}' debe ser mayor a cero.")
            if linea.costo_unitario < 0:
                raise CompraError(f"El costo de '{linea.nombre_producto}' no puede ser negativo.")

        subtotal = round(sum(l.subtotal for l in lineas), 2)
        total = round(subtotal + impuesto, 2)

        sesion_caja = self.caja_repo.obtener_sesion_abierta(usuario_id) if pago_es_efectivo else None
        if pago_es_efectivo and not sesion_caja:
            raise CompraError("Debe abrir la caja para registrar una compra pagada al contado.")
        caja_sesion_id = sesion_caja.id if sesion_caja else None

        with self.db.transaction() as cur:
            compra_id = self.compra_repo.crear_compra(
                cur, proveedor_id, numero_documento, subtotal, impuesto, total,
                pago_es_efectivo, caja_sesion_id, usuario_id,
            )

            for linea in lineas:
                cur.execute(
                    "SELECT stock_actual, costo_promedio_actual FROM productos WHERE id = ?",
                    (linea.producto_id,),
                )
                fila = cur.fetchone()
                stock_actual = fila["stock_actual"]
                costo_promedio_actual = fila["costo_promedio_actual"]

                detalle_id = self.compra_repo.crear_linea_detalle(
                    cur, compra_id, linea.producto_id, linea.cantidad,
                    linea.costo_unitario, linea.subtotal,
                )

                nuevo_costo_promedio = calcular_costo_promedio_ponderado(
                    stock_actual, costo_promedio_actual, linea.cantidad, linea.costo_unitario,
                )
                nuevo_stock = stock_actual + linea.cantidad

                cur.execute(
                    "UPDATE productos SET stock_actual = ?, costo_promedio_actual = ? WHERE id = ?",
                    (nuevo_stock, nuevo_costo_promedio, linea.producto_id),
                )

                self.compra_repo.registrar_historial_costo(
                    cur, linea.producto_id, linea.costo_unitario, nuevo_costo_promedio, detalle_id,
                )

                self.inventario_repo.registrar_movimiento(
                    cur, linea.producto_id, "entrada", linea.cantidad, "compra", compra_id, usuario_id,
                )

            if pago_es_efectivo and caja_sesion_id:
                self.caja_repo.registrar_movimiento(
                    cur, caja_sesion_id, "egreso", total, f"Compra #{compra_id}", compra_id,
                )

            return compra_id

    def listar_compras(self):
        return self.compra_repo.listar_compras()

    def obtener_compra_con_lineas(self, compra_id: int) -> dict:
        lineas = self.compra_repo.obtener_lineas(compra_id)
        return {"lineas": lineas}
