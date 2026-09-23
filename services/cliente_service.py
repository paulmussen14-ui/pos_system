"""Lógica de negocio de clientes."""

from repositories.cliente_repository import ClienteRepository
from models.cliente import Cliente


class ClienteError(Exception):
    pass


class ClienteService:

    def __init__(self):
        self.cliente_repo = ClienteRepository()

    def listar(self, texto_busqueda: str = ""):
        return self.cliente_repo.listar(texto_busqueda)

    def obtener_por_id(self, cliente_id: int):
        return self.cliente_repo.obtener_por_id(cliente_id)

    def crear(self, nombre: str, telefono: str, direccion: str) -> int:
        nombre = nombre.strip()
        if not nombre:
            raise ClienteError("El nombre del cliente es obligatorio.")
        cliente = Cliente(id=None, nombre=nombre, documento="",
                           telefono=telefono.strip(), direccion=direccion.strip())
        return self.cliente_repo.crear(cliente)

    def actualizar(self, cliente_id: int, nombre: str, telefono: str, direccion: str) -> None:
        nombre = nombre.strip()
        if not nombre:
            raise ClienteError("El nombre del cliente es obligatorio.")
        cliente = Cliente(id=cliente_id, nombre=nombre, documento="",
                           telefono=telefono.strip(), direccion=direccion.strip())
        self.cliente_repo.actualizar(cliente)

    def eliminar(self, cliente_id: int) -> None:
        self.cliente_repo.eliminar(cliente_id)

    def historial_compras(self, cliente_id: int):
        return self.cliente_repo.historial_compras(cliente_id)
