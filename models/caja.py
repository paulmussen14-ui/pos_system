from dataclasses import dataclass
from typing import Optional


@dataclass
class CajaSesion:
    id: Optional[int]
    usuario_id: int
    fecha_apertura: str
    monto_apertura: float
    fecha_cierre: Optional[str]
    monto_esperado: Optional[float]
    monto_contado: Optional[float]
    diferencia: Optional[float]
    estado: str  # abierta | cerrada

    @classmethod
    def from_row(cls, row) -> "CajaSesion":
        return cls(
            id=row["id"],
            usuario_id=row["usuario_id"],
            fecha_apertura=row["fecha_apertura"],
            monto_apertura=row["monto_apertura"],
            fecha_cierre=row["fecha_cierre"],
            monto_esperado=row["monto_esperado"],
            monto_contado=row["monto_contado"],
            diferencia=row["diferencia"],
            estado=row["estado"],
        )


@dataclass
class CajaMovimiento:
    id: Optional[int]
    caja_sesion_id: int
    tipo: str  # venta | ingreso_manual | egreso | retiro
    monto: float
    descripcion: Optional[str]
    referencia_id: Optional[int]
    fecha: str
