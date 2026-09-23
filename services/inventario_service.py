"""Lógica de negocio de inventario: consultas de stock, alertas, ajustes manuales."""

from repositories.producto_repository import ProductoRepository
from repositories.inventario_repository import InventarioRepository


class InventarioError(Exception):
    pass


class InventarioService:

    def __init__(self):
        self.producto_repo = ProductoRepository()
        self.inventario_repo = InventarioRepository()

    def productos_stock_bajo(self):
        return self.producto_repo.listar_stock_bajo()

    def productos_agotados(self):
        return self.producto_repo.listar_agotados()

    def movimientos(self, producto_id: int | None = None):
        return self.inventario_repo.listar_movimientos(producto_id)

    def ajustar_stock(self, producto_id: int, cantidad_nueva: float, motivo: str, usuario_id: int) -> None:
        if cantidad_nueva < 0:
            raise InventarioError("El stock no puede ser negativo.")
        if not motivo.strip():
            raise InventarioError("Debe indicar un motivo para el ajuste.")

        self.inventario_repo.registrar_ajuste_manual(producto_id, cantidad_nueva, motivo.strip(), usuario_id)
