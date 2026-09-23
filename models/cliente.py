from dataclasses import dataclass
from typing import Optional


@dataclass
class Cliente:
    id: Optional[int]
    nombre: str
    documento: Optional[str]
    telefono: Optional[str]
    direccion: Optional[str]

    @classmethod
    def from_row(cls, row) -> "Cliente":
        return cls(
            id=row["id"],
            nombre=row["nombre"],
            documento=row["documento"],
            telefono=row["telefono"],
            direccion=row["direccion"],
        )
