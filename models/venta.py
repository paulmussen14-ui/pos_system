from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VentaDetalleItem:
    """Línea de venta usada en memoria mientras se arma el carrito en la UI.

    `cantidad` y `precio_venta_unitario` siempre están en la UNIDAD BASE
    del producto (la misma que usan inventario y stock), para no romper
    nada de lo que ya depende de esos dos campos. `presentacion_nombre`,
    `cantidad_presentacion` y `factor_unidades` son solo para mostrar y
    editar en qué medida se vendió (ej. "2 Caja" = factor 24 = 48
    unidades base), igual que ya se hace en compras."""
    producto_id: int
    nombre_producto: str
    cantidad: float
    precio_venta_unitario: float
    costo_unitario_snapshot: float  # oculto al usuario, solo interno
    presentacion_nombre: str = "Unidad"
    cantidad_presentacion: Optional[float] = None
    factor_unidades: float = 1.0

    def __post_init__(self):
        if self.cantidad_presentacion is None:
            self.cantidad_presentacion = (
                self.cantidad / self.factor_unidades if self.factor_unidades else self.cantidad
            )

    @property
    def subtotal(self) -> float:
        return round(self.cantidad * self.precio_venta_unitario, 2)

    @property
    def precio_presentacion_unitario(self) -> float:
        """Precio de una unidad completa de la presentación elegida
        (ej. el precio de 1 caja), solo para mostrar en el carrito."""
        return round(self.precio_venta_unitario * self.factor_unidades, 2)


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