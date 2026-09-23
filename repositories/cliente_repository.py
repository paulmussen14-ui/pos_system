"""Acceso a datos de clientes."""

from database.connection import get_db
from models.cliente import Cliente
from utils.busqueda import filtro_por_palabras


class ClienteRepository:

    def __init__(self):
        self.db = get_db()

    def listar(self, texto_busqueda: str = "", limite: int | None = None, offset: int = 0) -> list[Cliente]:
        """
        limite/offset: si se indica limite, la consulta trae como máximo esa
        cantidad de filas a partir de offset (paginación), en vez de traer
        toda la tabla de una vez. Si limite es None, se comporta igual que
        antes (trae todo lo que cumpla el filtro).
        """
        # Búsqueda por LIKE: cada palabra escrita debe aparecer en el nombre,
        # el teléfono o el documento, en cualquier orden y en cualquier parte
        # (ej. "perez juan" encuentra "Juan Perez", "987" encuentra por teléfono).
        # No usa FTS a propósito: con FTS solo se encuentra por inicio de
        # palabra y un símbolo raro puede hacer fallar la consulta.
        filtro, params = filtro_por_palabras(
            ["nombre", "telefono", "documento"], texto_busqueda
        )

        query = "SELECT * FROM clientes"
        if filtro:
            query += " WHERE " + filtro
        query += " ORDER BY nombre ASC"

        if limite is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limite, offset])

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