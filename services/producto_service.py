"""Lógica de negocio de productos: validaciones antes de delegar al repositorio."""

from repositories.producto_repository import ProductoRepository
from models.producto import Producto
from models.producto_presentacion import ProductoPresentacion


class ProductoError(Exception):
    pass


class ProductoService:

    def __init__(self):
        self.producto_repo = ProductoRepository()

    def listar(self, texto_busqueda: str = ""):
        return self.producto_repo.listar(solo_activos=True, texto_busqueda=texto_busqueda)

    def obtener(self, producto_id: int):
        return self.producto_repo.obtener_por_id(producto_id)

    def crear_producto(self, nombre: str, categoria_id, marca: str, unidad_medida: str,
                        precio_venta: float, stock_inicial: float, stock_minimo: float,
                        proveedor_id, costo_inicial: float = 0.0) -> int:
        nombre = nombre.strip()
        if not nombre:
            raise ProductoError("El nombre del producto es obligatorio.")
        if precio_venta < 0:
            raise ProductoError("El precio de venta no puede ser negativo.")
        if stock_inicial < 0:
            raise ProductoError("El stock inicial no puede ser negativo.")
        if stock_minimo < 0:
            raise ProductoError("El stock mínimo no puede ser negativo.")

        producto = Producto(
            id=None, nombre=nombre, categoria_id=categoria_id, marca=marca.strip() if marca else None,
            unidad_medida=unidad_medida.strip() or "unidad", precio_venta_actual=precio_venta,
            costo_promedio_actual=costo_inicial, stock_actual=stock_inicial,
            stock_minimo=stock_minimo, proveedor_id=proveedor_id, activo=True,
        )
        return self.producto_repo.crear(producto)

    def actualizar_producto(self, producto_id: int, nombre: str, categoria_id, marca: str,
                             unidad_medida: str, precio_venta: float, stock_minimo: float,
                             proveedor_id) -> None:
        existente = self.producto_repo.obtener_por_id(producto_id)
        if not existente:
            raise ProductoError("Producto no encontrado.")

        nombre = nombre.strip()
        if not nombre:
            raise ProductoError("El nombre del producto es obligatorio.")
        if precio_venta < 0:
            raise ProductoError("El precio de venta no puede ser negativo.")

        precio_cambio = precio_venta != existente.precio_venta_actual

        producto = Producto(
            id=producto_id, nombre=nombre, categoria_id=categoria_id, marca=marca.strip() if marca else None,
            unidad_medida=unidad_medida.strip() or "unidad", precio_venta_actual=precio_venta,
            costo_promedio_actual=existente.costo_promedio_actual, stock_actual=existente.stock_actual,
            stock_minimo=stock_minimo, proveedor_id=proveedor_id, activo=True,
        )
        self.producto_repo.actualizar(producto, registrar_cambio_precio=precio_cambio)

    def desactivar_producto(self, producto_id: int) -> None:
        self.producto_repo.desactivar(producto_id)

    def historial_costos(self, producto_id: int):
        return self.producto_repo.historial_costos(producto_id)

    def categorias(self):
        return self.producto_repo.listar_categorias()

    def crear_categoria(self, nombre: str) -> int:
        nombre = nombre.strip()
        if not nombre:
            raise ProductoError("El nombre de la categoría es obligatorio.")
        return self.producto_repo.crear_categoria(nombre)

    def proveedores(self):
        return self.producto_repo.listar_proveedores()

    def crear_proveedor(self, nombre: str, documento: str = "", telefono: str = "", direccion: str = "") -> int:
        nombre = nombre.strip()
        if not nombre:
            raise ProductoError("El nombre del proveedor es obligatorio.")
        return self.producto_repo.crear_proveedor(nombre, documento, telefono, direccion)

    # ---- Presentaciones de venta (caja, docena, paquete, etc.) ----
    def presentaciones(self, producto_id: int) -> list[ProductoPresentacion]:
        return self.producto_repo.listar_presentaciones(producto_id)

    def guardar_presentaciones(self, producto_id: int, filas: list[dict]) -> None:
        """Recibe la lista de presentaciones tal como quedó en el formulario
        (cada fila: {"nombre": str, "cantidad_unidades": float, "precio": float}),
        valida y reemplaza todas las presentaciones del producto.
        Filas completamente vacías se ignoran (el usuario dejó una fila sin usar)."""
        presentaciones: list[ProductoPresentacion] = []
        for fila in filas:
            nombre = (fila.get("nombre") or "").strip()
            cantidad = fila.get("cantidad_unidades")
            precio = fila.get("precio")

            if not nombre and not cantidad and not precio:
                continue  # fila vacía, se descarta sin avisar

            if not nombre:
                raise ProductoError("Cada presentación necesita un nombre (ej. Caja, Docena).")
            try:
                cantidad = float(cantidad)
                precio = float(precio)
            except (TypeError, ValueError):
                raise ProductoError(f"La presentación \"{nombre}\" tiene cantidad o precio inválido.")
            if cantidad <= 0:
                raise ProductoError(f"La presentación \"{nombre}\" debe equivaler a más de 0 unidades.")
            if precio < 0:
                raise ProductoError(f"La presentación \"{nombre}\" no puede tener precio negativo.")

            presentaciones.append(
                ProductoPresentacion(
                    id=None, producto_id=producto_id, nombre=nombre,
                    cantidad_unidades=cantidad, precio=precio,
                )
            )

        nombres = [p.nombre.lower() for p in presentaciones]
        if len(nombres) != len(set(nombres)):
            raise ProductoError("Hay presentaciones con el mismo nombre; usa nombres distintos.")

        self.producto_repo.reemplazar_presentaciones(producto_id, presentaciones)