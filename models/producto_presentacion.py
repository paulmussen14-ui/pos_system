from dataclasses import dataclass
from typing import Optional


@dataclass
class ProductoPresentacion:
    """Una forma adicional de vender/comprar un producto (caja, docena,
    paquete de 6, etc.), con su propio precio y su equivalencia en
    unidades base del producto (productos.unidad_medida)."""

    id: Optional[int]
    producto_id: int
    nombre: str
    cantidad_unidades: float  # a cuántas unidades base equivale esta presentación
    precio: float
    orden: int = 0
    activo: bool = True

    @property
    def precio_por_unidad(self) -> float:
        if self.cantidad_unidades <= 0:
            return 0.0
        return self.precio / self.cantidad_unidades

    @classmethod
    def from_row(cls, row) -> "ProductoPresentacion":
        return cls(
            id=row["id"],
            producto_id=row["producto_id"],
            nombre=row["nombre"],
            cantidad_unidades=row["cantidad_unidades"],
            precio=row["precio"],
            orden=row["orden"],
            activo=bool(row["activo"]),
        )