from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VentaDetalleItem:
    """Línea de venta usada en memoria mientras se arma el carrito en la UI."""
    producto_id: int
    nombre_producto: str
    cantidad: float
    precio_venta_unitario: float
    costo_unitario_snapshot: float  # oculto al usuario, solo interno

    @property
    def subtotal(self) -> float:
        return round(self.cantidad * self.precio_venta_unitario, 2)


@dataclass
class Venta:
    id: Optional[int]
    cliente_id: Optional[int]
    usuario_id: int
    fecha: str
    subtotal: float
    descuento: float
    total: float
    metodo_pago_id: Optional[int]
    estado: str
    caja_sesion_id: Optional[int]
    cliente_nombre: Optional[str] = None
    metodo_pago_nombre: Optional[str] = None
    lineas: list = field(default_factory=list)
