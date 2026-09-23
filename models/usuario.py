from dataclasses import dataclass
from typing import Optional


@dataclass
class Usuario:
    id: Optional[int]
    nombre: str
    usuario: str
    password_hash: str
    recovery_code_hash: str
    recovery_code_usado: bool

    @classmethod
    def from_row(cls, row) -> "Usuario":
        return cls(
            id=row["id"],
            nombre=row["nombre"],
            usuario=row["usuario"],
            password_hash=row["password_hash"],
            recovery_code_hash=row["recovery_code_hash"],
            recovery_code_usado=bool(row["recovery_code_usado"]),
        )
