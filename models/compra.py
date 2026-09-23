from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompraDetalleItem:
    """Línea de compra usada en memoria mientras se arma el formulario en la UI.

    `cantidad` y `costo_unitario` siempre están en la UNIDAD BASE del
    producto (la misma que usan inventario y el costo promedio ponderado),
    para no romper nada de lo que ya depende de esos dos campos.
    `presentacion_nombre`, `cantidad_presentacion` y `factor_unidades` son
    solo para mostrar y editar en qué medida se digitó la compra
    (ej. "3 Caja" = factor 24 = 72 unidades base)."""
    producto_id: int
    nombre_producto: str
    cantidad: float
    costo_unitario: float
    presentacion_nombre: str = "Unidad"
    cantidad_presentacion: Optional[float] = None
    factor_unidades: float = 1.0

    def __post_init__(self):
        if self.cantidad_presentacion is None:
            self.cantidad_presentacion = self.cantidad

    @property
    def subtotal(self) -> float:
        return round(self.cantidad * self.costo_unitario, 2)

    @property
    def costo_presentacion_total(self) -> float:
        """Costo de una unidad completa de la presentación elegida
        (ej. el costo de 1 caja), para precargar el formulario al editar."""
        return round(self.costo_unitario * self.factor_unidades, 2)


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