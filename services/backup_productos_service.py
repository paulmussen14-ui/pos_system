"""Exportar e importar el catálogo de productos (para migrar a otra PC).

Formato: un archivo JSON con categorías, proveedores y productos (con sus
presentaciones, stock y costo). Al importar NUNCA se pisan productos que ya
existen (se comparan por nombre, sin distinguir mayúsculas ni tildes de
mayúscula/minúscula): se omiten y se informan. El import completo es UNA sola
transacción (todo o nada) y solo empieza si TODO el archivo es válido.
"""

import json
from datetime import datetime
from pathlib import Path

FORMATO = "pos_productos"
VERSION = 1


class ProductoBackupError(Exception):
    """Error de negocio al exportar/importar (mensaje apto para el usuario)."""


def _clave(texto) -> str:
    return " ".join(str(texto or "").split()).casefold()


def _texto(valor) -> str | None:
    limpio = " ".join(str(valor or "").split())
    return limpio or None


def _numero(valor, campo: str, exclusivo: bool = False) -> float:
    if valor is None or valor == "":
        valor = 0
    try:
        n = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{campo} no es un número válido")
    if n < 0 or (exclusivo and n == 0):
        raise ValueError(f"{campo} debe ser {'mayor a' if exclusivo else 'mayor o igual a'} 0")
    return n


class BackupProductosService:

    def __init__(self, db=None):
        if db is None:
            from database.connection import get_db
            db = get_db()
        self.db = db

    # ------------------------------------------------------------ Exportar
    def exportar(self, ruta) -> int:
        """Guarda los productos ACTIVOS en un archivo JSON. Devuelve cuántos."""
        conn = self.db.get_connection()

        presentaciones: dict[int, list] = {}
        for r in conn.execute(
            "SELECT producto_id, nombre, cantidad_unidades, precio FROM producto_presentaciones "
            "WHERE activo = 1 ORDER BY orden, id"
        ):
            presentaciones.setdefault(r["producto_id"], []).append({
                "nombre": r["nombre"],
                "cantidad_unidades": r["cantidad_unidades"],
                "precio": r["precio"],
            })

        productos = []
        for r in conn.execute(
            """SELECT p.*, c.nombre AS categoria, pr.nombre AS proveedor
               FROM productos p
               LEFT JOIN categorias c ON c.id = p.categoria_id
               LEFT JOIN proveedores pr ON pr.id = p.proveedor_id
               WHERE p.activo = 1 ORDER BY p.nombre"""
        ):
            productos.append({
                "nombre": r["nombre"],
                "categoria": r["categoria"],
                "marca": r["marca"],
                "unidad_medida": r["unidad_medida"],
                "precio_venta_actual": r["precio_venta_actual"],
                "costo_promedio_actual": r["costo_promedio_actual"],
                "stock_actual": r["stock_actual"],
                "stock_minimo": r["stock_minimo"],
                "proveedor": r["proveedor"],
                "presentaciones": presentaciones.get(r["id"], []),
            })

        datos = {
            "formato": FORMATO,
            "version": VERSION,
            "exportado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "categorias": [r["nombre"] for r in conn.execute(
                "SELECT nombre FROM categorias WHERE activo = 1 ORDER BY nombre")],
            "proveedores": [dict(r) for r in conn.execute(
                "SELECT nombre, documento, telefono, direccion FROM proveedores "
                "WHERE activo = 1 ORDER BY nombre")],
            "productos": productos,
        }
        Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(productos)

    # ------------------------------------------------------------ Importar
    def _leer_y_validar(self, ruta) -> dict:
        try:
            datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ProductoBackupError(f"No se pudo leer el archivo: {e}")

        if not isinstance(datos, dict) or datos.get("formato") != FORMATO:
            raise ProductoBackupError("El archivo no es una exportación de productos de este sistema.")
        if datos.get("version") != VERSION:
            raise ProductoBackupError(
                f"Versión de archivo no compatible ({datos.get('version')}). Se esperaba la {VERSION}."
            )
        if not isinstance(datos.get("productos"), list):
            raise ProductoBackupError("El archivo no tiene la lista de productos.")

        errores: list[str] = []
        productos = []
        for i, bruto in enumerate(datos["productos"], start=1):
            try:
                productos.append(self._normalizar(bruto))
            except ValueError as e:
                errores.append(f"Producto #{i}: {e}")
        if errores:
            resto = f" (y {len(errores) - 5} errores más)" if len(errores) > 5 else ""
            raise ProductoBackupError(
                "El archivo tiene datos inválidos, no se importó nada:\n- "
                + "\n- ".join(errores[:5]) + resto
            )

        proveedores = []
        for bruto in datos.get("proveedores") or []:
            if isinstance(bruto, dict) and _texto(bruto.get("nombre")):
                proveedores.append({k: _texto(bruto.get(k)) for k in ("nombre", "documento", "telefono", "direccion")})

        return {
            "productos": productos,
            "categorias": [c for c in (_texto(x) for x in datos.get("categorias") or []) if c],
            "proveedores": proveedores,
        }

    @staticmethod
    def _normalizar(bruto) -> dict:
        if not isinstance(bruto, dict):
            raise ValueError("formato incorrecto")
        nombre = _texto(bruto.get("nombre"))
        if not nombre:
            raise ValueError("falta el nombre")

        pres = []
        vistos = set()
        for p in bruto.get("presentaciones") or []:
            if not isinstance(p, dict):
                raise ValueError(f'"{nombre}": presentación con formato incorrecto')
            pn = _texto(p.get("nombre"))
            if not pn:
                raise ValueError(f'"{nombre}": una presentación no tiene nombre')
            if _clave(pn) in vistos:
                raise ValueError(f'"{nombre}": presentación repetida "{pn}"')
            vistos.add(_clave(pn))
            try:
                pres.append({
                    "nombre": pn,
                    "cantidad_unidades": _numero(p.get("cantidad_unidades"), "cantidad de la presentación", True),
                    "precio": _numero(p.get("precio"), "precio de la presentación"),
                })
            except ValueError as e:
                raise ValueError(f'"{nombre}" ({pn}): {e}')

        try:
            return {
                "nombre": nombre,
                "categoria": _texto(bruto.get("categoria")),
                "marca": _texto(bruto.get("marca")),
                "unidad_medida": _texto(bruto.get("unidad_medida")) or "unidad",
                "precio_venta_actual": _numero(bruto.get("precio_venta_actual"), "precio de venta"),
                "costo_promedio_actual": _numero(bruto.get("costo_promedio_actual"), "costo"),
                "stock_actual": _numero(bruto.get("stock_actual"), "stock"),
                "stock_minimo": _numero(bruto.get("stock_minimo"), "stock mínimo"),
                "proveedor": _texto(bruto.get("proveedor")),
                "presentaciones": pres,
            }
        except ValueError as e:
            raise ValueError(f'"{nombre}": {e}')

    def importar(self, ruta, usuario_id: int | None = None) -> dict:
        """Crea los productos que no existan. Devuelve
        {"creados": n, "omitidos": [nombres ya existentes o repetidos]}."""
        datos = self._leer_y_validar(ruta)
        conn = self.db.get_connection()

        existentes = {_clave(r["nombre"]) for r in conn.execute("SELECT nombre FROM productos")}
        categorias = {_clave(r["nombre"]): r["id"] for r in conn.execute("SELECT id, nombre FROM categorias")}
        proveedores = {_clave(r["nombre"]): r["id"] for r in conn.execute("SELECT id, nombre FROM proveedores")}
        datos_prov = {_clave(p["nombre"]): p for p in datos["proveedores"]}

        creados = 0
        omitidos: list[str] = []

        with self.db.transaction() as cur:
            def id_categoria(nombre):
                if not nombre:
                    return None
                clave = _clave(nombre)
                if clave not in categorias:
                    cur.execute("INSERT INTO categorias (nombre) VALUES (?)", (nombre,))
                    categorias[clave] = cur.lastrowid
                return categorias[clave]

            def id_proveedor(nombre):
                if not nombre:
                    return None
                clave = _clave(nombre)
                if clave not in proveedores:
                    extra = datos_prov.get(clave, {})
                    cur.execute(
                        "INSERT INTO proveedores (nombre, documento, telefono, direccion) VALUES (?, ?, ?, ?)",
                        (nombre, extra.get("documento"), extra.get("telefono"), extra.get("direccion")),
                    )
                    proveedores[clave] = cur.lastrowid
                return proveedores[clave]

            for nombre in datos["categorias"]:
                id_categoria(nombre)

            for p in datos["productos"]:
                clave = _clave(p["nombre"])
                if clave in existentes:
                    omitidos.append(p["nombre"])
                    continue
                existentes.add(clave)

                cur.execute(
                    """INSERT INTO productos
                       (nombre, categoria_id, marca, unidad_medida, precio_venta_actual,
                        costo_promedio_actual, stock_actual, stock_minimo, proveedor_id, activo)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (p["nombre"], id_categoria(p["categoria"]), p["marca"], p["unidad_medida"],
                     p["precio_venta_actual"], p["costo_promedio_actual"], p["stock_actual"],
                     p["stock_minimo"], id_proveedor(p["proveedor"])),
                )
                producto_id = cur.lastrowid

                cur.execute("INSERT INTO historial_precios (producto_id, precio_venta) VALUES (?, ?)",
                            (producto_id, p["precio_venta_actual"]))
                if p["costo_promedio_actual"] > 0:
                    cur.execute(
                        """INSERT INTO historial_costos
                           (producto_id, costo_unitario, costo_promedio_resultante, motivo)
                           VALUES (?, ?, ?, 'importacion')""",
                        (producto_id, p["costo_promedio_actual"], p["costo_promedio_actual"]),
                    )
                if p["stock_actual"] > 0:
                    # El stock inicial queda registrado en el kardex como ajuste.
                    cur.execute(
                        """INSERT INTO inventario_movimientos
                           (producto_id, tipo, cantidad, referencia_tipo, referencia_id, usuario_id)
                           VALUES (?, 'ajuste', ?, 'ajuste', NULL, ?)""",
                        (producto_id, p["stock_actual"], usuario_id),
                    )
                for orden, pr in enumerate(p["presentaciones"]):
                    cur.execute(
                        """INSERT INTO producto_presentaciones
                           (producto_id, nombre, cantidad_unidades, precio, orden, activo)
                           VALUES (?, ?, ?, ?, ?, 1)""",
                        (producto_id, pr["nombre"], pr["cantidad_unidades"], pr["precio"], orden),
                    )
                creados += 1

        return {"creados": creados, "omitidos": omitidos}
