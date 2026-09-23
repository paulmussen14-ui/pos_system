"""Acceso a datos de la tabla usuarios. Solo CRUD, sin lógica de negocio."""

from database.connection import get_db
from models.usuario import Usuario


class UsuarioRepository:

    def __init__(self):
        self.db = get_db()

    def existe_usuario(self) -> bool:
        """El sistema debe tener solo UNA cuenta de administrador."""
        cur = self.db.get_connection().execute("SELECT COUNT(*) AS total FROM usuarios")
        return cur.fetchone()["total"] > 0

    def crear(self, nombre: str, usuario: str, password_hash: str, recovery_code_hash: str) -> int:
        with self.db.transaction() as cur:
            cur.execute(
                """INSERT INTO usuarios (nombre, usuario, password_hash, recovery_code_hash)
                   VALUES (?, ?, ?, ?)""",
                (nombre, usuario, password_hash, recovery_code_hash),
            )
            return cur.lastrowid

    def obtener_por_usuario(self, usuario: str) -> Usuario | None:
        cur = self.db.get_connection().execute(
            "SELECT * FROM usuarios WHERE usuario = ?", (usuario,)
        )
        row = cur.fetchone()
        return Usuario.from_row(row) if row else None

    def obtener_por_id(self, usuario_id: int) -> Usuario | None:
        cur = self.db.get_connection().execute(
            "SELECT * FROM usuarios WHERE id = ?", (usuario_id,)
        )
        row = cur.fetchone()
        return Usuario.from_row(row) if row else None

    def obtener_unico(self) -> Usuario | None:
        """Como solo existe una cuenta, la obtiene directamente."""
        cur = self.db.get_connection().execute("SELECT * FROM usuarios LIMIT 1")
        row = cur.fetchone()
        return Usuario.from_row(row) if row else None

    def actualizar_password(self, usuario_id: int, nuevo_password_hash: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE usuarios SET password_hash = ? WHERE id = ?",
                (nuevo_password_hash, usuario_id),
            )

    def marcar_codigo_recuperacion_usado(self, usuario_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE usuarios SET recovery_code_usado = 1 WHERE id = ?",
                (usuario_id,),
            )

    def actualizar_codigo_recuperacion(self, usuario_id: int, nuevo_codigo_hash: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE usuarios SET recovery_code_hash = ?, recovery_code_usado = 0 WHERE id = ?",
                (nuevo_codigo_hash, usuario_id),
            )
