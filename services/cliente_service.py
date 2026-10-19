"""Lógica de negocio de clientes."""

from repositories.cliente_repository import ClienteRepository
from models.cliente import Cliente


class ClienteError(Exception):
    pass


class ClienteService:

    def __init__(self):
        self.cliente_repo = ClienteRepository()

    def listar(self, texto_busqueda: str = "", limite: int | None = None, offset: int = 0):
        return self.cliente_repo.listar(texto_busqueda, limite=limite, offset=offset)

    def obtener_por_id(self, cliente_id: int):
        return self.cliente_repo.obtener_por_id(cliente_id)

    def crear(self, nombre: str, telefono: str, direccion: str, documento: str = "",
              email: str = "") -> int:
        nombre = nombre.strip()
        if not nombre:
            raise ClienteError("El nombre del cliente es obligatorio.")
        cliente = Cliente(id=None, nombre=nombre, documento=(documento or "").strip(),
                           telefono=telefono.strip(), direccion=direccion.strip(),
                           email=(email or "").strip())
        return self.cliente_repo.crear(cliente)

    def actualizar(self, cliente_id: int, nombre: str, telefono: str, direccion: str,
                    documento: str | None = None, email: str | None = None) -> None:
        """documento=None / email=None conservan lo que el cliente ya tenia (asi
        una pantalla que no los edita no los borra por accidente). Para borrarlos
        a proposito, pasar "" ."""
        nombre = nombre.strip()
        if not nombre:
            raise ClienteError("El nombre del cliente es obligatorio.")
        existente = None
        if documento is None or email is None:
            existente = self.cliente_repo.obtener_por_id(cliente_id)
        if documento is None:
            documento = (existente.documento if existente else "") or ""
        if email is None:
            email = (existente.email if existente else "") or ""
        cliente = Cliente(id=cliente_id, nombre=nombre, documento=documento.strip(),
                           telefono=telefono.strip(), direccion=direccion.strip(),
                           email=email.strip())
        self.cliente_repo.actualizar(cliente)

    def eliminar(self, cliente_id: int) -> None:
        self.cliente_repo.eliminar(cliente_id)

    def historial_compras(self, cliente_id: int):
        return self.cliente_repo.historial_compras(cliente_id)