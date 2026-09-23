"""
Lógica de negocio de ventas.

El registro de una venta es una operación atómica que debe:
1. Validar stock disponible de cada línea.
2. Insertar cabecera + líneas.
3. Congelar el costo vigente de cada producto en costo_unitario_snapshot
   (así la utilidad histórica nunca cambia si el costo cambia después).
4. Descontar stock y registrar el movimiento de inventario.
5. Si el pago es en efectivo, registrar el movimiento de caja.

Todo dentro de una única transacción SQLite (todo o nada).
"""

from database.connection import get_db
from repositories.producto_repository import ProductoRepository
from repositories.venta_repository import VentaRepository
from repositories.inventario_repository import InventarioRepository
from repositories.caja_repository import CajaRepository
from models.venta import VentaDetalleItem


class VentaError(Exception):
    """Error de negocio en el flujo de ventas (mensaje apto para mostrar al usuario)."""


class VentaService:

    def __init__(self):
        self.db = get_db()
        self.producto_repo = ProductoRepository()
        self.venta_repo = VentaRepository()
        self.inventario_repo = InventarioRepository()
        self.caja_repo = CajaRepository()

    def registrar_venta(
        self,
        lineas: list[VentaDetalleItem],
        usuario_id: int,
        cliente_id: int | None,
        metodo_pago_id: int | None,
        descuento: float = 0.0,
    ) -> int:
        if not lineas:
            raise VentaError("La venta debe tener al menos un producto.")
        if descuento < 0:
            raise VentaError("El descuento no puede ser negativo.")

        # El flag "es_efectivo" se determina desde la configuración del método
        # de pago (no adivinando por el nombre), y se congela en la venta.
        pago_es_efectivo = self.venta_repo.metodo_pago_es_efectivo(metodo_pago_id)

        sesion_caja = self.caja_repo.obtener_sesion_abierta(usuario_id)
        if pago_es_efectivo and not sesion_caja:
            raise VentaError("Debe abrir la caja antes de registrar ventas en efectivo.")

        # Validar stock disponible de todas las líneas ANTES de tocar la BD
        for linea in lineas:
            producto = self.producto_repo.obtener_por_id(linea.producto_id)
            if not producto or not producto.activo:
                raise VentaError(f"El producto '{linea.nombre_producto}' no está disponible.")
            if linea.cantidad <= 0:
                raise VentaError(f"La cantidad de '{linea.nombre_producto}' debe ser mayor a cero.")
            if producto.stock_actual < linea.cantidad:
                raise VentaError(
                    f"Stock insuficiente de '{linea.nombre_producto}' "
                    f"(disponible: {producto.stock_actual}, solicitado: {linea.cantidad})."
                )

        subtotal = round(sum(l.subtotal for l in lineas), 2)
        if descuento > subtotal:
            raise VentaError("El descuento no puede ser mayor que el subtotal.")
        total = round(subtotal - descuento, 2)

        caja_sesion_id = sesion_caja.id if sesion_caja else None

        with self.db.transaction() as cur:
            venta_id = self.venta_repo.crear_venta(
                cur, cliente_id, usuario_id, subtotal, descuento, total,
                metodo_pago_id, pago_es_efectivo, caja_sesion_id,
            )

            for linea in lineas:
                # Se vuelve a leer el costo vigente dentro de la transacción
                cur.execute("SELECT stock_actual, costo_promedio_actual FROM productos WHERE id = ?",
                            (linea.producto_id,))
                fila = cur.fetchone()
                stock_actual = fila["stock_actual"]
                costo_vigente = fila["costo_promedio_actual"]

                if stock_actual < linea.cantidad:
                    raise VentaError(f"Stock insuficiente de '{linea.nombre_producto}'.")

                self.venta_repo.crear_linea_detalle(
                    cur, venta_id, linea.producto_id, linea.cantidad,
                    linea.precio_venta_unitario, costo_vigente, linea.subtotal,
                )

                nuevo_stock = stock_actual - linea.cantidad
                cur.execute("UPDATE productos SET stock_actual = ? WHERE id = ?",
                            (nuevo_stock, linea.producto_id))

                self.inventario_repo.registrar_movimiento(
                    cur, linea.producto_id, "salida", linea.cantidad, "venta", venta_id, usuario_id,
                )

            if pago_es_efectivo and caja_sesion_id:
                self.caja_repo.registrar_movimiento(
                    cur, caja_sesion_id, "venta", total, f"Venta #{venta_id}", venta_id,
                )

            return venta_id

    def anular_venta(self, venta_id: int, usuario_id: int) -> None:
        venta = self.venta_repo.obtener_venta(venta_id)
        if not venta:
            raise VentaError("Venta no encontrada.")
        if venta["estado"] == "anulada":
            raise VentaError("La venta ya está anulada.")

        lineas = self.venta_repo.obtener_lineas(venta_id)

        with self.db.transaction() as cur:
            self.venta_repo.anular_venta(cur, venta_id)

            for linea in lineas:
                cur.execute("SELECT stock_actual FROM productos WHERE id = ?", (linea["producto_id"],))
                stock_actual = cur.fetchone()["stock_actual"]
                nuevo_stock = stock_actual + linea["cantidad"]
                cur.execute("UPDATE productos SET stock_actual = ? WHERE id = ?",
                            (nuevo_stock, linea["producto_id"]))

                self.inventario_repo.registrar_movimiento(
                    cur, linea["producto_id"], "entrada", linea["cantidad"],
                    "anulacion", venta_id, usuario_id,
                )

            # Solo se revierte el dinero de caja si la venta original fue en
            # efectivo (usamos el snapshot pago_es_efectivo, no el método de
            # pago actual, que pudo haber cambiado de configuración después).
            if venta["caja_sesion_id"] and venta["pago_es_efectivo"]:
                self.caja_repo.registrar_movimiento(
                    cur, venta["caja_sesion_id"], "egreso", venta["total"],
                    f"Anulación venta #{venta_id}", venta_id,
                )

    def registrar_devolucion(self, venta_id: int, producto_id: int, cantidad: float,
                              motivo: str, usuario_id: int) -> int:
        if cantidad <= 0:
            raise VentaError("La cantidad a devolver debe ser mayor a cero.")

        lineas = self.venta_repo.obtener_lineas(venta_id)
        linea = next((l for l in lineas if l["producto_id"] == producto_id), None)
        if not linea:
            raise VentaError("Ese producto no pertenece a la venta indicada.")
        if cantidad > linea["cantidad"]:
            raise VentaError("No puede devolver más cantidad de la vendida.")

        devolucion_id = self.venta_repo.crear_devolucion(venta_id, producto_id, cantidad, motivo, usuario_id)

        with self.db.transaction() as cur:
            cur.execute("SELECT stock_actual FROM productos WHERE id = ?", (producto_id,))
            stock_actual = cur.fetchone()["stock_actual"]
            cur.execute("UPDATE productos SET stock_actual = ? WHERE id = ?",
                        (stock_actual + cantidad, producto_id))
            self.inventario_repo.registrar_movimiento(
                cur, producto_id, "entrada", cantidad, "devolucion", venta_id, usuario_id,
            )

        return devolucion_id

    def obtener_venta_con_lineas(self, venta_id: int) -> dict | None:
        venta = self.venta_repo.obtener_venta(venta_id)
        if not venta:
            return None
        venta["lineas"] = self.venta_repo.obtener_lineas(venta_id)
        return venta

    def listar_ventas(self, fecha_desde: str = "", fecha_hasta: str = ""):
        return self.venta_repo.listar_ventas(fecha_desde, fecha_hasta)

    def metodos_pago(self):
        return self.venta_repo.listar_metodos_pago()
    def cambiar_cliente(self, venta_id: int, cliente_id: int | None) -> None:
        venta = self.venta_repo.obtener_venta(venta_id)
        if not venta:
            raise VentaError("Venta no encontrada.")
        with self.db.transaction() as cur:
            self.venta_repo.actualizar_cliente(cur, venta_id, cliente_id)
