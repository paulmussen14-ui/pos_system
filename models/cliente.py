from dataclasses import dataclass
from typing import Optional


@dataclass
class Cliente:
    id: Optional[int]
    nombre: str
    documento: Optional[str]
    telefono: Optional[str]
    direccion: Optional[str]
    email: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Cliente":
        return cls(
            id=row["id"],
            nombre=row["nombre"],
            documento=row["documento"],
            telefono=row["telefono"],
            direccion=row["direccion"],
            email=row["email"] if "email" in row.keys() else None,
        )
