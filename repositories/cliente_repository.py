"""Acceso a datos de clientes."""

from database.connection import get_db
from models.cliente import Cliente


class ClienteRepository:

    def __init__(self):
        self.db = get_db()

    def listar(self, texto_busqueda: str = "") -> list[Cliente]:
        texto_busqueda = texto_busqueda.strip()
        if texto_busqueda:
            # FTS5 MATCH usa el índice invertido, a diferencia de
            # LIKE '%texto%' que fuerza un escaneo completo de la tabla.
            # Se envuelve en comillas + "*" para hacer match por prefijo
            # de palabra (ej. "gase" encuentra "Gaseosa Inca Kola").
            match_expr = f'"{texto_busqueda.replace(chr(34), chr(34) * 2)}"*'
            query = """
                SELECT c.* FROM clientes c
                JOIN clientes_fts fts ON fts.rowid = c.id
                WHERE clientes_fts MATCH ?
                ORDER BY c.nombre ASC
            """
            params = [match_expr]
        else:
            query = "SELECT * FROM clientes ORDER BY nombre ASC"
            params = []

        cur = self.db.get_connection().execute(query, params)
        return [Cliente.from_row(r) for r in cur.fetchall()]

    def obtener_por_id(self, cliente_id: int) -> Cliente | None:
        cur = self.db.get_connection().execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,))
        row = cur.fetchone()
        return Cliente.from_row(row) if row else None

    def crear(self, cliente: Cliente) -> int:
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO clientes (nombre, documento, telefono, direccion) VALUES (?, ?, ?, ?)",
                (cliente.nombre, cliente.documento, cliente.telefono, cliente.direccion),
            )
            return cur.lastrowid

    def actualizar(self, cliente: Cliente) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE clientes SET nombre = ?, documento = ?, telefono = ?, direccion = ? WHERE id = ?",
                (cliente.nombre, cliente.documento, cliente.telefono, cliente.direccion, cliente.id),
            )

    def eliminar(self, cliente_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))

    def historial_compras(self, cliente_id: int) -> list[dict]:
        cur = self.db.get_connection().execute(
            """SELECT * FROM ventas WHERE cliente_id = ? AND estado = 'completada'
               ORDER BY fecha DESC""",
            (cliente_id,),
        )
        return [dict(r) for r in cur.fetchall()]