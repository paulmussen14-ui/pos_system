from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompraDetalleItem:
    """Línea de compra usada en memoria mientras se arma el formulario en la UI."""
    producto_id: int
    nombre_producto: str
    cantidad: float
    costo_unitario: float

    @property
    def subtotal(self) -> float:
        return round(self.cantidad * self.costo_unitario, 2)


@dataclass
class Compra:
    id: Optional[int]
    proveedor_id: Optional[int]
    numero_documento: Optional[str]
    fecha: str
    subtotal: float
    impuesto: float
    total: float
    usuario_id: int
    proveedor_nombre: Optional[str] = None
    lineas: list = field(default_factory=list)
