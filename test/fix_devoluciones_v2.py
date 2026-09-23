"""Aplica el arreglo de devoluciones a tu copia local del repo.

Uso (desde la carpeta pos_system, app cerrada):
    python aplicar_fix_devoluciones.py

- Edita services/venta_service.py y repositories/venta_repository.py.
- Guarda copias .bak de ambos antes de tocarlos.
- Respeta los saltos de linea de tu archivo (Windows CRLF o Linux LF).
- Si algo no coincide con lo esperado, NO modifica nada y te avisa.
- Si ya esta aplicado, no hace nada.
"""
import shutil
import sys
from pathlib import Path

REPO_VENTA = Path("repositories/venta_repository.py")
SERV_VENTA = Path("services/venta_service.py")

NUEVO_REPO = '''    def crear_devolucion(self, cursor, venta_id: int, producto_id: int, cantidad: float,
                          motivo: str, usuario_id: int) -> int:
        """Recibe un cursor externo: la devolucion y la reposicion de stock
        deben ocurrir en la MISMA transaccion (todo o nada)."""
        cursor.execute(
            """INSERT INTO devoluciones (venta_id, producto_id, cantidad, motivo, usuario_id)
               VALUES (?, ?, ?, ?, ?)""",
            (venta_id, producto_id, cantidad, motivo, usuario_id),
        )
        return cursor.lastrowid

    def cantidad_devuelta(self, cursor, venta_id: int, producto_id: int) -> float:
        """Total ya devuelto de un producto en una venta (unidad base)."""
        cursor.execute(
            """SELECT COALESCE(SUM(cantidad), 0) AS total
               FROM devoluciones WHERE venta_id = ? AND producto_id = ?""",
            (venta_id, producto_id),
        )
        return cursor.fetchone()["total"]

'''

NUEVO_ANULAR = '''        lineas = self.venta_repo.obtener_lineas(venta_id)

        # Cantidad vendida por producto (una venta puede repetir un producto
        # en varias lineas).
        vendido: dict[int, float] = {}
        for linea in lineas:
            vendido[linea["producto_id"]] = vendido.get(linea["producto_id"], 0.0) + linea["cantidad"]

        with self.db.transaction() as cur:
            self.venta_repo.anular_venta(cur, venta_id)

            for producto_id, cantidad_vendida in vendido.items():
                # Lo que ya volvio al stock por devoluciones no se repone otra vez.
                ya_devuelto = self.venta_repo.cantidad_devuelta(cur, venta_id, producto_id)
                a_reponer = round(cantidad_vendida - ya_devuelto, 6)
                if a_reponer <= 0:
                    continue

                cur.execute("SELECT stock_actual FROM productos WHERE id = ?", (producto_id,))
                stock_actual = cur.fetchone()["stock_actual"]
                cur.execute("UPDATE productos SET stock_actual = ? WHERE id = ?",
                            (stock_actual + a_reponer, producto_id))

                self.inventario_repo.registrar_movimiento(
                    cur, producto_id, "entrada", a_reponer,
                    "anulacion", venta_id, usuario_id,
                )

'''

NUEVO_DEVOLVER = '''    def registrar_devolucion(self, venta_id: int, producto_id: int, cantidad: float,
                              motivo: str, usuario_id: int) -> int:
        if cantidad <= 0:
            raise VentaError("La cantidad a devolver debe ser mayor a cero.")

        venta = self.venta_repo.obtener_venta(venta_id)
        if not venta:
            raise VentaError("Venta no encontrada.")
        if venta["estado"] != "completada":
            raise VentaError("No se puede devolver productos de una venta anulada.")

        vendido = sum(
            l["cantidad"] for l in self.venta_repo.obtener_lineas(venta_id)
            if l["producto_id"] == producto_id
        )
        if vendido <= 0:
            raise VentaError("Ese producto no pertenece a la venta indicada.")

        # Validacion y escritura en la MISMA transaccion: si dos devoluciones
        # llegan seguidas, la segunda ya ve lo que devolvio la primera.
        with self.db.transaction() as cur:
            ya_devuelto = self.venta_repo.cantidad_devuelta(cur, venta_id, producto_id)
            disponible = round(vendido - ya_devuelto, 6)
            if cantidad > disponible:
                if disponible <= 0:
                    raise VentaError("Este producto ya fue devuelto por completo.")
                raise VentaError(
                    f"Solo se puede devolver hasta {disponible:g} "
                    f"(vendido: {vendido:g}, ya devuelto: {ya_devuelto:g})."
                )

            devolucion_id = self.venta_repo.crear_devolucion(
                cur, venta_id, producto_id, cantidad, motivo, usuario_id
            )
            cur.execute("SELECT stock_actual FROM productos WHERE id = ?", (producto_id,))
            stock_actual = cur.fetchone()["stock_actual"]
            cur.execute("UPDATE productos SET stock_actual = ? WHERE id = ?",
                        (stock_actual + cantidad, producto_id))
            self.inventario_repo.registrar_movimiento(
                cur, producto_id, "entrada", cantidad, "devolucion", venta_id, usuario_id,
            )

        return devolucion_id

'''


def leer(ruta: Path):
    crudo = ruta.read_bytes().decode("utf-8")
    crlf = "\r\n" in crudo
    return crudo.replace("\r\n", "\n"), crlf


def escribir(ruta: Path, texto: str, crlf: bool) -> None:
    if crlf:
        texto = texto.replace("\n", "\r\n")
    ruta.write_bytes(texto.encode("utf-8"))


def entre(texto: str, inicio: str, fin: str, nombre: str):
    a = texto.find(inicio)
    b = texto.find(fin, a + 1) if a != -1 else -1
    if a == -1 or b == -1:
        raise ValueError(f"No encontre el bloque '{nombre}' (tu archivo es distinto al esperado).")
    return a, b


def main() -> int:
    print("== Aplicando arreglo de devoluciones ==")
    print(f"Carpeta actual: {Path.cwd()}")
    for r in (REPO_VENTA, SERV_VENTA):
        if not r.exists():
            print(f"No encuentro {r}. Ejecuta este script desde la carpeta pos_system.")
            return 1

    repo, crlf_repo = leer(REPO_VENTA)
    serv, crlf_serv = leer(SERV_VENTA)

    if "def cantidad_devuelta" in repo and "ya_devuelto" in serv:
        print("El arreglo ya estaba aplicado. No se cambio nada.")
        return 0

    try:
        a, b = entre(repo, "    def crear_devolucion(", "    def actualizar_cliente(", "crear_devolucion")
        repo_nuevo = repo[:a] + NUEVO_REPO + repo[b:]

        a, b = entre(
            serv,
            "        lineas = self.venta_repo.obtener_lineas(venta_id)\n\n        with self.db.transaction() as cur:\n            self.venta_repo.anular_venta",
            "            # Solo se revierte el dinero de caja",
            "anular_venta",
        )
        serv_nuevo = serv[:a] + NUEVO_ANULAR + serv[b:]

        a, b = entre(serv_nuevo, "    def registrar_devolucion(", "    def obtener_venta_con_lineas(", "registrar_devolucion")
        serv_nuevo = serv_nuevo[:a] + NUEVO_DEVOLVER + serv_nuevo[b:]

        compile(repo_nuevo, str(REPO_VENTA), "exec")
        compile(serv_nuevo, str(SERV_VENTA), "exec")
    except (ValueError, SyntaxError) as e:
        print(f"ALTO: {e}\nNo se modifico nada. Mandame estos dos archivos y lo reviso.")
        return 2

    for r in (REPO_VENTA, SERV_VENTA):
        shutil.copy2(r, str(r) + ".bak")
    escribir(REPO_VENTA, repo_nuevo, crlf_repo)
    escribir(SERV_VENTA, serv_nuevo, crlf_serv)
    print("Listo. Arreglo aplicado en:")
    print(f"  - {REPO_VENTA}  (copia: {REPO_VENTA}.bak)")
    print(f"  - {SERV_VENTA}  (copia: {SERV_VENTA}.bak)")
    print("Para deshacer: borra los archivos y quita el '.bak' del nombre de las copias.")
    return 0


if __name__ == "__main__":
    sys.exit(main())