from dataclasses import dataclass
from typing import Optional


@dataclass
class Producto:
    id: Optional[int]
    nombre: str
    categoria_id: Optional[int]
    marca: Optional[str]
    unidad_medida: str
    precio_venta_actual: float
    costo_promedio_actual: float
    stock_actual: float
    stock_minimo: float
    proveedor_id: Optional[int]
    activo: bool = True
    categoria_nombre: Optional[str] = None  # relleno por joins, no persistido
    proveedor_nombre: Optional[str] = None  # relleno por joins, no persistido

    @property
    def stock_bajo(self) -> bool:
        return self.stock_actual <= self.stock_minimo and self.stock_actual > 0

    @property
    def agotado(self) -> bool:
        return self.stock_actual <= 0

    @classmethod
    def from_row(cls, row) -> "Producto":
        return cls(
            id=row["id"],
            nombre=row["nombre"],
            categoria_id=row["categoria_id"],
            marca=row["marca"],
            unidad_medida=row["unidad_medida"],
            precio_venta_actual=row["precio_venta_actual"],
            costo_promedio_actual=row["costo_promedio_actual"],
            stock_actual=row["stock_actual"],
            stock_minimo=row["stock_minimo"],
            proveedor_id=row["proveedor_id"],
            activo=bool(row["activo"]),
            categoria_nombre=row["categoria_nombre"] if "categoria_nombre" in row.keys() else None,
            proveedor_nombre=row["proveedor_nombre"] if "proveedor_nombre" in row.keys() else None,
        )
