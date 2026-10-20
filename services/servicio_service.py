"""Catálogo de servicios del modelo de negocio "servicios" (consultas, cortes, sesiones...).

Cada servicio tiene un precio base y una duración sugerida (que la agenda usa al reservar).
Además puede tener:
  - opciones (tabla subservicios): adicionales con su propio costo, que se SUMA al precio base
    (nunca vienen incluidos en el servicio). Se definen UNA sola vez en un catálogo global y
    cada servicio solo marca cuáles le aplican (tabla servicio_subservicios). Dos clases:
      · efecto: se cobra aparte y se pueden elegir varios a la vez.
      · tipo: otra modalidad del servicio (no es un efecto); se elige uno solo.
  - productos: lo que se usa o entrega al atender; al cobrar descuentan stock, y cada uno
    puede cobrarse aparte (suma su precio) o ir incluido en el precio del servicio.

Para que lo cobrado salga en Caja, Reportes y el historial de ventas igual que
cualquier venta, cada servicio tiene un producto OCULTO asociado (activo = 0,
sin stock). Nunca aparece en Productos ni en las alertas de inventario.
"""

from database.connection import get_db


CLASE_EFECTO = "efecto"
CLASE_TIPO = "tipo"
CLASES_SUBSERVICIO = (CLASE_EFECTO, CLASE_TIPO)


class ServicioError(Exception):
    """Error de validación del catálogo de servicios (mensaje apto para el usuario)."""


def _validar(nombre: str, precio: float, duracion_min: int) -> str:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ServicioError("El nombre del servicio es obligatorio.")
    if precio is None or precio < 0:
        raise ServicioError("El precio no puede ser negativo.")
    if not (5 <= int(duracion_min) <= 480):
        raise ServicioError("La duración debe estar entre 5 minutos y 8 horas.")
    return nombre


class ServicioService:

    def __init__(self):
        self.db = get_db()

    def listar(self, solo_activos: bool = True) -> list[dict]:
        consulta = "SELECT * FROM servicios"
        if solo_activos:
            consulta += " WHERE activo = 1"
        consulta += " ORDER BY nombre COLLATE NOCASE"
        return [dict(f) for f in self.db.get_connection().execute(consulta).fetchall()]

    def obtener(self, servicio_id: int) -> dict | None:
        fila = self.db.get_connection().execute(
            "SELECT * FROM servicios WHERE id = ?", (servicio_id,)
        ).fetchone()
        return dict(fila) if fila else None

    def crear(self, nombre: str, precio: float, duracion_min: int,
              opcion_ids: list[int] | None = None, productos: list[dict] | None = None) -> int:
        nombre = _validar(nombre, precio, duracion_min)
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO servicios (nombre, precio, duracion_min) VALUES (?, ?, ?)",
                (nombre, round(float(precio), 2), int(duracion_min)),
            )
            servicio_id = cur.lastrowid
            self.asegurar_producto(cur, servicio_id)
            self._guardar_detalle(cur, servicio_id, opcion_ids, productos)
            return servicio_id

    def actualizar(self, servicio_id: int, nombre: str, precio: float, duracion_min: int,
                   opcion_ids: list[int] | None = None, productos: list[dict] | None = None) -> None:
        nombre = _validar(nombre, precio, duracion_min)
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE servicios SET nombre = ?, precio = ?, duracion_min = ? WHERE id = ?",
                (nombre, round(float(precio), 2), int(duracion_min), servicio_id),
            )
            self.asegurar_producto(cur, servicio_id)
            self._guardar_detalle(cur, servicio_id, opcion_ids, productos)

    def cambiar_activo(self, servicio_id: int, activo: bool) -> None:
        with self.db.transaction() as cur:
            cur.execute("UPDATE servicios SET activo = ? WHERE id = ?", (int(activo), servicio_id))

    def asegurar_producto(self, cur, servicio_id: int) -> int:
        """Devuelve el id del producto oculto del servicio, creándolo si hace falta,
        y deja su nombre y precio al día. Debe llamarse dentro de una transacción."""
        cur.execute("SELECT nombre, precio, producto_id FROM servicios WHERE id = ?", (servicio_id,))
        servicio = cur.fetchone()
        if servicio is None:
            raise ServicioError("El servicio ya no existe.")

        producto_id = servicio["producto_id"]
        if producto_id:
            cur.execute("SELECT id FROM productos WHERE id = ?", (producto_id,))
            if cur.fetchone() is None:
                producto_id = None

        if producto_id:
            cur.execute(
                "UPDATE productos SET nombre = ?, precio_venta_actual = ? WHERE id = ?",
                (servicio["nombre"], servicio["precio"], producto_id),
            )
        else:
            cur.execute(
                """INSERT INTO productos (nombre, unidad_medida, precio_venta_actual,
                                          costo_promedio_actual, stock_actual, stock_minimo, activo)
                   VALUES (?, 'servicio', ?, 0, 0, 0, 0)""",
                (servicio["nombre"], servicio["precio"]),
            )
            producto_id = cur.lastrowid
            cur.execute("UPDATE servicios SET producto_id = ? WHERE id = ?", (producto_id, servicio_id))
        return producto_id

    # ---------------------------------------- Sub-servicios y productos ----
    def listar_subservicios(self, servicio_id: int, solo_activos: bool = True) -> list[dict]:
        """Opciones (efectos y tipos) que aplican a este servicio, tomadas del catálogo global."""
        consulta = ("SELECT s.* FROM subservicios s "
                    "JOIN servicio_subservicios v ON v.subservicio_id = s.id WHERE v.servicio_id = ?")
        if solo_activos:
            consulta += " AND s.activo = 1"
        consulta += " ORDER BY s.nombre COLLATE NOCASE"
        return [dict(f) for f in self.db.get_connection().execute(consulta, (servicio_id,)).fetchall()]

    # -------------------------------------------- Catálogo de opciones ----
    def listar_opciones(self, solo_activas: bool = True) -> list[dict]:
        """Todo el catálogo de opciones (efectos primero, luego tipos de servicio)."""
        consulta = "SELECT * FROM subservicios"
        if solo_activas:
            consulta += " WHERE activo = 1"
        consulta += " ORDER BY clase = 'tipo', nombre COLLATE NOCASE"
        return [dict(f) for f in self.db.get_connection().execute(consulta).fetchall()]

    def contar_servicios_de_opcion(self, opcion_id: int) -> int:
        """En cuántos servicios está marcada esta opción."""
        return self.db.get_connection().execute(
            "SELECT COUNT(*) FROM servicio_subservicios WHERE subservicio_id = ?",
            (opcion_id,)).fetchone()[0]

    def guardar_opcion(self, nombre: str, precio: float, clase: str, opcion_id: int | None = None) -> int:
        """Crea (o edita, si viene opcion_id) una opción del catálogo. No se permiten dos
        opciones con el mismo nombre y clase, para no repetir datos."""
        nombre = (nombre or "").strip()
        if not nombre:
            raise ServicioError("El nombre de la opción es obligatorio.")
        if precio is None or precio < 0:
            raise ServicioError("El costo adicional no puede ser negativo.")
        if clase not in CLASES_SUBSERVICIO:
            raise ServicioError("La clase debe ser efecto o tipo de servicio.")
        precio = round(float(precio), 2)
        with self.db.transaction() as cur:
            cur.execute("SELECT id FROM subservicios WHERE lower(nombre) = lower(?) AND clase = ? AND id != ?",
                        (nombre, clase, opcion_id or 0))
            if cur.fetchone():
                raise ServicioError(f"Ya existe «{nombre}» en el catálogo; no hace falta repetirla.")
            if opcion_id:
                cur.execute("UPDATE subservicios SET nombre = ?, precio = ?, clase = ? WHERE id = ?",
                            (nombre, precio, clase, opcion_id))
            else:
                cur.execute("INSERT INTO subservicios (servicio_id, nombre, precio, clase) "
                            "VALUES (0, ?, ?, ?)", (nombre, precio, clase))
                opcion_id = cur.lastrowid
            self._asegurar_producto_subservicio(cur, opcion_id)
        return opcion_id

    def cambiar_activo_opcion(self, opcion_id: int, activo: bool) -> None:
        """Desactivar una opción la oculta de las reservas nuevas; las ya hechas la conservan."""
        with self.db.transaction() as cur:
            cur.execute("UPDATE subservicios SET activo = ? WHERE id = ?", (int(activo), opcion_id))

    def listar_productos(self, servicio_id: int) -> list[dict]:
        """Productos del servicio, con los datos del producto (nombre, precio, stock)."""
        filas = self.db.get_connection().execute(
            """SELECT sp.id, sp.producto_id, sp.cantidad, sp.cobrar,
                      p.nombre, p.precio_venta_actual AS precio, p.stock_actual, p.unidad_medida
               FROM servicio_productos sp JOIN productos p ON p.id = sp.producto_id
               WHERE sp.servicio_id = ? ORDER BY p.nombre COLLATE NOCASE""",
            (servicio_id,),
        ).fetchall()
        return [dict(f) for f in filas]

    def _guardar_detalle(self, cur, servicio_id: int, opcion_ids, productos) -> None:
        """Deja las opciones y productos del servicio exactamente como se indican
        (None = no tocar). Las opciones no se crean aquí: se marcan las del catálogo global,
        así un efecto como «Ojo de gato» se define una vez y sirve para todos los servicios."""
        if opcion_ids is not None:
            cur.execute("DELETE FROM servicio_subservicios WHERE servicio_id = ?", (servicio_id,))
            for opcion_id in dict.fromkeys(int(i) for i in opcion_ids):
                cur.execute(
                    "INSERT INTO servicio_subservicios (servicio_id, subservicio_id) "
                    "SELECT ?, id FROM subservicios WHERE id = ?", (servicio_id, opcion_id))

        if productos is not None:
            cur.execute("DELETE FROM servicio_productos WHERE servicio_id = ?", (servicio_id,))
            vistos = set()
            for prod in productos:
                producto_id = int(prod["producto_id"])
                cantidad = float(prod.get("cantidad") or 0)
                if cantidad <= 0:
                    raise ServicioError("La cantidad de cada producto debe ser mayor a cero.")
                if producto_id in vistos:
                    raise ServicioError("Un producto no puede repetirse en el mismo servicio.")
                vistos.add(producto_id)
                cur.execute(
                    "INSERT INTO servicio_productos (servicio_id, producto_id, cantidad, cobrar) "
                    "VALUES (?, ?, ?, ?)",
                    (servicio_id, producto_id, cantidad, int(bool(prod.get("cobrar")))),
                )

    def _asegurar_producto_subservicio(self, cur, subservicio_id: int) -> int:
        """Igual que asegurar_producto, pero para un sub-servicio (producto oculto propio)."""
        cur.execute("SELECT nombre, precio, producto_id FROM subservicios WHERE id = ?", (subservicio_id,))
        sub = cur.fetchone()
        producto_id = sub["producto_id"]
        if producto_id:
            cur.execute("SELECT id FROM productos WHERE id = ?", (producto_id,))
            if cur.fetchone() is None:
                producto_id = None
        if producto_id:
            cur.execute("UPDATE productos SET nombre = ?, precio_venta_actual = ? WHERE id = ?",
                        (sub["nombre"], sub["precio"], producto_id))
        else:
            cur.execute(
                """INSERT INTO productos (nombre, unidad_medida, precio_venta_actual,
                                          costo_promedio_actual, stock_actual, stock_minimo, activo)
                   VALUES (?, 'servicio', ?, 0, 0, 0, 0)""",
                (sub["nombre"], sub["precio"]),
            )
            producto_id = cur.lastrowid
            cur.execute("UPDATE subservicios SET producto_id = ? WHERE id = ?", (producto_id, subservicio_id))
        return producto_id

    def asegurar_producto_subservicio(self, cur, subservicio_id: int) -> int:
        return self._asegurar_producto_subservicio(cur, subservicio_id)

    def listar_productos_disponibles(self) -> list[dict]:
        """Productos reales que se pueden asociar a un servicio (activos; los productos
        ocultos que representan servicios no aparecen)."""
        filas = self.db.get_connection().execute(
            "SELECT id, nombre, precio_venta_actual AS precio, stock_actual, unidad_medida FROM productos "
            "WHERE activo = 1 ORDER BY nombre COLLATE NOCASE").fetchall()
        return [dict(f) for f in filas]
